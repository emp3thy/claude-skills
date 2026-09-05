"""rank.py: the 4.9 formula, presets, spread cap, determinism (spec 4.9)."""
from __future__ import annotations

import json
from copy import deepcopy
from math import ceil
from pathlib import Path
from typing import Any

import pytest
from config import DEFAULTS
from evidence import fingerprint
from inventory import write_json
from rank import FORMULA_VERSION, PRESETS, _main, rank


def _inventory() -> dict[str, Any]:
    def entry(
        path: str, hotspot: float, degree: int, fan_in: int | None, mode: str = "import-lines"
    ) -> dict[str, Any]:
        return {"path": path, "path_class": "source", "hotspot_score": hotspot, "churn": 1,
                "coupling_degree": degree, "fan_in_approx": fan_in, "fan_in_mode": mode}
    # y.py's fan_in is 10 (not None, as the brief drafted it) so that
    # repo_maxima's fan-in denominator is 10 -- matching Task 6's pinned
    # worked-example maxima {"hotspot": 1.0, "coupling": 10, "fan_in": 10} --
    # rather than 5 (max of x.py=2, z.py=5 alone). Without it F for x.py/z.py
    # comes out to 0.4/1.0 instead of the 0.2/0.5 the worked-example priorities
    # (6.30/4.125) require; y.py's own finding never sets fan_in, so this is
    # invisible to every other assertion.
    return {"hotspot_band": ["x.py"], "files": [
        entry("x.py", 0.8, 4, 2), entry("y.py", 0.0, 0, 10), entry("z.py", 1.0, 10, 5),
        entry("w.py", 0.5, 2, 9, mode="anywhere"),
    ]}


def _finding(family: str, path: str, sev: int, effort: str, tier: str | None, *,
             hotspot: float = 0.0, degree: int = 0, fan_in: int | None = None,
             confirmed: list[str] | None = None, verdict: str = "confirm") -> dict[str, Any]:
    fp, qh = fingerprint(family, path, f"{family}{path}{sev}{effort}")
    return {
        "fingerprint": fp, "quote_hash": qh, "family": family, "debt_type": "code",
        "type_id": None, "title": "t", "severity": sev, "effort": effort, "source": "scout",
        "rule_id": None, "note": "",
        "evidence": [{"file": path, "line_start": 1, "line_end": 1, "quote": "q",
                      "quote_verified": True}],
        "confirmed_by": confirmed or [f"scout:{family}"], "signals_cited": [],
        "signals": {"hotspot_score": hotspot, "churn": 1, "coupling_degree": degree,
                    "fan_in_approx": fan_in, "path_class": "source",
                    "in_hotspot_band": hotspot > 0.5},
        "tier": tier, "verdict": verdict, "proof": "", "checked": [], "opened": [],
        "trap_matched": None, "verified": tier is not None,
    }


def _worked_example() -> list[dict[str, Any]]:
    return [
        _finding("error-masking", "x.py", 4, "M", "A", hotspot=0.8, degree=4, fan_in=2),  # X 6.30
        _finding("security", "y.py", 5, "S", "B"),                                        # Y 3.50
        _finding("architecture", "z.py", 3, "L", "A", hotspot=1.0, degree=10, fan_in=5),  # Z 4.125
    ]


def test_worked_example_balanced_and_quick_wins() -> None:
    verified = {"schema_version": 2, "findings": _worked_example(), "stats": {}}
    doc = rank(verified, _inventory(), DEFAULTS, preset="balanced", top=3)
    assert list(doc) == ["schema_version", "formula_version", "preset", "top", "weights",
                         "tractability", "top_n", "findings"]
    assert doc["formula_version"] == FORMULA_VERSION == 1
    ordered = [(f["fingerprint"], f["priority"]) for f in doc["findings"]]
    x, y, z = _worked_example()
    assert ordered == [(x["fingerprint"], 6.3), (z["fingerprint"], 4.125), (y["fingerprint"], 3.5)]
    assert doc["top_n"] == [x["fingerprint"], z["fingerprint"], y["fingerprint"]]
    assert doc["findings"][0]["terms"] == {
        "severity": 4, "H": 0.8, "C": 0.4, "F": 0.2, "interest": 2.1,
        "tier_weight": 1.0, "tractability": 0.75, "priority": 6.3,
    }
    assert [f["rank"] for f in doc["findings"]] == [1, 2, 3]
    quick = rank(verified, _inventory(), DEFAULTS, preset="quick-wins", top=3)
    assert [round(f["priority"], 2) for f in quick["findings"]] == [4.2, 3.5, 1.65]
    assert quick["top_n"] == [x["fingerprint"], y["fingerprint"], z["fingerprint"]]


