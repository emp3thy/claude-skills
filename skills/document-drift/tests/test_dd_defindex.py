from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from dd_common import read_json, write_json
from dd_config import DEFAULTS
from dd_defindex import RANK, at_commit, build, by_norm, is_specific, norm, run
from dd_helpers import make_repo
from dd_inventory import run as inventory_run


def _build(files: dict[str, str], unique: set[str] | None = None) -> list[dict[str, Any]]:
    return [dict(d) for d in build(sorted(files), files.get, unique or set())]


def _find(defs: list[dict[str, Any]], name: str, kind: str | None = None) -> dict[str, Any]:
    hits = [d for d in defs if d["name"] == name and (kind is None or d["kind"] == kind)]
    assert len(hits) == 1, (name, kind, hits)
    return hits[0]


def _span(d: dict[str, Any]) -> tuple[int, int]:
    return d["start"], d["end"]


PY_FUNCS = '''\
import os


@decorator
def top(a, b):
    """Doc."""
    return a + b


class Store:
    def put(self, key):
        return key

    async def fetch(self):
        return None
'''


def test_python_function_and_class_ranges():
    defs = _build({"pkg/store.py": PY_FUNCS})
    top = _find(defs, "top", "function")
    assert _span(top) == (4, 7)  # from the decorator
    assert top["norm"] == "top" and top["file"] == "pkg/store.py"
    assert top["change_ranges"] == [[4, 7]] and top["reading"] == [4, 7]
    assert _span(_find(defs, "Store", "class")) == (10, 15)
    put = _find(defs, "put", "function")
    assert _span(put) == (11, 12)
    assert put["owners"] == ["Store"]
    assert _span(_find(defs, "fetch", "function")) == (14, 15)


def test_python_definition_span_starts_at_the_first_decorator():
    text = "\n".join([
        "import functools",      # 1
        "",                      # 2
        "@app.get('/health')",   # 3
        "@functools.cache",      # 4
        "def health():",         # 5
        "    return 'ok'",       # 6
        "",                      # 7
        "@dataclass(",           # 8
        "    frozen=True,",      # 9
        ")",                     # 10
        "class Config:",         # 11
        "    port: int = 8080",  # 12
        "",                      # 13
        "def plain():",          # 14
        "    pass",              # 15
    ]) + "\n"
    defs = _build({"src/app.py": text})
    health = _find(defs, "health", "function")
    assert _span(health) == (3, 6)
    assert health["change_ranges"] == [[3, 6]] and health["reading"] == [3, 6]
    assert _span(_find(defs, "Config", "class")) == (8, 12)
    assert _span(_find(defs, "plain", "function")) == (14, 15)


def test_module_indexed_by_dotted_path_and_last_segment():
    defs = _build({"src/svc/storage.py": "X = 1\nY = 2\n", "src/svc/__init__.py": "\n"})
    storage = [d for d in defs if d["kind"] == "module" and d["file"] == "src/svc/storage.py"]
    # every dotted suffix of the path, so a src layout still answers to the import name
    assert sorted(d["name"] for d in storage) == ["src.svc.storage", "storage", "svc.storage"]
    assert all(_span(d) == (1, 2) for d in storage)
    dotted = _find(defs, "svc.storage", "module")
    assert dotted["norm"] == "svc_storage"
    assert by_norm(defs)["svc_storage"] == [dotted]
    package = [d for d in defs if d["kind"] == "module" and d["file"] == "src/svc/__init__.py"]
    assert sorted(d["name"] for d in package) == ["src.svc", "svc"]
    assert not any("__init__" in d["name"] for d in defs if d["kind"] == "module")


REG = '''\
TOOLS = [
    Tool(name="store.put", description="Put an item"),
]
parser.add_argument("--port", type=int)
MAPPING = {"plain_key": 1}
'''


def test_literal_registration_kinds():
    defs = _build({"svc/tools.py": REG})
    put = _find(defs, "store.put")
    assert put["kind"] == "reg" and put["norm"] == "store_put"
    assert _find(defs, "--port")["kind"] == "reg"
    assert _find(defs, "--port")["norm"] == "--port"
    assert _find(defs, "plain_key")["kind"] == "literal"
    assert RANK[put["kind"]] == 1 and RANK["literal"] == 2 and RANK["function"] == 0
    # "Put an item" does not look like a name
    assert not [d for d in defs if d["name"] == "Put an item"]


