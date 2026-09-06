# tech-debt-scan v2 phase 4a: the probe — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `tools_probe.py` and `tool_normalisers.py` so the skill can run already-installed external tools and write `tool-signals.json`, which nothing reads yet.

**Architecture:** `tool_normalisers.py` holds ten pure functions, `normalise_<tool>(payload, root) -> list[Signal]`, with no I/O, so each is testable from a captured payload with nothing mocked. `tools_probe.py` holds the CLI, presence detection, the runner and one registry table mapping a tool to its argv builder, artefact predicate, timeout, output channel, exit table, normaliser and fact-or-inference class. The runner never installs, never invokes `npx` and never executes project code.

**Tech Stack:** Python 3.11+, standard library only plus `yaml` (already a dependency through `config.py`). `pytest` for tests. The external tools are subprocesses, never imports.

**Spec:** `docs/superpowers/specs/2026-09-04-tech-debt-scan-v2-design.md` — sections 4.5 (this phase's contract), 3.3 (conventions), 11 (phase 4a scope and gate). Read 4.5 in full before Task 1.

## Global Constraints

- Python 3.11+; standard library only in the skill's scripts, plus `yaml`. No new dependencies.
- Flat sibling imports (spec 0(d)): `from config import load_config`, `from inventory import write_json`, `from redaction import redact`. No package-relative imports.
- `ruff`, `mypy`, `python skills/tech-debt-scan/scripts/skill_check.py` and `python -m pytest -q` all green before every commit. The suite baseline entering this plan is 785 passed, 2 skipped, 1 deselected.
- Goldens are byte-compared and written LF-only through `inventory.write_json`. Regeneration under `UPDATE_GOLDENS=1` must be idempotent.
- The only language-aware code in the skill is the inventory's extension map and this phase's normalisers (spec 0(d)). A language name branched on anywhere else is a defect, and a cross-cutting test already asserts it.
- Never install a tool, never invoke `npx`, never execute project code. Presence is `shutil.which`, then `<root>/node_modules/.bin` for jscpd, knip and madge only.
- No tool output field that can carry source text or a credential reaches `tool-signals.json`. Named instances: gitleaks `Secret` and `Match`, jscpd `fragment`. This is a spec 4.5 rule, not a preference.
- Commit messages end with the line `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Confidence floor for this plan is 92%. Every task states its confidence and embeds its own mitigation.

---

## Guardrails from prior sessions

These are retrieved reflections with their confidence, surfaced here because they bind this plan rather than because they are generally true.

- **Read the argparse setup, never an existing example, when documenting a command** (0.95, evidence 7). Task 9 documents `tools_probe.py`; its flags come from the argparse block written in Task 8, verified by running `--help`, not from this plan's prose.
- **Verify a RED step is genuinely RED** (0.75, evidence 2). Several tasks here add a normaliser whose absence raises `NotImplementedError` from Task 1's registry. That exception can satisfy a `pytest.raises` written carelessly, so every RED assertion in this plan asserts on a returned value, never merely that something raised.
- **Keep docs in sync in the same change** (0.95, evidence 7). Task 9 is a docs task, but a module docstring belongs to the task that changes the module, not to Task 9.
- Dismissed as not applicable: the TypeScript `Partial<T>` reflection (no TypeScript in this plan), the `tempfile.mkstemp` fd-leak reflection (no temp files are opened by this plan; jscpd's report directory is created and removed with `tempfile.TemporaryDirectory`, which does not use the `mkstemp` idiom), the ralph-queue reflection (no queue involved).

---

## Assumptions surfaced

### Real concerns

**1. Four normalisers are written against payloads nobody has run.** gitleaks, osv-scanner, hadolint and actionlint are not installed and cannot be. Their canned payloads come from each tool's documented schema, so a normaliser can pass every test and still misread the real tool — which is exactly what happened to the other five before they were installed: four of five documented assumptions were wrong.

*Mitigation, embedded in Tasks 6 and 7:* every canned payload is committed with a provenance comment naming the tool version and schema source it was written from, so a later correction starts from a known claim rather than a guess. The registry isolates each normaliser to one pure function, so correcting one is a single-function change with its own test. Task 9 records the four as unvalidated in `docs/architecture.md`, so the limitation is visible outside this plan.

**2. jscpd's real output channel is a file it creates.** The runner must support a tool whose result is not on stdout, must ignore that tool's stdout entirely, and must clean up the directory it made. This is the only tool of the ten shaped this way, so the abstraction is being designed from a single example.

*Mitigation, embedded in Task 2:* the output channel is a registry field with two values, `stdout` and `report_file`, and the runner is tested for both against fake tools before any real normaliser exists. If a later tool needs a third channel it is a registry value, not a rewrite.

**3. The corpus cannot exercise every normaliser.** service-py has no Dockerfile, web-ts has no lockfile osv-scanner would read, no fixture has a secret gitleaks would find. So the fixture-level goldens in Task 8 cover the tools that fire on the corpus and the per-normaliser tests carry everything else.

*Mitigation, embedded in Task 8:* the golden asserts each non-firing tool's `status` and `reason` explicitly, so "produced nothing" is distinguished from "never ran", which is the failure this phase most needs to catch.

### Verified safe

- `apply_verdicts.family_cap` already lifts the tier cap when `confirmed_by` carries a `tool:` token, for duplication, dead-code, architecture, test-quality, dependency-debt and security. Read this session at `apply_verdicts.py:58`. Nothing in 4a touches it, and 4b needs no new cap logic.
- `inventory.write_json` writes LF-only through `write_bytes`, so a golden written by this phase cannot pick up CRLF on Windows. Read at `inventory.py:719`.
- `config.py` already carries the `tools` block with `allow`, `deny`, `network` and `timeout_s` defaults. Read at `config.py:80`. Task 2 consumes it; no config schema change is needed.
- `redaction.redact` and `SECRET_TOKEN_RE` landed in phase 3 and are importable flat. Signals pass through `redact` at write time in Task 8.
- All five installable tools are installed and were run against the corpus this session: ruff 0.x, lizard 1.24.0, vulture 2.16, madge 8.0.0, jscpd 5.1.2, knip. Every payload embedded in Tasks 3 to 5 is real captured output, not invented.

### Minor or accepted

- `tool-signals.json` is written and nothing reads it until 4b, exactly as phase 2 shipped `ranked.json` before phase 3 rendered it.
- The `version` field is recorded per tool but never asserted by a golden, because a tool update would break the test for the wrong reason.
- lizard reports every function, not only complex ones; the normaliser applies a threshold so the signal list stays bounded.
- knip on a project without `node_modules` reports whole unused files rather than unused exports. Both shapes are handled; only the first is exercised by the corpus.
- osv-scanner's `--offline` path and its no-database skip are implemented and unit-tested but never executed against a real database.

---

## File structure

| File | Responsibility |
|---|---|
| `skills/tech-debt-scan/scripts/tool_normalisers.py` | Create. The `Signal` shape, the path relativiser, and ten pure `normalise_<tool>` functions. No I/O, no subprocess, no config. |
| `skills/tech-debt-scan/scripts/tools_probe.py` | Create. CLI, presence detection, the registry, the runner, and the `tool-signals.json` writer. |
| `skills/tech-debt-scan/tests/test_tool_normalisers.py` | Create. One class per normaliser, driven by committed payloads. |
| `skills/tech-debt-scan/tests/test_tools_probe.py` | Create. Presence, the runner's four statuses, both output channels, the deny list, `--skip-all`, the CLI. |
| `skills/tech-debt-scan/tests/fixtures/tool-output/` | Create. Captured and canned payloads, one file per tool. |
| `skills/tech-debt-scan/tests/golden/<fixture>/tool-signals.json` | Create in Task 8, one per corpus fixture. |
| `docs/architecture.md`, `README.md` | Modify in Task 9. |

---

## Task 1: The Signal shape, the relativiser and presence detection

**Confidence: 96%.** Two small pure functions and a table. The only subtlety is that ruff's absolute path must survive a relativiser whose sibling in `merge_findings` rejects absolute paths outright, and Step 1 pins that difference.

**Files:**
- Create: `skills/tech-debt-scan/scripts/tool_normalisers.py`
- Create: `skills/tech-debt-scan/scripts/tools_probe.py`
- Create: `skills/tech-debt-scan/tests/test_tool_normalisers.py`
- Create: `skills/tech-debt-scan/tests/test_tools_probe.py`

**Interfaces:**
- Consumes: `merge_findings._normalise_path` (for the agreement test only, never at runtime).
- Produces: `tool_normalisers.Signal`, `tool_normalisers.rel_path(root: Path, raw: str) -> str | None`, `tools_probe.TOOLS: dict[str, ToolSpec]`, `tools_probe.ToolSpec`, `tools_probe.find_tool(name: str, root: Path) -> str | None`.

- [ ] **Step 1: Write the failing tests for the relativiser**

Create `skills/tech-debt-scan/tests/test_tool_normalisers.py`:

```python
"""Tests for the pure tool-output normalisers (spec 4.5)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


class TestRelPath:
    def test_absolute_windows_path_under_root_is_relativised(self) -> None:
        from tool_normalisers import rel_path

        root = Path("C:/repo")
        raw = "C:\\repo\\src\\pay\\refund.py"
        assert rel_path(root, raw) == "src/pay/refund.py"

    def test_relative_path_is_forward_slashed(self) -> None:
        from tool_normalisers import rel_path

        assert rel_path(Path("C:/repo"), "src\\pay\\refund.py") == "src/pay/refund.py"

    def test_leading_dot_slash_is_stripped(self) -> None:
        from tool_normalisers import rel_path

        assert rel_path(Path("C:/repo"), "./src/a.py") == "src/a.py"

    def test_path_outside_root_is_rejected(self) -> None:
        from tool_normalisers import rel_path

        assert rel_path(Path("C:/repo"), "C:\\elsewhere\\a.py") is None

    def test_parent_traversal_is_rejected(self) -> None:
        from tool_normalisers import rel_path

        assert rel_path(Path("C:/repo"), "../outside.py") is None

    def test_empty_and_non_string_are_rejected(self) -> None:
        from tool_normalisers import rel_path

        assert rel_path(Path("C:/repo"), "   ") is None
        assert rel_path(Path("C:/repo"), None) is None  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "raw", ["src/a.py", "src\\a.py", "./src/a.py", "../outside.py", "  ", "/abs/a.py"]
    )
    def test_agrees_with_merge_findings_on_relative_inputs(self, raw: str) -> None:
        """The probe has its own relativiser; on inputs merge_findings accepts they agree.

        merge_findings._normalise_path rejects absolute paths outright because a
        scout must never cite one. The probe must accept an absolute path a tool
        emitted and turn it into a relative one, so the two differ deliberately on
        exactly that input class and nowhere else.
        """
        from merge_findings import _normalise_path
        from tool_normalisers import rel_path

        assert rel_path(Path("C:/repo"), raw) == _normalise_path(raw)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_tool_normalisers.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'tool_normalisers'`.

- [ ] **Step 3: Write `tool_normalisers.py` with the Signal shape and the relativiser**

Create `skills/tech-debt-scan/scripts/tool_normalisers.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest skills/tech-debt-scan/tests/test_tool_normalisers.py -q`
Expected: PASS, 7 tests.

- [ ] **Step 5: Write the failing tests for presence detection**

Create `skills/tech-debt-scan/tests/test_tools_probe.py`:

```python
"""Tests for the external-tool probe (spec 4.5)."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


class TestRegistry:
    def test_every_first_cut_tool_is_registered(self) -> None:
        from tools_probe import TOOLS

        assert set(TOOLS) == {
            "osv-scanner", "gitleaks", "ruff", "vulture", "lizard",
            "jscpd", "knip", "madge", "hadolint", "actionlint",
        }

    def test_fact_class_is_exactly_the_four_spec_names(self) -> None:
        from tools_probe import TOOLS

        facts = {name for name, spec in TOOLS.items() if spec.fact}
        assert facts == {"osv-scanner", "gitleaks", "hadolint", "actionlint"}

    def test_only_node_tools_look_in_node_modules(self) -> None:
        from tools_probe import TOOLS

        node = {name for name, spec in TOOLS.items() if spec.node_bin}
        assert node == {"jscpd", "knip", "madge"}


class TestFindTool:
    def test_found_on_path(self, tmp_path: Path, monkeypatch) -> None:
        import tools_probe

        monkeypatch.setattr(tools_probe.shutil, "which", lambda name: "C:/bin/ruff.exe")
        assert tools_probe.find_tool("ruff", tmp_path) == "C:/bin/ruff.exe"

    def test_absent_returns_none(self, tmp_path: Path, monkeypatch) -> None:
        import tools_probe

        monkeypatch.setattr(tools_probe.shutil, "which", lambda name: None)
        assert tools_probe.find_tool("ruff", tmp_path) is None

    def test_node_tool_found_in_node_modules_bin(self, tmp_path: Path, monkeypatch) -> None:
        import tools_probe

        monkeypatch.setattr(tools_probe.shutil, "which", lambda name: None)
        binary = tmp_path / "node_modules" / ".bin" / "madge.cmd"
        binary.parent.mkdir(parents=True)
        binary.write_text("", encoding="utf-8")
        assert tools_probe.find_tool("madge", tmp_path) == str(binary)

    def test_non_node_tool_ignores_node_modules_bin(self, tmp_path: Path, monkeypatch) -> None:
        import tools_probe

        monkeypatch.setattr(tools_probe.shutil, "which", lambda name: None)
        binary = tmp_path / "node_modules" / ".bin" / "ruff.cmd"
        binary.parent.mkdir(parents=True)
        binary.write_text("", encoding="utf-8")
        assert tools_probe.find_tool("ruff", tmp_path) is None

    def test_npx_is_never_referenced_anywhere_in_the_probe(self) -> None:
        """Spec 4.5 forbids npx outright: it would install a package to run it."""
        source = (SCRIPTS / "tools_probe.py").read_text(encoding="utf-8")
        assert "npx" not in source
```

- [ ] **Step 6: Run the tests to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_tools_probe.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'tools_probe'`.

- [ ] **Step 7: Write `tools_probe.py` with the registry and presence detection**

Create `skills/tech-debt-scan/scripts/tools_probe.py`:

```python
"""Run already-installed external tools and write ``tool-signals.json`` (spec 4.5).

Never installs anything, never invokes ``npx`` and never executes project
code. Presence is ``shutil.which``, then ``<root>/node_modules/.bin`` for the
three Node tools only. Each present tool runs under a per-tool timeout and is
recorded as ``ran``, ``absent``, ``failed`` or ``skipped``.

The registry is the whole contract: one row per tool giving how to invoke it,
when it is worth invoking, where its output appears, which exit codes mean
what, which normaliser reads it, and whether its signals are fact-class.
Adding a tool is a row plus a pure function in ``tool_normalisers.py``.

Nothing reads ``tool-signals.json`` until phase 4b.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Final

from tool_normalisers import Signal

# A normaliser takes a parsed payload and the repo root and returns signals.
Normaliser = Callable[[Any, Path], list[Signal]]

NODE_TOOLS: Final[frozenset[str]] = frozenset({"jscpd", "knip", "madge"})


@dataclass(frozen=True)
class ToolSpec:
    """One registry row: everything the runner needs to know about a tool."""

    name: str
    family: str
    fact: bool
    channel: str  # "stdout" or "report_file"
    parse: str  # "json", "csv" or "lines"
    findings_exit: tuple[int, ...]  # exit codes that mean "ran, found things"
    timeout_s: int | None = None  # None means the config default
    node_bin: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


TOOLS: Final[dict[str, ToolSpec]] = {
    "osv-scanner": ToolSpec("osv-scanner", "dependency-debt", True, "stdout", "json", (1,), 300),
    "gitleaks": ToolSpec("gitleaks", "security", True, "stdout", "json", (1,)),
    "hadolint": ToolSpec("hadolint", "pipeline-infra", True, "stdout", "json", (1,)),
    "actionlint": ToolSpec("actionlint", "pipeline-infra", True, "stdout", "json", (1,)),
    "ruff": ToolSpec("ruff", "error-handling", False, "stdout", "json", (1,)),
    "vulture": ToolSpec("vulture", "dead-code", False, "stdout", "lines", (3,)),
    "lizard": ToolSpec("lizard", "complexity", False, "stdout", "csv", ()),
    "jscpd": ToolSpec("jscpd", "duplication", False, "report_file", "json", (), None, True),
    "knip": ToolSpec("knip", "dead-code", False, "stdout", "json", (1,), None, True),
    "madge": ToolSpec("madge", "architecture", False, "stdout", "json", (1,), None, True),
}


def find_tool(name: str, root: Path) -> str | None:
    """The executable for ``name``, or None when it is not installed.

    ``shutil.which`` first, then ``<root>/node_modules/.bin`` for the three
    Node tools. A project-local binary is a tool the repository already
    depends on; ``npx`` would fetch one, which spec 4.5 forbids.
    """
    found = shutil.which(name)
    if found:
        return found
    if name not in NODE_TOOLS:
        return None
    bin_dir = root / "node_modules" / ".bin"
    for suffix in ("", ".cmd", ".exe", ".ps1"):
        candidate = bin_dir / f"{name}{suffix}"
        if candidate.is_file():
            return str(candidate)
    return None
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `python -m pytest skills/tech-debt-scan/tests/test_tools_probe.py skills/tech-debt-scan/tests/test_tool_normalisers.py -q`
Expected: PASS, 14 tests.

- [ ] **Step 9: Run the gate and commit**

```bash
python -m ruff check .
python -m mypy
python skills/tech-debt-scan/scripts/skill_check.py
python -m pytest -q
git add skills/tech-debt-scan/scripts/tool_normalisers.py skills/tech-debt-scan/scripts/tools_probe.py skills/tech-debt-scan/tests/test_tool_normalisers.py skills/tech-debt-scan/tests/test_tools_probe.py
git commit -m "$(cat <<'EOF'
feat(tech-debt-scan): the tool registry, the Signal shape and presence detection

Presence is shutil.which, then node_modules/.bin for jscpd, knip and madge
only; a test greps the module to prove npx appears nowhere in it. The
probe's relativiser differs from merge_findings' on exactly one input
class -- an absolute path, which a tool may emit and a scout may not -- and
a parametrised test pins that they agree everywhere else.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: The runner — four statuses, two output channels

**Confidence: 93%.** The runner is the one place a subprocess is spawned, and it must behave correctly for a tool nobody has installed. Every test here drives a fake tool written as a Python script, so the runner is proven without depending on any real tool being present.

**Files:**
- Modify: `skills/tech-debt-scan/scripts/tools_probe.py`
- Modify: `skills/tech-debt-scan/tests/test_tools_probe.py`

**Interfaces:**
- Consumes: `tools_probe.TOOLS`, `tools_probe.ToolSpec`, `tools_probe.find_tool` (Task 1); `config.load_config`.
- Produces: `tools_probe.ToolResult`, `tools_probe.run_tool(spec, executable, argv, root, timeout_s) -> ToolResult`, `tools_probe.STDERR_CHARS = 200`.

- [ ] **Step 1: Write the failing tests for the runner**

Append to `skills/tech-debt-scan/tests/test_tools_probe.py`:

```python
import json
import textwrap


def _fake_tool(tmp_path: Path, body: str) -> tuple[str, list[str]]:
    """A Python script standing in for an external tool; returns (exe, argv)."""
    script = tmp_path / "fake_tool.py"
    script.write_text(textwrap.dedent(body), encoding="utf-8")
    return sys.executable, [sys.executable, str(script)]


class TestRunTool:
    def test_exit_zero_with_valid_json_is_ran(self, tmp_path: Path) -> None:
        from tools_probe import TOOLS, run_tool

        exe, argv = _fake_tool(tmp_path, """
            import json, sys
            print(json.dumps([{"ok": True}]))
            sys.exit(0)
        """)
        result = run_tool(TOOLS["ruff"], exe, argv, tmp_path, 30)
        assert result.status == "ran"
        assert result.payload == [{"ok": True}]

    def test_findings_exit_with_valid_json_is_ran(self, tmp_path: Path) -> None:
        """Exit 1 is ruff's "found something", not a failure."""
        from tools_probe import TOOLS, run_tool

        exe, argv = _fake_tool(tmp_path, """
            import json, sys
            print(json.dumps([{"code": "BLE001"}]))
            sys.exit(1)
        """)
        result = run_tool(TOOLS["ruff"], exe, argv, tmp_path, 30)
        assert result.status == "ran"

    def test_vulture_exit_three_is_ran_not_failed(self, tmp_path: Path) -> None:
        """vulture exits 3 when it finds something; an exit table assuming 1
        would mark every productive run a failure (spec 4.5)."""
        from tools_probe import TOOLS, run_tool

        exe, argv = _fake_tool(tmp_path, """
            import sys
            print("a.py:1: unused function 'f' (60% confidence)")
            sys.exit(3)
        """)
        result = run_tool(TOOLS["vulture"], exe, argv, tmp_path, 30)
        assert result.status == "ran"
        assert result.payload == ["a.py:1: unused function 'f' (60% confidence)"]

    def test_unparseable_json_is_failed_with_truncated_stderr(self, tmp_path: Path) -> None:
        from tools_probe import STDERR_CHARS, TOOLS, run_tool

        exe, argv = _fake_tool(tmp_path, """
            import sys
            print("not json at all")
            sys.stderr.write("E" * 500)
            sys.exit(1)
        """)
        result = run_tool(TOOLS["ruff"], exe, argv, tmp_path, 30)
        assert result.status == "failed"
        assert len(result.reason) <= STDERR_CHARS
        assert result.reason.startswith("EEE")

    def test_unexpected_exit_code_is_failed(self, tmp_path: Path) -> None:
        from tools_probe import TOOLS, run_tool

        exe, argv = _fake_tool(tmp_path, """
            import json, sys
            print(json.dumps([]))
            sys.exit(42)
        """)
        result = run_tool(TOOLS["ruff"], exe, argv, tmp_path, 30)
        assert result.status == "failed"
        assert "42" in result.reason

    def test_timeout_is_failed_and_names_the_limit(self, tmp_path: Path) -> None:
        from tools_probe import TOOLS, run_tool

        exe, argv = _fake_tool(tmp_path, """
            import time
            time.sleep(30)
        """)
        result = run_tool(TOOLS["ruff"], exe, argv, tmp_path, 1)
        assert result.status == "failed"
        assert "timed out" in result.reason
        assert "1" in result.reason

    def test_report_file_channel_reads_the_file_and_ignores_stdout(self, tmp_path: Path) -> None:
        """jscpd writes its report to a file and fills stdout with promotional
        text; the runner must read the file and ignore stdout (spec 4.5)."""
        from tools_probe import TOOLS, run_tool

        exe, argv = _fake_tool(tmp_path, """
            import json, os, sys
            print("Support jscpd project -> https://opencollective.com/jscpd")
            out = sys.argv[1]
            os.makedirs(out, exist_ok=True)
            with open(os.path.join(out, "jscpd-report.json"), "w", encoding="utf-8") as fh:
                json.dump({"duplicates": [{"lines": 8}]}, fh)
            sys.exit(0)
        """)
        result = run_tool(TOOLS["jscpd"], exe, argv, tmp_path, 30)
        assert result.status == "ran"
        assert result.payload == {"duplicates": [{"lines": 8}]}

    def test_report_file_absent_is_failed(self, tmp_path: Path) -> None:
        from tools_probe import TOOLS, run_tool

        exe, argv = _fake_tool(tmp_path, """
            import sys
            print("wrote nothing")
            sys.exit(0)
        """)
        result = run_tool(TOOLS["jscpd"], exe, argv, tmp_path, 30)
        assert result.status == "failed"
        assert "report" in result.reason

    def test_report_directory_is_removed_after_the_run(self, tmp_path: Path) -> None:
        from tools_probe import TOOLS, run_tool

        exe, argv = _fake_tool(tmp_path, """
            import json, os, sys
            out = sys.argv[1]
            os.makedirs(out, exist_ok=True)
            with open(os.path.join(out, "jscpd-report.json"), "w", encoding="utf-8") as fh:
                json.dump({"duplicates": []}, fh)
        """)
        before = set(tmp_path.iterdir())
        run_tool(TOOLS["jscpd"], exe, argv, tmp_path, 30)
        assert set(tmp_path.iterdir()) == before

    def test_missing_executable_is_failed_not_an_exception(self, tmp_path: Path) -> None:
        from tools_probe import TOOLS, run_tool

        result = run_tool(TOOLS["ruff"], "no-such-exe", ["no-such-exe"], tmp_path, 5)
        assert result.status == "failed"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_tools_probe.py -q -k RunTool`
Expected: FAIL, `ImportError: cannot import name 'run_tool' from 'tools_probe'`.

- [ ] **Step 3: Write the runner**

Append to `skills/tech-debt-scan/scripts/tools_probe.py`:

```python
import csv
import json
import subprocess
import tempfile
import time
from dataclasses import dataclass as _dataclass

STDERR_CHARS: Final[int] = 200
REPORT_FILENAME: Final[str] = "jscpd-report.json"


@_dataclass(frozen=True)
class ToolResult:
    """What one attempted tool run produced."""

    status: str  # "ran", "absent", "failed" or "skipped"
    payload: Any = None
    reason: str = ""
    duration_s: float = 0.0


def _parse(spec: ToolSpec, text: str) -> Any:
    """The tool's raw output as its declared shape, or ValueError."""
    if spec.parse == "json":
        return json.loads(text)
    if spec.parse == "lines":
        return [line for line in text.splitlines() if line.strip()]
    if spec.parse == "csv":
        return [row for row in csv.reader(text.splitlines()) if row]
    raise ValueError(f"unknown parse mode {spec.parse!r}")


def run_tool(
    spec: ToolSpec, executable: str, argv: list[str], root: Path, timeout_s: int
) -> ToolResult:
    """Run one tool and classify the attempt.

    ``ran`` means the process exited with a code the spec's table allows and
    its output parsed. Anything else is ``failed``, carrying the first
    ``STDERR_CHARS`` characters of stderr, because unparseable output is the
    failure signal for every tool in the first cut.

    A ``report_file`` tool writes its result into a directory this function
    creates and removes; its stdout is progress and promotional text and is
    never parsed.
    """
    started = time.monotonic()
    report_dir: tempfile.TemporaryDirectory[str] | None = None
    full_argv = list(argv)
    if spec.channel == "report_file":
        report_dir = tempfile.TemporaryDirectory(dir=root)
        full_argv.append(report_dir.name)
    try:
        try:
            completed = subprocess.run(  # noqa: S603 - argv is built from the registry
                full_argv,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_s,
                cwd=root,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ToolResult("failed", reason=f"timed out after {timeout_s}s",
                              duration_s=time.monotonic() - started)
        except OSError as exc:
            return ToolResult("failed", reason=str(exc)[:STDERR_CHARS],
                              duration_s=time.monotonic() - started)

        duration = time.monotonic() - started
        stderr = (completed.stderr or "").strip()[:STDERR_CHARS]
        if completed.returncode != 0 and completed.returncode not in spec.findings_exit:
            reason = stderr or f"exit {completed.returncode}"
            if str(completed.returncode) not in reason:
                reason = f"exit {completed.returncode}: {reason}"
            return ToolResult("failed", reason=reason[:STDERR_CHARS], duration_s=duration)

        if spec.channel == "report_file":
            assert report_dir is not None
            report = Path(report_dir.name) / REPORT_FILENAME
            if not report.is_file():
                return ToolResult("failed", reason=f"no {REPORT_FILENAME} report written",
                                  duration_s=duration)
            raw = report.read_text(encoding="utf-8", errors="replace")
        else:
            raw = completed.stdout or ""

        try:
            payload = _parse(spec, raw)
        except (ValueError, csv.Error):
            return ToolResult("failed", reason=stderr or "unparseable output",
                              duration_s=duration)
        return ToolResult("ran", payload=payload, duration_s=duration)
    finally:
        if report_dir is not None:
            report_dir.cleanup()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest skills/tech-debt-scan/tests/test_tools_probe.py -q`
Expected: PASS, all `TestRunTool` cases green.

- [ ] **Step 5: Run the gate and commit**

```bash
python -m ruff check .
python -m mypy
python -m pytest -q
git add skills/tech-debt-scan/scripts/tools_probe.py skills/tech-debt-scan/tests/test_tools_probe.py
git commit -m "$(cat <<'EOF'
feat(tech-debt-scan): the tool runner, its four statuses and both output channels

Every test drives a Python script standing in for an external tool, so the
runner is proven with nothing installed. Three real behaviours are pinned:
vulture's exit 3 is a productive run and not a failure, an unexpected exit
code and unparseable output are both failures carrying 200 characters of
stderr, and a report-file tool has its stdout ignored entirely while its
report directory is created and removed.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: The Python normalisers — ruff and vulture

**Confidence: 96%.** Both payloads are real output captured this session. ruff's is JSON with an absolute backslashed filename; vulture's is plain text with a documented line grammar.

**Files:**
- Modify: `skills/tech-debt-scan/scripts/tool_normalisers.py`
- Modify: `skills/tech-debt-scan/tests/test_tool_normalisers.py`
- Create: `skills/tech-debt-scan/tests/fixtures/tool-output/ruff.json`
- Create: `skills/tech-debt-scan/tests/fixtures/tool-output/vulture.txt`

**Interfaces:**
- Consumes: `tool_normalisers.rel_path`, `tool_normalisers.signal` (Task 1).
- Produces: `normalise_ruff(payload, root) -> list[Signal]`, `normalise_vulture(payload, root) -> list[Signal]`, `RUFF_KINDS: dict[str, tuple[str, str]]`.

- [ ] **Step 1: Commit the captured payloads**

Create `skills/tech-debt-scan/tests/fixtures/tool-output/ruff.json` — real `ruff check --isolated --output-format json` output, captured 2026-09-06 against the service-py fixture:

```json
[
  {
    "cell": null,
    "code": "BLE001",
    "end_location": {"column": 21, "row": 33},
    "filename": "C:\\repo\\src\\pay\\refund.py",
    "fix": null,
    "location": {"column": 12, "row": 33},
    "message": "Do not catch blind exception: `Exception`",
    "noqa_row": 33,
    "url": "https://docs.astral.sh/ruff/rules/blind-except"
  },
  {
    "cell": null,
    "code": "C901",
    "end_location": {"column": 5, "row": 60},
    "filename": "C:\\repo\\src\\pay\\refund.py",
    "fix": null,
    "location": {"column": 5, "row": 41},
    "message": "`issue_partial` is too complex (13 > 10)",
    "noqa_row": 41,
    "url": "https://docs.astral.sh/ruff/rules/complex-structure"
  },
  {
    "cell": null,
    "code": "F401",
    "end_location": {"column": 18, "row": 3},
    "filename": "C:\\repo\\src\\pay\\utils.py",
    "fix": null,
    "location": {"column": 1, "row": 3},
    "message": "`os.path` imported but unused",
    "noqa_row": 3,
    "url": "https://docs.astral.sh/ruff/rules/unused-import"
  },
  {
    "cell": null,
    "code": "E722",
    "end_location": {"column": 12, "row": 22},
    "filename": "C:\\repo\\src\\pay\\ledger.py",
    "fix": null,
    "location": {"column": 5, "row": 22},
    "message": "Do not use bare `except`",
    "noqa_row": 22,
    "url": "https://docs.astral.sh/ruff/rules/bare-except"
  }
]
```

Create `skills/tech-debt-scan/tests/fixtures/tool-output/vulture.txt` — real `vulture` output, captured 2026-09-06 against the service-py fixture, exit code 3:

```
src\pay\legacy_export.py:8: unused function 'export_v1' (60% confidence)
src\pay\refund.py:45: unused function 'issue_partial' (60% confidence)
src\pay\utils.py:11: unused function 'fingerprint' (60% confidence)
tests\fixtures\seed.py:4: unused variable 'SEED_A' (60% confidence)
src\pay\models.py:17: unused attribute 'legacy_id' (100% confidence)
```

- [ ] **Step 2: Write the failing tests**

Append to `skills/tech-debt-scan/tests/test_tool_normalisers.py`:

```python
import json

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "tool-output"
ROOT = Path("C:/repo")


class TestNormaliseRuff:
    def _signals(self) -> list:
        from tool_normalisers import normalise_ruff

        payload = json.loads((FIXTURES / "ruff.json").read_text(encoding="utf-8"))
        return normalise_ruff(payload, ROOT)

    def test_absolute_backslashed_filename_becomes_relative(self) -> None:
        assert {s["file"] for s in self._signals()} == {
            "src/pay/refund.py", "src/pay/utils.py", "src/pay/ledger.py",
        }

    def test_blind_except_is_error_masking(self) -> None:
        blind = next(s for s in self._signals() if s["extra"]["code"] == "BLE001")
        assert blind["kind"] == "error-masking"
        assert blind["family"] == "error-handling"
        assert blind["line_start"] == 33
        assert blind["line_end"] == 33

    def test_complexity_rule_spans_its_whole_range(self) -> None:
        complex_unit = next(s for s in self._signals() if s["extra"]["code"] == "C901")
        assert complex_unit["kind"] == "complexity"
        assert (complex_unit["line_start"], complex_unit["line_end"]) == (41, 60)

    def test_unused_import_is_dead_code(self) -> None:
        unused = next(s for s in self._signals() if s["extra"]["code"] == "F401")
        assert (unused["kind"], unused["family"]) == ("unused", "dead-code")

    def test_every_ruff_signal_is_inference_class(self) -> None:
        assert all(s["fact"] is False for s in self._signals())

    def test_unmapped_rule_codes_are_dropped(self) -> None:
        from tool_normalisers import normalise_ruff

        payload = [{
            "code": "W291", "filename": "C:\\repo\\a.py",
            "location": {"row": 1, "column": 1}, "end_location": {"row": 1, "column": 2},
            "message": "trailing whitespace",
        }]
        assert normalise_ruff(payload, ROOT) == []

    def test_a_malformed_record_is_skipped_not_fatal(self) -> None:
        from tool_normalisers import normalise_ruff

        payload = [{"code": "E722"}, {"code": "E722", "filename": "C:\\repo\\a.py",
                                      "location": {"row": 2, "column": 1},
                                      "end_location": {"row": 2, "column": 3},
                                      "message": "Do not use bare `except`"}]
        assert len(normalise_ruff(payload, ROOT)) == 1


class TestNormaliseVulture:
    def _signals(self) -> list:
        from tool_normalisers import normalise_vulture

        lines = (FIXTURES / "vulture.txt").read_text(encoding="utf-8").splitlines()
        return normalise_vulture([line for line in lines if line.strip()], ROOT)

    def test_each_line_becomes_one_dead_code_signal(self) -> None:
        signals = self._signals()
        assert len(signals) == 5
        assert {s["family"] for s in signals} == {"dead-code"}
        assert {s["kind"] for s in signals} == {"unused"}

    def test_backslashed_path_and_line_are_parsed(self) -> None:
        first = self._signals()[0]
        assert first["file"] == "src/pay/legacy_export.py"
        assert first["line_start"] == 8 and first["line_end"] == 8

    def test_confidence_and_symbol_kind_are_carried_in_extra(self) -> None:
        first = self._signals()[0]
        assert first["extra"] == {"confidence": 60, "symbol_kind": "function",
                                  "symbol": "export_v1"}

    def test_high_confidence_attribute_is_kept(self) -> None:
        attribute = next(s for s in self._signals() if s["extra"]["symbol_kind"] == "attribute")
        assert attribute["extra"]["confidence"] == 100

    def test_a_line_that_does_not_match_the_grammar_is_dropped(self) -> None:
        from tool_normalisers import normalise_vulture

        assert normalise_vulture(["*** not a finding ***"], ROOT) == []

    def test_every_vulture_signal_is_inference_class(self) -> None:
        assert all(s["fact"] is False for s in self._signals())
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_tool_normalisers.py -q -k "Ruff or Vulture"`
Expected: FAIL, `ImportError: cannot import name 'normalise_ruff'`. Confirm the failure names the missing function and is not an assertion about a raised exception.

- [ ] **Step 4: Write the two normalisers**

Append to `skills/tech-debt-scan/scripts/tool_normalisers.py`:

```python
import re

# ruff rule code -> (family, kind). Codes outside this map are not debt
# signals for our purposes and are dropped rather than guessed at.
RUFF_KINDS: Final[dict[str, tuple[str, str]]] = {
    "E722": ("error-handling", "error-masking"),
    "BLE001": ("error-handling", "error-masking"),
    "S110": ("error-handling", "error-masking"),
    "S112": ("error-handling", "error-masking"),
    "C901": ("complexity", "complexity"),
    "PLR0911": ("complexity", "complexity"),
    "PLR0912": ("complexity", "complexity"),
    "PLR0913": ("complexity", "complexity"),
    "PLR0915": ("complexity", "complexity"),
    "F401": ("dead-code", "unused"),
    "UP035": ("dependency-debt", "deprecated"),
}

_VULTURE_LINE: Final[re.Pattern[str]] = re.compile(
    r"^(?P<file>.+?):(?P<line>\d+): unused (?P<kind>\w+) '(?P<symbol>[^']+)' "
    r"\((?P<confidence>\d+)% confidence\)$"
)


def normalise_ruff(payload: Any, root: Path) -> list[Signal]:
    """ruff's JSON diagnostics as signals.

    ruff reports ``filename`` as an absolute path with backslashes even when
    given a relative one, so every record goes through ``rel_path``. Rule
    codes outside ``RUFF_KINDS`` are dropped: ruff reports far more than debt.
    """
    if not isinstance(payload, list):
        return []
    out: list[Signal] = []
    for record in payload:
        if not isinstance(record, dict):
            continue
        mapping = RUFF_KINDS.get(str(record.get("code")))
        if mapping is None:
            continue
        family, kind = mapping
        rel = rel_path(root, record.get("filename"))
        location = record.get("location") or {}
        end = record.get("end_location") or {}
        start_row, end_row = location.get("row"), end.get("row")
        if rel is None or not isinstance(start_row, int):
            continue
        out.append(
            signal(
                "ruff", family, kind,
                file=rel,
                line_start=start_row,
                line_end=end_row if isinstance(end_row, int) else start_row,
                message=str(record.get("message", "")),
                fact=False,
                extra={"code": str(record["code"])},
            )
        )
    return out


def normalise_vulture(payload: Any, root: Path) -> list[Signal]:
    """vulture's plain-text lines as dead-code signals.

    vulture has no JSON mode. Each finding is one line of the form
    ``path:line: unused <kind> '<symbol>' (<n>% confidence)``; a line that
    does not match is dropped rather than guessed at. The confidence is
    carried through as a number so 4b can weight a 60% hint below a 100% one.
    """
    if not isinstance(payload, list):
        return []
    out: list[Signal] = []
    for line in payload:
        if not isinstance(line, str):
            continue
        match = _VULTURE_LINE.match(line.strip())
        if match is None:
            continue
        rel = rel_path(root, match.group("file"))
        if rel is None:
            continue
        row = int(match.group("line"))
        out.append(
            signal(
                "vulture", "dead-code", "unused",
                file=rel, line_start=row, line_end=row,
                message=f"unused {match.group('kind')} '{match.group('symbol')}'",
                fact=False,
                extra={
                    "confidence": int(match.group("confidence")),
                    "symbol_kind": match.group("kind"),
                    "symbol": match.group("symbol"),
                },
            )
        )
    return out
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest skills/tech-debt-scan/tests/test_tool_normalisers.py -q`
Expected: PASS.

- [ ] **Step 6: Run the gate and commit**

```bash
python -m ruff check .
python -m mypy
python -m pytest -q
git add skills/tech-debt-scan/scripts/tool_normalisers.py skills/tech-debt-scan/tests/test_tool_normalisers.py skills/tech-debt-scan/tests/fixtures/tool-output
git commit -m "$(cat <<'EOF'
feat(tech-debt-scan): the ruff and vulture normalisers

Both fixtures are real output captured from the installed tools against the
service-py corpus, not payloads written from documentation. ruff's absolute
backslashed filename is relativised and rule codes outside the debt map are
dropped; vulture has no JSON mode at all, so its plain-text grammar is
parsed and its confidence carried through for 4b to weight.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: The lizard normaliser — CSV, and a composite field

**Confidence: 94%.** lizard's CSV has no header row and its sixth column packs name, line range and path into one string with a mixed separator. The column order is pinned by a captured row, and a threshold keeps the signal list bounded.

**Files:**
- Modify: `skills/tech-debt-scan/scripts/tool_normalisers.py`
- Modify: `skills/tech-debt-scan/tests/test_tool_normalisers.py`
- Create: `skills/tech-debt-scan/tests/fixtures/tool-output/lizard.csv`

**Interfaces:**
- Consumes: `rel_path`, `signal`.
- Produces: `normalise_lizard(payload, root) -> list[Signal]`, `LIZARD_MIN_CCN: int`, `LIZARD_MIN_NLOC: int`.

- [ ] **Step 1: Commit the captured payload**

Create `skills/tech-debt-scan/tests/fixtures/tool-output/lizard.csv` — real `lizard --csv` output captured 2026-09-06, paths shortened to the fixture root. The columns are NLOC, CCN, token count, parameter count, length, the composite `name@start-end@file`, file, name, signature, start line, end line:

```
2,1,18,2,2,"__init__@16-17@src/pay/gateway.py","src/pay/gateway.py","__init__","__init__( self , base : str = API_BASE )",16,17
9,3,73,3,9,"refund@19-27@src/pay/gateway.py","src/pay/gateway.py","refund","refund( self , order_id : str , amount_cents : int )",19,27
4,2,66,2,4,"post@12-15@src/pay/ledger.py","src/pay/ledger.py","post","post( entry : Entry , path : Path = LEDGER_PATH )",12,15
34,13,290,4,34,"issue_partial@41-74@src/pay/refund.py","src/pay/refund.py","issue_partial","issue_partial( order_id : str , amount : int , reason : str , actor : str )",41,74
18,11,150,2,18,"settle@10-27@src\pay\settlement.py","src\pay\settlement.py","settle","settle( order : Order , now : datetime )",10,27
```

- [ ] **Step 2: Write the failing tests**

Append to `skills/tech-debt-scan/tests/test_tool_normalisers.py`:

```python
import csv


class TestNormaliseLizard:
    def _signals(self) -> list:
        from tool_normalisers import normalise_lizard

        text = (FIXTURES / "lizard.csv").read_text(encoding="utf-8")
        rows = [row for row in csv.reader(text.splitlines()) if row]
        return normalise_lizard(rows, ROOT)

    def test_only_units_over_the_threshold_are_reported(self) -> None:
        """lizard reports every function; a signal per function would swamp
        the lead cap, so only complex or long units become signals."""
        assert {s["extra"]["name"] for s in self._signals()} == {"issue_partial", "settle"}

    def test_line_range_comes_from_the_last_two_columns(self) -> None:
        partial = next(s for s in self._signals() if s["extra"]["name"] == "issue_partial")
        assert (partial["line_start"], partial["line_end"]) == (41, 74)

    def test_ccn_and_nloc_are_carried_in_extra(self) -> None:
        partial = next(s for s in self._signals() if s["extra"]["name"] == "issue_partial")
        assert partial["extra"]["ccn"] == 13
        assert partial["extra"]["nloc"] == 34
        assert partial["extra"]["parameters"] == 4

    def test_backslashed_path_is_forward_slashed(self) -> None:
        settle = next(s for s in self._signals() if s["extra"]["name"] == "settle")
        assert settle["file"] == "src/pay/settlement.py"

    def test_kind_and_family_are_complexity(self) -> None:
        assert {(s["kind"], s["family"]) for s in self._signals()} == {
            ("complexity", "complexity")
        }

    def test_a_short_row_is_skipped_not_fatal(self) -> None:
        from tool_normalisers import normalise_lizard

        assert normalise_lizard([["2", "1", "18"]], ROOT) == []

    def test_a_non_numeric_row_is_skipped_not_fatal(self) -> None:
        from tool_normalisers import normalise_lizard

        row = ["x", "y", "1", "2", "3", "c", "src/a.py", "f", "f()", "a", "b"]
        assert normalise_lizard([row], ROOT) == []

    def test_every_lizard_signal_is_inference_class(self) -> None:
        assert all(s["fact"] is False for s in self._signals())
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_tool_normalisers.py -q -k Lizard`
Expected: FAIL, `ImportError: cannot import name 'normalise_lizard'`.

- [ ] **Step 4: Write the normaliser**

Append to `skills/tech-debt-scan/scripts/tool_normalisers.py`:

```python
# A unit is worth a signal when it is genuinely hard to hold in the head.
# lizard reports every function it parses, so without a threshold a
# medium repository would fill the lead cap with two-line constructors.
LIZARD_MIN_CCN: Final[int] = 10
LIZARD_MIN_NLOC: Final[int] = 60

# lizard --csv writes no header. Columns, in order: NLOC, CCN, token count,
# parameter count, length, "name@start-end@file", file, name, signature,
# start line, end line.
_LIZARD_COLUMNS: Final[int] = 11


def normalise_lizard(payload: Any, root: Path) -> list[Signal]:
    """lizard's CSV rows as complexity signals.

    lizard has no JSON mode and always exits 0, so the rows themselves are
    the only signal that it ran. Only units at or above ``LIZARD_MIN_CCN``
    cyclomatic complexity or ``LIZARD_MIN_NLOC`` lines are reported.
    """
    if not isinstance(payload, list):
        return []
    out: list[Signal] = []
    for row in payload:
        if not isinstance(row, list) or len(row) < _LIZARD_COLUMNS:
            continue
        try:
            nloc, ccn, _tokens, parameters = (int(row[0]), int(row[1]), int(row[2]), int(row[3]))
            start, end = int(row[9]), int(row[10])
        except (TypeError, ValueError):
            continue
        if ccn < LIZARD_MIN_CCN and nloc < LIZARD_MIN_NLOC:
            continue
        rel = rel_path(root, row[6])
        if rel is None:
            continue
        name = str(row[7])
        out.append(
            signal(
                "lizard", "complexity", "complexity",
                file=rel, line_start=start, line_end=end,
                message=f"{name} has cyclomatic complexity {ccn} over {nloc} lines",
                fact=False,
                extra={"name": name, "ccn": ccn, "nloc": nloc, "parameters": parameters},
            )
        )
    return out
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest skills/tech-debt-scan/tests/test_tool_normalisers.py -q`
Expected: PASS.

- [ ] **Step 6: Run the gate and commit**

```bash
python -m ruff check .
python -m mypy
python -m pytest -q
git add skills/tech-debt-scan/scripts/tool_normalisers.py skills/tech-debt-scan/tests/test_tool_normalisers.py skills/tech-debt-scan/tests/fixtures/tool-output/lizard.csv
git commit -m "$(cat <<'EOF'
feat(tech-debt-scan): the lizard normaliser

lizard has no JSON mode and always exits 0, so its CSV rows are both the
result and the evidence that it ran. The captured fixture pins the column
order, which the tool documents only by example, and a complexity-or-length
threshold keeps a per-function reporter from filling the lead cap with
two-line constructors.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: The JavaScript normalisers — madge, jscpd and knip

**Confidence: 93%.** Three real payloads, and the one place source text could leak. jscpd's duplicate record carries a `fragment` field holding the duplicated source, which must be dropped for the same reason gitleaks' `Secret` is.

**Files:**
- Modify: `skills/tech-debt-scan/scripts/tool_normalisers.py`
- Modify: `skills/tech-debt-scan/tests/test_tool_normalisers.py`
- Create: `skills/tech-debt-scan/tests/fixtures/tool-output/madge.json`, `jscpd.json`, `knip.json`

**Interfaces:**
- Consumes: `rel_path`, `signal`.
- Produces: `normalise_madge`, `normalise_jscpd`, `normalise_knip`, each `(payload, root) -> list[Signal]`.

- [ ] **Step 1: Commit the captured payloads**

Create `skills/tech-debt-scan/tests/fixtures/tool-output/madge.json` — real `madge --extensions ts --circular --json` output captured 2026-09-06 against the web-ts fixture. Note that paths are relative to the scanned directory, not the repository root:

```json
[
  ["cart/cart.ts", "cart/pricing.ts", "cart/stock.ts"]
]
```

Create `skills/tech-debt-scan/tests/fixtures/tool-output/jscpd.json` — real `jscpd --reporters json --min-tokens 20` output captured 2026-09-06 against a synthetic clone pair, trimmed to one duplicate and its statistics:

```json
{
  "duplicates": [
    {
      "firstFile": {
        "end": 8,
        "endLoc": {"column": 1, "line": 8, "position": 269},
        "name": "src/util/format.ts",
        "start": 1,
        "startLoc": {"column": 0, "line": 1, "position": 0}
      },
      "format": "typescript",
      "fragment": "export function compute(items: number[], rate: number): number {\n  let total = 0;\n}",
      "isNew": false,
      "lines": 8,
      "secondFile": {
        "end": 12,
        "endLoc": {"column": 1, "line": 12, "position": 269},
        "name": "src/util/format-legacy.ts",
        "start": 5,
        "startLoc": {"column": 0, "line": 5, "position": 0}
      },
      "tokens": 79
    }
  ],
  "statistics": {
    "detectionDate": "2026-09-06T16:32:58.732Z",
    "total": {"clones": 1, "duplicatedLines": 8, "lines": 115, "percentage": 6.95}
  }
}
```

Create `skills/tech-debt-scan/tests/fixtures/tool-output/knip.json` — real `knip --reporter json` output captured 2026-09-06 against the web-ts fixture, trimmed to three issues covering both shapes it produces:

```json
{
  "issues": [
    {
      "file": "vendor/tiny-emitter.js",
      "exports": [],
      "files": [{"name": "vendor/tiny-emitter.js"}],
      "types": [],
      "dependencies": []
    },
    {
      "file": "src/util/format-legacy.ts",
      "exports": [{"name": "formatLegacy", "line": 4, "col": 17, "pos": 96}],
      "files": [],
      "types": [],
      "dependencies": []
    },
    {
      "file": "package.json",
      "exports": [],
      "files": [],
      "types": [],
      "dependencies": [{"name": "left-pad", "line": 12, "col": 6, "pos": 240}]
    }
  ]
}
```

- [ ] **Step 2: Write the failing tests**

Append to `skills/tech-debt-scan/tests/test_tool_normalisers.py`:

```python
class TestNormaliseMadge:
    def _signals(self, base: str = "src") -> list:
        from tool_normalisers import normalise_madge

        payload = json.loads((FIXTURES / "madge.json").read_text(encoding="utf-8"))
        return normalise_madge(payload, ROOT, base=base)

    def test_one_cycle_becomes_one_signal(self) -> None:
        assert len(self._signals()) == 1

    def test_the_signal_names_the_first_file_of_the_cycle(self) -> None:
        assert self._signals()[0]["file"] == "src/cart/cart.ts"

    def test_the_whole_cycle_is_carried_in_extra(self) -> None:
        assert self._signals()[0]["extra"]["cycle"] == [
            "src/cart/cart.ts", "src/cart/pricing.ts", "src/cart/stock.ts",
        ]

    def test_kind_and_family_are_cycle_and_architecture(self) -> None:
        assert (self._signals()[0]["kind"], self._signals()[0]["family"]) == (
            "cycle", "architecture",
        )

    def test_a_cycle_has_no_line_range(self) -> None:
        """A cycle is a property of the import graph, not of any line."""
        assert self._signals()[0]["line_start"] is None
        assert self._signals()[0]["line_end"] is None

    def test_an_empty_graph_produces_nothing(self) -> None:
        from tool_normalisers import normalise_madge

        assert normalise_madge([], ROOT, base="src") == []

    def test_every_madge_signal_is_inference_class(self) -> None:
        assert all(s["fact"] is False for s in self._signals())


class TestNormaliseJscpd:
    def _signals(self) -> list:
        from tool_normalisers import normalise_jscpd

        payload = json.loads((FIXTURES / "jscpd.json").read_text(encoding="utf-8"))
        return normalise_jscpd(payload, ROOT)

    def test_one_duplicate_becomes_one_signal(self) -> None:
        assert len(self._signals()) == 1

    def test_the_signal_names_the_first_file_and_its_span(self) -> None:
        first = self._signals()[0]
        assert first["file"] == "src/util/format.ts"
        assert (first["line_start"], first["line_end"]) == (1, 8)

    def test_the_second_file_and_its_span_are_carried_in_extra(self) -> None:
        extra = self._signals()[0]["extra"]
        assert extra["other_file"] == "src/util/format-legacy.ts"
        assert extra["other_line_start"] == 5
        assert extra["other_line_end"] == 12
        assert extra["tokens"] == 79

    def test_the_duplicated_source_fragment_is_never_carried(self) -> None:
        """jscpd's `fragment` holds the duplicated source itself. It is dropped
        for the same reason gitleaks' Secret is: tool-signals.json is read into
        prompts (spec 4.5)."""
        blob = json.dumps(self._signals())
        assert "fragment" not in blob
        assert "export function compute" not in blob

    def test_the_nondeterministic_detection_date_is_never_carried(self) -> None:
        assert "detectionDate" not in json.dumps(self._signals())
        assert "2026-09-06T16:32" not in json.dumps(self._signals())

    def test_a_report_with_no_duplicates_produces_nothing(self) -> None:
        from tool_normalisers import normalise_jscpd

        assert normalise_jscpd({"duplicates": [], "statistics": {}}, ROOT) == []


class TestNormaliseKnip:
    def _signals(self) -> list:
        from tool_normalisers import normalise_knip

        payload = json.loads((FIXTURES / "knip.json").read_text(encoding="utf-8"))
        return normalise_knip(payload, ROOT)

    def test_an_unused_file_becomes_a_whole_file_signal(self) -> None:
        unused_file = next(s for s in self._signals() if s["file"] == "vendor/tiny-emitter.js")
        assert unused_file["extra"]["issue"] == "files"
        assert unused_file["line_start"] is None

    def test_an_unused_export_carries_its_line_and_symbol(self) -> None:
        export = next(s for s in self._signals() if s["extra"].get("symbol") == "formatLegacy")
        assert export["file"] == "src/util/format-legacy.ts"
        assert export["line_start"] == 4 and export["line_end"] == 4

    def test_an_unused_dependency_is_dependency_debt(self) -> None:
        dependency = next(s for s in self._signals() if s["extra"].get("symbol") == "left-pad")
        assert dependency["family"] == "dependency-debt"
        assert dependency["kind"] == "unused"

    def test_unused_files_and_exports_are_dead_code(self) -> None:
        families = {s["family"] for s in self._signals()
                    if s["extra"].get("issue") in {"files", "exports"}}
        assert families == {"dead-code"}

    def test_empty_categories_produce_no_signals(self) -> None:
        from tool_normalisers import normalise_knip

        payload = {"issues": [{"file": "a.ts", "exports": [], "files": [], "types": [],
                               "dependencies": []}]}
        assert normalise_knip(payload, ROOT) == []

    def test_every_knip_signal_is_inference_class(self) -> None:
        assert all(s["fact"] is False for s in self._signals())
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_tool_normalisers.py -q -k "Madge or Jscpd or Knip"`
Expected: FAIL, `ImportError: cannot import name 'normalise_madge'`.

- [ ] **Step 4: Write the three normalisers**

Append to `skills/tech-debt-scan/scripts/tool_normalisers.py`:

```python
# knip issue category -> (family, kind). Categories outside this map are
# real knip output but not debt families we act on.
KNIP_CATEGORIES: Final[dict[str, tuple[str, str]]] = {
    "files": ("dead-code", "unused"),
    "exports": ("dead-code", "unused"),
    "types": ("dead-code", "unused"),
    "dependencies": ("dependency-debt", "unused"),
    "devDependencies": ("dependency-debt", "unused"),
    "unlisted": ("dependency-debt", "unused"),
}


def _joined(base: str, rel: str) -> str:
    """``rel`` prefixed with the directory madge or jscpd was pointed at."""
    prefix = base.strip("/")
    return f"{prefix}/{rel}" if prefix else rel


def normalise_madge(payload: Any, root: Path, *, base: str = "") -> list[Signal]:
    """madge's circular-dependency list as architecture signals.

    madge reports paths relative to the directory it was given, so ``base``
    puts them back under the repository root. A cycle is a property of the
    import graph rather than of any line, so the signal carries no line
    range and names the cycle's first file.
    """
    if not isinstance(payload, list):
        return []
    out: list[Signal] = []
    for cycle in payload:
        if not isinstance(cycle, list) or not cycle:
            continue
        members = [rel_path(root, _joined(base, str(item))) for item in cycle]
        kept = [member for member in members if member is not None]
        if not kept:
            continue
        out.append(
            signal(
                "madge", "architecture", "cycle",
                file=kept[0], line_start=None, line_end=None,
                message=f"import cycle through {len(kept)} modules: {' -> '.join(kept)}",
                fact=False,
                extra={"cycle": kept},
            )
        )
    return out


def normalise_jscpd(payload: Any, root: Path, *, base: str = "") -> list[Signal]:
    """jscpd's duplicate list as duplication signals.

    ``fragment`` holds the duplicated source itself and is never copied into
    a signal, for the same reason gitleaks' ``Secret`` is not: this file is
    read into prompts. ``statistics.detectionDate`` is a wall-clock stamp and
    is likewise never propagated, so a golden of these signals is stable.
    """
    if not isinstance(payload, dict):
        return []
    out: list[Signal] = []
    for duplicate in payload.get("duplicates") or []:
        if not isinstance(duplicate, dict):
            continue
        first, second = duplicate.get("firstFile") or {}, duplicate.get("secondFile") or {}
        first_rel = rel_path(root, _joined(base, str(first.get("name", ""))))
        second_rel = rel_path(root, _joined(base, str(second.get("name", ""))))
        if first_rel is None or second_rel is None:
            continue
        out.append(
            signal(
                "jscpd", "duplication", "clone",
                file=first_rel,
                line_start=first.get("start"),
                line_end=first.get("end"),
                message=(
                    f"{duplicate.get('lines', 0)} duplicated lines shared with {second_rel}"
                ),
                fact=False,
                extra={
                    "other_file": second_rel,
                    "other_line_start": second.get("start"),
                    "other_line_end": second.get("end"),
                    "tokens": duplicate.get("tokens"),
                    "format": duplicate.get("format"),
                },
            )
        )
    return out


def normalise_knip(payload: Any, root: Path) -> list[Signal]:
    """knip's issue list as dead-code and dependency signals.

    knip reports per file, with one array per issue category. Without
    ``node_modules`` it reports whole unused files and no exports; with them
    it reports both. Each entry in a mapped category becomes one signal.
    """
    if not isinstance(payload, dict):
        return []
    out: list[Signal] = []
    for issue in payload.get("issues") or []:
        if not isinstance(issue, dict):
            continue
        rel = rel_path(root, issue.get("file"))
        if rel is None:
            continue
        for category, mapping in KNIP_CATEGORIES.items():
            family, kind = mapping
            for entry in issue.get(category) or []:
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("name", ""))
                line = entry.get("line")
                row = line if isinstance(line, int) else None
                whole_file = category == "files"
                out.append(
                    signal(
                        "knip", family, kind,
                        file=rel,
                        line_start=None if whole_file else row,
                        line_end=None if whole_file else row,
                        message=(
                            f"unused file {rel}" if whole_file
                            else f"unused {category[:-1]} '{name}'"
                        ),
                        fact=False,
                        extra={"issue": category, "symbol": name},
                    )
                )
    return out
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest skills/tech-debt-scan/tests/test_tool_normalisers.py -q`
Expected: PASS.

- [ ] **Step 6: Run the gate and commit**

```bash
python -m ruff check .
python -m mypy
python -m pytest -q
git add skills/tech-debt-scan/scripts/tool_normalisers.py skills/tech-debt-scan/tests/test_tool_normalisers.py skills/tech-debt-scan/tests/fixtures/tool-output
git commit -m "$(cat <<'EOF'
feat(tech-debt-scan): the madge, jscpd and knip normalisers

