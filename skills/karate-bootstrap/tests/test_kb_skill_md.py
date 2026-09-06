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
