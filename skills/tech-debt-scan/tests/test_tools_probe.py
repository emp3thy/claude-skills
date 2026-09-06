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

    def test_offline_with_a_nonexistent_database_directory_skips_osv_scanner(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """The env var being *set* is not enough (review finding Q8): it must
        also name a directory that actually exists, or an operator's typo or
        a stale path is indistinguishable from a real local database."""
        import tools_probe
        from config import load_config

        (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(tools_probe, "find_tool", lambda name, root: "osv-scanner")
        monkeypatch.setenv(
            "OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY", str(tmp_path / "does-not-exist")
        )
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

    def test_ruff_argv_carries_isolated_and_no_cache(self, tmp_path: Path) -> None:
        """Pins both Task 8 ruff fixes (review finding Q3): --isolated so the
        scanned repository's own config cannot silence the rules asked for,
        and --no-cache so a probe run never writes .ruff_cache into the
        scanned tree. Neither was asserted anywhere before this."""
        from tools_probe import TOOLS, argv_for

        argv = argv_for(TOOLS["ruff"], "ruff", tmp_path, network=True)
        assert "--isolated" in argv
        assert "--no-cache" in argv

    def test_every_string_in_the_document_is_redacted(self, tmp_path: Path) -> None:
        """Redaction must reach every string in the document, not only
        ``message`` and not only the ``signals`` array: rule ids, symbol names
        and cycle-member paths inside ``extra`` are tool-supplied text too,
        wherever they sit -- a plain value, nested inside a list within
        ``extra``, used as a dictionary *key*, or in a failing tool's
        ``reason`` over in the ``tools`` map."""
        from tools_probe import redact_document

        secret = "sk_live_51H8f2kL9mN3pQ7rS4tU6vW"
        stderr = f'exit 1: bad.py:3: invalid syntax at "api_key = "{secret}""'
        document = {
            "schema_version": 2,
            "tools": {
                "vulture": {"status": "failed", "version": "", "duration_s": 0.1,
                            "reason": stderr},
            },
            "signals": [{
                "tool": "ruff", "family": "security", "kind": "error-masking",
                "file": "a.py", "line_start": 1, "line_end": 1,
                "message": f'token = "{secret}"',
                "fact": False,
                "extra": {
                    "code": "E722",
                    "note": f"rotated credential was {secret}",
                    "aliases": [f"backup: {secret}"],
                    f"symbol {secret}": "keyed by tool-supplied text",
                },
            }],
        }
        out = redact_document(document)
        serialised = json.dumps(out)
        assert secret not in serialised
        assert "sk_l***" in serialised
        assert out["schema_version"] == 2
        assert out["tools"]["vulture"]["status"] == "failed"

    def test_a_dict_key_carrying_a_secret_is_redacted(self) -> None:
        """The same gap one level down (Task 8 deferred minor): ``_redact_value``
        walked values only, so a normaliser keying ``extra`` by tool-supplied
        text would put a credential in the document through the key."""
        from tools_probe import _redact_value

        secret = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"
        out = _redact_value({f"seen at {secret}": {"nested": [f"also {secret}"]}})
        assert secret not in json.dumps(out)

    def test_probe_redacts_secrets_reaching_the_document_via_a_normaliser(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Pins the wiring, not just the helper (review finding Q4): every
        other redaction test calls redact_signals directly, so deleting
        ``redact_signals(signals)`` from probe()'s return statement would
        leave them all green. This one drives probe() end to end with a
        stubbed run_tool and normaliser, so the secret must pass through the
        actual call site to be caught."""
        import tools_probe
        from config import load_config

        secret = "sk_live_51H8f2kL9mN3pQ7rS4tU6vW"
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        monkeypatch.setattr(tools_probe, "find_tool", lambda name, root: "fake-ruff")
        monkeypatch.setattr(
            tools_probe,
            "run_tool",
            lambda spec, argv, root, timeout: tools_probe.ToolResult("ran", payload=[]),
        )
        monkeypatch.setitem(
            tools_probe.NORMALISERS,
            "ruff",
            lambda payload, root: [{
                "tool": "ruff", "family": "security", "kind": "error-masking",
                "file": "a.py", "line_start": 1, "line_end": 1,
                "message": "fine",
                "fact": False,
                "extra": {"note": f"token was {secret}"},
            }],
        )
        config = load_config(tmp_path)
        config["tools"]["deny"] = [name for name in tools_probe.TOOLS if name != "ruff"]
        document = tools_probe.probe(tmp_path, config)
        assert secret not in json.dumps(document)

    def test_probe_redacts_a_secret_reaching_the_document_via_a_failure_reason(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """The whole-branch review's Critical, pinned. ``run_tool`` puts up to
        STDERR_CHARS characters of raw tool stderr into ``reason``, and a tool
        that fails while reading a file prints the offending source line --
        vulture 2.16 does exactly that on a syntax error, so a credential on
        that line reached ``tool-signals.json`` verbatim. Redaction covered
        ``signals`` only, so no existing test saw it. Driving probe() end to
        end means deleting the redaction call fails here."""
        import tools_probe
        from config import load_config

        secret = "sk_live_51H8f2kL9mN3pQ7rS4tU6vW"
        stderr = f'bad.py:3: invalid syntax at "api_key = "{secret}""'
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        monkeypatch.setattr(tools_probe, "find_tool", lambda name, root: "fake-vulture")
        monkeypatch.setattr(
            tools_probe,
            "run_tool",
            lambda spec, argv, root, timeout: tools_probe.ToolResult(
                "failed", reason=f"exit 1: {stderr}"
            ),
        )
        config = load_config(tmp_path)
        config["tools"]["deny"] = [name for name in tools_probe.TOOLS if name != "vulture"]
        document = tools_probe.probe(tmp_path, config)
        assert document["tools"]["vulture"]["status"] == "failed"
        assert secret not in json.dumps(document)
        assert "invalid syntax" in document["tools"]["vulture"]["reason"]


class TestNormaliserFailureIsContained:
    """The normaliser call was unguarded and _main caught only (OSError,
    ValueError, ConfigError, KeyError), so an AttributeError from a normaliser
    -- the exact shape the deferred osv-scanner minors would raise -- killed
    the process with a traceback, wrote no tool-signals.json at all, and
    exited 1 rather than the SKILL.md convention's code."""

    def test_a_raising_normaliser_costs_one_tool_and_not_the_run(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        import tools_probe
        from config import load_config

        def _boom(payload: Any, root: Path) -> list[Any]:
            raise AttributeError("'str' object has no attribute 'get'")

        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        monkeypatch.setattr(tools_probe, "find_tool", lambda name, root: "fake")
        monkeypatch.setattr(
            tools_probe,
            "run_tool",
            lambda spec, argv, root, timeout: tools_probe.ToolResult("ran", payload=[]),
        )
        monkeypatch.setitem(tools_probe.NORMALISERS, "ruff", _boom)
        monkeypatch.setitem(
            tools_probe.NORMALISERS,
            "vulture",
            lambda payload, root: [{
                "tool": "vulture", "family": "dead-code", "kind": "unused",
                "file": "a.py", "line_start": 1, "line_end": 1,
                "message": "unused variable 'x'", "fact": False, "extra": {},
            }],
        )
        config = load_config(tmp_path)
        config["tools"]["deny"] = [
            name for name in tools_probe.TOOLS if name not in ("ruff", "vulture")
        ]
        document = tools_probe.probe(tmp_path, config)

        assert document["tools"]["ruff"]["status"] == "failed"
        assert "normaliser for ruff" in document["tools"]["ruff"]["reason"]
        assert "AttributeError" in document["tools"]["ruff"]["reason"]
        # Every other tool's work still reaches the document.
        assert document["tools"]["vulture"]["status"] == "ran"
        assert [signal["tool"] for signal in document["signals"]] == ["vulture"]

    def test_a_missing_normaliser_row_still_raises_rather_than_being_demoted(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """The guard must not swallow a programming error. A tool registered
        without a NORMALISERS row is a defect in the registry, not a tool
        failure, and _main no longer catches KeyError around probe() either."""
        import tools_probe
        from config import load_config

        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        monkeypatch.setattr(tools_probe, "find_tool", lambda name, root: "fake")
        monkeypatch.setattr(
            tools_probe,
            "run_tool",
            lambda spec, argv, root, timeout: tools_probe.ToolResult("ran", payload=[]),
        )
        monkeypatch.delitem(tools_probe.NORMALISERS, "ruff")
        config = load_config(tmp_path)
        config["tools"]["deny"] = [name for name in tools_probe.TOOLS if name != "ruff"]
        with pytest.raises(KeyError):
            tools_probe.probe(tmp_path, config)

    def test_main_still_writes_the_document_when_a_normaliser_raises(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """The consequence that mattered: before the guard, no output file was
        written at all."""
        import tools_probe
        from config import load_config

        def _boom(payload: Any, root: Path) -> list[Any]:
            raise AttributeError("boom")

        tree = tmp_path / "tree"
        tree.mkdir()
        (tree / "a.py").write_text("x = 1\n", encoding="utf-8")
        workdir = tmp_path / "out"
        monkeypatch.setattr(tools_probe, "find_tool", lambda name, root: "fake")
        monkeypatch.setattr(
            tools_probe,
            "run_tool",
            lambda spec, argv, root, timeout: tools_probe.ToolResult("ran", payload=[]),
        )
        monkeypatch.setitem(tools_probe.NORMALISERS, "ruff", _boom)
        monkeypatch.setattr(tools_probe, "load_config", load_config)
        assert tools_probe._main([str(tree), "--workdir", str(workdir)]) == 0
        written = json.loads((workdir / "tool-signals.json").read_text(encoding="utf-8"))
        assert written["tools"]["ruff"]["status"] == "failed"


class TestRelativeRoot:
    """The whole-branch review's High finding. ``_main`` never resolved the
    repository path while every sibling script does, and ``run_tool`` sets
    ``cwd=root`` while ``argv_for`` also passes ``str(root)`` -- so a relative
    ``<repo>`` was re-resolved against the new cwd into ``<root>/<root>``.
    Measured before the fix on one fixture tree: 7 signals with an absolute
    path, 0 with the relative spelling of the same tree, with ruff and lizard
    both still reporting ``ran``. SKILL.md's convention is a user-supplied
    relative ``<repo>``, so this was the ordinary case."""

    def test_the_same_tree_gives_the_same_signals_by_relative_and_absolute_path(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        import shutil

        if shutil.which("ruff") is None:
            pytest.skip("ruff is not installed on this machine")

        from config import load_config
        from tools_probe import probe

        tree = tmp_path / "tree"
        tree.mkdir()
        (tree / "a.py").write_text(
            "import os\n\n\ndef f():\n    try:\n        pass\n    except:\n        pass\n",
            encoding="utf-8",
        )
        absolute = probe(tree, load_config(tree))
        monkeypatch.chdir(tmp_path)
        relative = probe(Path("tree"), load_config(Path("tree")))
        assert relative["signals"] == absolute["signals"]
        assert relative["signals"] != []
        assert {name: entry["status"] for name, entry in relative["tools"].items()} == {
            name: entry["status"] for name, entry in absolute["tools"].items()
        }

    def test_main_resolves_the_path_like_every_sibling_script(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """inventory.py, patterns.py and rules.py all resolve; tools_probe.py
        was the only one that did not."""
        import tools_probe

        seen: list[Path] = []
        tree = tmp_path / "tree"
        tree.mkdir()
        monkeypatch.setattr(
            tools_probe,
            "probe",
            lambda root, config, skip_all=False: seen.append(root)
            or {"schema_version": 2, "tools": {}, "signals": []},
        )
        monkeypatch.chdir(tmp_path)
        assert tools_probe._main(["tree", "--workdir", str(tmp_path / "out")]) == 0
        assert seen == [tree.resolve()]


class TestGlobOperandGuard:
    """Review finding Q2: hadolint's artefact predicate and its argv builder
    globbed different patterns, so a repository whose only Dockerfile is
    Dockerfile.prod passed artefact_present and then reached hadolint with no
    file operand -- hadolint reads a Dockerfile from inherited stdin in that
    case and hangs until the timeout."""

    def test_dockerfile_prod_only_is_correctly_invoked(self, tmp_path: Path) -> None:
        from tools_probe import TOOLS, argv_for, artefact_present

        (tmp_path / "Dockerfile.prod").write_text("FROM python\n", encoding="utf-8")
        spec = TOOLS["hadolint"]
        assert artefact_present(spec, tmp_path) is True
        argv = argv_for(spec, "hadolint", tmp_path, network=True)
        assert any(part.endswith("Dockerfile.prod") for part in argv)

    @pytest.mark.parametrize(
        "dockerfile_path", ["Dockerfile", "nested/Dockerfile", "Dockerfile.prod"]
    )
    def test_every_hadolint_artefact_shape_yields_a_nonempty_operand_list(
        self, dockerfile_path: str, tmp_path: Path
    ) -> None:
        """Every shape ARTEFACTS["hadolint"] accepts must also be a shape
        _glob_operands finds -- the two are built from the same patterns, so
        the artefact predicate passing can never again mean an empty argv."""
        from tools_probe import TOOLS, _glob_operands, argv_for, artefact_present

        path = tmp_path / dockerfile_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("FROM python\n", encoding="utf-8")
        spec = TOOLS["hadolint"]
        assert artefact_present(spec, tmp_path) is True
        assert _glob_operands(spec, tmp_path) != []
        argv = argv_for(spec, "hadolint", tmp_path, network=True)
        assert len(argv) > 3  # more than just [executable, "--format", "json"]

    def test_probe_skips_rather_than_runs_a_glob_operand_tool_with_no_files(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """The structural guard, not just the alignment fix above: even if a
        glob expansion for a GLOB_OPERAND_TOOLS member ever comes back empty
        again, probe() must skip it rather than hand run_tool an argv with no
        file operand."""
        import tools_probe
        from config import load_config

        (tmp_path / "Dockerfile").write_text("FROM python\n", encoding="utf-8")
        monkeypatch.setattr(tools_probe, "find_tool", lambda name, root: "hadolint")
        monkeypatch.setattr(tools_probe, "_glob_operands", lambda spec, root: [])
        document = tools_probe.probe(tmp_path, load_config(tmp_path))
        assert document["tools"]["hadolint"]["status"] == "skipped"
        assert document["tools"]["hadolint"]["reason"] == "no matching artefact"

    def test_the_glob_operand_tools_are_exactly_hadolint_and_actionlint(self) -> None:
        """Documents the hazard's current scope: every other builder passes
        the target directory itself, which is always non-empty, so this is
        where the guard needs to apply today. actionlint joined in the
        whole-branch fix wave -- with no operand it walks up from its cwd
        looking for a .git directory and errors out when there is none."""
        from tools_probe import GLOB_OPERAND_TOOLS

        assert {"hadolint", "actionlint"} == GLOB_OPERAND_TOOLS

    def test_actionlint_is_invoked_with_its_workflow_files_as_operands(
        self, tmp_path: Path
    ) -> None:
        """The predicate globs .github/workflows/*.yml; before the sweep the
        argv passed no file operand at all, so the two selected different
        things and actionlint's own cwd walk decided what was scanned."""
        from tools_probe import TOOLS, argv_for, artefact_present

        workflow = tmp_path / ".github" / "workflows" / "ci.yml"
        workflow.parent.mkdir(parents=True)
        workflow.write_text("on: push\n", encoding="utf-8")
        spec = TOOLS["actionlint"]
        assert artefact_present(spec, tmp_path) is True
        argv = argv_for(spec, "actionlint", tmp_path, network=True)
        assert any(part.endswith("ci.yml") for part in argv)


class TestPredicateAgreesWithArgv:
    """The whole-branch review's sweep: every artefact predicate checked
    against what that tool's argv actually scans. Ruling 16 fixed the one
    disagreement it was shown (hadolint) without asking whether the table held
    others; it held three more."""

    def test_osv_scanner_finds_a_lockfile_in_a_subdirectory(self, tmp_path: Path) -> None:
        """Its ten patterns were bare filenames, so root.glob matched the root
        only -- while the invocation is --recursive. Proven on this repository
        before the fix: two lockfiles under tests/fixtures/corpus and
        "osv-scanner skipped: no matching artefact". osv-scanner is the only
        tool on spec 4.8's fact-class tier-A bypass, so its gate being wrong
        meant the sole unverified route to tier A never fired."""
        from tools_probe import TOOLS, artefact_present

        spec = TOOLS["osv-scanner"]
        assert artefact_present(spec, tmp_path) is False
        nested = tmp_path / "services" / "api"
        nested.mkdir(parents=True)
        (nested / "requirements.txt").write_text("flask==1.0\n", encoding="utf-8")
        assert artefact_present(spec, tmp_path) is True

    def test_osv_scanner_still_finds_a_lockfile_at_the_root(self, tmp_path: Path) -> None:
        """``**/`` in pathlib matches the root directory too, so widening the
        patterns is a superset of what they matched before, not a swap."""
        from tools_probe import TOOLS, artefact_present

        (tmp_path / "Cargo.lock").write_text("", encoding="utf-8")
        assert artefact_present(TOOLS["osv-scanner"], tmp_path) is True

    def test_jscpd_is_restricted_to_the_four_languages_its_gate_selects_for(
        self, tmp_path: Path
    ) -> None:
        """The gate is JS/TS; the invocation parsed every format jscpd knows.
        On a copy of this repository 3,022 of 3,267 signals were jscpd's and
        12 of those were JS/TS."""
        from tools_probe import ARTEFACTS, JSCPD_FORMATS, TOOLS, argv_for

        argv = argv_for(TOOLS["jscpd"], "jscpd", tmp_path, network=True)
        assert "--format" in argv
        assert argv[argv.index("--format") + 1] == JSCPD_FORMATS
        gated = {pattern.rsplit(".", 1)[1] for pattern in ARTEFACTS["jscpd"]}
        formats = set(JSCPD_FORMATS.split(","))
        assert gated == {"js", "ts", "tsx", "jsx"}
        assert formats == {"javascript", "typescript", "tsx", "jsx"}
        assert len(gated) == len(formats)

    def test_jscpd_is_told_to_ignore_the_trees_the_inventory_never_walks(
        self, tmp_path: Path
    ) -> None:
        """jscpd descended into node_modules -- reproduced on a scratch tree
        with two identical vendored files and a .gitignore listing it. The
        ignore list is derived from inventory.py's own classification, not a
        second list invented here, so the probe and the inventory cannot drift
        apart about what is vendored."""
        from inventory import DEFAULT_IGNORE, PATH_CLASS_GLOBS
        from tools_probe import TOOLS, _ignore_globs, argv_for

        globs = _ignore_globs()
        for name in DEFAULT_IGNORE:
            assert f"**/{name}/**" in globs
        for pattern in PATH_CLASS_GLOBS["vendored"]:
            stem = pattern.removeprefix("*/").removesuffix("/*")
            assert f"**/{stem}/**" in globs
        assert "**/node_modules/**" in globs
        assert "**/*.min.js" in globs

        argv = argv_for(TOOLS["jscpd"], "jscpd", tmp_path, network=True)
        assert "--ignore" in argv
        assert "**/node_modules/**" in argv[argv.index("--ignore") + 1]

    def test_lizard_gates_on_every_extension_its_parsers_accept(self, tmp_path: Path) -> None:
        """The predicate named six extensions while the invocation scans every
        language lizard has a parser for, so a repository written entirely in
        one of the others was never offered to it."""
        from tools_probe import ARTEFACTS, TOOLS, artefact_present

        patterns = set(ARTEFACTS["lizard"])
        for extension in ("py", "ts", "java", "go", "cs", "rb", "php", "rs", "c", "cpp"):
            assert f"**/*.{extension}" in patterns
        (tmp_path / "app.rb").write_text("def f; end\n", encoding="utf-8")
        assert artefact_present(TOOLS["lizard"], tmp_path) is True

    def test_every_builder_names_an_absolute_target(self, tmp_path: Path) -> None:
        """The convention argv_for documents: no builder may depend on cwd for
        *what* it scans, because run_tool sets cwd separately. knip and
        actionlint passed no target at all before the sweep."""
        from tools_probe import TOOLS, argv_for

        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "Dockerfile").write_text("FROM python\n", encoding="utf-8")
        workflow = tmp_path / ".github" / "workflows" / "ci.yml"
        workflow.parent.mkdir(parents=True)
        workflow.write_text("on: push\n", encoding="utf-8")

        for name, spec in TOOLS.items():
            argv = argv_for(spec, name, tmp_path, network=True)
            named = [part for part in argv[1:] if str(tmp_path) in part]
            assert named, f"{name} names no absolute target: {argv}"

class TestSignalSortKeyTotality:
    def test_signals_tied_on_file_line_kind_message_still_sort_deterministically(
        self,
    ) -> None:
        """Reproduces the review's jscpd tie (finding Q1): one block
        duplicated in two different places produces two signals equal on
        file, line_start, kind and message, differing only in extra. Without
        extra in the key, a stable sort falls back to preserving the tool's
        own (not guaranteed stable) emission order for the tied pair --
        exactly the non-determinism the sort exists to remove."""
        import random

        from tools_probe import _signal_sort_key

        base: dict[str, Any] = {
            "tool": "jscpd", "family": "duplication", "kind": "clone",
            "file": "a.ts", "line_start": 10, "line_end": 30,
            "message": "20 duplicated lines shared with b.ts", "fact": False,
        }
        first: dict[str, Any] = {**base, "extra": {"other_line_start": 200, "other_line_end": 220}}
        second: dict[str, Any] = {**base, "extra": {"other_line_start": 400, "other_line_end": 420}}
        canonical_order = sorted([first, second], key=_signal_sort_key)
        assert canonical_order in ([first, second], [second, first])
        for _ in range(20):
            shuffled = [first, second]
            random.shuffle(shuffled)
            assert sorted(shuffled, key=_signal_sort_key) == canonical_order


class TestRuffRuleSetsAgree:
    def test_ruff_select_and_ruff_kinds_name_the_same_codes(self) -> None:
        """RUFF_SELECT (tools_probe) and RUFF_KINDS (tool_normalisers) are two
        independently maintained lists of the same rule codes (review finding
        Q5); adding a code to only one silently breaks the pairing with no
        test failure until now."""
        from tool_normalisers import RUFF_KINDS
        from tools_probe import RUFF_SELECT

        assert set(RUFF_SELECT.split(",")) == set(RUFF_KINDS)


class TestRegistryCompleteness:
    def test_every_tool_has_a_normaliser_and_an_artefact_row(self) -> None:
        """Review finding Q6: registering a tool without a NORMALISERS row
        raises an uncaught KeyError from the CLI the first time that tool
        actually runs. _main now also catches KeyError as a defence in
        depth (verified by hand below; the CLI itself has no test coverage
        yet -- review finding Q7, out of scope for this round)."""
        from tools_probe import ARTEFACTS, NORMALISERS, TOOLS

        assert set(NORMALISERS) == set(ARTEFACTS) == set(TOOLS)


class TestRuffNoCacheLeak:
    def test_probe_leaves_no_ruff_cache_in_a_scratch_copy_of_the_corpus(
        self, tmp_path: Path
    ) -> None:
        """Pins the Task 8 --no-cache fix (review finding Q3): deleting the
        flag leaves every test in this file green and instead breaks
        test_corpus.py's byte-identical-fixture check in an unrelated file,
        with no visible connection to the cause. Runs against a scratch copy
        under pytest's own tmp_path -- never the corpus fixture in place."""
        import shutil

        if shutil.which("ruff") is None:
            pytest.skip("ruff is not installed on this machine")

        from config import load_config
        from tools_probe import probe

        source = CORPUS / "service-py" / "files"
        scratch = tmp_path / "service-py-scratch"
        shutil.copytree(source, scratch)
        probe(scratch, load_config(scratch))
        assert not (scratch / ".ruff_cache").exists()


GOLDEN = Path(__file__).resolve().parent / "golden"
CORPUS = Path(__file__).resolve().parent / "fixtures" / "corpus"


FIXTURES_WITH_GOLDENS: Final[tuple[str, ...]] = ("service-py", "web-ts", "mixed-decoys")


def _golden_comparison(fixture: str) -> tuple[dict[str, Any], dict[str, Any], list[str], list[str]]:
    """A live probe of ``fixture`` and its golden, reduced to what is comparable.

    ``absent`` is the one status that is a fact about the machine rather than
    about the fixture, so it is what makes a golden unportable: pinning it
    records that osv-scanner, gitleaks, hadolint and actionlint happen not to
    be installed on the developer's machine, and a reviewer who has any of
    them -- or phase 4b's own gate, which spec 11 says runs "with the installed
    tools present" -- gets a red suite for the wrong reason. Proven with a stub
    hadolint on PATH: status flipped to ``ran``, one signal appeared, and the
    mixed-decoys golden failed.

    So the golden records ``covered_tools``: the tools whose status, reason and
    signals it actually pins, which is every tool that was not ``absent`` when
    it was generated. The comparison is then the intersection of that set with
    the tools this machine can exercise, and the signal lists are filtered to
    the same set on both sides. A tool the golden covers but this machine
    lacks, and a tool this machine has but the golden never saw, are both
    excluded -- and the caller names both in its failure message, so nothing
    is dropped quietly.
    """
    from config import load_config
    from tools_probe import probe

    root = CORPUS / fixture / "files"
    document = probe(root, load_config(root))
    present = {name for name, entry in document["tools"].items() if entry["status"] != "absent"}
    actual = {
        "schema_version": document["schema_version"],
        "covered_tools": sorted(present),
        # version and duration_s stay out: they are machine-dependent and
        # would fail for the wrong reason (spec 4.5).
        "tools": {name: {"status": entry["status"], "reason": entry["reason"]}
                  for name, entry in document["tools"].items() if name in present},
        "signals": document["signals"],
    }
    path = GOLDEN / fixture / "tool-signals.json"
    if os.environ.get("UPDATE_GOLDENS"):
        from inventory import write_json

        write_json(path, actual)
    expected = json.loads(path.read_text(encoding="utf-8"))
    covered = set(expected["covered_tools"])
    return actual, expected, sorted(covered & present), sorted(present - covered)


class TestCorpusGoldens:
    @pytest.mark.parametrize("fixture", FIXTURES_WITH_GOLDENS)
    def test_tool_signals_match_the_golden(self, fixture: str) -> None:
        """The signals array is compared in full for every tool the golden
        covers and this machine can exercise; each such tool's status and
        reason are compared too, so a tool that silently stops running fails
        here rather than quietly producing an empty list."""
        actual, expected, compared, uncovered = _golden_comparison(fixture)
        assert compared, (
            f"{fixture}: the golden covers {expected['covered_tools']} and this machine "
            f"can exercise none of them, so this test would prove nothing"
        )
        assert {
            "schema_version": actual["schema_version"],
            "tools": {name: actual["tools"][name] for name in compared},
            "signals": [s for s in actual["signals"] if s["tool"] in compared],
        } == {
            "schema_version": expected["schema_version"],
            "tools": {name: expected["tools"][name] for name in compared},
            "signals": [s for s in expected["signals"] if s["tool"] in compared],
        }, (
            f"{fixture}: compared {compared}; not pinned by this golden "
            f"(present here, absent when it was generated): {uncovered}"
        )

    @pytest.mark.parametrize("fixture", FIXTURES_WITH_GOLDENS)
    def test_the_golden_covers_every_machine_independent_row(self, fixture: str) -> None:
        """The floor that stops the portability filter degenerating into a test
        that compares nothing.

        ``probe`` checks ``artefact_present`` before ``find_tool``, so a tool
        skipped for a missing artefact is skipped on every machine, installed
        or not: those rows are a fact about the fixture. Every golden must
        therefore cover all of them, on any machine, and this asserts it
        without depending on which tools happen to be installed."""
        from config import load_config
        from tools_probe import probe

        root = CORPUS / fixture / "files"
        document = probe(root, load_config(root))
        machine_independent = {
            name for name, entry in document["tools"].items()
            if entry["status"] == "skipped" and entry["reason"] == "no matching artefact"
        }
        expected = json.loads(
            (GOLDEN / fixture / "tool-signals.json").read_text(encoding="utf-8")
        )
        assert machine_independent, f"{fixture} skips no tool for a missing artefact"
        assert machine_independent <= set(expected["covered_tools"])
