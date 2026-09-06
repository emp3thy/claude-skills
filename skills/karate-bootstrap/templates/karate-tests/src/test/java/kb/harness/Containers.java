package kb.harness;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.Network;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.containers.output.OutputFrame;
import org.testcontainers.containers.output.Slf4jLogConsumer;
import org.testcontainers.containers.startupcheck.OneShotStartupCheckStrategy;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.containers.wait.strategy.WaitStrategy;
import org.testcontainers.images.builder.ImageFromDockerfile;
import org.testcontainers.utility.DockerImageName;

/**
 * The test topology (design spec 4.2): one network; Postgres, Artemis, WireMock, the one-shot
 * db-manager, then the app built from the repo's Dockerfile. Started once per JVM, lazily,
 * from karate-config.js. Every value that differs between repos comes from kb-runtime.json.
 */
public final class Containers {

    private static final Logger LOG = LoggerFactory.getLogger(Containers.class);

    static final String DB_ALIAS = "db";
    static final String AMQ_ALIAS = "artemis";
    static final String STUBS_ALIAS = "wiremock";
    static final String APP_ALIAS = "app";
    static final int DB_PORT = 5432;
    static final int AMQ_CORE_PORT = 61616;
    static final int AMQ_AMQP_PORT = 5672;
    static final int AMQ_STOMP_PORT = 61613;
    static final int AMQ_HTTP_PORT = 8161;
    static final int STUBS_PORT = 8080;

    static final DockerImageName POSTGRES_IMAGE = DockerImageName.parse("postgres:16-alpine");
    static final DockerImageName ARTEMIS_IMAGE = DockerImageName.parse("apache/activemq-artemis:2.44.0-alpine");
    static final DockerImageName WIREMOCK_IMAGE = DockerImageName.parse("wiremock/wiremock:3.13.2-alpine");

    private static final Path TARGET = Paths.get("target");

    private static boolean started;
    private static RuntimeException failure;
    private static Network network;
    private static PostgreSQLContainer<?> postgres;
    private static GenericContainer<?> artemis;
    private static GenericContainer<?> wiremock;
    private static GenericContainer<?> app;
    private static KbRuntime runtime;

    private Containers() {
    }

    public static synchronized void start() {
        if (started) {
            return;
        }
        if (failure != null) {
            throw new IllegalStateException("topology failed earlier: " + failure.getMessage(), failure);
        }
        try {
            runtime = KbRuntime.load();
            network = Network.newNetwork();

            postgres = new PostgreSQLContainer<>(POSTGRES_IMAGE)
                .withNetwork(network)
                .withNetworkAliases(DB_ALIAS)
                .withDatabaseName(runtime.dbName())
                .withUsername(runtime.dbUser())
                .withPassword(runtime.dbPassword())
                .withLogConsumer(fileLog("postgres"));
            postgres.start();

            artemis = new GenericContainer<>(ARTEMIS_IMAGE)
                .withNetwork(network)
                .withNetworkAliases(AMQ_ALIAS)
                .withExposedPorts(AMQ_CORE_PORT, AMQ_AMQP_PORT, AMQ_STOMP_PORT, AMQ_HTTP_PORT)
                .withEnv("ARTEMIS_USER", runtime.amqUser())
                .withEnv("ARTEMIS_PASSWORD", runtime.amqPassword())
                .withEnv("ANONYMOUS_LOGIN", "false")
                .withEnv("EXTRA_ARGS", artemisExtraArgs(runtime.amqQueues(), runtime.amqTopics()))
                .waitingFor(Wait.forLogMessage(".*AMQ221007.*\\n", 1).withStartupTimeout(Duration.ofSeconds(120)))
                .withLogConsumer(fileLog("artemis"));
            artemis.start();

            wiremock = new GenericContainer<>(WIREMOCK_IMAGE)
                .withNetwork(network)
                .withNetworkAliases(STUBS_ALIAS)
                .withExposedPorts(STUBS_PORT)
                .waitingFor(Wait.forHttp("/__admin/health").forPort(STUBS_PORT).forStatusCode(200))
                .withLogConsumer(fileLog("wiremock"));
            wiremock.start();
            if ("jwks".equals(runtime.authMode())) {
                Jwt.publishJwks();
            }

            runMigrations();

            Map<String, String> tokens = tokenValues(runtime);
            app = buildApp()
                .withNetwork(network)
                .withNetworkAliases(APP_ALIAS)
                .withExposedPorts(runtime.appPort())
                .waitingFor(appWait(runtime.readinessPath(), runtime.appPort(),
                    runtime.startupTimeoutSeconds(), runtime.serverless()))
                .withLogConsumer(fileLog("app"))
                .withLogConsumer(new Slf4jLogConsumer(LOG).withPrefix("app"));
            for (Map<String, String> entry : runtime.env()) {
                app.withEnv(entry.get("name"), substitute(entry.get("value"), tokens));
            }
            app.start();
            started = true;
            LOG.info("topology up: app={} db={} jms={}", appBaseUrl(), jdbcUrl(), jmsUrl());
            Runtime.getRuntime().addShutdownHook(new Thread(Containers::stopAll, "kb-shutdown"));
        } catch (RuntimeException e) {
            failure = e;
            throw e;
        }
    }

