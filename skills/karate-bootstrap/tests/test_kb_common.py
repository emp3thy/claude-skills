"""Tests for kb_common module."""
from __future__ import annotations

from pathlib import Path

import kb_common
import pytest
from kb_common import (
    EXIT_MISSING_OUTPUT,
    EXIT_VALIDATION,
    KbError,
    iter_files,
    read_json,
    read_yaml,
    read_yaml_docs,
    rel,
    require_file,
    run_cli,
    write_json,
    write_yaml,
)


def test_exit_codes_match_spec() -> None:
    assert kb_common.EXIT_OK == 0
    assert kb_common.EXIT_VALIDATION == 2
    assert kb_common.EXIT_UNSUPPORTED_STACK == 3
    assert kb_common.EXIT_NO_SCHEMA == 4
    assert kb_common.EXIT_MISSING_OUTPUT == 5
    assert kb_common.EXIT_STOPPED == 6
    assert kb_common.EXIT_TOOLCHAIN == 7


def test_kberror_defaults_to_validation_exit() -> None:
    err = KbError("bad")
    assert err.exit_code == EXIT_VALIDATION
    assert str(err) == "bad"


def test_json_roundtrip_creates_parent_dirs(tmp_path: Path) -> None:
    target = tmp_path / "out" / "nested" / "x.json"
    write_json(target, {"b": 1, "a": [1, 2]})
    assert read_json(target) == {"b": 1, "a": [1, 2]}
    assert target.read_text(encoding="utf-8").endswith("\n")


def test_yaml_roundtrip_preserves_key_order(tmp_path: Path) -> None:
    target = tmp_path / "ledger.yaml"
    write_yaml(target, {"version": 1, "entry_points": [{"id": "GET /x"}], "unresolved": []})
    text = target.read_text(encoding="utf-8")
    assert text.index("version") < text.index("entry_points") < text.index("unresolved")
    assert read_yaml(target)["entry_points"][0]["id"] == "GET /x"


def test_read_yaml_docs_splits_multi_document(tmp_path: Path) -> None:
    target = tmp_path / "multi.yml"
    target.write_text("kind: A\n---\nkind: B\n", encoding="utf-8")
    assert [d["kind"] for d in read_yaml_docs(target)] == ["A", "B"]


def test_require_file_raises_missing_output(tmp_path: Path) -> None:
    with pytest.raises(KbError) as excinfo:
        require_file(tmp_path / "nope.json", "stack.json")
    assert excinfo.value.exit_code == EXIT_MISSING_OUTPUT
    assert "stack.json" in str(excinfo.value)


def test_rel_is_posix(tmp_path: Path) -> None:
    child = tmp_path / "src" / "A.java"
    assert rel(child, tmp_path) == "src/A.java"


def test_iter_files_skips_ignored_dirs(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "A.java").write_text("x", encoding="utf-8")
    (tmp_path / "target").mkdir()
    (tmp_path / "target" / "B.java").write_text("x", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "c.py").write_text("x", encoding="utf-8")
    found = sorted(rel(p, tmp_path) for p in iter_files(tmp_path, (".java", ".py")))
    assert found == ["src/A.java"]


def test_run_cli_maps_kberror_to_exit_code(capsys: pytest.CaptureFixture[str]) -> None:
    def failing(_argv: list[str] | None) -> int:
        raise KbError("no stack", EXIT_MISSING_OUTPUT)

    assert run_cli(failing, []) == EXIT_MISSING_OUTPUT
    assert "error: no stack" in capsys.readouterr().err
