"""Statement export."""
import re
from enum import Enum

HEADER_RE = re.compile(r"^#")  # compiled once at import: not a loop cost (decoy)


class Kind(Enum):
    CARD = "card"
    BANK = "bank"


def export_statements(paths):
    lines = []
    for path in paths:
        handle = open(path)  # planted TD-36: I/O inside the loop
        for line in handle:
            lines.append(line.strip())
    return lines


def kind_labels():
    labels = []
    for kind in Kind:  # decoy: a loop over an enum has a bounded N
        labels.append(kind.value.upper())
    return labels


def format_amount(cents):
    return f"{cents / 100:.2f}"
