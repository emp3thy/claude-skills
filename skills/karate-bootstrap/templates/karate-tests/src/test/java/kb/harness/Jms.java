package kb.harness;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Enumeration;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.LinkedList;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import javax.jms.Connection;
import javax.jms.Destination;
import javax.jms.JMSException;
import javax.jms.Message;
import javax.jms.MessageConsumer;
import javax.jms.MessageProducer;
import javax.jms.Session;
import javax.jms.TextMessage;
import org.apache.qpid.jms.JmsConnectionFactory;

/**
 * Artemis over AMQP 1.0 (Qpid JMS), exposed to Karate as {@code Jms}. One consumer per destination
 * for the whole JVM; every scenario takes its own message by content with the match form of await.
 * A session with a registered listener belongs to the provider's delivery thread for as long as
 * that listener is set, so each listener-driven consumer gets its own {@link Session} and
 * publishing uses one session of its own, never a listener's session.
 */
public final class Jms {

    private static final ObjectMapper JSON = new ObjectMapper();
    private static final Map<String, Inbox> INBOX = new ConcurrentHashMap<>();
    private static final Map<String, Session> CONSUMER_SESSIONS = new ConcurrentHashMap<>();
    private static final Map<String, MessageConsumer> CONSUMERS = new ConcurrentHashMap<>();
    private static Connection connection;
    private static Session producerSession;

    /** The messages delivered on one destination. Its own monitor guards the list. */
    static final class Inbox {
        final LinkedList<Map<String, Object>> messages = new LinkedList<>();
    }

    private Jms() {
    }

    /** Subscribes once per destination. Idempotent: later calls do not drop queued messages. */
    public static synchronized void watch(String destination) {
        try {
            ensureConnection();
            Inbox inbox = INBOX.computeIfAbsent(destination, d -> new Inbox());
            if (!CONSUMERS.containsKey(destination)) {
                Session consumerSession = connection.createSession(false, Session.AUTO_ACKNOWLEDGE);
                MessageConsumer consumer = consumerSession.createConsumer(destinationFor(consumerSession, destination));
                consumer.setMessageListener(message -> {
                    Map<String, Object> mapped = toMap(message);
                    synchronized (inbox) {
                        inbox.messages.add(mapped);
                        inbox.notifyAll();
                    }
                });
                CONSUMER_SESSIONS.put(destination, consumerSession);
                CONSUMERS.put(destination, consumer);
            }
        } catch (JMSException e) {
            throw new IllegalStateException("Jms.watch failed for " + destination + ": " + e.getMessage(), e);
        }
    }

    /** Next message on the destination. Parallel scenarios use the match form instead. */
    public static Map<String, Object> await(String destination, long timeoutMs) {
        return await(destination, timeoutMs, null);
    }

    /**
     * The first message whose body contains every key and value of {@code matchMap}; other messages
     * stay in the inbox, in order, for other scenarios. Returns {body, properties, messageId}.
     */
    public static Map<String, Object> await(String destination, long timeoutMs, Map<String, Object> matchMap) {
        Inbox inbox = INBOX.get(destination);
        if (inbox == null) {
            throw new IllegalStateException("Jms.await(" + destination + ") called without Jms.watch first");
        }
        Map<String, Object> found = takeMatching(inbox, System.currentTimeMillis() + timeoutMs, matchMap);
        if (found == null) {
            throw new AssertionError("no message on " + destination
                + (matchMap == null ? "" : " matching " + matchMap) + " within " + timeoutMs + "ms");
        }
        return found;
    }

