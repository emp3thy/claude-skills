# Validation: approximate fan-in, approximate cycles, regex leads, and script time

Empirical check of the riskiest deterministic heuristics in [06-design-brainstorm.md](06-design-brainstorm.md): the stem-reference graph of section 4.2, the lead table of section 4.3, concern 3 of section 6, and the 75 percent row of section 7. Everything was measured on real repositories with throwaway scripts. Variants added after the first run to explain a result are labelled as such.

## Verdicts

| Design assumption | Verdict | Headline |
|---|---|---|
| Approximate fan-in as designed (stem anywhere in the file, 10-word stoplist) is usable in ranking | REFUTED as designed, CONFIRMED with two changes | As designed: edge precision 0.14 to 0.18, Spearman 0.58 to 0.67, top-10 overlap 4 to 5 of 10, ranking term F off by more than 0.25 for 16 to 18 percent of files. Stems matched only in import-like lines plus duplicated stems marked ambiguous: precision 0.90 to 0.98, recall 1.0, Spearman 0.985 to 1.0. |
| Approximate SCCs of size 2 to 5 are usable as cycle leads | REFUTED as designed, PARTIAL after the fixes | As designed: 3 approximate cycles, 0 real, 0 of 7 true cycles found. After the fixes: 1 emitted, real, 1 of 7 found. |
| Regex leads have adequate precision as leads | PARTIAL | Exception swallowing: 7 of 15 sampled hits are clear leads, 12 of 15 counting annotated deliberate swallows. Commented-out code: 0 of 33. Credentials: 0 of 9, all test fixtures or `$VAR` placeholders. Bare `except:` and empty `catch {}` not assessable (0 and 1 hits). |
| Deterministic stages finish under two minutes on 5,000 files | CONFIRMED for the stem graph and the regex pass | 4.6 s for tokenise, graph and Tarjan at 5,000 files; 3.6 s extrapolated for the regex pass. Git pass and blame not measured. |
| Minimum stem length 4 | CONFIRMED | Lengths 5 and 6 change precision by under 0.01 and remove eligible files. |

## Method

**Repositories.** `ralph` (219 Python files after exclusions), `better-memory` (240), `FusionHelper` (333). `weatherToBattery` was the listed third target but its 555-file count is a virtual environment named `.venv-fix`; the project has 32 files, so FusionHelper was substituted as the brief allowed and weatherToBattery kept as a small fourth sample. Exclusions: the v1 `DEFAULT_IGNORE` list plus `site`, `graphify-out`, and every dot-directory. The last rule matters: ralph carries a full copy of itself under `.worktrees/loop-split` (172 files) and 103 queue files under `.ralph-work`.

**Ground truth.** Every file is parsed with `ast`; `import a.b`, `from a.b import c` and relative imports are resolved to in-repo files. The resolver registers each file under every dotted name it would have if any ancestor directory were on `sys.path` (`a/b/c.py` as `a.b.c`, `b.c`, `c`; `a/b/__init__.py` as `a.b`, `b`), takes the longest resolving prefix, and breaks ties between same-named files by preferring the importer's directory, then the longest shared ancestor. `from a.b import c` tries `a.b.c` as a submodule before `a.b`. Limits: implicit edges to parent-package `__init__.py` files are not added; `from pkg import Name` resolves to `pkg/__init__.py`, not the defining module; dynamic imports are not followed (5 occurrences in total); entry points, `python scripts/x.py` calls and pytest discovery create no edges, so true fan-in 0 does not mean dead. Parse errors: 0. Unresolved external imports: 1,109, 1,210, 671 and 84.

**Approximation as designed.** Each file is tokenised with `[A-Za-z_][A-Za-z0-9_]*`. B references A when A's stem (4 or more characters, not in the stoplist `utils config index main types common base core helpers models`) is in B's set. Stoplist files are ambiguous and excluded as targets. Variants: minimum stem length 5 and 6; stem must appear in an import-like line (starting with `from`, `import`, `using`, `use`, `require`, `include`, `package`, or containing `require(` or `import(`, with parenthesised continuation lines included); stems shared by two or more files marked ambiguous; and, added after the first run, package files (`__init__`, `index`, `mod`, `lib`) taking the parent directory name as stem, and a hand-extended stoplist.

**Metrics.** Edge precision and recall against import edges, counting edges whose target is eligible; Spearman correlation of approximate and true fan-in over eligible files; files with approximate fan-in 0 and true fan-in above 0 (the dangerous direction for dead-code corroboration) and the reverse; mean absolute error of the design's F = fan_in / repo max, and the count of files with F error above 0.25; top-10 overlap by fan-in; Tarjan SCCs of size 2 to 5 on both graphs, an approximate cycle counting as real when its members are strongly connected in the true graph.

