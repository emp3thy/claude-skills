Run
Run id: 2026-01-09-e8e9
Mode: later
Scope: since e60469bbdd91ad996e42509f04d7c699b8f4c52a
Last run: e60469bbdd91ad996e42509f04d7c699b8f4c52a (commit)
Head: 1e5a17fbc453844532790cdbda8f7599c53bbbf6
Check: no

Docs
scanned: 10
excluded: 1
- basename:CHANGELOG*: 1
skipped: 0

References and anchors
references: 60
anchored: 31
unanchored: 28
- ambiguous: 14
- unknown: 14

Checkability
README.md: 8 refs, 3 anchored (38%)
docs/cli.md: 15 refs, 7 anchored (47%)
docs/configuration.md: 6 refs, 4 anchored (67%)
docs/design.md: 3 refs, 1 anchored (33%)
docs/internals.md: 5 refs, 2 anchored (40%)
docs/operations.md: 7 refs, 4 anchored (57%)
docs/process.md: 0 refs, 0 anchored (0%)
docs/storage.md: 1 refs, 1 anchored (100%)
docs/tools.md: 9 refs, 8 anchored (89%)
docs/untouched.md: 6 refs, 1 anchored (17%)
Unverifiable (no anchor):
  - docs/process.md
Weakly anchored:
  - docs/design.md
  - docs/internals.md
  - docs/storage.md
  - docs/untouched.md
A later run cannot see code changes behind these docs until they name code.

Notice loop
placed 0, escalated 1, cleared 0 (now anchored 0, block changed 0, drift-ignore 0), removed 0, stale 0

Change set
changed files 10, hunks 10
- README.md: anchors 1, doc changed
- docs/cli.md: anchors 1, doc changed
- docs/configuration.md: doc changed
- docs/design.md: missing 2, doc changed
- docs/internals.md: anchors 2, doc changed
- docs/operations.md: anchors 4, doc changed
- docs/tools.md: doc changed

Review units
checked 1, unchecked by cap 0, unchecked after retry 0, retry units 0, not reviewed 0 ranges

Claims checked
claims checked: 34

Edits proposed
review: 2
gap: 1
notice: 1
script: 3

Script edits
citations: 4 checked, 0 current, 2 moved, 0 ambiguous, 1 use sites, 1 unresolved
fact rows: 2 checked, 1 corrected, 1 not in scan
agent edits dropped as overlap-script: 0

Script checks
kept 7

Verdicts
accept 3, reject 0, unsure 0, unverified 0

Applied
applied 7, reverted 0, link updates 0
- README.md
- docs/cli.md
- docs/design.md
- docs/internals.md
- docs/operations.md

Gaps
candidates 1
gaps by kind: undocumented 0, missing-from-list 1
targets by doc:
- docs/cli.md: 1
no home 0
refusals: not-user-facing 0, already-documented 0
unchecked gap docs: 0

Needs a human decision
entries: 1
- docs/design.md:13 unverified: Writes go to disk before the reply returns, so a crash loses no acknowledged write.

Markers
markers without reasons: 0
stale markers: 0
stale notices: 0

Result
Branch: docs/drift-golden
Commits: 4d525ba8e33e53084755d241f47413af14b5e579 (corrections)
Commits: 2553f8da6a86ecca79b4b3e6e1d0a02b5bec62fd (additions)
Commits: c47622b10ccafb1132b03b0276ac9589e881a3f7 (citations)
