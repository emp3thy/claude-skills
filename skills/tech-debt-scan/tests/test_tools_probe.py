"""Tests for the external-tool probe (spec 4.5)."""
from __future__ import annotations

import json
import os
import sys
import textwrap
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
        result = run_tool(TOOLS["ruff"], argv, tmp_path, 30)
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
        result = run_tool(TOOLS["ruff"], argv, tmp_path, 30)
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
        result = run_tool(TOOLS["vulture"], argv, tmp_path, 30)
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
        result = run_tool(TOOLS["ruff"], argv, tmp_path, 30)
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
        result = run_tool(TOOLS["ruff"], argv, tmp_path, 30)
        assert result.status == "failed"
        assert "42" in result.reason

    def test_timeout_is_failed_and_names_the_limit(self, tmp_path: Path) -> None:
        from tools_probe import TOOLS, run_tool

        exe, argv = _fake_tool(tmp_path, """
            import time
            time.sleep(30)
        """)
        result = run_tool(TOOLS["ruff"], argv, tmp_path, 1)
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
        result = run_tool(TOOLS["jscpd"], argv, tmp_path, 30)
        assert result.status == "ran"
        assert result.payload == {"duplicates": [{"lines": 8}]}

    def test_report_file_absent_is_failed(self, tmp_path: Path) -> None:
        from tools_probe import TOOLS, run_tool

        exe, argv = _fake_tool(tmp_path, """
            import sys
            print("wrote nothing")
            sys.exit(0)
        """)
        result = run_tool(TOOLS["jscpd"], argv, tmp_path, 30)
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
        run_tool(TOOLS["jscpd"], argv, tmp_path, 30)
        assert set(tmp_path.iterdir()) == before

    def test_missing_executable_is_failed_not_an_exception(self, tmp_path: Path) -> None:
        from tools_probe import TOOLS, run_tool

        result = run_tool(TOOLS["ruff"], ["no-such-exe"], tmp_path, 5)
        assert result.status == "failed"

    def test_report_file_valid_survives_nonzero_exit(self, tmp_path: Path) -> None:
        """jscpd's findings_exit is empty; a valid, already-written report must
        not be discarded just because the exit code is unexpected. The report
        decides and the exit code is commentary for this channel."""
        from tools_probe import TOOLS, run_tool

        exe, argv = _fake_tool(tmp_path, """
            import json, os, sys
            out = sys.argv[1]
            os.makedirs(out, exist_ok=True)
            with open(os.path.join(out, "jscpd-report.json"), "w", encoding="utf-8") as fh:
                json.dump({"duplicates": [{"lines": 8}]}, fh)
            sys.exit(1)
        """)
        result = run_tool(TOOLS["jscpd"], argv, tmp_path, 30)
        assert result.status == "ran"
        assert result.payload == {"duplicates": [{"lines": 8}]}

    def test_report_file_present_but_unparseable_is_failed(self, tmp_path: Path) -> None:
        """Mirror of the tested stdout-unparseable branch, for the channel
        the spec itself says is the trickiest."""
        from tools_probe import TOOLS, run_tool

        exe, argv = _fake_tool(tmp_path, """
            import os, sys
            out = sys.argv[1]
            os.makedirs(out, exist_ok=True)
            with open(os.path.join(out, "jscpd-report.json"), "w", encoding="utf-8") as fh:
                fh.write("not json at all")
            sys.exit(0)
        """)
        result = run_tool(TOOLS["jscpd"], argv, tmp_path, 30)
        assert result.status == "failed"

    def test_cleanup_error_does_not_lose_the_result(self, tmp_path: Path, monkeypatch) -> None:
        """A transient Windows file-lock during cleanup() must not replace a
        pending ToolResult return with an exception - Task 8's loop calls
        run_tool for every tool and depends on it always returning one."""
        import tempfile

        from tools_probe import TOOLS, run_tool

        def _raise_cleanup(self: object) -> None:
            raise OSError("simulated transient file lock")

        monkeypatch.setattr(tempfile.TemporaryDirectory, "cleanup", _raise_cleanup)

        exe, argv = _fake_tool(tmp_path, """
            import json, os, sys
            out = sys.argv[1]
            os.makedirs(out, exist_ok=True)
            with open(os.path.join(out, "jscpd-report.json"), "w", encoding="utf-8") as fh:
                json.dump({"duplicates": []}, fh)
            sys.exit(0)
        """)
        result = run_tool(TOOLS["jscpd"], argv, tmp_path, 30)
        assert result.status == "ran"
        assert result.payload == {"duplicates": []}


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
        assert document["tools"]["hadolint"]["status"] == "skipped"
        assert document["tools"]["hadolint"]["reason"] == "no matching artefact"

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
