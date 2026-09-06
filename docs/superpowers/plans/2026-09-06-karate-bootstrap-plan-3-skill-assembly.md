# karate-bootstrap Plan 3 of 4: Skill Assembly Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Plan 1 and Plan 2 scripts and template into a skill Opus 4.8 or Sonnet 4.6 can run end to end: `SKILL.md` with one pinned command per step, the three subagent prompts rendered by script, the per-stack cheat sheets and harness notes, a linter that keeps `SKILL.md` honest, and evals that prove the command chain and the trigger description.

**Architecture:** `SKILL.md` is a numbered procedure over the existing scripts; every step names one command and one output file and every command is linted against the script's `--help` in CI by `kb_check_skill.py`. Subagent prompts are `string.Template` files under `prompts/` that `kb_prompt.py render` fills with the ledger entry, the cheat sheet path and the env-map roles, so the main agent never composes a prompt freehand. The ledger gains the four bookkeeping commands the chain spike showed were missing (`add-entry`, `mark --feature/--stub/--seed`, `record-run`, `override`). Reference sheets mirror `markers.py`, and a test proves every marker token appears in its sheet. A dry-run test executes the whole pinned chain on both fixture repos with canned subagent outputs.

**Tech Stack:** Python 3.11+ with `pyyaml`; pytest, ruff, mypy strict. Markdown for `SKILL.md`, prompts, reference sheets and evals. No LLM calls in scripts or tests. No Java changes.

**Spec:** `docs/superpowers/specs/2026-09-05-karate-bootstrap-design.md` at commit `dc15a94` (skill-assembly amendment for this plan: sections 5.2 to 5.4, 5.6, 5.7, 9, 11).

**Phasing:** Plan 1 (analysis core) landed as PR #7; Plan 2 (harness template, scaffold, report, iterate, checkpoint) as PR #8. This is Plan 3 of 4. Plan 4 covers the fixture apps with db-manager images and the first live container runs. Branch: `feat/karate-bootstrap-plan-3` from `main` at `771c861`.

## Guardrails

Surfaced from better-memory (planning and implementation phases), the `standards/ralph-runtime.md` knowledge document, and the Plan 1 and Plan 2 executions before any task was drafted.

- **[[planning-memory-first]]** (reflection mem-34049f47, confidence 0.9, used 29x): planning and implementation memories plus the standards document were retrieved before drafting; the Plan 3 decisions (Q1 to Q3, finding F1) were put to the user in the visualiser and answered before this plan was written.
- **[[confidence-gate]]** (standards, non-skippable): every task carries a confidence percentage and the evidence that earns it. Nothing sits below 90%. The chain spike run today (every pinned command on `spring-mini` with canned subagent outputs, all gates green) is the evidence behind Tasks 6 and 8.
- **[[docs-in-sync]]** (reflection mem-f3ce58e6, confidence 0.95, evidence 7, used 30x; its CLI-flag-drift hint applies word for word here): every command in `SKILL.md` is copied from the scripts' `argparse` definitions, never paraphrased from the spec, and `kb_check_skill.py` lints them in CI. The repo `README.md` gains its karate-bootstrap section in the same task as `SKILL.md`. A script whose flags change updates its module docstring in the same task.
- **[[spec-code-lint]]** (standards): plan code is not lint-clean by default. Every task ends with `ruff check .` and `mypy` before commit. The controller extracts every Python block from this plan and runs ruff and mypy on it before Task 1 is dispatched, as in Plan 2.
- **[[cross-read]]** (standards): the prompt files embed example outputs; tests feed each example back through the consuming script (`merge_entry`, `add_rows`, `record_files`, `parse_feature`) so prose and example cannot disagree with the schema.
- **[[stage-by-path]]** (Plan 1 incident): `git add` names explicit paths only. Never `git add -A`, `git add .`, or `commit -a`. Rendered prompts go under `karate-tests/.prompts/`, which the template's `.gitignore` excludes.
- **[[unique-module-names]]** (spec section 9): new modules are `kb_prompt.py` and `kb_check_skill.py`; tests are `test_kb_*.py`; no `__init__.py` under `skills/karate-bootstrap/tests/`.
- **[[worktree-git]]** (Plan 1 and 2 executions): the Bash tool's worktree guard refuses compound commands that mix `cd`, shell variables or `-C` with git, and refuses `python` invoked on paths built from variables. Plain commands, one per invocation, from `C:\Users\gethi\source\claude-skills\.claude\worktrees\karate-testcontainers`.
- **[[implementer-drift]]** (Plan 2 Task 8): a cheap-tier implementer changed one literal in a verbatim test and reported "no deviations". Reviewers diff committed tests against the brief's code blocks; controllers treat "matches the brief" claims as unverified.
- **[[both-modes]]** (Plan 2 final review, Critical C1): anything shipped into a target repo must hold in every mode it can run in. `SKILL.md` therefore documents the `-Dkb.skipContainers=true` self-test and the live run as distinct steps with distinct expectations.
- **[[verify-red]]** (reflection mem-66b096bf, confidence 0.75): confirm each red is the predicted failure before implementing.

Dismissed as not applicable, with reasons: Playwright text matching (no browser tests); `tempfile.mkstemp` fd leak (no fd-level temp files); TypeScript `Partial<T>` (no TypeScript); paired enter/exit freeze logging (pure-data scripts); "ralph-queue means ralph builds it" (the user executes this plan interactively).

## Task confidence summary

| Task | Deliverable | Confidence | Evidence and embedded mitigation |
|------|-------------|-----------:|----------------------------------|
| 1 | Ledger bookkeeping commands (`add-entry`, `mark --feature/--stub/--seed`, `record-run`, `override`), `seed_ledger` reuse, Plan 2 parked scaffold fixes | 92% | Same shapes as the existing `mark`/`merge` code read at plan time; every command pinned by tests on the real `spring-mini` ledger |
| 2 | `kb_prompt.py render` and the three prompt files | 90% | `string.Template` with strict substitution; every placeholder listed in one table and covered by a render test per prompt; each embedded example output is validated by the script that consumes it. The remaining risk, prompt quality for a live Opus or Sonnet run, is only measurable in Plan 4's fixture runs |
| 3 | Four stack cheat sheets | 91% | Content derived from `markers.py`, `discover.py` conventions and spec section 8; a test asserts every `tokens_for(stack, kind)` token appears in its sheet |
| 4 | Harness notes (`testcontainers-notes`, `karate-notes`, `failure-triage`, `podman`) | 93% | Facts come from the Plan 2 spike and the landed harness code; a heading test pins structure |
| 5 | `kb_check_skill.py` with tests | 94% | Port of `tech-debt-scan/scripts/skill_check.py`, which has run in CI since PR #5 |
| 6 | `SKILL.md`, its lint test, CI step | 90% | Every command copied from the `argparse` listing in this plan; the chain ran green today; `kb_check_skill.py` and Task 8's dry run are the gates |
| 7 | `evals/trigger-eval.md`, description test, repo README section | 93% | Pure text plus a frontmatter test |
| 8 | Dry-run eval on `spring-mini` and `dotnet-mini` | 92% | The `spring-mini` chain ran green today with canned outputs; the `dotnet-mini` traces reference marker lines read from the fixture at plan time |

All eight tasks are at or above 90%; no Step 0 spikes.

## Global Constraints

Copied from the spec; every task's requirements include this section.

- Python floor `>=3.11`; ruff `target-version = "py311"` with `E,F,I,B,UP,SIM`, line length 100; mypy `python_version = "3.11"`, strict. Only runtime dependency: `pyyaml>=6.0`.
- Scripts are direct-path invocable (`python skills/karate-bootstrap/scripts/<name>.py`), import siblings flatly (`from kb_common import ...`), and new basenames carry the `kb_` prefix.
- Exit codes (spec section 9, `kb_common.py`): 0 ok, 2 validation failure, 3 unsupported stack, 4 no schema source, 5 missing expected output, 6 stopped by stop condition, 7 container runtime or JDK missing.
- `SKILL.md` (spec section 9): under 500 lines; numbered steps, one pinned command each, one pinned output file each, an exit-code table; the "no improvisation" rule (a missing expected output means abort with exit 5); subagent prompts only via `kb_prompt.py render`; cheat sheets loaded only for the detected stack; the skill commits with `kb_checkpoint.py` and never pushes; `--no-commit` never runs git.
- Invocation (spec section 9): `/karate-bootstrap <repo-path> [--service-dir <sub>] [--migrations-image <ref>] [--app-image <tag>] [--max-iterations 15] [--double-trace] [--no-commit]`.
- Ledger entry shape (spec section 6, `discover.seed_ledger`): `id, kind, method|destination, path|type, handler, auth, request, responses, reads, exits, rules{file,count,sources}, features, stubs, seeds, observed_overrides, status{traced,stubbed,tested,passing}`. Trace output fields accepted by `merge_entry`: `id, auth, request, responses, reads, exits, exits_none_reason, type, rules.sources, unresolved`. Exit kinds `db-write` (`table`, `op`), `amq-publish` (`destination`, `type`), `http-out` (`host_key`, `method`, `path`); every exit needs `via: file:line`. Read kinds `db-read`, `http-in`.
- Rules CSV header is exactly `rule_id,field,mutation,value,expected_status,expected_code,expected_message_contains,source`; mutations `missing, null, empty, too_long, too_short, invalid_format, out_of_range, invalid_enum, cross_field`.
- Isolation by data (spec 5.6): suite-level stubs under `stubs/<downstream>/*.json`; unique ids per scenario; `Jms.await` with a match map; `Stubs.verify` by unique path or body; `@parallel=false` for `Stubs.reset`, `Stubs.load`, `Db.truncate`, and `reset.feature`'s `stubs:`/`truncate:` arguments; `reset.feature` applies `watch, truncate, seed, stubs` in that order.
- Harness API the prompts may name (Plan 2, `kb.harness`): `Db.run(path)`, `Db.row(table, where)`, `Db.awaitRow(table, where, timeoutMs)`, `Db.count(table, where)`, `Db.truncate(tables)`; `Jms.watch(dest)`, `Jms.await(dest, timeoutMs)`, `Jms.await(dest, timeoutMs, matchMap)`, `Jms.publish(dest, body, headers)`; `Stubs.reset()`, `Stubs.load(path)`, `Stubs.verify(method, urlPath, times)`, `Stubs.verify(method, urlPath, bodyContains, times)`; `Jwt.token(claims)`; globals `appBaseUrl`, `mutate`, `skipContainers`.
- Report JSON contract (spec 5.7): `{"passed", "skipped", "failed": [{"feature", "scenario", "outline", "tags", "step", "error"}]}`; `feature` values are `features/<name>.feature`, the same strings the ledger's `features` lists hold.
- `defects.md` entries (spec section 7): `## DEF-NNN: <title>` then `status`, `slug`, `severity`, `category`, `entry_point`, `scenario`, `evidence`, `root_cause`, `suggested_fix`.
- Commits: Conventional Commits, scope `karate-bootstrap`, ending with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Never bypass hooks. [[stage-by-path]] applies to every commit.

---

## File Structure

```
skills/karate-bootstrap/
  SKILL.md                                                   Task 6
  scripts/
    flow_map.py        (modify: new_entry, add-entry, mark --feature/--stub/--seed, record-run, override)   Task 1
    discover.py        (modify: seed_ledger uses flow_map.new_entry)                                       Task 1
    kb_scaffold.py     (modify: narrow the conn needle; rules/harness-smoke.csv in HARNESS_FILES)           Task 1
    kb_prompt.py       (new: render prompts/<name>.md with entry context)                                   Task 2
    kb_check_skill.py  (new: lint SKILL.md commands against --help)                                         Task 5
  prompts/trace.md rules.md generate.md                                                                     Task 2
  reference/stack-spring.md stack-quarkus.md stack-aspnetcore.md stack-python.md                            Task 3
  reference/testcontainers-notes.md karate-notes.md failure-triage.md podman.md                             Task 4
  evals/trigger-eval.md                                                                                     Task 7
  templates/karate-tests/.gitignore  (modify: .prompts/)                                                    Task 2
  tests/
    test_kb_flow_map.py test_kb_discover.py test_kb_scaffold.py  (modify)                                   Task 1
    test_kb_prompt.py                                                                                       Task 2
    test_kb_reference.py                                                                                    Task 3 (Task 4 extends)
    test_kb_check_skill.py                                                                                  Task 5 (Task 6 extends)
    test_kb_skill_md.py                                                                                     Task 7
    test_kb_dry_run.py                                                                                      Task 8
README.md                    (modify: karate-bootstrap install and quickstart)                              Task 7
.github/workflows/test.yml   (modify: kb_check_skill step)                                                  Task 6
```

Responsibilities: `flow_map.py` stays the only writer of `flow-map.yaml`. `kb_prompt.py` is the only reader of `prompts/` and the only writer under `karate-tests/.prompts/`. `SKILL.md` names commands and files only; it holds no logic. Reference sheets are documentation for the subagents and are tested for coverage of `markers.py`, never the other way round.

Task order and dependencies: 1 (ledger commands) is consumed by 2 (the prompts tell subagents which commands record their output), 6 and 8; 2 is consumed by 6 and 8; 3 and 4 are independent documentation consumed by 6; 5 is consumed by 6 (the real-SKILL.md lint test and CI step land with `SKILL.md`); 7 depends on 6; 8 depends on everything.

---

### Task 1: Ledger bookkeeping commands and Plan 2 parked fixes

**Confidence:** 92%. The chain spike today had to edit `flow-map.yaml` by hand at three points; these commands close those gaps with the same patterns `mark`, `merge` and `set_auth` already use (read at plan time: `flow_map.py:176-236`). The scaffold fixes are the two items parked at Plan 2's final review.

**Files:**
- Modify: `skills/karate-bootstrap/scripts/flow_map.py` (docstring, `new_entry`, `add_entry`, `record_files`, `record_run`, `add_override`, `_cmd_mark`, new `_cmd_*`, `build_parser`)
- Modify: `skills/karate-bootstrap/scripts/discover.py` (`seed_ledger` uses `flow_map.new_entry`; delete `_blank_status`)
- Modify: `skills/karate-bootstrap/scripts/kb_scaffold.py:58,83` (`HARNESS_FILES`, `_DB_URL_NEEDLES`)
- Test: `skills/karate-bootstrap/tests/test_kb_flow_map.py`, `tests/test_kb_discover.py`, `tests/test_kb_scaffold.py`

**Interfaces:**
- Consumes: `flow_map.find_entry`, `load_ledger`, `save_ledger`, `STATUS_FLAGS`, `VIA_RE`, `KbError` (Plan 1).
- Produces for Tasks 2, 6, 8: `new_entry(base: dict) -> dict`; `add_entry(ledger, entry_id, kind, handler, method=None, path=None, destination=None, dest_type="queue") -> dict`; `record_files(ledger, entry_id, features=(), stubs=(), seeds=()) -> dict`; `record_run(ledger, report) -> dict[str, int]` (`tested`, `passing`, `failing`); `add_override(ledger, entry_id, scenario, field, old, new, reason) -> dict`; CLI `flow_map.py add-entry --ledger PATH --id ID --kind {http,amq-subscribe} --handler file:line [--method M --path P] [--destination D --type {queue,topic}]`, `flow_map.py mark ... [--feature F]... [--stub S]... [--seed X]...`, `flow_map.py record-run --ledger PATH --report PATH`, `flow_map.py override --ledger PATH --entry ID --scenario S --field F --old O --new N --reason R`.

- [ ] **Step 1: Add the failing tests to `tests/test_kb_flow_map.py`**

Add `add_entry`, `add_override`, `new_entry`, `record_files`, `record_run` to the `from flow_map import (...)` list (alphabetical). Append:

```python
def test_new_entry_carries_every_bookkeeping_field() -> None:
    entry = new_entry({"id": "GET /x", "kind": "http", "method": "GET", "path": "/x",
                       "handler": "src/X.java:3"})
    assert entry["status"] == {"traced": False, "stubbed": False, "tested": False,
                               "passing": False}
    assert entry["rules"] == {"file": None, "count": 0, "sources": []}
    assert (entry["features"], entry["stubs"], entry["seeds"], entry["observed_overrides"]) == (
        [], [], [], []
    )
    assert entry["auth"] == "unknown" and entry["request"] is None
    assert entry["method"] == "GET" and entry["handler"] == "src/X.java:3"


def test_add_entry_seeds_http_and_amq_entries(spring_ledger: tuple[Path, dict[str, Any]]) -> None:
    _, ledger = spring_ledger
    before = len(ledger["entry_points"])
    http = add_entry(ledger, "DELETE /api/shipments/{id}", "http",
                     "src\\main\\java\\com\\acme\\shipments\\ShipmentController.java:30",
                     method="delete", path="/api/shipments/{id}")
    assert http["method"] == "DELETE"
    assert http["handler"] == "src/main/java/com/acme/shipments/ShipmentController.java:30"
    assert http["status"]["traced"] is False
    amq = add_entry(ledger, "amq shipment.cancelled", "amq-subscribe", f"{LISTENER}:20",
                    destination="shipment.cancelled", dest_type="topic")
    assert (amq["destination"], amq["type"]) == ("shipment.cancelled", "topic")
    assert len(ledger["entry_points"]) == before + 2
    assert next_entry(ledger, "traced")["id"] == "POST /api/shipments"
    with pytest.raises(KbError, match="already in the ledger"):
        add_entry(ledger, "amq shipment.cancelled", "amq-subscribe", f"{LISTENER}:20",
                  destination="x")
    with pytest.raises(KbError, match="--method and --path"):
        add_entry(ledger, "PUT /x", "http", f"{LISTENER}:20")
    with pytest.raises(KbError, match="file:line"):
        add_entry(ledger, "PUT /y", "http", "ShipmentController.java", method="PUT", path="/y")
    with pytest.raises(KbError, match="unknown entry kind"):
        add_entry(ledger, "cron nightly", "cron", f"{LISTENER}:20")


def test_record_files_appends_and_dedupes(spring_ledger: tuple[Path, dict[str, Any]]) -> None:
    _, ledger = spring_ledger
    entry = record_files(ledger, "POST /api/shipments",
                         features=["features/post-api-shipments.feature"],
                         stubs=["stubs\\pricing\\default.json", "stubs/pricing/outage.json"],
                         seeds=["seed/post-api-shipments.sql"])
    assert entry["features"] == ["features/post-api-shipments.feature"]
    assert entry["stubs"] == ["stubs/pricing/default.json", "stubs/pricing/outage.json"]
    record_files(ledger, "POST /api/shipments", features=["features/post-api-shipments.feature"],
                 stubs=["stubs/pricing/default.json"])
    assert entry["features"] == ["features/post-api-shipments.feature"]
    assert entry["stubs"] == ["stubs/pricing/default.json", "stubs/pricing/outage.json"]
    assert entry["seeds"] == ["seed/post-api-shipments.sql"]


def test_record_run_sets_tested_and_passing_from_the_report(
    spring_ledger: tuple[Path, dict[str, Any]],
) -> None:
    _, ledger = spring_ledger
    record_files(ledger, "POST /api/shipments", features=["features/post-api-shipments.feature"])
    record_files(ledger, "GET /api/shipments/{id}", features=["features/get-api-shipments-id.feature"])
    report = {"passed": 3, "skipped": 0, "failed": [
        {"feature": "features/get-api-shipments-id.feature", "scenario": "missing",
         "outline": False, "tags": ["@error"], "step": "status 404", "error": "got 500"},
    ]}
    assert record_run(ledger, report) == {"tested": 2, "passing": 1, "failing": 1}
    post = find_entry(ledger, "POST /api/shipments")["status"]
    get = find_entry(ledger, "GET /api/shipments/{id}")["status"]
    amq = find_entry(ledger, "amq shipment.requested")["status"]
    assert (post["tested"], post["passing"]) == (True, True)
    assert (get["tested"], get["passing"]) == (True, False)
    assert (amq["tested"], amq["passing"]) == (False, False)
    assert record_run(ledger, {"passed": 4, "skipped": 0, "failed": []}) == {
        "tested": 2, "passing": 2, "failing": 0,
    }
    assert find_entry(ledger, "GET /api/shipments/{id}")["status"]["passing"] is True


def test_add_override_appends_to_the_entry(spring_ledger: tuple[Path, dict[str, Any]]) -> None:
    _, ledger = spring_ledger
    item = add_override(ledger, "POST /api/shipments", "creates a shipment", "status", "201",
                        "200", "controller returns ok(), not created()")
    assert item == {"scenario": "creates a shipment", "field": "status", "old": "201",
                    "new": "200", "reason": "controller returns ok(), not created()"}
    assert find_entry(ledger, "POST /api/shipments")["observed_overrides"] == [item]


def test_cli_add_entry_mark_files_record_run_override(
    spring_ledger: tuple[Path, dict[str, Any]], tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ledger_path, _ = spring_ledger
    assert run_cli(main, ["add-entry", "--ledger", str(ledger_path), "--id", "PUT /api/shipments/{id}",
                          "--kind", "http", "--handler", f"{SERVICE}:40", "--method", "PUT",
                          "--path", "/api/shipments/{id}"]) == 0
    assert "PUT /api/shipments/{id}" in capsys.readouterr().out
    assert run_cli(main, ["mark", "--entry", "POST /api/shipments", "--generated",
                          "--feature", "features/post-api-shipments.feature",
                          "--stub", "stubs/pricing/default.json",
                          "--seed", "seed/post-api-shipments.sql",
                          "--ledger", str(ledger_path)]) == 0
    entry = find_entry(load_ledger(ledger_path), "POST /api/shipments")
    assert entry["status"]["stubbed"] is True
    assert entry["features"] == ["features/post-api-shipments.feature"]
    assert entry["stubs"] == ["stubs/pricing/default.json"]
    assert entry["seeds"] == ["seed/post-api-shipments.sql"]
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"passed": 1, "skipped": 0, "failed": []}), encoding="utf-8")
    capsys.readouterr()
    assert run_cli(main, ["record-run", "--ledger", str(ledger_path), "--report", str(report)]) == 0
    assert "tested: 1" in capsys.readouterr().out
    assert find_entry(load_ledger(ledger_path), "POST /api/shipments")["status"]["passing"] is True
    assert run_cli(main, ["override", "--ledger", str(ledger_path), "--entry", "POST /api/shipments",
                          "--scenario", "happy", "--field", "status", "--old", "201",
                          "--new", "200", "--reason", "observed"]) == 0
    assert find_entry(load_ledger(ledger_path), "POST /api/shipments")["observed_overrides"] == [
        {"scenario": "happy", "field": "status", "old": "201", "new": "200", "reason": "observed"}
    ]
    assert run_cli(main, ["add-entry", "--ledger", str(ledger_path), "--id", "PUT /api/shipments/{id}",
                          "--kind", "http", "--handler", f"{SERVICE}:40", "--method", "PUT",
                          "--path", "/x"]) == 2
```

