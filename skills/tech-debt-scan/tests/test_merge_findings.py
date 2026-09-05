"""merge_findings.py: validation, quote verification, clustering, corroboration (spec 4.7)."""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any

from config import DEFAULTS
from evidence import fingerprint
from inventory import build_all, write_json, write_outputs
from merge_findings import CLUSTER_WINDOW, _main, merge
from patterns import run_patterns
from rules import run_rules

SECRET = "sk_live_51H8f2kL9mN3pQ7rS4tU6vW"
SWALLOW = "except Exception:\n        pass"


def _repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "pay.py").write_text(
        "import logging\n"
        "log = logging.getLogger(__name__)\n"
        "\n"
        "def refund(order):\n"
        "    try:\n"
        "        order.refund()\n"
        "    except Exception:\n"
        "        pass\n"
        "\n"
        "def charge(order):\n"
        "    # TODO: retry on timeout\n"
        f'    token = "{SECRET}"\n'
        "    return order.charge(token)\n",
        encoding="utf-8",
    )
    (repo / "src" / "util.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    workdir = tmp_path / "wd"
    inventory, coupling = build_all(repo, config=DEFAULTS)
    write_outputs(inventory, coupling, workdir)
    patterns, _ = run_patterns(repo, inventory, DEFAULTS, blame=False)
    write_json(workdir / "patterns.json", patterns)
    findings, leads = run_rules(repo, inventory, DEFAULTS)
    write_json(
        workdir / "rule-findings.json",
        {"schema_version": 2, "findings": findings, "leads": leads},
    )
    write_json(
        workdir / "scan-plan.json",
        {
            "schema_version": 2,
            "set": "explicit",
            "top": 5,
            "chunked": False,
            "thresholds": DEFAULTS["chunking"],
            "entries": [
                {
                    "family": "error-masking",
                    "module": None,
                    "prompt": "prompts/scout-error-masking.md",
                    "output": "scouts/error-masking.json",
                    "leads": 1,
                },
                {
                    "family": "security",
                    "module": None,
                    "prompt": "prompts/scout-security.md",
                    "output": "scouts/security.json",
                    "leads": 1,
                },
            ],
            "families_run": ["error-masking", "security"],
            "families_skipped": [],
        },
    )
    return repo, workdir


def _finding(
    family: str, title: str, file: str, start: int, end: int, quote: str, **extra: Any
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "title": title,
        "family": family,
        "debt_type": "code",
        "type_id": None,
        "severity": 3,
        "effort": "M",
        "signals_cited": [],
        "evidence": [{"file": file, "line_start": start, "line_end": end, "quote": quote}],
        "note": "n",
    }
    item.update(extra)
    return item


def _scout(
    workdir: Path, family: str, findings: list[dict[str, Any]], **channels: Any
) -> None:
    doc = {
        "family": family,
        "module": None,
        "findings": findings,
        "open_questions": channels.get("open_questions", []),
        "looks_bad_but_fine": channels.get("looks_bad_but_fine", []),
        "not_assessed": [],
    }
    write_json(workdir / "scouts" / f"{family}.json", doc)


def test_invented_quote_becomes_an_open_question_and_moved_quote_gets_real_range(
    tmp_path: Path,
) -> None:
    repo, workdir = _repo(tmp_path)
    _scout(
        workdir,
        "error-masking",
        [
            _finding("error-masking", "swallowed", "src/pay.py", 7, 8, SWALLOW),
            _finding("error-masking", "moved", "src/pay.py", 1, 2, "except   Exception:  pass"),
            _finding("error-masking", "invented", "src/pay.py", 3, 3, "this line does not exist"),
        ],
    )
    _scout(workdir, "security", [])
    doc = merge(workdir, repo, DEFAULTS)
    assert list(doc) == ["schema_version", "candidates", "open_questions",
                         "looks_bad_but_fine", "stats"]
    scout_candidates = [c for c in doc["candidates"] if c["source"] == "scout"]
    assert len(scout_candidates) == 1, "the two verified findings cluster (same range)"
    cand = scout_candidates[0]
    assert cand["evidence"][0] == {
        "file": "src/pay.py",
        "line_start": 7,
        "line_end": 8,
        "quote": SWALLOW,
        "quote_verified": True,
    }
    assert cand["tier"] is None
    assert doc["open_questions"] == [
        {"file": "src/pay.py", "line_start": 3, "question": "invented", "reason": "quote not found"}
    ]
    stats = doc["stats"]["error-masking"]
    assert list(stats) == ["raw", "dropped", "quote_failed", "clustered", "suppressed", "disabled"]
    assert stats["raw"] == 3 and stats["quote_failed"] == 1 and stats["clustered"] == 1


def test_fingerprint_cluster_and_corroboration(tmp_path: Path) -> None:
    repo, workdir = _repo(tmp_path)
    _scout(
        workdir,
        "error-masking",
        [
            _finding(
                "error-masking", "a", "src/pay.py", 7, 8, SWALLOW, severity=2, effort="L"
            ),
            _finding(
                "error-masking",
                "b",
                "src/pay.py",
                5,
                6,
                "try:\n        order.refund()",
                severity=4,
                effort="S",
                signals_cited=["pattern:error-masking:swallowed-catch"],
            ),
        ],
    )
    _scout(workdir, "security", [])
    doc = merge(workdir, repo, DEFAULTS)
    assert "dropped_reasons" not in doc["stats"]["security"], "nothing dropped, key must be absent"
    cand = next(c for c in doc["candidates"] if c["source"] == "scout")
    assert cand["severity"] == 4 and cand["effort"] == "S" and cand["title"] == "b"
    assert len(cand["evidence"]) == 2
    fp = fingerprint("error-masking", "src/pay.py", "try:\n        order.refund()")[0]
    alt = fingerprint("error-masking", "src/pay.py", SWALLOW)[0]
    assert cand["fingerprint"] in {fp, alt}
    assert "scout:error-masking" in cand["confirmed_by"]
    assert any(c.startswith("pattern:") for c in cand["confirmed_by"])
    assert cand["signals_cited"] == ["pattern:error-masking:swallowed-catch"]
    assert list(cand) == ["fingerprint", "quote_hash", "family", "debt_type", "type_id", "title",
                          "severity", "effort", "source", "rule_id", "note", "evidence",
                          "confirmed_by", "signals_cited", "signals", "tier"]
    assert list(cand["signals"]) == ["hotspot_score", "churn", "coupling_degree", "fan_in_approx",
                                     "path_class", "in_hotspot_band"]


def test_far_apart_findings_do_not_cluster_and_satd_corroborates(tmp_path: Path) -> None:
    repo, workdir = _repo(tmp_path)
    lines = [f"x = {i}" for i in range(1, 40)]
    (repo / "src" / "long.py").write_text("\n".join(lines) + "\n", encoding="utf-8")
    far = 1 + CLUSTER_WINDOW + 1
    _scout(
        workdir,
        "error-masking",
        [
            _finding("error-masking", "top", "src/long.py", 1, 1, "x = 1"),
            _finding("error-masking", "bottom", "src/long.py", far, far, f"x = {far}"),
        ],
    )
    _scout(
        workdir,
        "security",
        [_finding("security", "todo-site", "src/pay.py", 11, 11, "# TODO: retry on timeout")],
    )
    doc = merge(workdir, repo, DEFAULTS)
    masking = [c for c in doc["candidates"] if c["family"] == "error-masking"]
    assert len(masking) == 2
    todo = next(c for c in doc["candidates"] if c["title"] == "todo-site")
    assert "satd" in todo["confirmed_by"]


def test_malformed_items_are_dropped_and_counted(tmp_path: Path) -> None:
    repo, workdir = _repo(tmp_path)
    wrong_family = _finding("security", "wrong family", "src/pay.py", 12, 12, "token")
    wrong_family["family"] = "dead-code"
    bad = [
        {"title": "no evidence", "family": "security", "debt_type": "code", "severity": 3,
         "effort": "M", "signals_cited": [], "evidence": [], "note": ""},
        wrong_family,
        _finding("security", "bad severity", "src/pay.py", 12, 12, "token", severity=9),
        _finding("security", "bad type", "src/pay.py", 12, 12, "token", type_id="TD-99"),
        "not a dict",
    ]
    _scout(workdir, "security", bad)  # type: ignore[arg-type]
    _scout(workdir, "error-masking", [])
    doc = merge(workdir, repo, DEFAULTS)
    assert [c for c in doc["candidates"] if c["source"] == "scout"] == []
    stats = doc["stats"]["security"]
    assert stats["dropped"] == 5
    assert list(stats) == [
        "raw", "dropped", "quote_failed", "clustered", "suppressed", "disabled", "dropped_reasons",
    ]
    reasons = stats["dropped_reasons"]
    assert len(reasons) == 5
    joined = " | ".join(reasons)
    assert "no evidence" in joined, "the item with an empty evidence list"
    assert "dead-code" in joined, "the wrong family value"
    assert "severity 9" in joined, "the out-of-range severity"
    assert "TD-99" in joined, "the invalid type_id"
    assert "not an object" in joined, "the bare string item"


def test_suppression_with_expiry_and_path_class_disable(tmp_path: Path) -> None:
    repo, workdir = _repo(tmp_path)
    fp, _ = fingerprint("error-masking", "src/pay.py", SWALLOW)
    _scout(workdir, "error-masking", [_finding("error-masking", "a", "src/pay.py", 7, 8, SWALLOW)])
    _scout(workdir, "security", [])
    cfg = deepcopy(DEFAULTS)
    cfg["suppressions"] = [{"fingerprint": fp, "reason": "known", "until": "2026-12-31"}]
    live = merge(workdir, repo, cfg, today=date(2026, 9, 5))
    assert [c for c in live["candidates"] if c["source"] == "scout"] == []
    assert live["stats"]["error-masking"]["suppressed"] == 1
    expired = merge(workdir, repo, cfg, today=date(2027, 1, 1))
    assert len([c for c in expired["candidates"] if c["source"] == "scout"]) == 1
    cfg2 = deepcopy(DEFAULTS)
    cfg2["families"]["per_path_class"]["source"] = {"disable": ["error-masking"]}
    off = merge(workdir, repo, cfg2)
    assert [c for c in off["candidates"] if c["source"] == "scout"] == []
    assert off["stats"]["error-masking"]["disabled"] == 1


def test_secret_is_redacted_everywhere_and_rule_candidates_pass_through(tmp_path: Path) -> None:
    repo, workdir = _repo(tmp_path)
    (repo / "Dockerfile").write_text("FROM alpine:3.20\nRUN apk add curl\n", encoding="utf-8")
    inventory, coupling = build_all(repo, config=DEFAULTS)
    write_outputs(inventory, coupling, workdir)
    findings, leads = run_rules(repo, inventory, DEFAULTS)
    write_json(
        workdir / "rule-findings.json",
        {"schema_version": 2, "findings": findings, "leads": leads},
    )
    _scout(
        workdir,
        "security",
        [
            _finding(
                "security",
                f'hard-coded token = "{SECRET}"',
                "src/pay.py",
                12,
                12,
                f'token = "{SECRET}"',
                note=f'token = "{SECRET}" assigned in charge()',
            )
        ],
        looks_bad_but_fine=[{"file": "src/util.py", "line_start": 1, "why": "helper by design"}],
    )
    _scout(workdir, "error-masking", [])
    doc = merge(workdir, repo, DEFAULTS)
    text = json.dumps(doc)
    assert SECRET not in text and "sk_l***" in text
    rule = [c for c in doc["candidates"] if c["source"] == "rule"]
    assert rule and all(c["tier"] == "A" for c in rule)
    assert doc["candidates"][-1]["source"] == "rule"
    assert doc["looks_bad_but_fine"] == [
        {"file": "src/util.py", "line_start": 1, "why": "helper by design"}
    ]


def test_cli(tmp_path: Path) -> None:
    _repo(tmp_path)
    workdir = tmp_path / "wd"
    _scout(workdir, "error-masking", [])
    _scout(workdir, "security", [])
    assert _main(["--workdir", str(workdir)]) == 0
    raw = (workdir / "candidates.json").read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    assert _main(["--workdir", str(tmp_path / "nowhere")]) == 2
