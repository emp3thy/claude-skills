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
        constant and every identifier (``ast.Name``, and the attribute name on
        ``ast.Attribute``) for the substring "npx", case-insensitively. A
        docstring mentioning npx is fine; a string literal or identifier that
        would execute or reference it at runtime is not.
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
