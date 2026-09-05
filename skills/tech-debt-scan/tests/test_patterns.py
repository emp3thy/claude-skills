"""patterns.py: regex leads, SATD table, redaction, inline disables (spec 4.3)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from config import DEFAULTS
from inventory import MAX_SCAN_BYTES, build_all, write_json
from make_history import git_output, replay_history
from patterns import RULES, Lead, _logger_present, _scan_files, capped_leads, redact, run_patterns

SCRIPTS = Path(__file__).parent.parent / "scripts"


@pytest.fixture(scope="module")
def service_py(service_py_repo: Path) -> tuple[Path, dict[str, Any]]:
    inventory, _ = build_all(service_py_repo, churn_months=240)
    return service_py_repo, inventory


@pytest.fixture(scope="module")
def web_ts(web_ts_repo: Path) -> tuple[Path, dict[str, Any]]:
    inventory, _ = build_all(web_ts_repo, churn_months=240)
    return web_ts_repo, inventory


@pytest.fixture(scope="module")
def mixed(mixed_decoys_repo: Path) -> tuple[Path, dict[str, Any]]:
    inventory, _ = build_all(mixed_decoys_repo, churn_months=240)
    return mixed_decoys_repo, inventory


def _run(repo: tuple[Path, dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
    doc, _inline = run_patterns(repo[0], repo[1], DEFAULTS, **kwargs)
    return doc


def _leads(doc: dict[str, Any], family: str, rule: str) -> dict[tuple[str, int], dict[str, Any]]:
    return {
        (item["file"], item["line"]): item
        for item in doc["leads"][family]
        if item["rule"] == rule
    }


def _synthetic(tmp_path: Path, files: dict[str, str]) -> tuple[Path, dict[str, Any]]:
    for rel, content in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    inventory, _ = build_all(tmp_path)
    return tmp_path, inventory


# --- A: core, SATD, blame -------------------------------------------------------


def test_rule_table_is_data_with_family_scope_and_blame() -> None:
    for rule in RULES:
        assert isinstance(rule.regex, re.Pattern)
        assert rule.scope and isinstance(rule.scope, frozenset)
        assert rule.family in {
            "half-finished", "error-masking", "dead-code", "security", "test-quality",
            "pipeline-infra", "lint",
        }
    satd = next(r for r in RULES if r.rule == "satd-marker")
    assert satd.blame is True
    assert {"source", "tests", "docs", "ci", "config", "build"} <= satd.scope
    assert all(not r.blame for r in RULES if r.rule != "satd-marker")


def test_satd_markers_with_age_ticket_and_commits_since(
    service_py: tuple[Path, dict[str, Any]],
) -> None:
    doc = _run(service_py)
    satd = {(s["file"], s["line"]): s for s in doc["satd"]}
    fixme = satd[("src/pay/refund.py", 35)]
    assert fixme["marker"] == "fixme"
    assert fixme["quote"].startswith("# FIXME: the gateway retries")
    assert fixme["ticket_ref"] is False
    assert fixme["age_days"] >= 700  # blamed to c1 on 2024-08-15
    assert fixme["commits_since"] == 6  # c6, c7, c9, c11, c14, c16
    assert fixme["path_class"] == "source"
    todo = satd[("src/pay/legacy_export.py", 7)]
    assert todo["marker"] == "todo"
    assert todo["ticket_ref"] is True  # "#42"
    assert todo["commits_since"] == 0
    assert set(fixme) == {
        "marker", "file", "line", "quote", "ticket_ref", "age_days", "commits_since", "path_class",
    }
    stats = doc["stats"]
    assert stats["markers_by_age_band"][">365d"] >= 2
    assert list(stats["markers_by_age_band"]) == [
        "<30d", "30-180d", "180-365d", ">365d", "unknown",
    ]
    assert 0.0 < stats["markers_without_ticket_share"] < 1.0
    assert set(stats["leads_per_family"]) == set(doc["leads"])


def test_commits_since_is_the_blamed_shas_position_in_the_file_log(
    service_py: tuple[Path, dict[str, Any]],
) -> None:
    """One ``git log`` per blamed file: commits_since is how many touched it since."""
    repo = service_py[0]
    rel = "src/pay/refund.py"
    satd = {(s["file"], s["line"]): s for s in _run(service_py)["satd"]}
    blamed = git_output(repo, "blame", "-w", "--porcelain", "-L", "35,35", "--", rel).split()[0]
    shas = git_output(repo, "log", "--format=%H", "--", rel).split()
    assert blamed in shas
    assert satd[(rel, 35)]["commits_since"] == shas.index(blamed)


def test_commits_since_is_null_when_the_blamed_sha_is_not_in_the_file_log(
    tmp_path: Path,
) -> None:
    """A renamed file: blame reaches past the rename, ``git log <path>`` does not."""
    source = "def export():\n    # TODO: finish the exporter\n    return None\n"
    history = tmp_path / "history.yaml"
    history.write_text(
        yaml.safe_dump({
            "commits": [
                {"author": "Ada Lovelace <ada@example.com>", "date": "2026-01-05T09:00:00+00:00",
                 "subject": "add the exporter", "files": {"src/old_exporter.py": source}},
                {"author": "Ada Lovelace <ada@example.com>", "date": "2026-02-05T09:00:00+00:00",
                 "subject": "rename the exporter", "delete": ["src/old_exporter.py"],
                 "files": {"src/exporter.py": source}},
            ]
        }),
        encoding="utf-8",
    )
    repo = replay_history(history, tmp_path, tmp_path / "repo")
    rel = "src/exporter.py"
    blamed = git_output(repo, "blame", "-w", "--porcelain", "-L", "2,2", "--", rel).split()[0]
    assert blamed not in git_output(repo, "log", "--format=%H", "--", rel).split()
    inventory, _ = build_all(repo, churn_months=240)
    doc, _inline = run_patterns(repo, inventory, DEFAULTS)
    entry = next(s for s in doc["satd"] if s["file"] == rel)
    assert entry["age_days"] is not None  # blame still dates the line
    assert entry["commits_since"] is None


def test_satd_marker_in_a_second_language(mixed: tuple[Path, dict[str, Any]]) -> None:
    doc = _run(mixed)
    satd = {(s["file"], s["line"]): s for s in doc["satd"]}
    assert satd[("internal/httpc/httpc.go", 11)]["marker"] == "deprecated"
    assert satd[("internal/httpc/httpc.go", 11)]["age_days"] is not None


def test_satd_markers_only_in_comments(tmp_path: Path) -> None:
    repo = _synthetic(
        tmp_path,
        {
            "app.py": 'label = "TODO list"\n# TODO: real marker\n',
            "web.ts": 'const x = "hack";\n/* HACK: block marker */\n',
        },
    )
    doc = _run(repo, blame=False)
    assert [(s["file"], s["line"], s["marker"]) for s in doc["satd"]] == [
        ("app.py", 2, "todo"),
        ("web.ts", 2, "hack"),
    ]


def test_no_blame_leaves_age_and_commits_null(service_py: tuple[Path, dict[str, Any]]) -> None:
    doc = _run(service_py, blame=False)
    assert doc["satd"]
    assert all(s["age_days"] is None and s["commits_since"] is None for s in doc["satd"])
    assert doc["stats"]["markers_by_age_band"]["unknown"] == len(doc["satd"])


def test_patterns_document_shape(service_py: tuple[Path, dict[str, Any]]) -> None:
    doc = _run(service_py, blame=False)
    assert list(doc) == ["schema_version", "leads", "satd", "stats"]
    assert doc["schema_version"] == 2
    assert list(doc["leads"]) == [
        "half-finished", "error-masking", "dead-code", "security", "test-quality",
        "pipeline-infra",
    ]
    for item in (lead for leads in doc["leads"].values() for lead in leads):
        assert list(item) == ["rule", "file", "line", "quote", "path_class", "extra"]


def test_capped_leads_hotspot_band_first() -> None:
    leads = [Lead("r", f"f{i}.py", 1, "q", "source").as_dict() for i in range(60)]
    band = [f"f{i}.py" for i in range(50, 60)]
    capped = capped_leads(leads, band)
    assert len(capped) == 40
    assert [item["file"] for item in capped[:10]] == band
    assert [item["file"] for item in capped[10:]] == [f"f{i}.py" for i in range(30)]
    assert capped_leads(leads, band, limit=5) == capped[:5]


def test_artefact_leads_carry_the_real_path_class_and_keep_rule_scope(tmp_path: Path) -> None:
    """Rule scope keys on the artefact class; the emitted path_class is the real one.

    The same workflow sits at the repository root (path class ``source``) and
    under a fixture tree (path class ``tests``). Both are artefact class ``ci``,
    so every ``ci``-scoped rule still reaches both. ``tls-disabled`` is a plain
    line rule with no tests skip, so it fires on both copies and the fixture-tree
    lead carries ``tests``; ``credential`` is the one scanner that skips
    ``path_class == "tests"``, so it fires on the root copy only.
    """
    workflow = (
        "jobs:\n"
        "  build:\n"
        "    env:\n"
        '      REGISTRY_TOKEN: "sk_live_9Qw3RtY7"\n'
        "    steps:\n"
        "      # TODO: pin the runner image\n"
        "      - run: curl --insecure https://registry.internal/health\n"
    )
    root = ".github/workflows/ci.yml"
    fixture = "tests/fixtures/z/.github/workflows/ci.yml"
    repo = _synthetic(tmp_path, {root: workflow, fixture: workflow})
    doc = _run(repo, blame=False)
    satd = {(s["file"], s["line"]): s for s in doc["satd"]}
    assert satd[(root, 6)]["path_class"] == "source"
    assert satd[(fixture, 6)]["path_class"] == "tests"
    tls = _leads(doc, "security", "tls-disabled")
    assert tls[(root, 7)]["path_class"] == "source"
    assert tls[(fixture, 7)]["path_class"] == "tests"
    credential = _leads(doc, "security", "credential")
    assert (root, 4) in credential
    assert (fixture, 4) not in credential
    emitted = [*doc["satd"], *(lead for items in doc["leads"].values() for lead in items)]
    assert emitted
    assert not {item["path_class"] for item in emitted} & {"ci", "container", "config", "build"}


def test_logger_present_keys_on_scan_scope_not_path_class(tmp_path: Path) -> None:
    """``_logger_present`` must key on ``ScanFile.scope``, not the emitted ``path_class``.

    A root-level artefact's ``path_class`` is ``source`` too (spec 4.3's split between
    the artefact class that drives rule scope and the real path class the file reports),
    so a logger-shaped import-like line inside a root ``.sql`` artefact must not flip the
    repo-wide ``logger_present`` flag -- only an actual first-party source file's import
    may. Before the fix, ``_logger_present`` checked ``sf.path_class == "source"``, which
    this root artefact also satisfies, so the flag would wrongly come back True.
    """
    repo = _synthetic(
        tmp_path,
        {
            "schema.sql": "use serilog;\nSELECT 1;\n",
            "app.py": 'print("hi")\n',
        },
    )
    files = _scan_files(repo[0], repo[1])
    sql = next(sf for sf in files if sf.path == "schema.sql")
    assert sql.path_class == "source"  # root artefact: the real path class is source
    assert sql.scope == "sql"  # rule/logger scope stays the artefact class
    assert _logger_present(files) is False


def test_generated_vendored_and_skipped_large_artefacts_are_not_scanned(tmp_path: Path) -> None:
    """The artefact walk applies the same three skips the code-file walk applies."""
    oversized = "FROM alpine\n# TODO: oversized artefact\n" + "# pad\n" * 400_000
    assert len(oversized.encode("utf-8")) > MAX_SCAN_BYTES
    repo = _synthetic(
        tmp_path,
        {
            "vendor/Dockerfile": "FROM alpine\n# TODO: vendored artefact\n",
            "generated/compose.yaml": "services:\n  # TODO: generated artefact\n",
            "Dockerfile": oversized,
            "app.py": "# TODO: a real marker\n",
        },
    )
    containers = {a["path"]: a for a in repo[1]["artefacts"]["container"]}
    assert containers["vendor/Dockerfile"]["path_class"] == "vendored"
    assert containers["generated/compose.yaml"]["path_class"] == "generated"
    assert containers["Dockerfile"]["skipped_large"] is True
    scanned = {sf.path for sf in _scan_files(repo[0], repo[1])}
    doc = _run(repo, blame=False)
    reported = {s["file"] for s in doc["satd"]} | {
        lead["file"] for items in doc["leads"].values() for lead in items
    }
    assert "app.py" in scanned and "app.py" in reported  # the walk is not vacuously empty
    for rel in ("vendor/Dockerfile", "generated/compose.yaml", "Dockerfile"):
        assert rel not in scanned
        assert rel not in reported


# --- B: error-masking and dead-code ----------------------------------------------


def test_swallowed_catch_positives_in_three_languages(
    service_py: tuple[Path, dict[str, Any]],
    web_ts: tuple[Path, dict[str, Any]],
    mixed: tuple[Path, dict[str, Any]],
) -> None:
    py = _leads(_run(service_py, blame=False), "error-masking", "swallowed-catch")
    lead = py[("src/pay/refund.py", 33)]
    assert lead["quote"] == "except Exception:"
    assert lead["extra"] == {
        "variable": None,
        "body": "pass",
        "catch_all": False,
        "annotated": False,
        "line_end": 34,
    }
    ts = _leads(_run(web_ts, blame=False), "error-masking", "swallowed-catch")
    lead = ts[("src/api/client.ts", 11)]
    assert lead["extra"]["variable"] == "e"
    assert lead["extra"]["body"] == "empty"
    go = _leads(_run(mixed, blame=False), "error-masking", "swallowed-catch")
    assert go[("internal/store/store.go", 27)]["extra"]["body"] == "return"
    assert go[("internal/store/store.go", 27)]["extra"]["variable"] == "err"
    assert go[("internal/store/store.go", 27)]["extra"]["line_end"] == 29
    assert go[("internal/store/store.go", 31)]["extra"]["body"] == "log-only"


def test_catch_decoys_are_not_leads(
    service_py: tuple[Path, dict[str, Any]],
    web_ts: tuple[Path, dict[str, Any]],
    mixed: tuple[Path, dict[str, Any]],
) -> None:
    py = _leads(_run(service_py, blame=False), "error-masking", "swallowed-catch")
    assert ("src/pay/refund.py", 38) not in py  # log.exception(...) then raise ... from exc
    ts = _leads(_run(web_ts, blame=False), "error-masking", "swallowed-catch")
    assert ("src/api/client-admin.ts", 14) not in ts  # console.error("...", e)
    go = _leads(_run(mixed, blame=False), "error-masking", "swallowed-catch")
    assert ("internal/store/store.go", 19) not in go  # return nil, err
    assert not any(path == "cmd/app/main.go" for path, _ in go)  # logs err and exits


def test_catch_all_variants_and_annotation(tmp_path: Path) -> None:
    repo = _synthetic(
        tmp_path,
        {
            "a.py": "try:\n    run()\nexcept:  # noqa: E722\n    pass\n",
            "B.java": "class B {\n  void f() {\n    try { g(); } catch (Throwable t) {}\n  }\n}\n",
            "c.cs": "class C {\n  void F() {\n    try { G(); } catch { }\n  }\n}\n",
            "d.rb": "def d\n  run\nrescue => e\n  # ignored\nend\n",
        },
    )
    leads = _leads(_run(repo, blame=False), "error-masking", "swallowed-catch")
    assert leads[("a.py", 3)]["extra"]["catch_all"] is True
    assert leads[("a.py", 3)]["extra"]["annotated"] is True
    assert leads[("B.java", 3)]["extra"]["catch_all"] is True
    assert leads[("B.java", 3)]["extra"]["variable"] == "t"
    assert leads[("c.cs", 3)]["extra"]["catch_all"] is True
    assert leads[("c.cs", 3)]["extra"]["variable"] is None
    assert leads[("d.rb", 3)]["extra"]["variable"] == "e"
    assert leads[("d.rb", 3)]["extra"]["body"] == "empty"


def test_assertion_switches_two_languages(tmp_path: Path) -> None:
    repo = _synthetic(
        tmp_path,
        {
            ".github/workflows/ci.yml": (
                "jobs:\n  t:\n    steps:\n"
                "      - run: python -O app.py\n"
                "      - run: java -da -jar app.jar\n"
            ),
            "app.py": "x = 1\n# assert x > 0\n",
            "build.cpp": "#define NDEBUG\nint main() { return 0; }\n",
            "settings.json": '{"assertions": false}\n',
        },
    )
    leads = _leads(_run(repo, blame=False), "error-masking", "assertions-disabled")
    assert set(leads) == {
        (".github/workflows/ci.yml", 4),
        (".github/workflows/ci.yml", 5),
        ("app.py", 2),
        ("build.cpp", 1),
        ("settings.json", 1),
    }


def test_commented_out_code_two_languages(
    service_py: tuple[Path, dict[str, Any]], tmp_path: Path
) -> None:
    py = _leads(_run(service_py, blame=False), "dead-code", "commented-out-code")
    lead = py[("src/pay/legacy_export.py", 17)]
    assert lead["extra"] == {"line_end": 19, "code_like": 3, "total": 3}
    assert lead["quote"] == "# def export_v0(refund_id):"
    repo = _synthetic(
        tmp_path,
        {
            "store.go": (
                "package store\n\n// if err != nil {\n//     return err\n// }\n\nfunc F() {}\n"
            ),
            "prose.go": (
                "package prose\n\n// This helper exists because the upstream\n"
                "// client retries on our behalf and we\n"
                "// need to avoid double posting.\nfunc G() {}\n"
            ),
            "short.py": "# x = 1\n# y = 2\nz = 3\n",
            "unbalanced.py": "# if a:\n#     f(\n#     g(\nz = 3\n",
        },
    )
    leads = _leads(_run(repo, blame=False), "dead-code", "commented-out-code")
    assert set(leads) == {("store.go", 3)}
    assert leads[("store.go", 3)]["extra"] == {"line_end": 5, "code_like": 2, "total": 3}


def test_legacy_names_two_languages(
    service_py: tuple[Path, dict[str, Any]],
    mixed: tuple[Path, dict[str, Any]],
    tmp_path: Path,
) -> None:
    py = _leads(_run(service_py, blame=False), "dead-code", "legacy-name")
    assert py[("src/pay/legacy_export.py", 1)]["extra"] == {"where": "path", "token": "legacy"}
    assert py[("src/pay/legacy_export.py", 8)]["extra"] == {"where": "symbol", "token": "v1"}
    go = _leads(_run(mixed, blame=False), "dead-code", "legacy-name")
    assert go[("internal/dispatch/dispatch.go", 30)]["extra"] == {
        "where": "symbol", "token": "legacy",
    }
    repo = _synthetic(
        tmp_path,
        {
            "hold.py": "def holdOrder():\n    pass\n\n\nclass Bolder:\n    pass\n",
            "oldham/town.go": "package town\n",
        },
    )
    assert _leads(_run(repo, blame=False), "dead-code", "legacy-name") == {}


def test_deprecation_two_languages_with_caller_count(
    web_ts: tuple[Path, dict[str, Any]], mixed: tuple[Path, dict[str, Any]]
) -> None:
    ts = _leads(_run(web_ts, blame=False), "dead-code", "deprecation")
    assert ts[("src/util/format-legacy.ts", 3)]["extra"] == {"callers_approx": 1}
    go = _leads(_run(mixed, blame=False), "dead-code", "deprecation")
    assert go[("internal/httpc/httpc.go", 11)]["extra"] == {"callers_approx": 1}


def test_flag_sdk_two_languages(
    web_ts: tuple[Path, dict[str, Any]], mixed: tuple[Path, dict[str, Any]]
) -> None:
    ts = _leads(_run(web_ts, blame=False), "dead-code", "flag-sdk")
    assert ("src/checkout/checkout.ts", 7) in ts
    go = _leads(_run(mixed, blame=False), "dead-code", "flag-sdk")
    assert ("cmd/app/main.go", 22) in go


# --- C: stubs, security, test-quality, no-timeout, stdout, lint, CLI, grep -------

LANGUAGE_BRANCH_RE = re.compile(
    r"^\s*(?:if|elif)\b.*(?:\b(?:language|lang)\b\s*(?:==|!=|\bin\b)"
    r"|[\"'](?:python|typescript|javascript|go|csharp|java|rust|ruby|php|kotlin|swift|cpp|c"
    r"|markdown)[\"'])"
)


def test_rule_table_covers_every_group() -> None:
    names = {r.rule for r in RULES}
    assert names >= {
        "satd-marker", "stub", "skip-marker", "no-timeout", "swallowed-catch",
        "assertions-disabled", "commented-out-code", "legacy-name", "deprecation", "flag-sdk",
        "credential", "string-sql", "dynamic-eval", "tls-disabled", "weak-hash",
        "permissive-cors", "security-suppression", "sleep", "retry-marker", "wall-clock",
        "unseeded-random", "try-in-test", "conditional-in-test", "numeric-assert",
        "assert-free", "stdout-write", "inline-disable",
    }
    assert len(RULES) >= 27


def test_stub_and_skip_leads_in_two_languages(
    service_py: tuple[Path, dict[str, Any]],
    web_ts: tuple[Path, dict[str, Any]],
    mixed: tuple[Path, dict[str, Any]],
) -> None:
    py = _run(service_py, blame=False)
    assert ("tests/test_refund.py", 21) in _leads(py, "half-finished", "stub")
    assert ("tests/test_refund.py", 19) in _leads(py, "half-finished", "skip-marker")
    go = _run(mixed, blame=False)
    assert ("internal/dispatch/dispatch.go", 31) in _leads(go, "half-finished", "stub")
    ts = _run(web_ts, blame=False)
    assert ("src/__tests__/pricing.spec.ts", 7) in _leads(ts, "half-finished", "skip-marker")


def test_credential_detected_and_redacted_in_two_languages(
    service_py: tuple[Path, dict[str, Any]], mixed: tuple[Path, dict[str, Any]]
) -> None:
    py = _leads(_run(service_py, blame=False), "security", "credential")
    lead = py[("src/pay/gateway.py", 11)]
    assert "sk_l***" in lead["quote"]
    assert "sk_live_51H8" not in lead["quote"]
    assert lead["extra"] == {"redacted": True}
    go = _leads(_run(mixed, blame=False), "security", "credential")
    assert "tok_***" in go[("internal/httpc/httpc.go", 9)]["quote"]
    assert redact('api_key = "sk_live_51H8f2kL9mN3pQ7rS4tU6vW"') == 'api_key = "sk_l***"'


def test_credential_exclusions(service_py: tuple[Path, dict[str, Any]], tmp_path: Path) -> None:
    py = _leads(_run(service_py, blame=False), "security", "credential")
    assert not any(path == "tests/fixtures/seed.py" for path, _ in py)
    repo = _synthetic(
        tmp_path,
        {
            "app.yml": (
                'password: "${DB_PASSWORD}"\n'
                'token: "{{ secrets.token }}"\n'
                'secret: "changeme-please-now"\n'
                'api_key: "<your-key-here>"\n'
                'password: "example_password_1"\n'
                'admin_password: "hunter2hunter2hunter2"\n'
                'short: "abc"\n'
            ),
            "src/x.py": "x = 1\n",
        },
    )
    leads = _leads(_run(repo, blame=False), "security", "credential")
    assert list(leads) == [("app.yml", 6)]
    assert leads[("app.yml", 6)]["quote"] == 'admin_password: "hunt***"'


def test_credential_redacted_on_satd_and_non_security_lines(tmp_path: Path) -> None:
    """A credential-shaped value must never survive unredacted, on any family's quote."""
    from patterns import _main

    secret = "sk_live_51H8f2kL9mN3pQ7rS4tU6vW"
    repo = _synthetic(
        tmp_path / "repo",
        {"app.py": f'token = "{secret}"  # not implemented yet\n'},
    )
    doc = _run(repo, blame=False)
    satd_quotes = [s["quote"] for s in doc["satd"]]
    assert satd_quotes and all(secret not in q for q in satd_quotes)
    assert any("sk_l***" in q for q in satd_quotes)
    stub = _leads(doc, "half-finished", "stub")
    stub_quotes = [item["quote"] for item in stub.values()]
    assert stub_quotes and all(secret not in q for q in stub_quotes)
    assert any("sk_l***" in q for q in stub_quotes)

    workdir = tmp_path / "wd"
    write_json(workdir / "inventory.json", repo[1])
    assert _main([str(repo[0]), "--workdir", str(workdir), "--no-blame"]) == 0
    raw = (workdir / "patterns.json").read_bytes()
    assert secret.encode("utf-8") not in raw
    assert raw.count(b"sk_l***") >= 2  # the satd entry and the stub lead, at least


