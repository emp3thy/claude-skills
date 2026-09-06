package kb.harness;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.nimbusds.jose.JWSVerifier;
import com.nimbusds.jose.crypto.RSASSAVerifier;
import com.nimbusds.jwt.SignedJWT;
import java.util.Map;
import org.junit.jupiter.api.Test;

class JwtTest {

    @Test
    void mappingWrapsBodyAsAWireMockStub() throws Exception {
        JsonNode node = new ObjectMapper().readTree(Jwt.mapping("/auth/x", "{\"a\":1}"));
        assertEquals("/auth/x", node.at("/request/urlPath").asText());
        assertEquals("GET", node.at("/request/method").asText());
        assertEquals(200, node.at("/response/status").asInt());
        assertEquals(1, node.at("/response/jsonBody/a").asInt());
        assertTrue(Jwt.mappings(Jwt.mapping("/a", "{}"), Jwt.mapping("/b", "{}")).startsWith("{\"mappings\":["));
    }

    @Test
    void tokenIsSignedByTheTestKeyWithTheGivenIssuer() throws Exception {
        SignedJWT jwt = SignedJWT.parse(Jwt.tokenFor("http://test/auth", Map.of("sub", "alice")));
        JWSVerifier verifier = new RSASSAVerifier(Jwt.key().toRSAPublicKey());
        assertTrue(jwt.verify(verifier));
        assertEquals("alice", jwt.getJWTClaimsSet().getSubject());
        assertEquals("kb-test-key", jwt.getHeader().getKeyID());
        assertEquals("http://test/auth", jwt.getJWTClaimsSet().getIssuer());
    }
}