    /**
     * Scans {@code inbox} under its monitor until {@code deadlineMillis} for the first message
     * matching {@code matchMap} (any message when null) and removes only that one; every other
     * message stays where it is, in arrival order, visible to the other waiters. Returns null on
     * timeout.
     */
    static Map<String, Object> takeMatching(Inbox inbox, long deadlineMillis, Map<String, Object> matchMap) {
        synchronized (inbox) {
            try {
                while (true) {
                    Iterator<Map<String, Object>> waiting = inbox.messages.iterator();
                    while (waiting.hasNext()) {
                        Map<String, Object> candidate = waiting.next();
                        if (matchMap == null || matches(candidate.get("body"), matchMap)) {
                            waiting.remove();
                            return candidate;
                        }
                    }
                    long remaining = deadlineMillis - System.currentTimeMillis();
                    if (remaining <= 0) {
                        return null;
                    }
                    inbox.wait(remaining);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(e);
            }
        }
    }

    public static synchronized void publish(String destination, Object body, Map<String, Object> headers) {
        try {
            ensureConnection();
            if (producerSession == null) {
                producerSession = connection.createSession(false, Session.AUTO_ACKNOWLEDGE);
            }
            String text = body instanceof String ? (String) body : JSON.writeValueAsString(body);
            TextMessage message = producerSession.createTextMessage(text);
            if (headers != null) {
                for (Map.Entry<String, Object> h : headers.entrySet()) {
                    message.setObjectProperty(h.getKey(), h.getValue());
                }
            }
            try (MessageProducer producer = producerSession.createProducer(destinationFor(producerSession, destination))) {
                producer.send(message);
            }
        } catch (JMSException | JsonProcessingException e) {
            throw new IllegalStateException("Jms.publish failed for " + destination + ": " + e.getMessage(), e);
        }
    }

    /**
     * Closes every consumer session, the producer session and the connection, then forgets them.
     * Called from the {@link Containers} shutdown hook, which matters when Ryuk is disabled.
     */
    public static synchronized void close() {
        for (Map.Entry<String, Session> entry : CONSUMER_SESSIONS.entrySet()) {
            try {
                entry.getValue().close();
            } catch (JMSException e) {
                System.err.println("Jms.close: consumer session for " + entry.getKey() + ": " + e.getMessage());
            }
        }
        if (producerSession != null) {
            try {
                producerSession.close();
            } catch (JMSException e) {
                System.err.println("Jms.close: producer session: " + e.getMessage());
            }
            producerSession = null;
        }
        if (connection != null) {
            try {
                connection.close();
            } catch (JMSException e) {
                System.err.println("Jms.close: connection: " + e.getMessage());
            }
            connection = null;
        }
        CONSUMER_SESSIONS.clear();
        CONSUMERS.clear();
        INBOX.clear();
    }

    /** True when {@code body} is a map holding every entry of {@code matchMap} with an equal value. */
    static boolean matches(Object body, Map<String, Object> matchMap) {
        if (matchMap == null || matchMap.isEmpty()) {
            return true;
        }
        if (!(body instanceof Map)) {
            return false;
        }
        Map<?, ?> map = (Map<?, ?>) body;
        for (Map.Entry<String, Object> expected : matchMap.entrySet()) {
            if (!map.containsKey(expected.getKey())) {
                return false;
            }
            Object actual = map.get(expected.getKey());
            if (!Objects.equals(String.valueOf(actual), String.valueOf(expected.getValue()))) {
                return false;
            }
        }
        return true;
    }

    /** Assigns the field only once the connection is started, so a failed start is retried. */
    private static void ensureConnection() throws JMSException {
        if (connection != null) {
            return;
        }
        JmsConnectionFactory factory = new JmsConnectionFactory(Containers.amqUser(), Containers.amqPassword(), Containers.jmsUrl());
        Connection started = factory.createConnection();
        started.start();
        connection = started;
    }

    private static Destination destinationFor(Session session, String name) throws JMSException {
        return Containers.isQueue(name) ? session.createQueue(name) : session.createTopic(name);
    }

    private static Map<String, Object> toMap(Message message) {
        Map<String, Object> out = new LinkedHashMap<>();
        try {
            Object body = message instanceof TextMessage ? ((TextMessage) message).getText() : message.getBody(Object.class);
            if (body instanceof String) {
                String text = (String) body;
                try {
                    body = JSON.readValue(text, Object.class);
                } catch (JsonProcessingException notJson) {
                    body = text;
                }
            }
            out.put("body", body);
            Map<String, Object> properties = new LinkedHashMap<>();
            Enumeration<?> names = message.getPropertyNames();
            while (names.hasMoreElements()) {
                String name = String.valueOf(names.nextElement());
                properties.put(name, message.getObjectProperty(name));
            }
            out.put("properties", properties);
            out.put("messageId", message.getJMSMessageID());
        } catch (JMSException e) {
            throw new IllegalStateException(e);
        }
        return out;
    }
}