def test_string_sql_two_languages_and_decoy(
    service_py: tuple[Path, dict[str, Any]], mixed: tuple[Path, dict[str, Any]], tmp_path: Path
) -> None:
    py = _leads(_run(service_py, blame=False), "security", "string-sql")
    assert ("src/pay/legacy_export.py", 11) in py
    go = _leads(_run(mixed, blame=False), "security", "string-sql")
    assert ("internal/store/store.go", 38) in go
    repo = _synthetic(
        tmp_path,
        {
            "db.py": (
                'cur.execute("SELECT 1 WHERE id = ?", (rid,))\n'
                'cur.execute("SELECT 1 WHERE id = %s", (rid,))\n'
            )
        },
    )
    assert _leads(_run(repo, blame=False), "security", "string-sql") == {}


def test_eval_tls_hash_cors_and_suppression_in_two_languages(
    service_py: tuple[Path, dict[str, Any]], mixed: tuple[Path, dict[str, Any]], tmp_path: Path
) -> None:
    py = _run(service_py, blame=False)
    go = _run(mixed, blame=False)
    assert ("src/pay/legacy_export.py", 13) in _leads(py, "security", "dynamic-eval")
    assert ("internal/shell/run.go", 7) in _leads(go, "security", "dynamic-eval")
    assert ("src/pay/gateway.py", 24) in _leads(py, "security", "tls-disabled")
    assert ("internal/httpc/httpc.go", 13) in _leads(go, "security", "tls-disabled")
    assert ("src/pay/utils.py", 12) in _leads(py, "security", "weak-hash")
    assert ("internal/crypto/hash.go", 9) in _leads(go, "security", "weak-hash")
    assert ("src/pay/gateway.py", 12) in _leads(py, "security", "permissive-cors")
    assert ("src/pay/legacy_export.py", 11) in _leads(py, "security", "security-suppression")
    assert ("internal/shell/run.go", 7) in _leads(go, "security", "security-suppression")
    repo = _synthetic(
        tmp_path,
        {
            "srv.go": (
                "package srv\n\nfunc h(w http.ResponseWriter) {\n"
                '\tw.Header().Set("Access-Control-Allow-Origin", "*")\n}\n'
            )
        },
    )
    assert ("srv.go", 4) in _leads(_run(repo, blame=False), "security", "permissive-cors")


