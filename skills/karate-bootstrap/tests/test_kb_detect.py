from __future__ import annotations

import json
from pathlib import Path

import pytest
from detect import detect, find_build_files, main
from kb_common import EXIT_TOOLCHAIN, EXIT_UNSUPPORTED_STACK, KbError

FIXTURES = Path(__file__).parent / "fixtures"


def test_spring_mini() -> None:
    result = detect(FIXTURES / "spring-mini")
    assert result["framework"] == "spring"
    assert result["language"] == "java"
    assert result["build"] == "maven"
    assert result["orm"] == "hibernate-jpa"
    assert result["db"] == "postgres"
    assert result["messaging"] == "artemis-jms"
    assert result["http_client"] == "resttemplate"
    assert result["validation"] == "bean-validation"
    assert result["auth"] == "spring-security"
    assert result["build_files"] == ["pom.xml"]


def test_quarkus_mini() -> None:
    result = detect(FIXTURES / "quarkus-mini")
    assert result["framework"] == "quarkus"
    assert result["orm"] == "panache"
    assert result["db"] == "postgres"
    assert result["messaging"] == "smallrye-amqp"
    assert result["http_client"] == "quarkus-rest-client"
    assert result["validation"] == "bean-validation"
    assert result["auth"] == "quarkus-oidc"


def test_dotnet_mini() -> None:
    result = detect(FIXTURES / "dotnet-mini")
    assert result["framework"] == "aspnetcore"
    assert result["language"] == "csharp"
    assert result["build"] == "dotnet"
    assert result["orm"] == "efcore"
    assert result["db"] == "postgres"
    assert result["messaging"] == "nms-amqp"
    assert result["http_client"] == "httpclient"
    assert result["validation"] == "fluentvalidation"
    assert result["auth"] == "jwt-bearer"
    assert result["build_files"] == ["Deals.Api.csproj"]


def test_fastapi_mini() -> None:
    result = detect(FIXTURES / "fastapi-mini")
    assert result["framework"] == "python"
    assert result["language"] == "python"
    assert result["build"] == "pip"
    assert result["orm"] == "sqlalchemy"
    assert result["db"] == "postgres"
    assert result["messaging"] == "qpid-proton"
    assert result["http_client"] == "httpx"
    assert result["validation"] == "pydantic"
    assert result["auth"] == "pyjwt"


def test_unsupported_repo_raises(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module example.com/x\n", encoding="utf-8")
    with pytest.raises(KbError) as excinfo:
        detect(tmp_path)
    assert excinfo.value.exit_code == EXIT_UNSUPPORTED_STACK


def test_java_without_spring_or_quarkus_is_unsupported(tmp_path: Path) -> None:
    text = "<project><artifactId>lib</artifactId></project>"
    (tmp_path / "pom.xml").write_text(text, encoding="utf-8")
    with pytest.raises(KbError) as excinfo:
        detect(tmp_path)
    assert excinfo.value.exit_code == EXIT_UNSUPPORTED_STACK


def test_find_build_files_skips_ignored_and_deep_dirs(tmp_path: Path) -> None:
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    (tmp_path / "target").mkdir()
    (tmp_path / "target" / "pom.xml").write_text("<project/>", encoding="utf-8")
    deep = tmp_path / "a" / "b" / "c" / "d"
    deep.mkdir(parents=True)
    (deep / "pom.xml").write_text("<project/>", encoding="utf-8")
    assert [p.name for p in find_build_files(tmp_path)] == ["pom.xml"]


def test_cli_writes_stack_json_with_service_dir(tmp_path: Path) -> None:
    out = tmp_path / "karate-tests" / "stack.json"
    code = main(
        [str(FIXTURES), "--service-dir", "dotnet-mini", "--out", str(out), "--skip-toolchain"]
    )
    assert code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["framework"] == "aspnetcore"
    assert data["service_dir"] == "dotnet-mini"
    assert data["toolchain"] == {"skipped": True}


def test_cli_toolchain_missing_exits_7(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import detect as detect_module

    monkeypatch.setattr(detect_module.shutil, "which", lambda _name: None)  # type: ignore[attr-defined]
    out = tmp_path / "stack.json"
    with pytest.raises(KbError) as excinfo:
        main([str(FIXTURES / "spring-mini"), "--out", str(out)])
    assert excinfo.value.exit_code == EXIT_TOOLCHAIN


def test_hibernate_validator_alone_is_not_an_orm(tmp_path: Path) -> None:
    (tmp_path / "pom.xml").write_text(
        "<project><dependencies>"
        "<dependency><groupId>io.quarkus</groupId>"
        "<artifactId>quarkus-resteasy-reactive</artifactId></dependency>"
        "<dependency><groupId>io.quarkus</groupId>"
        "<artifactId>quarkus-hibernate-validator</artifactId></dependency>"
        "</dependencies></project>",
        encoding="utf-8",
    )
    result = detect(tmp_path)
    assert result["framework"] == "quarkus"
    assert result["orm"] is None
    assert result["validation"] == "bean-validation"