LONG = "\n".join(
    ["def handler():"]
    + [f"    step_{i} = {i}" for i in range(1, 6)]
    + ["    config = {", '        "outer": 1,', '        "inner": load(',
       "            'alpha_key',", "        ),"]
    + [f'        "k{i}": {i},' for i in range(1, 5)]
    + ["    }"]
    + [f"    tail_{i} = {i}" for i in range(1, 14)]
    + ["    return config", ""]
)


def test_literal_range_is_largest_enclosing_node_within_15_lines():
    defs = _build({"app/h.py": LONG})
    assert _span(_find(defs, "handler", "function")) == (1, 30)
    alpha = _find(defs, "alpha_key")
    # the literal sits in a 3-line call (9-11) inside a 10-line statement (7-16) inside a
    # 30-line function: the range is the statement, the largest node within 15 lines
    assert _span(alpha) == (7, 16)
    assert alpha["change_ranges"] == [[7, 16]] and alpha["reading"] == [7, 16]


OWNERS = '''\
class Registry:
    def tools(self):
        return [
            Tool(
                name="memory.retrieve",
                schema={"query": {"type": "string"}},
            ),
        ]
'''


def test_owners_include_enclosing_defs_and_registration_name():
    defs = _build({"svc/reg.py": OWNERS})
    query = _find(defs, "query")
    assert query["kind"] == "literal"
    assert set(query["owners"]) == {"memory_retrieve", "tools", "Registry"}
    reg = _find(defs, "memory.retrieve")
    assert reg["kind"] == "reg"
    assert set(reg["owners"]) == {"tools", "Registry"}


def _large_class() -> str:
    lines = ["class Big:", '    """Big class.', "", '    More."""', ""]
    for i in range(1, 7):
        lines.append(f"    def m{i}(self):")
        lines.extend([f"        v = {j}" for j in range(9)])
        lines.append("        return v")
        lines.append("")
    return "\n".join(lines) + "\n"


def test_large_class_signature_ranges():
    text = _large_class()
    defs = _build({"big.py": text})
    big = _find(defs, "Big", "class")
    assert big["end"] - big["start"] + 1 > 60
    methods = [_find(defs, f"m{i}", "function")["start"] for i in range(1, 7)]
    assert big["change_ranges"] == [[1, 4]] + [[m, m] for m in methods]
    assert big["reading"] == [1, 4]
    small = _find(defs, "m1", "function")
    assert small["change_ranges"] == [[small["start"], small["end"]]]


SQL = '''\
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY,
  body TEXT NOT NULL
);

CREATE VIRTUAL TABLE items_fts USING fts5(body);
CREATE INDEX idx_items_body ON items(body);
ALTER TABLE items ADD COLUMN created_at TEXT;
'''


def test_sql_objects_and_columns():
    defs = _build({"db/schema.sql": SQL})
    items = _find(defs, "items", "sql")
    assert _span(items) == (1, 4)
    assert _span(_find(defs, "items_fts", "sql")) == (6, 6)
    assert _span(_find(defs, "idx_items_body", "sql")) == (7, 7)
    body = _find(defs, "body", "sqlcol")
    assert _span(body) == (3, 3) and body["owners"] == ["items"]
    assert _span(_find(defs, "id", "sqlcol")) == (2, 2)
    added = _find(defs, "created_at", "sqlcol")
    assert _span(added) == (8, 8) and added["owners"] == ["items"]



SQL_MORE = """\
CREATE TABLE users (
  id SERIAL,
  email VARCHAR(255) NOT NULL, -- unique; checked by the app
  active BOOLEAN DEFAULT 'yes;no',
  CONSTRAINT users_email UNIQUE (email),
  PRIMARY KEY (id)
);
CREATE TABLE t (id INTEGER, name TEXT);
CREATE TRIGGER users_touch AFTER UPDATE ON users
BEGIN
  UPDATE users SET active = CASE WHEN 1 THEN 1 ELSE 0 END;
  INSERT INTO log VALUES ('x;y');
END;
"""


