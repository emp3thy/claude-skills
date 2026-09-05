"""Evidence helpers shared by every script that fingerprints, verifies or scores a quote.

A leaf module (standard library only, no sibling imports) so ``rules.py``,
``merge_findings.py``, ``verify_prompts.py``, ``rank.py`` and phase 5's
``baseline.py`` can import it without pulling in each other's tables.

``fingerprint`` is spec 4.7 step 4; ``find_quote`` is step 3 (cited range first,
then anywhere in the file, whitespace-normalised); ``signals_for`` is step 6.
``repo_maxima`` and ``priority_terms`` are the 4.9 priority formula, defined
once here so ``verify_prompts.py`` (provisional ranking at tier B) and
``rank.py`` (the real ranking) compute it the same way.
"""
from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

SIGNAL_KEYS: tuple[str, ...] = (
    "hotspot_score", "churn", "coupling_degree", "fan_in_approx", "path_class", "in_hotspot_band",
)


def normalise_quote(text: str) -> str:
    """Collapse every whitespace run to one space and strip the ends."""
    return " ".join(text.split())


def fingerprint(family: str, path: str, quote: str) -> tuple[str, str]:
    """Spec 4.7: sha1(family|path|sha1(normalised quote))[:16] and the inner hash."""
    quote_hash = hashlib.sha1(normalise_quote(quote).encode("utf-8")).hexdigest()
    outer = hashlib.sha1(f"{family}|{path}|{quote_hash}".encode()).hexdigest()
    return outer[:16], quote_hash


def _window_matches(lines: Sequence[str], start: int, end: int, wanted: str) -> bool:
    return normalise_quote("\n".join(lines[start - 1:end])) == wanted


def find_quote(
    lines: Sequence[str],
    quote: str,
    line_start: int | None,
    line_end: int | None,
    *,
    max_lines: int = 6,
) -> tuple[int, int] | None:
    """1-based inclusive range holding ``quote`` after whitespace normalisation.

    The cited range is tried first (so a quote that is genuinely there keeps
    its line numbers); otherwise every window of 1 to ``max_lines`` lines is
    tried from the top, and the first match is the real range.
    """
    wanted = normalise_quote(quote)
    if not wanted:
        return None
    total = len(lines)
    if line_start is not None and line_end is not None:
        start, end = max(1, line_start), min(total, max(line_start, line_end))
        if start <= end and _window_matches(lines, start, end, wanted):
            return start, end
    for width in range(1, max_lines + 1):
        for start in range(1, total - width + 2):
            if _window_matches(lines, start, start + width - 1, wanted):
                return start, start + width - 1
    return None


def signals_for(inventory: dict[str, Any], path: str | None) -> dict[str, Any]:
    """The 4.7 ``signals`` object for ``path``: file entry, else artefact entry, else nulls."""
    signals: dict[str, Any] = {
        "hotspot_score": 0.0, "churn": 0, "coupling_degree": 0, "fan_in_approx": None,
        "path_class": None, "in_hotspot_band": False,
    }
    if path is None:
        return signals
    for entry in inventory.get("files", []):
        if entry.get("path") == path:
            signals["hotspot_score"] = entry.get("hotspot_score", 0.0)
            signals["churn"] = entry.get("churn", 0)
            signals["coupling_degree"] = entry.get("coupling_degree", 0)
            signals["fan_in_approx"] = entry.get("fan_in_approx")
            signals["path_class"] = entry.get("path_class")
            signals["in_hotspot_band"] = path in inventory.get("hotspot_band", [])
            return signals
    for entries in (inventory.get("artefacts") or {}).values():
        for artefact in entries:
            if artefact.get("path") == path:
                signals["churn"] = artefact.get("churn", 0)
                signals["path_class"] = artefact.get("path_class")
                return signals
    return signals


TIER_WEIGHT: dict[str | None, float] = {"A": 1.0, "B": 0.7, "C": 0.35, None: 0.7}


def repo_maxima(inventory: dict[str, Any]) -> dict[str, float | int]:
    """Repository maxima for the H, C and F terms; fan-in counts import-line entries only."""
    files = [e for e in inventory.get("files", []) if isinstance(e, dict)]
    hotspot = max((float(e.get("hotspot_score") or 0.0) for e in files), default=0.0)
    coupling = max((int(e.get("coupling_degree") or 0) for e in files), default=0)
    fan_in = max(
        (
            int(e["fan_in_approx"])
            for e in files
            if isinstance(e.get("fan_in_approx"), int)
            and e.get("fan_in_mode", "import-lines") == "import-lines"
        ),
        default=0,
    )
    return {"hotspot": hotspot, "coupling": coupling, "fan_in": fan_in}


def priority_terms(
    candidate: dict[str, Any],
    maxima: dict[str, float | int],
    weights: dict[str, float],
    tractability: dict[str, float],
    *,
    tier: str | None,
    fan_in_mode: str,
) -> dict[str, Any]:
    """Every term of the 4.9 formula, rounded so a reader can recompute the priority."""
    signals = candidate.get("signals") or {}

    def ratio(value: Any, maximum: float | int) -> float:
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not maximum:
            return 0.0
        return round(float(value) / float(maximum), 4)

    h = ratio(signals.get("hotspot_score"), maxima["hotspot"])
    c = ratio(signals.get("coupling_degree"), maxima["coupling"])
    # An ``anywhere`` fan-in is the labelled low-confidence fallback: it never scores.
    f = (
        ratio(signals.get("fan_in_approx"), maxima["fan_in"])
        if fan_in_mode == "import-lines"
        else 0.0
    )
    interest = round(1 + weights["wH"] * h + weights["wC"] * c + weights["wF"] * f, 4)
    tier_weight = TIER_WEIGHT.get(tier, 0.7)
    tract = float(tractability.get(str(candidate.get("effort")), tractability["M"]))
    severity = int(candidate.get("severity") or 0)
    return {
        "severity": severity, "H": h, "C": c, "F": f, "interest": interest,
        "tier_weight": tier_weight, "tractability": tract,
        "priority": round(severity * interest * tier_weight * tract, 4),
    }
