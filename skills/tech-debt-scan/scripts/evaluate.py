"""Score scan output against a fixture's ``planted.json`` (spec 6).

Reads ``findings.json`` (preferred) or ``verified.json`` from the workdir,
plus ``ranked.json`` when present for top-N membership, and reports per
family: planted items found (recall), reported findings that hit a planted
item (precision), and decoy hits by tier; plus whether any decoy sits in
tier A or in the top N, which are the hard release bars from v2.0. A finding
is "reported" when its tier is A or B; tier C is listed for a human and never
counts toward precision or recall.

``planted.json`` may carry a top-level ``churn_months``: the inventory window
the fixture is scored under, because a corpus's commit dates are fixed while
the default window moves. It is reported back as ``churn_months`` (null when
the fixture does not record one) and printed above the table, so a harness can
see which window produced the numbers.

A finding hits a planted item or decoy when the families match and one
evidence item names the same file (a null path matches a repository-level
finding with null evidence) and, when the item carries a non-zero line range
and the evidence carries lines, the ranges overlap. The report never fails
the process; the phase 5 live harness reads the counts.

``python scripts/evaluate.py --planted <planted.json> --workdir <dir> [--top N] [--json]``
prints a table, or the JSON report with ``--json``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Final

SCHEMA_VERSION: Final[int] = 2
REPORTED_TIERS: Final[tuple[str, ...]] = ("A", "B")
TIER_RANK: Final[dict[str, int]] = {"A": 0, "B": 1, "C": 2}


def _as_list(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, list):
        return [item for item in document if isinstance(item, dict)]
    if isinstance(document, dict):
        for key in ("findings", "candidates"):
            if isinstance(document.get(key), list):
                return [item for item in document[key] if isinstance(item, dict)]
    return []


def load_findings(workdir: Path) -> tuple[list[dict[str, Any]], str]:
    """(findings, file name used): findings.json when present, else verified.json."""
    for name in ("findings.json", "verified.json"):
        path = workdir / name
        if path.is_file():
            return _as_list(json.loads(path.read_bytes())), name
    raise FileNotFoundError(f"neither findings.json nor verified.json in {workdir}")


def load_top_n(workdir: Path) -> set[str]:
    path = workdir / "ranked.json"
    if not path.is_file():
        return set()
    document = json.loads(path.read_bytes())
    top = document.get("top_n") if isinstance(document, dict) else None
    return {str(fp) for fp in top} if isinstance(top, list) else set()


def _ranges_overlap(start: int, end: int, item_lines: list[int]) -> bool:
    return not (end < item_lines[0] or start > item_lines[1])


def hits(finding: dict[str, Any], item: dict[str, Any]) -> bool:
    """True when ``finding`` points at the planted item or decoy ``item``."""
    if finding.get("family") != item.get("family"):
        return False
    path = item.get("path")
    lines = item.get("lines")
    ranged = isinstance(lines, list) and len(lines) == 2 and lines != [0, 0]
    for evidence in finding.get("evidence") or []:
        if evidence.get("file") != path:
            continue
        if path is None or not ranged:
            return True
        start = evidence.get("line_start")
        if start is None:
            return True
        end = evidence.get("line_end")
        end = start if end is None else end
        if (isinstance(lines, list) and len(lines) == 2
                and _ranges_overlap(int(start), int(end), [int(lines[0]), int(lines[1])])):
            return True
    return False


def _ratio(part: int, whole: int) -> float | None:
    return round(part / whole, 3) if whole else None


def evaluate(
    findings: list[dict[str, Any]],
    planted_doc: dict[str, Any],
    top_n: set[str],
    *,
    top: int = 5,
) -> dict[str, Any]:
    planted = [p for p in planted_doc.get("planted", []) if isinstance(p, dict)]
    decoys = [d for d in planted_doc.get("decoys", []) if isinstance(d, dict)]
    window = planted_doc.get("churn_months")
    reported = [f for f in findings if f.get("tier") in REPORTED_TIERS]
    families = sorted(
        {str(p["family"]) for p in planted}
        | {str(d["family"]) for d in decoys}
        | {str(f.get("family")) for f in findings}
    )

    planted_report: list[dict[str, Any]] = []
    for item in planted:
        tiers = sorted(
            (str(f.get("tier")) for f in findings if hits(f, item)),
            key=lambda t: TIER_RANK.get(t, 9),
        )
        found = any(hits(f, item) for f in reported)
        expect = TIER_RANK.get(str(item.get("expect_tier", "A")), 0)
        best = TIER_RANK.get(tiers[0], 9) if tiers else 9
        planted_report.append({
            "id": item.get("id"), "family": item.get("family"), "found": found,
            "tiers": tiers, "tier_met": found and best <= expect,
        })
    decoy_report: list[dict[str, Any]] = []
    for item in decoys:
        hitting = [f for f in findings if hits(f, item)]
        decoy_report.append({
            "id": item.get("id"), "family": item.get("family"),
            "hit_tiers": sorted((str(f.get("tier")) for f in hitting),
                                key=lambda t: TIER_RANK.get(t, 9)),
            "in_top_n": any(str(f.get("fingerprint")) in top_n or f.get("in_top_n") is True
                            for f in hitting),
        })

    per_family: dict[str, dict[str, Any]] = {}
    for family in families:
        fam_planted = [p for p in planted if p.get("family") == family]
        fam_reported = [f for f in reported if f.get("family") == family]
        found_count = sum(
            1 for p in fam_planted if any(hits(f, p) for f in fam_reported)
        )
        precise = sum(1 for f in fam_reported if any(hits(f, p) for p in fam_planted))
        decoy_hits = {tier: 0 for tier in ("A", "B", "C")}
        for f in findings:
            if f.get("family") != family:
                continue
            tier = str(f.get("tier"))
            if tier in decoy_hits and any(hits(f, d) for d in decoys):
                decoy_hits[tier] += 1
        per_family[family] = {
            "planted": len(fam_planted),
            "found": found_count,
            "recall": _ratio(found_count, len(fam_planted)),
            "reported": len(fam_reported),
            "precise": precise,
            "precision": _ratio(precise, len(fam_reported)),
            "decoy_hits": decoy_hits,
        }

    on_planted = sum(1 for f in reported if any(hits(f, p) for p in planted))
    on_decoys = sum(
        1 for f in reported
        if not any(hits(f, p) for p in planted) and any(hits(f, d) for d in decoys)
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "top": top,
        "churn_months": window if isinstance(window, int) else None,
        "families": per_family,
        "planted": planted_report,
        "decoys": decoy_report,
        "decoys_in_tier_a": sum(1 for d in decoy_report if "A" in d["hit_tiers"]),
        "decoys_in_top_n": sum(1 for d in decoy_report if d["in_top_n"]),
        "counts": {
            "reported": len(reported),
            "on_planted": on_planted,
            "on_decoys": on_decoys,
            "unplanted": len(reported) - on_planted - on_decoys,
        },
    }


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def render_table(report: dict[str, Any]) -> str:
    window = report.get("churn_months")
    rows = [
        f"scored at churn_months {window if window is not None else '(unrecorded)'}",
        f"{'family':<18} {'planted':>7} {'found':>5} {'recall':>6} {'reported':>8} "
        f"{'precision':>9} {'decoy A/B/C':>11}",
    ]
    for family, stats in report["families"].items():
        by_tier = stats["decoy_hits"]
        decoys = f"{by_tier['A']}/{by_tier['B']}/{by_tier['C']}"
        rows.append(
            f"{family:<18} {stats['planted']:>7} {stats['found']:>5} {_fmt(stats['recall']):>6} "
            f"{stats['reported']:>8} {_fmt(stats['precision']):>9} {decoys:>11}"
        )
    counts = report["counts"]
    rows.append(
        f"reported {counts['reported']}, on planted {counts['on_planted']}, "
        f"on decoys {counts['on_decoys']}, unplanted {counts['unplanted']}"
    )
    rows.append(f"decoys in tier A: {report['decoys_in_tier_a']}")
    rows.append(f"decoys in top {report['top']}: {report['decoys_in_top_n']}")
    return "\n".join(rows)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score scan output against planted.json")
    parser.add_argument("--planted", required=True, help="path to the fixture's planted.json")
    parser.add_argument(
        "--workdir",
        default=".tech-debt",
        help="directory holding findings.json or verified.json and optionally ranked.json",
    )
    parser.add_argument("--top", type=int, default=5, help="top-N size used for the decoy check")
    parser.add_argument("--json", action="store_true", help="print the JSON report instead")
    args = parser.parse_args(argv)
    planted_path = Path(args.planted)
    workdir = Path(args.workdir)
    if not planted_path.is_file():
        print(f"error: {planted_path} not found", file=sys.stderr)
        return 2
    try:
        planted_doc = json.loads(planted_path.read_bytes())
        findings, source = load_findings(workdir)
        top_n = load_top_n(workdir)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    report = evaluate(findings, planted_doc, top_n, top=args.top)
    report["source"] = source
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render_table(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