All three payloads are real captured output. madge and jscpd report paths
relative to the directory they were pointed at, so both take a base and put
them back under the repository root.

jscpd's duplicate record carries a fragment field holding the duplicated
source. It is dropped rather than redacted, the rule spec 4.5 sets for
gitleaks' Secret, because tool-signals.json is read into prompts. The
report's detectionDate is a wall-clock stamp and is likewise never
propagated, so a golden of these signals is stable.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: The fact-class normalisers — osv-scanner and gitleaks

**Confidence: 92%.** Neither tool is installed, so both payloads are written from the documented schema. This is the plan's largest correctness risk and the reason each payload carries a provenance comment: a later correction should start from a recorded claim rather than a guess.

**Files:**
- Modify: `skills/tech-debt-scan/scripts/tool_normalisers.py`
- Modify: `skills/tech-debt-scan/tests/test_tool_normalisers.py`
- Create: `skills/tech-debt-scan/tests/fixtures/tool-output/osv-scanner.json`, `gitleaks.json`, `PROVENANCE.md`

**Interfaces:**
- Consumes: `rel_path`, `signal`.
- Produces: `normalise_osv_scanner`, `normalise_gitleaks`, each `(payload, root) -> list[Signal]`.

- [ ] **Step 1: Record provenance for every canned payload**

