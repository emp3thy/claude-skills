package kb.harness;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import org.junit.jupiter.api.Test;

/** Inbox logic only: no broker is involved. */
class JmsTest {

    private static Map<String, Object> message(String dealId) {
        return Map.of("body", Map.of("dealId", dealId), "properties", Map.of(), "messageId", "id-" + dealId);
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
    void takeMatchingReturnsTheMatchingMessageAndRequeuesTheOthers() {
        BlockingQueue<Map<String, Object>> queue = new LinkedBlockingQueue<>();
        queue.add(message("d-1"));
        queue.add(message("d-2"));
        queue.add(message("d-3"));
        Map<String, Object> found = Jms.takeMatching(queue, System.currentTimeMillis() + 1000, Map.of("dealId", "d-2"));
        assertEquals("id-d-2", found.get("messageId"));
        // Skipped messages go back behind anything that arrived meanwhile; order is not preserved,
        // which is fine because every scenario matches by content, never by position.
        assertEquals(2, queue.size());
        Set<Object> remaining = new HashSet<>();
        remaining.add(queue.poll().get("messageId"));
        remaining.add(queue.poll().get("messageId"));
        assertEquals(Set.of("id-d-1", "id-d-3"), remaining);
    }

    @Test
    void takeMatchingTimesOutWithNullAndKeepsTheInbox() {
        BlockingQueue<Map<String, Object>> queue = new LinkedBlockingQueue<>();
        queue.add(message("d-1"));
        assertNull(Jms.takeMatching(queue, System.currentTimeMillis() + 150, Map.of("dealId", "zzz")));
        assertEquals(1, queue.size());
    }

    @Test
    void takeMatchingWithoutAMapTakesTheFirstMessage() {
        BlockingQueue<Map<String, Object>> queue = new LinkedBlockingQueue<>();
        queue.add(message("d-1"));
        queue.add(message("d-2"));
        assertEquals("id-d-1", Jms.takeMatching(queue, System.currentTimeMillis() + 1000, null).get("messageId"));
        assertEquals(1, queue.size());
    }
}
