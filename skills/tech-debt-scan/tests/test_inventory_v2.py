"""inventory.py v2: classes, git pass, coupling, graph, band, mapping, docs (spec 4.2)."""
from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest
import yaml
from config import load_config
from inventory import _classify_path, _line_metrics, walk_inventory
from make_history import replay_history

FIXTURES = Path(__file__).parent / "fixtures"


# --- Task 5: path classes, artefact classes, conditional ignore -----------------


def test_v1_fixture_result_gains_schema_version_and_artefacts() -> None:
    result = walk_inventory(FIXTURES / "python-repo")
    assert result["schema_version"] == 2
    assert result["total_files"] == 3
    assert isinstance(result["artefacts"], dict)
    assert set(result["artefacts"]) == {
        "manifest", "lockfile", "runtime_version", "ci", "container", "iac", "sql",
        "notebook", "model_binary", "governance", "build", "config",
    }


@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        ("src/app.py", "source"),
        ("setup.py", "source"),
        ("tests/test_app.py", "tests"),
        ("pkg/test/helper.py", "tests"),
        ("spec/thing_spec.rb", "tests"),
        ("src/__tests__/cart.test.ts", "tests"),
        ("src/api.spec.ts", "tests"),
        ("lib/store_test.go", "tests"),
        ("Domain/OrderTests.cs", "tests"),
        ("Models/Order.g.cs", "generated"),
        ("Forms/Main.designer.cs", "generated"),
        ("Forms/Main.Designer.cs", "generated"),
        ("proto/order_pb2.py", "generated"),
        ("proto/order.pb.go", "generated"),
        ("dist/app.min.js", "generated"),
        ("src/generated/types.ts", "generated"),
        ("api.generated.ts", "generated"),
        ("vendor/lib.js", "vendored"),
        ("src/third_party/x.c", "vendored"),
        ("extern/y.h", "vendored"),
        ("README.md", "docs"),
        ("guide.rst", "docs"),
        ("docs/adr/0001.md", "docs"),
        ("docs/notes.txt", "docs"),
    ],
)
def test_classify_path_table(rel: str, expected: str) -> None:
    assert _classify_path(rel) == expected


def test_classify_path_precedence_vendored_beats_tests() -> None:
    assert _classify_path("vendor/lib/tests/test_x.py") == "vendored"
    assert _classify_path("src/generated/foo.test.ts") == "generated"


def test_classify_path_config_extension() -> None:
    assert _classify_path("qa/check.py") == "source"
    assert _classify_path("qa/check.py", {"tests": ["qa/*"]}) == "tests"


def test_service_py_path_classes(service_py_repo: Path) -> None:
    result = walk_inventory(service_py_repo)
    classes = {entry["path"]: entry["path_class"] for entry in result["files"]}
    assert classes["src/pay/refund.py"] == "source"
    assert classes["setup.py"] == "source"
    assert classes["tests/test_refund.py"] == "tests"
    assert classes["tests/conftest.py"] == "tests"
    assert classes["tests/fixtures/seed.py"] == "tests"
    assert classes["README.md"] == "docs"
    assert classes["docs/adr/0001-ledger.md"] == "docs"
    assert classes["docs/übersicht.md"] == "docs"
    assert result["total_files"] == 16
    assert {e["language"] for e in result["files"]} == {"python", "markdown"}


def test_web_ts_path_classes(web_ts_repo: Path) -> None:
    result = walk_inventory(web_ts_repo)
    classes = {entry["path"]: entry["path_class"] for entry in result["files"]}
    assert classes["src/cart/cart.ts"] == "source"
    assert classes["src/__tests__/cart.test.ts"] == "tests"
    assert classes["src/__tests__/pricing.spec.ts"] == "tests"
    assert classes["src/generated/api-types.ts"] == "generated"
    assert classes["vendor/tiny-emitter.js"] == "vendored"
    assert classes["docs/architecture.md"] == "docs"
    assert result["total_files"] == 16


def test_service_py_artefact_classes(service_py_repo: Path) -> None:
    artefacts = walk_inventory(service_py_repo)["artefacts"]
    paths = {cls: sorted(e["path"] for e in entries) for cls, entries in artefacts.items()}
    assert paths["manifest"] == ["pyproject.toml", "requirements.txt"]
    assert paths["ci"] == [".github/workflows/ci.yml", ".github/workflows/release.yml"]
    assert paths["container"] == ["Dockerfile"]
    assert paths["lockfile"] == []
    entry = next(e for e in artefacts["manifest"] if e["path"] == "pyproject.toml")
    assert list(entry) == [
        "path", "path_class", "loc", "churn", "last_touched", "size_bytes", "skipped_large",
    ]
    assert entry["path_class"] == "source"
    assert entry["loc"] == 8
    assert entry["size_bytes"] > 0
    assert entry["skipped_large"] is False


