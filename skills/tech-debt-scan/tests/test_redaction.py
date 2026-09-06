"""redaction.py: the shared credential cut used by every script that writes a quote."""
from __future__ import annotations

import pytest
from redaction import CREDENTIAL_RE, SECRET_TOKEN_RE, redact


def test_credential_value_is_cut_to_four_characters() -> None:
    assert redact('api_key = "sk_live_51H8f2kL9mN3pQ7rS4tU6vW"') == 'api_key = "sk_l***"'
    assert redact('RUN export API_TOKEN="abcdefghijkl0123" && pip install requests') == (
        'RUN export API_TOKEN="abcd***" && pip install requests'
    )


def test_a_line_without_a_credential_is_returned_unchanged() -> None:
    line = "def refund(order_id: str) -> None:  # FIXME: the gateway retries twice"
    assert CREDENTIAL_RE.search(line) is None
    assert redact(line) == line


# --- branch review: Important 3, a secret restated in prose ---------------------


def test_a_secret_restated_in_prose_is_redacted() -> None:
    """Branch review Important 3: an agent's restatement carries no assignment shape.

    ``CREDENTIAL_RE`` requires ``<name> = "value"``. A scout or verifier that
    *restates* a value in prose puts no operator between the key name and the
    quoted value, so ``redact`` was a no-op and the raw secret reached
    ``design.md``, ``findings.json`` and the promoted ``PBI.md``. The branch's
    own goldens carry exactly this shape (a placeholder there, but the corpus
    proves the channel fires on a first live run).

    ``SECRET_TOKEN_RE`` closes it by issuer prefix, wherever the token appears,
    and cuts to the same ``value[:4] + "***"`` shape ``CREDENTIAL_RE`` produces,
    so a reader cannot tell which pattern caught it.
    """
    prose = "api_key value is 'sk_live_51H8f2kL9mN3pQ7rS4tU6vW', a real key"
    assert CREDENTIAL_RE.search(prose) is None, "the assignment regex must stay as it is"
    assert redact(prose) == "api_key value is 'sk_l***', a real key"

    # The reviewer's shipped example, in the shape it reaches the document.
    assert redact("api_key value is 'sk_test_placeholder_xxx_do_not_use'") == (
        "api_key value is 'sk_t***'"
    )


@pytest.mark.parametrize(
    ("secret", "cut"),
    [
        ("sk_live_51H8f2kL9mN3pQ7rS4tU6vW", "sk_l***"),
        ("sk_test_51H8f2kL9mN3pQ7rS4tU6vW", "sk_t***"),
        ("rk_live_51H8f2kL9mN3pQ7rS4tU6vW", "rk_l***"),
        ("ghp_16C7e42F292c6912E7710c838347Ae178B4a", "ghp_***"),
        ("gho_16C7e42F292c6912E7710c838347Ae178B4a", "gho_***"),
        ("ghu_16C7e42F292c6912E7710c838347Ae178B4a", "ghu_***"),
        ("ghs_16C7e42F292c6912E7710c838347Ae178B4a", "ghs_***"),
        ("ghr_16C7e42F292c6912E7710c838347Ae178B4a", "ghr_***"),
        ("github_pat_11ABCDEFG0abcdefghij_KLMNOPqrstuvwxyz0123456789ABCDEfghij", "gith***"),
        ("AKIAIOSFODNN7EXAMPLE", "AKIA***"),
        ("ASIAIOSFODNN7EXAMPLE", "ASIA***"),
        ("AROAIOSFODNN7EXAMPLE", "AROA***"),
        ("xoxb-EXAMPLE-NOT-A-REAL-SLACK-TOKEN", "xoxb***"),
        ("xoxp-EXAMPLE-NOT-A-REAL-SLACK-TOKEN", "xoxp***"),
        ("xapp-1-A012BCDEFGH-1234567890123-abcdefabcdefabcdefabcdef", "xapp***"),
        ("AIzaSyD-abcdefghijklmnopqrstuvwxyz01234", "AIza***"),
        ("glpat-abcdefghij0123456789", "glpa***"),
        ("npm_abcdefghij0123456789ABCDEFGHIJ01234567", "npm_***"),
        ("dop_v1_abcdefghij0123456789abcdefghij0123456789abcdefghij0123456789", "dop_***"),
        ("-----BEGIN RSA PRIVATE KEY-----", "----***"),
        ("-----BEGIN PRIVATE KEY-----", "----***"),
    ],
)
def test_every_covered_issuer_prefix_is_cut_wherever_it_appears(secret: str, cut: str) -> None:
    """Prefix matching, not entropy: each issuer's own marker is what fires.

    Each token is checked in prose (no assignment anywhere on the line), which is
    the shape ``CREDENTIAL_RE`` cannot see, so this is ``SECRET_TOKEN_RE`` doing
    the work in every case.
    """
    line = f"the verifier read {secret} out of the file"
    assert CREDENTIAL_RE.search(line) is None
    assert redact(line) == f"the verifier read {cut} out of the file"


@pytest.mark.parametrize(
    "line",
    [
        "def sk_live_handler(request):  # not a token, a function name",
        "from app.tokens import npm_registry_client",
        "AKIA is the prefix AWS uses for a long-lived access key id",
        "see https://example.test/docs/xoxb-tokens for the Slack token guide",
        "ghp_ tokens are classic personal access tokens",
        "sk_test_x",
        "the constant AIzaSy is only four characters of a real key",
        "-----BEGIN CERTIFICATE-----",
    ],
)
def test_ordinary_identifiers_and_prose_are_never_touched(line: str) -> None:
    """The prefixes are specific, but they must not fire on code or documentation.

    A prefix that appears as an identifier, in a URL path, or as prose *about*
    the prefix carries no token body of a plausible length, so nothing matches.
    A PEM certificate header is not a private key.
    """
    assert SECRET_TOKEN_RE.search(line) is None, line
    assert redact(line) == line


def test_the_two_patterns_agree_on_shape_and_compose() -> None:
    """An assignment whose value is a known token is cut once, not twice.

    ``CREDENTIAL_RE`` runs first and leaves ``sk_l***``, whose remaining body is
    too short for ``SECRET_TOKEN_RE`` to match, so the second pass is inert and
    the output is byte-identical to what phase 2 produced. This is what keeps the
    existing goldens' credential lines unchanged.
    """
    assert redact('api_key = "sk_live_51H8f2kL9mN3pQ7rS4tU6vW"') == 'api_key = "sk_l***"'
    assert redact('token: "ghp_16C7e42F292c6912E7710c838347Ae178B4a"') == 'token: "ghp_***"'
    # Two secrets on one line, one in each shape, both cut.
    both = 'api_key = "sk_live_51H8f2kL9mN3pQ7rS4tU6vW" leaked as AKIAIOSFODNN7EXAMPLE'
    assert redact(both) == 'api_key = "sk_l***" leaked as AKIA***'
