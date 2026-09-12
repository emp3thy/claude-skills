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
replace the scout's. The two unverified states get different reasons: not
selected (raise ``--top`` or the verifier budget) and selected with no verdict
returned (re-dispatch that batch). Migration's "churn on both sides" lift uses the
``coupling`` corroboration only, because a candidate carries churn for its
primary file alone. Every finding also carries ``tier_reason``, the prose for
why it landed on its tier -- computed on the same branch as the tier itself
(``_tier_and_reason``) so the two cannot disagree -- which the design writer's
tier C table renders in place of the bare verdict word. A capped finding's
reason names the corroboration that family's cap actually wants (tool,
coupling, both, a specific signal token, or -- for doc-drift and
pipeline-infra, which never lift -- neither), read off ``_family_cap_and_lift``
so the wording cannot drift from ``family_cap``'s own branching; a tool-raised
candidate gets its own wording there, because its ``confirmed_by`` is empty by
design and the scout sentence would read as "no tool corroborated this" on a
finding a tool raised. Every piece of
verifier prose kept on a finding (``proof``, ``checked``, ``opened``,
``trap_matched``) goes through ``redaction.redact`` first: the verifier reads
the repository, so it can quote a credential back.
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
TEST_GAPS_LIFT_TOKEN: Final[str] = "signal:no-mapped-tests"


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


def _family_cap_and_lift(cand: dict[str, Any]) -> tuple[str | None, str | None]:
    """The family's cap tier and, from the same branch, what would lift it.

    One function so the cap and its description cannot disagree: ``family_cap``
    and the cap sentence in ``_tier_and_reason`` are both read off this rather
    than a second table naming what each family wants, which could drift from
    the tier logic below. The lift half is ``None`` exactly when nothing in
    ``confirmed_by`` can lift the cap at all -- doc-drift and pipeline-infra
    scout findings are always capped -- so the caller can pick a template that
    does not promise a way out that does not exist.
    """
    family = cand["family"]
    signals = cand.get("signals") or {}
    tool, coupling = _has(cand, "tool:"), _token(cand, "coupling")
    if family == "duplication":
        return (None if tool or coupling else "B"), "tool or coupling corroboration"
    if family == "dead-code":
        if tool:
            return None, "tool corroboration"
        ordinary = (signals.get("churn") == 0 and signals.get("fan_in_approx") == 0
                    and signals.get("path_class") == "source")
        return ("B" if ordinary else "C"), "tool corroboration"
    if family == "god-classes":
        capped = cand.get("type_id") == "TD-20" and not coupling
        return ("B" if capped else None), "coupling corroboration"
    if family == "architecture":
        if tool or coupling:
            return None, "tool or coupling corroboration"
        return ("C" if cand.get("type_id") == "TD-10" else "B"), "tool or coupling corroboration"
    if family == "test-gaps":
        lifted = _token(cand, TEST_GAPS_LIFT_TOKEN)
        return (None if lifted else "B"), f"the {TEST_GAPS_LIFT_TOKEN} signal"
    if family == "test-quality":
        # Spec 2.3: "tier B max without CI data" -- the cap still lifts on a
        # ``tool:`` token like dependency-debt's and security's do (a family with
        # no tool signals of its own in practice never exercises the lift), but the
        # reason says what spec 2.3 actually names: this scan never reads CI data,
        # not "tool corroboration", which this family gets no tool signals for.
        return (None if tool else "B"), "CI data, which this scan never reads"
    if family == "performance":
        # Spec 2026-09-12, section 3. TD-37 is a cardinality claim: N+1, complexity,
        # "will not scale". Nothing static can prove the N, so it is capped at C
        # whatever the verifier says; the lift names what would be needed.
        if cand.get("type_id") == "TD-37":
            return "C", "runtime evidence, which this scan never reads"
        return (None if tool else "B"), "tool corroboration"
    if family == "concerns":
        # No cap: confirm is B, confirm plus a hotspot or coupling token is A --
        # the base rule in _tier_and_reason, stated here so the family is listed.
        return None, None
    if family in ("dependency-debt", "security"):
        return (None if tool else "B"), "tool corroboration"
    if family == "migration":
        return (None if coupling else "B"), "coupling corroboration"
    if family in ("doc-drift", "pipeline-infra") and cand.get("source") == "scout":
        return "B", None
    return None, None


