"""Deterministic priority ranking of verified findings (spec 4.9).

Reads ``verified.json`` and ``inventory.json`` from ``--workdir`` and
``.tech-debt.yaml`` from the repository root; writes ``ranked.json``.

    priority     = severity x interest x tier_weight x tractability
    interest     = 1 + wH*H + wC*C + wF*F   (H, C, F in [0, 1], repo-relative)
    tier_weight  = A 1.0, B 0.7, C 0.35
    tractability = S 1.0, M 0.75, L 0.5 (quick-wins: 1.0, 0.5, 0.2)

Only tier A and B findings can enter the top N; tier C, rejected and (under
``quick-wins``) uncorroborated duplication and ownership findings are emitted
with ``in_top_n: false``. No family holds more than ``ceil(spread_cap x N)`` of
the top N; a displaced finding carries ``spread_capped: true``. Ties break on
the fingerprint. Every term, the preset, the weights and ``formula_version``
are recorded so a reader can recompute any priority; the output is
byte-identical for identical inputs.
"""
from __future__ import annotations

import argparse
import json
import sys
from math import ceil
from pathlib import Path
from typing import Any, Final

from config import ConfigError, load_config
from evidence import priority_terms, repo_maxima
from inventory import write_json

SCHEMA_VERSION: Final[int] = 2
FORMULA_VERSION: Final[int] = 1
PRESETS: Final[dict[str, dict[str, Any]]] = {
    "balanced": {"weights": {"wH": 1.0, "wC": 0.5, "wF": 0.5},
                 "tractability": {"S": 1.0, "M": 0.75, "L": 0.5}, "exclude": False},
    "hotspot-first": {"weights": {"wH": 1.5, "wC": 0.5, "wF": 0.25},
                      "tractability": {"S": 1.0, "M": 0.75, "L": 0.5}, "exclude": False},
    "architecture": {"weights": {"wH": 0.75, "wC": 1.0, "wF": 1.0},
                     "tractability": {"S": 1.0, "M": 0.75, "L": 0.5}, "exclude": False},
    "quick-wins": {"weights": {"wH": 1.0, "wC": 0.5, "wF": 0.5},
                   "tractability": {"S": 1.0, "M": 0.5, "L": 0.2}, "exclude": True},
}
ELIGIBLE_TIERS: Final[frozenset[str]] = frozenset({"A", "B"})


def _settings(
    config: dict[str, Any], preset: str
) -> tuple[dict[str, float], dict[str, float], bool]:
    if preset not in PRESETS:
        raise ConfigError(f"unknown preset {preset!r}; expected one of {sorted(PRESETS)}")
    chosen = PRESETS[preset]
    if preset == "balanced":
        rcfg = config.get("ranking") or {}
        weights = {k: float(v) for k, v in (rcfg.get("weights") or chosen["weights"]).items()}
        tract_src = rcfg.get("tractability") or chosen["tractability"]
        tract = {k: float(v) for k, v in tract_src.items()}
        return weights, tract, False
    return dict(chosen["weights"]), dict(chosen["tractability"]), bool(chosen["exclude"])


def _excluded_by_quick_wins(finding: dict[str, Any]) -> bool:
    if finding["family"] == "ownership":
        return True
    if finding["family"] == "duplication":
        sources = finding.get("confirmed_by", [])
        return not any(str(s).startswith("tool:") or s == "coupling" for s in sources)
    return False


def rank(
    verified: dict[str, Any],
    inventory: dict[str, Any],
    config: dict[str, Any],
    *,
    preset: str,
    top: int,
) -> dict[str, Any]:
    weights, tract, exclude = _settings(config, preset)
    maxima = repo_maxima(inventory)
    modes = {str(e["path"]): str(e.get("fan_in_mode", "import-lines"))
             for e in inventory.get("files", [])}
    spread_cap = float((config.get("ranking") or {}).get("spread_cap", 0.5))
    per_family_cap = max(1, ceil(spread_cap * top))
    scored: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for finding in verified.get("findings", []):
        primary = finding["evidence"][0]["file"] if finding.get("evidence") else ""
        mode = modes.get(primary, "import-lines")
        terms = priority_terms(
            finding, maxima, weights, tract, tier=finding.get("tier"), fan_in_mode=mode
        )
        scored.append((finding, terms))
    scored.sort(key=lambda item: (-item[1]["priority"], item[0]["fingerprint"]))
    chosen: list[str] = []
    per_family: dict[str, int] = {}
    entries: list[dict[str, Any]] = []
    for position, (finding, terms) in enumerate(scored, start=1):
        excluded = exclude and _excluded_by_quick_wins(finding)
        eligible = finding.get("tier") in ELIGIBLE_TIERS and not excluded
        capped = False
        in_top = False
        if eligible and len(chosen) < top:
            if per_family.get(finding["family"], 0) < per_family_cap:
                chosen.append(finding["fingerprint"])
                per_family[finding["family"]] = per_family.get(finding["family"], 0) + 1
                in_top = True
            else:
                capped = True
        entries.append({
            "fingerprint": finding["fingerprint"], "rank": position,
            "priority": terms["priority"], "terms": terms, "tier": finding.get("tier"),
            "in_top_n": in_top, "spread_capped": capped,
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "formula_version": FORMULA_VERSION,
        "preset": preset,
        "top": int(top),
        "weights": weights,
        "tractability": tract,
        "top_n": chosen,
        "findings": entries,
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rank verified findings deterministically")
    parser.add_argument("--workdir", default=".tech-debt", help="directory holding verified.json")
    parser.add_argument("--preset", default=None,
                        help="balanced, hotspot-first, architecture or quick-wins")
    parser.add_argument("--top", type=int, default=None,
                        help="findings to report (default: config)")
    args = parser.parse_args(argv)
    workdir = Path(args.workdir)
    verified_path, inventory_path = workdir / "verified.json", workdir / "inventory.json"
    if not verified_path.is_file() or not inventory_path.is_file():
        message = f"error: verified.json and inventory.json are required in {workdir}"
        print(message, file=sys.stderr)
        return 2
    try:
        inventory = json.loads(inventory_path.read_bytes())
        if not isinstance(inventory, dict):
            raise ValueError(f"inventory.json in {workdir} must be an object")
        verified = json.loads(verified_path.read_bytes())
        if not isinstance(verified, dict) or not isinstance(verified.get("findings"), list):
            raise ValueError(f"verified.json in {workdir} must be an object with a findings list")
        config = load_config(Path(str(inventory.get("root", "."))))
        preset = args.preset or str(config["ranking"]["preset"])
        top = args.top if args.top is not None else int(config["top"])
        doc = rank(verified, inventory, config, preset=preset, top=top)
    # OSError covers an unreadable input; ValueError covers bad JSON (json.loads
    # raises a JSONDecodeError, a ValueError subclass) or a document of the
    # wrong top-level shape; KeyError covers a finding missing a required key;
    # ConfigError covers an unknown --preset or an unusable .tech-debt.yaml.
    except (ConfigError, OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    write_json(workdir / "ranked.json", doc)
    print(f"ranked {len(doc['findings'])} finding(s); "
          f"top {len(doc['top_n'])} under preset {preset}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