    /**
     * Stops the topology and closes the JMS connection. Registered as a JVM shutdown hook by a
     * successful {@link #start()}, which is the only teardown when Ryuk is disabled.
     */
    static synchronized void stopAll() {
        Jms.close();
        stopQuietly(app, APP_ALIAS);
        stopQuietly(wiremock, STUBS_ALIAS);
        stopQuietly(artemis, AMQ_ALIAS);
        stopQuietly(postgres, DB_ALIAS);
        if (network != null) {
            try {
                network.close();
            } catch (RuntimeException e) {
                LOG.warn("Containers.stopAll: closing the network failed: {}", e.getMessage());
            }
            network = null;
        }
    }

    private static void stopQuietly(GenericContainer<?> container, String name) {
        if (container == null) {
            return;
        }
        try {
            container.stop();
        } catch (RuntimeException e) {
            LOG.warn("Containers.stopAll: stopping {} failed: {}", name, e.getMessage());
        }
    }

    public static String appBaseUrl() { return "http://" + app.getHost() + ":" + app.getMappedPort(runtime.appPort()); }
    public static String jdbcUrl() { return postgres.getJdbcUrl(); }
    public static String dbUser() { return runtime.dbUser(); }
    public static String dbPassword() { return runtime.dbPassword(); }
    public static String jmsUrl() { return "amqp://" + artemis.getHost() + ":" + artemis.getMappedPort(AMQ_AMQP_PORT); }
    public static String amqUser() { return runtime.amqUser(); }
    public static String amqPassword() { return runtime.amqPassword(); }
    public static String stubsHost() { return wiremock.getHost(); }
    public static int stubsPort() { return wiremock.getMappedPort(STUBS_PORT); }
    public static String stubsInternalUrl() { return "http://" + STUBS_ALIAS + ":" + STUBS_PORT; }
    public static String authInternalUrl() { return stubsInternalUrl() + "/auth"; }
    public static Path appLogPath() { return TARGET.resolve("app.log"); }

    /** Queue unless the ledger listed the destination as a topic. */
    public static boolean isQueue(String destination) {
        KbRuntime rt = runtime != null ? runtime : KbRuntime.load();
        return rt.amqQueues().contains(destination) || !rt.amqTopics().contains(destination);
    }

    /** Values for the {{token}} placeholders kb_scaffold.py writes into kb-runtime.json (spec 5.5). */
    static Map<String, String> tokenValues(KbRuntime rt) {
        Map<String, String> values = new LinkedHashMap<>();
        values.put("db.host", DB_ALIAS);
        values.put("db.port", Integer.toString(DB_PORT));
        values.put("db.name", rt.dbName());
        values.put("db.user", rt.dbUser());
        values.put("db.password", rt.dbPassword());
        values.put("amq.host", AMQ_ALIAS);
        values.put("amq.corePort", Integer.toString(AMQ_CORE_PORT));
        values.put("amq.amqpPort", Integer.toString(AMQ_AMQP_PORT));
        values.put("amq.stompPort", Integer.toString(AMQ_STOMP_PORT));
        values.put("amq.user", rt.amqUser());
        values.put("amq.password", rt.amqPassword());
        values.put("stubs.url", stubsInternalUrl());
        values.put("auth.url", authInternalUrl());
        return values;
    }

