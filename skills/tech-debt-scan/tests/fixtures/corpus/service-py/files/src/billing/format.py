"""Billing amount formatter."""


def format_amount(cents):
    return f"{cents / 100:.2f}"