def test_sql_statement_ends_and_any_column_type():
    defs = _build({"db/more.sql": SQL_MORE})
    assert _span(_find(defs, "users", "sql")) == (1, 7)
    assert _span(_find(defs, "t", "sql")) == (8, 8)
    assert _span(_find(defs, "users_touch", "sql")) == (9, 13)
    cols = sorted((d["owners"][0], d["name"], d["start"]) for d in defs if d["kind"] == "sqlcol")
    assert cols == [("t", "id", 8), ("t", "name", 8),
                    ("users", "active", 4), ("users", "email", 3), ("users", "id", 2)]


TS = '''\
export function NavRail({ items }: { items: string[] }) {
  return <nav>{items.map((item) => <a key={item}>{item}</a>)}</nav>;
}

export function formatPrice(cents: number): string {
  // a comment with a stray } brace
  return `$${(cents / 100).toFixed(2)} }`;
}

export const LIMIT = 10;

export const routes = {
  home: "/",
};

const handler = async (req: Request) => {
  const label = "{";
  return label;
};

export class Session extends Base {
  private token = "x";

  constructor(store: Store) {
    super(store);
  }

  async refresh(force: boolean): Promise<void> {
    if (force) {
      this.token = `${this.token}}`;
    }
  }
}
'''


def test_ts_function_class_export_const_and_method_ranges():
    defs = _build({"src/session.ts": TS})
    assert _span(_find(defs, "NavRail", "function")) == (1, 3)
    assert _span(_find(defs, "formatPrice", "function")) == (5, 8)
    assert _span(_find(defs, "LIMIT", "function")) == (10, 10)
    assert _span(_find(defs, "routes", "function")) == (12, 14)
    assert _span(_find(defs, "handler", "function")) == (16, 19)
    session = _find(defs, "Session", "class")
    assert _span(session) == (21, 33)
    ctor = _find(defs, "constructor", "function")
    assert _span(ctor) == (24, 26) and ctor["owners"] == ["Session"]
    refresh = _find(defs, "refresh", "function")
    assert _span(refresh) == (28, 32) and refresh["owners"] == ["Session"]
    # string literals that look like names get a one-line range
    # nothing is defined from a comment, a template literal or a short string
    assert not [d for d in defs if d["kind"] in ("literal", "reg")]
    assert sorted(d["name"] for d in defs if d["kind"] == "function") == [
        "LIMIT", "NavRail", "constructor", "formatPrice", "handler", "refresh", "routes"]


def test_ts_string_literals_one_line_with_registration():
    text = 'program.option("--verbose", "Talk more");\nconst MODE = "fast_mode";\n'
    defs = _build({"cli.js": text})
    verbose = _find(defs, "--verbose")
    assert verbose["kind"] == "reg" and _span(verbose) == (1, 1)
    fast = _find(defs, "fast_mode")
    assert fast["kind"] == "literal" and _span(fast) == (2, 2)


def test_unique_basename_file_definitions():
    files = {"a/config.py": "X = 1\n", "b/config.py": "Y = 1\n", "a/server.py": "Z = 1\n"}
    defs = _build(files, unique={"server.py"})
    file_defs = [d for d in defs if d["kind"] == "file"]
    assert [(d["name"], d["file"], _span(d)) for d in file_defs] == [
        ("server.py", "a/server.py", (1, 1))
    ]
    assert file_defs[0]["norm"] == "server_py"


@pytest.mark.parametrize(
    ("text", "normed", "specific"),
    [
        ("mcp__better-memory__memory_retrieve", "memory_retrieve", True),
        ("memory.retrieve", "memory_retrieve", True),
        ("memory_retrieve", "memory_retrieve", True),
        ("src/app.py", "src/app_py", True),
        ("better-memory", "better_memory", False),
        ("--force", "--force", True),
        ("--dry-run", "--dry-run", True),
        ("camelCase", "camelCase", True),
        ("BETTER_MEMORY_HOME", "BETTER_MEMORY_HOME", True),
        ("HOME", "HOME", True),
        ("query", "query", False),
        ("limit", "limit", False),
        ("scope", "scope", False),
        ("ID", "ID", False),
    ],
)
def test_norm_and_is_specific(text, normed, specific):
    assert norm(text) == normed
    assert is_specific(text) is specific


