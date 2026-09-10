from __future__ import annotations

from typing import Any

from evidence_doc import evidence_locations, render_evidence

BODY = """### Proof

self._control is written at agentcore.py:135 and read nowhere.

### Evidence

- `better_memory/storage/agentcore.py:135-135`

```
        self._control = control_client
```

- `better_memory/storage/factory.py:82-86`

```
        control_client = boto3.client("bedrock-agentcore-control")
```

### Remediation

Delete the parameter from the bottom up.

### Acceptance criteria

- [ ] grep for _control returns no hits.
"""


def _finding(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "title": "AgentCoreBackend stores a control_client it never reads",
        "status": "approved",
        "slug": "agentcorebackend-stores-a-control-client-it-never-reads",
        "severity": "2",
        "category": "dead-code",
        "body_md": BODY,
        "line": 491,
        "family": "dead-code",
        "fingerprint": "4cba0399f66dd81c",
        "tier": "A",
        "type_id": "TD-09",
        "debt_type": "code",
        "effort": "S",
        "diff": "NEW",
    }
    base.update(over)
    return base


def _metadata(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "root": r"C:\Users\gethi\source\better-memory",
        "scan_date": "2026-09-09",
        "preset": "balanced",
    }
    base.update(over)
    return base


def test_evidence_locations_reads_every_cited_span() -> None:
    assert evidence_locations(BODY) == [
        ("better_memory/storage/agentcore.py", 135),
        ("better_memory/storage/factory.py", 82),
    ]


MIXED_SHAPES_BODY = """### Evidence

- repository-level finding (no file or line range)

- `pkg/whole.py` (whole file)

```
whole file quote
```

- `pkg/exact.py:42-50`

```
exact quote
```
"""


def test_evidence_locations_reads_all_three_citation_shapes() -> None:
    """The repository-level shape names no file, so it correctly yields no
    location. The whole-file shape names a file but no line -- ``None``, not
    ``0``, because ``0`` would read as a real anchor downstream."""
    assert evidence_locations(MIXED_SHAPES_BODY) == [
        ("pkg/whole.py", None),
        ("pkg/exact.py", 42),
    ]


def test_evidence_locations_does_not_match_a_bare_backtick_bullet() -> None:
    """A bare ``- `path` `` line -- naming neither a line span nor "(whole
    file)" -- is not one of the two citation shapes design_writer emits.
    ``body_md`` is the finding's whole rendered body, including free-form
    Proof/Remediation prose that ``free_text()`` only escapes for lines
    starting with ``#`` or a backtick fence, so a prose bullet like
    ``- `config.py` is the entry point`` must not be read as a citation."""
    assert evidence_locations("- `config.py`\n") == []
    assert evidence_locations("- `config.py` is the entry point\n") == []


WHOLE_FILE_ONLY_BODY = """### Proof

The whole module is dead code.

### Evidence

- `pkg/dead_module.py` (whole file)

```
def unused(): ...
```

### Remediation

Delete the file.

### Acceptance criteria

- [ ] grep confirms no importers.
"""


def test_render_evidence_matches_open_questions_for_a_whole_file_citation() -> None:
    """Regression: a finding whose only evidence is a whole-file citation used
    to make ``evidence_locations`` return ``[]``, which emptied ``files`` and
    silently dropped every matching open question. This is the bug."""
    questions = [
        {"file": "pkg/dead_module.py", "line_start": 10,
         "question": "Is dead_module.py referenced by a plugin loader?"},
    ]
    out = render_evidence(
        _finding(body_md=WHOLE_FILE_ONLY_BODY),
        metadata=_metadata(),
        open_questions=questions,
        looks_bad_but_fine=[],
    )
    assert "### Open questions from the scan" in out
    assert "Is dead_module.py referenced by a plugin loader?" in out


MIXED_WHOLE_THEN_LINE_BODY = """### Proof

Related evidence spans two files.

### Evidence

- `pkg/whole.py` (whole file)

```
whole file marker
```

- `pkg/exact.py:135-135`

```
exact quote
```

### Remediation

Fix it.

### Acceptance criteria

- [ ] done
"""