def test_test_quality_signals_in_two_languages(
    service_py: tuple[Path, dict[str, Any]], mixed: tuple[Path, dict[str, Any]], tmp_path: Path
) -> None:
    py = _run(service_py, blame=False)
    go = _run(mixed, blame=False)
    assert ("tests/test_ledger.py", 14) in _leads(py, "test-quality", "sleep")
    assert ("internal/store/store_test.go", 15) in _leads(go, "test-quality", "sleep")
    py_free = _leads(py, "test-quality", "assert-free")
    go_free = _leads(go, "test-quality", "assert-free")
    assert py_free[("tests/test_ledger.py", 18)]["extra"] == {"test": "test_reverse_smoke"}
    assert go_free[("internal/store/store_test.go", 14)]["extra"] == {"test": "TestLoadSmoke"}
    assert ("tests/test_ledger.py", 11) not in py_free
    assert ("internal/store/store_test.go", 8) not in go_free
    assert ("tests/test_ledger.py", 15) in _leads(py, "test-quality", "numeric-assert")
    assert not any(p.startswith("src/") for p, _ in _leads(py, "test-quality", "sleep"))
    repo = _synthetic(
        tmp_path,
        {
            "tests/test_time.py": (
                "import random\nimport pytest\nfrom datetime import datetime\n\n"
                "@pytest.mark.flaky(reruns=3)\n"
                "def test_clock():\n"
                "    stamp = datetime.now()\n"
                "    pick = random.choice([1, 2])\n"
                "    try:\n"
                "        run(stamp, pick)\n"
                "    except ValueError:\n"
                "        pass\n"
                "    if pick == 1:\n"
                "        assert stamp\n"
            ),
            "src/__tests__/clock.test.ts": (
                "jest.retryTimes(3);\n"
                'test("clock", () => {\n'
                "  const stamp = Date.now();\n"
                "  const pick = Math.random();\n"
                "  try {\n"
                "    run(stamp, pick);\n"
                "  } catch (e) {}\n"
                "  if (pick > 0.5) {\n"
                "    expect(stamp).toBeGreaterThan(1700000000000);\n"
                "  }\n"
                "});\n"
            ),
        },
    )
    doc = _run(repo, blame=False)
    ts = "src/__tests__/clock.test.ts"
    expected = {
        "retry-marker": {("tests/test_time.py", 5), (ts, 1)},
        "wall-clock": {("tests/test_time.py", 7), (ts, 3)},
        "unseeded-random": {("tests/test_time.py", 8), (ts, 4)},
        "try-in-test": {("tests/test_time.py", 9), (ts, 5), (ts, 7)},
        "conditional-in-test": {("tests/test_time.py", 13), (ts, 8)},
        "numeric-assert": {(ts, 9)},
        "assert-free": set(),
    }
    for rule, hits in expected.items():
        assert set(_leads(doc, "test-quality", rule)) == hits, rule
    assert doc["leads"]["error-masking"] == []  # the catch in a test is not the catch rule's job