**Regex leads.** Implemented as 4.3 describes: bare `except:`; a broad except whose block is one statement that is `pass`, `return`, `return None`, or a call on `log`, `logger`, `logging`, `LOG` or `warnings.warn`; `catch {}` and `catch (e) {}` in non-Python source; three or more consecutive comment lines each ending in `;`, `{` or `)` or containing `=`; and `(password|secret|token|api_key)\s*=\s*["'][^"']{8,}` case-insensitively over source, CI and config extensions. Up to 15 hits per rule were sampled with a fixed seed and judged as true lead, deliberate and annotated, false positive, or test context; for the two rules with poor samples every hit was then read.

**Timing.** Stages were timed per repository, then on a synthetic corpus of 5,000 files made by replicating the 824 real files with 5,000 distinct stems, each injected into 200 files so edge density resembles the as-designed graph. The regex pass was timed over 853 real files and extrapolated linearly.

## Results: fan-in (F1)

P and R are edge precision and recall, rho is Spearman, "F>0.25" counts eligible files whose ranking term is wrong by more than 0.25, "top10" is the overlap of the ten highest fan-in files.

| Repository | Variant | Eligible | Ambiguous | True edges | Approx edges | P | R | rho | F MAE | F>0.25 | top10 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ralph | as designed | 212 | 7 | 383 | 1,937 | 0.17 | 0.87 | 0.58 | 0.093 | 34 | 4 |
| ralph | import lines | 212 | 7 | 383 | 427 | 0.78 | 0.86 | 0.89 | 0.035 | 8 | 6 |
| ralph | import lines + duplicate stems ambiguous | 178 | 41 | 287 | 292 | 0.98 | 1.00 | 0.985 | 0.001 | 0 | 10 |
| better-memory | as designed | 237 | 3 | 561 | 2,857 | 0.18 | 0.92 | 0.67 | 0.090 | 42 | 4 |
| better-memory | import lines | 237 | 3 | 561 | 564 | 0.85 | 0.86 | 0.84 | 0.009 | 0 | 7 |
| better-memory | import lines + duplicate stems ambiguous | 188 | 52 | 439 | 447 | 0.98 | 1.00 | 1.00 | 0.001 | 0 | 10 |
| FusionHelper | as designed | 331 | 2 | 473 | 3,114 | 0.14 | 0.90 | 0.62 | 0.037 | 21 | 5 |
| FusionHelper | import lines | 331 | 2 | 473 | 483 | 0.88 | 0.89 | 0.78 | 0.002 | 0 | 8 |
| FusionHelper | import lines + duplicate stems ambiguous | 294 | 39 | 414 | 459 | 0.90 | 1.00 | 0.999 | 0.001 | 0 | 8 |

weatherToBattery (30 eligible files) goes from precision 0.61 and Spearman 0.80 as designed to 1.0 and 1.0 under import lines. Minimum stem length 5 matches length 4 to two decimals everywhere. Length 6 gives precision 0.18, 0.18 and 0.14 (a gain under 0.01) and marks 9 to 19 real modules ambiguous.

**Dead-code corroboration failure modes.** Files with approximate fan-in 0 but true fan-in above 0: 0 in every repository as designed, and 0 under import lines plus duplicate-stem ambiguity. Under import lines alone the count is 6, 11, 8 and 0, every one an `__init__.py`. No ordinary module was ever reported unreferenced while imported, provided parenthesised continuation lines are captured: with single-line capture FusionHelper reports 8 ordinary modules unreferenced (non-package recall 0.976). The reverse direction is large as designed: 62 of 151, 61 of 163 and 80 of 279 unimported files acquire phantom references, so the as-designed graph hides 30 to 41 percent of import-dead files. After the fixes: 2, 0, 0 and 0.

**Over-counted stems** (false-positive edges per target stem, as designed):

- ralph: `__init__` 549, `state` 82, `status` 81, `conftest` 80, `check` 80, `target` 51, `attempts` 46, `skills` 45, `events` 44, `iteration` 36.
- better-memory: `__init__` 1,043, `agentcore` 119, `reflections` 83, `session` 77, `sqlite` 65, `observations` 59, `conftest` 58, `semantic` 56.
- FusionHelper: `__init__` 1,285, `geometry` 158, `profile` 108, `params` 105, `surface` 83, `fh_verify` 80, `holes` 76, `solid` 66.

`__init__` alone is 28 to 41 percent of all approximate edges: every file with a `def __init__` "references" every package. The rest is repository vocabulary no fixed list can anticipate. Under the import-line restriction the residual over-counts are `conftest` (72 and 48; five files share the stem), `events` 19, `agentcore` 13, `geometry` 21 and `bundlekit` 15, all duplicate-stem collisions. The hand-extended stoplist (adding `client`, `engine`, `schema`, `app` and 25 others) was harmful on the small repository: it removed weatherToBattery's real modules and dropped its correlation to 0.46.

