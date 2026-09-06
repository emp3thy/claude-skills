"""Pure normalisers turning one tool's output into signals (spec 4.5).

Every function here takes an already-parsed payload and the repository root
and returns a list of ``Signal`` dicts. Nothing in this module runs a
subprocess, reads a file or touches config, so each normaliser is testable
from a captured payload with nothing mocked; ``tools_probe.py`` owns every
side effect.

Signals are the probe's whole vocabulary. ``fact`` marks a signal a human
would accept without a second opinion -- a published vulnerability, a
committed secret, a Dockerfile rule -- and only fact-class signals may
become candidates in phase 4b. Everything else is a lead or corroboration.

No field that can carry source text or a credential is ever copied into a
signal. gitleaks reports the matched secret in ``Secret`` and ``Match`` and
jscpd reports the duplicated source in ``fragment``; both are dropped rather
than redacted, because a redacted secret is still its own first four
characters while a dropped one is nothing (spec 4.5).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Final, TypedDict


class Signal(TypedDict):
    """One normalised observation from one tool."""

    tool: str
    family: str
    kind: str
    file: str | None
    line_start: int | None
    line_end: int | None
    message: str
    fact: bool
    extra: dict[str, Any]


# Every family a normaliser may assign. Checked against categories.FAMILIES by
# a test: a family name the skill does not know would reach candidates in 4b
# and match nothing there.
SIGNAL_FAMILIES: Final[frozenset[str]] = frozenset(
    {
        "complex-units", "dead-code", "dependency-debt", "duplication",
        "error-masking", "architecture", "security", "pipeline-infra",
    }
)

KINDS: Final[frozenset[str]] = frozenset(
    {
        "vuln", "secret", "clone", "cycle", "unused", "deprecated",
        "complexity", "error-masking", "dockerfile", "workflow",
    }
)


def rel_path(root: Path, raw: Any) -> str | None:
    """``raw`` as a root-relative forward-slashed path, or None if unusable.

    Tools disagree about path shape and ruff reports an absolute path with
    backslashes even for relative input, so an absolute path under ``root``
    is relativised rather than rejected. This is the one deliberate
    difference from ``merge_findings._normalise_path``, which rejects every
    absolute path because a scout must never cite one.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.replace("\\", "/").strip()
    root_text = str(root).replace("\\", "/").rstrip("/")
    if root_text and (text == root_text or text.lower().startswith(root_text.lower() + "/")):
        text = text[len(root_text) + 1 :]
    while text.startswith("./"):
        text = text[2:]
    if not text:
        return None
    if text.startswith("/") or ".." in text.split("/") or ":" in text.split("/")[0]:
        return None
    return text


def signal(
    tool: str,
    family: str,
    kind: str,
    *,
    file: str | None,
    line_start: int | None = None,
    line_end: int | None = None,
    message: str,
    fact: bool,
    extra: dict[str, Any] | None = None,
) -> Signal:
    """A ``Signal`` with its kind checked against the spec's closed set."""
    if kind not in KINDS:
        raise ValueError(f"unknown signal kind {kind!r}; spec 4.5 fixes the set")
    if family not in SIGNAL_FAMILIES:
        raise ValueError(f"unknown family {family!r}; categories.FAMILIES fixes the set")
    return Signal(
        tool=tool,
        family=family,
        kind=kind,
        file=file,
        line_start=line_start,
        line_end=line_end,
        message=message,
        fact=fact,
        extra=extra or {},
    )
