"""Tests for the external-tool probe (spec 4.5)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Final

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


# The registry's contract, pinned against spec 4.5 section 4.5's tool table
# and its "Fact versus inference" / timeout prose -- not against tools_probe.py
# itself, so this catches a regression rather than only restating the code.
# vulture's findings exit is 3 (not the common 1); lizard and jscpd have no
# findings exit at all because both always exit 0; jscpd's channel is the
# report file it writes while every other tool's is stdout; lizard parses as
# CSV and vulture as plain lines, everything else as JSON; osv-scanner's
# timeout is 300s and every other tool takes the config default (None here).
SPEC_4_5_REGISTRY: Final[dict[str, dict[str, Any]]] = {
    "osv-scanner": {"channel": "stdout", "parse": "json", "findings_exit": (1,), "timeout_s": 300},
    "gitleaks": {"channel": "stdout", "parse": "json", "findings_exit": (1,), "timeout_s": None},
    "ruff": {"channel": "stdout", "parse": "json", "findings_exit": (1,), "timeout_s": None},
    "vulture": {"channel": "stdout", "parse": "lines", "findings_exit": (3,), "timeout_s": None},
    "lizard": {"channel": "stdout", "parse": "csv", "findings_exit": (), "timeout_s": None},
    "jscpd": {"channel": "report_file", "parse": "json", "findings_exit": (), "timeout_s": None},
    "knip": {"channel": "stdout", "parse": "json", "findings_exit": (1,), "timeout_s": None},
    "madge": {"channel": "stdout", "parse": "json", "findings_exit": (1,), "timeout_s": None},
    "hadolint": {"channel": "stdout", "parse": "json", "findings_exit": (1,), "timeout_s": None},
    "actionlint": {"channel": "stdout", "parse": "json", "findings_exit": (1,), "timeout_s": None},
}


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

    def test_every_signal_family_is_a_real_family(self) -> None:
        """A family name the skill does not know would reach candidates in 4b and
        match nothing. categories.FAMILIES is the authority."""
        from categories import FAMILIES
        from tool_normalisers import SIGNAL_FAMILIES

        assert set(FAMILIES) >= SIGNAL_FAMILIES

    def test_only_node_tools_look_in_node_modules(self) -> None:
        from tools_probe import TOOLS

        node = {name for name, spec in TOOLS.items() if spec.node_bin}
        assert node == {"jscpd", "knip", "madge"}

    @pytest.mark.parametrize("name", sorted(SPEC_4_5_REGISTRY))
    def test_registry_fields_match_spec_4_5(self, name: str) -> None:
        """channel, parse, findings_exit and timeout_s pinned per tool.

        These four fields are the part of spec 4.5 corrected against measured
        tool behaviour; an untested table can silently regress to the
        documented-but-wrong values the correction replaced.
        """
        from tools_probe import TOOLS

        expected = SPEC_4_5_REGISTRY[name]
        spec = TOOLS[name]
        assert spec.channel == expected["channel"]
        assert spec.parse == expected["parse"]
        assert spec.findings_exit == expected["findings_exit"]
        assert spec.timeout_s == expected["timeout_s"]


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

    def test_npx_is_never_invoked(self) -> None:
        """Spec 4.5 forbids npx outright: it would install a package to run it.

        The guarantee is about what the probe *invokes*, not about what it is
        allowed to *explain*. The module's own docstrings name ``npx`` to state
        the rule plainly for a reader; that mention must not trip this test.
        So this walks the AST rather than grepping raw source, skipping module,
        class and function docstrings, and checks every remaining string
        constant, every identifier (``ast.Name``, and the attribute name on
        ``ast.Attribute``), and every import alias (``ast.alias.name`` and its
        ``asname``, covering ``import npx`` and ``from npx import run`` alike)
        for the substring "npx", case-insensitively. A docstring mentioning
        npx is fine; a string literal, identifier or import that would
        execute or reference it at runtime is not.
        """
        import ast

        source = (SCRIPTS / "tools_probe.py").read_text(encoding="utf-8")
        tree = ast.parse(source)

        docstring_nodes: set[ast.AST] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                body = getattr(node, "body", None)
                if body:
                    first = body[0]
                    if (
                        isinstance(first, ast.Expr)
                        and isinstance(first.value, ast.Constant)
                        and isinstance(first.value.value, str)
                    ):
                        docstring_nodes.add(first.value)

        for node in ast.walk(tree):
            if node in docstring_nodes:
                continue
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert "npx" not in node.value.lower()
            elif isinstance(node, ast.Name):
                assert "npx" not in node.id.lower()
            elif isinstance(node, ast.Attribute):
                assert "npx" not in node.attr.lower()
            elif isinstance(node, ast.ImportFrom):
                if node.module is not None:
                    assert "npx" not in node.module.lower()
            elif isinstance(node, ast.alias):
                assert "npx" not in node.name.lower()
                if node.asname:
                    assert "npx" not in node.asname.lower()
