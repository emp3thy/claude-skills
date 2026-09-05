"""Credential redaction shared by every script that writes a quote (spec 4.3, 4.4).

``redact`` cuts every credential-shaped value in a string to its first four
characters, so a password, token or secret assigned as a quoted literal never
reaches a JSON output unredacted, whichever script, rule or family found it.
Both ``patterns.py`` and ``rules.py`` import this module flat, the skill's
sibling-import convention (spec 0(d)); a phase 2 ``merge_findings.py`` can
adopt it without pulling in ``patterns.py``'s scanner machinery or
``rules.py``'s rule tables.
"""
from __future__ import annotations

import re
from typing import Final

CREDENTIAL_RE: Final[re.Pattern[str]] = re.compile(
    r"\b\w*(?:password|passwd|secret|token|api_key|apikey|access_key)\w*[\"']?\s*(?:=|:=|:)\s*"
    r"[\"'](?P<value>[^\"'\n]{8,})[\"']",
    re.IGNORECASE,
)


def redact(text: str) -> str:
    """Cut every credential-shaped value in ``text`` to its first four characters."""

    def cut(match: re.Match[str]) -> str:
        value = match.group("value")
        return match.group(0).replace(value, value[:4] + "***")

    return CREDENTIAL_RE.sub(cut, text)