`json` is already imported in that test module.

- [ ] **Step 2: Add the `seed_ledger` test to `tests/test_kb_discover.py`**

Add `seed_ledger` to the `from discover import (...)` list and `from flow_map import new_entry` after it (imports sorted: `detect`, `discover`, `flow_map`, `kb_common`, `kb_helpers`). Append:

```python
def test_seed_ledger_entries_match_new_entry_shape() -> None:
    root = FIXTURES / "spring-mini"
    stack_info = detect(root)
    config = parse_app_config(root)
    env_map = build_env_map(stack_info, None, None, config)
    entries = find_entry_points(root, "spring", config)
    ledger = seed_ledger(stack_info, env_map, entries, detect_migrations(root, "spring", config),
                        "spring-mini", "Dockerfile")
    for seeded, base in zip(ledger["entry_points"], entries, strict=True):
        assert seeded == new_entry(base)
```

- [ ] **Step 3: Add the scaffold tests to `tests/test_kb_scaffold.py`**

In the `test_env_value_rules` parametrize table, after the `QUARKUS_DATASOURCE_DB_KIND` row, add:

```python
    ("spring", "SPRING_DATASOURCE_HIKARI_CONNECTION_TIMEOUT", "db", "30000", "application.yml",
     None),
    ("aspnetcore", "Deals__ConnStr", "db", "", "deployment.yml",
     "Host={{db.host}};Port={{db.port}};Database={{db.name}};"
     "Username={{db.user}};Password={{db.password}}"),
```

In `test_copy_template_never_overwrites_generated_content`, replace the last five lines (from the `# The smoke feature is harness content` comment to the end of the function) with:

```python
    # The smoke feature and its CSV are harness content, so --force refreshes them despite
    # their generated prefixes; defects.md stays the repo's.
    for harness in ("src/test/resources/features/harness-smoke.feature",
                    "rules/harness-smoke.csv"):
        assert harness in third["overwritten"]
        assert (out / harness).read_text(encoding="utf-8") != "edited", harness
    assert (out / "defects.md").read_text(encoding="utf-8") == "edited"
```

- [ ] **Step 4: Run the new tests and confirm the predicted failures**

Run: `pytest skills/karate-bootstrap/tests/test_kb_flow_map.py skills/karate-bootstrap/tests/test_kb_discover.py skills/karate-bootstrap/tests/test_kb_scaffold.py -q`
Expected ([[verify-red]]): `test_kb_flow_map.py` and `test_kb_discover.py` fail at collection with `ImportError` (`add_entry`, `new_entry` do not exist); in `test_kb_scaffold.py` the `HIKARI_CONNECTION_TIMEOUT` row fails (`conn` in the needles gives a JDBC URL), the `Deals__ConnStr` row fails (no `connstr` needle), and the copy test fails on `rules/harness-smoke.csv` (kept, not overwritten).

- [ ] **Step 5: Implement the ledger commands in `scripts/flow_map.py`**

Docstring: add after the `mark` line and before `set-auth`:

```
    mark        --entry ID (--generated|--tested|--passing|--failing)
                [--feature F]... [--stub S]... [--seed X]... --ledger PATH
                flips status flags and records generated files on the entry
    add-entry   --ledger PATH --id ID --kind http|amq-subscribe --handler file:line
                [--method M --path P] [--destination D --type queue|topic]
                seeds an entry the discover regexes missed (spec 5.2)
    record-run  --ledger PATH --report PATH
                sets tested and passing on every entry with features from report.json
    override    --ledger PATH --entry ID --scenario S --field F --old O --new N --reason R
                appends an observed-behaviour override (spec 5.7, classification 3)
```

(Replace the existing single `mark` docstring line with the three-line block above.) Add after `AUTH_MODES`:

```python
ENTRY_KINDS = ("http", "amq-subscribe")
```

Add after `find_entry`:

```python
def new_entry(base: dict[str, Any]) -> dict[str, Any]:
    """An untraced entry: ``base`` (id, kind, handler and the kind's own fields) plus the
    bookkeeping fields every phase expects. discover.seed_ledger and add_entry both use it."""
    item: dict[str, Any] = dict(base)
    item.update({
        "auth": "unknown",
        "request": None,
        "responses": [],
        "reads": [],
        "exits": [],
        "rules": {"file": None, "count": 0, "sources": []},
        "features": [],
        "stubs": [],
        "seeds": [],
        "observed_overrides": [],
        "status": dict.fromkeys(STATUS_FLAGS, False),
    })
    return item


def add_entry(ledger: dict[str, Any], entry_id: str, kind: str, handler: str,
              method: str | None = None, path: str | None = None,
              destination: str | None = None, dest_type: str = "queue") -> dict[str, Any]:
    """Seed an entry point the discover regexes missed (spec 5.2)."""
    if kind not in ENTRY_KINDS:
        raise KbError(f"{entry_id}: unknown entry kind {kind!r}; expected one of {ENTRY_KINDS}")
    if any(e.get("id") == entry_id for e in ledger["entry_points"]):
        raise KbError(f"{entry_id}: already in the ledger")
    clean_handler = handler.replace("\\", "/")
    if not VIA_RE.match(clean_handler):
        raise KbError(f"{entry_id}: handler must be file:line, got {handler!r}")
    base: dict[str, Any] = {"id": entry_id, "kind": kind}
    if kind == "http":
        if not method or not path:
            raise KbError(f"{entry_id}: http entries need --method and --path")
        base.update({"method": method.upper(), "path": path})
    else:
        if not destination:
            raise KbError(f"{entry_id}: amq-subscribe entries need --destination")
        base.update({"destination": destination, "type": dest_type})
    base["handler"] = clean_handler
    entry = new_entry(base)
    ledger["entry_points"].append(entry)
    return entry
```

Add after `mark_entry`:

```python
def record_files(ledger: dict[str, Any], entry_id: str, features: Iterable[str] = (),
                 stubs: Iterable[str] = (), seeds: Iterable[str] = ()) -> dict[str, Any]:
    """Append generated file paths (posix, de-duplicated) to the entry's lists."""
    entry = find_entry(ledger, entry_id)
    for key, items in (("features", features), ("stubs", stubs), ("seeds", seeds)):
        existing: list[str] = entry.setdefault(key, [])
        for item in items:
            clean = str(item).replace("\\", "/")
            if clean not in existing:
                existing.append(clean)
    return entry


def record_run(ledger: dict[str, Any], report: dict[str, Any]) -> dict[str, int]:
    """After a full run: every entry with features is tested; passing unless one of its
    features appears in the report's failed list (spec 5.7)."""
    failed_features = {str(item.get("feature", "")) for item in report.get("failed", [])}
    counts = {"tested": 0, "passing": 0, "failing": 0}
    for entry in ledger["entry_points"]:
        features = [str(f) for f in entry.get("features", [])]
        if not features:
            continue
        status = entry.setdefault("status", dict.fromkeys(STATUS_FLAGS, False))
        status["tested"] = True
        status["passing"] = not (set(features) & failed_features)
        counts["tested"] += 1
        counts["passing" if status["passing"] else "failing"] += 1
    return counts


def add_override(ledger: dict[str, Any], entry_id: str, scenario: str, field: str,
                 old: str, new: str, reason: str) -> dict[str, Any]:
    """Record that a generated expectation was replaced by observed behaviour."""
    entry = find_entry(ledger, entry_id)
    item = {"scenario": scenario, "field": field, "old": old, "new": new, "reason": reason}
    entry.setdefault("observed_overrides", []).append(item)
    return item
```

Add `from collections.abc import Iterable` to the imports (after `import argparse` block, before `from pathlib import Path`, keeping ruff's isort order: `from collections.abc import Iterable` sorts before `from pathlib import Path`).

Replace `_cmd_mark` with:

```python
def _cmd_mark(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    if args.generated:
        mark_entry(ledger, args.entry, "stubbed")
    if args.tested:
        mark_entry(ledger, args.entry, "tested")
    if args.passing:
        mark_entry(ledger, args.entry, "passing")
    if args.failing:
        mark_entry(ledger, args.entry, "passing", False)
    record_files(ledger, args.entry, args.feature or [], args.stub or [], args.seed or [])
    save_ledger(args.ledger, ledger)
    print(f"marked {args.entry}: {find_entry(ledger, args.entry)['status']}")
    return EXIT_OK
```

Add after `_cmd_set_auth`:

```python
def _cmd_add_entry(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    entry = add_entry(ledger, args.id, args.kind, args.handler, args.method, args.path,
                      args.destination, args.type)
    save_ledger(args.ledger, ledger)
    print(f"added {entry['id']} ({entry['kind']}) at {entry['handler']}")
    return EXIT_OK


def _cmd_record_run(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    report = read_json(require_file(args.report, "report.json"))
    counts = record_run(ledger, report)
    save_ledger(args.ledger, ledger)
    print(f"recorded run: tested: {counts['tested']}  passing: {counts['passing']}  "
          f"failing: {counts['failing']}")
    return EXIT_OK


def _cmd_override(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    item = add_override(ledger, args.entry, args.scenario, args.field, args.old, args.new,
                        args.reason)
    save_ledger(args.ledger, ledger)
    print(f"override on {args.entry}: {json.dumps(item)}")
    return EXIT_OK
```

In `build_parser`, extend the `mark` block before its `set_defaults`:

```python
    mark.add_argument("--feature", action="append", help="feature path to record (repeatable)")
    mark.add_argument("--stub", action="append", help="stub path to record (repeatable)")
    mark.add_argument("--seed", action="append", help="seed path to record (repeatable)")
```

and add after the `set-auth` block:

```python
    add = sub.add_parser("add-entry", help="Seed an entry point the discover regexes missed")
    add.add_argument("--ledger", type=Path, required=True)
    add.add_argument("--id", required=True, help='entry id, e.g. "PUT /api/deals/{id}"')
    add.add_argument("--kind", choices=ENTRY_KINDS, required=True)
    add.add_argument("--handler", required=True, help="file:line of the handler")
    add.add_argument("--method", default=None, help="HTTP method (kind http)")
    add.add_argument("--path", default=None, help="route path (kind http)")
    add.add_argument("--destination", default=None, help="queue or topic name (kind amq-subscribe)")
    add.add_argument("--type", choices=("queue", "topic"), default="queue")
    add.set_defaults(func=_cmd_add_entry)

    run = sub.add_parser("record-run", help="Set tested and passing per entry from report.json")
    run.add_argument("--ledger", type=Path, required=True)
    run.add_argument("--report", type=Path, required=True)
    run.set_defaults(func=_cmd_record_run)

    over = sub.add_parser("override", help="Append an observed-behaviour override to an entry")
    over.add_argument("--ledger", type=Path, required=True)
    over.add_argument("--entry", required=True)
    over.add_argument("--scenario", required=True)
    over.add_argument("--field", required=True)
    over.add_argument("--old", required=True)
    over.add_argument("--new", required=True)
    over.add_argument("--reason", required=True)
    over.set_defaults(func=_cmd_override)
```

- [ ] **Step 6: Make `discover.seed_ledger` reuse `new_entry`**

In `scripts/discover.py`: add `from flow_map import new_entry` after the `from kb_common import (...)` block (before `from markers import ...`, alphabetical). Delete `_blank_status`. Replace the loop in `seed_ledger`:

```python
    entry_points: list[dict[str, Any]] = []
    for entry in entries:
        item: dict[str, Any] = dict(entry)
        item.update({
            "auth": "unknown",
            "request": None,
            "responses": [],
            "reads": [],
            "exits": [],
            "rules": {"file": None, "count": 0, "sources": []},
            "features": [],
            "stubs": [],
            "seeds": [],
            "observed_overrides": [],
            "status": _blank_status(),
        })
        entry_points.append(item)
```

with

```python
    entry_points = [new_entry(entry) for entry in entries]
```

- [ ] **Step 7: Apply the parked scaffold fixes in `scripts/kb_scaffold.py`**

```python
HARNESS_FILES = ("src/test/resources/features/harness-smoke.feature", "rules/harness-smoke.csv")
```

```python
_DB_URL_NEEDLES = ("url", "jdbc", "connectionstring", "connstr", "dsn")
```

Update the comment near `_DB_URL_NEEDLES` (or add one) to say: bare `conn` was dropped because Hikari keys such as `connection-timeout` matched it.

- [ ] **Step 8: Full gate and the spec commands' help**

Run: `pytest -q` then `ruff check .` then `mypy` then `python skills/karate-bootstrap/scripts/flow_map.py add-entry --help` then `python skills/karate-bootstrap/scripts/flow_map.py mark --help` then `python skills/karate-bootstrap/scripts/flow_map.py record-run --help` then `python skills/karate-bootstrap/scripts/flow_map.py override --help`
Expected: green; each help lists the flags named in the Interfaces block. [[docs-in-sync]]

- [ ] **Step 9: Commit**

```bash
git add skills/karate-bootstrap/scripts/flow_map.py skills/karate-bootstrap/scripts/discover.py skills/karate-bootstrap/scripts/kb_scaffold.py skills/karate-bootstrap/tests/test_kb_flow_map.py skills/karate-bootstrap/tests/test_kb_discover.py skills/karate-bootstrap/tests/test_kb_scaffold.py
git commit -m "feat(karate-bootstrap): ledger add-entry, mark files, record-run and override

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: `kb_prompt.py render` and the three prompt files

**Confidence:** 90%. Rendering is `string.Template` with strict substitution over a context built from the ledger and env-map (both shapes read at plan time); every placeholder is listed in the table below and exercised by a render test per prompt. Each prompt embeds an example output, and the tests feed the example back through the script that consumes it (`merge_entry`, `add_rows`, `parse_feature` plus `unsafe_parallel_scenarios`), so the examples cannot drift from the schemas ([[cross-read]]). What no test here can measure is how well Opus 4.8 or Sonnet 4.6 follow the prompts on a real repo; Plan 4's fixture runs are that eval, and the prompts are plain files the user can tune at work.

**Files:**
- Create: `skills/karate-bootstrap/scripts/kb_prompt.py`
- Create: `skills/karate-bootstrap/prompts/trace.md`, `prompts/rules.md`, `prompts/generate.md`
- Modify: `skills/karate-bootstrap/templates/karate-tests/.gitignore` (add `.prompts/`)
- Test: `skills/karate-bootstrap/tests/test_kb_prompt.py`

**Interfaces:**
- Consumes: `flow_map.load_ledger`, `find_entry`; `kb_rules.slug_for`; `kb_common.{read_json, read_text, require_file, run_cli, KbError, EXIT_OK}`; env-map `keys[].{key, role, env_var}`; ledger `stack.{framework, cheat_sheet}`, `app.auth.mode`, entry fields.
- Produces for Tasks 6 and 8: CLI `kb_prompt.py render --prompt {trace,rules,generate} --ledger PATH --entry ID --repo ROOT --out PATH [--env PATH] [--tests-dir DIR] [--source FILE] [--focus file:line] [--prompts-dir DIR]`; Python `build_context(prompt, ledger, entry_id, env_map, repo, tests_dir, source, focus) -> dict[str, str]`, `render(prompt, context, prompts_dir) -> str`, constants `PROMPTS`, `PROMPTS_DIR`.
- Placeholders every template may use (all strings):

| Placeholder | Value |
|-------------|-------|
| `entry_id`, `slug`, `kind`, `handler`, `handler_path` | from the ledger entry; `slug` via `kb_rules.slug_for`; `handler_path` is the absolute posix path of the handler file |
| `stack`, `cheat_sheet` | `stack.framework`; absolute path of `<skill>/reference/stack-<stack>.md` |
| `repo`, `tests_dir` | absolute posix paths; `tests_dir` defaults to `<repo>/karate-tests` |
| `entry_json`, `exits_json`, `reads_json`, `responses_json` | `json.dumps(..., indent=2)` of the entry and its lists |
| `roles` | markdown table of env-map keys (`key`, `role`, `env var`), or `(no env-map given)` |
| `downstreams` | comma-separated downstream names from `downstream:<name>` roles, or `none` |
| `auth_mode`, `auth_instruction` | `app.auth.mode`; one sentence telling the generator whether to send a bearer token |
| `entry_instruction` | one paragraph: how to drive an `http` entry versus an `amq-subscribe` entry |
| `focus` | empty, or a "Start at file:line" paragraph when `--focus` is given |
| `source`, `source_path` | rules only: the validation source, relative and absolute |
| `candidates_csv`, `candidates_note`, `rows_csv` | rules only: `<tests>/rules/<slug>.candidates.csv`, whether it exists and how many rows, `<tests>/rules/<slug>.rows.csv` |
| `rules_file`, `rules_count` | `entry.rules.file` or `none`; count as text |
| `feature_file`, `seed_file`, `example_file`, `stubs_dir` | `features/<slug>.feature`, `seed/<slug>.sql`, `seed/examples/<slug>.json`, `stubs` |

- [ ] **Step 1: Write `tests/test_kb_prompt.py`**

```python
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from detect import main as detect_main
from discover import main as discover_main
from flow_map import find_entry, load_ledger, merge_entry
from kb_common import EXIT_OK, KbError, read_json, run_cli
from kb_features import parse_feature, unsafe_parallel_scenarios
from kb_prompt import PROMPTS, PROMPTS_DIR, build_context, main, render
from kb_rules import add_rows

FIXTURES = Path(__file__).parent / "fixtures"
SPRING = FIXTURES / "spring-mini"
TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "karate-tests"
REQUEST = "src/main/java/com/acme/shipments/ShipmentRequest.java"
_PLACEHOLDER_RE = re.compile(r"\$[a-z_]")


@pytest.fixture()
def analysed(tmp_path: Path) -> tuple[Path, Path, dict[str, Any], dict[str, Any]]:
    stack = tmp_path / "stack.json"
    env = tmp_path / "env-map.json"
    ledger = tmp_path / "flow-map.yaml"
    assert detect_main([str(SPRING), "--out", str(stack), "--skip-toolchain"]) == 0
    assert discover_main([str(SPRING), "--stack", str(stack), "--out-env", str(env),
                          "--out-ledger", str(ledger)]) == 0
    return ledger, env, load_ledger(ledger), read_json(env)


def _block(text: str, heading: str, fence: str) -> str:
    """The first fenced block of the given language after a heading line."""
    start = text.index(heading)
    open_tag = f"```{fence}\n"
    begin = text.index(open_tag, start) + len(open_tag)
    end = text.index("\n```", begin)
    return text[begin:end]


def test_prompt_files_exist_and_gitignore_hides_rendered_prompts() -> None:
    assert PROMPTS == ("trace", "rules", "generate")
    for name in PROMPTS:
        assert (PROMPTS_DIR / f"{name}.md").is_file()
    assert ".prompts/" in (TEMPLATE / ".gitignore").read_text(encoding="utf-8")


def test_trace_context_and_render(analysed: tuple[Path, Path, dict[str, Any], dict[str, Any]],
                                  tmp_path: Path) -> None:
    _, _, ledger, env_map = analysed
    context = build_context("trace", ledger, "POST /api/shipments", env_map, SPRING,
                            tmp_path / "karate-tests", None, None)
    assert context["slug"] == "post-api-shipments"
    assert context["cheat_sheet"].endswith("reference/stack-spring.md")
    assert Path(context["cheat_sheet"]).is_file()
    assert context["handler_path"].endswith("ShipmentController.java")
    assert "| PRICING_BASE_URL | downstream:pricing | PRICING_BASE_URL |" in context["roles"]
    assert context["downstreams"] == "pricing"
    assert context["auth_mode"] == "disabled"
    assert context["focus"] == ""
    text = render("trace", context, PROMPTS_DIR)
    assert "POST /api/shipments" in text
    assert "12 hops" in text and "unresolved" in text
    assert _PLACEHOLDER_RE.search(text) is None


def test_trace_example_output_merges_into_the_ledger(
    analysed: tuple[Path, Path, dict[str, Any], dict[str, Any]], tmp_path: Path,
) -> None:
    _, _, ledger, env_map = analysed
    context = build_context("trace", ledger, "POST /api/shipments", env_map, SPRING,
                            tmp_path / "karate-tests", None, None)
    text = render("trace", context, PROMPTS_DIR)
    example = json.loads(_block(text, "## Example output", "json"))
    assert example["id"] == "POST /api/shipments"
    assert merge_entry(ledger, example) == 0
    entry = find_entry(ledger, "POST /api/shipments")
    assert entry["status"]["traced"] is True
    assert {e["kind"] for e in entry["exits"]} == {"db-write", "amq-publish", "http-out"}


def test_focus_adds_a_start_at_paragraph(
    analysed: tuple[Path, Path, dict[str, Any], dict[str, Any]], tmp_path: Path,
) -> None:
    _, _, ledger, env_map = analysed
    context = build_context("trace", ledger, "POST /api/shipments", env_map, SPRING,
                            tmp_path / "karate-tests", None,
                            "src/main/java/com/acme/shipments/ShipmentService.java:30")
    assert "Start at" in context["focus"] and "ShipmentService.java:30" in context["focus"]
    assert "ShipmentService.java:30" in render("trace", context, PROMPTS_DIR)


def test_rules_context_needs_a_source_and_its_example_rows_load(
    analysed: tuple[Path, Path, dict[str, Any], dict[str, Any]], tmp_path: Path,
) -> None:
    _, _, ledger, env_map = analysed
    tests_dir = tmp_path / "karate-tests"
    with pytest.raises(KbError, match="--source"):
        build_context("rules", ledger, "POST /api/shipments", env_map, SPRING, tests_dir,
                      None, None)
    context = build_context("rules", ledger, "POST /api/shipments", None, SPRING, tests_dir,
                            REQUEST, None)
    assert context["source"] == REQUEST
    assert context["source_path"].endswith(REQUEST)
    assert context["candidates_csv"].endswith("rules/post-api-shipments.candidates.csv")
    assert "not present" in context["candidates_note"]
    assert context["rows_csv"].endswith("rules/post-api-shipments.rows.csv")
    text = render("rules", context, PROMPTS_DIR)
    assert "rule_id,field,mutation,value,expected_status,expected_code," in text
    assert _PLACEHOLDER_RE.search(text) is None
    rows = tmp_path / "rows.csv"
    rows.write_text(_block(text, "## Example rows file", "csv") + "\n", encoding="utf-8")
    assert add_rows(tests_dir, ledger, "POST /api/shipments", rows) >= 3
    assert find_entry(ledger, "POST /api/shipments")["rules"]["file"] == (
        "rules/post-api-shipments.csv"
    )


def test_rules_candidates_note_counts_existing_rows(
    analysed: tuple[Path, Path, dict[str, Any], dict[str, Any]], tmp_path: Path,
) -> None:
    _, _, ledger, _ = analysed
    tests_dir = tmp_path / "karate-tests"
    candidates = tests_dir / "rules" / "post-api-shipments.candidates.csv"
    candidates.parent.mkdir(parents=True)
    candidates.write_text(
        "rule_id,field,mutation,value,expected_status,expected_code,expected_message_contains,source\n"
        ",reference,missing,,400,,,x:1\n,reference,empty,,400,,,x:1\n", encoding="utf-8")
    context = build_context("rules", ledger, "POST /api/shipments", None, SPRING, tests_dir,
                            REQUEST, None)
    assert "2 candidate rows" in context["candidates_note"]


def test_generate_context_and_example_feature_is_parallel_safe(
    analysed: tuple[Path, Path, dict[str, Any], dict[str, Any]], tmp_path: Path,
) -> None:
    _, _, ledger, env_map = analysed
    find_entry(ledger, "POST /api/shipments")["rules"].update(
        {"file": "rules/post-api-shipments.csv", "count": 9})
    context = build_context("generate", ledger, "POST /api/shipments", env_map, SPRING,
                            tmp_path / "karate-tests", None, None)
    assert context["feature_file"] == "features/post-api-shipments.feature"
    assert context["seed_file"] == "seed/post-api-shipments.sql"
    assert context["example_file"] == "seed/examples/post-api-shipments.json"
    assert context["rules_file"] == "rules/post-api-shipments.csv" and context["rules_count"] == "9"
    assert "do not send an Authorization header" in context["auth_instruction"]
    assert "Given url appBaseUrl" in context["entry_instruction"]
    text = render("generate", context, PROMPTS_DIR)
    assert "@parallel=false" in text and "Jms.await(" in text and "Stubs.verify(" in text
    assert _PLACEHOLDER_RE.search(text) is None
    feature = _block(text, "## Feature shape", "gherkin")
    parsed = parse_feature(feature)
    assert len(parsed.scenarios()) >= 3
    assert unsafe_parallel_scenarios(feature) == []
    summary = json.loads(_block(text, "## Reply", "json"))
    assert set(summary) >= {"features", "stubs", "seeds"}


def test_generate_context_for_amq_and_jwks(
    analysed: tuple[Path, Path, dict[str, Any], dict[str, Any]], tmp_path: Path,
) -> None:
    _, _, ledger, env_map = analysed
    ledger["app"]["auth"] = {"mode": "jwks", "keys": ["AUTH_ISSUER_URI"]}
    context = build_context("generate", ledger, "amq shipment.requested", env_map, SPRING,
                            tmp_path / "karate-tests", None, None)
    assert "Jwt.token(" in context["auth_instruction"]
    assert "Jms.publish('shipment.requested'" in context["entry_instruction"]
    assert "Never `Jms.watch('shipment.requested')`" in context["entry_instruction"]


def test_render_reports_a_missing_placeholder(tmp_path: Path) -> None:
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "trace.md").write_text("Entry $entry_id needs $nope", encoding="utf-8")
    with pytest.raises(KbError, match="nope"):
        render("trace", {"entry_id": "x"}, prompts)


