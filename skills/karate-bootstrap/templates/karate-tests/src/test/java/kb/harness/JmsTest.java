package kb.harness;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

/** Inbox logic only: no broker is involved. */
class JmsTest {

    private static Map<String, Object> message(String dealId) {
        return Map.of("body", Map.of("dealId", dealId), "properties", Map.of(), "messageId", "id-" + dealId);
    }

    private static Jms.Inbox inboxOf(String... dealIds) {
        Jms.Inbox inbox = new Jms.Inbox();
        for (String dealId : dealIds) {
            inbox.messages.add(message(dealId));
        }
        return inbox;
    }

    @Test
    void matchesRequiresEveryKeyAndValue() {
        Map<String, Object> body = Map.of("dealId", "d-1", "status", "PENDING", "n", 2);
        assertTrue(Jms.matches(body, Map.of("dealId", "d-1")));
        assertTrue(Jms.matches(body, Map.of("dealId", "d-1", "n", 2)));
        assertFalse(Jms.matches(body, Map.of("dealId", "d-2")));
        assertFalse(Jms.matches(body, Map.of("missing", "x")));
        assertFalse(Jms.matches("not a map", Map.of("dealId", "d-1")));
        assertTrue(Jms.matches(List.of(1), Map.of()));
    }

    @Test
    void takeMatchingReturnsTheMatchingMessageAndLeavesTheOthersInOrder() {
        Jms.Inbox inbox = inboxOf("d-1", "d-2", "d-3");
        Map<String, Object> found = Jms.takeMatching(inbox, System.currentTimeMillis() + 1000, Map.of("dealId", "d-2"));
        assertEquals("id-d-2", found.get("messageId"));
        assertEquals(List.of("id-d-1", "id-d-3"),
            inbox.messages.stream().map(m -> m.get("messageId")).toList());
    }

    @Test
    void takeMatchingTimesOutWithNullAndKeepsTheInbox() {
        Jms.Inbox inbox = inboxOf("d-1");
        assertNull(Jms.takeMatching(inbox, System.currentTimeMillis() + 150, Map.of("dealId", "zzz")));
        assertEquals(1, inbox.messages.size());
    }

    @Test
    void takeMatchingWithoutAMapTakesTheFirstMessage() {
        Jms.Inbox inbox = inboxOf("d-1", "d-2");
        assertEquals("id-d-1", Jms.takeMatching(inbox, System.currentTimeMillis() + 1000, null).get("messageId"));
        assertEquals(1, inbox.messages.size());
    }

    @Test
    void concurrentWaitersEachTakeTheirOwnMessage() throws InterruptedException {
        Jms.Inbox inbox = new Jms.Inbox();
        AtomicReference<Map<String, Object>> forOne = new AtomicReference<>();
        AtomicReference<Map<String, Object>> forTwo = new AtomicReference<>();
        long deadline = System.currentTimeMillis() + 2000;
        Thread one = new Thread(() -> forOne.set(Jms.takeMatching(inbox, deadline, Map.of("dealId", "d-1"))));
        Thread two = new Thread(() -> forTwo.set(Jms.takeMatching(inbox, deadline, Map.of("dealId", "d-2"))));
        one.start();
        two.start();
        Thread.sleep(100);
        synchronized (inbox) {
            inbox.messages.add(message("d-2"));
            inbox.messages.add(message("d-1"));
            inbox.notifyAll();
        }
        one.join(5000);
        two.join(5000);
        assertEquals("id-d-1", forOne.get().get("messageId"));
        assertEquals("id-d-2", forTwo.get().get("messageId"));
        assertTrue(inbox.messages.isEmpty());
    }
}
