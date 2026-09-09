---
schema_version: 2
scan_date: 2026-09-09
root: C:\Users\gethi\AppData\Local\Temp\live-mixed-decoys-60r1jacg
total_files: 15
total_loc: 534
languages:
- go
- markdown
preset: balanced
families_run:
- complex-units
- god-classes
- duplication
- dead-code
- error-masking
- test-gaps
- half-finished
- migration
- dependency-debt
- doc-drift
- architecture
- security
- test-quality
- pipeline-infra
families_skipped: []
tools_run:
- lizard
tools_absent:
- actionlint (absent)
- gitleaks (absent)
- hadolint (absent)
- jscpd (skipped)
- knip (skipped)
- madge (skipped)
- osv-scanner (absent)
- ruff (skipped)
- vulture (skipped)
git_available: true
counts:
  candidates: 36
  quote_failed: 0
  verified: 35
  tier_a: 16
  tier_b: 5
  tier_c: 14
  unverified: 1
  rejected: 1
  suppressed: 0
---

# Tech-debt scan - 2026-09-09

Scanned `C:\Users\gethi\AppData\Local\Temp\live-mixed-decoys-60r1jacg` - 15 files, 534 LOC across: go, markdown.

Review each finding below. To act on one, change its `status:` from `pending` to
`approved`, `rejected`, or `accepted` (add a `reason:` and an optional `until:` ISO
date), then run `/tech-debt-promote`.

Top hotspots: `internal/lookup/lookup.go` (50.0), `internal/store/store.go` (8.5), `cmd/app/main.go` (4.2), `internal/dispatch/dispatch.go` (2.5), `internal/httpc/httpc.go` (2.0).

# Top 5

## lookup.PathFor routing table has no test at all

```yaml
status: pending
slug: lookup-pathfor-routing-table-has-no-test-at-all
fingerprint: 4ab7633f1331e12f
tier: A
priority: 7.5
family: test-gaps
category: test-gaps
debt_type: test
type_id: TD-04
severity: 3
effort: S
diff: NEW
```

### Proof

No lookup_test.go exists (only internal/store/store_test.go in the whole repo). TestOpenMissing calls Open("missing"), which routes through PathFor's fallback branch (line 8, 'missing' not in paths map) but only asserts that os.Stat then errors — it never inspects the returned path string, so even the fallback branch is unverified. The known-name branch (lines 5-6, e.g. paths["n001"]) is never exercised by any test in the repo. No integration/e2e suite exists to cover it indirectly.

### Evidence

- `internal/lookup/lookup.go:4-9`

```
func PathFor(name string) string {
	if p, ok := paths[name]; ok {
		return p
	}
	return "data/" + name + ".json"
}
```

### Signals

- hotspot score 50.0, churn 1, coupling pairs 0, fan-in 1 (approximate)
- confirmed by: hotspot, scout:test-gaps, signal:no-mapped-tests

### Remediation

Add internal/lookup/lookup_test.go. Write a table-driven test covering: (1) a known key already present in the paths map, asserting PathFor returns the exact mapped value; (2) an unknown key, asserting PathFor returns the constructed fallback string "data/" + name + ".json" rather than just checking it fails elsewhere; (3) an empty-string name, asserting the fallback still constructs a sane path. Update or replace the existing Open("missing") test in the caller package so it asserts on the returned path value, not just the resulting os.Stat error, so the fallback branch is actually verified rather than incidentally exercised.

### Acceptance criteria

- [ ] lookup_test.go exists and calls PathFor with at least one key present in the paths map, asserting the exact returned string
- [ ] lookup_test.go calls PathFor with a key absent from the paths map and asserts the returned string equals the fallback format
- [ ] The existing TestOpenMissing (or equivalent) is updated to assert on the returned path value rather than only the os.Stat error
- [ ] go test ./internal/lookup/... passes

## legacy dispatch handler panics unconditionally

```yaml
status: pending
slug: legacy-dispatch-handler-panics-unconditionally
fingerprint: a9f954d154719182
tier: A
priority: 6.2
family: half-finished
category: half-finished
debt_type: code
type_id: null
severity: 4
effort: S
diff: NEW
```

### Proof

internal/dispatch/dispatch.go:7-12 registers legacyHandler under the 'legacy' key in the live handlers map; Run (lines 15-24) looks up handlers[args[0]] and invokes it directly, with no guard for the legacy case. cmd/app/main.go:25 (opened) calls dispatch.Run(os.Args[1:]) unconditionally from main, so `app legacy` panics and crashes the process (line 31: panic("not implemented")). No ticket number, TODO date, or comment marking this as an intentional, tracked deferral — the only comment (line 14) just describes routing, not the panic.

### Evidence

- `internal/dispatch/dispatch.go:7-12`

```
var handlers = map[string]handler{
	"start":  start,
	"stop":   stop,
	"status": status,
	"legacy": legacyHandler,
}
```

- `internal/dispatch/dispatch.go:30-32`

```
func legacyHandler(args []string) error {
	panic("not implemented")
}
```

