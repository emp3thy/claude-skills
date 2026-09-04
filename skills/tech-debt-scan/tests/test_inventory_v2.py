"""inventory.py v2: classes, git pass, coupling, graph, band, mapping, docs (spec 4.2)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from config import load_config
from inventory import _classify_path, _line_metrics, walk_inventory

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
    assert set(entry) >= {"path", "loc", "churn", "last_touched", "size_bytes"}
    assert entry["loc"] == 8
    assert entry["size_bytes"] > 0


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
        "fan_in_mode", "coupling_degree",
    ]
