from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from dd_common import read_json, write_json
from dd_manifests import entry_points, targets
from dd_patterns import Name, run, scan, scan_files

_IDENTITY = ("-c", "user.name=Fixture", "-c", "user.email=fixture@example.com",
             "-c", "commit.gpgsign=false")


def _scan(files: dict[str, str]) -> list[Name]:
    return scan(sorted(files), files.get)


def _of(names: list[Name], kind: str) -> set[tuple[str, str | None, bool]]:
    return {(n["name"], n["parent"], n["hidden"]) for n in names if n["kind"] == kind}


def _line(names: list[Name], kind: str, name: str) -> int:
    return next(n["line"] for n in names if n["kind"] == kind and n["name"] == name)


ARGPARSE = """\
import argparse


def _add_init_flags(p):
    p.add_argument("--template")


def build():
    parser = argparse.ArgumentParser(prog="tool")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("target")
    parsers = parser.add_subparsers(dest="cmd")
    parsers.add_parser("serve").add_argument(
        "--port", type=int)
    init = parsers.add_parser(
        "init", aliases=["setup"])
    init.add_argument("--force")
    group = init.add_mutually_exclusive_group()
    group.add_argument("--quiet")
    _add_init_flags(init)
    return parser
"""


def test_argparse_commands_flags_and_parents() -> None:
    names = _scan({"cli.py": ARGPARSE})
    assert _of(names, "command") == {("serve", None, False), ("init", None, False),
                                     ("setup", None, False)}
    assert _of(names, "flag") == {
        ("-v", None, False), ("--verbose", None, False), ("--port", "serve", False),
        ("--force", "init", False), ("--quiet", "init", False),
        # a parser passed into a helper: the receiver is a parameter, so no parent
        ("--template", None, False),
    }
    assert _line(names, "flag", "--port") == 14
    assert _line(names, "command", "init") == 16
    assert all(n["file"] == "cli.py" for n in names)


def test_hidden_flag_suppress_and_underscore() -> None:
    src = """\
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--debug-dump",
                    help=argparse.SUPPRESS)
parser.add_argument("--_internal")
parser.add_argument("--color")
sub = parser.add_subparsers()
sub.add_parser("_selftest")




parser.add_argument("--legacy")  # DEPRECATED: use --color
parser.add_argument("--plain")
"""
    names = _scan({"main.py": src})
    flags = _of(names, "flag")
    assert ("--debug-dump", None, True) in flags
    assert ("--_internal", None, True) in flags
    assert ("--color", None, False) in flags
    assert ("--legacy", None, True) in flags
    assert ("--plain", None, True) in flags  # within three lines of the deprecation word
    assert _of(names, "command") == {("_selftest", None, True)}


def test_click_and_typer_commands() -> None:
    src = """\
import click
import typer

app = typer.Typer()


@click.group()
def cli():
    pass


@cli.command(name="sync-all")
@click.option("--dry-run", "-n", is_flag=True)
@click.option("--secret", hidden=True)
def sync(dry_run, secret):
    pass


@click.command()
@click.argument("path")
def export(path):
    pass


@app.command()
def doctor(
    fix: bool = typer.Option(False, "--fix"),
):
    pass
"""
    names = _scan({"cmds.py": src})
    assert _of(names, "command") == {("cli", None, False), ("sync-all", None, False),
                                     ("export", None, False), ("doctor", None, False)}
    assert _of(names, "flag") == {("--dry-run", "sync-all", False),
                                  ("-n", "sync-all", False),
                                  ("--secret", "sync-all", True)}
    assert _line(names, "command", "sync-all") == 12
    assert _line(names, "command", "doctor") == 26


def test_env_direct_reads_and_prefix_family() -> None:
    config = """\
import os

HOME = os.getenv("SVC_HOME")
TOKEN = os.environ["API_TOKEN"]
LEVEL = os.environ.get(
    "SVC_LOG_LEVEL", "info")
PATH = os.getenv("PATH")
"""
    helpers = """\
from .settings import setting

cache = setting("SVC_CACHE_DIR")
label = "SVC_lowercase_is_not_a_name"
other = "OTHER_CACHE_DIR"
"""
    names = _scan({"svc/config.py": config, "svc/helpers.py": helpers})
    env = {(n["name"], n["file"], n["line"]) for n in names if n["kind"] == "env"}
    assert env == {
        ("SVC_HOME", "svc/config.py", 3), ("API_TOKEN", "svc/config.py", 4),
        ("SVC_LOG_LEVEL", "svc/config.py", 6), ("PATH", "svc/config.py", 7),
        ("SVC_CACHE_DIR", "svc/helpers.py", 3),
    }


