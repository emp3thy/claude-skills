"""Phase 3 of karate-bootstrap: validation rules as data.

``extract`` parses declarative validators (Bean Validation, FluentValidation,
.NET data annotations, Pydantic) into candidate rows in
``rules/<slug>.candidates.csv``. A rules subagent confirms candidates, adds the
imperative branches, and appends through ``add``, which assigns sequential
``rule_id`` values, de-duplicates on (field, mutation, value) and updates the
ledger's ``rules.file`` and ``rules.count``. ``mark-scanned`` records that a
validation source has been read.

Boundary values follow one convention so the generated Scenario Outline is
predictable: too_long uses max+1, too_short uses min-1, out_of_range uses the
first excluded integer below the minimum (0 for GreaterThan(0), Positive,
DecimalMin, gt=0), invalid_format uses the literal ``!!``.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from flow_map import find_entry, load_ledger, save_ledger
from kb_common import EXIT_OK, KbError, read_text, require_file, run_cli

CSV_HEADER = (
    "rule_id",
    "field",
    "mutation",
    "value",
    "expected_status",
    "expected_code",
    "expected_message_contains",
    "source",
)
MUTATIONS = (
    "missing",
    "null",
    "empty",
    "too_long",
    "too_short",
    "invalid_format",
    "out_of_range",
    "invalid_enum",
    "cross_field",
)
INVALID_FORMAT_VALUE = "!!"


def slug_for(entry_id: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", entry_id.lower())).strip("-")


def _row(field: str, mutation: str, value: str, status: str, source: str) -> dict[str, Any]:
    return {
        "rule_id": "",
        "field": field,
        "mutation": mutation,
        "value": value,
        "expected_status": status,
        "expected_code": "",
        "expected_message_contains": "",
        "source": source,
    }


# --- Bean Validation (Spring, Quarkus) --------------------------------------

_ANNOTATION_RE = re.compile(r"@(\w+)(?:\(([^)]*)\))?")
_JAVA_FIELD_RE = re.compile(
    r"^\s*(?:private|public|protected)?\s*(?:final\s+)?[\w<>\[\],.? ]+?\s+(\w+)\s*(?:=|;)"
)
_ARG_RE = re.compile(r"(\w+)\s*=\s*(\"[^\"]*\"|[-\w.]+)")


def _args(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    named = {k: v.strip('"') for k, v in _ARG_RE.findall(raw)}
    if not named and raw.strip():
        named["value"] = raw.strip().strip('"')
    return named


def _first_int(value: str | None) -> int | None:
    if value is None:
        return None
    match = re.search(r"-?\d+", value)
    return int(match.group(0)) if match else None


def extract_bean_validation(text: str, source_rel: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    pending: list[tuple[int, str, dict[str, str]]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        annotations = list(_ANNOTATION_RE.finditer(line))
        field_match = _JAVA_FIELD_RE.match(_ANNOTATION_RE.sub("", line))
        if annotations and not field_match:
            for match in annotations:
                pending.append((number, match.group(1), _args(match.group(2))))
            continue
        if not field_match:
            pending = []
            continue
        for match in annotations:
            pending.append((number, match.group(1), _args(match.group(2))))
        field = field_match.group(1)
        for ann_line, name, args in pending:
            src = f"{source_rel}:{ann_line}"
            if name in ("NotNull", "NotBlank", "NotEmpty"):
                rows.append(_row(field, "missing", "", "400", src))
                if name in ("NotBlank", "NotEmpty"):
                    rows.append(_row(field, "empty", "", "400", src))
            elif name == "Size":
                mx, mn = _first_int(args.get("max")), _first_int(args.get("min"))
                if mx is not None:
                    rows.append(_row(field, "too_long", str(mx + 1), "400", src))
                if mn is not None and mn > 0:
                    rows.append(_row(field, "too_short", str(mn - 1), "400", src))
            elif name in ("Min", "DecimalMin", "Positive", "PositiveOrZero"):
                mn = (
                    _first_int(args.get("value"))
                    if name in ("Min", "DecimalMin")
                    else (0 if name == "Positive" else -1)
                )
                below = (
                    (mn - 1)
                    if name == "Min" and mn is not None
                    else (0 if name in ("DecimalMin", "Positive") else -1)
                )
                rows.append(_row(field, "out_of_range", str(below), "400", src))
            elif name in ("Max", "DecimalMax"):
                mx = _first_int(args.get("value"))
                if mx is not None:
                    rows.append(_row(field, "out_of_range", str(mx + 1), "400", src))
            elif name in ("Pattern", "Email"):
                rows.append(_row(field, "invalid_format", INVALID_FORMAT_VALUE, "400", src))
        pending = []
    return rows


# --- FluentValidation (.NET) -------------------------------------------------

_RULEFOR_RE = re.compile(
    r"RuleFor\s*\(\s*\w+\s*=>\s*\w+\.(\w+)\s*\)((?:\s*\.\w+\([^)]*\))+)"
)
_CHAIN_RE = re.compile(r"\.(\w+)\(([^)]*)\)")


def _ends_statement(line: str) -> bool:
    """True when ``line`` holds a ``;`` outside every double-quoted string literal."""
    in_string = False
    escaped = False
    for char in line:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == ";":
            return True
    return False


def _fluent_statements(text: str) -> list[tuple[int, str]]:
    """Join each ``RuleFor(...)`` statement onto one line, keyed by its first line.

    FluentValidation chains are routinely wrapped across lines, one call per
    line, so the regexes have to see the whole statement at once.
    """
    statements: list[tuple[int, str]] = []
    start: int | None = None
    parts: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if start is None:
            if "RuleFor" not in line:
                continue
            start = number
        parts.append(line.strip())
        if _ends_statement(line):
            statements.append((start, " ".join(parts)))
            start, parts = None, []
    if start is not None:
        statements.append((start, " ".join(parts)))
    return statements


def extract_fluent_validation(text: str, source_rel: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, statement in _fluent_statements(text):
        for match in _RULEFOR_RE.finditer(statement):
            field, chain = match.group(1), match.group(2)
            src = f"{source_rel}:{number}"
            for call, raw in _CHAIN_RE.findall(chain):
                arg = _first_int(raw)
                if call in ("NotEmpty", "NotNull"):
                    rows.append(_row(field, "missing", "", "400", src))
                    if call == "NotEmpty":
                        rows.append(_row(field, "empty", "", "400", src))
                elif call == "MaximumLength" and arg is not None:
                    rows.append(_row(field, "too_long", str(arg + 1), "400", src))
                elif call == "MinimumLength" and arg is not None and arg > 0:
                    rows.append(_row(field, "too_short", str(arg - 1), "400", src))
                elif call == "Length":
                    parts = [int(p) for p in re.findall(r"-?\d+", raw)]
                    if len(parts) == 2:
                        if parts[0] > 0:
                            rows.append(_row(field, "too_short", str(parts[0] - 1), "400", src))
                        rows.append(_row(field, "too_long", str(parts[1] + 1), "400", src))
                elif call in ("GreaterThan", "GreaterThanOrEqualTo") and arg is not None:
                    below = arg if call == "GreaterThan" else arg - 1
                    rows.append(_row(field, "out_of_range", str(below), "400", src))
                elif call in ("LessThan", "LessThanOrEqualTo") and arg is not None:
                    above = arg if call == "LessThan" else arg + 1
                    rows.append(_row(field, "out_of_range", str(above), "400", src))
                elif call in ("InclusiveBetween", "ExclusiveBetween"):
                    parts = [int(p) for p in re.findall(r"-?\d+", raw)]
                    if len(parts) == 2:
                        rows.append(_row(field, "out_of_range", str(parts[0] - 1), "400", src))
                elif call in ("Matches", "EmailAddress"):
                    rows.append(_row(field, "invalid_format", INVALID_FORMAT_VALUE, "400", src))
                elif call == "IsInEnum":
                    rows.append(_row(field, "invalid_enum", "NOT_A_VALUE", "400", src))
    return rows


# --- .NET data annotations ---------------------------------------------------

_CS_ATTR_RE = re.compile(r"(?<![\w)\]])\[(\w+)(?:\(([^)]*)\))?\]")
_CS_PROP_RE = re.compile(r"^\s*public\s+[\w<>\[\]?]+\s+(\w+)\s*\{")


def extract_data_annotations(text: str, source_rel: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    pending: list[tuple[int, str, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        attributes = list(_CS_ATTR_RE.finditer(line))
        prop = _CS_PROP_RE.match(_CS_ATTR_RE.sub("", line))
        if attributes and not prop:
            for attr in attributes:
                pending.append((number, attr.group(1), attr.group(2) or ""))
            continue
        if not prop:
            pending = []
            continue
        for attr in attributes:
            pending.append((number, attr.group(1), attr.group(2) or ""))
        field = prop.group(1)
        for attr_line, name, raw in pending:
            src = f"{source_rel}:{attr_line}"
            numbers = [int(n) for n in re.findall(r"-?\d+", raw)]
            named = _args(raw)
            if name == "Required":
                rows.append(_row(field, "missing", "", "400", src))
            elif name == "StringLength" and numbers:
                rows.append(_row(field, "too_long", str(numbers[0] + 1), "400", src))
                mn = _first_int(named.get("MinimumLength"))
                if mn is not None and mn > 0:
                    rows.append(_row(field, "too_short", str(mn - 1), "400", src))
            elif name == "MaxLength" and numbers:
                rows.append(_row(field, "too_long", str(numbers[0] + 1), "400", src))
            elif name == "MinLength" and numbers and numbers[0] > 0:
                rows.append(_row(field, "too_short", str(numbers[0] - 1), "400", src))
            elif name == "Range" and len(numbers) >= 1:
                rows.append(_row(field, "out_of_range", str(numbers[0] - 1), "400", src))
            elif name in ("RegularExpression", "EmailAddress", "Url", "Phone"):
                rows.append(_row(field, "invalid_format", INVALID_FORMAT_VALUE, "400", src))
        pending = []
    return rows


# --- Pydantic -----------------------------------------------------------------

_PY_CLASS_RE = re.compile(r"^class\s+(\w+)\s*\(([^)]*)\)\s*:")
_PY_FIELD_RE = re.compile(r"^\s{4}(\w+)\s*:\s*([^=]+?)(?:\s*=\s*(.+))?$")
_PY_KW_RE = re.compile(r"(\w+)\s*=\s*(r?\"[^\"]*\"|r?'[^']*'|[-\w.]+)")


def extract_pydantic(text: str, source_rel: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    in_model = False
    for number, line in enumerate(text.splitlines(), start=1):
        klass = _PY_CLASS_RE.match(line)
        if klass:
            bases = klass.group(2)
            in_model = "BaseModel" in bases and not klass.group(1).endswith(("Out", "Response"))
            continue
        if not in_model:
            continue
        field_match = _PY_FIELD_RE.match(line)
        if not field_match:
            continue
        field = field_match.group(1)
        annotation = field_match.group(2)
        default = field_match.group(3)
        src = f"{source_rel}:{number}"
        kwargs = dict(_PY_KW_RE.findall(default or ""))
        required = default is None or (
            default.startswith("Field(") and "..." in default.split(",")[0]
        )
        if required and "None" not in annotation:
            rows.append(_row(field, "missing", "", "422", src))
        mx, mn = _first_int(kwargs.get("max_length")), _first_int(kwargs.get("min_length"))
        if mx is not None:
            rows.append(_row(field, "too_long", str(mx + 1), "422", src))
        if mn is not None and mn > 0:
            rows.append(_row(field, "too_short", str(mn - 1), "422", src))
        gt, ge = _first_int(kwargs.get("gt")), _first_int(kwargs.get("ge"))
        if gt is not None:
            rows.append(_row(field, "out_of_range", str(gt), "422", src))
        elif ge is not None:
            rows.append(_row(field, "out_of_range", str(ge - 1), "422", src))
        lt, le = _first_int(kwargs.get("lt")), _first_int(kwargs.get("le"))
        if lt is not None:
            rows.append(_row(field, "out_of_range", str(lt), "422", src))
        elif le is not None and gt is None and ge is None:
            rows.append(_row(field, "out_of_range", str(le + 1), "422", src))
        if "pattern" in kwargs or "regex" in kwargs or "EmailStr" in annotation:
            rows.append(_row(field, "invalid_format", INVALID_FORMAT_VALUE, "422", src))
    return rows


# --- orchestration ------------------------------------------------------------

_EXTRACTORS: dict[str, tuple[Callable[[str, str], list[dict[str, Any]]], ...]] = {
    "spring": (extract_bean_validation,),
    "quarkus": (extract_bean_validation,),
    "aspnetcore": (extract_fluent_validation, extract_data_annotations),
    "python": (extract_pydantic,),
}


def extract_for_entry(root: Path, stack: str, entry: dict[str, Any]) -> list[dict[str, Any]]:
    sources = [s["file"] for s in entry.get("rules", {}).get("sources", [])]
    schema_ref = (entry.get("request") or {}).get("schema_ref")
    if schema_ref and schema_ref not in sources:
        sources.append(schema_ref)
    rows: list[dict[str, Any]] = []
    for source_rel in sources:
        path = root / source_rel
        if not path.is_file():
            continue
        text = read_text(path)
        for extractor in _EXTRACTORS.get(stack, ()):
            rows.extend(extractor(text, source_rel))
    return rows


def _rules_dir(out_dir: Path) -> Path:
    path = out_dir / "rules"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_HEADER)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != CSV_HEADER:
            raise KbError(f"{path}: CSV header must be exactly {','.join(CSV_HEADER)}")
        rows = list(reader)
    for row in rows:
        if row["mutation"] not in MUTATIONS:
            raise KbError(
                f"{path}: unknown mutation {row['mutation']!r}; expected one of {MUTATIONS}"
            )
        if not row["expected_status"].isdigit():
            raise KbError(
                f"{path}: expected_status must be an integer, got {row['expected_status']!r}"
            )
    return rows


def write_candidates(out_dir: Path, entry: dict[str, Any], rows: list[dict[str, Any]]) -> Path:
    path = _rules_dir(out_dir) / f"{slug_for(entry['id'])}.candidates.csv"
    _write_csv(path, rows)
    return path


def add_rows(out_dir: Path, ledger: dict[str, Any], entry_id: str, rows_csv: Path) -> int:
    entry = find_entry(ledger, entry_id)
    incoming = _read_csv(require_file(rows_csv, "rows CSV"))
    target = _rules_dir(out_dir) / f"{slug_for(entry_id)}.csv"
    existing = _read_csv(target) if target.is_file() else []
    seen = {(r["field"], r["mutation"], r["value"]) for r in existing}
    for row in incoming:
        key = (row["field"], row["mutation"], row["value"])
        if key in seen:
            continue
        seen.add(key)
        existing.append(row)
    for index, row in enumerate(existing, start=1):
        row["rule_id"] = f"R{index:03d}"
    _write_csv(target, existing)
    rules = entry.setdefault("rules", {"file": None, "count": 0, "sources": []})
    rules["file"] = f"rules/{target.name}"
    rules["count"] = len(existing)
    return len(existing)


def mark_scanned(ledger: dict[str, Any], entry_id: str, source_rel: str) -> None:
    rules = find_entry(ledger, entry_id).setdefault(
        "rules", {"file": None, "count": 0, "sources": []}
    )
    for source in rules["sources"]:
        if source["file"] == source_rel:
            source["scanned"] = True
            return
    rules["sources"].append({"file": source_rel, "scanned": True})


def _cmd_extract(args: argparse.Namespace) -> int:
    root = args.repo / args.service_dir if args.service_dir else args.repo
    ledger = load_ledger(args.ledger)
    stack = str(ledger["stack"]["framework"])
    for entry in ledger["entry_points"]:
        if not any(r.get("rules") for r in entry.get("responses", [])):
            continue
        rows = extract_for_entry(root, stack, entry)
        path = write_candidates(args.out_dir, entry, rows)
        print(f"{entry['id']}: {len(rows)} candidate rows -> {path}")
    return EXIT_OK


def _cmd_add(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    count = add_rows(args.out_dir, ledger, args.entry_id, args.rows_csv)
    save_ledger(args.ledger, ledger)
    print(f"{args.entry_id}: {count} rules")
    return EXIT_OK


def _cmd_mark_scanned(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    mark_scanned(ledger, args.entry_id, args.source)
    save_ledger(args.ledger, ledger)
    print(f"{args.entry_id}: scanned {args.source}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validation rules as CSV data")
    sub = parser.add_subparsers(dest="command", required=True)

    extract = sub.add_parser("extract", help="Write candidate rows from declarative validators")
    extract.add_argument("repo", type=Path)
    extract.add_argument("--service-dir", default=None)
    extract.add_argument("--ledger", type=Path, required=True)
    extract.add_argument("--out-dir", type=Path, required=True, help="karate-tests directory")
    extract.set_defaults(func=_cmd_extract)

    add = sub.add_parser("add", help="Append confirmed rows to rules/<slug>.csv")
    add.add_argument("entry_id")
    add.add_argument("rows_csv", type=Path)
    add.add_argument("--ledger", type=Path, required=True)
    add.add_argument("--out-dir", type=Path, required=True)
    add.set_defaults(func=_cmd_add)

    scanned = sub.add_parser("mark-scanned", help="Record that a validation source was read")
    scanned.add_argument("entry_id")
    scanned.add_argument("source")
    scanned.add_argument("--ledger", type=Path, required=True)
    scanned.set_defaults(func=_cmd_mark_scanned)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(run_cli(main))