def test_cli_render_writes_the_prompt_file(
    analysed: tuple[Path, Path, dict[str, Any], dict[str, Any]], tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ledger_path, env_path, _, _ = analysed
    out = tmp_path / "karate-tests" / ".prompts" / "trace-post-api-shipments.md"
    assert run_cli(main, ["render", "--prompt", "trace", "--ledger", str(ledger_path),
                          "--env", str(env_path), "--entry", "POST /api/shipments",
                          "--repo", str(SPRING), "--out", str(out)]) == EXIT_OK
    assert out.is_file() and "POST /api/shipments" in out.read_text(encoding="utf-8")
    assert str(out) in capsys.readouterr().out
    assert run_cli(main, ["render", "--prompt", "trace", "--ledger", str(ledger_path),
                          "--entry", "POST /api/shipments", "--repo", str(SPRING),
                          "--out", str(out)]) == 2
    assert run_cli(main, ["render", "--prompt", "generate", "--ledger", str(ledger_path),
                          "--env", str(env_path), "--entry", "nope", "--repo", str(SPRING),
                          "--out", str(out)]) == 2
```

- [ ] **Step 2: Run it to confirm the import fails**

Run: `pytest skills/karate-bootstrap/tests/test_kb_prompt.py -q`
Expected: `ModuleNotFoundError: No module named 'kb_prompt'`.

- [ ] **Step 3: Add `.prompts/` to the template's `.gitignore`**

`skills/karate-bootstrap/templates/karate-tests/.gitignore` becomes:

```
target/
.prompts/
```

- [ ] **Step 4: Create `scripts/kb_prompt.py`**

```python
"""Render subagent prompts for karate-bootstrap (design spec 5.3, 5.4, 5.6, 9).

Each prompt is a ``string.Template`` file under ``prompts/`` filled with one ledger entry,
the stack cheat sheet path, the env-map role table and the file paths the subagent must
use. The main agent never composes a prompt freehand: it renders one with this script and
passes the file path to the Agent tool.

Usage:
    python scripts/kb_prompt.py render --prompt trace|rules|generate \
        --ledger karate-tests/flow-map.yaml --entry <id> --repo <root> \
        --out karate-tests/.prompts/<name>.md [--env karate-tests/env-map.json] \
        [--tests-dir karate-tests] [--source <file>] [--focus <file:line>] [--prompts-dir DIR]

``--env`` is required for trace and generate (host keys and downstream names); ``--source``
is required for rules (the validation file the subagent reads). ``--focus`` re-renders a
trace prompt that starts at an unresolved hop.

Exit codes: 0 ok, 2 bad arguments or an unknown entry, 5 when a prompt file or input is missing.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from string import Template
from typing import Any

from flow_map import find_entry, load_ledger
from kb_common import EXIT_MISSING_OUTPUT, EXIT_OK, KbError, read_json, read_text, run_cli
from kb_rules import slug_for

PROMPTS = ("trace", "rules", "generate")
SKILL_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = SKILL_DIR / "prompts"
CSV_HEADER_LINE = ("rule_id,field,mutation,value,expected_status,expected_code,"
                   "expected_message_contains,source")


def _posix(path: Path) -> str:
    return path.resolve().as_posix()


def roles_table(env_map: dict[str, Any] | None) -> str:
    if env_map is None:
        return "(no env-map given)"
    lines = ["| key | role | env var |", "|---|---|---|"]
    for key in env_map.get("keys", []):
        lines.append(f"| {key.get('key')} | {key.get('role')} | {key.get('env_var') or ''} |")
    return "\n".join(lines)


def downstream_names(env_map: dict[str, Any] | None) -> str:
    names: list[str] = []
    for key in (env_map or {}).get("keys", []):
        role = str(key.get("role", ""))
        if role.startswith("downstream:"):
            name = role.split(":", 1)[1]
            if name not in names:
                names.append(name)
    return ", ".join(names) if names else "none"


def auth_instruction(mode: str) -> str:
    if mode == "jwks":
        return ("Auth mode is jwks: the harness serves a JWKS the app trusts. Add "
                "`* header Authorization = 'Bearer ' + Jwt.token({ sub: 'test-user' })` to the "
                "Background and extend the claims map with whatever roles the handler checks.")
    if mode == "disabled":
        return ("Auth mode is disabled: the harness turns the app's auth switch off, so do not "
                "send an Authorization header and do not write 401 or 403 scenarios.")
    if mode == "blocked":
        return ("Auth mode is blocked: no token can satisfy the app. Test only the entry points "
                "the trace marked as not requiring auth; do not send an Authorization header.")
    return "Auth mode is none: the app has no auth; do not send an Authorization header."


def entry_instruction(entry: dict[str, Any]) -> str:
    if entry.get("kind") == "amq-subscribe":
        destination = entry.get("destination")
        return (f"This entry is an AMQ subscription on `{destination}`. Drive it with "
                f"`Jms.publish('{destination}', body, {{}})` and assert the exits with "
                f"`Db.awaitRow` and `Jms.await` on the destinations the trace lists. Never "
                f"`Jms.watch('{destination}')`: the harness would compete with the app for the "
                f"message on an anycast queue.")
    return (f"This entry is HTTP {entry.get('method')} {entry.get('path')}. Every scenario "
            f"starts with `Given url appBaseUrl` and `And path '{entry.get('path')}'`, sends "
            f"the request, then asserts status, body and the exits.")


def candidates_note(path: Path) -> str:
    if not path.is_file():
        return ("not present (no declarative validators were found for this entry); every row "
                "comes from your reading of the source")
    rows = [line for line in read_text(path).splitlines() if line.strip()]
    return f"present with {max(0, len(rows) - 1)} candidate rows to confirm or drop"


def build_context(prompt: str, ledger: dict[str, Any], entry_id: str,
                  env_map: dict[str, Any] | None, repo: Path, tests_dir: Path,
                  source: str | None, focus: str | None) -> dict[str, str]:
    if prompt not in PROMPTS:
        raise KbError(f"unknown prompt {prompt!r}; expected one of {PROMPTS}")
    if prompt in ("trace", "generate") and env_map is None:
        raise KbError(f"prompt {prompt} needs --env (host keys and downstream names)")
    if prompt == "rules" and not source:
        raise KbError("prompt rules needs --source (the validation file to read)")
    entry = find_entry(ledger, entry_id)
    stack = str(ledger.get("stack", {}).get("framework", "unknown"))
    cheat_sheet = SKILL_DIR / str(ledger.get("stack", {}).get("cheat_sheet")
                                  or f"reference/stack-{stack}.md")
    slug = slug_for(entry_id)
    handler = str(entry.get("handler") or "")
    handler_file = handler.rsplit(":", 1)[0] if handler else ""
    rules = entry.get("rules") or {}
    auth_mode = str((ledger.get("app", {}).get("auth") or {}).get("mode", "none"))
    focus_text = ""
    if focus:
        focus_text = (f"\nStart at `{focus}`: a previous trace could not follow the code there. "
                      f"Trace only from that location onward and report the rest of the path; "
                      f"keep every exit you find with its own file:line.\n")
    context = {
        "prompt_kind": prompt,
        "entry_id": entry_id,
        "slug": slug,
        "kind": str(entry.get("kind", "")),
        "handler": handler,
        "handler_path": _posix(repo / handler_file) if handler_file else "",
        "stack": stack,
        "cheat_sheet": _posix(cheat_sheet),
        "repo": _posix(repo),
        "tests_dir": _posix(tests_dir),
        "entry_json": json.dumps(entry, indent=2),
        "exits_json": json.dumps(entry.get("exits", []), indent=2),
        "reads_json": json.dumps(entry.get("reads", []), indent=2),
        "responses_json": json.dumps(entry.get("responses", []), indent=2),
        "roles": roles_table(env_map),
        "downstreams": downstream_names(env_map),
        "auth_mode": auth_mode,
        "auth_instruction": auth_instruction(auth_mode),
        "entry_instruction": entry_instruction(entry),
        "focus": focus_text,
        "source": source or "",
        "source_path": _posix(repo / source) if source else "",
        "candidates_csv": _posix(tests_dir / "rules" / f"{slug}.candidates.csv"),
        "candidates_note": candidates_note(tests_dir / "rules" / f"{slug}.candidates.csv"),
        "rows_csv": _posix(tests_dir / "rules" / f"{slug}.rows.csv"),
        "csv_header": CSV_HEADER_LINE,
        "rules_file": str(rules.get("file") or "none"),
        "rules_count": str(rules.get("count") or 0),
        "feature_file": f"features/{slug}.feature",
        "seed_file": f"seed/{slug}.sql",
        "example_file": f"seed/examples/{slug}.json",
        "stubs_dir": "stubs",
    }
    return context


def render(prompt: str, context: dict[str, str], prompts_dir: Path) -> str:
    path = prompts_dir / f"{prompt}.md"
    if not path.is_file():
        raise KbError(f"prompt file missing: {path}", EXIT_MISSING_OUTPUT)
    try:
        return Template(read_text(path)).substitute(context)
    except KeyError as err:
        raise KbError(f"{path}: placeholder {err.args[0]!r} has no value") from err
    except ValueError as err:
        raise KbError(f"{path}: bad placeholder syntax ({err}); write a literal $ as $$") from err


def _cmd_render(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    env_map = read_json(args.env) if args.env else None
    tests_dir: Path = args.tests_dir if args.tests_dir else args.repo / "karate-tests"
    context = build_context(args.prompt, ledger, args.entry, env_map, args.repo, tests_dir,
                            args.source, args.focus)
    text = render(args.prompt, context, args.prompts_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"rendered {args.prompt} prompt for {args.entry} -> {args.out}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a subagent prompt from prompts/<name>.md")
    sub = parser.add_subparsers(dest="command", required=True)
    rend = sub.add_parser("render", help="Fill a prompt template with one ledger entry")
    rend.add_argument("--prompt", choices=PROMPTS, required=True)
    rend.add_argument("--ledger", type=Path, required=True, help="flow-map.yaml")
    rend.add_argument("--entry", required=True, help="entry id from the ledger")
    rend.add_argument("--repo", type=Path, required=True, help="service root")
    rend.add_argument("--out", type=Path, required=True, help="prompt file to write")
    rend.add_argument("--env", type=Path, default=None, help="env-map.json (trace, generate)")
    rend.add_argument("--tests-dir", type=Path, default=None,
                      help="karate-tests directory (default <repo>/karate-tests)")
    rend.add_argument("--source", default=None, help="validation source file (rules)")
    rend.add_argument("--focus", default=None, help="file:line to start a narrower trace at")
    rend.add_argument("--prompts-dir", type=Path, default=PROMPTS_DIR,
                      help="directory holding trace.md, rules.md, generate.md")
    rend.set_defaults(func=_cmd_render)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(run_cli(main))
```

- [ ] **Step 5: Write `prompts/trace.md`**

Everything below the heading is the file. `$name` are template placeholders; there is no literal dollar sign anywhere else in the file.

````markdown
# Trace one entry point: $entry_id

You are a read-only code tracer working for the karate-bootstrap skill. Starting at one handler,
follow every call path until it reaches an exit and report what you found as JSON. You never
edit files. You never guess: an exit you cannot see in the code goes in `unresolved`.

## Inputs

- Repository root: `$repo`
- Stack: `$stack`. Read the cheat sheet first; its marker tables say what a database write, a
  message publish and an outbound HTTP call look like in this stack, how table names resolve,
  and which tokens the `verify-refs` gate accepts on a `via` line: `$cheat_sheet`
- Handler: `$handler` (file `$handler_path`)
- The ledger entry as it stands (untraced fields are empty):

```json
$entry_json
```

- Config keys and their roles. Use the `env var` column as the `host_key` of every `http-out`
  exit and `http-in` read:

$roles
$focus

## Method

1. Open the handler at the line given. Note the request type, path variables and the validation
   it applies (annotations on the request type, validator classes, explicit checks).
2. Follow every call the handler makes, depth first, to at most 12 hops. A branch stops at the
   first of: a database write, a message publish, an outbound HTTP call, a response return, or a
   third-party library boundary (framework, ORM or client internals).
3. For each stop, record the file and line of the statement that performs it, relative to the
   repository root, as `file:line`. The `verify-refs` gate opens that file and requires a cheat
   sheet marker token on that line or within three lines. A `via` that points at a declaration,
   an import or a comment fails the trace.
4. Record `reads`: database reads (`db-read` with the table) and inbound HTTP responses the code
   consumes (`http-in` with the `host_key`, method and path of the downstream call). They become
   seeds and stubs.
5. Record `responses`: every distinct status the handler can return with a short `when`. Mark
   validation branches with `"rules": true`. Give `via` for branches that come from explicit code
   such as a throw or an early return.
6. Record `rules.sources`: every file that holds validation for this entry (the request DTO with
   its annotations, validator classes, service-layer checks), each with `"scanned": false`.
7. Resolve table names from the entity mapping (`@Table`, `[Table]`, `DbSet` name,
   `__tablename__`), not from the class name, unless the cheat sheet says the default mapping
   applies. Resolve destination names from the literal in the code or the config key that holds
   it; `queue` unless the code clearly uses a topic.
8. Anything you cannot follow (reflection, dynamic dispatch, generated code, the hop cap) goes in
   `unresolved` with the `file:line` where you stopped and a one-line reason.
9. An entry that writes nothing (a pure read) returns `"exits": []` with a non-empty
   `exits_none_reason`.
10. `auth`: `required` when the handler or its class demands authentication, `none` when it is
    open, `unknown` if you cannot tell.

## Output contract

Reply with JSON only: no prose before or after it. Field rules:

- `id`: exactly `$entry_id`.
- `exits[]`: `kind` is `db-write` (`table`, `op` = insert|update|delete), `amq-publish`
  (`destination`, `type` = queue|topic) or `http-out` (`host_key`, `method`, `path`); every exit
  has `via`.
- `reads[]`: `kind` is `db-read` (`table`, `via`) or `http-in` (`host_key`, `method`, `path`).
- `responses[]`: `status`, `when`, optional `rules` and `via`; `testable: false` on 401/403 when
  auth is switched off in tests.
- `request`: `content_type`, `schema_ref` (the request type's file), `example` =
  `seed/examples/$slug.json` (the generate step writes it).
- `type`: for an AMQ entry only, `queue` or `topic`.
- `unresolved[]`: `at` (`file:line`) and `reason`.

## Example output

The shape, with illustrative values; every path in a real answer must exist in this repository.

```json
{
  "id": "$entry_id",
  "auth": "required",
  "request": {
    "content_type": "application/json",
    "schema_ref": "src/main/java/com/acme/deals/DealRequest.java",
    "example": "seed/examples/$slug.json"
  },
  "responses": [
    { "status": 201, "when": "happy" },
    { "status": 400, "when": "validation", "rules": true },
    { "status": 404, "when": "counterparty not found", "via": "src/main/java/com/acme/deals/DealService.java:41" }
  ],
  "reads": [
    { "kind": "db-read", "table": "counterparties", "via": "src/main/java/com/acme/deals/CounterpartyRepository.java:18" },
    { "kind": "http-in", "host_key": "PRICING_BASE_URL", "method": "GET", "path": "/prices/{product}" }
  ],
  "exits": [
    { "kind": "db-write", "table": "deals", "op": "insert", "via": "src/main/java/com/acme/deals/DealService.java:52" },
    { "kind": "amq-publish", "destination": "deal.created", "type": "queue", "via": "src/main/java/com/acme/deals/DealService.java:54" },
    { "kind": "http-out", "host_key": "PRICING_BASE_URL", "method": "GET", "path": "/prices/{product}", "via": "src/main/java/com/acme/deals/PricingClient.java:27" }
  ],
  "rules": {
    "sources": [
      { "file": "src/main/java/com/acme/deals/DealRequest.java", "scanned": false },
      { "file": "src/main/java/com/acme/deals/DealService.java", "scanned": false }
    ]
  },
  "unresolved": []
}
```
````

- [ ] **Step 6: Write `prompts/rules.md`**

````markdown
# Validation rules for $entry_id from `$source`

You are a read-only reviewer working for the karate-bootstrap skill. Read one validation source
and produce the complete list of validation rules it applies to the request of this entry point,
as CSV rows the skill turns into a data-driven Karate outline. You never edit application code.

## Inputs

- Repository root: `$repo`
- Source to read: `$source` (file `$source_path`)
- Entry point: `$entry_id` (`$kind`, handler `$handler`)
- Candidate rows extracted from declarative validators: `$candidates_csv`, $candidates_note.
- Where to write your rows: `$rows_csv` (create the directory if needed)
- The entry's responses from the trace, for status codes and which branches are validation:

```json
$responses_json
```

## What a row means

Each row is one way a request can fail validation. The skill generates a scenario per row that
takes a valid base request, applies `mutation` to `field` with `value`, sends it, and expects
`expected_status`, a body whose error code equals `expected_code` (empty means do not check) and
a message containing `expected_message_contains` (empty means do not check).

CSV header, exactly:

```
$csv_header
```

`mutation` is one of `missing`, `null`, `empty`, `too_long`, `too_short`, `invalid_format`,
`out_of_range`, `invalid_enum`, `cross_field`. Boundary conventions: `too_long` uses max+1,
`too_short` uses min-1, `out_of_range` uses the first excluded integer (0 for "greater than 0"),
`invalid_format` uses the literal `!!` unless the field needs a specific shape, `invalid_enum`
uses `NOT_A_VALUE`, `cross_field` carries a short expression such as `before:tradeDate` that the
generate step turns into a concrete pair of values. `rule_id` stays empty; the skill assigns it.
`source` is `file:line` of the check.

## Method

1. Read the source file completely. Confirm every candidate row you agree with, drop the ones the
   code does not enforce, and correct their values.
2. Add the rules declarative extraction cannot see: imperative checks (`if ... throw`, guard
   clauses, service-layer validation), cross-field rules, enum membership, conditional
   requirements. One row per distinct failure.
3. Fill `expected_code` and `expected_message_contains` from the code that builds the error
   response (an exception mapper, a problem-details factory, a validator message). Leave them
   empty when the message is framework-generated and you cannot see it.
4. Use the status the trace recorded for validation responses; 400 for Bean Validation,
   FluentValidation and data annotations; 422 for FastAPI or Pydantic unless the code maps it.
5. Write the rows file with the exact header above. Do not edit `rules/*.csv` yourself: the skill
   appends your rows with `kb_rules.py add`, de-duplicating on field, mutation and value.

## Reply

After writing the file, reply with JSON only:

```json
{ "rows_csv": "$rows_csv", "rows": 12, "dropped_candidates": 1, "notes": "one-line summary" }
```

## Example rows file

```csv
$csv_header
,reference,missing,,400,VALIDATION,reference is required,src/main/java/com/acme/shipments/ShipmentRequest.java:8
,reference,too_long,51,400,VALIDATION,reference must be at most 50,src/main/java/com/acme/shipments/ShipmentRequest.java:9
,weightKg,out_of_range,0,400,VALIDATION,weight must be positive,src/main/java/com/acme/shipments/ShipmentRequest.java:13
,countryCode,invalid_format,!!,400,VALIDATION,countryCode must match,src/main/java/com/acme/shipments/ShipmentRequest.java:17
,weightKg,out_of_range,1001,400,LIMIT,weight exceeds 1000kg,src/main/java/com/acme/shipments/ShipmentService.java:28
```
````

- [ ] **Step 7: Write `prompts/generate.md`**

````markdown
# Generate the Karate feature for $entry_id

You are a test author working for the karate-bootstrap skill. Write the feature file, stub
mappings, seed data and example request for one entry point, under `$tests_dir` only. The suite
documents observed behaviour of the application as it is today; it does not judge it. You never
touch application source, the Dockerfile or anything outside the tests directory.

## Inputs

- Repository root: `$repo`
- Tests directory: `$tests_dir`
- Entry point, fully traced:

```json
$entry_json
```

- Validation rules file: `$rules_file` ($rules_count rows). When it is `none`, write no `@rules`
  outline.
- Downstream services the app calls, each stubbed by WireMock under
  `http://wiremock:8080/<name>`: $downstreams
- Auth: $auth_instruction
- Entry kind: $entry_instruction

## Files to write

| File | Content |
|------|---------|
| `$feature_file` | the feature below |
| `$example_file` | a valid base request body as JSON (for AMQ entries, a valid message body) |
| `$seed_file` | SQL inserts the feature needs beyond what it creates itself (reference rows the handler reads); additive only, unique keys, `-- comments` allowed |
| `$stubs_dir/<downstream>/default.json` | WireMock mappings for every `http-out` exit and `http-in` read, one file per downstream, `{"mappings":[...]}`; add or extend, never delete another entry's mappings |
| `$stubs_dir/<downstream>/<error>.json` | only when a failure path needs a different downstream answer and cannot be driven by request data |

## Rules that keep the suite green in parallel (design spec 5.6)

1. Scenarios run four at a time against one app, one database, one broker and one WireMock.
   Nothing may depend on a global reset.
2. Every scenario derives a unique value in its Background (`* def uid = java.util.UUID.randomUUID() + ''`),
   puts it in the request, and asserts rows and messages by it.
3. Stubs are suite-level and discriminate by request data (path parameter, query, body) with
   `priority`. A failure path is driven by a reserved input the mapping documents, for example a
   product code `ERR-500` answered with a 500 by a low-priority mapping. Every `urlPath` starts
   with `/<downstream>`.
4. Messages are matched by content: `Jms.await('deal.created', 5000, { dealId: response.id })`.
5. Downstream calls are verified by unique data: `Stubs.verify('GET', '/pricing/rates/' + uid, 1)`
   when the path carries it, else `Stubs.verify('POST', '/pricing/quotes', base.externalId, 1)`
   which matches on the request body.
6. A scenario that must reset shared state (`Stubs.reset`, `Stubs.load`, `Db.truncate`, or the
   `stubs:`/`truncate:` arguments of `reset.feature`) carries `@parallel=false` and restores the
   default stubs before it ends. The generated gate rejects such calls without the tag.
7. Validation outlines never write; they read `$rules_file` through the `mutate` helper.
8. Do not write scenarios for 401 or 403 unless the auth instruction above says tokens are in
   play. Do not write a scenario for a response the trace did not record.

## Harness API (globals in every feature)

- `appBaseUrl`; `mutate(base, field, mutation, value)`; `skipContainers`.
- `Db.run(path)`, `Db.row(table, where)`, `Db.awaitRow(table, where, timeoutMs)`,
  `Db.count(table, where)`, `Db.truncate(tables)`.
- `Jms.watch(dest)`, `Jms.await(dest, timeoutMs)`, `Jms.await(dest, timeoutMs, matchMap)`,
  `Jms.publish(dest, body, headers)`.
- `Stubs.reset()`, `Stubs.load(path)`, `Stubs.verify(method, urlPath, times)`,
  `Stubs.verify(method, urlPath, bodyContains, times)`.
- `Jwt.token(claims)`.
- `call read('classpath:common/reset.feature') { watch: [...], truncate: [...], seed: 'classpath:seed/x.sql', stubs: [...] }`
  applied in that order; `seed` is additive and parallel-safe, `truncate` and `stubs` need
  `@parallel=false`.

## Feature shape

Adapt this shape to the entry. Tags: `@smoke` on the happy path, `@error` on failure paths,
`@rules` on the validation outline, `@amq` on AMQ-driven features, `@known-defect` never (the
fix loop adds it).

```gherkin
@smoke
Feature: POST /api/deals

Background:
  * def uid = java.util.UUID.randomUUID() + ''
  * call read('classpath:common/reset.feature') { watch: ['deal.created'] }
  * def base = read('classpath:seed/examples/post-api-deals.json')
  * set base.externalId = 'EXT-' + uid

Scenario: creates a deal, writes deals and deal_audit, publishes deal.created
  Given url appBaseUrl
  And path '/api/deals'
  And request base
  When method post
  Then status 201
  And match response contains { id: '#uuid', status: 'PENDING' }
  * def row = Db.row('deals', { external_id: base.externalId })
  * match row.status == 'PENDING'
  * match Db.count('deal_audit', { deal_id: row.id }) == 1
  * def msg = Jms.await('deal.created', 5000, { dealId: response.id })
  * match msg.body.externalId == base.externalId
  * Stubs.verify('POST', '/pricing/quotes', base.externalId, 1)

@error
Scenario: unknown counterparty returns 404
  * set base.counterpartyId = 'CP-MISSING-' + uid
  Given url appBaseUrl
  And path '/api/deals'
  And request base
  When method post
  Then status 404

@rules
Scenario Outline: validation rule <rule_id> on <field>
  * def payload = mutate(base, '<field>', '<mutation>', '<value>')
  Given url appBaseUrl
  And path '/api/deals'
  And request payload
  When method post
  Then status <expected_status>
  And match response.code == '<expected_code>'
  And match response.message contains '<expected_message_contains>'

  Examples:
    | read('classpath:rules/post-api-deals.csv') |
```

## Stub mapping shape

One file per downstream, suite-level. `priority` 1 wins over 5.

```json
{
  "mappings": [
    {
      "priority": 5,
      "request": { "method": "POST", "urlPath": "/pricing/quotes" },
      "response": { "status": 200, "headers": { "Content-Type": "application/json" },
                    "jsonBody": { "price": 42.5, "currency": "USD" } }
    },
    {
      "priority": 1,
      "request": { "method": "POST", "urlPath": "/pricing/quotes",
                   "bodyPatterns": [ { "contains": "ERR-500" } ] },
      "response": { "status": 500, "jsonBody": { "error": "pricing unavailable" } }
    }
  ]
}
```

## Reply

After writing the files, reply with JSON only, listing every path you wrote relative to
`$tests_dir` (the skill records them on the ledger with `flow_map.py mark`):

```json
{
  "features": ["$feature_file"],
  "stubs": ["stubs/pricing/default.json"],
  "seeds": ["$seed_file", "$example_file"],
  "notes": "one line on anything the trace did not cover"
}
```
````

- [ ] **Step 8: Run the prompt tests**

Run: `pytest skills/karate-bootstrap/tests/test_kb_prompt.py -q`
Expected: 10 passed. If `test_trace_example_output_merges_into_the_ledger` fails on `via`, the example's paths are not `file:line`; if `test_rules_...` fails inside `add_rows`, a row's mutation or status is outside the enum; fix the prompt text, not the test.

- [ ] **Step 9: Full gate and the spec command's help**

Run: `pytest -q` then `ruff check .` then `mypy` then `python skills/karate-bootstrap/scripts/kb_prompt.py render --help`
Expected: green; help lists `--prompt {trace,rules,generate}`, `--ledger`, `--entry`, `--repo`, `--out`, `--env`, `--tests-dir`, `--source`, `--focus`, `--prompts-dir`. [[docs-in-sync]]

- [ ] **Step 10: Commit**

```bash
git add skills/karate-bootstrap/scripts/kb_prompt.py skills/karate-bootstrap/prompts/trace.md skills/karate-bootstrap/prompts/rules.md skills/karate-bootstrap/prompts/generate.md skills/karate-bootstrap/templates/karate-tests/.gitignore skills/karate-bootstrap/tests/test_kb_prompt.py
git commit -m "feat(karate-bootstrap): kb_prompt renders the trace, rules and generate prompts

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Stack cheat sheets

**Confidence:** 91%. The sheets are documentation for the trace and rules subagents. Their marker and token tables are derived from `markers.py` (read at plan time), the config-key conventions from `discover.py` (`assign_role`, `_DB_KEY`, `_AMQ_KEY`, `_AUTH_KEY`, `_ON_BOOT_KEYS`, `MANIFEST_NAMES`), and the rest from spec section 8. A test asserts every `tokens_for(stack, kind)` token appears verbatim in the stack's sheet and that each sheet carries the required headings, so a marker added to `markers.py` without its sheet fails CI.

**Files:**
- Create: `skills/karate-bootstrap/reference/stack-spring.md`, `stack-quarkus.md`, `stack-aspnetcore.md`, `stack-python.md`
- Test: `skills/karate-bootstrap/tests/test_kb_reference.py`

**Interfaces:**
- Consumes: `markers.STACKS`, `markers.KINDS`, `markers.tokens_for(stack, kind)`, `markers.CHEAT_SHEET`.
- Produces for Task 6 and the prompts: `reference/stack-<stack>.md`, each with the headings `## Entry points`, `## Exits: database writes`, `## Exits: message publish`, `## Subscriptions`, `## Exits: outbound HTTP`, `## Reads`, `## Table and destination names`, `## Config keys and roles`, `## Readiness`, `## Auth switches`, `## Validation`, `## Marker tokens verify-refs accepts`.

- [ ] **Step 1: Write `tests/test_kb_reference.py`**

```python
from __future__ import annotations

from pathlib import Path

import pytest
from markers import CHEAT_SHEET, KINDS, STACKS, tokens_for

SKILL = Path(__file__).resolve().parent.parent
REFERENCE = SKILL / "reference"

STACK_HEADINGS = (
    "## Entry points",
    "## Exits: database writes",
    "## Exits: message publish",
    "## Subscriptions",
    "## Exits: outbound HTTP",
    "## Reads",
    "## Table and destination names",
    "## Config keys and roles",
    "## Readiness",
    "## Auth switches",
    "## Validation",
    "## Marker tokens verify-refs accepts",
)


@pytest.mark.parametrize("stack", STACKS)
def test_stack_sheet_exists_where_the_ledger_points(stack: str) -> None:
    path = SKILL / CHEAT_SHEET[stack]
    assert path == REFERENCE / f"stack-{stack}.md"
    assert path.is_file()


@pytest.mark.parametrize("stack", STACKS)
def test_stack_sheet_has_every_heading(stack: str) -> None:
    text = (REFERENCE / f"stack-{stack}.md").read_text(encoding="utf-8")
    for heading in STACK_HEADINGS:
        assert heading in text, f"{stack}: missing {heading}"


@pytest.mark.parametrize("stack", STACKS)
def test_stack_sheet_lists_every_marker_token(stack: str) -> None:
    text = (REFERENCE / f"stack-{stack}.md").read_text(encoding="utf-8")
    tokens_section = text[text.index("## Marker tokens verify-refs accepts"):]
    for kind in KINDS:
        for token in tokens_for(stack, kind):
            assert f"`{token}`" in tokens_section, f"{stack}/{kind}: token {token!r} not listed"
```

- [ ] **Step 2: Run it to see the four missing sheets**

Run: `pytest skills/karate-bootstrap/tests/test_kb_reference.py -q`
Expected: 12 failures, all `AssertionError` or `FileNotFoundError` on the missing sheets.

- [ ] **Step 3: Write `reference/stack-spring.md`**

````markdown
# Spring Boot cheat sheet

Loaded for `stack.framework: spring`. Marker regexes live in `scripts/markers.py`; this sheet
explains them for a tracer and lists the tokens the `verify-refs` gate accepts.

## Entry points

- `@RestController` classes; the class-level `@RequestMapping("/prefix")` prefixes every method
  path.
- Methods: `@GetMapping`, `@PostMapping`, `@PutMapping`, `@DeleteMapping`, `@PatchMapping`, with
  the path in `value` or `path` or as the bare string; `@RequestMapping(method = ...)` also
  counts. Path variables stay as `{id}` in the entry id.
- Entry id: `<METHOD> <full path>`, for example `POST /api/shipments`. Handler is the annotated
  method's line.

## Exits: database writes

- Spring Data repositories: `save`, `saveAll`, `saveAndFlush`, `delete`, `deleteById`,
  `deleteAll`, `deleteAllById`; `op` is `insert` for a new entity, `update` for a loaded one,
  `delete` for the delete family.
- JPA: `EntityManager.persist`, `merge`, `remove`; `@Modifying @Query` methods (`op` from the
  query verb).
- JDBC: `JdbcTemplate.update`, `batchUpdate` (`op` from the SQL verb).
- Hibernate `Session.save/update/delete` in older code.

## Exits: message publish

- `JmsTemplate.convertAndSend(destination, payload)` and `send(destination, creator)`; the
  destination is the first argument or a `@Value` config key. Spring's default is a queue;
  `spring.jms.pub-sub-domain=true` makes every destination a topic.

## Subscriptions

- `@JmsListener(destination = "name")` methods are `amq-subscribe` entries with id
  `amq <name>`; `containerFactory` with pub-sub enabled means `type: topic`.

## Exits: outbound HTTP

- `RestTemplate` (`getForObject`, `postForEntity`, `exchange`), `WebClient`, `RestClient`,
  `@FeignClient` interfaces. `host_key` is the env var behind the base URL (`@Value`,
  `@ConfigurationProperties`, or the Feign `url` attribute). Path as the literal with
  `{placeholders}`.

## Reads

- Repository `findBy*`, `findById`, `existsBy*`, `count*`; `EntityManager.find`; JDBC
  `query*`. Record `db-read` with the table.
- The response of any outbound call the code consumes is an `http-in` read.

## Table and destination names

- Entity classes: `@Table(name = "...")` wins; otherwise Spring's default naming turns
  `ShipmentAudit` into `shipment_audit`. `@Entity(name)` names the entity, not the table.
- Destinations: literal strings or config keys under `spring.artemis.*` and custom
  `*.queue`/`*.topic` keys.

## Config keys and roles

- Files: `application.yml`, `application.yaml`, `application.properties` (base profile only;
  `application-<profile>.*` and `src/test` variants are ignored). Manifest env wins over the
  Dockerfile which wins over config placeholders.
- `db`: `spring.datasource.url|username|password`, `spring.jpa.*`, `hibernate.connection.*`,
  any `jdbc:` placeholder. `amq`: `spring.artemis.broker-url|user|password`, `spring.jms.*`,
  any `tcp://`, `amqp://` or `failover:` placeholder. `auth`: keys containing `security`,
  `oauth2`, `jwt`, `issuer`, `jwks`, `oidc`. `downstream:<name>`: any other key ending in
  `url`, `uri`, `base-url`, `endpoint` or `host`, named after the key (`pricing.base-url` and
  `PRICING_BASE_URL` both become `pricing`).
- Env var for a config key: relaxed binding, `spring.datasource.url` is
  `SPRING_DATASOURCE_URL`; a `${VAR:default}` placeholder names it directly.

## Readiness

- Manifest `readinessProbe.httpGet.path` when present; Spring Boot's own paths are
  `/actuator/health/readiness` or `/actuator/health`. Fallback: port wait.

## Auth switches

- A boolean under `app.security.*`, `security.enabled`, `auth.enabled` guarding the
  `SecurityFilterChain` bean; a profile such as `noauth` on the security config.
- jwks mode: `spring.security.oauth2.resourceserver.jwt.issuer-uri` or `jwk-set-uri`; the
  harness answers both under `http://wiremock:8080/auth`.

## Validation

- Bean Validation on the request DTO: `@NotNull`, `@NotBlank`, `@NotEmpty`, `@Size`, `@Min`,
  `@Max`, `@DecimalMin`, `@DecimalMax`, `@Pattern`, `@Email`, `@Positive`, `@PositiveOrZero`,
  `@Negative`, `@NegativeOrZero`, `@Past`, `@Future`, `@Digits`, `@AssertTrue`, activated by
  `@Valid` on the parameter. Default status 400 (`MethodArgumentNotValidException`).
- Imperative checks in services throw `IllegalArgumentException` or custom exceptions mapped by
  `@ControllerAdvice`; read the advice for the status and error code.

## Migrations and boot behaviour

- Flyway under `src/main/resources/db/migration`, Liquibase under `db/changelog`.
  `spring.jpa.hibernate.ddl-auto` in `create`, `create-drop`, `update` means the app also
  migrates on boot (`also_on_boot`).

## Marker tokens verify-refs accepts

A `via` line (or one of the three lines after it) must contain one of these literal tokens for
its exit kind.

- entry-http: `Mapping`
- entry-amq: `@JmsListener`
- db-write: `.save(`, `.saveAll(`, `.saveAndFlush(`, `.delete`, `.persist(`, `.merge(`, `.remove(`, `@Modifying`, `jdbcTemplate.update(`, `jdbcTemplate.batchUpdate(`
- amq-publish: `convertAndSend(`, `.send(`
- http-out: `restTemplate.`, `RestTemplate`, `WebClient`, `webClient.`, `@FeignClient`, `RestClient`
- validation: `@NotNull`, `@NotBlank`, `@NotEmpty`, `@Size`, `@Min`, `@Max`, `@DecimalMin`, `@DecimalMax`, `@Pattern`, `@Email`, `@Positive`, `@Negative`, `@Past`, `@Future`, `@Digits`, `@AssertTrue`
````

- [ ] **Step 4: Write `reference/stack-quarkus.md`**

````markdown
# Quarkus cheat sheet

Loaded for `stack.framework: quarkus`. Marker regexes live in `scripts/markers.py`; this sheet
explains them for a tracer and lists the tokens the `verify-refs` gate accepts.

## Entry points

- JAX-RS resources: class-level `@Path("/prefix")` plus method `@GET`, `@POST`, `@PUT`,
  `@DELETE`, `@PATCH`; the method's own `@Path` sits on the line before or after the verb
  annotation. Reactive routes (`@Route`) are rare in these repos; report them as unresolved
  with the file:line if you meet one.
- Entry id: `<METHOD> <full path>`. Handler is the verb annotation's line.

## Exits: database writes

- Panache: `persist`, `persistAndFlush`, `delete`, `deleteById`, `deleteAll`, `update("...")`
  on entities or repositories; `op` from the call (update statements: read the JPQL verb).
- JPA: `EntityManager.persist`, `merge`, `remove`.
- `@Transactional` on a method does not itself write; find the statement inside.

## Exits: message publish

- SmallRye Reactive Messaging: `Emitter<T>.send(payload)` on a field annotated
  `@Channel("name")`; `@Outgoing("name")` methods. The destination is
  `mp.messaging.outgoing.<name>.address` when set, else the channel name. Topic when the
  connector config says so; default queue.

## Subscriptions

- `@Incoming("name")` methods are `amq-subscribe` entries; the ledger id uses the resolved
  address (`mp.messaging.incoming.<name>.address` when set, else the channel name).

## Exits: outbound HTTP

- MicroProfile REST clients: interfaces with `@RegisterRestClient(configKey = "...")`, injected
  with `@RestClient`; `RestClientBuilder`; Vert.x `WebClient`. `host_key` is the env var behind
  `quarkus.rest-client.<configKey>.url` or the client's URL config. Path from the interface's
  `@Path` plus the method's.

## Reads

- Panache `findById`, `find(...)`, `list(...)`, `count(...)`; `EntityManager.find`; record
  `db-read` with the table. Consumed REST client responses are `http-in` reads.

## Table and destination names

- `@Table(name = "...")` wins; Quarkus' default physical naming keeps the entity name as-is
  unless `quarkus.hibernate-orm.physical-naming-strategy` is set. Check `persistence.xml` or
  `import.sql` for explicit names.
- Destinations resolve through `mp.messaging.*.address`, then the channel name.

## Config keys and roles

- Files: `application.properties`, `application.yml`, `application.yaml` (base profile;
  `%dev.` and `%test.` prefixed keys are ignored).
- `db`: `quarkus.datasource.jdbc.url`, `quarkus.datasource.username|password`,
  `quarkus.hibernate-orm.*`. `amq`: `quarkus.qpid-jms.url|username|password`, `amqp-host`,
  `amqp-port`, `mp.messaging.*`, any `amqp://` placeholder. `auth`: `quarkus.oidc.*`, keys
  containing `jwt`, `issuer`, `jwks`. `downstream:<name>`: `quarkus.rest-client.<name>.url`
  and other `*.url` keys, named after the key.
- Env var: `quarkus.datasource.jdbc.url` is `QUARKUS_DATASOURCE_JDBC_URL`; `${VAR:default}`
  placeholders name it directly.

## Readiness

- Manifest probe when present; Quarkus' own paths are `/q/health/ready` and `/q/health`.
  Fallback: port wait.

## Auth switches

- `quarkus.oidc.enabled=false` removes OIDC; `quarkus.http.auth.*` policies can be set
  permissive by config; a `%test` profile is ignored by the skill, so look for a plain key.
- jwks mode: `quarkus.oidc.auth-server-url` (issuer) and optional `quarkus.oidc.jwks-path`;
  the harness serves discovery at `http://wiremock:8080/auth/.well-known/openid-configuration`.

## Validation

- Hibernate Validator annotations on the request type, the same set as Spring; `@Valid` on the
  parameter. Default status 400 with a `violations` array in the body unless an
  `ExceptionMapper` changes it.

## Migrations and boot behaviour

- Flyway under `src/main/resources/db/migration`; `quarkus.hibernate-orm.database.generation`
  in `drop-and-create`, `update`, `create` means `also_on_boot`.

## Marker tokens verify-refs accepts

- entry-http: `@GET`, `@POST`, `@PUT`, `@DELETE`, `@PATCH`
- entry-amq: `@Incoming`
- db-write: `.persist(`, `.persistAndFlush(`, `.delete(`, `.deleteById(`, `.deleteAll(`, `.merge(`, `.remove(`, `.update(`
- amq-publish: `.send(`, `@Outgoing(`
- http-out: `@RestClient`, `RestClientBuilder`, `WebClient`, `Client.`
- validation: `@NotNull`, `@NotBlank`, `@NotEmpty`, `@Size`, `@Min`, `@Max`, `@DecimalMin`, `@DecimalMax`, `@Pattern`, `@Email`, `@Positive`, `@Negative`, `@Past`, `@Future`, `@Digits`, `@AssertTrue`
````

- [ ] **Step 5: Write `reference/stack-aspnetcore.md`**

````markdown
# ASP.NET Core cheat sheet

Loaded for `stack.framework: aspnetcore`. Marker regexes live in `scripts/markers.py`; this
sheet explains them for a tracer and lists the tokens the `verify-refs` gate accepts.

## Entry points

- Controllers: `[ApiController]` classes with `[Route("api/[controller]")]`; `[controller]`
  expands to the class name without the `Controller` suffix, lower-cased. Methods carry
  `[HttpGet]`, `[HttpPost]`, `[HttpPut]`, `[HttpDelete]`, `[HttpPatch]` with an optional route
  template; route constraints such as `{id:guid}` become `{id}` in the entry id.
- Minimal APIs: `app.MapGet("/path", ...)`, `MapPost`, `MapPut`, `MapDelete`, `MapPatch` in
  `Program.cs` or extension methods; the handler line is the `Map*` call.
- Entry id: `<METHOD> <full path>` with a leading slash.

## Exits: database writes

- EF Core: `DbSet.Add`, `AddAsync`, `AddRange`, `AddRangeAsync`, `Update`, `UpdateRange`,
  `Remove`, `RemoveRange`, followed by `SaveChanges` or `SaveChangesAsync`. Point `via` at the
  `SaveChanges*` line; `op` from the `DbSet` call that precedes it.
- Raw SQL: `ExecuteSqlRaw`, `ExecuteSqlInterpolated`, `ExecuteUpdate`, `ExecuteDelete` (`op`
  from the statement).
- Dapper `Execute` with INSERT/UPDATE/DELETE text.

## Exits: message publish

- Apache.NMS (AMQP): `IMessageProducer.Send(message)` and `SendAsync`; the producer is created
  with `session.CreateProducer(destination)`, where the destination came from
  `session.GetQueue("name")` or `GetTopic("name")`. Follow the producer field back to its
  creation to find the name.
- MassTransit: `IPublishEndpoint.Publish<T>`, `ISendEndpoint.Send`; the destination is the
  message type's mapped name or the `ReceiveEndpoint` name.

## Subscriptions

- NMS: `session.GetQueue("name")` or `GetTopic("name")` followed by `CreateConsumer` and
  `consumer.Listener += handler` in a `BackgroundService`; the entry id is `amq <name>` and
  the handler line is the `GetQueue`/`GetTopic` call.
- MassTransit: `IConsumer<T>` implementations and `ReceiveEndpoint("name", ...)`.

## Exits: outbound HTTP

- `HttpClient` and typed clients (`IHttpClientFactory`, `AddHttpClient<T>`): `GetAsync`,
  `PostAsync`, `PutAsync`, `DeleteAsync`, `SendAsync`, `GetFromJsonAsync`, `PostAsJsonAsync`,
  `PutAsJsonAsync`, `GetStringAsync`. `host_key` is the env var behind the client's
  `BaseAddress` (a `Pricing__BaseUrl` style configuration key). YARP routes are outbound
  proxies: record them as `http-out` with the cluster's destination key.

## Reads

- EF: `Find`, `FindAsync`, `FirstOrDefault*`, `SingleOrDefault*`, `ToList*`, `Any*`, `Count*`
  on a `DbSet`; record `db-read` with the table. Consumed HTTP responses are `http-in` reads.

## Table and destination names

- `[Table("name")]` on the entity wins; else the `DbSet<T>` property name in the `DbContext`;
  else the class name. Check `OnModelCreating` for `ToTable(...)`.
- Queue and topic names are the literals passed to `GetQueue`/`GetTopic` or configuration keys
  under `Amq__*`.

## Config keys and roles

- Files: `appsettings.json` (base only; `appsettings.<Environment>.json` is ignored). Keys are
  flattened with `__`: `ConnectionStrings:Deals` is `ConnectionStrings__Deals`, and that is
  also the env var name.
- `db`: `ConnectionStrings__*`, any `Host=` placeholder. `amq`: `Amq__*`, `ActiveMq__*`,
  `Artemis__*`, any `amqp://`, `activemq:` or `failover:` placeholder. `auth`: `Auth__*`,
  `Authentication__*`, `Jwt__*`, keys containing `Authority`, `Issuer`, `Jwks`.
  `downstream:<name>`: `<Name>__BaseUrl`, `<Name>__Url`, named after the first segment
  (`Pricing__BaseUrl` becomes `pricing`).

## Readiness

- Manifest probe when present; common app paths are `/health/ready`, `/health`, `/healthz`.
  Fallback: port wait.

## Auth switches

- `Auth__Enabled=false` (or `Authentication__Enabled`) guarding `AddAuthentication` and
  `UseAuthentication` in `Program.cs`; a `RequireAuthorization()` toggle.
- jwks mode: `Auth__Authority` (issuer) with JWT bearer; the harness's issuer is plain HTTP, so
  the app must set `RequireHttpsMetadata = false` for tests, and the README notes it when the
  code does not.

## Validation

- FluentValidation: `AbstractValidator<T>` classes with `RuleFor(x => x.Field)` chains
  (`NotEmpty`, `NotNull`, `MaximumLength`, `MinimumLength`, `Length`, `GreaterThan`,
  `GreaterThanOrEqualTo`, `LessThan`, `LessThanOrEqualTo`, `InclusiveBetween`,
  `ExclusiveBetween`, `Matches`, `EmailAddress`); status 400 with a `ValidationProblemDetails`
  body unless a filter changes it.
- Data annotations on the request type: `[Required]`, `[StringLength]`, `[Range]`,
  `[RegularExpression]`, `[MaxLength]`, `[MinLength]`, `[EmailAddress]`, `[Url]`, `[Phone]`,
  `[Compare]`; `[ApiController]` returns 400 automatically.

## Migrations and boot behaviour

- EF migrations under a `Migrations/` directory; `db.Database.Migrate()` at startup means
  `also_on_boot`.

## Marker tokens verify-refs accepts

- entry-http: `[Http`, `.Map`
- entry-amq: `GetQueue(`, `GetTopic(`, `ReceiveEndpoint(`, `IConsumer<`, `Listener +=`
- db-write: `SaveChanges`, `.Add(`, `.AddAsync(`, `.AddRange(`, `.Update(`, `.Remove(`, `.RemoveRange(`, `ExecuteSql`, `ExecuteUpdate`, `ExecuteDelete`
- amq-publish: `.Send(`, `.SendAsync(`, `.Publish(`, `.PublishAsync(`, `CreateProducer(`
- http-out: `HttpClient`, `.GetAsync(`, `.PostAsync(`, `.PutAsync(`, `.DeleteAsync(`, `.SendAsync(`, `FromJsonAsync`, `AsJsonAsync`, `GetStringAsync(`
- validation: `RuleFor(`, `[Required`, `[StringLength`, `[Range`, `[RegularExpression`, `[MaxLength`, `[MinLength`, `[EmailAddress`, `[Url`, `[Phone`, `[Compare`
````

- [ ] **Step 6: Write `reference/stack-python.md`**

````markdown
# Python web cheat sheet

Loaded for `stack.framework: python` (FastAPI, Flask or Django). Marker regexes live in
`scripts/markers.py`; this sheet explains them for a tracer and lists the tokens the
`verify-refs` gate accepts.

## Entry points

- FastAPI: `@app.get("/path")`, `@app.post`, `@app.put`, `@app.delete`, `@app.patch`, and the
  same on an `APIRouter` (`@router.post`) whose `prefix=` joins the path. Path parameters stay
  as `{id}`.
- Flask: `@app.route("/path", methods=[...])`, `@bp.route`; one entry per method listed.
- Django: patterns in `urls.py` mapped to views; report each pattern with the view's line as
  the handler.
- Entry id: `<METHOD> <full path>`.

## Exits: database writes

- SQLAlchemy: `session.add`, `add_all`, `delete`, `merge`, then `commit` or `flush`. Point `via`
  at the `add`/`delete` line (the `commit` line is also accepted); `op` from the call.
- psycopg or asyncpg: `cursor.execute("INSERT ...")` and `UPDATE`/`DELETE` text; `op` from the
  statement.
- Django ORM: `Model.save()`, `objects.create`, `update`, `delete`.

## Exits: message publish

- qpid-proton: `container.send`, `sender.send(Message(...))`; the destination is the address
  the sender was created with (`create_sender(conn, "name")`).
- stomp.py: `conn.send(destination="/queue/name", body=...)`; `/queue/` is a queue,
  `/topic/` a topic.

## Subscriptions

- qpid-proton: `create_receiver(conn, "name")` and `on_message` handlers; stomp.py:
  `conn.subscribe(destination="/queue/name", ...)`. Entry id `amq <name>` without the
  `/queue/` or `/topic/` prefix; `type` from the prefix.

## Exits: outbound HTTP

- `httpx.get/post/...`, `httpx.Client`, `httpx.AsyncClient`, `requests.get/post/...`,
  `aiohttp.ClientSession`. `host_key` is the env var read for the base URL (`os.environ`,
  `os.getenv`, a settings module attribute).

## Reads

- SQLAlchemy `session.get`, `query(...)`, `select(...)` executions; psycopg `SELECT`; Django
  `objects.get/filter`. Record `db-read` with the table. Consumed HTTP responses are
  `http-in` reads.

## Table and destination names

- SQLAlchemy `__tablename__` on the model; Django `Meta.db_table` else `<app>_<model>`.
- Destinations are the literal addresses; strip stomp prefixes.

## Config keys and roles

- Sources: `settings.py`, `config.py` attributes read from `os.environ`/`os.getenv`, and
  `.env.example`. Only keys read from the environment carry an env var; a settings attribute
  without one cannot be injected by the harness.
- `db`: `DATABASE_URL`, `DB_*`, `PG*`, any `postgresql://` placeholder. `amq`: `AMQ_*`,
  `BROKER_*`, `ARTEMIS_*`, `STOMP_*`, any `amqp://` or `stomp://` placeholder. `auth`: keys
  containing `JWT`, `OIDC`, `ISSUER`, `JWKS`, `AUTH`. `downstream:<name>`: other `*_URL` and
  `*_BASE_URL` keys, named after the prefix (`PRICING_BASE_URL` becomes `pricing`).

## Readiness

- Manifest probe when present; otherwise a port wait (the default port is 8000 for uvicorn
  unless the Dockerfile exposes another).

## Auth switches

- A settings flag such as `AUTH_ENABLED`, `AUTH_MODE=mock`, `DISABLE_AUTH` guarding the
  dependency or middleware that validates tokens.
- jwks mode: `JWKS_URL`, `OIDC_ISSUER`, `AUTH_ISSUER` read by PyJWT, python-jose or Authlib;
  the harness serves `http://wiremock:8080/auth/.well-known/jwks.json`.

## Validation

- Pydantic models: `Field(..., min_length=, max_length=, gt=, ge=, lt=, le=, pattern=)`,
  `constr`, `conint`, `confloat`, `conlist`, `condecimal`, `EmailStr`, `@validator` and
  `@field_validator` methods. FastAPI answers 422 with a `detail` array; Flask and Django code
  usually returns 400 explicitly.
- Imperative checks raise `HTTPException(status_code=...)` or return error responses; read the
  handler and service for them.

## Migrations and boot behaviour

- Alembic under `alembic/versions`, Django under `migrations/`; `Base.metadata.create_all(`
  at startup means `also_on_boot`.

## Marker tokens verify-refs accepts

- entry-http: `@app.`, `@router.`, `.route(`
- entry-amq: `create_receiver(`, `.subscribe(`
- db-write: `session.add(`, `session.add_all(`, `session.delete(`, `session.merge(`, `.commit(`, `.flush(`, `.execute(`
- amq-publish: `.send(`, `.publish(`
- http-out: `httpx.`, `requests.`, `aiohttp.`
- validation: `Field(`, `validator`, `constr(`, `conint(`, `confloat(`, `conlist(`, `condecimal(`
````

- [ ] **Step 7: Run the reference tests**

Run: `pytest skills/karate-bootstrap/tests/test_kb_reference.py -q`
Expected: 12 passed. A failing token test names the stack, kind and token: add the missing token to that sheet's last section verbatim (with backticks).

- [ ] **Step 8: Full gate, then commit**

Run: `pytest -q` then `ruff check .` then `mypy`
Expected: green.

```bash
git add skills/karate-bootstrap/reference/stack-spring.md skills/karate-bootstrap/reference/stack-quarkus.md skills/karate-bootstrap/reference/stack-aspnetcore.md skills/karate-bootstrap/reference/stack-python.md skills/karate-bootstrap/tests/test_kb_reference.py
git commit -m "docs(karate-bootstrap): stack cheat sheets mirroring the marker tables

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Harness notes: testcontainers, karate, failure triage, podman

**Confidence:** 93%. Every fact below comes from the Plan 2 spike, the landed harness code (`Containers.java`, `Stubs.java`, `KarateRunner.java`, `reset.feature`) or spec sections 5.5, 5.7 and 10, all read during Plan 2. A heading test pins the structure the SKILL.md steps point at.

**Files:**
- Create: `skills/karate-bootstrap/reference/testcontainers-notes.md`, `karate-notes.md`, `failure-triage.md`, `podman.md`
- Test: `skills/karate-bootstrap/tests/test_kb_reference.py` (extend)

**Interfaces:**
- Consumes: nothing new.
- Produces for Task 6: the four note files with the headings listed in the test.

- [ ] **Step 1: Extend `tests/test_kb_reference.py`**

Append:

```python
NOTE_HEADINGS = {
    "testcontainers-notes.md": ("## Topology", "## kb-runtime.json", "## Tokens",
                                "## Waits and timeouts", "## Logs and evidence files",
                                "## Running"),
    "karate-notes.md": ("## Runner flags", "## Tags", "## Data-driven outlines",
                        "## Calling reset.feature", "## Java helpers", "## Reports"),
    "failure-triage.md": ("## Classification order", "## 1. Infra", "## 2. Stub or seed missing",
                          "## 3. Expectation wrong", "## 4. Suspected app defect",
                          "## Quarantine procedure", "## Stop conditions"),
    "podman.md": ("## Linux", "## Windows and macOS", "## Ryuk", "## Verify"),
}


@pytest.mark.parametrize("name", sorted(NOTE_HEADINGS))
def test_note_has_every_heading(name: str) -> None:
    text = (REFERENCE / name).read_text(encoding="utf-8")
    for heading in NOTE_HEADINGS[name]:
        assert heading in text, f"{name}: missing {heading}"
```

- [ ] **Step 2: Run it to see the four missing notes**

Run: `pytest skills/karate-bootstrap/tests/test_kb_reference.py -q -k note`
Expected: 4 failures with `FileNotFoundError`.

- [ ] **Step 3: Write `reference/testcontainers-notes.md`**

````markdown
# Testcontainers harness notes

What the Java harness under `karate-tests/src/test/java/kb/harness/` does, for the agent running
the suite and the developer reading it afterwards. Nothing here is templated per repo.

## Topology

One Docker network, started lazily by `karate-config.js` on the first scenario unless
`-Dkb.skipContainers=true`:

1. Postgres `postgres:16-alpine`, alias `db`, port 5432, database, user and password from
   `kb-runtime.json`.
2. Artemis `apache/activemq-artemis:2.44.0-alpine`, alias `artemis`, AMQP on 5672 (core 61616,
   STOMP 61613, console 8161). Queues (anycast) and topics (multicast) are pre-created from
   the runtime file through `EXTRA_ARGS --queues ... --addresses ...`. Ready when the log shows
   `AMQ221007`.
3. WireMock `wiremock/wiremock:3.13.2-alpine`, alias `wiremock`, port 8080, ready on
   `GET /__admin/health`. In `jwks` auth mode the harness imports discovery and JWKS mappings
   under `/auth` before the app starts.
4. The db-manager image from `migrations.image`, one-shot (`OneShotStartupCheckStrategy`, five
   minute cap), must exit 0; its output is `target/db-manager.log`.
5. The app, built with `ImageFromDockerfile` from the service root and `app.dockerfileRel`, or
   `-Dapp.image=<tag>` to skip the build. Env from the runtime file with tokens substituted.
   Readiness from `app.readinessPath`, else a port wait; serverless doubles the timeout.

A failed start is remembered and rethrown by every later scenario instead of retried. A JVM
shutdown hook stops the containers and closes the JMS connection (needed when Ryuk is off).

## kb-runtime.json

`src/test/resources/kb-runtime.json`, written by `kb_scaffold.py`, schema version 1: `app`
(`repoRootRel`, `dockerfileRel`, `port`, `readinessPath`, `serverless`,
`startupTimeoutSeconds`), `env[]` (`name`, `role`, `value` with tokens), `db`, `migrations`
(`strategy`, `image`, `env`), `amq` (`user`, `password`, `queues`, `topics`), `downstreams[]`
(`name`, `envVar`), `auth` (`mode`, and `key`/`value` or `issuerKeys`). Re-running the scaffold
rewrites it; nothing else in the module is repo-specific.

## Tokens

Substituted by `Containers` at start: `{{db.host}}`=`db`, `{{db.port}}`=`5432`,
`{{db.name}}`, `{{db.user}}`, `{{db.password}}`, `{{amq.host}}`=`artemis`,
`{{amq.amqpPort}}`=`5672`, `{{amq.corePort}}`=`61616`, `{{amq.stompPort}}`=`61613`,
`{{amq.user}}`, `{{amq.password}}`, `{{stubs.url}}`=`http://wiremock:8080`,
`{{auth.url}}`=`http://wiremock:8080/auth`. Each downstream is reached as
`{{stubs.url}}/<name>`, so every stub `urlPath` starts with `/<name>`.

## Waits and timeouts

- Artemis: log message, 120 s. WireMock: HTTP health. db-manager: exit 0 within 5 minutes.
- App: `startupTimeoutSeconds` (default 120, doubled when serverless) on the readiness path or
  the listening port. A slow first image build counts against it only after the build.
- `Jms.await` default 5000 ms in generated features; `Db.awaitRow` polls every 250 ms.

## Logs and evidence files

Under `karate-tests/target/`: `postgres.log`, `artemis.log`, `wiremock.log`, `db-manager.log`,
`app.log` (also echoed through SLF4J with prefix `app`), `stubs-unmatched.json` (WireMock's
unmatched requests and near misses, written by the runner after a containerised run),
`karate-reports/` (cucumber JSON per feature, JUnit XML, HTML), `surefire-reports/`.

## Running

- `mvn -B test` from `karate-tests/` (JDK 17 or newer, a container engine). `./mvnw -B test`
  when Maven is not installed.
- `-Dkb.skipContainers=true` runs only `@harness` features (the smoke self-test).
- `-Dkb.threads=1` runs scenarios sequentially; `-Dapp.image=<tag>` uses a prebuilt image;
  `-Dkarate.options="--tags @smoke"` or `"classpath:features/x.feature"` narrows the run.
- Ryuk needs `ryuk.container.privileged=true` (set in `testcontainers.properties`); podman users
  read `podman.md`.
````

- [ ] **Step 4: Write `reference/karate-notes.md`**

````markdown
# Karate notes (1.5.2)

## Runner flags

`KarateRunner` runs `classpath:features` excluding `@known-defect`, writes cucumber JSON and
JUnit XML, with `kb.threads` (default 4) parallel scenarios. Under `-Dkb.skipContainers=true`
it also requires `@harness`. `-Dkarate.options="..."` accepts Karate's own CLI options: a
feature path, `--tags @smoke`, `--tags ~@rules`.

## Tags

- `@smoke` happy path, `@error` failure paths, `@rules` validation outline, `@amq` AMQ-driven
  feature, `@known-defect` quarantined (excluded from every run), `@harness` container-free
  self-test, `@parallel=false` Karate's built-in tag that serialises a scenario or feature.
- `@ignore` on `common/reset.feature` keeps it out of the run; it only executes through `call`.

## Data-driven outlines

`Examples:` with a single cell `| read('classpath:rules/<slug>.csv') |` expands the outline to
one scenario per CSV row; column names become `<placeholders>`. The CSV is a Maven test
resource because `pom.xml` registers `rules/`, `stubs/` and `seed/` at the module root. Row
names appear in reports as the outline name with placeholders substituted.

## Calling reset.feature

`* call read('classpath:common/reset.feature') { watch: ['deal.created'], seed: 'classpath:seed/x.sql' }`
applies `watch`, `truncate`, `seed`, `stubs` in that order. `watch` subscribes before the
request so no message is missed. `seed` is additive and parallel-safe. `truncate` and `stubs`
change shared state: the calling scenario needs `@parallel=false`. Variables the call defines
(`args`, `watch`, `stubs`) leak into the caller when the call has no `def`; do not reuse those
names.

## Java helpers

Exposed by `karate-config.js` as `Db`, `Jms`, `Stubs`, `Jwt` (only when containers run) plus
`appBaseUrl`, `mutate` and `skipContainers`. JavaScript maps pass to Java as `Map<String,
Object>`; arrays as `List`. `Jms.await(dest, ms, { key: value })` matches on message body
fields by string comparison and leaves other messages in the inbox in order.
`Stubs.verify(method, urlPath, times)` counts journal entries; the four-argument form adds a
body `contains` clause. Failures raise `AssertionError` with the expected and recorded counts.

## Reports

`target/karate-reports/<package.qualified.name>.json` per feature (cucumber JSON: `uri`
`features/<name>.feature`, `elements[]` with `keyword` `Scenario` or `Scenario Outline`,
`tags[].name`, `steps[].result.status` and `error_message`), `<name>.xml` JUnit,
`karate-summary-json.txt` with counts, `karate-summary.html`. `@known-defect` scenarios never
appear in these files; `kb_report.py parse` counts them from the feature files instead.
````

- [ ] **Step 5: Write `reference/failure-triage.md`**

````markdown
# Failure triage

Used in the run-and-iterate phase. One hypothesis and one change per iteration, logged with
`kb_iterate.py log` before the change is made. Evidence per failure group comes from
`kb_iterate.py next`: the failing step and its match diff, the tail of `target/app.log`,
`target/stubs-unmatched.json`, and `target/db-manager.log` when the failure is at startup.

## Classification order

Work down the list; the first class that fits wins.

## 1. Infra

Container did not start, wait timeout, connection refused, db-manager exited non-zero,
`topology failed earlier` on every scenario. Signs: the failure is in the first scenario to run,
`app.log` ends before readiness, `db-manager.log` shows a migration error. Fix inside
`karate-tests/` only: `kb-runtime.json` values (env, readiness path, timeout), the db-manager
image reference, stub mappings the app needs at boot. A Dockerfile that does not build, a
missing base image, or an app that needs a service the harness does not provide is not
fixable here: log the iteration with `--classification infra --unfixable` and let
`check-stop` stop the run.

## 2. Stub or seed missing

WireMock answered 404 (the request appears in `stubs-unmatched.json`, usually with a near miss
naming the closest mapping), a foreign-key violation, an empty read the scenario expected to
find. Add or widen the stub mapping under `stubs/<downstream>/`, or add the reference rows to
the entry's seed file. Keep mappings suite-level and matched by request data.

## 3. Expectation wrong

The app answered consistently and not erroneously, and the generated expectation was the
guess: a 200 where 201 was assumed, a different field name, a message published on a
different destination, a validation message worded differently. Adopt the observed behaviour
in the feature or the rules CSV, and record it with
`flow_map.py override --entry <id> --scenario <name> --field <what> --old <expected> --new <observed> --reason "..."`
so the README lists it.

## 4. Suspected app defect

A 5xx, a stack trace in the response or `app.log`, behaviour contradicting the app's own
validation, data written that the request did not ask for. Do not change the app. Quarantine
the scenario and document it.

## Quarantine procedure

1. Add `@known-defect` to the scenario (or the feature when every scenario is affected).
2. Append an entry to `karate-tests/defects.md` in the spec's format: `## DEF-NNN: <title>`,
   then `status: pending`, `slug`, `severity` (high, medium, low), `category: app-defect`,
   `entry_point: <ledger id>`, `scenario: features/<file>.feature:<line>`, `evidence: |` with
   request, response and the `app.log` lines, `root_cause: <file:line and one sentence>`,
   `suggested_fix: <one sentence>`.
3. Re-run; the green gate accepts the failure only when the owning entry's id appears on an
   `entry_point:` line in `defects.md`.

## Stop conditions

`kb_iterate.py check-stop` stops the run (exit 6) at the iteration cap (default 15), when the
same signature has been logged three iterations in a row, or when the last iteration was logged
`--unfixable`. A stopped run still commits what it has and writes the README with the counts,
so a developer can pull the branch and continue.
````

- [ ] **Step 6: Write `reference/podman.md`**

````markdown
# Podman with Testcontainers

Dev laptops use podman or the docker CLI, not Docker Desktop. Testcontainers talks to whatever
socket `DOCKER_HOST` names.

## Linux

Rootless podman:

```bash
systemctl --user enable --now podman.socket
export DOCKER_HOST=unix://${XDG_RUNTIME_DIR}/podman/podman.sock
```

## Windows and macOS

Podman runs in a machine (WSL2 on Windows). After `podman machine start`, read the socket
from `podman machine inspect --format '{{.ConnectionInfo.PodmanSocket.Path}}'` and export it
as `DOCKER_HOST` (on Windows, a named pipe such as `npipe:////./pipe/podman-machine-default`).
Setting it once in the user environment avoids repeating it per shell.

## Ryuk

Testcontainers starts Ryuk to reap containers. Podman needs it privileged, which the module's
`src/test/resources/testcontainers.properties` sets (`ryuk.container.privileged=true`). If the
engine still refuses, set `TESTCONTAINERS_RYUK_DISABLED=true`; the harness's shutdown hook then
stops the containers itself when the JVM exits normally.

## Verify

```bash
cd karate-tests
mvn -B test -Dkb.skipContainers=true   # no engine needed: the harness self-test
mvn -B test -Dkarate.options="--tags @smoke"   # first live run, happy paths only
```

`target/app.log` and `target/db-manager.log` show where a first run stops.
````

- [ ] **Step 7: Run the reference tests, the full gate, and commit**

Run: `pytest skills/karate-bootstrap/tests/test_kb_reference.py -q` then `pytest -q` then `ruff check .` then `mypy`
Expected: 16 passed in the reference file; everything green.

```bash
git add skills/karate-bootstrap/reference/testcontainers-notes.md skills/karate-bootstrap/reference/karate-notes.md skills/karate-bootstrap/reference/failure-triage.md skills/karate-bootstrap/reference/podman.md skills/karate-bootstrap/tests/test_kb_reference.py
git commit -m "docs(karate-bootstrap): harness, karate, triage and podman notes

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: `kb_check_skill.py`

**Confidence:** 94%. A port of `skills/tech-debt-scan/scripts/skill_check.py` (read at plan time; in CI since PR #5) with karate-bootstrap defaults and the `kb_` name. Its tests mirror the sibling's four unit cases; the real-`SKILL.md` case lands with `SKILL.md` in Task 6.

**Files:**
- Create: `skills/karate-bootstrap/scripts/kb_check_skill.py`
- Test: `skills/karate-bootstrap/tests/test_kb_check_skill.py`

**Interfaces:**
- Consumes: nothing from the other scripts (stand-alone by design, like its sibling).
- Produces for Task 6: `extract_commands(text) -> list[str]`, `check_command(scripts_dir, command) -> list[str]`, `check_skill(skill_path, scripts_dir) -> list[str]`; CLI `python scripts/kb_check_skill.py [--skill PATH] [--scripts DIR]`, exit 0 clean, 2 with the offending commands on stderr.

- [ ] **Step 1: Write `tests/test_kb_check_skill.py`**

```python
from __future__ import annotations

from pathlib import Path

from kb_check_skill import check_command, check_skill, extract_commands

SKILL = Path(__file__).resolve().parent.parent / "SKILL.md"
SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"

_SIMPLE = """\
import argparse
p = argparse.ArgumentParser()
p.add_argument("path")
p.add_argument("--out")
p.parse_args()
"""

_SUBCMD = """\
import argparse
p = argparse.ArgumentParser()
sub = p.add_subparsers(dest="cmd", required=True)
r = sub.add_parser("render")
r.add_argument("--prompt")
r.add_argument("--out")
p.parse_args()
"""


def _fake_script(tmp_path: Path, name: str, body: str) -> Path:
    scripts = tmp_path / "scripts"
    scripts.mkdir(exist_ok=True)
    (scripts / name).write_text(body, encoding="utf-8")
    return scripts


def test_extract_commands_finds_python_script_invocations_only() -> None:
    text = (
        "intro\n```bash\npython scripts/detect.py <repo> --out karate-tests/stack.json\n"
        "python scripts/flow_map.py next --phase traced --ledger karate-tests/flow-map.yaml\n```\n"
        "inline `python scripts/kb_prompt.py render --prompt trace --out x.md` too\n"
        "not a command: mvn -B test\nnor: python scripts/<name>.py --x\n"
    )
    commands = extract_commands(text)
    assert len(commands) == 3
    assert commands[2] == "python scripts/kb_prompt.py render --prompt trace --out x.md"


def test_check_passes_for_a_valid_command(tmp_path: Path) -> None:
    scripts = _fake_script(tmp_path, "thing.py", _SIMPLE)
    assert check_command(scripts, "python scripts/thing.py somepath --out o.json") == []


def test_check_flags_an_unknown_flag(tmp_path: Path) -> None:
    scripts = _fake_script(tmp_path, "thing.py", _SIMPLE)
    errors = check_command(scripts, "python scripts/thing.py somepath --nope x")
    assert len(errors) == 1 and "--nope" in errors[0]


def test_check_reports_a_missing_script(tmp_path: Path) -> None:
    scripts = _fake_script(tmp_path, "thing.py", _SIMPLE)
    errors = check_command(scripts, "python scripts/missing.py --out o")
    assert len(errors) == 1 and "script not found" in errors[0]


def test_subcommand_flags_are_checked_against_the_subparser(tmp_path: Path) -> None:
    scripts = _fake_script(tmp_path, "sub.py", _SUBCMD)
    assert check_command(scripts, "python scripts/sub.py render --prompt trace --out o.md") == []
    errors = check_command(scripts, "python scripts/sub.py render --ledger l.yaml")
    assert len(errors) == 1 and "--ledger" in errors[0] and "sub.py render" in errors[0]


def test_check_skill_collects_every_error(tmp_path: Path) -> None:
    scripts = _fake_script(tmp_path, "thing.py", _SIMPLE)
    skill = tmp_path / "SKILL.md"
    skill.write_text(
        "```bash\npython scripts/thing.py a --out o\npython scripts/thing.py a --bad 1\n"
        "python scripts/gone.py\n```\n",
        encoding="utf-8",
    )
    errors = check_skill(skill, scripts)
    assert len(errors) == 2
```

- [ ] **Step 2: Run it to confirm the import fails**

Run: `pytest skills/karate-bootstrap/tests/test_kb_check_skill.py -q`
Expected: `ModuleNotFoundError: No module named 'kb_check_skill'`.

- [ ] **Step 3: Create `scripts/kb_check_skill.py`**

```python
"""Lint SKILL.md commands against the scripts they invoke.

A CI guard against doc drift: every ``python scripts/<name>.py ...`` command in SKILL.md must
name a script that exists and must only use flags the script's ``--help`` accepts. Renaming a
flag in a script but not in SKILL.md (or the reverse) fails the build instead of shipping a
stale procedure to the model that follows it.

Algorithm: regex-extract every ``python scripts/<name>.py ...`` command, confirm the script
exists, run ``python scripts/<name>.py --help`` (plus ``<subcommand> --help`` when the command
targets an argparse subparser), and require every ``--flag`` token in the command to appear
in that help text. Positional arguments and values are ignored.

Usage: python scripts/kb_check_skill.py [--skill PATH] [--scripts DIR]

Exit 0 when every command lints clean, 2 (offending commands on stderr) otherwise.
Stand-alone by design: no sibling imports, so it also works from a checkout without pyyaml.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# A full ``python scripts/<name>.py ...`` invocation up to the line end or a closing backtick.
# Script names are real lowercase module names, so prose like ``scripts/<name>.py`` is skipped.
_COMMAND_RE = re.compile(r"python\s+scripts/[a-z_][a-z0-9_]*\.py[^\n`]*")

# Argparse renders subparser choices as ``{render,mark}`` in help text.
_CHOICES_RE = re.compile(r"\{([a-z0-9,_-]+)\}")


def extract_commands(text: str) -> list[str]:
    """Every ``python scripts/*.py ...`` command string found in ``text``."""
    return [match.group(0).rstrip() for match in _COMMAND_RE.finditer(text)]


def _parse_command(command: str) -> tuple[str, list[str], list[str]]:
    tokens = command.split()
    script_rel = tokens[1]
    rest = tokens[2:]
    flags = [t for t in rest if t.startswith("--")]
    positionals = [t for t in rest if not t.startswith("-")]
    return script_rel, positionals, flags


def _run_help(script_path: Path, subcommand: list[str]) -> str:
    proc = subprocess.run(
        [sys.executable, str(script_path), *subcommand, "--help"],
        capture_output=True,
        text=True,
    )
    return proc.stdout + proc.stderr


def _subcommand_choices(help_text: str) -> set[str]:
    match = _CHOICES_RE.search(help_text)
    return set(match.group(1).split(",")) if match else set()


def check_command(scripts_dir: Path, command: str) -> list[str]:
    """Lint errors for one command (empty when it lints clean)."""
    script_rel, positionals, flags = _parse_command(command)
    script_path = scripts_dir / Path(script_rel).name
    if not script_path.exists():
        return [f"{command!r}: script not found: {script_path}"]
    help_text = _run_help(script_path, [])
    choices = _subcommand_choices(help_text)
    subcommand = next((p for p in positionals if p in choices), None)
    if subcommand is not None:
        help_text = _run_help(script_path, [subcommand])
    where = f"{script_path.name} {subcommand}".strip()
    return [
        f"{command!r}: flag {flag} not accepted by `{where} --help`"
        for flag in flags
        if flag not in help_text
    ]


def check_skill(skill_path: Path, scripts_dir: Path) -> list[str]:
    """Lint every command in ``skill_path`` against ``scripts_dir``."""
    text = skill_path.read_text(encoding="utf-8")
    errors: list[str] = []
    for command in extract_commands(text):
        errors.extend(check_command(scripts_dir, command))
    return errors


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Lint SKILL.md commands against scripts")
    parser.add_argument("--skill", type=Path, default=here.parent / "SKILL.md",
                        help="path to SKILL.md")
    parser.add_argument("--scripts", type=Path, default=here,
                        help="path to the scripts/ directory")
    args = parser.parse_args(argv)
    errors = check_skill(args.skill, args.scripts)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 2
    print(f"ok: all SKILL.md commands match their scripts ({args.skill})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests, then the full gate, then commit**

Run: `pytest skills/karate-bootstrap/tests/test_kb_check_skill.py -q` then `pytest -q` then `ruff check .` then `mypy`
Expected: 6 passed; everything green.

```bash
git add skills/karate-bootstrap/scripts/kb_check_skill.py skills/karate-bootstrap/tests/test_kb_check_skill.py
git commit -m "feat(karate-bootstrap): kb_check_skill lints SKILL.md commands against --help

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: `SKILL.md`, its lint test and the CI step

**Confidence:** 90%. Every command below was copied from the scripts' `argparse` definitions (the listing in this plan's preparation) and is linted by `kb_check_skill.py`; the phase order is the one the chain spike executed green today; Task 8 re-executes it in CI. The procedure is written for Opus 4.8 and Sonnet 4.6 in the register `tech-debt-scan/SKILL.md` uses (read at plan time): prerequisite, one command, postcondition, abort rule.

**Files:**
- Create: `skills/karate-bootstrap/SKILL.md`
- Modify: `skills/karate-bootstrap/tests/test_kb_check_skill.py` (append the real-skill test)
- Modify: `.github/workflows/test.yml` (add the lint step)

**Interfaces:**
- Consumes: every script CLI from Plans 1 and 2 and Tasks 1, 2, 5; the reference and prompt files from Tasks 2 to 4.
- Produces: the skill procedure the user invokes as `/karate-bootstrap <repo-path> [...]`; Task 7 tests its frontmatter and Task 8 executes its commands.

- [ ] **Step 1: Append the real-skill test to `tests/test_kb_check_skill.py`**

```python
def test_real_skill_md_lints_clean() -> None:
    assert SKILL.is_file()
    assert check_skill(SKILL, SCRIPTS) == []
```

Run: `pytest skills/karate-bootstrap/tests/test_kb_check_skill.py::test_real_skill_md_lints_clean -q`
Expected: fails on `SKILL.is_file()`.

- [ ] **Step 2: Write `skills/karate-bootstrap/SKILL.md`**

The file follows. Keep it under 500 lines; do not paraphrase commands.

````markdown
---
name: karate-bootstrap
description: Bootstrap a first ground-truth Karate integration-test suite that runs green under Testcontainers for a Spring Boot, Quarkus, ASP.NET Core or Python service that has no Karate tests. Use when asked to add karate tests, bootstrap integration tests, or build a testcontainers suite for a service or repo. Not for unit tests.
triggers:
  - /karate-bootstrap
---

# karate-bootstrap

Takes a service repository with no Karate tests and leaves it with a first "ground truth"
suite under `karate-tests/` that runs green under Testcontainers, locally and in Azure DevOps.
The suite documents the behaviour the service has today; suspected defects are quarantined
and reported, never fixed. Scripts do every deterministic step (discovery, the ledger, gates,
scaffolding, report parsing, git checkpoints); you do the judgement inside narrow subagent
tasks (tracing code paths, confirming validation rules, writing features) and the fix loop.

Read `reference/testcontainers-notes.md` once before a run. Read the stack cheat sheet the
ledger names (`reference/stack-<stack>.md`) when you dispatch the first trace. Read
`reference/failure-triage.md` before the first fix iteration.

## No improvisation

If any expected output file from a numbered step is missing, abort with exit 5. Do not retry
steps you were not told to retry. Do not edit `flow-map.yaml`, `rules/*.csv` or
`kb-runtime.json` by hand: every change goes through a script. Do not compose a subagent
prompt yourself: render it with `kb_prompt.py`. Never edit the application's source, its
Dockerfile or its pipeline. Never push.

## Invocation

```
/karate-bootstrap <repo-path> [--service-dir <sub>] [--migrations-image <ref>] [--app-image <tag>]
                  [--max-iterations 15] [--double-trace] [--no-commit]
```

| Flag | Effect |
|------|--------|
| `--service-dir <sub>` | The service lives in a sub-directory of the repo (monorepo). Pass it to every script that accepts it; `<root>` below means `<repo-path>/<sub>`. |
| `--migrations-image <ref>` | The db-manager image that owns the schema. Without it the scaffold looks the database up in `~/.karate-bootstrap/config.yaml` and aborts with exit 4 when nothing matches. |
| `--app-image <tag>` | Test a prebuilt image instead of building the Dockerfile: adds `-Dapp.image=<tag>` to every Maven run. |
| `--max-iterations <n>` | Fix-loop cap (default 15). |
| `--double-trace` | Trace every entry twice with independent subagents and merge both results; disagreements get a third, narrower trace. |
| `--no-commit` | Write files only; pass `--no-commit` to every `kb_checkpoint.py` call so git is never touched. |

## Conventions

- Run every `python scripts/...` command from this skill's directory (`skills/karate-bootstrap/`)
  so the relative script paths resolve; scripts are direct-path invocable, no package install.
  Pass `<root>` as an absolute path.
- `<tests>` is `<root>/karate-tests`. Every artefact the run produces lives there. Rendered
  prompts go to `<tests>/.prompts/` (ignored by the template's `.gitignore`).
- `<skill>` is this skill's absolute directory; `templates/karate-tests/README.md.tmpl` is
  referenced relative to it.
- Maven runs from `<tests>`: `mvn -B test` (JDK 17 or newer and a container engine on the
  machine; `./mvnw -B test` when Maven is not installed). Append `-Dapp.image=<tag>` when
  `--app-image` was given. Podman users: `reference/podman.md`.
- Every step names one command and one output. A step's postcondition is the file it must
  leave behind.

## Exit codes

| Code | Meaning |
|-----:|---------|
| 0 | Suite green (or green with quarantined defects listed in `defects.md`). |
| 2 | A gate or script rejected its input; the message names the gap. |
| 3 | Unsupported stack (not Spring Boot, Quarkus, ASP.NET Core or a Python web framework). |
| 4 | No schema source: no `--migrations-image` and no matching central config entry. |
| 5 | An expected output file is missing (the no-improvisation rule). |
| 6 | Stopped by a stop condition after committing what exists. |
| 7 | Container runtime, JDK 17+ or Maven missing on this machine. |

## Subagents

Three kinds, each driven by a prompt file `kb_prompt.py` renders for one entry. Read the
rendered file and pass its complete text as the subagent's prompt; add nothing, remove nothing.

| Kind | Agent | May write | Returns |
|------|-------|-----------|---------|
| trace | read-only (Explore) | nothing | JSON matching the ledger entry schema |
| rules | read-only (Explore) | `<tests>/rules/<slug>.rows.csv` only | JSON with `rows_csv` and counts |
| generate | general-purpose | files under `<tests>` only (`features/`, `stubs/`, `seed/`) | JSON listing the files written |

Save every JSON reply to `<tests>/.prompts/<kind>-<slug>.json` before you feed it to a script.
Dispatch trace subagents one at a time unless `--double-trace` asks for pairs.

## Workflow

### Step 0: Preflight

- Prerequisite: `<repo-path>` exists.
- Commands:

```bash
python scripts/kb_checkpoint.py begin --repo <repo-path>
python scripts/detect.py <root> --service-dir <sub> --out <tests>/stack.json
```

- `begin` creates and checks out `karate-bootstrap` when the repo is on its default branch and
  leaves any other branch alone. Add `--no-commit` when the flag was given (then it does
  nothing). `detect.py` checks the container runtime, JDK and Maven, then classifies the
  stack; omit `--service-dir` when there is none.
- Postcondition: `<tests>/stack.json`. Exit 3 or 7 from `detect.py` ends the run with that code.

### Step 1: Discover

- Prerequisite: `<tests>/stack.json`.
- Command:

```bash
python scripts/discover.py <root> --stack <tests>/stack.json --out-env <tests>/env-map.json --out-ledger <tests>/flow-map.yaml
```

- Postcondition: `<tests>/env-map.json` (config keys with roles, port, readiness, auth mode)
  and `<tests>/flow-map.yaml` seeded with one untraced entry per entry point.

### Step 2: Confirm entry points and auth

- Prerequisite: the two files from Step 1.
- Open `<tests>/flow-map.yaml` and the routes in the code once. For every entry point the
  regexes missed (a route, a listener), add it:

```bash
python scripts/flow_map.py add-entry --ledger <tests>/flow-map.yaml --id "<METHOD> <path>" --kind http --handler <file:line> --method <METHOD> --path <path>
python scripts/flow_map.py add-entry --ledger <tests>/flow-map.yaml --id "amq <destination>" --kind amq-subscribe --handler <file:line> --destination <destination> --type queue
```

- If `app.auth.confirmed` is `false`, or the mode is wrong, read the security configuration
  (cheat sheet: "Auth switches") and record what you found:

```bash
python scripts/flow_map.py set-auth --ledger <tests>/flow-map.yaml --mode disabled --key <ENV_VAR> --value <off-value>
python scripts/flow_map.py set-auth --ledger <tests>/flow-map.yaml --mode jwks --issuer-keys <ISSUER_ENV>,<JWKS_ENV>
```

  Use `--mode none` when the app has no auth and `--mode blocked` when it cannot be switched
  off or pointed at a test issuer.
- Postcondition: `<tests>/flow-map.yaml` lists every entry point and `app.auth` has a confirmed
  mode.

### Step 3: Trace every entry point

- Prerequisite: `<tests>/flow-map.yaml`, `<tests>/env-map.json`.
- Loop until `next` prints `{"done": true}`:

```bash
python scripts/flow_map.py next --phase traced --ledger <tests>/flow-map.yaml
python scripts/kb_prompt.py render --prompt trace --ledger <tests>/flow-map.yaml --env <tests>/env-map.json --entry "<id>" --repo <root> --out <tests>/.prompts/trace-<slug>.md
python scripts/flow_map.py merge <tests>/.prompts/trace-<slug>.json --ledger <tests>/flow-map.yaml
```

  Between `render` and `merge`, dispatch the trace subagent with the rendered prompt and save
  its JSON reply as `<tests>/.prompts/trace-<slug>.json`. `next` prints the entry id, its
  handler and the cheat sheet path; `<slug>` is the id lower-cased with non-alphanumerics
  collapsed to `-` (`POST /api/deals` becomes `post-api-deals`).
- If `merge` reports `unresolved: N` above zero, re-render with the first unresolved location
  and dispatch again, then merge again; repeat until the entry merges with zero unresolved:

```bash
python scripts/kb_prompt.py render --prompt trace --ledger <tests>/flow-map.yaml --env <tests>/env-map.json --entry "<id>" --repo <root> --focus <file:line> --out <tests>/.prompts/trace-<slug>-2.md
```

- With `--double-trace`: dispatch two independent subagents from the same rendered prompt,
  merge the first reply, then merge the second (the ledger keeps the union of exits; a `via`
  present in only one reply is a disagreement to resolve with a third, `--focus` trace).
- Gate:

```bash
python scripts/flow_map.py validate --phase traced --ledger <tests>/flow-map.yaml --repo <root> --env <tests>/env-map.json
```

  The gate also runs `verify-refs`: every exit's `via` must sit within three lines of a marker
  token from the cheat sheet, or the entry is reset to untraced. On any gap, go back to the loop
  for the entries it names. Do not edit the ledger to silence a gap.
- Postcondition: `validate --phase traced` prints `phase traced: pass`.

### Step 4: Validation rules

- Prerequisite: the traced ledger.
- Command:

```bash
python scripts/kb_rules.py extract <root> --ledger <tests>/flow-map.yaml --out-dir <tests>
```

- For every entry whose `rules.sources` has a file with `scanned: false`, render the rules
  prompt for that source, dispatch a read-only rules subagent, then append its rows and mark
  the source scanned:

```bash
python scripts/kb_prompt.py render --prompt rules --ledger <tests>/flow-map.yaml --entry "<id>" --source <source-file> --repo <root> --tests-dir <tests> --out <tests>/.prompts/rules-<slug>-<n>.md
python scripts/kb_rules.py add "<id>" <tests>/rules/<slug>.rows.csv --ledger <tests>/flow-map.yaml --out-dir <tests>
python scripts/kb_rules.py mark-scanned "<id>" <source-file> --ledger <tests>/flow-map.yaml
```

  `add` de-duplicates on field, mutation and value and assigns `rule_id`s; run it once per
  rows file even when the file is empty of new rows.
- Postcondition: every entry with validation responses has `rules.file` and a `rules.count`
  matching its CSV, and every source is `scanned: true`. The generated gate in Step 6 checks
  this.

### Step 5: Scaffold the module

- Prerequisite: the traced ledger and `<tests>/env-map.json`.
- Command:

```bash
python scripts/kb_scaffold.py <root> --ledger <tests>/flow-map.yaml --env <tests>/env-map.json --out <tests> --migrations-image <ref>
```

  Omit `--migrations-image` to resolve the image from `~/.karate-bootstrap/config.yaml`
  (`--config <path>` points elsewhere). Exit 4 means no schema source: stop and report it.
  Add `--force` only when re-scaffolding a module whose harness files you intend to refresh;
  generated content is never overwritten either way.
- Postcondition: `<tests>/pom.xml`, `<tests>/src/test/resources/kb-runtime.json`, the harness
  classes and `<tests>/defects.md`. Then:

```bash
python scripts/kb_checkpoint.py commit --repo <repo-path> --phase 5 --message "scaffold the Karate module"
```

### Step 6: Generate features

- Prerequisite: the scaffolded module and the rules files.
- Loop until `next` prints `{"done": true}`:

```bash
python scripts/flow_map.py next --phase generated --ledger <tests>/flow-map.yaml
python scripts/kb_prompt.py render --prompt generate --ledger <tests>/flow-map.yaml --env <tests>/env-map.json --entry "<id>" --repo <root> --tests-dir <tests> --out <tests>/.prompts/generate-<slug>.md
python scripts/flow_map.py mark --entry "<id>" --generated --feature features/<slug>.feature --stub stubs/<downstream>/default.json --seed seed/<slug>.sql --ledger <tests>/flow-map.yaml
```

  Between `render` and `mark`, dispatch the generate subagent (general-purpose, may write only
  under `<tests>`) and save its JSON reply as `<tests>/.prompts/generate-<slug>.json`. Pass
  every path from the reply's `features`, `stubs` and `seeds` lists to `mark` (repeat
  `--feature`, `--stub`, `--seed` as needed; omit a flag whose list is empty).
- Gate:

```bash
python scripts/flow_map.py validate --phase generated --ledger <tests>/flow-map.yaml --repo <root> --tests-dir <tests>
```

  Gaps name the entry and what is missing (a feature, a `Db.` assertion for a written table, a
  `Jms.` assertion for a published destination, a `Stubs.verify` for an outbound call, a rules
  count mismatch, an exclusive-state call without `@parallel=false`). Re-dispatch the generate
  subagent for that entry with the gap text appended to the rendered prompt, then `mark` and
  validate again.
- Postcondition: `validate --phase generated` prints `phase generated: pass`. Then:

```bash
python scripts/kb_checkpoint.py commit --repo <repo-path> --phase 6 --message "generate features, stubs and seeds"
```

### Step 7: First run

- Prerequisite: the generated gate passed.
- Self-test first, from `<tests>`: `mvn -B test -Dkb.skipContainers=true`. It compiles the
  module and runs the harness smoke feature without containers. A failure here is a scaffold
  or environment problem (JDK, Maven Central): fix the environment or report exit 7; never
  edit the Java.
- Full run, from `<tests>`: `mvn -B test` (plus `-Dapp.image=<tag>` when given). The first run
  builds the app image and can take several minutes. Then:

```bash
python scripts/kb_report.py parse --reports <tests>/target/karate-reports --out <tests>/target/report.json
python scripts/flow_map.py record-run --ledger <tests>/flow-map.yaml --report <tests>/target/report.json
python scripts/flow_map.py validate --phase green --ledger <tests>/flow-map.yaml --repo <root> --report <tests>/target/report.json --defects <tests>/defects.md
```

- If Maven produced no `target/karate-reports/*.json` at all, the app never started: treat it
  as an infra failure in Step 8 using `target/app.log` and `target/db-manager.log`.
- Postcondition: `<tests>/target/report.json`. When the green gate passes, go to Step 9.

### Step 8: Iterate until green or stopped

- Prerequisite: `<tests>/target/report.json` with failures.
- Loop:

```bash
python scripts/kb_iterate.py next --report <tests>/target/report.json --tests-dir <tests>
```

  Read the group it prints (the largest failure signature with its evidence) and classify it
  with `reference/failure-triage.md`: infra, stub-or-seed, expectation, or app-defect. Then
  log the iteration before changing anything:

```bash
python scripts/kb_iterate.py log --log <tests>/.iterations.log --signature "<signature>" --hypothesis "<one sentence>" --change "<one sentence>" --classification <class>
```

  Add `--unfixable` to an infra iteration that cannot be fixed from inside `<tests>`.
- Make the one change the hypothesis names, inside `<tests>` only. For an expectation change,
  also record it:

```bash
python scripts/flow_map.py override --ledger <tests>/flow-map.yaml --entry "<id>" --scenario "<scenario>" --field <what> --old "<expected>" --new "<observed>" --reason "<why>"
```

  For a suspected app defect, tag the scenario `@known-defect` and append the `defects.md`
  entry described in `failure-triage.md`; no override.
- Re-run the touched feature from `<tests>`:
  `mvn -B test -Dkarate.options="classpath:features/<slug>.feature"`, then the full
  `mvn -B test`, then:

```bash
python scripts/kb_report.py parse --reports <tests>/target/karate-reports --out <tests>/target/report.json
python scripts/flow_map.py record-run --ledger <tests>/flow-map.yaml --report <tests>/target/report.json
python scripts/kb_iterate.py check-stop --log <tests>/.iterations.log --report <tests>/target/report.json --max-iterations 15
python scripts/flow_map.py validate --phase green --ledger <tests>/flow-map.yaml --repo <root> --report <tests>/target/report.json --defects <tests>/defects.md
```

  `check-stop` prints `continue`, `done`, or `stop:<reason>` with exit 6. Pass the user's
  `--max-iterations` value. On `stop:` go to Step 9 and finish with exit 6. On `done` and a
  passing green gate, go to Step 9. Otherwise loop.
- Postcondition per iteration: a new line in `<tests>/.iterations.log` and a fresh
  `<tests>/target/report.json`.

### Step 9: Report

- Prerequisite: `<tests>/target/report.json` and `<tests>/defects.md`.
- Commands:

```bash
python scripts/kb_report.py summary --ledger <tests>/flow-map.yaml --defects <tests>/defects.md --report <tests>/target/report.json --template templates/karate-tests/README.md.tmpl --out <tests>/README.md
python scripts/kb_checkpoint.py commit --repo <repo-path> --phase 9 --message "first ground-truth Karate suite"
```

- Postcondition: `<tests>/README.md`. Tell the user: the branch and commit, the counts table
  `summary` printed, how many scenarios are quarantined and where `defects.md` is, the auth
  and schema modes used, and how to run the suite (`cd karate-tests && mvn test`). Exit 0 on a
  passing green gate, 6 after a stop condition.

## Token budget

One trace subagent per entry point (a small service has 3 to 10), one rules subagent per
validation source, one generate subagent per entry point, then the fix loop. Budget about 30k
output tokens per entry point for trace, rules and generate together, and 5 to 15k per fix
iteration. Scripts do no LLM work.

## Caveats

- Postgres only; ActiveMQ Artemis over AMQP 1.0 only; downstream HTTP is stubbed, never called.
- The generated suite documents current behaviour. A quarantined scenario is a suspected
  defect for a developer to judge, not a verdict.
- No live LLM in this repo's tests: `kb_check_skill.py` lints these commands and
  `tests/test_kb_dry_run.py` executes the chain with canned subagent replies.
- Windows: `mvn` needs `JAVA_HOME`; the template test in this repo shows the exact value used.
````

- [ ] **Step 3: Lint the new SKILL.md and run its tests**

Run: `python skills/karate-bootstrap/scripts/kb_check_skill.py` then `pytest skills/karate-bootstrap/tests/test_kb_check_skill.py -q`
Expected: `ok: all SKILL.md commands match their scripts (...)`; 7 passed. A reported flag means the SKILL.md command drifted from `argparse`: fix the SKILL.md command (the script is the authority) unless the spec's command block says otherwise, in which case report it.

- [ ] **Step 4: Add the CI step to `.github/workflows/test.yml`**

In the `test` job, after `- run: python skills/tech-debt-scan/scripts/skill_check.py` add:

```yaml
      - run: python skills/karate-bootstrap/scripts/kb_check_skill.py
```

- [ ] **Step 5: Full gate and commit**

Run: `pytest -q` then `ruff check .` then `mypy` then `wc -l skills/karate-bootstrap/SKILL.md`
Expected: green; the line count is under 500.

```bash
git add skills/karate-bootstrap/SKILL.md skills/karate-bootstrap/tests/test_kb_check_skill.py .github/workflows/test.yml
git commit -m "feat(karate-bootstrap): SKILL.md procedure with linted commands

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Trigger eval, `SKILL.md` shape test, repo README

**Confidence:** 93%. Pure text plus a frontmatter test. The description wording follows the sibling skill's (third person, "Use when ..." triggers, an explicit "Not for unit tests"); the test pins the trigger terms the eval document lists.

**Files:**
- Create: `skills/karate-bootstrap/evals/trigger-eval.md`
- Create: `skills/karate-bootstrap/tests/test_kb_skill_md.py`
- Modify: `README.md` (new section before `## Output formats`)

**Interfaces:**
- Consumes: `SKILL.md` (Task 6), `scripts/` listing.
- Produces: the eval document Plan 4's manual run follows; the README section users install from.

- [ ] **Step 1: Write `tests/test_kb_skill_md.py`**

```python
from __future__ import annotations

import re
from pathlib import Path

import yaml

SKILL_DIR = Path(__file__).resolve().parent.parent
SKILL = SKILL_DIR / "SKILL.md"
EVAL = SKILL_DIR / "evals" / "trigger-eval.md"

# Scripts the procedure never calls directly: shared modules and the CI linter.
LIBRARY_SCRIPTS = {"kb_common.py", "markers.py", "kb_features.py", "kb_check_skill.py"}
POSITIVE_TERMS = ("karate", "integration test", "testcontainers")


def _frontmatter() -> dict[str, object]:
    text = SKILL.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    end = text.index("\n---\n", 4)
    data = yaml.safe_load(text[4:end])
    assert isinstance(data, dict)
    return data


def test_frontmatter_names_the_skill_and_its_trigger() -> None:
    data = _frontmatter()
    assert data["name"] == "karate-bootstrap"
    assert data["triggers"] == ["/karate-bootstrap"]


def test_description_carries_the_positive_terms_and_excludes_unit_tests() -> None:
    description = str(_frontmatter()["description"])
    assert len(description) <= 1024
    lowered = description.lower()
    for term in POSITIVE_TERMS:
        assert term in lowered, term
    assert "not for unit tests" in lowered
    assert "unit test" not in lowered.replace("not for unit tests", "")


def test_skill_md_is_under_500_lines_with_ten_steps() -> None:
    lines = SKILL.read_text(encoding="utf-8").splitlines()
    assert len(lines) < 500
    numbers = [int(match.group(1)) for line in lines
               if (match := re.match(r"^### Step (\d+):", line))]
    assert numbers == list(range(10))


def test_every_step_names_a_postcondition() -> None:
    text = SKILL.read_text(encoding="utf-8")
    sections = re.split(r"^### Step \d+:", text, flags=re.MULTILINE)[1:]
    for index, section in enumerate(sections):
        assert "Postcondition" in section, f"Step {index} has no postcondition"


def test_every_runnable_script_appears_in_the_procedure() -> None:
    text = SKILL.read_text(encoding="utf-8")
    for script in sorted((SKILL_DIR / "scripts").glob("*.py")):
        if script.name in LIBRARY_SCRIPTS:
            continue
        assert f"scripts/{script.name}" in text, script.name


def test_reference_and_prompt_files_named_in_skill_md_exist() -> None:
    text = SKILL.read_text(encoding="utf-8")
    for rel in re.findall(r"`(reference/[a-z0-9-]+\.md)`", text):
        assert (SKILL_DIR / rel).is_file(), rel
    assert (SKILL_DIR / "templates" / "karate-tests" / "README.md.tmpl").is_file()


def test_trigger_eval_lists_positive_and_negative_prompts() -> None:
    text = EVAL.read_text(encoding="utf-8")
    assert "## Must fire" in text and "## Must not fire" in text
    positives = text[text.index("## Must fire"):text.index("## Must not fire")]
    assert positives.count("\n- ") >= 4
    assert "unit test" in text[text.index("## Must not fire"):].lower()
```

- [ ] **Step 2: Run it to confirm the eval file is missing**

Run: `pytest skills/karate-bootstrap/tests/test_kb_skill_md.py -q`
Expected: the six `SKILL.md` tests pass (Task 6 landed it) and `test_trigger_eval_lists_positive_and_negative_prompts` fails with `FileNotFoundError`.

- [ ] **Step 3: Write `evals/trigger-eval.md`**

````markdown
# Trigger eval for karate-bootstrap

Checks that the skill's description makes Claude Code pick `karate-bootstrap` for the requests
it is for and leave it alone for the ones it is not. This repository's tests never call a
model, so the automated part is `tests/test_kb_skill_md.py` (the description must carry the
key terms of every prompt below and must say it is not for unit tests). The model-in-the-loop
part is manual.

## How to run the manual part

1. Install the skill (README, "karate-bootstrap") in a Claude Code session with no other
   karate-related skill.
2. For each prompt below, start a fresh conversation in a repository that matches the prompt
   and paste it verbatim.
3. Record whether Claude invoked `/karate-bootstrap` (or announced it was using the skill)
   before doing anything else.
4. Pass criterion: every "must fire" prompt fires; no "must not fire" prompt fires. Record the
   run date and model in the table at the end.

## Must fire

- Add karate tests to this service.
- Bootstrap integration tests for this repo; it has none.
- Build a testcontainers suite for this service so it runs in our ADO pipeline.
- We need a first set of Karate feature files for the deals API, running against real
  Postgres and Artemis in containers.
- Give this Spring Boot app a ground-truth integration test suite I can run locally.

## Must not fire

- Add unit tests for DealService.
- Write JUnit tests for the validator class.
- Increase the unit test coverage of the pricing module.
- Run the existing Karate suite and tell me what fails.

## Runs

| Date | Model | Must fire | Must not fire | Notes |
|------|-------|-----------|---------------|-------|
| (none yet) | | | | |
````

- [ ] **Step 4: Add the README section**

In `README.md`, immediately before the `## Output formats` heading, insert:

````markdown
## Also in this repo: karate-bootstrap

`karate-bootstrap` takes a Spring Boot, Quarkus, ASP.NET Core or Python service that has no
Karate tests and leaves it with a first ground-truth suite under `karate-tests/` that runs
green under Testcontainers (Postgres, ActiveMQ Artemis over AMQP 1.0, WireMock for
downstream HTTP, the shared db-manager image for the schema), locally and in Azure DevOps.

Install it the same way:

```bash
ln -s "$PWD/claude-skills/skills/karate-bootstrap" ~/.claude/skills/karate-bootstrap
```

Then, in Claude Code:

```
/karate-bootstrap <repo-path> [--service-dir <sub>] [--migrations-image <ref>] [--app-image <tag>]
                  [--max-iterations 15] [--double-trace] [--no-commit]
```

The run scans the repo, traces every endpoint and listener to its database writes, message
publishes and outbound calls, extracts validation rules as CSV data, scaffolds a Maven module
with the Testcontainers harness, generates the features, runs them and iterates until green
or a stop condition, quarantining suspected app defects in `karate-tests/defects.md`. By
default it commits at each phase gate on a `karate-bootstrap` branch and never pushes.

Requirements on the machine: Python 3.11+ with `pyyaml`, JDK 17+, Maven (or the bundled
wrapper), and a container engine (docker or podman; see
`skills/karate-bootstrap/reference/podman.md`). See
[`skills/karate-bootstrap/SKILL.md`](skills/karate-bootstrap/SKILL.md) for every pinned
command, and `docs/superpowers/specs/2026-09-05-karate-bootstrap-design.md` for the design.
````

- [ ] **Step 5: Run the tests, the full gate, and commit**

Run: `pytest skills/karate-bootstrap/tests/test_kb_skill_md.py -q` then `pytest -q` then `ruff check .` then `mypy`
Expected: 7 passed; everything green.

```bash
git add skills/karate-bootstrap/evals/trigger-eval.md skills/karate-bootstrap/tests/test_kb_skill_md.py README.md
git commit -m "docs(karate-bootstrap): trigger eval, SKILL.md shape test and README section

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Dry-run eval on both fixture repos

**Confidence:** 92%. The `spring-mini` chain ran green today exactly as scripted below (detect, discover, trace loop, traced gate, rules, scaffold, generate loop and gate, report, green gate, check-stop, summary). The `dotnet-mini` traces below point `via` at lines read from the fixture today (`Services/DealService.cs` 25, 28, 29; `Messaging/DealRequestedConsumer.cs` 28), each carrying a marker token `verify-refs` accepts (`FromJsonAsync`, `SaveChanges`, `.Send(`). The test locates lines by content, not number, so fixture edits do not break it. Each command runs through `subprocess` with the same invocation `SKILL.md` prints, so a script whose CLI drifts fails here as well as in the linter.

**Files:**
- Create: `skills/karate-bootstrap/tests/test_kb_dry_run.py`

**Interfaces:**
- Consumes: every script CLI; the fixtures `spring-mini` and `dotnet-mini`; `tests/fixtures/karate-reports/features.harness-smoke.json`; `kb_helpers.line_of`.
- Produces: the regression test named in spec section 11.

- [ ] **Step 1: Write `tests/test_kb_dry_run.py`**

```python
"""Every pinned SKILL.md command, in order, on both fixture repos, with canned subagent replies.

No mocking and no containers: the trace, rules and generate subagents are replaced by the
JSON, CSV and feature text a real run would have produced; everything else is the real
script wired exactly as SKILL.md prescribes, run through subprocess so the CLI surface is
exercised too. Git steps run against a throwaway repository.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from kb_common import read_json
from kb_helpers import line_of
from kb_rules import slug_for

SKILL = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
REPORTS = FIXTURES / "karate-reports"
IMAGE = "registry.example/db-manager:1"


def run(*args: str, cwd: Path | None = None) -> str:
    proc = subprocess.run([sys.executable, *args], cwd=cwd or SKILL, capture_output=True,
                          text=True)
    assert proc.returncode == 0, f"{' '.join(args)}\n{proc.stdout}\n{proc.stderr}"
    return proc.stdout


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def spring_traces(repo: Path) -> dict[str, dict[str, Any]]:
    service = "src/main/java/com/acme/shipments/ShipmentService.java"
    listener = "src/main/java/com/acme/shipments/ShipmentEventsListener.java"
    request = "src/main/java/com/acme/shipments/ShipmentRequest.java"
    return {
        "POST /api/shipments": {
            "id": "POST /api/shipments", "auth": "required",
            "request": {"content_type": "application/json", "schema_ref": request,
                        "example": "seed/examples/post-api-shipments.json"},
            "responses": [{"status": 201, "when": "happy"},
                          {"status": 400, "when": "validation", "rules": True}],
            "reads": [{"kind": "http-in", "host_key": "PRICING_BASE_URL", "method": "GET",
                       "path": "/rates/{countryCode}"}],
            "exits": [
                {"kind": "db-write", "table": "shipments", "op": "insert",
                 "via": f"{service}:{line_of(repo / service, 'repository.save')}"},
                {"kind": "amq-publish", "destination": "shipment.created", "type": "queue",
                 "via": f"{service}:{line_of(repo / service, 'convertAndSend')}"},
                {"kind": "http-out", "host_key": "PRICING_BASE_URL", "method": "GET",
                 "path": "/rates/{countryCode}",
                 "via": f"{service}:{line_of(repo / service, 'getForObject')}"},
            ],
            "rules": {"sources": [{"file": request, "scanned": False}]},
            "unresolved": [],
        },
        "GET /api/shipments/{id}": {
            "id": "GET /api/shipments/{id}", "exits": [], "exits_none_reason": "read-only lookup",
            "unresolved": [], "responses": [{"status": 200, "when": "found"},
                                            {"status": 404, "when": "missing"}],
        },
        "amq shipment.requested": {
            "id": "amq shipment.requested", "unresolved": [],
            "exits": [{"kind": "db-write", "table": "shipments", "op": "insert",
                       "via": f"{listener}:{line_of(repo / listener, 'repository.save')}"}],
        },
    }


def dotnet_traces(repo: Path) -> dict[str, dict[str, Any]]:
    service = "Services/DealService.cs"
    consumer = "Messaging/DealRequestedConsumer.cs"
    validator = "Validators/DealRequestValidator.cs"
    return {
        "POST /api/deals": {
            "id": "POST /api/deals", "auth": "required",
            "request": {"content_type": "application/json", "schema_ref": "Data/Deal.cs",
                        "example": "seed/examples/post-api-deals.json"},
            "responses": [{"status": 201, "when": "happy"},
                          {"status": 400, "when": "validation", "rules": True}],
            "reads": [{"kind": "http-in", "host_key": "Pricing__BaseUrl", "method": "GET",
                       "path": "/prices/{product}"}],
            "exits": [
                {"kind": "db-write", "table": "deals", "op": "insert",
                 "via": f"{service}:{line_of(repo / service, 'SaveChangesAsync')}"},
                {"kind": "amq-publish", "destination": "deal.created", "type": "queue",
                 "via": f"{service}:{line_of(repo / service, '_producer.Send(')}"},
                {"kind": "http-out", "host_key": "Pricing__BaseUrl", "method": "GET",
                 "path": "/prices/{product}",
                 "via": f"{service}:{line_of(repo / service, 'GetFromJsonAsync')}"},
            ],
            "rules": {"sources": [{"file": validator, "scanned": False}]},
            "unresolved": [],
        },
        "GET /api/deals/{id}": {
            "id": "GET /api/deals/{id}", "exits": [], "exits_none_reason": "read-only lookup",
            "unresolved": [], "responses": [{"status": 200, "when": "found"},
                                            {"status": 404, "when": "missing"}],
        },
        "amq deal.requested": {
            "id": "amq deal.requested", "unresolved": [],
            "exits": [{"kind": "db-write", "table": "deals", "op": "update",
                       "via": f"{consumer}:{line_of(repo / consumer, '_db.SaveChanges()')}"}],
        },
    }


def feature_text(table: str, destination: str, downstream_path: str) -> str:
    return (
        f"@smoke\nFeature: canned\n\nBackground:\n  * def uid = java.util.UUID.randomUUID() + ''\n"
        f"  * call read('classpath:common/reset.feature') {{ watch: ['{destination}'] }}\n\n"
        f"Scenario: happy\n  * def row = Db.row('{table}', {{ reference: uid }})\n"
        f"  * def msg = Jms.await('{destination}', 5000, {{ id: uid }})\n"
        f"  * Stubs.verify('GET', '{downstream_path}', 1)\n"
    )


CASES: dict[str, tuple[Callable[[Path], dict[str, dict[str, Any]]], str, str, str, str]] = {
    "spring-mini": (spring_traces, "POST /api/shipments", "shipments", "shipment.created",
                    "/pricing/rates/GB"),
    "dotnet-mini": (dotnet_traces, "POST /api/deals", "deals", "deal.created",
                    "/pricing/prices/BRENT"),
}


@pytest.mark.parametrize("fixture", sorted(CASES))
def test_pinned_command_chain_runs_green(tmp_path: Path, fixture: str) -> None:
    traces_for, post_id, table, destination, downstream_path = CASES[fixture]
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURES / fixture, repo)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "kb@example.com")
    git(repo, "config", "user.name", "kb")
    git(repo, "add", "--", ".")
    git(repo, "commit", "-q", "-m", "fixture")
    tests = repo / "karate-tests"
    tests.mkdir()
    ledger, env, stack = tests / "flow-map.yaml", tests / "env-map.json", tests / "stack.json"
    prompts = tests / ".prompts"
    traces = traces_for(repo)
    post_slug = slug_for(post_id)

    # Step 0 and 1
    assert "karate-bootstrap" in run("scripts/kb_checkpoint.py", "begin", "--repo", str(repo))
    assert git(repo, "branch", "--show-current") == "karate-bootstrap"
    run("scripts/detect.py", str(repo), "--out", str(stack), "--skip-toolchain")
    run("scripts/discover.py", str(repo), "--stack", str(stack), "--out-env", str(env),
        "--out-ledger", str(ledger))
    seeded = yaml.safe_load(ledger.read_text(encoding="utf-8"))
    assert {e["id"] for e in seeded["entry_points"]} == set(traces)

    # Step 3: trace loop with rendered prompts and canned replies
    while True:
        pending = json.loads(run("scripts/flow_map.py", "next", "--phase", "traced",
                                 "--ledger", str(ledger)))
        if pending.get("done"):
            break
        prompt = prompts / "trace.md"
        run("scripts/kb_prompt.py", "render", "--prompt", "trace", "--ledger", str(ledger),
            "--env", str(env), "--entry", pending["id"], "--repo", str(repo), "--out", str(prompt))
        assert pending["id"] in prompt.read_text(encoding="utf-8")
        reply = prompts / "trace.json"
        reply.write_text(json.dumps(traces[pending["id"]]), encoding="utf-8")
        assert "unresolved: 0" in run("scripts/flow_map.py", "merge", str(reply),
                                      "--ledger", str(ledger))
    assert "phase traced: pass" in run("scripts/flow_map.py", "validate", "--phase", "traced",
                                       "--ledger", str(ledger), "--repo", str(repo),
                                       "--env", str(env))

    # Step 4: rules, candidates confirmed verbatim
    run("scripts/kb_rules.py", "extract", str(repo), "--ledger", str(ledger),
        "--out-dir", str(tests))
    source = traces[post_id]["rules"]["sources"][0]["file"]
    run("scripts/kb_prompt.py", "render", "--prompt", "rules", "--ledger", str(ledger),
        "--entry", post_id, "--source", source, "--repo", str(repo), "--tests-dir", str(tests),
        "--out", str(prompts / "rules.md"))
    candidates = tests / "rules" / f"{post_slug}.candidates.csv"
    rows = tests / "rules" / f"{post_slug}.rows.csv"
    rows.write_text(candidates.read_text(encoding="utf-8"), encoding="utf-8")
    assert f"{post_id}:" in run("scripts/kb_rules.py", "add", post_id, str(rows),
                                "--ledger", str(ledger), "--out-dir", str(tests))
    run("scripts/kb_rules.py", "mark-scanned", post_id, source, "--ledger", str(ledger))

    # Step 5: scaffold and checkpoint
    run("scripts/kb_scaffold.py", str(repo), "--ledger", str(ledger), "--env", str(env),
        "--out", str(tests), "--migrations-image", IMAGE)
    runtime = read_json(tests / "src/test/resources/kb-runtime.json")
    assert runtime["migrations"]["image"] == IMAGE and runtime["amq"]["queues"]
    assert '"committed": true' in run("scripts/kb_checkpoint.py", "commit", "--repo", str(repo),
                                      "--phase", "5", "--message", "scaffold")

    # Step 6: generate loop with a canned feature, stub and seed per entry
    features = tests / "src/test/resources/features"
    (tests / "stubs/pricing").mkdir(parents=True)
    (tests / "stubs/pricing/default.json").write_text('{"mappings":[]}', encoding="utf-8")
    (tests / "seed/examples").mkdir(parents=True)
    (tests / "seed/examples" / f"{post_slug}.json").write_text("{}", encoding="utf-8")
    (tests / "seed" / f"{post_slug}.sql").write_text("-- nothing to seed\n", encoding="utf-8")
    while True:
        pending = json.loads(run("scripts/flow_map.py", "next", "--phase", "generated",
                                 "--ledger", str(ledger)))
        if pending.get("done"):
            break
        run("scripts/kb_prompt.py", "render", "--prompt", "generate", "--ledger", str(ledger),
            "--env", str(env), "--entry", pending["id"], "--repo", str(repo),
            "--tests-dir", str(tests), "--out", str(prompts / "generate.md"))
        (features / f"{post_slug}.feature").write_text(
            feature_text(table, destination, downstream_path), encoding="utf-8")
        run("scripts/flow_map.py", "mark", "--entry", pending["id"], "--generated",
            "--feature", f"features/{post_slug}.feature", "--stub", "stubs/pricing/default.json",
            "--seed", f"seed/{post_slug}.sql", "--ledger", str(ledger))
    assert "phase generated: pass" in run("scripts/flow_map.py", "validate", "--phase",
                                          "generated", "--ledger", str(ledger),
                                          "--repo", str(repo), "--tests-dir", str(tests))
    run("scripts/kb_checkpoint.py", "commit", "--repo", str(repo), "--phase", "6",
        "--message", "generate")

    # Step 7: a captured green run stands in for mvn test
    reports = tests / "target/karate-reports"
    reports.mkdir(parents=True)
    shutil.copy2(REPORTS / "features.harness-smoke.json", reports / "features.harness-smoke.json")
    report = tests / "target/report.json"
    run("scripts/kb_report.py", "parse", "--reports", str(reports), "--out", str(report))
    assert "failing: 0" in run("scripts/flow_map.py", "record-run", "--ledger", str(ledger),
                               "--report", str(report))
    assert "phase green: pass" in run("scripts/flow_map.py", "validate", "--phase", "green",
                                      "--ledger", str(ledger), "--repo", str(repo),
                                      "--report", str(report),
                                      "--defects", str(tests / "defects.md"))
    assert run("scripts/kb_iterate.py", "check-stop", "--log", str(tests / ".iterations.log"),
               "--report", str(report), "--max-iterations", "15").strip() == "done"

    # Step 9: report and final checkpoint
    run("scripts/kb_report.py", "summary", "--ledger", str(ledger), "--defects",
        str(tests / "defects.md"), "--report", str(report), "--template",
        str(SKILL / "templates/karate-tests/README.md.tmpl"), "--out", str(tests / "README.md"))
    readme = (tests / "README.md").read_text(encoding="utf-8")
    assert "| Entry points | 3 |" in readme and "$" not in readme.replace("${XDG_RUNTIME_DIR}", "")
    run("scripts/kb_checkpoint.py", "commit", "--repo", str(repo), "--phase", "9",
        "--message", "report")
    assert git(repo, "status", "--short") == ""
    assert not any(".prompts" in line for line in git(repo, "ls-files").splitlines())
```

- [ ] **Step 2: Run it**

Run: `pytest skills/karate-bootstrap/tests/test_kb_dry_run.py -v`
Expected: 2 passed (about 20 seconds each; every command is a subprocess). A failure prints the exact command and its output. The `.prompts` assertion proves the template's `.gitignore` keeps rendered prompts out of the checkpoint commits.

- [ ] **Step 3: Full gate and commit**

Run: `pytest -q` then `ruff check .` then `mypy`
Expected: green.

```bash
git add skills/karate-bootstrap/tests/test_kb_dry_run.py
git commit -m "test(karate-bootstrap): dry-run eval executes the pinned command chain on both fixtures

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Assumptions

Three-bucket surface as the standards document asks. **Real concerns needing a choice: 0.** The three decisions this plan rests on (Q1 prompt rendering by `kb_prompt.py`, Q2 the checked-in trigger eval with a description test, Q3 the Python-only dry run) and finding F1 (the four ledger commands) were put to the user on the visualiser page and answered before this plan was written; they are recorded in the spec amendment `dc15a94`.

### Verified safe

- The full pinned command chain ran green today on `spring-mini` with canned subagent outputs and no containers (3 entries traced and gated, 9 rules rows, 28 files scaffolded, generated gate, report parse, green gate, `check-stop` `done`, README rendered); Task 8 re-executes it on both fixtures in CI.
- Every command in `SKILL.md` was copied from the scripts' `argparse` definitions listed during planning, and `kb_check_skill.py` (a port of the linter that has guarded `tech-debt-scan` since PR #5) lints them in CI.
- `flow_map.next` already returns `cheat_sheet` as `reference/stack-<stack>.md`, so `kb_prompt.py` resolves the sheet without a new lookup; `markers.tokens_for` is the single source the sheet test reads.
- `merge_entry`, `add_rows`, `record_files` and `parse_feature` validate the prompts' embedded examples in tests, so the examples cannot drift from the schemas.
- `dotnet-mini`'s marker lines (`GetFromJsonAsync`, `SaveChangesAsync`, `_producer.Send(`, `_db.SaveChanges()`) were read from the fixture today and are located by content in the test.
- The template `.gitignore` already excludes `target/`; adding `.prompts/` keeps rendered prompts out of every `kb_checkpoint.py commit` (asserted by the dry run).

### Minor, accepted

- Prompt quality for a live Opus 4.8 or Sonnet 4.6 run is not measurable in this repository; Plan 4's fixture runs are that eval, and the prompt files are plain markdown the user can tune at work.
- `SKILL.md` names the subagent kind (read-only versus general-purpose) as guidance; the exact Agent tool name differs by harness.
- `--double-trace` is a `SKILL.md` procedure (two merges, `--focus` on disagreement), not a script; the ledger keeps the last merge's exits, so the procedure tells the agent to merge the reply with more exits second.
- The dry run stands in `features.harness-smoke.json` for `mvn test`; compiling the scaffolded module is Plan 2's Maven gate and Plan 4's live runs.
- The `karate-notes.md` warning that `reset.feature` variables leak into the caller's scope is documentation, not a fix (the Plan 2 final review listed it as Minor).
- Quarkus and Python have cheat sheets without fixture apps (spec 12); their token tables are checked, their prose is not exercised until a real repo.

## Plan 3 exit criteria

- `pytest -q`, `ruff check .` and `mypy` green; `python skills/karate-bootstrap/scripts/kb_check_skill.py` prints `ok`; both CI jobs green on the PR.
- `SKILL.md` under 500 lines with ten steps, each with a pinned command and a postcondition; every runnable script named in it.
- The repo contains no `karate-tests/.prompts/` output, no `target/` output and no `.superpowers/` files ([[stage-by-path]]).
- Memory sweep recorded: every reviewer finding that led to a fix commit; the Plan 3 decisions; anything Plan 4 must know about running the skill for real.
- Handoff through `superpowers:finishing-a-development-branch` (push the feature branch, open the PR against `main`).

## Self-review record

Run after the plan was written, against spec commit `dc15a94`.

1. **Spec coverage.** 5.2 `add-entry` and `set-auth`: Task 1 and Step 2 of `SKILL.md`. 5.3 trace loop, `kb_prompt.py render`, `--focus`, `verify-refs` in the gate, `--double-trace`: Tasks 2 and 6. 5.4 rules loop with the rows file and `add`/`mark-scanned`: Tasks 2 and 6. 5.5 scaffold command and `--config`/`--force` notes: Task 6. 5.6 generate loop with `mark --feature/--stub/--seed` and the gate: Tasks 1, 2, 6. 5.7 run, `record-run`, `override`, iterate loop, stop conditions, quarantine: Tasks 1, 4, 6. 5.8 summary: Task 6. 8 cheat sheets: Task 3. 9 packaging (`kb_prompt.py`, `kb_check_skill.py`, `prompts/`, `evals/`, `SKILL.md` rules, invocation, git behaviour, exit codes): Tasks 2, 5, 6, 7. 10 local and CI: Tasks 4 and 6. 11 trigger eval and dry run: Tasks 7 and 8. Not in this plan by design: fixture apps, db-manager images, live container runs (Plan 4).
2. **Placeholder scan.** No TBD, TODO, "similar to Task N" or "add error handling"; every code and document step carries its content.
3. **Type and name consistency.** `new_entry`, `add_entry`, `record_files`, `record_run`, `add_override` and the CLI flags (`--feature`, `--stub`, `--seed`, `--id`, `--kind`, `--handler`, `--method`, `--path`, `--destination`, `--type`, `--scenario`, `--field`, `--old`, `--new`, `--reason`) match between Task 1's code, its tests, `SKILL.md` and the dry run. `kb_prompt.py`'s `--prompt/--ledger/--entry/--repo/--out/--env/--tests-dir/--source/--focus` match between the module, its tests, `SKILL.md` and the dry run. Prompt placeholders match the context table. The reference headings match between the sheets and `test_kb_reference.py`. `kb_check_skill` names match the sibling's API.
4. **Cross-read.** `SKILL.md` Step 6 tells the agent to pass every path from the generate reply to `mark`; the generate prompt's reply example lists `features`, `stubs`, `seeds`. `SKILL.md` Step 8's `override` flags match `flow_map.py override`. The rules prompt says the subagent writes `rules/<slug>.rows.csv`, `SKILL.md` Step 4 appends it with `add`, and the dry run does the same.