def test_routes_decorators() -> None:
    src = """\
from fastapi import APIRouter
from flask import Blueprint

router = APIRouter()
bp = Blueprint("x", __name__)


@router.get("/items/{item_id}")
def get_item(item_id):
    pass


@router.post(
    "/items")
def create_item():
    pass


@bp.route("/health", methods=["GET"])
def health():
    pass


@router.delete("/admin/_purge")
def purge():
    pass


@router.get("not-a-path")
def odd():
    pass
"""
    names = _scan({"api.py": src})
    assert _of(names, "route") == {("/items/{item_id}", None, False),
                                   ("/items", None, False), ("/health", None, False),
                                   ("/admin/_purge", None, True)}
    assert _line(names, "route", "/items") == 14


def test_mcp_tool_multiline_name_and_params() -> None:
    src = """\
from mcp.types import Tool

SEARCH_SCHEMA = {"type": "object", "properties": {"query": {"type": "string"}}}


def list_tools():
    return [
        Tool(
            name="memory_observe",
            description="Record an observation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "outcome": {"type": "string"},
                },
            },
        ),
        Tool(
            description="Search.",
            name="memory_search",
            inputSchema=SEARCH_SCHEMA,
        ),
    ]


@server.tool()
def recall(topic: str, limit: int = 5):
    pass


@server.tool(name="forget_all")
def forget(scope: str):
    pass
"""
    names = _scan({"server.py": src})
    assert _of(names, "tool") == {("memory_observe", None, False),
                                  ("memory_search", None, False), ("recall", None, False),
                                  ("forget_all", None, False)}
    assert _line(names, "tool", "memory_observe") == 9
    assert _of(names, "param") == {
        ("content", "memory_observe", False), ("outcome", "memory_observe", False),
        ("query", "memory_search", False), ("topic", "recall", False),
        ("limit", "recall", False), ("scope", "forget_all", False),
    }
    assert _line(names, "param", "content") == 14


def test_js_process_env_commander_and_routes() -> None:
    src = """\
const { program } = require("commander");
const express = require("express");
const app = express();

const port = process.env.APP_PORT || 3000;
const key = process.env[
  "APP_API_KEY"];

program
  .command("deploy <env>")
  .option("-f, --force", "force it")
  .option("--dry-run")
  .option("verbose", { type: "boolean" });

app.get(
  "/status", (req, res) => res.send("ok"));
router.post("/jobs/:id", handler);
const label = "APP_REGION";
"""
    names = _scan({"src/index.ts": src})
    assert _of(names, "env") == {("APP_PORT", None, False), ("APP_API_KEY", None, False),
                                 ("APP_REGION", None, False)}
    assert _line(names, "env", "APP_API_KEY") == 7
    assert _of(names, "command") == {("deploy", None, False)}
    assert _of(names, "flag") == {("--force", None, False), ("--dry-run", None, False),
                                  ("--verbose", None, False)}
    assert _of(names, "route") == {("/status", None, False), ("/jobs/:id", None, False)}
    assert _line(names, "route", "/status") == 16


PYPROJECT = """\
[project]
name = "svc"

[project.scripts]
svc = "svc.cli:main"
svc-admin = "svc.admin:main"

[project.entry-points."svc.plugins"]
csv = "svc.plugins.csv:Plugin"
"""
PACKAGE = """\
{
  "name": "webapp",
  "bin": {"webapp": "bin/cli.js"},
  "scripts": {
    "build": "tsc",
    "test": "vitest"
  }
}
"""
MAKEFILE = """\
.PHONY: all lint
all: lint

lint:
\truff check .

_private:
\techo hidden
"""
JUSTFILE = """\
default:
    just --list

release version:
    echo {{version}}
"""
TASKFILE = """\
version: "3"
tasks:
  fmt:
    cmds: [gofmt -w .]
"""
DOCKERFILE = """\
FROM python:3.12
ENV APP_HOME=/app \\
    APP_MODE=prod
ENV LANG C.UTF-8
RUN echo "ENV NOT_THIS=1"
"""
DOTENV = """\
# comment
DATABASE_URL=postgres://localhost/db
export REDIS_URL=redis://localhost
"""


