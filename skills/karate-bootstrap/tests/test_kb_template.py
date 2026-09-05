"""The Karate template is a real Maven project. These tests pin its shape; the
``maven``-marked test compiles and smoke-runs it (opt in with ``KB_MAVEN=1``)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "karate-tests"
NS = {"m": "http://maven.apache.org/POM/4.0.0"}

REQUIRED_FILES = [
    "pom.xml",
    "mvnw",
    "mvnw.cmd",
    ".mvn/wrapper/maven-wrapper.properties",
    ".gitignore",
    "defects.md",
    "azure-pipelines.karate.yml",
    "rules/harness-smoke.csv",
    "stubs/.gitkeep",
    "seed/.gitkeep",
    "src/test/java/kb/harness/KbRuntime.java",
    "src/test/java/kb/harness/KarateRunner.java",
    "src/test/resources/karate-config.js",
    "src/test/resources/kb-runtime.json",
    "src/test/resources/logback-test.xml",
    "src/test/resources/testcontainers.properties",
    "src/test/resources/common/mutate.js",
    "src/test/resources/features/harness-smoke.feature",
]

# Spec 5.5 pins. A change here is a spec change first.
PINNED_PROPERTIES = {
    "maven.compiler.release": "17",
    "karate.version": "1.5.2",
    "testcontainers.version": "1.21.4",
    "postgresql.version": "42.7.13",
    "qpid.version": "1.17.0",
    "nimbus.version": "9.37.3",
    "jackson.version": "2.17.2",
    "junit.version": "5.10.3",
    "logback.version": "1.5.6",
    "surefire.version": "3.2.5",
}


def test_template_files_present() -> None:
    missing = [rel for rel in REQUIRED_FILES if not (TEMPLATE / rel).is_file()]
    assert missing == []


def test_pom_pins_match_spec() -> None:
    root = ET.parse(TEMPLATE / "pom.xml").getroot()
    properties = root.find("m:properties", NS)
    assert properties is not None
    props = {child.tag.split("}")[1]: (child.text or "").strip() for child in properties}
    for name, value in PINNED_PROPERTIES.items():
        assert props.get(name) == value, name
    artifacts = {
        dep.findtext("m:artifactId", default="", namespaces=NS)
        for dep in root.iterfind("m:dependencies/m:dependency", NS)
    }
    assert {"karate-junit5", "testcontainers", "junit-jupiter", "postgresql", "qpid-jms-client",
            "nimbus-jose-jwt", "jackson-databind", "logback-classic"} <= artifacts
    assert "mockserver" not in " ".join(artifacts)
    surefire = ".//m:plugin/m:configuration/m:includes/m:include"
    includes = [i.text for i in root.iterfind(surefire, NS)]
    assert includes == ["**/*Test.java", "**/KarateRunner.java"]
    resources = ".//m:testResource/m:includes/m:include"
    assert [i.text for i in root.iterfind(resources, NS)] == ["rules/**", "stubs/**", "seed/**"]


def test_wrapper_is_pinned_only_script() -> None:
    props = (TEMPLATE / ".mvn/wrapper/maven-wrapper.properties").read_text(encoding="utf-8")
    assert "wrapperVersion=3.3.2" in props
    assert "distributionType=only-script" in props
    assert "apache-maven-3.9.9-bin.zip" in props
    assert (TEMPLATE / "mvnw").read_text(encoding="utf-8").startswith("#!/bin/sh")
    assert "@REM" in (TEMPLATE / "mvnw.cmd").read_text(encoding="utf-8")[:400]


def test_runtime_template_is_valid_v1_with_neutral_defaults() -> None:
    runtime = json.loads((TEMPLATE / "src/test/resources/kb-runtime.json").read_text("utf-8"))
    assert runtime["version"] == 1
    assert runtime["app"]["readinessPath"] is None
    assert runtime["env"] == []
    assert runtime["migrations"]["image"] is None
    assert runtime["auth"] == {"mode": "none"}


def test_java_sources_carry_no_template_tokens() -> None:
    # Java is copied verbatim (spec 5.5). "${" is string.Template's marker; the harness's own
    # "{{db.host}}" runtime tokens are substituted at container start and are allowed.
    for path in (TEMPLATE / "src/test/java").rglob("*.java"):
        assert "${" not in path.read_text(encoding="utf-8"), path


def _wrapper(module: Path) -> list[str]:
    name = "mvnw.cmd" if os.name == "nt" else "mvnw"
    return [str(module / name)]


@pytest.mark.maven
@pytest.mark.skipif(os.environ.get("KB_MAVEN") != "1",
                    reason="set KB_MAVEN=1 to compile the template with Maven (needs JDK 17+)")
def test_template_compiles_and_smoke_runs(tmp_path: Path) -> None:
    module = tmp_path / "karate-tests"
    shutil.copytree(TEMPLATE, module)
    if os.name != "nt":
        (module / "mvnw").chmod(0o755)
    proc = subprocess.run(
        [*_wrapper(module), "-B", "-q", "test", "-Dkb.skipContainers=true"],
        cwd=module, capture_output=True, text=True, shell=(os.name == "nt"),
    )
    assert proc.returncode == 0, proc.stdout[-4000:] + proc.stderr[-4000:]
    reports = module / "target" / "karate-reports"
    assert (reports / "features.harness-smoke.json").is_file()
    summary = json.loads((reports / "karate-summary-json.txt").read_text(encoding="utf-8"))
    assert summary["scenariosfailed"] == 0
    assert summary["scenariosPassed"] >= 5
    assert (module / "target" / "surefire-reports" / "TEST-kb.harness.KarateRunner.xml").is_file()
