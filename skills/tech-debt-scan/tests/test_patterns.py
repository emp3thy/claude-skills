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
