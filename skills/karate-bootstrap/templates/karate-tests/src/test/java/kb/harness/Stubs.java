package kb.harness;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

/** WireMock helpers exposed to Karate as {@code Stubs}, driven over the admin REST API (spec 5.5). */
public final class Stubs {

    private static final HttpClient HTTP = HttpClient.newHttpClient();
    private static final ObjectMapper JSON = new ObjectMapper();

    private Stubs() {
    }

    /** Removes every mapping and the request journal. Exclusive state: @parallel=false. */
    public static void reset() {
        expect2xx(post("/__admin/reset", ""), "reset");
    }

    /** Imports a {"mappings":[...]} document from classpath:... or the filesystem. Exclusive state. */
    public static void load(String path) {
        expect2xx(post("/__admin/mappings/import", Db.readText(path)), "import " + path);
    }

    /** Exactly {@code times} journal entries match method + urlPath. */
    public static boolean verify(String method, String urlPath, int times) {
        return verify(method, urlPath, null, times);
    }

    /** Exactly {@code times} journal entries match method + urlPath and a body containing {@code bodyContains}. */
    public static boolean verify(String method, String urlPath, String bodyContains, int times) {
        HttpResponse<String> response = post("/__admin/requests/count", countBody(method, urlPath, bodyContains));
        expect2xx(response, "count");
        int count = readCount(response.body());
        if (count == times) {
            return true;
        }
        throw new AssertionError("Stubs.verify " + method + " " + urlPath
            + (bodyContains == null ? "" : " body~" + bodyContains) + ": expected " + times
            + " request(s), WireMock recorded " + count);
    }

    /** Writes unmatched requests and their near misses to target/stubs-unmatched.json for kb_iterate.py. */
    public static Path unmatched() {
        String requests = get("/__admin/requests/unmatched").body();
        String nearMisses = get("/__admin/requests/unmatched/near-misses").body();
        Path file = Paths.get("target", "stubs-unmatched.json");
        try {
            Files.createDirectories(file.getParent());
            Files.writeString(file, "{\"unmatched\":" + requests + ",\"nearMisses\":" + nearMisses + "}",
                StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
        return file;
    }

    static String countBody(String method, String urlPath, String bodyContains) {
        ObjectNode node = JSON.createObjectNode().put("method", method).put("urlPath", urlPath);
        if (bodyContains != null) {
            node.putArray("bodyPatterns").addObject().put("contains", bodyContains);
        }
        return node.toString();
    }

    static int readCount(String body) {
        try {
            JsonNode node = JSON.readTree(body);
            return node.path("count").asInt(-1);
        } catch (IOException e) {
            throw new IllegalStateException("unreadable count response: " + body, e);
        }
    }

    static String baseUrl() {
        return "http://" + Containers.stubsHost() + ":" + Containers.stubsPort();
    }

    static HttpResponse<String> post(String path, String body) {
        return send(HttpRequest.newBuilder(URI.create(baseUrl() + path))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8))
            .build());
    }

    static HttpResponse<String> get(String path) {
        return send(HttpRequest.newBuilder(URI.create(baseUrl() + path)).GET().build());
    }

    private static HttpResponse<String> send(HttpRequest request) {
        try {
            return HTTP.send(request, HttpResponse.BodyHandlers.ofString());
        } catch (IOException e) {
            throw new IllegalStateException("WireMock call failed: " + request.uri(), e);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(e);
        }
    }

    static void expect2xx(HttpResponse<String> response, String what) {
        if (response.statusCode() / 100 != 2) {
            throw new IllegalStateException("WireMock " + what + " failed: " + response.statusCode() + " " + response.body());
        }
    }
}
