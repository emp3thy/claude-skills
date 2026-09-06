"""Credential redaction shared by every script that writes a quote (spec 4.3, 4.4).

``redact`` cuts every credential-shaped value in a string to its first four
characters, so a password, token or secret assigned as a quoted literal never
reaches a JSON output unredacted, whichever script, rule or family found it.
Both ``patterns.py`` and ``rules.py`` import this module flat, the skill's
sibling-import convention (spec 0(d)); a phase 2 ``merge_findings.py`` can
adopt it without pulling in ``patterns.py``'s scanner machinery or
``rules.py``'s rule tables.

Two patterns run, in this order:

``CREDENTIAL_RE`` matches the assignment shape ``<name> = "value"``. It is also
the ``security`` / ``credential`` detection rule in ``patterns.py``, so its
scope is deliberately frozen: widening it would change what the scan *finds*,
not just what it hides, and would move every ranked golden and evaluation
number with it.

``SECRET_TOKEN_RE`` matches a well-known secret by its issuer prefix wherever it
appears, with no assignment needed. It exists because an agent that *restates* a
value in prose ("api_key value is 'sk_live_...'") puts no operator between the
name and the value, so the assignment regex is a no-op on it, and the negative-
space sections of ``design.md`` carry agent prose verbatim. It is used only by
``redact``; no ``Rule`` references it, so detection is untouched. Recognition is
by prefix, not by entropy, so an ordinary identifier that merely starts with an
issuer's marker (``sk_live_handler``, ``npm_registry_client``) carries no token
body of a plausible length and is left alone.

Both cut to the same ``value[:4] + "***"`` shape, so a reader cannot tell which
pattern caught a given secret.
"""
from __future__ import annotations

import re
from typing import Final

CREDENTIAL_RE: Final[re.Pattern[str]] = re.compile(
    r"\b\w*(?:password|passwd|secret|token|api_key|apikey|access_key)\w*[\"']?\s*(?:=|:=|:)\s*"
    r"[\"'](?P<value>[^\"'\n]{8,})[\"']",
    re.IGNORECASE,
)

SECRET_TOKEN_RE: Final[re.Pattern[str]] = re.compile(
    r"""
      # Stripe secret and restricted keys
      \b(?:sk|rk)_(?:live|test)_[A-Za-z0-9_]{16,}
      # GitHub personal-access, OAuth, user-to-server, server-to-server, refresh
    | \bgh[pousr]_[A-Za-z0-9]{20,}
      # GitHub fine-grained personal access tokens
    | \bgithub_pat_[A-Za-z0-9_]{30,}
      # AWS access key ids (long-lived, temporary, role, user, service, ...)
    | \b(?:A3T[A-Z0-9]|ABIA|ACCA|AGPA|AIDA|AIPA|AKIA|ANPA|ANVA|AROA|ASIA)
      [A-Z0-9]{16}(?![A-Z0-9])
      # Slack bot / user / app-level / legacy tokens
    | \bxox[abeprs]-[A-Za-z0-9-]{20,}
    | \bxapp-[A-Za-z0-9-]{20,}
      # Google API keys
    | \bAIza[A-Za-z0-9_-]{35}(?![A-Za-z0-9_-])
      # GitLab personal access tokens
    | \bglpat-[A-Za-z0-9_-]{20,}
      # npm automation and publish tokens
    | \bnpm_[A-Za-z0-9]{20,}
      # DigitalOcean personal access, OAuth and refresh tokens
    | \bdo[oprs]_v1_[A-Za-z0-9]{32,}
      # PEM private key header, any algorithm (a certificate header is not one)
    | -----BEGIN\ (?:[A-Z0-9]+\ )*PRIVATE\ KEY-----
    """,
    re.VERBOSE,
)


def _cut(value: str) -> str:
    """The redacted stand-in for one secret: its first four characters, then ``***``."""
    return value[:4] + "***"


def redact(text: str) -> str:
    """Cut every credential-shaped value in ``text`` to its first four characters."""

    def cut_assignment(match: re.Match[str]) -> str:
        value = match.group("value")
        return match.group(0).replace(value, _cut(value))

    # The assignment pass runs first, so a known token written as a quoted value is
    # cut once, by the regex that also detects it; what reaches the second pass is
    # already a stub too short for any issuer prefix to match.
    text = CREDENTIAL_RE.sub(cut_assignment, text)
    return SECRET_TOKEN_RE.sub(lambda m: _cut(m.group(0)), text)
