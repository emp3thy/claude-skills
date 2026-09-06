package kb.harness;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.wait.strategy.HostPortWaitStrategy;
import org.testcontainers.containers.wait.strategy.HttpWaitStrategy;

/** Pure helpers only: nothing here talks to a container engine. */
class ContainersTest {

    @Test
    void substituteReplacesEveryKnownTokenAndLeavesUnknownOnes() {
        Map<String, String> values = Map.of("db.host", "db", "db.port", "5432", "db.name", "shipments");
        assertEquals("jdbc:postgresql://db:5432/shipments",
            Containers.substitute("jdbc:postgresql://{{db.host}}:{{db.port}}/{{db.name}}", values));
        assertEquals("{{unknown}} stays", Containers.substitute("{{unknown}} stays", values));
        assertEquals("false", Containers.substitute("false", values));
    }

    @Test
    void tokenValuesCoverTheSpecTokens() {
        Map<String, String> values = Containers.tokenValues(KbRuntime.load());
        assertEquals("db", values.get("db.host"));
        assertEquals("5432", values.get("db.port"));
        assertEquals("artemis", values.get("amq.host"));
        assertEquals("5672", values.get("amq.amqpPort"));
        assertEquals("61616", values.get("amq.corePort"));
        assertEquals("61613", values.get("amq.stompPort"));
        assertEquals("http://wiremock:8080", values.get("stubs.url"));
        assertEquals("http://wiremock:8080/auth", values.get("auth.url"));
    }

    @Test
    void artemisExtraArgsListQueuesAsAnycastAndTopicsAsMulticast() {
        assertEquals("--http-host 0.0.0.0 --relax-jolokia --queues a,b --addresses t",
            Containers.artemisExtraArgs(List.of("a", "b"), List.of("t")));
        assertEquals("--http-host 0.0.0.0 --relax-jolokia",
            Containers.artemisExtraArgs(List.of(), List.of()));
    }

    @Test
    void appWaitFallsBackToAPortWaitWithoutAReadinessPath() {
        assertInstanceOf(HostPortWaitStrategy.class, Containers.appWait(null, 8080, 120, false));
        assertInstanceOf(HttpWaitStrategy.class, Containers.appWait("/health/ready", 8080, 120, true));
    }
}