### Signals

- hotspot score 2.5, churn 1, coupling pairs 0, fan-in 1 (approximate)
- confirmed by: hotspot, pattern:stub, scout:half-finished

### Remediation

Decide whether the legacy command is still needed. If not, remove the "legacy" entry from the handlers map in dispatch.go and delete legacyHandler, so unknown-command handling in Run returns the existing "unknown command" error instead of routing to a panic. If legacy support must remain available, replace the panic with a return of a typed, non-fatal error (e.g. errors.New("legacy command not implemented")) so Run's normal error path handles it and main.go's exit path stays graceful. Either way, remove any dead code and keep the routing comment in Run accurate.

### Acceptance criteria

- [ ] legacyHandler no longer contains panic("not implemented")
- [ ] Either the "legacy" map entry and legacyHandler are deleted, or legacyHandler returns an error instead of panicking
- [ ] Running the built binary with `app legacy` exits with a non-zero status and an error message instead of a Go panic/stack trace
- [ ] go build ./... succeeds with no dead references to a removed legacyHandler

## dispatch.Run's routing table and legacy panic path are untested

```yaml
status: pending
slug: dispatch-run-s-routing-table-and-legacy-panic-path-are-untested
fingerprint: b47c540bcdea4204
tier: A
priority: 6.2
family: test-gaps
category: test-gaps
debt_type: test
type_id: TD-04
severity: 4
effort: S
diff: NEW
```

### Proof

Glob for **/*_test.go finds only internal/store/store_test.go; no dispatch test exists. Run (lines 15-23) has three untested branches: empty args (line 16-18), unknown command (19-21), and successful handler dispatch (23). The map (lines 7-12) is confirmed the sole routing mechanism (no reflection/other tables), and 'legacy' at line 11 wires to legacyHandler which panics unconditionally (lines 30-32), so any test exercising Run with args[0]=='legacy' would crash rather than assert. main.go passes os.Args straight through with no filtering, so the path is live.

### Evidence

- `internal/dispatch/dispatch.go:15-23`

```
func Run(args []string) error {
	if len(args) == 0 {
		return errors.New("no command")
	}
	h, ok := handlers[args[0]]
	if !ok {
		return errors.New("unknown command: " + args[0])
	}
	return h(args[1:])
```

- `internal/dispatch/dispatch.go:30-32`

```
func legacyHandler(args []string) error {
	panic("not implemented")
}
```

### Signals

- hotspot score 2.5, churn 1, coupling pairs 0, fan-in 1 (approximate)
- confirmed by: hotspot, scout:test-gaps, signal:no-mapped-tests

### Remediation

Add internal/dispatch/dispatch_test.go covering all branches of Run: empty args returns the "no command" error; an unrecognized command returns "unknown command: <name>"; a known command (e.g. "status") dispatches to its handler and returns its result. Do not add a test that invokes the legacy path until finding a9f954d154719182 (the unconditional panic) is fixed — write that fix first, then add a case asserting legacyHandler's corrected (non-panicking) behavior. Sequence the work so the panic fix lands before or together with this test to avoid a test that documents a crash as expected behavior.

### Acceptance criteria

- [ ] dispatch_test.go exists with cases for empty args, unknown command, and at least one known command
- [ ] A test case exercises the "legacy" key only after legacyHandler no longer panics, and asserts its returned value/error
- [ ] go test ./internal/dispatch/... passes with no recover()-wrapped panic assertions
- [ ] Test coverage for dispatch.go's Run function reaches all three branches (no command, unknown command, dispatched command)

## flags.IsEnabled (payments kill switch) has no test

```yaml
status: pending
slug: flags-isenabled-payments-kill-switch-has-no-test
fingerprint: 738155637b8b33d1
tier: A
priority: 6.056
family: test-gaps
category: test-gaps
debt_type: test
type_id: TD-04
severity: 4
effort: S
diff: NEW
```

### Proof

docs/runbook.md explicitly documents payments.killswitch as a real, permanent incident-response control operated by on-call, matching the in-code comment (flags.go lines 3-6). Glob for **/*_test.go finds only store_test.go; no test exists for IsEnabled (lines 11-13) covering the true, false, or unknown-key cases. Because this is a production safety control rather than glue/config, the 'glue rarely needs tests' trap does not apply, and severity 4 is warranted: an untested regression (e.g. inverted logic) would surface only when on-call needs the switch during an incident.

### Evidence

- `internal/flags/flags.go:11-13`

```
func IsEnabled(name string) bool {
	return Flags[name]
}
```

### Signals

- hotspot score 0.7, churn 2, coupling pairs 0, fan-in 1 (approximate)
- confirmed by: scout:test-gaps, signal:no-mapped-tests

### Remediation

