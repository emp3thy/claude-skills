package kb.harness;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

/** Postgres helpers exposed to Karate as {@code Db}. Identifiers are validated, values are bound. */
public final class Db {

    private static final Pattern IDENT = Pattern.compile("^[A-Za-z_][A-Za-z0-9_]*$");

    private Db() {
    }

    /** Runs a seed script; statements are split on a ';' at end of line. Seeds are inserts, not functions. */
    public static void run(String path) {
        String sql = readText(path);
        try (Connection c = connect(); Statement st = c.createStatement()) {
            for (String statement : sql.split(";\\s*\\r?\\n")) {
                String trimmed = statement.trim();
                if (!trimmed.isEmpty() && !trimmed.startsWith("--")) {
                    st.execute(trimmed);
                }
            }
        } catch (SQLException e) {
            throw new IllegalStateException("Db.run failed for " + path + ": " + e.getMessage(), e);
        }
    }

    public static Map<String, Object> row(String table, Map<String, Object> where) {
        List<Map<String, Object>> rows = select(table, where, 1);
        return rows.isEmpty() ? null : rows.get(0);
    }

    public static Map<String, Object> awaitRow(String table, Map<String, Object> where, long timeoutMs) {
        long deadline = System.currentTimeMillis() + timeoutMs;
        while (true) {
            Map<String, Object> found = row(table, where);
            if (found != null) {
                return found;
            }
            if (System.currentTimeMillis() > deadline) {
                throw new AssertionError("no row in " + table + " matching " + where + " within " + timeoutMs + "ms");
            }
            sleep(250);
        }
    }

    public static long count(String table, Map<String, Object> where) {
        checkIdent(table);
        StringBuilder sql = new StringBuilder("SELECT COUNT(*) FROM ").append(table);
        List<Object> params = whereClause(sql, where);
        try (Connection c = connect(); PreparedStatement ps = c.prepareStatement(sql.toString())) {
            bind(ps, params);
            try (ResultSet rs = ps.executeQuery()) {
                rs.next();
                return rs.getLong(1);
            }
        } catch (SQLException e) {
            throw new IllegalStateException("Db.count failed: " + e.getMessage(), e);
        }
    }

    /** Exclusive state: callers carry @parallel=false (spec 5.6). */
    public static void truncate(List<String> tables) {
        if (tables == null || tables.isEmpty()) {
            return;
        }
        tables.forEach(Db::checkIdent);
        String sql = "TRUNCATE TABLE " + String.join(", ", tables) + " RESTART IDENTITY CASCADE";
        try (Connection c = connect(); Statement st = c.createStatement()) {
            st.execute(sql);
        } catch (SQLException e) {
            throw new IllegalStateException("Db.truncate failed: " + e.getMessage(), e);
        }
    }

    private static List<Map<String, Object>> select(String table, Map<String, Object> where, int limit) {
        checkIdent(table);
        StringBuilder sql = new StringBuilder("SELECT * FROM ").append(table);
        List<Object> params = whereClause(sql, where);
        sql.append(" LIMIT ").append(limit);
        List<Map<String, Object>> out = new ArrayList<>();
        try (Connection c = connect(); PreparedStatement ps = c.prepareStatement(sql.toString())) {
            bind(ps, params);
            try (ResultSet rs = ps.executeQuery()) {
                ResultSetMetaData meta = rs.getMetaData();
                while (rs.next()) {
                    Map<String, Object> rowMap = new LinkedHashMap<>();
                    for (int i = 1; i <= meta.getColumnCount(); i++) {
                        rowMap.put(meta.getColumnLabel(i), rs.getObject(i));
                    }
                    out.add(rowMap);
                }
            }
        } catch (SQLException e) {
            throw new IllegalStateException("Db.select failed: " + e.getMessage(), e);
        }
        return out;
    }

    private static List<Object> whereClause(StringBuilder sql, Map<String, Object> where) {
        List<Object> params = new ArrayList<>();
        if (where == null || where.isEmpty()) {
            return params;
        }
        sql.append(" WHERE ");
        boolean first = true;
        for (Map.Entry<String, Object> e : where.entrySet()) {
            checkIdent(e.getKey());
            if (!first) {
                sql.append(" AND ");
            }
            first = false;
            if (e.getValue() == null) {
                sql.append(e.getKey()).append(" IS NULL");
            } else {
                sql.append(e.getKey()).append(" = ?");
                params.add(e.getValue());
            }
        }
        return params;
    }

    private static void bind(PreparedStatement ps, List<Object> params) throws SQLException {
        for (int i = 0; i < params.size(); i++) {
            ps.setObject(i + 1, params.get(i));
        }
    }

    private static Connection connect() throws SQLException {
        return DriverManager.getConnection(Containers.jdbcUrl(), Containers.dbUser(), Containers.dbPassword());
    }

    private static void checkIdent(String name) {
        if (name == null || !IDENT.matcher(name).matches()) {
            throw new IllegalArgumentException("invalid SQL identifier: " + name);
        }
    }

    /** Reads classpath:x or a filesystem path; shared with Stubs.load. */
    static String readText(String path) {
        String clean = path.startsWith("classpath:") ? path.substring("classpath:".length()) : path;
        try (InputStream in = Db.class.getResourceAsStream("/" + clean)) {
            if (in != null) {
                return new String(in.readAllBytes(), StandardCharsets.UTF_8);
            }
            Path file = Paths.get(clean);
            if (Files.isRegularFile(file)) {
                return Files.readString(file, StandardCharsets.UTF_8);
            }
            throw new IllegalArgumentException("not found on classpath or filesystem: " + path);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    private static void sleep(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(e);
        }
    }
}