Create `skills/tech-debt-scan/tests/fixtures/tool-output/PROVENANCE.md`:

```markdown
# Where each payload came from

Captured from the installed tool against the corpus on 2026-09-06:

| File | Tool | Version | Command |
|---|---|---|---|
| `ruff.json` | ruff | installed | `ruff check --isolated --output-format json` |
| `vulture.txt` | vulture | 2.16 | `vulture <root>` (exit 3) |
| `lizard.csv` | lizard | 1.24.0 | `lizard --csv <root>` |
| `madge.json` | madge | 8.0.0 | `madge --extensions ts --circular --json <dir>` |
| `jscpd.json` | jscpd | 5.1.2 | `jscpd --reporters json --min-tokens 20 --output <dir>` |
| `knip.json` | knip | installed | `knip --reporter json` (exit 1) |

Written from the tool's documented schema, never executed — these four are
not installable on the development machine:

| File | Tool | Schema source |
|---|---|---|
| `osv-scanner.json` | osv-scanner | documented `results[].packages[].vulnerabilities[]` shape, v1 JSON output |
| `gitleaks.json` | gitleaks | documented report array with `RuleID`, `File`, `StartLine`, `Entropy` |
| `hadolint.json` | hadolint | documented array of `{file, line, column, level, code, message}` |
| `actionlint.json` | actionlint | documented `-format '{{json .}}'` array of `{message, filepath, line, column, kind}` |

A normaliser in the second table has never seen its tool's real output. When
one is corrected against a real run, update this row with the version and
command that produced the correction, so the next reader knows which claims
have been tested and which have not.
```

