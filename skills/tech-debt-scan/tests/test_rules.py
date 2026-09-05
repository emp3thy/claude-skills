"""rules.py: deterministic pipeline-infra, manifest, release and ownership findings."""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from config import DEFAULTS, deep_merge
from evaluate import evaluate
from inventory import MAX_SCAN_BYTES, build_all, write_json
from make_history import CORPUS_ROOT
from rules import fingerprint, run_rules

NOW = datetime(2026, 9, 4, tzinfo=UTC)
Repo = tuple[Path, dict[str, Any]]
Finding = dict[str, Any]


@pytest.fixture(scope="module")
def service_py(service_py_repo: Path) -> Repo:
    inventory, _ = build_all(service_py_repo, churn_months=240)
    return service_py_repo, inventory


@pytest.fixture(scope="module")
def web_ts(web_ts_repo: Path) -> Repo:
    inventory, _ = build_all(web_ts_repo, churn_months=240)
    return web_ts_repo, inventory


@pytest.fixture(scope="module")
def mixed(mixed_decoys_repo: Path) -> Repo:
    inventory, _ = build_all(mixed_decoys_repo, churn_months=240)
    return mixed_decoys_repo, inventory


def _run(repo: Repo, config: dict[str, Any] | None = None) -> list[Finding]:
    findings, _leads = run_rules(repo[0], repo[1], config or DEFAULTS, now=NOW)
    return findings


def _leads(repo: Repo) -> dict[str, list[dict[str, Any]]]:
    _findings, leads = run_rules(repo[0], repo[1], DEFAULTS, now=NOW)
    return leads


def _at(findings: list[Finding], family: str, path: str | None) -> Finding | None:
    for finding in findings:
        if finding["family"] == family and finding["evidence"][0]["file"] == path:
            return finding
    return None


def _rules(finding: Finding | None) -> set[str]:
    return set(finding["confirmed_by"]) if finding else set()


def test_finding_schema_source_tier_and_one_per_file(service_py: Repo) -> None:
    findings = _run(service_py)
    keys = [(f["family"], f["evidence"][0]["file"]) for f in findings]
    assert len(keys) == len(set(keys))
    ci = _at(findings, "pipeline-infra", ".github/workflows/ci.yml")
    assert ci is not None
    assert list(ci) == [
        "fingerprint", "quote_hash", "family", "debt_type", "type_id", "title", "severity",
        "effort", "source", "rule_id", "note", "evidence", "confirmed_by", "signals_cited",
        "signals", "tier",
    ]
    assert (ci["source"], ci["tier"], ci["debt_type"], ci["type_id"]) == (
        "rule", "A", "build", "TD-14",
    )
    assert _rules(ci) == {
        "rule:ci.no-timeout", "rule:ci.no-permissions", "rule:ci.unpinned-action",
        "rule:ci.mutable-runner", "rule:ci.no-cache",
    }
    assert ci["severity"] == 2
    assert ci["effort"] == "S"
    assert ci["rule_id"].startswith("ci.")
    assert all(e["quote_verified"] is True for e in ci["evidence"])
    assert all(e["line_start"] == e["line_end"] for e in ci["evidence"])
    assert len(ci["fingerprint"]) == 16 and len(ci["quote_hash"]) == 40
    assert ci["signals"]["path_class"] == "source"  # the artefact's path class, not its class
    assert ci["signals"]["in_hotspot_band"] is False
    assert len(ci["title"]) <= 80
    assert ci["signals_cited"] == []


def test_fingerprint_matches_the_merge_formula() -> None:
    inner = hashlib.sha1(b"uses: actions/checkout@v4").hexdigest()
    outer = hashlib.sha1(f"pipeline-infra|.github/workflows/ci.yml|{inner}".encode()).hexdigest()
    got = fingerprint("pipeline-infra", ".github/workflows/ci.yml", "uses:   actions/checkout@v4")
    assert got == (outer[:16], inner)