def test_presets_and_config_override() -> None:
    assert set(PRESETS) == {"balanced", "hotspot-first", "architecture", "quick-wins"}
    assert PRESETS["hotspot-first"]["weights"] == {"wH": 1.5, "wC": 0.5, "wF": 0.25}
    assert PRESETS["architecture"]["weights"] == {"wH": 0.75, "wC": 1.0, "wF": 1.0}
    assert PRESETS["quick-wins"]["tractability"] == {"S": 1.0, "M": 0.5, "L": 0.2}
    cfg = deepcopy(DEFAULTS)
    cfg["ranking"]["weights"] = {"wH": 2.0, "wC": 0.0, "wF": 0.0}
    verified = {"schema_version": 2, "findings": _worked_example(), "stats": {}}
    doc = rank(verified, _inventory(), cfg, preset="balanced", top=3)
    assert doc["weights"] == {"wH": 2.0, "wC": 0.0, "wF": 0.0}
    assert doc["findings"][0]["terms"]["interest"] == 2.6
    fixed = rank(verified, _inventory(), cfg, preset="hotspot-first", top=3)
    assert fixed["weights"] == PRESETS["hotspot-first"]["weights"], \
        "named presets ignore config weights"


def test_tier_c_and_rejected_never_in_top_n_and_f_is_zero_for_anywhere() -> None:
    findings = [
        _finding("dead-code", "y.py", 5, "S", "C", verdict="downgrade"),
        _finding("dead-code", "x.py", 5, "S", None, verdict="reject"),
        _finding("error-masking", "w.py", 2, "S", "B", fan_in=9),
    ]
    doc = rank({"findings": findings}, _inventory(), DEFAULTS, preset="balanced", top=5)
    assert doc["top_n"] == [findings[2]["fingerprint"]]
    by = {f["fingerprint"]: f for f in doc["findings"]}
    assert by[findings[0]["fingerprint"]]["in_top_n"] is False
    assert (by[findings[1]["fingerprint"]]["in_top_n"] is False
            and by[findings[1]["fingerprint"]]["tier"] is None)
    assert by[findings[2]["fingerprint"]]["terms"]["F"] == 0.0


def test_spread_cap_and_fingerprint_tie_break() -> None:
    findings = [_finding("error-masking", f"e{i}.py", 4, "S", "A") for i in range(5)]
    findings += [_finding("security", "s.py", 2, "S", "A")]
    doc = rank({"findings": findings}, _inventory(), DEFAULTS, preset="balanced", top=4)
    cap = ceil(DEFAULTS["ranking"]["spread_cap"] * 4)
    top = [f for f in doc["findings"] if f["in_top_n"]]
    assert sum(
        1 for f in top
        if findings[0]["family"] == "error-masking"
        and f["fingerprint"] in {x["fingerprint"] for x in findings[:5]}
    ) == cap
    assert findings[5]["fingerprint"] in doc["top_n"]
    capped = [f for f in doc["findings"] if f["spread_capped"]]
    assert len(capped) == 3 and all(not f["in_top_n"] for f in capped)
    masking_ranked = [
        f["fingerprint"] for f in doc["findings"] if f["fingerprint"] != findings[5]["fingerprint"]
    ]
    assert masking_ranked == sorted(masking_ranked), "equal priority breaks ties by fingerprint"