**Duplicate and package stems.** 37 of 219 ralph files share a stem (`__init__` 24, `conftest` 4), 49 of 240 in better-memory, 37 of 333 in FusionHelper; marking them ambiguous costs 12 to 22 percent of files their fan-in, almost all package inits and test harness files. Mapping `__init__` to its directory name instead restores recall on package files but inflates the repository maximum (`ralph_executor/__init__.py` 125 against a true 27, `better_memory/__init__.py` 170 against 80), because every import line naming a submodule also names the package, and that compresses F for every other file (ralph F MAE 0.048, 12 files off by more than 0.25). Package files should be ambiguous, not mapped.

**Cycles.** True SCCs of size 2 to 5: ralph 2 (`config`/`user_config`; `sweep/__init__` with four sweep modules), better-memory 3 (`_diag`/`config`; `services/__init__`/`observation`; `cli/__init__`/`cli/main`), FusionHelper 2 (`lint/__init__` with `rules/__init__` and `r9_no_catch`; `preflight/__init__`/`staging`). Five of seven run through a package `__init__.py` re-export and two through the stoplisted `config.py`.

| Variant | Approx cycles (3 repos) | Real | True cycles found |
|---|---|---|---|
| as designed | 3 | 0 | 0 of 7 |
| import lines | 2 | 1 | 1 of 7 (as a 2-member subset) |
| import lines + duplicate stems ambiguous | 1 | 1 | 1 of 7 |

The three as-designed cycles are `subprocess_utils` with `test_subprocess_encoding_audit`, `e2e_mutation_smoke` with `M4_seeded_breach`, and `conftest` with `scratch`. In each, one file's docstring names the other in prose. The better-memory import-line cycle (`handlers/knowledge` with `serializers`) is a duplicate-stem collision with `services/knowledge.py`.

## Results: regex leads (F2)

| Rule | ralph | better-memory | FusionHelper | weatherToBattery | Total | In tests |
|---|---|---|---|---|---|---|
| bare `except:` | 0 | 0 | 0 | 0 | 0 | 0 |
| swallow: broad except with `pass`, `return None` or bare log (441 broad excepts in total) | 12 | 41 | 39 | 2 | 94 | 5 |
| `catch {}` or `catch (e) {}` | 0 | 1 | 0 | 0 | 1 | 0 |
| commented-out code | 3 | 2 | 21 | 7 | 33 | 8 |
| credential-shaped assignment | 9 | 0 | 0 | 0 | 9 | 7 |

Three repositories enable ruff's `E` set, so bare `except:` (E722) is lint-blocked and cannot be assessed. The one `catch(e){}` hit is inside `htmx.min.js`, which the design's `generated` class excludes.

**Exception swallowing.** Sample of 15, all source class: 7 true leads (four `except Exception: pass` blocks in `fh_verify.py` returning partial results, three `except BaseException: pass` blocks around JSON parsing and file cleanup); 5 deliberate and annotated (`# noqa: BLE001` with a comment such as "exposures must never block retrieve", or a best-effort `return None`); 3 false positives, all `except Exception: log.warning(..., exc_info=True)` or `log.warning("... %s", exc)` followed by a fallback path. Precision 0.47 strict, 0.80 counting annotated swallows as leads a scout should still see. Across all 94 hits: 70 `pass`, 10 `return`, 14 log calls, of which 9 carry the exception (`exc_info`, `.exception(` or the `as` name) and 5 drop it. 38 of 94 carry a trailing comment or `noqa` on the except line; 28 catch `BaseException`.

**Commented-out code.** Sample of 15: 0 true. All 33 hits were then read: 0 are code. Shapes: worked arithmetic in comments (`(40 - 32) / 2 = 4.0 mm`, 16 hits in FusionHelper part files), field-mapping tables (`ppv = solar generation (kW)`), prose with `=` inside backticks, numbered lists whose items end in `)`, and test comments walking through expected values. Stripping the markers and calling `ast.parse` on each run fails for all 33; a "majority of lines look like a statement" rule keeps 5, all still prose. The repositories do not enable ruff `ERA001`, so the absence of real commented-out code is genuine.

**Credentials.** 9 hits: 7 in tests (`anthropic_api_key="fake-key"`, `TOKEN = "ghp_fake_token_value"`), 2 in a commented `kubectl` example in a secrets template with `$GH_TOKEN` placeholders. Under the design's scope the test hits vanish and the 2 remaining are false. No real secret exists in these repositories, so recall is unmeasurable.

## Results: time (F3)

