package kb.harness;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

/** Seed-script parsing only: no database is involved. */
class DbTest {

    @Test
    void stripCommentsKeepsAStatementUnderALeadingCommentLine() {
        String chunk = "-- seed deals\nINSERT INTO deals (id) VALUES ('d-1')";
        assertEquals("INSERT INTO deals (id) VALUES ('d-1')", Db.stripComments(chunk));
    }

    @Test
    void stripCommentsEmptiesAChunkOfOnlyComments() {
        assertTrue(Db.stripComments("-- one\n   -- two\n").trim().isEmpty());
    }
}