def test_norm_routes_placeholders():
    assert norm("/items/<id>", routes=True) == "/items/{}"
    assert norm("/items/{id}", routes=True) == "/items/{}"
    assert norm("/items/:id", routes=True) == "/items/{}"
    assert norm("/items/<id>") == "/items/<id>"


def test_by_norm_groups_definitions():
    defs = _build({"a.py": "def memory_retrieve():\n    return 'memory.retrieve'\n"})
    groups = by_norm(defs)
    kinds = sorted(d["kind"] for d in groups["memory_retrieve"])
    assert kinds == ["function", "literal"]


def _sha(repo: Path, rev: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), "rev-parse", rev], check=True,
                         capture_output=True, text=True)
    return out.stdout.strip()


def test_at_commit_reads_old_content(tmp_path):
    old = "def keep():\n    return 1\n"
    new = "\n\n\n" + old
    repo = make_repo(tmp_path, [
        {"date": "2026-01-01T00:00:00Z", "subject": "one", "files": {"svc/mod.py": old}},
        {"date": "2026-01-02T00:00:00Z", "subject": "two", "files": {"svc/mod.py": new}},
    ])
    then = at_commit(repo, _sha(repo, "HEAD~1"), ["svc/mod.py"])
    now = at_commit(repo, _sha(repo, "HEAD"), ["svc/mod.py"])
    assert _span(_find([dict(d) for d in then], "keep", "function")) == (1, 2)
    assert _span(_find([dict(d) for d in now], "keep", "function")) == (4, 5)
    assert _find([dict(d) for d in then], "mod.py", "file")["file"] == "svc/mod.py"


def test_run_writes_sorted_index_and_skips_syntax_errors(tmp_path):
    files = {
        "svc/b.py": "def beta():\n    pass\n",
        "svc/a.py": "def alpha(:\n",
        "tests/test_x.py": "def test_x():\n    pass\n",
        "README.md": "# r\n",
        "pyproject.toml": "[project]\nname = 'svc'\n",
    }
    repo = make_repo(tmp_path, [{"date": "2026-01-01T00:00:00Z", "subject": "init",
                                 "files": files}])
    work = tmp_path / "work"
    write_json(work / "inventory.json", {
        "files": sorted(files),
        "sources": {"source": ["svc/a.py", "svc/b.py"], "test": ["tests/test_x.py"],
                    "doc": ["README.md"], "config": ["pyproject.toml"]},
        "project_files": ["pyproject.toml"],
    })
    result = run(repo, work)
    assert read_json(work / "defindex.json") == result
    assert result["skipped"] == [{"file": "svc/a.py", "reason": "syntax-error"}]
    defs = result["definitions"]
    names = {(d["name"], d["kind"]) for d in defs}
    assert ("beta", "function") in names
    assert ("README.md", "file") in names and ("a.py", "file") in names
    assert not [d for d in defs if d["file"] == "tests/test_x.py"]
    assert not [d for d in defs if d["kind"] == "function" and d["file"] == "svc/a.py"]
    keys = [(d["file"], d["start"], d["end"], d["kind"], d["name"]) for d in defs]
    assert keys == sorted(keys)


def test_run_indexes_sql_through_inventory(tmp_path):
    files = {"db/schema.sql": "CREATE TABLE items (\n  id INTEGER,\n  body TEXT\n);\n",
             "README.md": "# r\n"}
    repo = make_repo(tmp_path, [{"date": "2026-01-01T00:00:00Z", "subject": "init",
                                 "files": files}])
    work = tmp_path / "work"
    inventory_run(repo, work, {**DEFAULTS})
    defs = run(repo, work)["definitions"]
    assert _span(_find(defs, "items", "sql")) == (1, 4)
    assert _find(defs, "body", "sqlcol")["owners"] == ["items"]