- [ ] **Step 2: Commit the canned payloads**

Create `skills/tech-debt-scan/tests/fixtures/tool-output/osv-scanner.json`:

```json
{
  "results": [
    {
      "source": {"path": "package-lock.json", "type": "lockfile"},
      "packages": [
        {
          "package": {"name": "left-pad", "version": "1.1.3", "ecosystem": "npm"},
          "vulnerabilities": [
            {
              "id": "GHSA-xxxx-yyyy-zzzz",
              "summary": "Prototype pollution in left-pad",
              "aliases": ["CVE-2099-0001"],
              "database_specific": {"severity": "HIGH"}
            }
          ],
          "groups": [{"ids": ["GHSA-xxxx-yyyy-zzzz"], "max_severity": "7.5"}]
        }
      ]
    }
  ]
}
```

Create `skills/tech-debt-scan/tests/fixtures/tool-output/gitleaks.json`. The `Secret` and `Match` values below are what the normaliser must drop, and are deliberately obvious non-secrets so the fixture itself carries nothing real:

```json
[
  {
    "RuleID": "generic-api-key",
    "Description": "Detected a Generic API Key",
    "File": "src/config/settings.py",
    "StartLine": 12,
    "EndLine": 12,
    "StartColumn": 14,
    "EndColumn": 48,
    "Entropy": 4.31,
    "Secret": "EXAMPLE-NOT-A-REAL-SECRET-VALUE",
    "Match": "api_key = \"EXAMPLE-NOT-A-REAL-SECRET-VALUE\"",
    "Tags": [],
    "Commit": "",
    "Author": "",
    "Date": ""
  }
]
```

