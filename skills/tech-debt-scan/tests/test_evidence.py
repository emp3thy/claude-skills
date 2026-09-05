"""evidence.py: fingerprint, quote normalisation and search, inventory signals (spec 4.7)."""
from __future__ import annotations

from typing import Any

from evidence import find_quote, fingerprint, normalise_quote, signals_for


def test_fingerprint_matches_the_phase_1_rule_findings_shape() -> None:
    fp, quote_hash = fingerprint("pipeline-infra", "Dockerfile", "FROM alpine")
    assert len(fp) == 16 and len(quote_hash) == 40
    assert fingerprint("pipeline-infra", "Dockerfile", "FROM   alpine ") == (fp, quote_hash)
    assert fingerprint("security", "Dockerfile", "FROM alpine")[0] != fp


def test_normalise_quote_collapses_whitespace() -> None:
    assert normalise_quote("  a \t b\n\n c ") == "a b c"


def test_find_quote_prefers_the_cited_range_then_anywhere() -> None:
    lines = [
        "x = 1", "try:", "    pass", "except Exception:", "    pass", "y = 2", "try:", "    pass",
    ]
    assert find_quote(lines, "except Exception:\n    pass", 4, 5) == (4, 5)
    assert find_quote(lines, "except Exception:  pass", 1, 2) == (4, 5)
    assert find_quote(lines, "try:\n    pass", 7, 8) == (7, 8)
    assert find_quote(lines, "try:\n    pass", None, None) == (2, 3)
    assert find_quote(lines, "not here", 1, 1) is None
    assert find_quote(lines, "", 1, 1) is None


def test_signals_for_reads_files_then_artefacts_then_null_shape() -> None:
    inventory: dict[str, Any] = {
        "hotspot_band": ["a.py"],
        "files": [{"path": "a.py", "hotspot_score": 0.5, "churn": 3, "coupling_degree": 1,
                   "fan_in_approx": 2, "path_class": "source"}],
        "artefacts": {"ci": [{"path": ".github/workflows/ci.yml", "path_class": "source"}]},
    }
    assert signals_for(inventory, "a.py") == {
        "hotspot_score": 0.5, "churn": 3, "coupling_degree": 1, "fan_in_approx": 2,
        "path_class": "source", "in_hotspot_band": True,
    }
    assert signals_for(inventory, ".github/workflows/ci.yml")["path_class"] == "source"
    assert signals_for(inventory, ".github/workflows/ci.yml")["in_hotspot_band"] is False
    assert signals_for(inventory, None) == {
        "hotspot_score": 0.0, "churn": 0, "coupling_degree": 0, "fan_in_approx": None,
        "path_class": None, "in_hotspot_band": False,
    }
    assert list(signals_for(inventory, "a.py")) == [
        "hotspot_score", "churn", "coupling_degree", "fan_in_approx", "path_class",
        "in_hotspot_band",
    ]
