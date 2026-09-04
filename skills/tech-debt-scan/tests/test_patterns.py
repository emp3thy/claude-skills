"""patterns.py: regex leads, SATD table, redaction, inline disables (spec 4.3)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from config import DEFAULTS
from inventory import build_all
from patterns import RULES, Lead, capped_leads, run_patterns

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
