from pathlib import Path


def test_redaction_is_byte_identical_to_tech_debt_scan():
    here = Path(__file__).resolve().parents[2]
    assert (here / "document-drift/scripts/dd_redaction.py").read_bytes() == (
        here / "tech-debt-scan/scripts/redaction.py"
    ).read_bytes()