def test_artefact_classes_synthetic(tmp_path: Path) -> None:
    files = {
        "package.json": '{"name": "x"}\n',
        "package-lock.json": "{}\n",
        ".nvmrc": "20\n",
        ".gitlab-ci.yml": "stages: [test]\n",
        "Makefile": "all:\n\techo hi\n",
        "scripts/deploy.sh": "#!/bin/sh\necho deploy\n",
        "Dockerfile.dev": "FROM alpine\n",
        "docker-compose.yml": "services: {}\n",
        "infra/main.tf": 'provider "aws" {}\n',
        "k8s/dep.yaml": "apiVersion: apps/v1\nkind: Deployment\n",
        "db/migrate/001_init.sql": "create table t (id int);\n",
        "nb/explore.ipynb": json.dumps(
            {
                "cells": [
                    {"cell_type": "markdown", "source": ["# hi"]},
                    {"cell_type": "code", "execution_count": 1, "source": ["x = 1"]},
                    {"cell_type": "code", "execution_count": 2, "source": ["x"]},
                ]
            }
        ),
        "settings.ini": "[main]\nkey = 1\n",
        "CODEOWNERS": "* @team\n",
        ".github/dependabot.yml": "version: 2\n",
        ".tech-debt.yaml": "churn_months: 6\n",
        "bin/tool.dll": "binary",
        "app.py": "print(1)\n",
    }
    for rel, content in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    (tmp_path / "model.pkl").write_bytes(b"\x80\x04binary")
    artefacts = walk_inventory(tmp_path)["artefacts"]
    paths = {cls: sorted(e["path"] for e in entries) for cls, entries in artefacts.items()}
    assert paths["manifest"] == ["package.json"]
    assert paths["lockfile"] == ["package-lock.json"]
    assert paths["runtime_version"] == [".nvmrc"]
    assert paths["ci"] == [".gitlab-ci.yml"]
    assert paths["build"] == ["Makefile", "scripts/deploy.sh"]
    assert paths["container"] == ["Dockerfile.dev", "docker-compose.yml"]
    assert paths["iac"] == ["infra/main.tf", "k8s/dep.yaml"]
    assert paths["sql"] == ["db/migrate/001_init.sql"]
    assert paths["notebook"] == ["nb/explore.ipynb"]
    assert paths["model_binary"] == ["model.pkl"]
    assert paths["config"] == ["settings.ini"]
    assert paths["governance"] == [".github/dependabot.yml", "CODEOWNERS"]
    everything = {p for entries in artefacts.values() for p in (e["path"] for e in entries)}
    assert ".tech-debt.yaml" not in everything
    assert "bin/tool.dll" not in everything
    notebook = artefacts["notebook"][0]
    assert notebook["cells"] == 3
    assert notebook["monotonic_execution"] is True
    model = artefacts["model_binary"][0]
    assert model["lfs_pointer"] is False
    assert model["loc"] == 0


def test_oversized_and_binary_files_are_never_read(tmp_path: Path) -> None:
    """Spec 4.2: over 2 MB or a NUL in the first KB means loc 0, complexity 0, skipped."""
    from inventory import MAX_SCAN_BYTES, _main

    repo = tmp_path / "repo"
    (repo / "data").mkdir(parents=True)
    (repo / "data" / "export.json").write_bytes(b"{}" + b"\n" * (MAX_SCAN_BYTES - 1))
    (repo / "blob.py").write_bytes(b"def go():\n" + b"\x00" * 8 + b"\n    return 1\n")
    (repo / "app.py").write_text("def go():\n    return 1\n", encoding="utf-8")

    result = walk_inventory(repo)
    export = next(e for e in result["artefacts"]["config"] if e["path"] == "data/export.json")
    assert export["size_bytes"] == MAX_SCAN_BYTES + 1
    assert export["skipped_large"] is True
    assert export["loc"] == 0
    blob = next(e for e in result["files"] if e["path"] == "blob.py")
    assert blob["skipped_large"] is True
    assert (blob["loc"], blob["complexity"], blob["max_indent"]) == (0, 0, 0)
    app = next(e for e in result["files"] if e["path"] == "app.py")
    assert app["skipped_large"] is False
    assert (app["loc"], app["complexity"]) == (2, 1)
    assert result["skipped_large_files"] == 2

    assert _main([str(repo), "--workdir", str(tmp_path / "wd")]) == 0


def test_bin_and_build_walked_only_with_a_manifest(tmp_path: Path) -> None:
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "package.json").write_text('{"name": "cli"}\n', encoding="utf-8")
    (tmp_path / "bin" / "cli.js").write_text("console.log(1);\n", encoding="utf-8")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "out.js").write_text("var a = 1;\n", encoding="utf-8")
    result = walk_inventory(tmp_path)
    paths = {e["path"] for e in result["files"]}
    assert "bin/cli.js" in paths
    assert "build/out.js" not in paths
    assert [e["path"] for e in result["artefacts"]["manifest"]] == ["bin/package.json"]


def test_build_dir_under_ordinary_source_dir_is_walked(tmp_path: Path) -> None:
    # internal/build is a real Go package directory (build being a stdlib package
    # name), not build output: its parent "internal" is neither the repository
    # root nor holding a manifest of its own, so it is not conditionally ignored
    # even though "internal/build" has no manifest either.
    (tmp_path / "go.mod").write_text("module example.com/app\n\ngo 1.22\n", encoding="utf-8")
    (tmp_path / "internal" / "build").mkdir(parents=True)
    (tmp_path / "internal" / "build" / "builder.go").write_text(
        "package build\n", encoding="utf-8"
    )
    result = walk_inventory(tmp_path)
    paths = {e["path"] for e in result["files"]}
    assert "internal/build/builder.go" in paths


def test_config_ignore_names_and_globs(tmp_path: Path) -> None:
    for rel in ("legacy_v1/a.py", "tmp/b.py", "src/c.py"):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x = 1\n", encoding="utf-8")
    (tmp_path / ".tech-debt.yaml").write_text('ignore: ["legacy_*", "tmp"]\n', encoding="utf-8")
    result = walk_inventory(tmp_path, config=load_config(tmp_path))
    assert {e["path"] for e in result["files"]} == {"src/c.py"}


def test_config_extends_path_classes(tmp_path: Path) -> None:
    (tmp_path / "qa").mkdir()
    (tmp_path / "qa" / "check.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / ".tech-debt.yaml").write_text(
        "path_classes:\n  tests: ['qa/*']\n", encoding="utf-8"
    )
    result = walk_inventory(tmp_path, config=load_config(tmp_path))
    assert result["files"][0]["path_class"] == "tests"


def test_line_metrics_deep_lines_and_longest_run() -> None:
    text = (
        "def f(a, b, c):\n"
        "    if a:\n"
        "        if b:\n"
        "            if c:\n"
        "                return 1\n"
        "\n"
        "        return 2\n"
        "    return 0\n"
    )
    loc, total, max_indent, deep, longest = _line_metrics(text.splitlines(keepends=True))
    assert (loc, total, max_indent) == (8, 13, 4)
    assert deep == 2  # the two lines at unit 3 and unit 4
    assert longest == 4  # units 2, 3, 4 and (after the blank) 2 again