def test_anchor_skips_a_leading_whole_file_citation_for_proximity_ordering() -> None:
    """A whole-file citation ahead of a ``file:start-end`` one must not become
    the anchor (it has no line), so proximity ordering still works off the
    real line."""
    questions = [
        {"file": "pkg/exact.py", "line_start": 900, "question": "far"},
        {"file": "pkg/exact.py", "line_start": 140, "question": "near"},
    ]
    out = render_evidence(
        _finding(body_md=MIXED_WHOLE_THEN_LINE_BODY),
        metadata=_metadata(),
        open_questions=questions,
        looks_bad_but_fine=[],
    )
    assert out.index("near") < out.index("far")


def test_header_carries_the_scan_and_classification_facts() -> None:
    out = render_evidence(
        _finding(), metadata=_metadata(), open_questions=[], looks_bad_but_fine=[]
    )
    lines = out.split("\n")
    assert lines[0] == "# AgentCoreBackend stores a control_client it never reads"
    assert r"Repository: C:\Users\gethi\source\better-memory" in lines
    assert "Scan: 2026-09-09 (preset balanced)" in lines
    assert "Finding: 4cba0399f66dd81c | dead-code | TD-09 | code" in lines
    assert "Tier A | severity 2 | effort S | NEW" in lines


def test_body_is_copied_verbatim() -> None:
    out = render_evidence(
        _finding(), metadata=_metadata(), open_questions=[], looks_bad_but_fine=[]
    )
    assert BODY.strip("\n") in out


def test_matching_open_questions_are_rendered_by_file() -> None:
    questions = [
        {"file": "better_memory/storage/agentcore.py", "line_start": 135,
         "question": "Is control_client retained for a planned operation?"},
        {"file": "better_memory/services/reflection.py", "line_start": 12,
         "question": "Unrelated question about another file."},
    ]
    out = render_evidence(
        _finding(), metadata=_metadata(), open_questions=questions, looks_bad_but_fine=[]
    )
    assert "### Open questions from the scan" in out
    assert "Is control_client retained for a planned operation?" in out
    assert "Unrelated question about another file." not in out


def test_matched_entries_are_ordered_by_line_proximity() -> None:
    questions = [
        {"file": "better_memory/storage/agentcore.py", "line_start": 900, "question": "far"},
        {"file": "better_memory/storage/agentcore.py", "line_start": 140, "question": "near"},
    ]
    out = render_evidence(
        _finding(), metadata=_metadata(), open_questions=questions, looks_bad_but_fine=[]
    )
    assert out.index("near") < out.index("far")


def test_looks_bad_but_fine_matches_any_evidence_file() -> None:
    entries = [
        {"file": "better_memory/storage/factory.py", "line_start": 82,
         "why": "The factory builds one client per backend by design."},
    ]
    out = render_evidence(
        _finding(), metadata=_metadata(), open_questions=[], looks_bad_but_fine=entries
    )
    assert "### Already ruled out" in out
    assert "The factory builds one client per backend by design." in out


def test_unmatched_sections_are_omitted_entirely() -> None:
    out = render_evidence(
        _finding(),
        metadata=_metadata(),
        open_questions=[{"file": "other.py", "line_start": 1, "question": "q"}],
        looks_bad_but_fine=[{"file": "other.py", "line_start": 1, "why": "w"}],
    )
    assert "### Open questions from the scan" not in out
    assert "### Already ruled out" not in out


def test_output_is_lf_only_and_ends_with_one_newline() -> None:
    out = render_evidence(
        _finding(), metadata=_metadata(), open_questions=[], looks_bad_but_fine=[]
    )
    assert "\r" not in out
    assert out.endswith("\n")
    assert not out.endswith("\n\n")


def test_absent_optional_fields_render_a_dash() -> None:
    finding = _finding()
    for key in ("tier", "type_id", "debt_type", "effort", "diff", "family"):
        finding.pop(key)
    out = render_evidence(
        finding, metadata=_metadata(), open_questions=[], looks_bad_but_fine=[]
    )
    assert "Finding: 4cba0399f66dd81c | dead-code | - | -" in out
    assert "Tier - | severity 2 | effort - | -" in out