def test_manifest_entry_points_and_targets() -> None:
    assert entry_points("pyproject.toml", PYPROJECT) == ["csv", "svc", "svc-admin"]
    assert entry_points("web/package.json", PACKAGE) == ["build", "test", "webapp"]
    assert entry_points("web/package.json", '{"name": "solo", "bin": "cli.js"}') == ["solo"]
    assert entry_points("pyproject.toml", "not [valid") == []
    assert targets("Makefile", MAKEFILE) == ["_private", "all", "lint"]
    assert targets("justfile", JUSTFILE) == ["default", "release"]
    assert targets("Taskfile.yml", TASKFILE) == ["fmt"]
    assert targets("README", "x:") == []


def test_project_files_scripts_targets_env_and_dotenv() -> None:
    files = {"pyproject.toml": PYPROJECT, "web/package.json": PACKAGE, "Makefile": MAKEFILE,
             "justfile": JUSTFILE, "Taskfile.yml": TASKFILE, "Dockerfile": DOCKERFILE,
             ".env.example": DOTENV}
    names = _scan(files)
    scripts = {(n["name"], n["file"], n["line"]) for n in names if n["kind"] == "script"}
    assert scripts == {("svc", "pyproject.toml", 5), ("svc-admin", "pyproject.toml", 6),
                       ("csv", "pyproject.toml", 9), ("webapp", "web/package.json", 3),
                       ("build", "web/package.json", 5), ("test", "web/package.json", 6)}
    assert _of(names, "target") == {("all", None, False), ("lint", None, False),
                                    ("_private", None, True), ("default", None, False),
                                    ("release", None, False), ("fmt", None, False)}
    assert _line(names, "target", "lint") == 4
    env = {(n["name"], n["file"], n["line"]) for n in names if n["kind"] == "env"}
    assert env == {("APP_HOME", "Dockerfile", 2), ("APP_MODE", "Dockerfile", 3),
                   ("LANG", "Dockerfile", 4), ("DATABASE_URL", ".env.example", 2),
                   ("REDIS_URL", ".env.example", 3)}


def test_syntax_error_skips_file_and_names_sort() -> None:
    files = {"b.py": 'import os\nos.getenv("B_ONE")\n', "a.py": "def broken(:\n",
             "c.py": 'import os\nos.getenv("C_TWO")\nos.getenv("C_ONE")\n'}
    names = scan(["c.py", "b.py", "a.py", "gone.py"], files.get)
    assert [(n["file"], n["line"]) for n in names] == [("b.py", 2), ("c.py", 2), ("c.py", 3)]
    skipped = scan_files(["a.py", "b.py", "gone.py"], files.get).skipped
    assert skipped == [{"file": "a.py", "reason": "syntax error"},
                       {"file": "gone.py", "reason": "unreadable"}]


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *_IDENTITY, *args],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def _commit(repo: Path, files: dict[str, str]) -> str:
    for rel, text in files.items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "change")
    return _git(repo, "rev-parse", "HEAD")


def _inventory(work: Path, sources: list[str], project: list[str]) -> None:
    write_json(work / "inventory.json", {"files": sorted([*sources, *project]),
                                         "sources": {"source": sources},
                                         "project_files": project})


def test_names_then_for_changed_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    first = _commit(repo, {
        "app/cli.py": 'import os\nos.getenv("APP_HOME")\n',
        "app/other.py": 'import argparse\np = argparse.ArgumentParser()\np.add_argument("--a")\n',
    })
    _commit(repo, {
        "app/cli.py": 'import os\nos.getenv("APP_HOME")\nlabel = "APP_CACHE"\n',
        "app/new.py": 'import os\nos.getenv("NEW_VAR")\n',
    })
    work = tmp_path / "work"
    work.mkdir()
    _inventory(work, ["app/cli.py", "app/new.py", "app/other.py"], [])
    changes: dict[str, Any] = {"last_run": first,
                               "changed_files": ["app/cli.py", "app/new.py", "gone.py"]}
    write_json(work / "changes.json", changes)
    result = run(repo, work)
    assert result == read_json(work / "patterns.json")
    assert {(n["name"], n["file"]) for n in result["names"]} == {
        ("APP_HOME", "app/cli.py"), ("APP_CACHE", "app/cli.py"),
        ("NEW_VAR", "app/new.py"), ("--a", "app/other.py")}
    # only the changed indexed files, as they were at the last run
    assert [(n["name"], n["file"]) for n in result["names_then"]] == [
        ("APP_HOME", "app/cli.py")]
    assert result["skipped"] == []

    write_json(work / "changes.json", {"last_run": None, "changed_files": []})
    assert run(repo, work)["names_then"] is None
