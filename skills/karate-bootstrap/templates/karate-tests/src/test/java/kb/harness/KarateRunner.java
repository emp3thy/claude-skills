package kb.harness;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.intuit.karate.Results;
import com.intuit.karate.Runner;
import org.junit.jupiter.api.Test;

/** JUnit 5 entry point. -Dkb.threads=N (default 4), -Dkb.skipContainers=true for container-free runs. */
class KarateRunner {

    @Test
    void karate() {
        int threads = Integer.getInteger("kb.threads", 4);
        boolean skipContainers = Boolean.getBoolean("kb.skipContainers");
        // Karate ANDs separate tag arguments, so a container-free run keeps only @harness features.
        String[] tags = skipContainers
            ? new String[] {"~@known-defect", "@harness"}
            : new String[] {"~@known-defect"};
        Results results = Runner.path("classpath:features")
            .tags(tags)
            .outputCucumberJson(true)
            .outputJunitXml(true)
            .parallel(threads);
        if (!skipContainers) {
            try {
                Stubs.unmatched();
            } catch (RuntimeException e) {
                System.err.println("stubs-unmatched.json not written: " + e.getMessage());
            }
        }
        assertEquals(0, results.getFailCount(), results.getErrorMessages());
    }
}
