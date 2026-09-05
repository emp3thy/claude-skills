package kb.harness;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.KeyUse;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import java.util.Date;
import java.util.Map;

/** Test issuer: one RSA key per JVM; discovery and JWKS served by WireMock under /auth (spec 5.5). */
public final class Jwt {

    private static final ObjectMapper JSON = new ObjectMapper();
    private static final RSAKey KEY = generate();

    private Jwt() {
    }

    /** RS256 bearer token with iss = the WireMock auth URL the app was configured with. */
    public static String token(Map<String, Object> claims) {
        return tokenFor(Containers.authInternalUrl(), claims);
    }

    static String tokenFor(String issuer, Map<String, Object> claims) {
        try {
            JWTClaimsSet.Builder builder = new JWTClaimsSet.Builder()
                .issuer(issuer)
                .issueTime(new Date())
                .expirationTime(new Date(System.currentTimeMillis() + 3_600_000L));
            if (claims != null) {
                claims.forEach(builder::claim);
            }
            SignedJWT jwt = new SignedJWT(new JWSHeader.Builder(JWSAlgorithm.RS256).keyID(KEY.getKeyID()).build(), builder.build());
            jwt.sign(new RSASSASigner(KEY));
            return jwt.serialize();
        } catch (JOSEException e) {
            throw new IllegalStateException("Jwt.token failed", e);
        }
    }

    /** Imports /auth/.well-known/openid-configuration and /auth/.well-known/jwks.json into WireMock. */
    public static void publishJwks() {
        String issuer = Containers.authInternalUrl();
        String jwks = new JWKSet(KEY.toPublicJWK()).toString();
        ObjectNode discovery = JSON.createObjectNode()
            .put("issuer", issuer)
            .put("jwks_uri", issuer + "/.well-known/jwks.json");
        discovery.putArray("id_token_signing_alg_values_supported").add("RS256");
        Stubs.post("/__admin/mappings/import", mappings(
            mapping("/auth/.well-known/openid-configuration", discovery.toString()),
            mapping("/auth/.well-known/jwks.json", jwks)));
    }

    static String mappings(String... items) {
        return "{\"mappings\":[" + String.join(",", items) + "]}";
    }

    /** A priority-1 GET stub returning {@code jsonBody} (a JSON document) as application/json. */
    static String mapping(String urlPath, String jsonBody) {
        try {
            ObjectNode node = JSON.createObjectNode().put("priority", 1);
            node.putObject("request").put("method", "GET").put("urlPath", urlPath);
            ObjectNode response = node.putObject("response").put("status", 200);
            response.putObject("headers").put("Content-Type", "application/json");
            response.set("jsonBody", JSON.readTree(jsonBody));
            return node.toString();
        } catch (JsonProcessingException e) {
            throw new IllegalArgumentException("mapping body is not JSON: " + jsonBody, e);
        }
    }

    static RSAKey key() {
        return KEY;
    }

    private static RSAKey generate() {
        try {
            return new RSAKeyGenerator(2048).keyUse(KeyUse.SIGNATURE).keyID("kb-test-key").generate();
        } catch (JOSEException e) {
            throw new IllegalStateException("cannot generate test RSA key", e);
        }
    }
}
