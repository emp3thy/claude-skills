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
        Results results = Runner.path("classpath:features")
            .tags("~@known-defect")
            .outputCucumberJson(true)
            .outputJunitXml(true)
            .parallel(threads);
        assertEquals(0, results.getFailCount(), results.getErrorMessages());
    }
}
