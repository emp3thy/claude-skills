package kb.harness;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Typed view over {@code kb-runtime.json}, the only repo-specific file in this module.
 * Written by karate-bootstrap's kb_scaffold.py; schema version 1 (design spec 5.5).
 */
public final class KbRuntime {

    public static final String RESOURCE = "/kb-runtime.json";
    private static volatile KbRuntime instance;
    private final JsonNode root;

    private KbRuntime(JsonNode root) {
        this.root = root;
    }

    public static KbRuntime load() {
        KbRuntime local = instance;
        if (local == null) {
            synchronized (KbRuntime.class) {
                local = instance;
                if (local == null) {
                    try (InputStream in = KbRuntime.class.getResourceAsStream(RESOURCE)) {
                        if (in == null) {
                            throw new IllegalStateException(RESOURCE + " not on the test classpath");
                        }
                        local = new KbRuntime(new ObjectMapper().readTree(in));
                        instance = local;
                    } catch (IOException e) {
                        throw new UncheckedIOException(e);
                    }
                }
            }
        }
        return local;
    }

    public String repo() { return root.path("repo").asText("unknown"); }
    public String stack() { return root.path("stack").asText("unknown"); }
    public String repoRootRel() { return root.path("app").path("repoRootRel").asText(".."); }
    public String dockerfileRel() { return root.path("app").path("dockerfileRel").asText("Dockerfile"); }
    public int appPort() { return root.path("app").path("port").asInt(8080); }

    /** Readiness path, or null when the harness must fall back to a port wait. */
    public String readinessPath() {
        JsonNode node = root.path("app").path("readinessPath");
        return node.isNull() || node.isMissingNode() ? null : node.asText();
    }

    public boolean serverless() { return root.path("app").path("serverless").asBoolean(false); }
    public int startupTimeoutSeconds() { return root.path("app").path("startupTimeoutSeconds").asInt(120); }

    /** Env entries as ordered maps with keys name, role, value (value still holds runtime tokens such as db.host). */
    public List<Map<String, String>> env() {
        List<Map<String, String>> out = new ArrayList<>();
        for (JsonNode item : root.path("env")) {
            Map<String, String> entry = new LinkedHashMap<>();
            entry.put("name", item.path("name").asText());
            entry.put("role", item.path("role").asText("passthrough"));
            entry.put("value", item.path("value").asText(""));
            out.add(entry);
        }
        return out;
    }

    public String dbName() { return root.path("db").path("name").asText("app"); }
    public String dbUser() { return root.path("db").path("user").asText("app"); }
    public String dbPassword() { return root.path("db").path("password").asText("app"); }
    public String migrationsStrategy() { return root.path("migrations").path("strategy").asText("migration-container"); }

    public String migrationsImage() {
        JsonNode node = root.path("migrations").path("image");
        return node.isNull() || node.isMissingNode() ? null : node.asText();
    }

    public Map<String, String> migrationsEnv() {
        Map<String, String> out = new LinkedHashMap<>();
        root.path("migrations").path("env").fields().forEachRemaining(e -> out.put(e.getKey(), e.getValue().asText()));
        return out;
    }

    public String amqUser() { return root.path("amq").path("user").asText("artemis"); }
    public String amqPassword() { return root.path("amq").path("password").asText("artemis"); }
    public List<String> amqQueues() { return texts(root.path("amq").path("queues")); }
    public List<String> amqTopics() { return texts(root.path("amq").path("topics")); }

    public List<String> downstreamNames() {
        List<String> out = new ArrayList<>();
        for (JsonNode item : root.path("downstreams")) {
            out.add(item.path("name").asText());
        }
        return out;
    }

    public String authMode() { return root.path("auth").path("mode").asText("none"); }
    public String authKey() { return root.path("auth").path("key").asText(null); }
    public String authValue() { return root.path("auth").path("value").asText(null); }
    public List<String> authIssuerKeys() { return texts(root.path("auth").path("issuerKeys")); }

    private static List<String> texts(JsonNode array) {
        List<String> out = new ArrayList<>();
        for (JsonNode item : array) {
            out.add(item.asText());
        }
        return out;
    }
}