    static String substitute(String template, Map<String, String> values) {
        String out = template;
        for (Map.Entry<String, String> e : values.entrySet()) {
            out = out.replace("{{" + e.getKey() + "}}", e.getValue());
        }
        return out;
    }

    /** artemis create arguments: --queues are anycast, --addresses multicast. */
    static String artemisExtraArgs(List<String> queues, List<String> topics) {
        StringBuilder args = new StringBuilder("--http-host 0.0.0.0 --relax-jolokia");
        if (!queues.isEmpty()) {
            args.append(" --queues ").append(String.join(",", queues));
        }
        if (!topics.isEmpty()) {
            args.append(" --addresses ").append(String.join(",", topics));
        }
        return args.toString();
    }

    /** Readiness probe from the ledger, port wait when there is none; serverless doubles the timeout. */
    static WaitStrategy appWait(String readinessPath, int port, int timeoutSeconds, boolean serverless) {
        Duration timeout = Duration.ofSeconds((long) timeoutSeconds * (serverless ? 2 : 1));
        if (readinessPath == null || readinessPath.isBlank()) {
            return Wait.forListeningPort().withStartupTimeout(timeout);
        }
        return Wait.forHttp(readinessPath).forPort(port).forStatusCode(200).withStartupTimeout(timeout);
    }

    private static void runMigrations() {
        if (!"migration-container".equals(runtime.migrationsStrategy())) {
            return;
        }
        String image = runtime.migrationsImage();
        if (image == null) {
            throw new IllegalStateException("kb-runtime.json has no migrations.image (design spec 5.5)");
        }
        Map<String, String> tokens = tokenValues(runtime);
        GenericContainer<?> manager = new GenericContainer<>(DockerImageName.parse(image))
            .withNetwork(network)
            .withStartupCheckStrategy(new OneShotStartupCheckStrategy().withTimeout(Duration.ofMinutes(5)))
            .withLogConsumer(fileLog("db-manager"));
        for (Map.Entry<String, String> e : runtime.migrationsEnv().entrySet()) {
            manager.withEnv(e.getKey(), substitute(e.getValue(), tokens));
        }
        try {
            manager.start();
        } catch (RuntimeException e) {
            throw new IllegalStateException("db-manager " + image + " did not exit 0; see target/db-manager.log", e);
        }
    }

    private static GenericContainer<?> buildApp() {
        String prebuilt = System.getProperty("app.image");
        if (prebuilt != null && !prebuilt.isBlank()) {
            return new GenericContainer<>(DockerImageName.parse(prebuilt));
        }
        Path repoRoot = Paths.get(System.getProperty("user.dir")).resolve(runtime.repoRootRel()).normalize();
        String tag = "kb-app-" + runtime.repo().toLowerCase().replaceAll("[^a-z0-9._-]", "-");
        ImageFromDockerfile image = new ImageFromDockerfile(tag, false)
            .withFileFromPath(".", repoRoot)
            .withDockerfilePath(runtime.dockerfileRel());
        return new GenericContainer<>(image);
    }

    private static Consumer<OutputFrame> fileLog(String name) {
        Path file = TARGET.resolve(name + ".log");
        try {
            Files.createDirectories(TARGET);
            Files.deleteIfExists(file);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
        return frame -> {
            String text = frame.getUtf8String();
            if (text == null || text.isEmpty()) {
                return;
            }
            try {
                Files.writeString(file, text, StandardCharsets.UTF_8, StandardOpenOption.CREATE, StandardOpenOption.APPEND);
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
        };
    }
}