def test_file_entries_carry_every_v2_key(service_py_repo: Path) -> None:
    entry = walk_inventory(service_py_repo)["files"][0]
    assert list(entry) == [
        "path", "ext", "loc", "mtime", "complexity", "max_indent", "churn",
        "language", "path_class", "hotspot_score", "deep_indent_lines", "longest_indented_run",
        "inline_disables", "last_touched", "authors", "top_author", "top_author_share",
        "top_author_line_share", "bugfix_share", "migration_commits", "flaky_commits",
        "untested_change_share", "mapped_tests", "fan_in_approx", "fan_out_approx",
        "fan_in_mode", "coupling_degree", "skipped_large",
    ]


# --- Task 6: git pass ------------------------------------------------------------


def test_git_pass_per_file_history_fields(service_py_repo: Path) -> None:
    result = walk_inventory(service_py_repo, churn_months=240)
    assert result["git_available"] is True
    files = {e["path"]: e for e in result["files"]}
    refund = files["src/pay/refund.py"]
    assert refund["churn"] == 7
    assert refund["authors"] == 1
    assert refund["top_author"] == "ada@example.com"
    assert refund["top_author_share"] == 1.0
    assert refund["bugfix_share"] == pytest.approx(2 / 7, abs=0.001)
    assert refund["untested_change_share"] == pytest.approx(4 / 7, abs=0.001)
    assert refund["last_touched"].startswith("2026-06-22")
    ledger = files["src/pay/ledger.py"]
    assert ledger["churn"] == 7
    assert ledger["authors"] == 3
    assert ledger["top_author"] == "ada@example.com"
    assert ledger["top_author_share"] == pytest.approx(5 / 7, abs=0.001)
    gateway = files["src/pay/gateway.py"]
    assert gateway["churn"] == 2
    assert gateway["authors"] == 1
    assert gateway["migration_commits"] == 1
    assert gateway["mapped_tests"] == []
    assert files["tests/test_ledger.py"]["flaky_commits"] == 1
    assert files["src/pay/legacy_export.py"]["churn"] == 1


def test_git_pass_authors_keyed_by_email_and_bots_dropped(service_py_repo: Path) -> None:
    result = walk_inventory(service_py_repo, churn_months=240)
    git = result["git"]
    assert [a["email"] for a in git["authors"]] == [
        "ada@example.com", "linus@example.com", "grace@example.com",
    ]
    assert [a["commits"] for a in git["authors"]] == [7, 5, 3]
    assert git["authors"][0]["name"] == "Ada Lovelace"
    assert git["authors"][0]["last_active"].startswith("2026-06-22")
    assert git["commits_in_window"] == 16
    assert git["bulk_commits_excluded"] == 0
    assert git["mailmap_present"] is False
    req = next(e for e in result["artefacts"]["manifest"] if e["path"] == "requirements.txt")
    assert req["churn"] == 2  # the bot commit still counts as churn
    assert req["last_touched"].startswith("2026-01-15")
    assert "git" in result["signal_sources"]


def test_git_pass_head_join_drops_deleted_file(service_py_repo: Path) -> None:
    result = walk_inventory(service_py_repo, churn_months=240)
    assert "src/pay/old_helper.py" not in {e["path"] for e in result["files"]}
    assert result["git"]["commits_in_window"] == 16  # the deletion commit is still counted


def test_git_pass_non_ascii_path(service_py_repo: Path) -> None:
    files = {e["path"]: e for e in walk_inventory(service_py_repo, churn_months=240)["files"]}
    assert files["docs/übersicht.md"]["churn"] == 1
    assert files["docs/übersicht.md"]["last_touched"].startswith("2024-10-05")


def test_git_pass_window_excludes_old_commits(service_py_repo: Path) -> None:
    result = walk_inventory(service_py_repo, churn_months=1)
    assert result["git_available"] is True
    assert all(e["churn"] == 0 for e in result["files"])
    assert result["git"]["commits_in_window"] == 0
    assert result["hotspots"] == []


def test_branches_and_tags(service_py_repo: Path) -> None:
    git = walk_inventory(service_py_repo, churn_months=240)["git"]
    branches = {b["name"]: b for b in git["branches"]}
    hotfix = branches["hotfix/ledger-rounding"]
    assert hotfix["merged"] is False
    assert hotfix["ref"] == "refs/heads/hotfix/ledger-rounding"
    assert hotfix["last_commit"].startswith("2026-04-10")
    assert branches["main"]["merged"] is True
    assert [t["name"] for t in git["tags"]] == ["v0.1.0", "v0.2.0"]
    assert git["tags"][0]["date"].startswith("2024-10-05")
    assert git["tags"][1]["date"].startswith("2026-02-20")