def family_cap(cand: dict[str, Any]) -> str | None:
    """The strongest tier the family allows without enough corroboration; None means no cap."""
    return _family_cap_and_lift(cand)[0]


def _weakest(a: str, b: str | None) -> str:
    return a if b is None or TIER_ORDER[a] >= TIER_ORDER[b] else b


def _tier_and_reason(
    cand: dict[str, Any], verdict: dict[str, Any] | None, *, selected: bool
) -> tuple[str | None, str]:
    """The earned tier and, on the same branch, why it earned it.

    One function so the tier and its reason cannot disagree: ``earned_tier`` and
    ``tier_reason`` are both thin wrappers over this that discard the half they
    don't need, rather than two copies of the same branching.

    ``selected`` splits the one tier the verifier never spoke for. Both states
    are tier C, but they call for opposite responses: a candidate the budget
    rule left below the cut is recovered by raising ``--top`` or the verifier
    budget, while one the plan *did* select and got no verdict for means a
    verifier batch was lost or came back short, and is recovered by
    re-dispatching that batch -- the only one of the two where re-running
    recovers a real answer. ``apply`` already counts them apart
    (``stats.missing_verdict``); this is the same fact in the sentence the
    maintainer reads.
    """
    if cand.get("tier") == "A":
        if cand.get("source") == "rule":
            return "A", "a deterministic rule finding, true by construction"
        return "A", "a published advisory, true by construction"
    if verdict is None:
        if selected:
            return "C", "selected for verification, but no verdict came back"
        return "C", "not selected for verification"
    kind = str(verdict.get("verdict"))
    if kind == "reject":
        return None, "the verifier rejected it"
    if kind == "downgrade":
        return "C", "the verifier downgraded it"
    if kind == "refer":
        return "C", "the verifier referred it"
    if kind != "confirm" or not all(e.get("quote_verified") for e in cand.get("evidence", [])):
        return "C", "a quote could not be verified"
    base = "A" if corroborated(cand) else "B"
    cap, lift = _family_cap_and_lift(cand)
    tier = _weakest(base, cap)
    if cap is not None:
        if lift is None:
            return tier, f"{cand['family']} is capped at {tier} for every scout-detected finding"
        if cand.get("source") == "tool":
            # A tool-raised candidate carries an empty ``confirmed_by`` on purpose
            # (a self-token would read as an independent second source and lift
            # this very cap), so it always lands here. Saying "without tool
            # corroboration" -- word for word what a scout-only finding gets --
            # would tell the maintainer no tool corroborated the secret a tool
            # found, and make the two indistinguishable in the report's tables.
            return tier, (f"{cand['family']} is capped at {tier}: the tool that raised it is "
                          f"not its own corroboration, and there is no other {lift}")
        return tier, f"{cand['family']} is capped at {tier} without {lift}"
    if tier == "A":
        own = f"scout:{cand['family']}"
        tokens = ", ".join(s for s in cand.get("confirmed_by", []) if s != own)
        return tier, f"confirmed and corroborated by {tokens}"
    return tier, "confirmed, with no independent corroboration"


def earned_tier(
    cand: dict[str, Any], verdict: dict[str, Any] | None, *, selected: bool = False
) -> str | None:
    """The earned tier. ``selected`` defaults because the tier is C either way; only
    the reason half of ``_tier_and_reason`` differs between the two states."""
    return _tier_and_reason(cand, verdict, selected=selected)[0]


def tier_reason(cand: dict[str, Any], verdict: dict[str, Any] | None, *, selected: bool) -> str:
    """Why the finding landed on its tier. ``selected`` has no default here: it is
    exactly the half this function returns that the two no-verdict states differ on."""
    return _tier_and_reason(cand, verdict, selected=selected)[1]


def _finding(
    cand: dict[str, Any], verdict: dict[str, Any] | None, *, selected: bool
) -> dict[str, Any]:
    # `selected` reaches `_tier_and_reason` so the two no-verdict states -- below
    # the budget cut, and selected with a verdict that never came back -- do not
    # share one sentence. Both are tier C and both are `unverified`; only the
    # reason tells them apart, and only one of them is worth re-running.
    out = dict(cand)
    out["tier"], out["tier_reason"] = _tier_and_reason(cand, verdict, selected=selected)
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