- [ ] **Step 3: Write the failing tests**

Append to `skills/tech-debt-scan/tests/test_tool_normalisers.py`:

```python
class TestNormaliseOsvScanner:
    def _signals(self) -> list:
        from tool_normalisers import normalise_osv_scanner

        payload = json.loads((FIXTURES / "osv-scanner.json").read_text(encoding="utf-8"))
        return normalise_osv_scanner(payload, ROOT)

    def test_one_vulnerability_becomes_one_signal(self) -> None:
        assert len(self._signals()) == 1

    def test_the_signal_names_the_lockfile_and_no_line(self) -> None:
        """osv-scanner's JSON carries no line numbers, so the evidence is the
        manifest path (spec 4.5)."""
        first = self._signals()[0]
        assert first["file"] == "package-lock.json"
        assert first["line_start"] is None and first["line_end"] is None

    def test_package_identity_and_advisory_are_carried_in_extra(self) -> None:
        extra = self._signals()[0]["extra"]
        assert extra["package"] == "left-pad"
        assert extra["version"] == "1.1.3"
        assert extra["ecosystem"] == "npm"
        assert extra["id"] == "GHSA-xxxx-yyyy-zzzz"

    def test_osv_signals_are_fact_class(self) -> None:
        """Fact-class is what lets 4b tier these without a verifier."""
        assert all(s["fact"] is True for s in self._signals())

    def test_kind_and_family_are_vuln_and_dependency_debt(self) -> None:
        first = self._signals()[0]
        assert (first["kind"], first["family"]) == ("vuln", "dependency-debt")

    def test_an_empty_result_set_produces_nothing(self) -> None:
        from tool_normalisers import normalise_osv_scanner

        assert normalise_osv_scanner({"results": []}, ROOT) == []


class TestNormaliseGitleaks:
    def _signals(self) -> list:
        from tool_normalisers import normalise_gitleaks

        payload = json.loads((FIXTURES / "gitleaks.json").read_text(encoding="utf-8"))
        return normalise_gitleaks(payload, ROOT)

    def test_one_finding_becomes_one_signal(self) -> None:
        assert len(self._signals()) == 1

    def test_the_signal_names_the_file_and_line(self) -> None:
        first = self._signals()[0]
        assert first["file"] == "src/config/settings.py"
        assert (first["line_start"], first["line_end"]) == (12, 12)

    def test_the_matched_secret_is_never_carried_in_any_field(self) -> None:
        """Dropped, not redacted: a redacted secret is still its own first four
        characters, and this file is read into prompts (spec 4.5)."""
        blob = json.dumps(self._signals())
        assert "EXAMPLE-NOT-A-REAL-SECRET-VALUE" not in blob
        assert "Secret" not in blob
        assert "Match" not in blob

    def test_rule_and_entropy_survive_because_the_verifier_needs_them(self) -> None:
        extra = self._signals()[0]["extra"]
        assert extra["rule"] == "generic-api-key"
        assert extra["entropy"] == 4.31

    def test_gitleaks_signals_are_fact_class(self) -> None:
        assert all(s["fact"] is True for s in self._signals())

    def test_a_record_without_a_usable_file_is_dropped(self) -> None:
        from tool_normalisers import normalise_gitleaks

        assert normalise_gitleaks([{"RuleID": "x", "StartLine": 1}], ROOT) == []
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_tool_normalisers.py -q -k "Osv or Gitleaks"`
Expected: FAIL, `ImportError: cannot import name 'normalise_osv_scanner'`.