def test_list_branches_merged_state_and_null_when_unavailable(
    service_py_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One bounded ``--merged`` pass decides every ref; a failed pass gives every ref null."""
    import git_history
    from git_history import list_branches

    branches = list_branches(service_py_repo)
    assert branches is not None
    assert {b["name"]: b["merged"] for b in branches} == {
        "hotfix/ledger-rounding": False, "main": True,
    }
    assert all(set(b) == {"name", "ref", "last_commit", "merged"} for b in branches)

    real_run_git = git_history.run_git
    calls: list[Sequence[str]] = []

    def without_merged(root: Path, args: Sequence[str]) -> str | None:
        calls.append(args)
        if any(str(arg).startswith("--merged") for arg in args):
            return None
        return real_run_git(root, args)

    monkeypatch.setattr(git_history, "run_git", without_merged)
    fallback = list_branches(service_py_repo)
    assert fallback is not None
    assert [b["name"] for b in fallback] == [b["name"] for b in branches]
    assert all(b["merged"] is None for b in fallback)
    assert len(calls) == 2  # one ref listing and one --merged pass, whatever the branch count


def test_parse_branch_refs_skips_symref() -> None:
    from git_history import parse_branch_refs

    stdout = (
        "refs/heads/main\tmain\t\t2026-01-01T09:00:00Z\taaa\n"
        "refs/remotes/origin/HEAD\torigin/HEAD\trefs/remotes/origin/main"
        "\t2026-01-01T09:00:00Z\taaa\n"
        "refs/remotes/origin/main\torigin/main\t\t2026-01-01T09:00:00Z\taaa\n"
    )
    refs = parse_branch_refs(stdout)
    assert [r["name"] for r in refs] == ["main", "origin/main"]
    assert refs[1]["ref"] == "refs/remotes/origin/main"
    assert refs[0]["sha"] == "aaa"


def test_parse_log_tab_in_subject_and_non_ascii_path() -> None:
    from git_history import parse_log

    stdout = (
        "\x1eabc\tAda\tada@example.com\t2024-09-10T10:00:00Z\tfeat: a\tb\n"
        "\nsrc/app.py\nsrc/naïve.py\n"
        "\x1edef\tGrace\tgrace@example.com\t2025-03-01T09:00:00Z\tfix: r\n\nsrc/app.py\n"
    )
    commits = parse_log(stdout)
    assert [c.sha for c in commits] == ["abc", "def"]
    assert commits[0].subject == "feat: a\tb"
    assert commits[0].files == ["src/app.py", "src/naïve.py"]
    assert commits[1].author_email == "grace@example.com"


def test_is_bot_matches_default_list() -> None:
    from config import DEFAULTS
    from git_history import is_bot

    bots = DEFAULTS["bot_authors"]
    assert is_bot("dependabot[bot]", bots)
    assert is_bot("github-actions", bots)
    assert is_bot("Claude", bots)
    assert not is_bot("Ada Lovelace", bots)


def test_bulk_commits_excluded_from_churn(tmp_path: Path) -> None:
    from make_history import replay_history

    files_root = tmp_path / "files"
    files_root.mkdir()
    bulk = "\n".join(f"      f{i}.py: 'x = {i}'" for i in range(60))
    history = tmp_path / "history.yaml"
    history.write_text(
        "commits:\n"
        "  - author: 'Bulk Bob <bob@example.com>'\n"
        "    date: '2026-01-01T09:00:00+00:00'\n"
        "    subject: 'chore: reformat everything'\n"
        f"    files:\n{bulk}\n"
        "  - author: 'Ada Lovelace <ada@example.com>'\n"
        "    date: '2026-02-01T09:00:00+00:00'\n"
        "    subject: 'feat: touch one'\n"
        "    files:\n      f0.py: 'x = 100'\n",
        encoding="utf-8",
    )
    for i in range(60):
        (files_root / f"f{i}.py").write_text(f"x = {i}" if i else "x = 100", encoding="utf-8")
    repo = replay_history(history, files_root, tmp_path / "repo")
    result = walk_inventory(repo, churn_months=240)
    files = {e["path"]: e for e in result["files"]}
    assert files["f0.py"]["churn"] == 1
    assert files["f1.py"]["churn"] == 0
    assert result["git"]["bulk_commits_excluded"] == 1
    assert result["git"]["commits_in_window"] == 2
    assert [a["email"] for a in result["git"]["authors"]] == ["ada@example.com"]


def test_no_git_shape(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    result = walk_inventory(tmp_path)
    assert result["git_available"] is False
    entry = result["files"][0]
    assert entry["churn"] == 0
    assert entry["last_touched"] is None
    assert entry["authors"] is None
    assert entry["top_author_share"] is None
    assert entry["top_author_line_share"] is None
    assert entry["untested_change_share"] is None
    assert result["hotspots"] == []
    assert result["git"] == {
        "authors": [], "branches": [], "tags": [], "commits_in_window": 0,
        "bulk_commits_excluded": 0, "mailmap_present": False,
    }
    assert result["signal_sources"] == {}


def test_blame_top_share_on_corpus(service_py_repo: Path) -> None:
    from config import DEFAULTS
    from git_history import blame_top_share

    share, email = blame_top_share(service_py_repo, "src/pay/refund.py", DEFAULTS["bot_authors"])
    assert share == 1.0
    assert email == "ada@example.com"
    share, _ = blame_top_share(service_py_repo, "src/pay/ledger.py", DEFAULTS["bot_authors"])
    assert share is not None and share < 1.0
    assert blame_top_share(service_py_repo, "does/not/exist.py", []) == (None, None)


# --- Task 7: change coupling -----------------------------------------------------


def test_coupling_pairs_on_service_py(service_py_repo: Path) -> None:
    from inventory import build_all

    inventory, coupling = build_all(service_py_repo, churn_months=240)
    pairs = {(p["a"], p["b"]): p for p in coupling["pairs"]}
    key = ("src/pay/ledger.py", "src/pay/refund.py")
    assert key in pairs
    assert pairs[key]["shared_commits"] == 5
    assert pairs[key]["ratio"] == pytest.approx(5 / 7, abs=0.001)
    assert pairs[key]["cross_directory"] is False
    assert ("src/pay/ledger.py", "src/pay/models.py") not in pairs  # shared 2 < min_shared 3
    assert not any("tests/" in p["a"] or "tests/" in p["b"] for p in coupling["pairs"])
    assert coupling["degree"] == {"src/pay/ledger.py": 1, "src/pay/refund.py": 1}
    files = {e["path"]: e for e in inventory["files"]}
    assert files["src/pay/refund.py"]["coupling_degree"] == 1
    assert files["src/pay/gateway.py"]["coupling_degree"] == 0
    assert coupling["schema_version"] == 2
    assert (coupling["min_shared"], coupling["min_ratio"], coupling["bulk_threshold"]) == (
        3, 0.3, 50,
    )
    assert coupling["fan_in_mode"] == "auto"
    assert list(coupling) == [
        "schema_version", "min_shared", "min_ratio", "bulk_threshold", "fan_in_mode",
        "pairs", "degree", "cycles", "directories", "unstable_edges",
    ]


def test_coupling_pair_on_web_ts(web_ts_repo: Path) -> None:
    from inventory import build_all

    _, coupling = build_all(web_ts_repo, churn_months=240)
    pairs = {(p["a"], p["b"]): p for p in coupling["pairs"]}
    key = ("src/api/client-admin.ts", "src/api/client.ts")
    assert pairs[key]["shared_commits"] == 4
    assert pairs[key]["ratio"] == pytest.approx(4 / 4.5, abs=0.001)
    assert len(coupling["pairs"]) == 1


def test_coupling_thresholds_come_from_config(service_py_repo: Path) -> None:
    from config import DEFAULTS, deep_merge
    from inventory import build_all

    cfg = deep_merge(DEFAULTS, {"coupling": {"min_shared": 6}})
    _, coupling = build_all(service_py_repo, churn_months=240, config=cfg)
    assert coupling["pairs"] == []
    assert coupling["degree"] == {}
    assert coupling["min_shared"] == 6


def test_change_coupling_unit_ratio_bulk_and_cross_directory() -> None:
    from git_history import Commit, change_coupling

    def commit(sha: str, files: list[str]) -> Commit:
        return Commit(sha, "A", "a@example.com", "2026-01-01T00:00:00Z", "s", files)

    # threshold is 3 so only the 4-file "bulk" commit below is excluded; commit
    # "3" (3 files) stays under it and is counted.
    commits = [
        commit("1", ["x/a.py", "y/b.py"]),
        commit("2", ["x/a.py", "y/b.py"]),
        commit("3", ["x/a.py", "y/b.py", "x/c.py"]),
        commit("4", ["x/a.py", "x/c.py"]),
        commit("5", ["x/a.py", "x/c.py"]),
        *[commit(str(n), ["x/c.py"]) for n in range(10, 30)],
        commit("bulk", ["x/a.py", "y/b.py", "x/d.py", "x/e.py"]),
    ]
    present = {"x/a.py", "y/b.py", "x/c.py", "x/d.py", "x/e.py"}
    pairs, degree = change_coupling(
        commits, present, min_shared=3, min_ratio=0.30, bulk_threshold=3
    )
    assert [(p["a"], p["b"]) for p in pairs] == [("x/a.py", "y/b.py")]
    assert pairs[0]["shared_commits"] == 3
    assert pairs[0]["ratio"] == pytest.approx(3 / 4, abs=0.001)  # a 5 commits, b 3
    assert pairs[0]["cross_directory"] is True
    # a and c share 3 commits but c has 23, so ratio 3 / 14 is below 0.30
    assert degree == {"x/a.py": 1, "y/b.py": 1}


def test_coupling_empty_without_git(tmp_path: Path) -> None:
    from inventory import build_all

    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    inventory, coupling = build_all(tmp_path)
    assert inventory["git_available"] is False
    assert coupling["pairs"] == []
    assert coupling["degree"] == {}
    assert coupling["cycles"] == []


# --- Task 8: reference graph ----------------------------------------------------


def test_fan_in_on_web_ts_matches_hand_count(web_ts_repo: Path) -> None:
    from inventory import build_all

    inventory, _ = build_all(web_ts_repo, churn_months=240)
    files = {e["path"]: e for e in inventory["files"]}
    expected = {
        # stock, checkout, index, cart.test, plus pricing.spec (its "../cart/..." path matches too)
        "src/cart/cart.ts": 5,
        "src/cart/pricing.ts": 3,  # cart, checkout, pricing.spec
        "src/cart/stock.ts": 1,  # pricing
        "src/checkout/checkout.ts": 1,  # index
        "src/util/format-legacy.ts": 1,  # checkout: the deprecated helper still has a caller
        "src/util/format.ts": 1,  # format-legacy
        "src/flags.ts": 3,  # checkout, client, client-admin
        "src/api/client.ts": 0,
        "src/api/client-admin.ts": 0,
    }
    for path, fan_in in expected.items():
        assert files[path]["fan_in_approx"] == fan_in, path
        assert files[path]["fan_in_mode"] == "import-lines", path
    assert files["src/index.ts"]["fan_in_approx"] is None  # package and stoplist name
    assert files["src/index.ts"]["fan_out_approx"] == 2
    assert files["src/checkout/checkout.ts"]["fan_out_approx"] == 4
    assert files["src/__tests__/cart.test.ts"]["fan_in_approx"] is None
    assert files["src/__tests__/cart.test.ts"]["fan_out_approx"] is None
    assert files["vendor/tiny-emitter.js"]["fan_out_approx"] is None


def test_three_file_cycle_found_in_web_ts(web_ts_repo: Path) -> None:
    from inventory import build_all

    _, coupling = build_all(web_ts_repo, churn_months=240)
    assert coupling["cycles"] == [
        {
            "members": ["src/cart/cart.ts", "src/cart/pricing.ts", "src/cart/stock.ts"],
            "approximate": True,
            "source": "import-lines",
            "lead_only": True,
        }
    ]


def test_service_py_fan_in_ambiguity_and_no_cycle(service_py_repo: Path) -> None:
    from inventory import build_all

    inventory, coupling = build_all(service_py_repo, churn_months=240)
    assert coupling["cycles"] == []
    files = {e["path"]: e for e in inventory["files"]}
    # tests/test_refund.py imports the module; tests/conftest.py's `Refund` class import also
    # matches the stem, which is the documented imprecision of stem matching
    assert files["src/pay/refund.py"]["fan_in_approx"] == 2
    assert files["src/pay/ledger.py"]["fan_in_approx"] == 2  # refund, tests/test_ledger.py
    assert files["src/pay/gateway.py"]["fan_in_approx"] == 1  # refund
    assert files["src/pay/legacy_export.py"]["fan_in_approx"] == 0
    assert files["src/pay/refund.py"]["fan_out_approx"] == 2  # ledger, gateway
    for ambiguous in ("src/pay/__init__.py", "src/pay/models.py", "src/pay/utils.py", "setup.py"):
        assert files[ambiguous]["fan_in_approx"] is None, ambiguous


def test_go_import_block_continuation(mixed_decoys_repo: Path) -> None:
    from inventory import build_all

    inventory, coupling = build_all(mixed_decoys_repo, churn_months=240)
    files = {e["path"]: e for e in inventory["files"]}
    # lookup is referenced only inside store.go's multi-line `import (` block
    assert files["internal/lookup/lookup.go"]["fan_in_approx"] == 1
    # store.go: main.go's import block only. `package` was removed from
    # IMPORT_LINE_RE (spec amendment; a package declaration never references
    # another file), so store_test.go's own `package store` line no longer
    # counts as an edge into store.go. See task-8-report.md fix round 1.
    assert files["internal/store/store.go"]["fan_in_approx"] == 1
    assert files["internal/dispatch/dispatch.go"]["fan_in_approx"] == 1
    assert files["internal/flags/flags.go"]["fan_in_approx"] == 1
    # httpc.go: main.go's import block only, for the same reason as store.go above
    assert files["internal/httpc/httpc.go"]["fan_in_approx"] == 1
    assert files["internal/httpc/httpc_safe.go"]["fan_in_approx"] == 0
    # internal/build/builder.go is a planted god-classes decoy; CONDITIONAL_IGNORE
    # was amended (spec 4.2, fix round 1) so a nested build/ under an ordinary
    # source directory without its own manifest is still walked. main.go's import
    # of "example.com/app/internal/build" tokenizes to "build", which is the
    # package directory name, not the "builder" stem, so it still is never mapped
    # to builder.go (spec 4.2) and fan_in_approx stays 0.
    assert files["internal/build/builder.go"]["fan_in_approx"] == 0
    assert files["internal/build/builder.go"]["fan_out_approx"] == 0
    assert files["cmd/app/main.go"]["fan_in_approx"] is None
    assert files["cmd/app/main.go"]["fan_out_approx"] == 4
    assert coupling["cycles"] == []


def test_shared_and_short_stems_are_ambiguous(tmp_path: Path) -> None:
    from inventory import build_all

    for rel, content in {
        "a/report.py": "x = 1\n",
        "b/report.py": "y = 2\n",
        "lib/db.py": "z = 3\n",
        "runner.py": "from a import report\nfrom lib import db\n",
    }.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    inventory, _ = build_all(tmp_path)
    files = {e["path"]: e for e in inventory["files"]}
    assert files["a/report.py"]["fan_in_approx"] is None
    assert files["b/report.py"]["fan_in_approx"] is None
    assert files["lib/db.py"]["fan_in_approx"] is None  # stem shorter than 4
    assert files["runner.py"]["fan_in_approx"] == 0
    assert files["runner.py"]["fan_out_approx"] == 0


def test_anywhere_fallback_is_labelled(tmp_path: Path) -> None:
    from config import DEFAULTS, deep_merge
    from inventory import build_all

    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "renderer.php").write_text(
        "<?php\nclass Renderer {\n    public function draw() {}\n}\n", encoding="utf-8"
    )
    (tmp_path / "webapp.php").write_text(
        "<?php\n$r = new Renderer();\n$r->draw();\n", encoding="utf-8"
    )
    inventory, coupling = build_all(tmp_path)
    files = {e["path"]: e for e in inventory["files"]}
    assert files["lib/renderer.php"]["fan_in_approx"] == 1
    assert files["lib/renderer.php"]["fan_in_mode"] == "anywhere"
    assert files["webapp.php"]["fan_in_approx"] == 0
    assert coupling["cycles"] == []
    strict = deep_merge(DEFAULTS, {"fan_in": {"mode": "import-lines"}})
    inventory, _ = build_all(tmp_path, config=strict)
    files = {e["path"]: e for e in inventory["files"]}
    assert files["lib/renderer.php"]["fan_in_approx"] == 0
    assert files["lib/renderer.php"]["fan_in_mode"] == "import-lines"


def test_directories_unstable_edges_and_scc_size_bounds(tmp_path: Path) -> None:
    from inventory import build_all

    for rel, content in {
        "app/alpha.py": "from core import engine\n",
        "app/bravo.py": "from core import engine\n",
        "app/charlie.py": "from core import engine\n",
        "core/engine.py": "from plugins import loader\n",
        "plugins/loader.py": "from app import alpha, bravo, charlie\n",
        "zeta/omega.py": "from core import engine\n",
    }.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    _, coupling = build_all(tmp_path)
    dirs = {d["path"]: d for d in coupling["directories"]}
    assert dirs["app"]["files"] == 3
    assert (dirs["app"]["fan_in"], dirs["app"]["fan_out"]) == (3, 3)
    assert dirs["app"]["instability"] == 0.5
    assert (dirs["core"]["fan_in"], dirs["core"]["fan_out"]) == (4, 1)
    assert dirs["core"]["instability"] == 0.2
    assert (dirs["plugins"]["fan_in"], dirs["plugins"]["fan_out"]) == (1, 3)
    assert dirs["plugins"]["instability"] == 0.75
    assert dirs["zeta"]["instability"] == 1.0
    assert coupling["unstable_edges"] == [
        {"from": "core", "to": "plugins", "from_instability": 0.2, "to_instability": 0.75}
    ]
    assert [c["members"] for c in coupling["cycles"]] == [
        ["app/alpha.py", "app/bravo.py", "app/charlie.py", "core/engine.py", "plugins/loader.py"]
    ]


def test_scc_larger_than_five_is_not_a_lead(tmp_path: Path) -> None:
    from inventory import build_all

    names = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot"]
    for index, name in enumerate(names):
        nxt = names[(index + 1) % len(names)]
        (tmp_path / f"{name}.py").write_text(f"import {nxt}\n", encoding="utf-8")
    _, coupling = build_all(tmp_path)
    assert coupling["cycles"] == []


def test_tarjan_scc_unit() -> None:
    from reference_graph import tarjan_scc

    adjacency = {"a": {"b"}, "b": {"c"}, "c": {"a"}, "d": {"a"}, "e": set()}
    components = tarjan_scc(adjacency)
    assert ["a", "b", "c"] in components
    assert ["d"] in components
    assert ["e"] in components
    assert len(components) == 3


def test_logical_lines_and_import_lines_unit() -> None:
    from reference_graph import import_lines, logical_lines

    go = 'package x\n\nimport (\n\t"fmt"\n\n\t"example.com/app/internal/store"\n)\n\nfunc f() {}\n'
    joined = logical_lines(go)
    assert any(line.startswith("import (") and "store" in line for line in joined)
    py = "from pay import (\n    ledger,\n    gateway,\n)\nx = call(a,\n    b)\n"
    assert import_lines(py) == ["from pay import ( ledger, gateway, )"]
    ts = 'const m = await import("./lazy");\nconst r = require("./req");\nlet x = 1;\n'
    assert len(import_lines(ts)) == 2
    assert import_lines("x = 1\ny = 2\n") == []


# --- Task 9: band, score, blame, mapping, docs, tests block, CLI -------------------


def test_hotspot_score_band_and_blame_on_service_py(service_py_repo: Path) -> None:
    result = walk_inventory(service_py_repo, churn_months=240)
    files = {e["path"]: e for e in result["files"]}
    assert result["hotspots"][0]["path"] == "src/pay/refund.py"
    assert set(result["hotspots"][0]) == {"path", "churn", "complexity", "loc", "score"}
    assert files["src/pay/refund.py"]["hotspot_score"] == result["hotspots"][0]["score"]
    assert files["src/pay/refund.py"]["hotspot_score"] == 100.0
    assert files["setup.py"]["hotspot_score"] == 0.0
    band = result["hotspot_band"]
    assert band[0] == "src/pay/refund.py"
    assert "src/pay/ledger.py" in band
    assert len(band) == 5  # 8 source files: ceil(0.8) = 1, floored to min 5
    assert all(files[p]["path_class"] == "source" for p in band)
    assert "setup.py" not in band  # score 0 never enters the band
    assert files["src/pay/refund.py"]["top_author_line_share"] == 1.0
    ledger_share = files["src/pay/ledger.py"]["top_author_line_share"]
    assert ledger_share is not None and ledger_share < 1.0
    assert files["tests/test_refund.py"]["top_author_line_share"] is None


def test_hotspot_band_bounds() -> None:
    from inventory import FileEntry, _hotspot_band

    def entries(count: int) -> list[FileEntry]:
        out: list[FileEntry] = []
        for index in range(count):
            entry = FileEntry(f"f{index}.py", ".py", 1, 0.0, 1, 1, 1, language="python")
            entry.hotspot_score = float(count - index)
            out.append(entry)
        return out

    band_cfg = {"fraction": 0.10, "min": 5, "max": 50}
    assert len(_hotspot_band(entries(600), band_cfg)) == 50
    assert len(_hotspot_band(entries(200), band_cfg)) == 20
    assert len(_hotspot_band(entries(30), band_cfg)) == 5
    assert _hotspot_band(entries(3), band_cfg) == ["f0.py", "f1.py", "f2.py"]
    zero = entries(10)
    for entry in zero:
        entry.hotspot_score = 0.0
    assert _hotspot_band(zero, band_cfg) == []
    tests_only = entries(10)
    for entry in tests_only:
        entry.path_class = "tests"
    assert _hotspot_band(tests_only, band_cfg) == []


def test_test_mapping_across_seven_conventions(tmp_path: Path) -> None:
    pairs = {
        "src/alpha.py": "tests/test_alpha.py",
        "src/bravo.go": "src/bravo_test.go",
        "src/charlie.ts": "src/__tests__/charlie.test.ts",
        "src/delta.ts": "spec/delta.spec.ts",
        "lib/echo.rb": "spec/echo_spec.rb",
        "src/Foxtrot.java": "test/FoxtrotTest.java",
        "src/Golf.cs": "tests/GolfTests.cs",
    }
    for rel in [*pairs, *pairs.values(), "src/hotel.py"]:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x = 1\n", encoding="utf-8")
    files = {e["path"]: e for e in walk_inventory(tmp_path)["files"]}
    for source, test in pairs.items():
        assert files[source]["mapped_tests"] == [test], source
        assert files[test]["mapped_tests"] == []
    assert files["src/hotel.py"]["mapped_tests"] == []


def test_tests_block_on_corpus(service_py_repo: Path, web_ts_repo: Path) -> None:
    service = walk_inventory(service_py_repo, churn_months=240)["tests"]
    assert service == {
        "test_to_source_ratio": 0.5,
        "coverage_gate": ["pyproject.toml"],
        "ci_retry_config": [],
    }
    web = walk_inventory(web_ts_repo, churn_months=240)["tests"]
    assert web["test_to_source_ratio"] == 0.2
    assert web["coverage_gate"] == ["package.json"]
    assert web["ci_retry_config"] == [".github/workflows/ci.yml"]


def test_docs_block_on_service_py(service_py_repo: Path) -> None:
    docs = walk_inventory(service_py_repo, churn_months=240)["docs"]
    assert docs["readme_present"] is True
    assert docs["readme_loc"] == 10
    assert docs["contributing_present"] is False
    assert docs["adr_dir_present"] is True
    assert docs["changelog_present"] is True
    assert docs["changelog_last_commit"].startswith("2024-10-05")
    assert docs["latest_tag"] == "v0.2.0"
    assert docs["latest_tag_date"].startswith("2026-02-20")
    assert docs["dangling_refs"] == [
        {"file": "README.md", "line": 10, "token": "src/pay/exporter.py"}
    ]
    # README last touched 2024-08-15, newest source (refund.py) 2026-06-22
    assert docs["stale_vs_code_days"]["README.md"] == 676
    assert docs["stale_vs_code_days"]["docs/adr/0001-ledger.md"] == 625


def test_doc_newer_than_the_code_is_zero_days_stale(tmp_path: Path) -> None:
    """stale_vs_code_days is how far a doc lags the code, never the distance either way."""
    history = tmp_path / "history.yaml"
    history.write_text(
        yaml.safe_dump({
            "commits": [
                {"author": "Ada Lovelace <ada@example.com>",
                 "date": "2026-01-05T09:00:00+00:00", "subject": "add the module",
                 "files": {"src/app.py": "def go():\n    return 1\n", "README.md": "# app\n"}},
                {"author": "Ada Lovelace <ada@example.com>",
                 "date": "2026-03-20T09:00:00+00:00", "subject": "document the module",
                 "files": {"README.md": "# app\n\nIt returns one.\n"}},
            ]
        }),
        encoding="utf-8",
    )
    repo = replay_history(history, tmp_path, tmp_path / "repo")
    docs = walk_inventory(repo, churn_months=240)["docs"]
    assert docs["stale_vs_code_days"] == {"README.md": 0}


def test_docs_block_on_web_ts_and_mixed(web_ts_repo: Path, mixed_decoys_repo: Path) -> None:
    web = walk_inventory(web_ts_repo, churn_months=240)["docs"]
    assert web["dangling_refs"] == []  # `src/cart` and `src/checkout` resolve as directories
    assert web["adr_dir_present"] is False
    mixed = walk_inventory(mixed_decoys_repo, churn_months=240)["docs"]
    assert mixed["dangling_refs"] == []  # `payments.killswitch` is not path-like
    assert mixed["changelog_present"] is False


def test_docs_block_without_git(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# x\n\nSee `lib/gone.py`.\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    docs = walk_inventory(tmp_path)["docs"]
    assert docs["readme_present"] is True
    assert docs["readme_loc"] == 3
    assert docs["changelog_last_commit"] is None
    assert docs["latest_tag"] is None
    assert docs["latest_tag_date"] is None
    assert docs["dangling_refs"] == [{"file": "README.md", "line": 3, "token": "lib/gone.py"}]
    assert docs["stale_vs_code_days"] == {"README.md": None}


def test_tooling_blocks(tmp_path: Path, web_ts_repo: Path) -> None:
    web = walk_inventory(web_ts_repo, churn_months=240)
    assert web["lint_config"] == [".eslintrc.json", "tslint.json"]
    assert web["boundary_tooling"] == []
    (tmp_path / "pyproject.toml").write_text(
        "[tool.ruff]\nline-length = 100\n\n[tool.importlinter]\nroot_package = 'x'\n",
        encoding="utf-8",
    )
    (tmp_path / ".importlinter").write_text("[importlinter]\n", encoding="utf-8")
    (tmp_path / "x.py").write_text("x = 1\n", encoding="utf-8")
    result = walk_inventory(tmp_path)
    assert result["boundary_tooling"] == [".importlinter", "pyproject.toml"]
    assert result["lint_config"] == ["pyproject.toml"]


def test_top_level_key_order_and_inline_disables(service_py_repo: Path) -> None:
    result = walk_inventory(service_py_repo, churn_months=240)
    assert list(result) == [
        "schema_version", "root", "total_files", "total_loc", "languages", "git_available",
        "churn_window_months", "hotspots", "hotspot_band", "files", "artefacts",
        "skipped_large_files", "docs", "tests", "git", "boundary_tooling", "lint_config",
        "signal_sources",
    ]
    assert result["skipped_large_files"] == 0
    assert all(e["inline_disables"] == 0 for e in result["files"])


def test_cli_writes_both_files_under_workdir(service_py_repo: Path, tmp_path: Path) -> None:
    from inventory import _main

    workdir = tmp_path / "wd"
    assert _main([str(service_py_repo), "--workdir", str(workdir), "--churn-months", "240"]) == 0
    inv_bytes = (workdir / "inventory.json").read_bytes()
    cpl_bytes = (workdir / "coupling.json").read_bytes()
    assert b"\r\n" not in inv_bytes and b"\r\n" not in cpl_bytes
    inventory = json.loads(inv_bytes)
    coupling = json.loads(cpl_bytes)
    assert inventory["schema_version"] == 2 and coupling["schema_version"] == 2
    assert inventory["churn_window_months"] == 240
    assert len(coupling["pairs"]) == 1


def test_cli_out_flag_keeps_v1_behaviour(service_py_repo: Path, tmp_path: Path) -> None:
    from inventory import _main

    out = tmp_path / "v1" / "inv.json"
    assert _main([str(service_py_repo), "--out", str(out)]) == 0
    assert out.is_file()
    assert not (tmp_path / "v1" / "coupling.json").exists()
    assert json.loads(out.read_bytes())["total_files"] == 16


def test_cli_reads_config_from_root(service_py_repo: Path, tmp_path: Path) -> None:
    import shutil

    from inventory import _main

    repo = tmp_path / "copy"
    shutil.copytree(service_py_repo, repo)
    (repo / ".tech-debt.yaml").write_text("churn_months: 240\n", encoding="utf-8")
    workdir = tmp_path / "wd"
    assert _main([str(repo), "--workdir", str(workdir)]) == 0
    inventory = json.loads((workdir / "inventory.json").read_bytes())
    assert inventory["churn_window_months"] == 240
    assert inventory["total_files"] == 16  # .tech-debt.yaml is neither a file nor an artefact