def test_release_workflow_without_permissions_is_severity_3(service_py: Repo) -> None:
    release = _at(_run(service_py), "pipeline-infra", ".github/workflows/release.yml")
    assert release is not None
    assert release["severity"] == 3
    assert "rule:ci.no-permissions" in _rules(release)
    assert "rule:ci.unpinned-action" not in _rules(release)
    assert "rule:ci.no-timeout" not in _rules(release)
    assert "rule:ci.mutable-runner" not in _rules(release)


def test_clean_workflow_and_commented_job(web_ts: Repo, mixed: Repo) -> None:
    assert _at(_run(web_ts), "pipeline-infra", ".github/workflows/ci.yml") is None
    ci = _at(_run(mixed), "pipeline-infra", ".github/workflows/ci.yml")
    assert _rules(ci) == {
        "rule:ci.continue-on-error", "rule:ci.unpinned-action", "rule:ci.mutable-runner",
        "rule:ci.commented-job",
    }
    assert ci is not None and ci["severity"] == 2


def test_container_rules_and_dev_only_drop(service_py: Repo, mixed: Repo) -> None:
    docker = _at(_run(service_py), "pipeline-infra", "Dockerfile")
    assert _rules(docker) == {"rule:container.no-user", "rule:container.unversioned-install"}
    assert docker is not None
    assert docker["severity"] == 2
    assert (docker["debt_type"], docker["type_id"]) == ("infrastructure", "TD-19")
    mixed_findings = _run(mixed)
    assert _rules(_at(mixed_findings, "pipeline-infra", "Dockerfile")) == {
        "rule:container.unversioned-install",
    }
    dev = _at(mixed_findings, "pipeline-infra", "docker-compose.dev.yml")
    assert _rules(dev) == {"rule:container.latest-image"}
    assert dev is not None
    assert dev["severity"] == 1  # dev-only path drops one severity
    assert [e["line_start"] for e in dev["evidence"]] == [3, 5]
    assert _at(mixed_findings, "pipeline-infra", "docker-compose.yml") is None


def test_credential_in_a_dockerfile_quote_is_redacted(tmp_path: Path) -> None:
    """A credential-shaped value must never survive unredacted in rule-findings.json."""
    from rules import _main

    secret = "abcdefghijkl0123"
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "Dockerfile").write_text(
        "FROM python:3.11-slim\n"
        f'RUN export API_TOKEN="{secret}" && pip install requests\n'
        "USER app\n",
        encoding="utf-8",
    )
    inventory, _ = build_all(repo)
    findings, _leads = run_rules(repo, inventory, DEFAULTS, now=NOW)
    docker = _at(findings, "pipeline-infra", "Dockerfile")
    assert _rules(docker) == {"rule:container.unversioned-install"}
    assert docker is not None
    assert secret not in json.dumps(docker)
    assert "abcd***" in docker["evidence"][0]["quote"]

    workdir = tmp_path / "wd"
    write_json(workdir / "inventory.json", inventory)
    assert _main([str(repo), "--workdir", str(workdir)]) == 0
    raw = (workdir / "rule-findings.json").read_bytes()
    assert secret.encode("utf-8") not in raw
    assert b"abcd***" in raw


def test_artefacts_under_a_tests_tree_never_become_findings(tmp_path: Path) -> None:
    """Spec 4.2: an artefact's path_class disables the rule groups on it."""
    dockerfile = "FROM alpine\nRUN apk add curl\n"
    repo = tmp_path / "repo"
    (repo / "tests" / "fixtures" / "x").mkdir(parents=True)
    (repo / "tests" / "fixtures" / "x" / "Dockerfile").write_text(dockerfile, encoding="utf-8")
    (repo / "Dockerfile").write_text(dockerfile, encoding="utf-8")
    inventory, _ = build_all(repo)
    classes = {
        str(a["path"]): a["path_class"] for a in inventory["artefacts"]["container"]
    }
    assert classes == {"Dockerfile": "source", "tests/fixtures/x/Dockerfile": "tests"}
    findings, _leads = run_rules(repo, inventory, DEFAULTS, now=NOW)
    assert [f["evidence"][0]["file"] for f in findings] == ["Dockerfile"]
    assert findings[0]["signals"]["path_class"] == "source"