def test_quick_wins_exclusions() -> None:
    findings = [
        _finding("duplication", "x.py", 5, "S", "B"),
        _finding("duplication", "z.py", 5, "S", "A", confirmed=["scout:duplication", "coupling"]),
        _finding("ownership", "y.py", 5, "S", "A", confirmed=["rule:ownership.knowledge-island"]),
        _finding("error-masking", "y.py", 1, "S", "B"),
    ]
    findings[2]["source"] = "rule"
    doc = rank({"findings": findings}, _inventory(), DEFAULTS, preset="quick-wins", top=5)
    assert doc["top_n"] == [findings[1]["fingerprint"], findings[3]["fingerprint"]]


def test_byte_identical_over_two_runs_and_cli(tmp_path: Path) -> None:
    workdir = tmp_path / "wd"
    write_json(workdir / "inventory.json", {"root": str(tmp_path), **_inventory()})
    write_json(workdir / "verified.json",
               {"schema_version": 2, "findings": _worked_example(), "stats": {}})
    assert _main(["--workdir", str(workdir), "--preset", "balanced", "--top", "3"]) == 0
    first = (workdir / "ranked.json").read_bytes()
    assert _main(["--workdir", str(workdir), "--preset", "balanced", "--top", "3"]) == 0
    assert first == (workdir / "ranked.json").read_bytes()
    assert b"\r" not in first
    assert json.loads(first)["preset"] == "balanced"
    assert _main(["--workdir", str(workdir), "--preset", "nonsense"]) == 2
    assert _main(["--workdir", str(tmp_path / "none")]) == 2


@pytest.mark.parametrize(
    ("bad_file", "bad_content"),
    [
        ("verified.json", "[]"),
        ("inventory.json", "[]"),
        ("verified.json", "{not json"),
    ],
    ids=["verified-is-list", "inventory-is-list", "verified-malformed-json"],
)
def test_cli_exits_2_on_malformed_or_wrongly_shaped_input(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    bad_file: str,
    bad_content: str,
) -> None:
    workdir = tmp_path / "wd"
    write_json(workdir / "inventory.json", {"root": str(tmp_path), **_inventory()})
    write_json(workdir / "verified.json",
               {"schema_version": 2, "findings": _worked_example(), "stats": {}})
    (workdir / bad_file).write_text(bad_content, encoding="utf-8")
    assert _main(["--workdir", str(workdir)]) == 2
    assert capsys.readouterr().err.startswith("error:")


@pytest.mark.parametrize("name", ["service-py", "web-ts", "mixed-decoys"])
def test_hotspot_score_correlates_with_planted_debt(
    name: str, request: pytest.FixtureRequest
) -> None:
    """Spec 4.9: hotspot_score tracks planted debt (complexity half unvalidated)."""
    from inventory import build_all

    repo = request.getfixturevalue(name.replace("-", "_") + "_repo")
    inventory, _ = build_all(repo, churn_months=240, config=DEFAULTS)
    planted = json.loads(
        (Path(__file__).parent / "fixtures" / "corpus" / name / "planted.json").read_bytes()
    )
    planted_paths = {p["path"] for p in planted["planted"] if p.get("path")}
    decoy_paths = {d["path"] for d in planted.get("decoys", []) if d.get("path")}
    scores = {e["path"]: e["hotspot_score"] for e in inventory["files"]
              if e["path_class"] == "source"}
    if len(scores) < 4 or not planted_paths & set(scores):
        pytest.skip("fixture too small for a correlation check")
    in_planted = [p for p in scores if p in planted_paths]
    # Decoys are deliberately built to look like debt (a 300-line lookup table, a
    # fluent builder, a main() that logs-and-exits, ...) without being debt; they
    # carry high complexity and so high hotspot_score. Excluding them from "other"
    # keeps this a comparison between planted debt and genuinely unremarkable files.
    not_planted = [p for p in scores if p not in planted_paths and p not in decoy_paths]
    mean_planted = sum(scores[p] for p in in_planted) / len(in_planted)
    mean_other = sum(scores[p] for p in not_planted) / max(1, len(not_planted))
    assert mean_planted >= mean_other, (
        f"mean_planted={mean_planted!r} mean_other(excl. decoys)={mean_other!r}"
    )