Add internal/flags/flags_test.go with cases for IsEnabled: a name present in the Flags map with a true value, a name present with a false value, and a name absent from the map (verifying it returns false via Go's zero-value map lookup rather than panicking). Since docs/runbook.md documents payments.killswitch as an operational on-call control, include a test case using that exact key name so a future rename or logic inversion is caught. Keep the test isolated from any global mutable state in Flags by resetting or scoping the map per test case if Flags is package-level and mutable.

### Acceptance criteria

- [ ] flags_test.go exists and asserts IsEnabled returns true for a key set to true in Flags
- [ ] flags_test.go asserts IsEnabled returns false for a key set to false in Flags
- [ ] flags_test.go asserts IsEnabled returns false for a key not present in Flags
- [ ] A test case explicitly covers the "payments.killswitch" key referenced in docs/runbook.md
- [ ] go test ./internal/flags/... passes

## TLS verification disabled on shared DefaultTransport

```yaml
status: pending
slug: tls-verification-disabled-on-shared-defaulttransport
fingerprint: a8a0b3c16057f8e1
tier: B
priority: 5.39
family: security
category: security
debt_type: security
type_id: TD-03
severity: 5
effort: S
diff: NEW
```

### Proof

httpc.go:13 sets http.DefaultTransport.(*http.Transport).TLSClientConfig = &tls.Config{InsecureSkipVerify: true}, mutating the process-wide default transport (not a request-scoped client), and Fetch is called unconditionally from main.go:28 against https://example.com/health, a public host. Any other code in the process using http.DefaultTransport (directly or via http.Get) inherits disabled cert verification. Not a placeholder/fixture — this is live production code on the main path. Real, high-severity issue.

### Evidence

- `internal/httpc/httpc.go:9-9`

```
const apiToken = "tok_***"
```

- `internal/httpc/httpc.go:12-14`

```
func Fetch(url string) string {
	http.DefaultTransport.(*http.Transport).TLSClientConfig = &tls.Config{InsecureSkipVerify: true}
	resp, err := http.Get(url)
```

### Signals

- hotspot score 2.0, churn 1, coupling pairs 0, fan-in 1 (approximate)
- confirmed by: hotspot, pattern:credential, pattern:tls-disabled, satd, scout:security

### Remediation

Stop mutating http.DefaultTransport globally. Update main.go's health check to call the existing FetchWithTimeout in httpc_safe.go (which already uses a scoped *http.Client with a timeout and default TLS verification) instead of the deprecated Fetch. Remove the InsecureSkipVerify line and the DefaultTransport mutation from Fetch entirely; if Fetch must be kept for backward compatibility, have it delegate to a request-scoped *http.Client with default TLS settings rather than touching the process-wide transport. Also relocate the hardcoded apiToken constant out of source (env var or secret store) as part of the same cleanup pass, since it sits in the same file and is a related exposure.

### Acceptance criteria

- [ ] No code path sets InsecureSkipVerify: true or otherwise mutates http.DefaultTransport
- [ ] main.go's health check calls FetchWithTimeout (or an equivalent function using a scoped client with default TLS verification) instead of the deprecated Fetch
- [ ] If Fetch is retained, it uses a request-scoped http.Client rather than modifying http.DefaultTransport
- [ ] apiToken is no longer a hardcoded string literal in httpc.go
- [ ] go build ./... succeeds and the health check request against https://example.com/health completes with TLS verification enabled

# Below the cut

## Store.Load logs generic message on unmarshal failure, drops cause, continues

```yaml
status: pending
slug: store-load-logs-generic-message-on-unmarshal-failure-drops-cause
fingerprint: 4731d613c0d929c9
tier: A
priority: 5.01
family: error-masking
category: error-masking
debt_type: defect
type_id: TD-13
severity: 3
effort: S
diff: NEW
```

### Proof

On unmarshal failure (line 31), the actual err is scoped to the if-statement and discarded — only a static string is printed via fmt.Println (line 32), not returned or logged with cause. Execution falls through to return out (line 34), which may be empty or partially populated, indistinguishable from a genuinely empty/valid store to the caller. store_test.go's TestLoadSmoke uses path "x", which fails at os.ReadFile (line 27) and returns nil before ever reaching the unmarshal branch, so this masking path is untested. This is not a process/request boundary handler — Load's caller has no way to detect corruption.

### Evidence

- `internal/store/store.go:30-34`

```
	out := map[string]string{}
	if err := json.Unmarshal(raw, &out); err != nil {
		fmt.Println("store: unmarshal failed")
	}
	return out
```

- `internal/store/store.go:25-29`

```
func (s *Store) Load(key string) map[string]string {
	raw, err := os.ReadFile(s.path)
	if err != nil {
		return nil
	}
```

## httpc.Fetch swallows HTTP request error, returns empty string

```yaml
status: pending
slug: httpc-fetch-swallows-http-request-error-returns-empty-string
fingerprint: 00c01f25e1d4eebe
tier: A
priority: 4.62
family: error-masking
category: error-masking
debt_type: defect
type_id: TD-13
severity: 3
effort: S
diff: NEW
```

### Proof

On http.Get error (line 14), Fetch returns "" with no log call anywhere in the function (lines 12-21) — the error value is discarded entirely, not just unwrapped. The sole caller, main.go:28, discards the return with '_', so a TLS failure, DNS failure, or connection refused during the health check produces zero observable signal: no log line, no error return, no non-2xx status. This is not a boundary catch-and-continue that reports, since nothing is reported.

### Evidence

- `internal/httpc/httpc.go:19-19`

```
	body, _ := io.ReadAll(resp.Body)
```

- `internal/httpc/httpc.go:14-17`

```
	resp, err := http.Get(url)
	if err != nil {
		return ""
	}
```

## Deprecated no-timeout Fetch still called from main's health check

```yaml
status: pending
slug: deprecated-no-timeout-fetch-still-called-from-main-s-health-chec
fingerprint: bdb2a46b2041a926
tier: A
priority: 4.62
family: half-finished
category: half-finished
debt_type: code
type_id: null
severity: 4
effort: M
diff: NEW
```

### Proof

httpc_safe.go:8 shows FetchWithTimeout's client has Timeout: 5*time.Second; httpc.go:14 shows Fetch uses http.Get, which uses http.DefaultClient with no timeout. main.go:28 calls the deprecated, unbounded Fetch as the last statement in main(), so a non-responding health endpoint blocks process exit indefinitely. No ticket or removal date accompanies the Deprecated marker at httpc.go:11. Real half-finished migration.

### Evidence

- `internal/httpc/httpc.go:11-14`

```
// Deprecated: use FetchWithTimeout from httpc_safe.go.
func Fetch(url string) string {
	http.DefaultTransport.(*http.Transport).TLSClientConfig = &tls.Config{InsecureSkipVerify: true}
	resp, err := http.Get(url)
```

- `cmd/app/main.go:28-28`

```
	_ = httpc.Fetch("https://example.com/health")
```

## Store mixes file-backed JSON loading with raw SQL querying

```yaml
status: pending
slug: store-mixes-file-backed-json-loading-with-raw-sql-querying
fingerprint: 242bb6e6d1f45475
tier: A
priority: 3.34
family: god-classes
category: god-classes
debt_type: design
type_id: TD-11
severity: 2
effort: S
diff: NEW
```

### Proof

Store's two fields are genuinely disjoint: path is set by Open (line 22) and used only by Load (line 26); db is never assigned anywhere (Open only sets path) yet Find (line 38) queries s.db exclusively — meaning Find would always nil-pointer-panic if called, and the two method/field clusters never interact. This is a real single-responsibility violation (file+JSON vs SQL), not a facade/DTO/builder. cmd/app/main.go only calls Open/Close (lines 16-21), never Find, consistent with the SQL side being unwired.

### Evidence

- `internal/store/store.go:12-17`

```
type Store struct {
	path string
	db   *sql.DB
}

func Open(name string) (*Store, error) {
```

## Store.db is never initialized, leaving Find() incomplete

```yaml
status: pending
slug: store-db-is-never-initialized-leaving-find-incomplete
fingerprint: 4d2f8764e8547e65
tier: A
priority: 3.34
family: half-finished
category: half-finished
debt_type: code
type_id: null
severity: 2
effort: S
diff: NEW
```

### Proof

store.go:12-15 declares db *sql.DB; Open() (17-23) only sets path via lookup.PathFor and os.Stat, never assigns db. Find() (37-39) calls s.db.Query unconditionally, so any call on a Store from Open() nil-panics. Store is a concrete struct, not an interface/abstract contract. No TODO/FIXME/ticket reference found in internal/store. main.go:16 only calls store.Open/s.Close(), never Find(), so the path is real but dormant, matching the stated severity 2.

### Evidence

- `internal/store/store.go:12-15`

```
type Store struct {
	path string
	db   *sql.DB
}
```

- `internal/store/store.go:17-23`

```
func Open(name string) (*Store, error) {
	path := lookup.PathFor(name)
	if _, err := os.Stat(path); err != nil {
		return nil, err
	}
	return &Store{path: path}, nil
}
```

- `internal/store/store.go:37-39`

```
func (s *Store) Find(id string) (*sql.Rows, error) {
	return s.db.Query("SELECT * FROM items WHERE id = '" + id + "'")
}
```

## Deprecated httpc.Fetch still called; replacement FetchWithTimeout unused

```yaml
status: pending
slug: deprecated-httpc-fetch-still-called-replacement-fetchwithtimeout
fingerprint: 013acd6db5ec7157
tier: B
priority: 3.234
family: migration
category: migration
debt_type: design
type_id: null
severity: 3
effort: S
diff: NEW
```

### Proof

Fetch carries a Deprecated marker (line 11) pointing to FetchWithTimeout, but grep for FetchWithTimeout across the repo shows only its definition (httpc_safe.go:10) and the deprecation comment — zero call sites. main.go:28, the only httpc call site in the repo, still calls Fetch. No ticket, removal date, or adapter/multi-backend rationale is attached to the comment, so this reads as an incomplete migration rather than a deliberate two-path design.

### Evidence

- `internal/httpc/httpc.go:11-13`

```
// Deprecated: use FetchWithTimeout from httpc_safe.go.
func Fetch(url string) string {
	http.DefaultTransport.(*http.Transport).TLSClientConfig = &tls.Config{InsecureSkipVerify: true}
```

- `internal/httpc/httpc_safe.go:10-10`

```
func FetchWithTimeout(url string) (int, error) {
```

- `cmd/app/main.go:28-28`

```
	_ = httpc.Fetch("https://example.com/health")
```

## httpc.Fetch (used on main's health-check path) is untested

```yaml
status: pending
slug: httpc-fetch-used-on-main-s-health-check-path-is-untested
fingerprint: 5a83178d9cb40959
tier: A
priority: 3.08
family: test-gaps
category: test-gaps
debt_type: test
type_id: TD-04
severity: 2
effort: S
diff: NEW
```

### Proof

Glob for **/*_test.go finds only internal/store/store_test.go; no test file exists for the httpc package, so neither Fetch (lines 12-21, called live from main.go:28) nor FetchWithTimeout has coverage for success, non-2xx, or request-error behavior. Fetch is on main's live health-check path, not dead glue, so the 'glue rarely needs tests' trap doesn't apply. Severity 2 is appropriate here since this candidate only concerns missing tests, distinct from the higher-severity error-masking defect itself (candidate 00c01f25e1d4eebe).

### Evidence

- `internal/httpc/httpc.go:12-18`

```
func Fetch(url string) string {
	http.DefaultTransport.(*http.Transport).TLSClientConfig = &tls.Config{InsecureSkipVerify: true}
	resp, err := http.Get(url)
	if err != nil {
		return ""
	}
	defer resp.Body.Close()
```

## build.Builder fluent config methods have no test

```yaml
status: pending
slug: build-builder-fluent-config-methods-have-no-test
fingerprint: f6a360e9cca15f3a
tier: A
priority: 2.056
family: test-gaps
category: test-gaps
debt_type: test
type_id: TD-04
severity: 2
effort: S
diff: NEW
```

### Proof

internal/build/builder.go:15-18 defines WithName, WithPort, WithTLS and Build. A glob for **/*_test.go in the repo returns only internal/store/store_test.go; no internal/build/*_test.go exists. cmd/app/main.go:15 (opened) calls build.NewConfig().WithName(...).WithPort(...).Build() but never exercises WithTLS, and it is not a test — it provides no assertions. So the chained builder methods, including the recently added WithTLS, have no unit or integration coverage anywhere in the repo.

### Evidence

- `internal/build/builder.go:15-18`

```
func (b *Builder) WithName(name string) *Builder { b.cfg.Name = name; return b }
func (b *Builder) WithPort(port int) *Builder    { b.cfg.Port = port; return b }
func (b *Builder) WithTLS(on bool) *Builder      { b.cfg.TLS = on; return b }
func (b *Builder) Build() Config                 { return b.cfg }
```

## CI workflow gaps in .github/workflows/ci.yml

```yaml
status: pending
slug: ci-workflow-gaps-in-github-workflows-ci-yml
fingerprint: 6a5a73520cb40aa3
tier: A
priority: 2.0
family: pipeline-infra
category: pipeline-infra
debt_type: build
type_id: TD-14
severity: 2
effort: S
diff: NEW
```

### Proof

verified by construction

### Evidence

- `.github/workflows/ci.yml:9-9`

```
continue-on-error: true
```

- `.github/workflows/ci.yml:7-7`

```
runs-on: ubuntu-latest
```

- `.github/workflows/ci.yml:11-11`

```
- uses: actions/checkout@v4
```

- `.github/workflows/ci.yml:12-12`

```
- uses: actions/setup-go@v5
```

- `.github/workflows/ci.yml:18-18`

```
#   runs-on: ubuntu-latest
```

## Container configuration gaps in Dockerfile

```yaml
status: pending
slug: container-configuration-gaps-in-dockerfile
fingerprint: 6c225b145abb8048
tier: A
priority: 2.0
family: pipeline-infra
category: pipeline-infra
debt_type: infrastructure
type_id: TD-19
severity: 2
effort: S
diff: NEW
```

### Proof

verified by construction

### Evidence

- `Dockerfile:8-8`

```
RUN apk add --no-cache curl
```

## Kubernetes manifest gaps in k8s/deployment.yaml

```yaml
status: pending
slug: kubernetes-manifest-gaps-in-k8s-deployment-yaml
fingerprint: 7bf4b30093bfa34f
tier: A
priority: 2.0
family: pipeline-infra
category: pipeline-infra
debt_type: infrastructure
type_id: TD-19
severity: 2
effort: S
diff: NEW
```

### Proof

verified by construction

### Evidence

- `k8s/deployment.yaml:9-9`

```
- name: app
```

- `k8s/deployment.yaml:10-10`

```
image: example/app:latest
```

- `k8s/deployment.yaml:12-12`

```
privileged: true
```

## No CI step builds or publishes the image or applies k8s manifests

```yaml
status: pending
slug: no-ci-step-builds-or-publishes-the-image-or-applies-k8s-manifest
fingerprint: 2bbdfabd33d37ac2
tier: B
priority: 1.575
family: pipeline-infra
category: pipeline-infra
debt_type: build
type_id: TD-19
severity: 3
effort: M
diff: NEW
```

### Proof

ci.yml:1-16 has a single job that checks out, sets up Go, and runs `go test ./...` (line 16); there is no docker build/push step and no kubectl apply/manifest-lint step anywhere in the workflow. Dockerfile (opened) pulls a script over curl|sh (line 9) and k8s/deployment.yaml sets image: example/app:latest with privileged: true (lines 10-12), both consistent with these manifests never passing through an automated pipeline that would catch such issues. docs/runbook.md (opened) only documents the payments kill switch, not a manual deploy process. No doc marks this as an intentional manual step.

### Evidence

- `.github/workflows/ci.yml:1-16`

```
name: ci
on: [push]
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    continue-on-error: true
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: "1.22"
          cache: true
      - run: go test ./...
```

- `k8s/deployment.yaml:1-10`

```
apiVersion: apps/v1
kind: Deployment
metadata:
  name: app
spec:
  template:
    spec:
      containers:
        - name: app
          image: example/app:latest
```

## Release process gaps

```yaml
status: pending
slug: release-process-gaps
fingerprint: 942a462aa461112c
tier: A
priority: 1.5
family: pipeline-infra
category: pipeline-infra
debt_type: build
type_id: TD-27
severity: 2
effort: M
diff: NEW
```

### Proof

verified by construction

### Evidence

- repository-level finding (no file or line range)

```
branch staging unmerged, last commit 2026-03-09 (184 days ago)
```

## TestLoadSmoke sleeps arbitrarily and asserts nothing

```yaml
status: pending
slug: testloadsmoke-sleeps-arbitrarily-and-asserts-nothing
fingerprint: 60debb6c727d06c5
tier: B
priority: 1.4392
family: test-quality
category: test-quality
debt_type: test
type_id: null
severity: 2
effort: S
diff: NEW
```

### Proof

store_test.go:14-17: TestLoadSmoke sleeps 10ms then calls Load synchronously and discards the result with '_ ='. Load (store.go:25-35) does no async or time-dependent work, so the sleep serves no purpose. No assertion is made on the returned map, error state, or the swallowed unmarshal error logged at store.go:32. This is a genuine assert-free, purposeless-sleep test, not a documented smoke test guarding only startup.

### Evidence

- `internal/store/store_test.go:14-17`

```
func TestLoadSmoke(t *testing.T) {
	time.Sleep(10 * time.Millisecond)
	_ = (&Store{path: "x"}).Load("k")
}
```

## go.sum references a package absent from go.mod's requires

```yaml
status: pending
slug: go-sum-references-a-package-absent-from-go-mod-s-requires
fingerprint: bf26c2f7166e080c
tier: B
priority: 1.4
family: dependency-debt
category: dependency-debt
debt_type: dependency
type_id: TD-02
severity: 2
effort: S
diff: NEW
```

### Proof

go.mod:1-3 declares module example.com/app with no require block at all. go.sum:1 nonetheless contains a hash entry for github.com/example/dep v1.2.0. A repo-wide grep for 'example/dep' and 'Fingerprint'-style import paths found no import of that package anywhere in source. This is an application module (has cmd/app/main.go), not a library, so an orphaned go.sum entry with zero matching requires indicates a stale lockfile (e.g., dependency removed without `go mod tidy`), not a legitimate library-without-lockfile situation.

### Evidence

- `go.mod:1-3`

```
module example.com/app

go 1.22
```

- `go.sum:1-1`

```
github.com/example/dep v1.2.0 h1:abc=
```

## Container configuration gaps in docker-compose.dev.yml

```yaml
status: pending
slug: container-configuration-gaps-in-docker-compose-dev-yml
fingerprint: e580ee72fab36350
tier: A
priority: 1.0
family: pipeline-infra
category: pipeline-infra
debt_type: infrastructure
type_id: TD-19
severity: 1
effort: S
diff: NEW
```

### Proof

verified by construction

### Evidence

- `docker-compose.dev.yml:3-3`

```
image: postgres:latest
```

- `docker-compose.dev.yml:5-5`

```
image: mailhog/mailhog:latest
```

# Below the cut: tier C and unverified

| slug | family | file | reason |
| --- | --- | --- | --- |
| f-290-entry-lookup-map-duplicates-the-fallback-it-shadows | dead-code | internal/lookup/lookup.go | dead-code is capped at C without tool corroboration |
| library-code-writes-to-stdout-instead-of-using-the-log-package | pipeline-infra | internal/store/store.go | the verifier downgraded it |
| store-find-query-builder-has-no-test-coverage | test-gaps | internal/store/store.go | the verifier downgraded it |
| string-concatenated-sql-in-store-find | security | internal/store/store.go | the verifier downgraded it |
| store-component-mixes-json-file-backend-with-unwired-sql-backend | architecture | internal/store/store.go | the verifier downgraded it |
| legacyhandler-is-wired-into-dispatch-but-always-panics | dead-code | internal/dispatch/dispatch.go | dead-code is capped at C without tool corroboration |
| deprecated-comment-on-fetch-is-not-followed-by-its-only-caller | doc-drift | internal/httpc/httpc.go | the verifier downgraded it |
| deprecated-fetch-still-wired-into-main-instead-of-its-replacemen | dead-code | internal/httpc/httpc.go | the verifier downgraded it |
| fetchwithtimeout-the-designated-replacement-has-no-callers | dead-code | internal/httpc/httpc_safe.go | dead-code is capped at C without tool corroboration |
| store-test-go-smoke-tests-load-without-asserting-its-output | test-gaps | internal/store/store_test.go | the verifier downgraded it |
| internal-crypto-package-fingerprint-has-zero-callers-repo-wide | dead-code | internal/crypto/hash.go | dead-code is capped at C without tool corroboration |
| internal-shell-package-run-has-zero-callers-repo-wide | dead-code | internal/shell/run.go | dead-code is capped at C without tool corroboration |
| shell-exec-with-gosec-suppression-rests-on-unverified-trust-clai | security | internal/shell/run.go | the verifier downgraded it |
| units-package-conversion-label-helpers-are-entirely-untested | test-gaps | internal/units/units.go | not selected for verification |

# Considered and rejected

- **README feature list predates the kill-switch subsystem it doesn't mention** - `README.md` - A document that describes a planned or external interface is not drift.

# Looks bad but is fine

- `internal/lookup/lookup.go:11` - 290-entry map literal inflates hotspot score and file length, but it is a flat, cohesive lookup table with no branching or nesting; PathFor itself is a trivial 4-line function.
- `internal/lookup/lookup.go:11` - 302-line file and top hotspot score, but it is a single flat lookup map plus one accessor function (PathFor) — one cohesive concept, not multiple responsibilities or fan-in coupling. This is a size/complex-units question, not a god class, and that family is disabled here.
- `internal/build/builder.go:9` - Fluent builder (WithName/WithPort/WithTLS/Build) chaining calls on itself; wide by design, matches the explicit builder trap.
- `internal/dispatch/dispatch.go:15` - Thin dispatch table mapping command names to handler functions; a thin controller by design, not a hub with multiple reasons to change.
- `internal/lookup/lookup.go:11` - Large literal map (n001..n290 -> data/nNNN.json) looks repetitive but is a single data table, not logic duplicated across separate call sites; falls under the 'repeated literal values alone' trap, not TD-05.
- `internal/build/builder.go:15` - WithName/WithPort/WithTLS are one-line builder setters with the same shape but each sets a distinct field; standard builder-pattern boilerplate, not coupled duplicate logic.
- `internal/httpc/httpc.go:12` - Fetch and FetchWithTimeout (httpc_safe.go) both issue an HTTP GET, but have different signatures, return types, and one is explicitly marked deprecated in favor of the other -- different reasons to change, not a duplication pair.
- `internal/flags/flags.go:5` - payments.killswitch is documented in docs/runbook.md and in-code as a permanent, deliberately always-off-in-normal-operation kill switch flipped by on-call during incidents; this is the documented-kill-switch trap, not a stuck feature flag.
- `internal/dispatch/dispatch.go:26` - start/stop/status handlers are trivial no-op stubs but are live, reachable dispatch targets exercised through the same map as legacyHandler, not dead code.
- `internal/httpc/httpc_safe.go:10` - FetchWithTimeout returns (int, error) and propagates the http.Get error to the caller unmodified; this is correct error handling, not masking.
- `internal/dispatch/dispatch.go:30` - legacyHandler panics unconditionally with no recover() anywhere in the call chain (Run -> h(args)); the panic propagates and crashes the process rather than being caught and hidden, so this is not error-masking.
- `cmd/app/main.go:25` - dispatch.Run error is checked and passed to log.Fatal, which logs and exits; this is a legitimate process-boundary handling, not masking.
- `cmd/app/main.go:14` - main() is startup glue wiring config, store, flags, dispatch, and httpc together with no branching logic of its own beyond error propagation; this is conventionally left to integration/e2e coverage rather than unit tests.
- `internal/store/store.go:41` - Close() is a no-op, which looks incomplete, but since db is never opened there is nothing to close given the current (file-based) usage path.
- `docker-compose.yml:1` - docker-compose.yml (postgres+redis) and docker-compose.dev.yml (postgres+mailhog) look like a base file plus a dev-environment override, a deliberate split rather than an old/new config pair -- no naming or comment hints that one supersedes the other.
- `internal/build/builder.go:6` - Config.TLS / WithTLS is set nowhere and never read from cfg.TLS anywhere in the repo; it is unused rather than a second way of doing something an existing path already does, so it does not fit the migration pattern of old-vs-new coexistence.
- `docker-compose.dev.yml:3` - postgres:latest / mailhog:latest are container image tags for local dev convenience, not Go package manifest entries; out of scope for this family which is limited to go.mod/go.sum structural issues, and dev-only floating tags against a pinned prod compose file is a common, intentional pattern.
- `internal/httpc/httpc_safe.go:1` - Both httpc.go and httpc_safe.go use Go's stdlib net/http, not two different third-party HTTP client libraries, so this is not a duplicate-dependency case for this family.
- `docs/runbook.md:3` - Flagged by the staleness signal (377 days) but its content (payments.killswitch behavior, location in internal/flags/flags.go, on-call flip procedure) matches the current implementation in internal/flags/flags.go exactly; the two files share the same last-touched date in the inventory, so this is not actual drift.
- `internal/httpc:1` - httpc.go and httpc_safe.go both live in package httpc; this is one cohesive package with two functions, not a cross-package cycle or layering violation, so it is out of scope for this family.
- `cmd/app/main.go:1` - main.go importing build, dispatch, flags, httpc, and store gives it fan_out=4-5 and instability=1.0, but that is expected for a cmd composition root, not a smell.
- `internal/units:1` - internal/units and internal/crypto and internal/shell show fan_in=0 in coupling.json (isolated, uncalled packages); that is a dead-code signal, not a cycle or misplacement, so it belongs to a different family.
- `internal/crypto/hash.go:9` - md5 used inside a function named Fingerprint(id) with no callers anywhere in the repo; nothing indicates it hashes passwords or credentials rather than serving as a cache key/checksum, matching the stated trap for weak hashes used non-cryptographically.
- `internal/store/store_test.go:8` - if _, err := Open("missing"); err == nil { t.Fatal(...) } is the standard Go idiom for asserting an expected error in the absence of an assertion library; it is not conditional logic masking a missing assertion.
- `docker-compose.dev.yml:1` - Floating tags (postgres:latest, mailhog/mailhog:latest) in a file explicitly named .dev are expected for a dev-only compose file, per the stated trap.
- `.github/workflows/ci.yml:17` - Commented-out lint job is dead pipeline config, not duplicated YAML; only one workflow file exists so no duplication was found.
- `README.md:3` - A document that describes a planned or external interface is not drift.

# Open questions for the maintainer

- `internal/lookup/lookup.go:4` - All 290 map entries equal the fallback formula "data/" + name + ".json" exactly; unclear if the map exists to allow future per-name overrides or is purely redundant with the fallback.
- `internal/build/builder.go:17` - WithTLS has zero callers (main.go only chains WithName/WithPort) and was added by the recent 'feat: builder TLS option' commit -- is this in-progress wiring for an upcoming caller, or a stalled feature that should be removed?
- `internal/units/units.go:4` - Kilobytes and units/labels.go's Label have zero callers and were added together by the recent 'chore: unit helpers for the report' commit -- is a consumer ('the report') still pending, making these premature rather than dead?
- `internal/store/store.go:25` - Is a nil map from Load meant to signal 'no data' by convention elsewhere in the codebase, or is this an unintentional gap since no production caller currently checks for it?
- `internal/httpc/httpc.go:12` - Fetch is marked Deprecated in favor of FetchWithTimeout (which does propagate errors correctly) but is still called from cmd/app/main.go:28 — is that call site scheduled for migration?
- `internal/dispatch/dispatch.go:30` - Is the "legacy" command still invoked by any external caller/script, or is it dead and safe to remove instead of implement?
- `internal/store/store.go:37` - Is Store.Find part of an in-progress SQL migration, or is the db field/Find method dead code left over from a dropped design?
- `internal/httpc/httpc.go:11` - Is there a tracked ticket for migrating main.go's health check call from Fetch to FetchWithTimeout, or was the deprecation comment added without a follow-up plan?
- `README.md:1` - Is the minimal README intentional for an internal-only service, or is CONTRIBUTING/CHANGELOG coverage expected for this repo?
- `internal/store/store.go:37` - Was Find() meant to belong to a separate SQL-backed repository/component that was never split out, or is db a leftover from an earlier design that lookup-based file storage replaced?
- `internal/crypto/hash.go:8` - Is Fingerprint(id) intended for security-sensitive identification (e.g. tied to auth) or purely a cache/checksum key? No callers exist in the repo to determine intended use.
- `internal/httpc/httpc.go:9` - Is apiToken a real, still-valid credential, or a placeholder left over from a prior implementation? It is unused by any code path in this repo.
- `internal/store/store.go:37` - Find is exported but has no caller and s.db is never assigned in Open; is this method dead code slated for removal or wiring in progress?
- `:0` - Is image build/push and k8s apply performed manually or by a deploy mechanism outside this repository (not visible from repo contents)?

# Not assessed

- Families not run: none
- Tools: a claim that needs a tool which did not run -- currency, end-of-life, vulnerability -- is not assessed; the frontmatter's tools_absent names every such tool
- Runtime-only: coverage numbers, flake confirmation, model staleness, rollout state, deploy frequency
- By design: magic literals, convention violations, and class-level metrics that need a parser