def test_no_timeout_in_three_languages_with_decoys(
    service_py: tuple[Path, dict[str, Any]],
    web_ts: tuple[Path, dict[str, Any]],
    mixed: tuple[Path, dict[str, Any]],
) -> None:
    py = _leads(_run(service_py, blame=False), "half-finished", "no-timeout")
    assert py[("src/pay/gateway.py", 20)]["extra"] == {"client": "requests/httpx"}
    assert ("src/pay/legacy_export.py", 18) not in py  # commented-out fetch( is skipped
    ts = _leads(_run(web_ts, blame=False), "half-finished", "no-timeout")
    assert ts[("src/api/client.ts", 9)]["extra"] == {"client": "fetch"}
    assert not any(path == "src/api/client-admin.ts" for path, _ in ts)
    go = _leads(_run(mixed, blame=False), "half-finished", "no-timeout")
    assert go[("internal/httpc/httpc.go", 14)]["extra"] == {"client": "net/http"}
    assert not any(path == "internal/httpc/httpc_safe.go" for path, _ in go)


def test_stdout_writes_need_a_logger_and_skip_cli(
    service_py: tuple[Path, dict[str, Any]],
    web_ts: tuple[Path, dict[str, Any]],
    mixed: tuple[Path, dict[str, Any]],
    tmp_path: Path,
) -> None:
    py = _leads(_run(service_py, blame=False), "pipeline-infra", "stdout-write")
    assert py[("src/pay/refund.py", 41)]["extra"] == {"count": 1}
    go = _leads(_run(mixed, blame=False), "pipeline-infra", "stdout-write")
    assert ("internal/store/store.go", 32) in go
    assert not any(path == "cmd/app/main.go" for path, _ in go)
    assert _run(web_ts, blame=False)["leads"]["pipeline-infra"] == []  # no logger library
    repo = _synthetic(
        tmp_path,
        {
            "cmd/tool/main.go": (
                'package main\n\nimport "fmt"\n\nfunc main() { fmt.Println("x") }\n'
            ),
            "internal/work.go": 'package work\n\nimport "log"\n\nfunc W() { fmt.Println("y") }\n',
            "server.py": 'import logging\n\ndef serve():\n    print("up")\n    print("ready")\n',
        },
    )
    leads = _leads(_run(repo, blame=False), "pipeline-infra", "stdout-write")
    assert set(leads) == {("internal/work.go", 5), ("server.py", 4)}
    assert leads[("server.py", 4)]["extra"] == {"count": 2}


