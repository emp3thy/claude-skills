from dd_common import StepError, read_json, run_git, write_json


def test_run_git_returns_none_on_failure(tmp_path):
    assert run_git(tmp_path, ["rev-parse", "HEAD"]) is None


def test_write_json_is_sorted_lf_with_trailing_newline(tmp_path):
    p = tmp_path / "x.json"
    write_json(p, {"b": 1, "a": [1]})
    assert p.read_bytes() == b'{\n "a": [\n  1\n ],\n "b": 1\n}\n'
    assert read_json(p) == {"a": [1], "b": 1}


def test_step_error_carries_code():
    assert StepError("x", 5).code == 5
