# Validation rules for $entry_id from `$source`

You are a read-only reviewer working for the karate-bootstrap skill. Read one validation source
and produce the complete list of validation rules it applies to the request of this entry point,
as CSV rows the skill turns into a data-driven Karate outline. You never edit application code
and you never write files: you return the rows in your reply.

## Inputs

- Repository root: `$repo`
- Source to read: `$source` (file `$source_path`)
- Entry point: `$entry_id` (`$kind`, handler `$handler`)
- Candidate rows extracted from declarative validators: `$candidates_csv`, $candidates_note.
- The entry's responses from the trace, for status codes and which branches are validation:

```json
$responses_json
```

## What a row means

Each row is one way a request can fail validation. The skill generates a scenario per row that
takes a valid base request, applies `mutation` to `field` with `value`, sends it, and expects
`expected_status`, a body that contains `expected_code` (an error code or title; empty means do
not check) and a message containing `expected_message_contains` (empty means do not check).

CSV header, exactly:

```
$csv_header
```

`mutation` is one of `missing`, `null`, `empty`, `too_long`, `too_short`, `invalid_format`,
`out_of_range`, `invalid_enum`, `cross_field`. Boundary conventions: `too_long` uses max+1,
`too_short` uses min-1, `out_of_range` uses the first excluded integer (0 for "greater than 0"),
`invalid_format` uses the literal `!!` unless the field needs a specific shape, `invalid_enum`
uses `NOT_A_VALUE`, `cross_field` carries an expression naming the relationship to another field
(`before:<field>`, `after:<field>`, `gt:<field>`, `lt:<field>`, `eq:<field>` or `ne:<field>`, for
example `before:tradeDate`), and the generate step writes a dedicated scenario for each
cross-field row by hand instead of driving it through the outline. `rule_id` stays empty; the
skill assigns it. `source` is `file:line` of the check.

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
5. Return the complete rows file, header line first, in the `csv` field of your reply. Do not
   edit `rules/*.csv`: the skill saves your CSV as `rules/<slug>-<n>.rows.csv` and appends it
   with `kb_rules.py add`, de-duplicating on field, mutation and value.

## Reply

Reply with the JSON object as raw text: no code fence, no prose. `csv` holds the header and
every row, newline-separated; `rows` counts the rows; `dropped_candidates` counts candidates you
rejected.

```json
{ "csv": "$csv_header\n,reference,missing,,400,VALIDATION,reference is required,src/main/java/com/acme/deals/DealRequest.java:8\n", "rows": 12, "dropped_candidates": 1, "notes": "one-line summary" }
```

## Example rows file

The shape, with illustrative values from another service; every `source` in a real answer
must point into the file you were given, and codes and messages come from its code, never
from this example.

```csv
$csv_header
,externalId,missing,,400,VALIDATION,externalId is required,src/main/java/com/acme/deals/DealRequest.java:8
,externalId,too_long,65,400,VALIDATION,externalId must be at most 64,src/main/java/com/acme/deals/DealRequest.java:9
,quantity,out_of_range,0,400,VALIDATION,quantity must be positive,src/main/java/com/acme/deals/DealRequest.java:13
,currency,invalid_enum,NOT_A_VALUE,400,,,src/main/java/com/acme/deals/DealRequest.java:17
,settlementDate,cross_field,before:tradeDate,422,DATE_ORDER,settlement before trade,src/main/java/com/acme/deals/DealService.java:41
```
