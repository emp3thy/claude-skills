package kb.harness;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
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
    private static final Map<String, BlockingQueue<Map<String, Object>>> INBOX = new ConcurrentHashMap<>();
    private static final Map<String, Session> CONSUMER_SESSIONS = new ConcurrentHashMap<>();
    private static final Map<String, MessageConsumer> CONSUMERS = new ConcurrentHashMap<>();
    private static Connection connection;
    private static Session producerSession;

    private Jms() {
    }

    /** Subscribes once per destination. Idempotent: later calls do not drop queued messages. */
    public static synchronized void watch(String destination) {
        try {
            ensureConnection();
            INBOX.computeIfAbsent(destination, d -> new LinkedBlockingQueue<>());
            if (!CONSUMERS.containsKey(destination)) {
                Session consumerSession = connection.createSession(false, Session.AUTO_ACKNOWLEDGE);
                MessageConsumer consumer = consumerSession.createConsumer(destinationFor(consumerSession, destination));
                consumer.setMessageListener(message -> INBOX.get(destination).offer(toMap(message)));
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
     * go back to the inbox for other scenarios. Returns {body, properties, messageId}.
     */
    public static Map<String, Object> await(String destination, long timeoutMs, Map<String, Object> matchMap) {
        BlockingQueue<Map<String, Object>> queue = INBOX.get(destination);
        if (queue == null) {
            throw new IllegalStateException("Jms.await(" + destination + ") called without Jms.watch first");
        }
        Map<String, Object> found = takeMatching(queue, System.currentTimeMillis() + timeoutMs, matchMap);
        if (found == null) {
            throw new AssertionError("no message on " + destination
                + (matchMap == null ? "" : " matching " + matchMap) + " within " + timeoutMs + "ms");
        }
        return found;
    }

    /**
     * Polls {@code queue} until {@code deadlineMillis} for a message matching {@code matchMap} (any
     * message when null). Non-matching messages are put back behind whatever arrived meanwhile;
     * order is not preserved. Returns null on timeout.
     */
    static Map<String, Object> takeMatching(BlockingQueue<Map<String, Object>> queue, long deadlineMillis,
                                            Map<String, Object> matchMap) {
        List<Map<String, Object>> others = new ArrayList<>();
        try {
            while (true) {
                long remaining = deadlineMillis - System.currentTimeMillis();
                Map<String, Object> message = remaining > 0 ? queue.poll(remaining, TimeUnit.MILLISECONDS) : null;
                if (message == null) {
                    queue.addAll(others);
                    return null;
                }
                if (matchMap == null || matches(message.get("body"), matchMap)) {
                    queue.addAll(others);
                    return message;
                }
                others.add(message);
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(e);
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

    private static void ensureConnection() throws JMSException {
        if (connection != null) {
            return;
        }
        JmsConnectionFactory factory = new JmsConnectionFactory(Containers.amqUser(), Containers.amqPassword(), Containers.jmsUrl());
        connection = factory.createConnection();
        connection.start();
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