- [ ] **Step 5: Write the two normalisers**

Append to `skills/tech-debt-scan/scripts/tool_normalisers.py`:

```python
def normalise_osv_scanner(payload: Any, root: Path) -> list[Signal]:
    """osv-scanner's results as fact-class dependency signals.

    The JSON carries no line numbers, so the evidence is the manifest or
    lockfile path with a null line range (spec 4.5). One signal per
    vulnerability per package, not one per package, so two advisories against
    one dependency stay separately actionable.
    """
    if not isinstance(payload, dict):
        return []
    out: list[Signal] = []
    for result in payload.get("results") or []:
        if not isinstance(result, dict):
            continue
        source = result.get("source") or {}
        rel = rel_path(root, source.get("path"))
        if rel is None:
            continue
        for entry in result.get("packages") or []:
            if not isinstance(entry, dict):
                continue
            package = entry.get("package") or {}
            name = str(package.get("name", ""))
            version = str(package.get("version", ""))
            ecosystem = str(package.get("ecosystem", ""))
            for vulnerability in entry.get("vulnerabilities") or []:
                if not isinstance(vulnerability, dict):
                    continue
                identifier = str(vulnerability.get("id", ""))
                out.append(
                    signal(
                        "osv-scanner", "dependency-debt", "vuln",
                        file=rel, line_start=None, line_end=None,
                        message=(
                            f"{name} {version} ({ecosystem}) is affected by "
                            f"{identifier}: {vulnerability.get('summary', '')}"
                        ),
                        fact=True,
                        extra={
                            "package": name, "version": version,
                            "ecosystem": ecosystem, "id": identifier,
                            "aliases": list(vulnerability.get("aliases") or []),
                        },
                    )
                )
    return out


def normalise_gitleaks(payload: Any, root: Path) -> list[Signal]:
    """gitleaks' findings as fact-class secret signals.

    ``Secret`` and ``Match`` hold the credential gitleaks matched and are
    dropped outright rather than redacted (spec 4.5): this file is read into
    prompts, and a redacted secret is still its own first four characters.
    The rule id, file, line range and entropy that remain are what the
    verifier needs to tell a real leak from a fixture.
    """
    if not isinstance(payload, list):
        return []
    out: list[Signal] = []
    for record in payload:
        if not isinstance(record, dict):
            continue
        rel = rel_path(root, record.get("File"))
        start = record.get("StartLine")
        if rel is None or not isinstance(start, int):
            continue
        end = record.get("EndLine")
        rule = str(record.get("RuleID", ""))
        out.append(
            signal(
                "gitleaks", "security", "secret",
                file=rel, line_start=start,
                line_end=end if isinstance(end, int) else start,
                message=f"{rule}: {record.get('Description', 'possible committed secret')}",
                fact=True,
                extra={"rule": rule, "entropy": record.get("Entropy")},
            )
        )
    return out
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest skills/tech-debt-scan/tests/test_tool_normalisers.py -q`
Expected: PASS.

- [ ] **Step 7: Run the gate and commit**

```bash
python -m ruff check .
python -m mypy
python -m pytest -q
git add skills/tech-debt-scan/scripts/tool_normalisers.py skills/tech-debt-scan/tests/test_tool_normalisers.py skills/tech-debt-scan/tests/fixtures/tool-output
git commit -m "$(cat <<'EOF'
feat(tech-debt-scan): the osv-scanner and gitleaks normalisers

Neither tool is installable here, so both payloads are written from the
documented schema and PROVENANCE.md records which fixtures have seen a real
tool and which have not -- four of the five installed tools contradicted
their documentation, so the distinction matters.

gitleaks reports the credential it matched in Secret and Match. Both are
dropped rather than redacted, and a test asserts the value appears in no
field of the rendered signal. What survives -- rule id, file, line range,
entropy -- is what a verifier needs to tell a real leak from a fixture.

osv findings carry a null line range because the JSON has no line numbers;
the manifest path is the evidence. They are fact-class, which is what lets
4b tier them without a verifier.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: The config-file normalisers — hadolint and actionlint

**Confidence: 93%.** Both are small flat arrays with well-documented shapes, and both are canned for the same reason as Task 6.

**Files:**
- Modify: `skills/tech-debt-scan/scripts/tool_normalisers.py`
- Modify: `skills/tech-debt-scan/tests/test_tool_normalisers.py`
- Create: `skills/tech-debt-scan/tests/fixtures/tool-output/hadolint.json`, `actionlint.json`

**Interfaces:**
- Consumes: `rel_path`, `signal`.
- Produces: `normalise_hadolint`, `normalise_actionlint`, each `(payload, root) -> list[Signal]`; `HADOLINT_SEVERITY: dict[str, int]`.

- [ ] **Step 1: Commit the canned payloads**

Create `skills/tech-debt-scan/tests/fixtures/tool-output/hadolint.json`:

```json
[
  {
    "file": "Dockerfile",
    "line": 1,
    "column": 1,
    "level": "warning",
    "code": "DL3006",
    "message": "Always tag the version of an image explicitly"
  },
  {
    "file": "Dockerfile",
    "line": 9,
    "column": 1,
    "level": "info",
    "code": "DL3059",
    "message": "Multiple consecutive `RUN` instructions. Consider consolidation."
  }
]
```

Create `skills/tech-debt-scan/tests/fixtures/tool-output/actionlint.json`:

```json
[
  {
    "message": "the runner of \"actions/checkout@v2\" action is too old to run on GitHub Actions",
    "filepath": ".github/workflows/ci.yml",
    "line": 21,
    "column": 9,
    "kind": "action",
    "snippet": "      - uses: actions/checkout@v2"
  },
  {
    "message": "shellcheck reported issue in this script: SC2086:info:1:6: Double quote to prevent globbing",
    "filepath": ".github/workflows/ci.yml",
    "line": 34,
    "column": 9,
    "kind": "shellcheck",
    "snippet": "        run: echo $VERSION"
  }
]
```

- [ ] **Step 2: Write the failing tests**

Append to `skills/tech-debt-scan/tests/test_tool_normalisers.py`:

```python
class TestNormaliseHadolint:
    def _signals(self) -> list:
        from tool_normalisers import normalise_hadolint

        payload = json.loads((FIXTURES / "hadolint.json").read_text(encoding="utf-8"))
        return normalise_hadolint(payload, ROOT)

    def test_each_record_becomes_one_dockerfile_signal(self) -> None:
        signals = self._signals()
        assert len(signals) == 2
        assert {s["kind"] for s in signals} == {"dockerfile"}
        assert {s["family"] for s in signals} == {"pipeline-infra"}

    def test_file_line_and_code_are_carried(self) -> None:
        first = self._signals()[0]
        assert first["file"] == "Dockerfile"
        assert (first["line_start"], first["line_end"]) == (1, 1)
        assert first["extra"]["code"] == "DL3006"

    def test_the_level_is_carried_as_a_severity_number(self) -> None:
        from tool_normalisers import HADOLINT_SEVERITY

        first = self._signals()[0]
        assert first["extra"]["severity"] == HADOLINT_SEVERITY["warning"]

    def test_hadolint_signals_are_fact_class(self) -> None:
        assert all(s["fact"] is True for s in self._signals())

    def test_an_unknown_level_falls_back_rather_than_raising(self) -> None:
        from tool_normalisers import normalise_hadolint

        payload = [{"file": "Dockerfile", "line": 3, "level": "nonsense",
                    "code": "DL9999", "message": "x"}]
        assert normalise_hadolint(payload, ROOT)[0]["extra"]["severity"] == 1


class TestNormaliseActionlint:
    def _signals(self) -> list:
        from tool_normalisers import normalise_actionlint

        payload = json.loads((FIXTURES / "actionlint.json").read_text(encoding="utf-8"))
        return normalise_actionlint(payload, ROOT)

    def test_each_record_becomes_one_workflow_signal(self) -> None:
        signals = self._signals()
        assert len(signals) == 2
        assert {s["kind"] for s in signals} == {"workflow"}
        assert {s["family"] for s in signals} == {"pipeline-infra"}

    def test_filepath_is_the_signal_file(self) -> None:
        assert {s["file"] for s in self._signals()} == {".github/workflows/ci.yml"}

    def test_the_kind_field_is_carried_in_extra(self) -> None:
        assert {s["extra"]["check"] for s in self._signals()} == {"action", "shellcheck"}

    def test_the_snippet_is_never_carried(self) -> None:
        """The snippet is a line of the workflow, which may hold a token; the
        file and line are enough to find it."""
        blob = json.dumps(self._signals())
        assert "snippet" not in blob
        assert "echo $VERSION" not in blob

    def test_actionlint_signals_are_fact_class(self) -> None:
        assert all(s["fact"] is True for s in self._signals())

    def test_a_record_without_a_filepath_is_dropped(self) -> None:
        from tool_normalisers import normalise_actionlint

        assert normalise_actionlint([{"message": "x", "line": 1}], ROOT) == []
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_tool_normalisers.py -q -k "Hadolint or Actionlint"`
Expected: FAIL, `ImportError: cannot import name 'normalise_hadolint'`.

- [ ] **Step 4: Write the two normalisers**

Append to `skills/tech-debt-scan/scripts/tool_normalisers.py`:

```python
# hadolint's level names as the severity scale the rest of the skill uses.
HADOLINT_SEVERITY: Final[dict[str, int]] = {
    "error": 4, "warning": 3, "info": 2, "style": 1,
}


