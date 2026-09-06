package kb.harness;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class StubsTest {

    @Test
    void countBodyIsAWireMockRequestPattern() {
        assertEquals("{\"method\":\"GET\",\"urlPath\":\"/pricing/rates/GB\"}",
            Stubs.countBody("GET", "/pricing/rates/GB", null));
        assertEquals("{\"method\":\"POST\",\"urlPath\":\"/pricing/quotes\","
                + "\"bodyPatterns\":[{\"contains\":\"EXT-\\\"quoted\\\"\"}]}",
            Stubs.countBody("POST", "/pricing/quotes", "EXT-\"quoted\""));
    }

    @Test
    void readCountReadsTheCountField() {
        assertEquals(3, Stubs.readCount("{\"count\":3}"));
        assertEquals(-1, Stubs.readCount("{}"));
    }
}
