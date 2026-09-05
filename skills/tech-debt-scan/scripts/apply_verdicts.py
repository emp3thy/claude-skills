"""Join verifier verdicts to candidates and assign the earned tier (spec 4.8, 2.3 caps).

Reads ``candidates.json``, ``verify-plan.json`` and every ``verdicts/verify-<nn>.json``
the plan names from ``--workdir``; writes ``verified.json``.

Tier A: confirmed, quote verified, and at least one independent corroboration
in ``confirmed_by`` (anything beyond the scout's own ``scout:<family>`` entry).
Tier B: confirmed without corroboration. Tier C: downgraded, referred, or
unverified (not selected, or selected with no verdict). Rejected findings keep
``tier: null`` with the proof for the report's "considered and rejected"
section. Rule findings and tool facts are tier A without a verifier. Family
caps from spec 2.3 apply after a confirm; the verifier's severity and effort
replace the scout's. Migration's "churn on both sides" lift uses the
``coupling`` corroboration only, because a candidate carries churn for its
primary file alone. Every piece of verifier prose kept on a finding (``proof``,
``checked``, ``opened``, ``trap_matched``) goes through ``redaction.redact``
first: the verifier reads the repository, so it can quote a credential back.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Final

from inventory import write_json
from redaction import redact
from validation import ValidationError, validate_effort
from verify_prompts import VERDICT_VALUES

SCHEMA_VERSION: Final[int] = 2
CORROBORATING_PREFIXES: Final[tuple[str, ...]] = ("pattern:", "rule:", "tool:", "signal:")
CORROBORATING_TOKENS: Final[frozenset[str]] = frozenset({"satd", "coupling", "hotspot"})
TIER_ORDER: Final[dict[str, int]] = {"A": 0, "B": 1, "C": 2}


def _has(cand: dict[str, Any], prefix: str) -> bool:
    return any(str(s).startswith(prefix) for s in cand.get("confirmed_by", []))


def _token(cand: dict[str, Any], name: str) -> bool:
    return name in cand.get("confirmed_by", [])


def corroborated(cand: dict[str, Any]) -> bool:
    own = f"scout:{cand['family']}"
    for source in cand.get("confirmed_by", []):
        s = str(source)
        if s == own:
            continue
        if (s.startswith(CORROBORATING_PREFIXES) or s in CORROBORATING_TOKENS
                or s.startswith("scout:")):
            return True
    return False


def family_cap(cand: dict[str, Any]) -> str | None:
    """The strongest tier the family allows without tool corroboration; None means no cap."""
    family = cand["family"]
    signals = cand.get("signals") or {}
    tool, coupling = _has(cand, "tool:"), _token(cand, "coupling")
    if family == "duplication":
        return None if tool or coupling else "B"
    if family == "dead-code":
        if tool:
            return None
        ordinary = (signals.get("churn") == 0 and signals.get("fan_in_approx") == 0
                    and signals.get("path_class") == "source")
        return "B" if ordinary else "C"
    if family == "god-classes":
        return "B" if cand.get("type_id") == "TD-20" and not coupling else None
    if family == "architecture":
        if tool or coupling:
            return None
        return "C" if cand.get("type_id") == "TD-10" else "B"
    if family == "test-gaps":
        return None if _token(cand, "signal:no-mapped-tests") else "B"
    if family in ("test-quality", "dependency-debt", "security"):
        return None if tool else "B"
    if family == "migration":
        return None if coupling else "B"
    if family in ("doc-drift", "pipeline-infra") and cand.get("source") == "scout":
        return "B"
    return None


def _weakest(a: str, b: str | None) -> str:
    return a if b is None or TIER_ORDER[a] >= TIER_ORDER[b] else b


def earned_tier(cand: dict[str, Any], verdict: dict[str, Any] | None) -> str | None:
    if cand.get("tier") == "A":
        return "A"
    if verdict is None:
        return "C"
    kind = str(verdict.get("verdict"))
    if kind == "reject":
        return None
    if kind in ("downgrade", "refer"):
        return "C"
    if kind != "confirm" or not all(e.get("quote_verified") for e in cand.get("evidence", [])):
        return "C"
    base = "A" if corroborated(cand) else "B"
    return _weakest(base, family_cap(cand))


def _finding(
    cand: dict[str, Any], verdict: dict[str, Any] | None, *, selected: bool
) -> dict[str, Any]:
    # `selected` is accepted and unused in phase 2: a selected candidate with no
    # verdict and an unselected one both land in `unverified` here. Kept so the
    # phase 5 baseline can tell the two apart.
    out = dict(cand)
    out["tier"] = earned_tier(cand, verdict)
    if verdict is not None:
        severity = verdict.get("severity")
        if isinstance(severity, int) and not isinstance(severity, bool) and 1 <= severity <= 5:
            out["severity"] = severity
        effort = verdict.get("effort")
        try:
            validate_effort(str(effort))
            out["effort"] = str(effort)
        except ValidationError:
            pass
        if cand["family"] == "test-quality" and not _has(cand, "tool:"):
            out["severity"] = min(int(out["severity"]), 3)
        out["verdict"] = str(verdict.get("verdict"))
        # The verifier reads the repository and quotes it back, so its prose is a
        # credential path like any other written quote (spec 4.3).
        out["proof"] = redact(str(verdict.get("proof", "")))
        out["checked"] = [redact(str(c)) for c in verdict.get("checked", []) or []]
        out["opened"] = [redact(str(o)) for o in verdict.get("opened", []) or []]
        trap = verdict.get("trap_matched")
        out["trap_matched"] = redact(str(trap)) if trap else None
        out["verified"] = True
    elif cand.get("tier") == "A":
        out.update({"verdict": "rule", "proof": "verified by construction",
                    "checked": [], "opened": [], "trap_matched": None, "verified": True})
    else:
        out.update({"verdict": "unverified", "proof": "", "checked": [], "opened": [],
                    "trap_matched": None, "verified": False})
    return out


def apply(
    candidates: list[dict[str, Any]],
    verify_plan: dict[str, Any],
    verdicts: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    known = {c["fingerprint"] for c in candidates}
    by_fp: dict[str, dict[str, Any]] = {}
    unknown = 0
    for items in verdicts.values():
        for item in items:
            if not isinstance(item, dict) or item.get("verdict") not in VERDICT_VALUES:
                continue
            fp = str(item.get("fingerprint"))
            if fp in known:
                by_fp[fp] = item
            else:
                unknown += 1
    selected = set(verify_plan.get("selected", []))
    findings = [_finding(c, by_fp.get(c["fingerprint"]), selected=c["fingerprint"] in selected)
                for c in candidates]
    counts = {"A": 0, "B": 0, "C": 0}
    rejected = 0
    for f in findings:
        if f["tier"] in counts:
            counts[f["tier"]] += 1
        elif f["verdict"] == "reject":
            rejected += 1
    stats = {
        "selected": len(selected),
        "verdicts": len(by_fp),
        "unknown_fingerprint": unknown,
        "missing_verdict": len([fp for fp in selected if fp not in by_fp]),
        "tier_a": counts["A"], "tier_b": counts["B"], "tier_c": counts["C"], "rejected": rejected,
    }
    return {"schema_version": SCHEMA_VERSION, "findings": findings, "stats": stats}


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply verifier verdicts and write verified.json")
    parser.add_argument("--workdir", default=".tech-debt", help="directory holding the scan files")
    args = parser.parse_args(argv)
    workdir = Path(args.workdir)
    cand_path, plan_path = workdir / "candidates.json", workdir / "verify-plan.json"
    if not cand_path.is_file() or not plan_path.is_file():
        message = f"error: candidates.json and verify-plan.json are required in {workdir}"
        print(message, file=sys.stderr)
        return 2
    try:
        cand_doc = json.loads(cand_path.read_bytes())
        if not isinstance(cand_doc, dict) or not isinstance(cand_doc.get("candidates"), list):
            raise ValueError(f"candidates.json in {workdir} must be an object with a "
                              "candidates list")
        candidates = cand_doc["candidates"]
        plan = json.loads(plan_path.read_bytes())
        if (not isinstance(plan, dict) or not isinstance(plan.get("batches"), list)
                or not isinstance(plan.get("selected"), list)):
            raise ValueError(f"verify-plan.json in {workdir} must be an object with "
                              "batches and selected lists")
        verdicts: dict[str, list[dict[str, Any]]] = {}
        for batch in plan.get("batches", []):
            path = workdir / str(batch["output"])
            if not path.is_file():
                print(f"warning: {path} missing; its candidates stay unverified", file=sys.stderr)
                continue
            loaded = json.loads(path.read_bytes())
            verdicts[str(batch["output"])] = loaded if isinstance(loaded, list) else []
        doc = apply(candidates, plan, verdicts)
    # OSError covers an unreadable input; ValueError covers bad JSON or a
    # document of the wrong top-level shape; KeyError covers a batch without
    # an "output" key.
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    write_json(workdir / "verified.json", doc)
    s = doc["stats"]
    print(f"tier A {s['tier_a']}, B {s['tier_b']}, C {s['tier_c']}, rejected {s['rejected']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