def normalise_hadolint(payload: Any, root: Path) -> list[Signal]:
    """hadolint's diagnostics as fact-class Dockerfile signals.

    A hadolint hit is a fact about a file on disk, so it is fact-class and
    merges in 4b with a same-file rule finding rather than becoming a
    separate candidate. An unrecognised level falls back to the lowest
    severity rather than raising, so a new hadolint level cannot fail a scan.
    """
    if not isinstance(payload, list):
        return []
    out: list[Signal] = []
    for record in payload:
        if not isinstance(record, dict):
            continue
        rel = rel_path(root, record.get("file"))
        line = record.get("line")
        if rel is None or not isinstance(line, int):
            continue
        code = str(record.get("code", ""))
        level = str(record.get("level", "")).lower()
        out.append(
            signal(
                "hadolint", "pipeline-infra", "dockerfile",
                file=rel, line_start=line, line_end=line,
                message=f"{code}: {record.get('message', '')}",
                fact=True,
                extra={"code": code, "level": level,
                       "severity": HADOLINT_SEVERITY.get(level, 1)},
            )
        )
    return out


def normalise_actionlint(payload: Any, root: Path) -> list[Signal]:
    """actionlint's diagnostics as fact-class workflow signals.

    ``snippet`` is a line of the workflow itself, which may carry a token or
    an inline secret reference, and is never copied into a signal; the file
    and line are enough to find it.
    """
    if not isinstance(payload, list):
        return []
    out: list[Signal] = []
    for record in payload:
        if not isinstance(record, dict):
            continue
        rel = rel_path(root, record.get("filepath"))
        line = record.get("line")
        if rel is None or not isinstance(line, int):
            continue
        out.append(
            signal(
                "actionlint", "pipeline-infra", "workflow",
                file=rel, line_start=line, line_end=line,
                message=str(record.get("message", "")),
                fact=True,
                extra={"check": str(record.get("kind", ""))},
            )
        )
    return out
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest skills/tech-debt-scan/tests/test_tool_normalisers.py -q`
Expected: PASS.

- [ ] **Step 6: Update PROVENANCE.md and run the gate and commit**

No change is needed to `PROVENANCE.md` — Task 6 already listed hadolint and actionlint in its canned table. Confirm both rows are present before committing.

```bash
python -m ruff check .
python -m mypy
python -m pytest -q
git add skills/tech-debt-scan/scripts/tool_normalisers.py skills/tech-debt-scan/tests/test_tool_normalisers.py skills/tech-debt-scan/tests/fixtures/tool-output
git commit -m "$(cat <<'EOF'
feat(tech-debt-scan): the hadolint and actionlint normalisers

Both are fact-class: a hit is a fact about a file on disk, so in 4b they
merge with a same-file rule finding rather than becoming separate
candidates. An unrecognised hadolint level falls back to the lowest
severity rather than raising, so a new level in a future release cannot
fail a scan.

actionlint's snippet is a line of the workflow, which may carry a token or
an inline secret reference, and is dropped for the same reason jscpd's
fragment is.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: The CLI, `tool-signals.json` and the corpus goldens

**Confidence: 92%.** This is the task that ties everything together and the only one that runs real tools. Its risk is that a golden captures whatever the installed tools happen to do today; Step 1 mitigates that by asserting statuses and reasons explicitly, so a tool that silently stops running is a test failure rather than an empty list nobody notices.

**Files:**
- Modify: `skills/tech-debt-scan/scripts/tools_probe.py`
- Modify: `skills/tech-debt-scan/tests/test_tools_probe.py`
- Create: `skills/tech-debt-scan/tests/golden/service-py/tool-signals.json`, and the same for `web-ts` and `mixed-decoys`

**Interfaces:**
- Consumes: everything from Tasks 1 to 7; `config.load_config`; `inventory.write_json`; `redaction.redact`.
- Produces: `tools_probe.probe(root, config, *, skip_all=False) -> dict[str, Any]`, `tools_probe.argv_for(spec, executable, root) -> list[str]`, `tools_probe.artefact_present(spec, root) -> bool`, `tools_probe.SCHEMA_VERSION = 2`, and the CLI `python scripts/tools_probe.py <repo> --workdir <dir> [--skip-all]`.

- [ ] **Step 1: Write the failing tests for artefact predicates, skipping and the document**

Append to `skills/tech-debt-scan/tests/test_tools_probe.py`:

```python
class TestArtefactPresent:
    def test_hadolint_needs_a_dockerfile(self, tmp_path: Path) -> None:
        from tools_probe import TOOLS, artefact_present

        assert artefact_present(TOOLS["hadolint"], tmp_path) is False
        (tmp_path / "Dockerfile").write_text("FROM python\n", encoding="utf-8")
        assert artefact_present(TOOLS["hadolint"], tmp_path) is True

    def test_actionlint_needs_a_workflow(self, tmp_path: Path) -> None:
        from tools_probe import TOOLS, artefact_present

        assert artefact_present(TOOLS["actionlint"], tmp_path) is False
        workflow = tmp_path / ".github" / "workflows" / "ci.yml"
        workflow.parent.mkdir(parents=True)
        workflow.write_text("on: push\n", encoding="utf-8")
        assert artefact_present(TOOLS["actionlint"], tmp_path) is True

    def test_osv_scanner_needs_a_lockfile(self, tmp_path: Path) -> None:
        from tools_probe import TOOLS, artefact_present

        assert artefact_present(TOOLS["osv-scanner"], tmp_path) is False
        (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
        assert artefact_present(TOOLS["osv-scanner"], tmp_path) is True

    def test_python_tools_need_a_python_file(self, tmp_path: Path) -> None:
        from tools_probe import TOOLS, artefact_present

        assert artefact_present(TOOLS["vulture"], tmp_path) is False
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        assert artefact_present(TOOLS["vulture"], tmp_path) is True

    def test_node_tools_need_a_js_or_ts_file(self, tmp_path: Path) -> None:
        from tools_probe import TOOLS, artefact_present

        assert artefact_present(TOOLS["madge"], tmp_path) is False
        (tmp_path / "a.ts").write_text("export const x = 1;\n", encoding="utf-8")
        assert artefact_present(TOOLS["madge"], tmp_path) is True


class TestProbe:
    def test_skip_all_writes_every_tool_skipped_and_no_signals(self, tmp_path: Path) -> None:
        from config import load_config
        from tools_probe import TOOLS, probe

        document = probe(tmp_path, load_config(tmp_path), skip_all=True)
        assert set(document["tools"]) == set(TOOLS)
        assert {entry["status"] for entry in document["tools"].values()} == {"skipped"}
        assert document["signals"] == []
        assert document["schema_version"] == 2

    def test_a_denied_tool_is_skipped_with_its_reason(self, tmp_path: Path) -> None:
        from config import load_config
        from tools_probe import probe

        config = load_config(tmp_path)
        config["tools"]["deny"] = ["ruff"]
        document = probe(tmp_path, config)
        assert document["tools"]["ruff"]["status"] == "skipped"
        assert "deny" in document["tools"]["ruff"]["reason"]

    def test_a_missing_artefact_is_skipped_with_its_reason(self, tmp_path: Path) -> None:
        from config import load_config
        from tools_probe import probe

        document = probe(tmp_path, load_config(tmp_path))
        assert document["tools"]["hadolint"]["status"] in {"skipped", "absent"}
        if document["tools"]["hadolint"]["status"] == "skipped":
            assert "artefact" in document["tools"]["hadolint"]["reason"]

    def test_offline_without_a_database_skips_osv_scanner(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        import tools_probe
        from config import load_config

        (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(tools_probe, "find_tool", lambda name, root: "osv-scanner")
        monkeypatch.delenv("OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY", raising=False)
        config = load_config(tmp_path)
        config["tools"]["network"] = False
        document = tools_probe.probe(tmp_path, config)
        assert document["tools"]["osv-scanner"]["status"] == "skipped"
        assert document["tools"]["osv-scanner"]["reason"] == "no local database"

    def test_offline_with_a_database_passes_the_offline_flag(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from tools_probe import TOOLS, argv_for

        monkeypatch.setenv("OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY", str(tmp_path))
        argv = argv_for(TOOLS["osv-scanner"], "osv-scanner", tmp_path, network=False)
        assert "--offline" in argv

    def test_online_does_not_pass_the_offline_flag(self, tmp_path: Path) -> None:
        from tools_probe import TOOLS, argv_for

        argv = argv_for(TOOLS["osv-scanner"], "osv-scanner", tmp_path, network=True)
        assert "--offline" not in argv

    def test_madge_is_always_invoked_with_explicit_extensions(self, tmp_path: Path) -> None:
        """Without --extensions madge returns an empty graph and exits 0 on a
        TypeScript tree -- a false "no cycles" (spec 4.5)."""
        from tools_probe import TOOLS, argv_for

        argv = argv_for(TOOLS["madge"], "madge", tmp_path, network=True)
        assert "--extensions" in argv
        assert "--circular" in argv

    def test_signals_are_redacted_before_they_are_written(self, tmp_path: Path) -> None:
        from tools_probe import redact_signals

        signals = [{
            "tool": "ruff", "family": "security", "kind": "error-masking",
            "file": "a.py", "line_start": 1, "line_end": 1,
            "message": 'token = "sk_live_51H8f2kL9mN3pQ7rS4tU6vW"',
            "fact": False, "extra": {"code": "E722"},
        }]
        out = redact_signals(signals)
        assert "sk_live_51H8f2kL9mN3pQ7rS4tU6vW" not in json.dumps(out)
        assert "sk_l***" in out[0]["message"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_tools_probe.py -q -k "Artefact or Probe"`
Expected: FAIL, `ImportError: cannot import name 'artefact_present'`.

- [ ] **Step 3: Write the argv builders, artefact predicates, probe and CLI**

Append to `skills/tech-debt-scan/scripts/tools_probe.py`:

