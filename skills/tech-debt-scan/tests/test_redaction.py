"""redaction.py: the shared credential cut used by every script that writes a quote."""
from __future__ import annotations

from redaction import CREDENTIAL_RE, redact


def test_credential_value_is_cut_to_four_characters() -> None:
    assert redact('api_key = "sk_live_51H8f2kL9mN3pQ7rS4tU6vW"') == 'api_key = "sk_l***"'
    assert redact('RUN export API_TOKEN="abcdefghijkl0123" && pip install requests') == (
        'RUN export API_TOKEN="abcd***" && pip install requests'
    )


def test_a_line_without_a_credential_is_returned_unchanged() -> None:
    line = "def refund(order_id: str) -> None:  # FIXME: the gateway retries twice"
    assert CREDENTIAL_RE.search(line) is None
    assert redact(line) == line