def test_inline_disables_counted_and_written_back(
    service_py: tuple[Path, dict[str, Any]], mixed: tuple[Path, dict[str, Any]], tmp_path: Path
) -> None:
    from patterns import _main

    _, inline = run_patterns(service_py[0], service_py[1], DEFAULTS, blame=False)
    assert inline["src/pay/legacy_export.py"] == 2
    assert inline["src/pay/refund.py"] == 0
    assert "tests/test_refund.py" not in inline  # source files only
    _, inline_go = run_patterns(mixed[0], mixed[1], DEFAULTS, blame=False)
    assert inline_go["internal/shell/run.go"] == 1
    workdir = tmp_path / "wd"
    write_json(workdir / "inventory.json", service_py[1])
    assert _main([str(service_py[0]), "--workdir", str(workdir), "--no-blame"]) == 0
    inventory = json.loads((workdir / "inventory.json").read_bytes())
    counts = {e["path"]: e["inline_disables"] for e in inventory["files"]}
    assert counts["src/pay/legacy_export.py"] == 2
    assert counts["tests/test_refund.py"] == 0
    raw = (workdir / "patterns.json").read_bytes()
    assert b"\r\n" not in raw
    patterns = json.loads(raw)
    assert patterns["schema_version"] == 2
    assert all(s["age_days"] is None for s in patterns["satd"])
    assert "sk_live_51H8" not in raw.decode("utf-8")


def test_cli_missing_inventory_exits_2(tmp_path: Path) -> None:
    from patterns import _main

    assert _main([str(tmp_path), "--workdir", str(tmp_path / "none")]) == 2


def test_no_script_branches_on_a_language_name() -> None:
    allowed = {"tools_probe.py"}  # the spec's tool normalisers are the one exception (0(d))
    offenders: list[str] = []
    for script in sorted(SCRIPTS.glob("*.py")):
        if script.name in allowed:
            continue
        for lineno, line in enumerate(script.read_text(encoding="utf-8").splitlines(), start=1):
            if LANGUAGE_BRANCH_RE.search(line):
                offenders.append(f"{script.name}:{lineno}: {line.strip()}")
    assert offenders == []