```python
import argparse
import os
import sys

from config import ConfigError, load_config
from inventory import write_json
from redaction import redact
from tool_normalisers import (
    normalise_actionlint, normalise_gitleaks, normalise_hadolint, normalise_jscpd,
    normalise_knip, normalise_lizard, normalise_madge, normalise_osv_scanner,
    normalise_ruff, normalise_vulture,
)

SCHEMA_VERSION: Final[int] = 2

NORMALISERS: Final[dict[str, Normaliser]] = {
    "osv-scanner": normalise_osv_scanner,
    "gitleaks": normalise_gitleaks,
    "ruff": normalise_ruff,
    "vulture": normalise_vulture,
    "lizard": normalise_lizard,
    "jscpd": normalise_jscpd,
    "knip": normalise_knip,
    "madge": normalise_madge,
    "hadolint": normalise_hadolint,
    "actionlint": normalise_actionlint,
}

# Glob patterns whose presence makes a tool worth running at all.
ARTEFACTS: Final[dict[str, tuple[str, ...]]] = {
    "osv-scanner": ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
                    "requirements.txt", "Pipfile.lock", "go.sum", "Cargo.lock",
                    "composer.lock", "Gemfile.lock"),
    "gitleaks": ("*",),
    "ruff": ("**/*.py",),
    "vulture": ("**/*.py",),
    "lizard": ("**/*.py", "**/*.js", "**/*.ts", "**/*.java", "**/*.go", "**/*.cs"),
    "jscpd": ("**/*.js", "**/*.ts", "**/*.tsx", "**/*.jsx"),
    "knip": ("package.json",),
    "madge": ("**/*.js", "**/*.ts", "**/*.tsx", "**/*.jsx"),
    "hadolint": ("Dockerfile", "**/Dockerfile", "**/Dockerfile.*"),
    "actionlint": (".github/workflows/*.yml", ".github/workflows/*.yaml"),
}

RUFF_SELECT: Final[str] = "E722,BLE001,S110,S112,C901,PLR0911,PLR0912,PLR0913,PLR0915,F401,UP035"
MADGE_EXTENSIONS: Final[str] = "js,jsx,ts,tsx"
JSCPD_MIN_TOKENS: Final[str] = "50"


def artefact_present(spec: ToolSpec, root: Path) -> bool:
    """True when the repository holds something ``spec``'s tool could read."""
    for pattern in ARTEFACTS[spec.name]:
        if pattern == "*":
            return True
        if next(root.glob(pattern), None) is not None:
            return True
    return False


def argv_for(spec: ToolSpec, executable: str, root: Path, *, network: bool) -> list[str]:
    """The exact command line for one tool.

    madge is given ``--extensions`` explicitly: without it madge returns an
    empty graph and exits 0 on a TypeScript tree, which reads as "no cycles"
    and would never fail a test (spec 4.5). ruff runs ``--isolated`` so the
    scanned repository's own configuration cannot silence the rules we ask
    for.
    """
    target = str(root)
    if spec.name == "ruff":
        return [executable, "check", "--isolated", "--output-format", "json",
                "--select", RUFF_SELECT, target]
    if spec.name == "vulture":
        return [executable, target]
    if spec.name == "lizard":
        return [executable, "--csv", target]
    if spec.name == "madge":
        return [executable, "--extensions", MADGE_EXTENSIONS, "--circular", "--json", target]
    if spec.name == "jscpd":
        return [executable, "--reporters", "json", "--min-tokens", JSCPD_MIN_TOKENS,
                target, "--output"]
    if spec.name == "knip":
        return [executable, "--reporter", "json"]
    if spec.name == "gitleaks":
        return [executable, "detect", "--no-git", "--report-format", "json",
                "--report-path", "-", "--source", target]
    if spec.name == "hadolint":
        dockerfiles = [str(path) for path in sorted(root.glob("**/Dockerfile"))]
        return [executable, "--format", "json", *dockerfiles]
    if spec.name == "actionlint":
        return [executable, "-format", "{{json .}}", "-no-color"]
    if spec.name == "osv-scanner":
        argv = [executable, "--format", "json", "--recursive", target]
        if not network:
            argv.insert(1, "--offline")
        return argv
    raise ValueError(f"no argv builder for {spec.name!r}")


def redact_signals(signals: list[Any]) -> list[Any]:
    """Every signal message run through the shared redactor before writing."""
    out = []
    for item in signals:
        copied = dict(item)
        copied["message"] = redact(str(copied.get("message", "")))
        out.append(copied)
    return out


def probe(root: Path, config: dict[str, Any], *, skip_all: bool = False) -> dict[str, Any]:
    """Run every allowed, present tool and return the ``tool-signals.json`` document."""
    tools_config = config.get("tools") or {}
    deny = set(tools_config.get("deny") or [])
    network = bool(tools_config.get("network", True))
    default_timeout = int(tools_config.get("timeout_s", 120))
    tools: dict[str, Any] = {}
    signals: list[Any] = []

    for name, spec in TOOLS.items():
        if skip_all:
            tools[name] = _entry("skipped", reason="--skip-all")
            continue
        if name in deny:
            tools[name] = _entry("skipped", reason="deny list")
            continue
        if not artefact_present(spec, root):
            tools[name] = _entry("skipped", reason="no matching artefact")
            continue
        executable = find_tool(name, root)
        if executable is None:
            tools[name] = _entry("absent")
            continue
        if name == "osv-scanner" and not network and not os.environ.get(
            "OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY"
        ):
            tools[name] = _entry("skipped", reason="no local database")
            continue
        timeout = spec.timeout_s or default_timeout
        result = run_tool(spec, executable, argv_for(spec, executable, root, network=network),
                          root, timeout)
        tools[name] = _entry(result.status, reason=result.reason, duration_s=result.duration_s)
        if result.status == "ran":
            signals.extend(NORMALISERS[name](result.payload, root))

    return {
        "schema_version": SCHEMA_VERSION,
        "tools": tools,
        "signals": redact_signals(signals),
    }


def _entry(status: str, *, reason: str = "", duration_s: float = 0.0) -> dict[str, Any]:
    return {"status": status, "version": "", "duration_s": round(duration_s, 3),
            "reason": reason}


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run installed external tools")
    parser.add_argument("path", help="repo root to scan")
    parser.add_argument("--workdir", default=".tech-debt",
                        help="directory to write tool-signals.json into (default .tech-debt)")
    parser.add_argument("--skip-all", action="store_true",
                        help="run nothing; write every tool skipped")
    args = parser.parse_args(argv)
    root = Path(args.path)
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2
    try:
        document = probe(root, load_config(root), skip_all=args.skip_all)
    except (OSError, ValueError, ConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    out_path = Path(args.workdir) / "tool-signals.json"
    write_json(out_path, document)
    ran = sum(1 for entry in document["tools"].values() if entry["status"] == "ran")
    print(f"wrote {out_path} ({ran} tools ran, {len(document['signals'])} signals)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest skills/tech-debt-scan/tests/test_tools_probe.py -q`
Expected: PASS.

- [ ] **Step 5: Write the corpus golden test**

Append to `skills/tech-debt-scan/tests/test_tools_probe.py`:

```python
import os

GOLDEN = Path(__file__).resolve().parent / "golden"
CORPUS = Path(__file__).resolve().parent / "fixtures" / "corpus"


class TestCorpusGoldens:
    @pytest.mark.parametrize("fixture", ["service-py", "web-ts", "mixed-decoys"])
    def test_tool_signals_match_the_golden(self, fixture: str) -> None:
        """The signals array is compared in full; each tool's status and reason
        are compared too, so a tool that silently stops running fails here
        rather than quietly producing an empty list. version and duration_s are
        excluded: they are machine-dependent and would fail for the wrong
        reason (spec 4.5)."""
        from config import load_config
        from tools_probe import probe

        root = CORPUS / fixture / "files"
        document = probe(root, load_config(root))
        actual = {
            "schema_version": document["schema_version"],
            "tools": {name: {"status": entry["status"], "reason": entry["reason"]}
                      for name, entry in document["tools"].items()},
            "signals": document["signals"],
        }
        path = GOLDEN / fixture / "tool-signals.json"
        if os.environ.get("UPDATE_GOLDENS"):
            from inventory import write_json

            write_json(path, actual)
        expected = json.loads(path.read_text(encoding="utf-8"))
        assert actual == expected
```

- [ ] **Step 6: Generate the goldens and read every one before accepting it**

```bash
UPDATE_GOLDENS=1 python -m pytest skills/tech-debt-scan/tests/test_tools_probe.py -q -k CorpusGoldens
python -m pytest skills/tech-debt-scan/tests/test_tools_probe.py -q -k CorpusGoldens
```

On PowerShell: `$env:UPDATE_GOLDENS="1"; python -m pytest ... ; Remove-Item Env:UPDATE_GOLDENS`.

Then read all three generated files and check each against these questions, reporting the answers in your task report:

1. Does every tool that should have run show `ran`? A `skipped` or `absent` you did not expect is a defect, not a golden.
2. Does every `skipped` carry a reason that is true of that fixture — no Dockerfile, no lockfile, no Python file?
3. Do the signals name real files that exist in that fixture, with plausible line numbers?
4. Does any signal carry a `fragment`, `snippet`, `Secret`, `Match` or `detectionDate` key, or a value that looks like source text? Any hit is a defect in a normaliser, not something to accept into a golden.
5. Is the second run byte-identical to the first?

- [ ] **Step 7: Run the gate and commit**

```bash
python -m ruff check .
python -m mypy
python skills/tech-debt-scan/scripts/skill_check.py
python -m pytest -q
git add skills/tech-debt-scan/scripts/tools_probe.py skills/tech-debt-scan/tests/test_tools_probe.py skills/tech-debt-scan/tests/golden
git commit -m "$(cat <<'EOF'
feat(tech-debt-scan): the probe CLI, tool-signals.json and the corpus goldens

The probe runs every allowed, present tool over a fixture and writes the
document nothing reads until 4b. Statuses and reasons are compared by the
golden alongside the signals, so a tool that silently stops running fails
the suite instead of quietly producing an empty list; version and duration
are excluded because they are machine-dependent.

madge is invoked with explicit --extensions and ruff with --isolated: the
first because madge otherwise reports an empty graph and exits 0, the
second so the scanned repository's own configuration cannot silence the
rules we asked for.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Documentation and the phase gate

**Confidence: 96%.** Documentation and verification only. The one judgement call is stating the canned-normaliser limitation plainly rather than burying it.

**Files:**
- Modify: `docs/architecture.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: everything. Produces nothing other tasks use.

- [ ] **Step 1: Read the real `--help` before writing a word about it**

```bash
python skills/tech-debt-scan/scripts/tools_probe.py --help
```

Every flag you document must appear in that output. Do not copy the invocation from this plan's prose — a prior session shipped a README example whose flags argparse did not define, and a reviewer caught it.

- [ ] **Step 2: Document the probe in `docs/architecture.md`**

Add a subsection under the pipeline description covering, in prose:

- What `tools_probe.py` and `tool_normalisers.py` each own, and that the split exists so a normaliser is testable from a captured payload with nothing mocked.
- That the probe never installs, never invokes `npx` and never executes project code, and that presence is `shutil.which` then `node_modules/.bin` for jscpd, knip and madge only.
- The four statuses and what each means.
- That `tool-signals.json` is written but read by nothing until phase 4b.
- **That six normalisers were written against real captured output and four — osv-scanner, gitleaks, hadolint, actionlint — were written from documentation and have never seen their tool run.** Name `tests/fixtures/tool-output/PROVENANCE.md` as the record of which is which. State plainly that four of the five installed tools contradicted their own documentation, so an unvalidated normaliser is a real risk and not a formality.
- That no field which can carry source text or a credential reaches `tool-signals.json`, naming gitleaks' `Secret` and `Match`, jscpd's `fragment` and actionlint's `snippet`.

- [ ] **Step 3: Add the probe to `README.md`'s script list**

One row per new script, in the existing table's style, with the one-line responsibility each. Do not describe step 4 of the workflow — SKILL.md gains that in 4b, and describing it now would document behaviour that does not exist.

- [ ] **Step 4: Sweep for drift**

Check that no document claims the probe is wired into `/tech-debt-scan`, that no document lists a flag `--help` does not show, and that `docs/architecture.md`'s script count and file list include both new modules.

- [ ] **Step 5: Run the full gate**

```bash
python -m ruff check .
python -m mypy
python skills/tech-debt-scan/scripts/skill_check.py
python -m pytest -q
```

All four green. `skill_check.py` must still pass unchanged: 4a adds no command to SKILL.md.

- [ ] **Step 6: Commit**

```bash
git add docs/architecture.md README.md
git commit -m "$(cat <<'EOF'
docs(tech-debt-scan): document the probe and which normalisers are unproven

Six normalisers were written against real captured output; four were
written from documentation and have never seen their tool run. The
architecture document says so plainly and points at PROVENANCE.md, because
four of the five tools that could be installed contradicted their own
documentation -- madge silently reports an empty graph without
--extensions, which no canned test would ever catch.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Self-review

**Spec coverage.** Section 4.5's requirements against tasks: presence detection including `node_modules/.bin` and never `npx` (Task 1); the runner, timeouts, four statuses, exit tables, truncated stderr (Task 2); ten normalisers (Tasks 3 to 7); fact and inference classification (Task 1's registry, asserted per normaliser in Tasks 3 to 7); the secret and source-text rules (Tasks 5, 6, 7); path normalisation and the agreement test (Task 1); golden determinism (Task 8); the offline mapping and the no-database skip (Task 8); `--skip-all` (Task 8); the deny list and missing artefacts (Task 8). Section 11's 4a gate is Task 8 plus Task 9's full run. No 4a requirement is unassigned.

**Deliberately out of scope**, because they are 4b: reading `tool-signals.json` anywhere, the `tool:` corroboration token, the fact-class tier bypass, module chunking, `--deep`, SKILL.md step 4 and the network notice, and the live run.

**Placeholder scan.** Every code step carries the code. Every test step carries its assertions. No step says "add error handling" or "similar to Task N". The four canned payloads are written out in full rather than described.

**Type consistency.** `Signal` is defined once in Task 1 and constructed only through `signal()`, which validates `kind` against `KINDS`. `rel_path(root, raw)` keeps one signature throughout. `normalise_madge` and `normalise_jscpd` take the extra keyword `base` and both are called with it in Task 8's argv-relative handling; the other eight take `(payload, root)` and the `Normaliser` alias in Task 1 matches that shape — Task 8's `NORMALISERS` table is typed against it, so a mismatch is a mypy error rather than a runtime surprise. `ToolSpec` fields are set in Task 1 and read in Tasks 2 and 8 only.

**One known gap to raise at execution.** `NORMALISERS` in Task 8 is typed `dict[str, Normaliser]`, but `normalise_madge` and `normalise_jscpd` have an extra keyword-only parameter with a default. That is compatible with the alias at runtime and mypy accepts a callable with extra defaulted keyword-only arguments; if a future mypy version rejects it, widen the alias rather than removing the parameter, because the base prefix is load-bearing for both tools' paths.