| Stage | FusionHelper (333 files) | Synthetic 5,000 files, 65 MB |
|---|---|---|
| tokenise | 0.33 s | 2.27 s |
| stem graph, N-squared membership loop | 0.010 s | 1.92 s |
| stem graph, inverted stem index | | 0.55 s |
| Tarjan | 0.001 s | 0.41 s |
| regex lead pass | | 3.6 s (from 0.62 s over 853 files) |

Total for the stem graph at 5,000 files: 4.6 s naive, 3.2 s with the inverted index. The under-two-minute claim holds for these stages by more than twenty times. The git pass, blame and tool probes were outside this experiment.

## Failure-mode analysis

1. **The stoplist is the wrong instrument.** The over-counted stems are `__init__` and repository vocabulary; a fixed list cannot cover the second and the design's list omits the first. Collision rate depends on where the stem is matched, not which stems are matched: restricting to import-like lines lifts precision from 0.14 to 0.18 up to 0.78 to 0.88 with no recall loss on ordinary modules, and the residual errors are duplicate stems.
2. **Recall is structurally 1.0 for ordinary Python modules.** A Python import must name the module stem, so the dangerous dead-code failure never occurred for a non-package file in any variant. This holds for languages whose imports name file paths (Python, JavaScript, TypeScript, Go, Rust, Ruby). For languages that import namespaces and use type names at call sites (C#, Java) the anywhere mode at 0.17 precision is the only option; that case was not measured.
3. **Package files are a different object.** `__init__.py` is referenced by directory name, never by stem, and imported implicitly by every submodule import. It is the largest false-positive source (28 to 41 percent of edges) and the only recall gap. Treat package and index files as ambiguous with fan-in null.
4. **Approximate cycles are prose artefacts.** Every as-designed cycle came from a docstring naming a sibling file; every true cycle runs through a package init or a stoplisted `config.py`. Under the fixed graph the one cycle emitted was real, but recall stays near zero on Python because its cycles live in re-export packages.
5. **Regex leads fail on prose and succeed on syntax.** The rules matching syntax (`except ... pass`, `BaseException`) produced usable leads; the rules recognising code inside comments or secrets inside strings matched explanatory text and fixtures.

## Recommended changes

1. **Match stems in import-like lines by default** for path-import languages, including parenthesised or backslash continuation lines (without them FusionHelper loses 8 ordinary modules). Keep the anywhere mode as an explicit per-language fallback for C# and Java, labelled lower confidence.
2. **Replace the word stoplist with a mechanical ambiguity rule** plus a short fixed list: ambiguous when the stem is shared by two or more files, when the file is a package or index file (`__init__`, `__main__`, `index`, `mod`, `lib`), when it is a test harness file (`conftest`, `setup`), or when it is in the existing ten. Do not extend the list with domain vocabulary.
3. **Keep the minimum stem length at 4.**
4. **Do not map package files to their directory name**; it inflates the repository maximum four to five times and compresses F for every other file.
5. **wF default.** With changes 1 and 2 the F term's mean absolute error is 0.001 and the balanced preset's wF 0.5 is safe. Without them wF should be 0 (concern 3 option B).
6. **Cycles.** Emit approximate cycles only from the import-line graph, as capped leads for the architecture scout, never as statistics, and say in `design.md` that recall on Python is low because cycles route through package re-exports. As designed, drop the cycle output.
7. **Dead-code corroboration.** Corroborate only ordinary modules, and record that fan-in counts imports only, so entry points, scripts run by name and pytest-discovered files have fan-in 0 without being dead; the dead-code verifier question must ask about those.
8. **Exception swallowing rule.** Keep `pass` and `return None` bodies. Keep log bodies only when the log call does not carry the exception (no `exc_info`, no `.exception(`, no use of the `as` name); that removes 9 of 14 log hits, which were all the sampled false positives. Add `annotated: true` when the except line carries a trailing comment or `noqa` (38 of 94), and emit `BaseException` as its own higher-severity rule (28 of 94).
9. **Commented-out code rule.** Replace the `= ; { )` test with "the run, stripped of comment markers, parses as a statement list in the file's language" (`ast.parse` rejected all 33 false hits); for other languages require a majority of lines to start with a statement keyword, an assignment or a call. As written, the rule should not ship.
10. **Credential rule.** Exclude values beginning with `$`, `${`, `{{`, `<` or `%`, and values matching `fake|dummy|example|placeholder|changeme|your_|xxx`; keep the tests-class exclusion, which removed 7 of 9 hits. The fixture corpus of 4.14 needs seeded true positives.
11. **Cost.** No optimisation is needed, but an inverted stem index (one pass over each file's identifier set against a stem-to-file map) is a three-line change that removes the quadratic loop.