def test_skipped_large_artefact_is_never_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec 4.2: rules.py reads only the artefacts the inventory would have read."""
    import rules

    repo = tmp_path / "repo"
    (repo / "svc").mkdir(parents=True)
    head = b"FROM alpine:3.20\n"  # a naive read yields container.no-user
    (repo / "Dockerfile").write_bytes(head + b"#" * (MAX_SCAN_BYTES + 1 - len(head)))
    (repo / "svc" / "Dockerfile").write_bytes(b"FROM alpine:3.20\n\x00RUN apk add curl\n")
    inventory, _ = build_all(repo, churn_months=240)
    containers = {str(a["path"]): a for a in inventory["artefacts"]["container"]}
    assert set(containers) == {"Dockerfile", "svc/Dockerfile"}
    assert all(a["skipped_large"] for a in containers.values())
    assert all(a["path_class"] == "source" for a in containers.values())

    seen: list[str] = []
    unpatched = rules._read

    def recording_read(root: Path, rel: str) -> str:
        seen.append(rel)
        return unpatched(root, rel)

    monkeypatch.setattr(rules, "_read", recording_read)
    findings, _leads = run_rules(repo, inventory, DEFAULTS, now=NOW)
    assert _at(findings, "pipeline-infra", "Dockerfile") is None
    assert _at(findings, "pipeline-infra", "svc/Dockerfile") is None
    assert findings == []
    assert "Dockerfile" not in seen and "svc/Dockerfile" not in seen

    monkeypatch.undo()  # the size guard inside _read itself, independent of the flag
    assert rules._read(repo, "Dockerfile") == ""


def test_iac_rules(mixed: Repo) -> None:
    findings = _run(mixed)
    deployment = _at(findings, "pipeline-infra", "k8s/deployment.yaml")
    assert _rules(deployment) == {
        "rule:iac.no-resource-limits", "rule:iac.latest-image", "rule:iac.privileged",
    }
    assert deployment is not None and deployment["severity"] == 2
    assert _at(findings, "pipeline-infra", "k8s/service.yaml") is None


def test_manifest_rules_and_migration_leads(service_py: Repo, web_ts: Repo, mixed: Repo) -> None:
    findings = _run(service_py)
    pyproject = _at(findings, "dependency-debt", "pyproject.toml")
    assert _rules(pyproject) == {"rule:manifest.no-lockfile"}
    assert pyproject is not None
    assert (pyproject["debt_type"], pyproject["type_id"]) == ("dependency", "TD-02")
    assert pyproject["evidence"][0]["quote"] == "[project]"
    assert _at(findings, "dependency-debt", "requirements.txt") is None
    assert _leads(service_py) == {
        "migration": [
            {
                "rule": "dual-manifest",
                "file": "setup.py",
                "line": 1,
                "quote": '"""Legacy packaging shim; pyproject.toml is the source of truth."""',
                "path_class": "source",
                "extra": {"pair": ["setup.py", "pyproject.toml"]},
            }
        ]
    }
    web_findings = _run(web_ts)
    assert _rules(_at(web_findings, "dependency-debt", "package.json")) == {
        "rule:manifest.two-lockfiles",
    }
    web_leads = _leads(web_ts)["migration"]
    assert [lead["file"] for lead in web_leads] == ["tslint.json"]
    assert web_leads[0]["extra"] == {"pair": ["tslint.json", ".eslintrc.json"]}
    assert _at(_run(mixed), "dependency-debt", "go.mod") is None
    assert _leads(mixed) == {"migration": []}


def test_tslint_lead_under_a_tests_tree_is_skipped_and_its_quote_redacted(
    tmp_path: Path,
) -> None:
    """The tslint lead obeys the path-class disable and redacts like its setup.py sibling."""
    secret = "abcdefghijkl0123"
    eslint = '{"root": true}\n'
    repo = tmp_path / "repo"
    (repo / "tests" / "fixtures" / "y").mkdir(parents=True)
    (repo / "tslint.json").write_text(f'{{"token": "{secret}"}}\n', encoding="utf-8")
    (repo / ".eslintrc.json").write_text(eslint, encoding="utf-8")
    fixtures = repo / "tests" / "fixtures" / "y"
    (fixtures / "tslint.json").write_text('{ "extends": "tslint:recommended" }\n', encoding="utf-8")
    (fixtures / ".eslintrc.json").write_text(eslint, encoding="utf-8")
    inventory, _ = build_all(repo, churn_months=240)
    classes = {str(a["path"]): a["path_class"] for a in inventory["artefacts"]["config"]}
    assert classes["tslint.json"] == "source"
    assert classes["tests/fixtures/y/tslint.json"] == "tests"

    _findings, leads = run_rules(repo, inventory, DEFAULTS, now=NOW)
    migration = leads["migration"]
    assert [lead["file"] for lead in migration] == ["tslint.json"]
    assert migration[0]["path_class"] == "source"
    assert migration[0]["extra"] == {"pair": ["tslint.json", ".eslintrc.json"]}
    assert secret not in json.dumps(leads)
    assert "abcd***" in migration[0]["quote"]


@pytest.mark.parametrize(
    ("fixture_name", "branch"),
    [("service_py", "hotfix/ledger-rounding"), ("web_ts", "release/1.2"), ("mixed", "staging")],
)
def test_stale_environment_branches(
    request: pytest.FixtureRequest, fixture_name: str, branch: str
) -> None:
    repo: Repo = request.getfixturevalue(fixture_name)
    release = _at(_run(repo), "pipeline-infra", None)
    assert release is not None
    assert "rule:release.stale-env-branch" in _rules(release)
    assert branch in release["evidence"][0]["quote"]
    assert release["evidence"][0]["line_start"] is None
    assert release["type_id"] == "TD-27"
    assert release["effort"] == "M"
    assert "rule:release.tag-cadence" not in _rules(release)


def test_tag_cadence_threshold_from_config(service_py: Repo) -> None:
    inventory = json.loads(json.dumps(service_py[1]))
    dates = [
        "2024-01-01T00:00:00Z", "2024-02-01T00:00:00Z", "2024-03-01T00:00:00Z",
        "2024-04-01T00:00:00Z", "2024-05-01T00:00:00Z", "2026-01-01T00:00:00Z",
    ]
    inventory["git"]["tags"] = [{"name": f"v0.{i}", "date": d} for i, d in enumerate(dates)]
    findings, _ = run_rules(service_py[0], inventory, DEFAULTS, now=NOW)
    release = _at(findings, "pipeline-infra", None)
    assert "rule:release.tag-cadence" in _rules(release)
    assert release is not None and "v0.4 to v0.5" in release["note"]
    relaxed = deep_merge(DEFAULTS, {"rules": {"release": {"gap_multiple": 30}}})
    findings, _ = run_rules(service_py[0], inventory, relaxed, now=NOW)
    assert "rule:release.tag-cadence" not in _rules(_at(findings, "pipeline-infra", None))


def test_ownership_island_and_repo_level_facts(service_py: Repo, web_ts: Repo) -> None:
    findings = _run(service_py)
    island = _at(findings, "ownership", "src/pay/refund.py")
    assert island is not None
    assert "rule:ownership.knowledge-island" in _rules(island)
    assert island["severity"] == 4  # top-5 hotspot
    assert (island["debt_type"], island["type_id"], island["effort"]) == (
        "knowledge-process", "TD-16", "M",
    )
    assert island["evidence"][0]["line_start"] is None
    assert "has left" not in island["note"]
    assert _at(findings, "ownership", "src/pay/ledger.py") is None
    repo_level = _at(findings, "ownership", None)
    assert "rule:ownership.no-codeowners" in _rules(repo_level)
    assert "rule:ownership.no-adr-no-pr-template" not in _rules(repo_level)  # ADR dir present
    assert repo_level is not None and repo_level["type_id"] == "TD-23"
    web_repo_level = _at(_run(web_ts), "ownership", None)
    assert {"rule:ownership.no-codeowners", "rule:ownership.no-adr-no-pr-template"} <= _rules(
        web_repo_level
    )
    assert web_repo_level is not None and web_repo_level["severity"] == 2


def test_ownership_suppressed_below_three_human_authors(mixed: Repo, service_py: Repo) -> None:
    assert not any(f["family"] == "ownership" for f in _run(mixed))
    strict = deep_merge(DEFAULTS, {"rules": {"ownership": {"min_human_authors": 4}}})
    assert not any(f["family"] == "ownership" for f in _run(service_py, strict))


def test_ownership_thresholds_from_config(service_py: Repo) -> None:
    for override in ({"island_share": 1.1}, {"island_max_authors": 0}):
        cfg = deep_merge(DEFAULTS, {"rules": {"ownership": override}})
        findings = _run(service_py, cfg)
        assert not any("rule:ownership.knowledge-island" in _rules(f) for f in findings)


def test_unowned_hotspot_with_codeowners(service_py: Repo, tmp_path: Path) -> None:
    repo = tmp_path / "copy"
    shutil.copytree(service_py[0], repo)
    (repo / "CODEOWNERS").write_text("src/pay/ledger.py @grace\n", encoding="utf-8")
    inventory, _ = build_all(repo, churn_months=240)
    findings, _ = run_rules(repo, inventory, DEFAULTS, now=NOW)
    unowned = _at(findings, "ownership", "CODEOWNERS")
    assert _rules(unowned) == {"rule:ownership.unowned-hotspot"}
    assert unowned is not None
    assert "src/pay/refund.py" in unowned["note"]
    assert "src/pay/ledger.py" not in unowned["note"]
    assert not any("rule:ownership.no-codeowners" in _rules(f) for f in findings)


def test_no_git_gives_only_artefact_findings(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("FROM alpine:3.20\nRUN apk add curl\n", encoding="utf-8")
    inventory, _ = build_all(tmp_path)
    findings, leads = run_rules(tmp_path, inventory, DEFAULTS, now=NOW)
    assert [f["evidence"][0]["file"] for f in findings] == ["Dockerfile"]
    assert leads == {"migration": []}


@pytest.mark.parametrize(
    ("corpus_name", "fixture_name"),
    [
        ("service-py", "service_py_repo"),
        ("web-ts", "web_ts_repo"),
        ("mixed-decoys", "mixed_decoys_repo"),
    ],
)
def test_no_corpus_decoy_reaches_tier_a(
    request: pytest.FixtureRequest, corpus_name: str, fixture_name: str
) -> None:
    """Spec success criterion 2, scored by evaluate.py over real rules.py output.

    The window comes from the fixture's own ``planted.json``: the corpus dates
    are fixed while the default 12-month window moves, so the bar only means
    anything at the window the fixture records.
    """
    repo: Path = request.getfixturevalue(fixture_name)
    planted_doc = json.loads(
        (CORPUS_ROOT / corpus_name / "planted.json").read_text(encoding="utf-8")
    )
    window = planted_doc.get("churn_months")
    assert isinstance(window, int), "planted.json must record the window it is scored under"
    inventory, _ = build_all(repo, churn_months=window)
    findings, _leads = run_rules(repo, inventory, DEFAULTS, now=NOW)
    report = evaluate(findings, planted_doc, set(), top=5)
    hit = [d["id"] for d in report["decoys"] if "A" in d["hit_tiers"]]
    assert report["decoys_in_tier_a"] == 0, f"decoys at tier A: {hit}"
    assert report["decoys_in_top_n"] == 0
    assert report["churn_months"] == window
    assert report["counts"]["reported"] > 0  # real findings were scored, not an empty list
    assert report["counts"]["on_planted"] > 0


def test_cli_writes_rule_findings(service_py: Repo, tmp_path: Path) -> None:
    from rules import _main

    workdir = tmp_path / "wd"
    write_json(workdir / "inventory.json", service_py[1])
    assert _main([str(service_py[0]), "--workdir", str(workdir)]) == 0
    raw = (workdir / "rule-findings.json").read_bytes()
    assert b"\r\n" not in raw
    document = json.loads(raw)
    assert list(document) == ["schema_version", "findings", "leads"]
    assert document["schema_version"] == 2
    assert any(f["family"] == "ownership" for f in document["findings"])
    assert document["leads"]["migration"][0]["file"] == "setup.py"


def test_cli_missing_inventory_exits_2(tmp_path: Path) -> None:
    from rules import _main

    assert _main([str(tmp_path), "--workdir", str(tmp_path / "none")]) == 2
