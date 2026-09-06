---
schema_version: 2
scan_date: 2026-09-06
root: <root>
total_files: 13
total_loc: 519
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
tools_run: []
tools_absent: []
git_available: true
counts:
  candidates: 31
  quote_failed: 1
  verified: 28
  tier_a: 10
  tier_b: 9
  tier_c: 9
  unverified: 3
  rejected: 3
  suppressed: 0
---

# Tech-debt scan - 2026-09-06

Scanned `<root>` - 13 files, 519 LOC across: go, markdown.

Review each finding below. To act on one, change its `status:` from `pending` to
`approved`, `rejected`, or `accepted` (add a `reason:` and an optional `until:` ISO
date), then run `/tech-debt-promote`.

Top hotspots: `internal/lookup/lookup.go` (50.0), `internal/store/store.go` (8.5), `cmd/app/main.go` (4.2), `internal/dispatch/dispatch.go` (2.5), `internal/httpc/httpc.go` (2.0).

# Top 5

## dispatch.Run branch logic (no-args, unknown cmd, legacy panic) is untested

```yaml
status: pending
slug: dispatch-run-branch-logic-no-args-unknown-cmd-legacy-panic-is-un
fingerprint: 81123c5aab0571a0
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

Only test file in the repo is internal/store/store_test.go (glob for **/*_test.go); no dispatch_test.go or unconventionally named test exists. Run() (dispatch.go:15-24) is invoked directly from main.go:25 with raw os.Args, so its empty-args, unknown-command and legacy-panic paths are all reachable from real CLI input with zero test coverage.

### Evidence

- `internal/dispatch/dispatch.go:15-24`

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
- confirmed by: hotspot, scout:test-gaps, signal:no-mapped-tests

### Remediation

Add `internal/dispatch/dispatch_test.go`; `internal/store/store_test.go` is the repository's only test file today. Table-drive `Run`: empty args returns the no-command error, an unknown name returns an error that echoes the name back, and a registered command such as `status` returns nil. Cover the `legacy` key separately with a recover, and expect that case to be rewritten once the panic becomes an error. `cmd/app/main.go` hands `os.Args[1:]` straight to `Run`, so each of these is reachable from the command line.

### Acceptance criteria

- [ ] `internal/dispatch/dispatch_test.go` covers the empty-args, unknown-command and registered-command paths.
- [ ] The unknown-command case asserts the offending name appears in the returned error.
- [ ] `go test ./internal/dispatch/...` passes.

## legacy dispatch command panics with not-implemented stub

```yaml
status: pending
slug: legacy-dispatch-command-panics-with-not-implemented-stub
fingerprint: a9f954d154719182
tier: A
priority: 6.2
family: half-finished
category: half-finished
debt_type: code
type_id: TD-22
severity: 4
effort: S
diff: NEW
```

### Proof

main.go:25 calls dispatch.Run(os.Args[1:]) directly, so running the binary with argument 'legacy' reaches handlers["legacy"] (dispatch.go:11) -> legacyHandler (dispatch.go:30-32), which unconditionally panics. This is a live CLI command table, not an abstract interface stub, and crashes the whole process instead of returning an error like its sibling handlers.

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

`legacyHandler` in `internal/dispatch/dispatch.go` panics, and the `handlers` map puts it one command-line argument away from any user, beside `start`, `stop` and `status`. Make it behave like its siblings: either return a plain error saying the command was withdrawn, or drop the `legacy` key so `Run` produces its own unknown-command error. Prefer dropping the key unless the name has to stay recognised for compatibility. Whichever way it goes, the process must exit on a message rather than a stack trace, and the dispatch tests must cover the argument.

### Acceptance criteria

- [ ] Running the binary with the `legacy` argument exits with an error rather than a panic.
- [ ] No panic remains in `internal/dispatch/dispatch.go`.
- [ ] A test covers the `legacy` argument path.

## TLS certificate verification disabled process-wide, invoked at startup

```yaml
status: pending
slug: tls-certificate-verification-disabled-process-wide-invoked-at-st
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

httpc.go:13 sets http.DefaultTransport.(*http.Transport).TLSClientConfig = &tls.Config{InsecureSkipVerify: true} unconditionally inside Fetch. main.go:28 calls httpc.Fetch("https://example.com/health") unconditionally at startup with no build/env guard, and no other call site exists. Because DefaultTransport is a package-level global, this disables TLS verification for the whole process for its remaining lifetime, affecting any other code using http.DefaultTransport. This is a live, real, unguarded security defect.

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

- `cmd/app/main.go:28-28`

```
_ = httpc.Fetch("https://example.com/health")
```

### Signals

- hotspot score 2.0, churn 1, coupling pairs 0, fan-in 1 (approximate)
- confirmed by: hotspot, pattern:credential, pattern:tls-disabled, satd, scout:security

### Remediation

`Fetch` in `internal/httpc/httpc.go` disables certificate verification by reassigning the TLS config on `http.DefaultTransport`, and `cmd/app/main.go` calls it unconditionally at startup, so every later HTTPS call in the process inherits it. Shrink the blast radius first: stop touching `DefaultTransport` and use the package-level client already declared in `internal/httpc/httpc_safe.go`. Then remove the skip-verify setting outright, since the health-check host is a public HTTPS endpoint needing no exemption. Move the hard-coded API token constant in the same file into configuration.

### Acceptance criteria

- [ ] Nothing under `internal/httpc` assigns to `http.DefaultTransport`.
- [ ] Certificate verification is never disabled anywhere in the repository.
- [ ] The API token literal is gone from `internal/httpc/httpc.go` and read from the environment instead.

## 290-entry path table duplicates the fallback path formula it sits beside

```yaml
status: pending
slug: f-290-entry-path-table-duplicates-the-fallback-path-formula-it-s
fingerprint: bf52c33dda8e609a
tier: B
priority: 5.25
family: duplication
category: duplication
debt_type: code
type_id: TD-05
severity: 3
effort: S
diff: NEW
```

### Proof

Read full paths map (lines 12-302): all 290 entries are 'nXXX': 'data/nXXX.json', exactly matching the fallback formula at line 8. No entry deviates from the pattern, so the map is not an override table with exceptions — it is pure duplication of the fallback logic, expressed as 290 literals that must be kept in sync with the format string if the scheme changes. store.go:18 (Open) calls lookup.PathFor but relies on neither the map's presence nor any special-cased value. A generated loop or removal of the map (letting the fallback handle all cases) would be strictly simpler.

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

- `internal/lookup/lookup.go:12-17`

```
	"n001": "data/n001.json",
	"n002": "data/n002.json",
	"n003": "data/n003.json",
	"n004": "data/n004.json",
	"n005": "data/n005.json",
	"n006": "data/n006.json",
```

### Signals

- hotspot score 50.0, churn 1, coupling pairs 0, fan-in 1 (approximate)
- confirmed by: hotspot, scout:duplication

### Remediation

Every one of the 290 entries in the `paths` map in `internal/lookup/lookup.go` is the same string the fallback in `PathFor` already builds, so the table adds nothing but a second place to keep the naming scheme. Confirm that once mechanically, by generating the fallback string for each key and diffing, so no exception hiding mid-table is lost. Then delete the map and let `PathFor` compute every path. Check `internal/store/store.go`, the only caller, for anything that depends on a lookup hit rather than the fallback.

### Acceptance criteria

- [ ] The `paths` map is gone from `internal/lookup/lookup.go` and `PathFor` computes the path for every name.
- [ ] A test asserts `PathFor` returns the same string for a name that was in the old table and for one that never was.
- [ ] `internal/store/store.go` resolves the same paths for existing store names as before.

## Fetch has no timeout and can hang forever on health check

```yaml
status: pending
slug: fetch-has-no-timeout-and-can-hang-forever-on-health-check
fingerprint: 45d73ee57cd37a54
tier: A
priority: 4.62
family: half-finished
category: half-finished
debt_type: code
type_id: TD-28
severity: 3
effort: S
diff: NEW
```

### Proof

Fetch (httpc.go:12-21) carries a Deprecated comment (line 11) pointing at FetchWithTimeout (httpc_safe.go:10-17), but main.go:28 still calls httpc.Fetch, not the replacement. Grep confirms FetchWithTimeout has zero call sites anywhere in the repo. The migration was never completed; no ticket reference exists in the comment.

### Evidence

- `internal/httpc/httpc.go:11-11`

```
// Deprecated: use FetchWithTimeout from httpc_safe.go.
```

- `cmd/app/main.go:28-28`

```
	_ = httpc.Fetch("https://example.com/health")
```

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

### Signals

- hotspot score 2.0, churn 1, coupling pairs 0, fan-in 1 (approximate)
- confirmed by: hotspot, pattern:no-timeout, satd, scout:half-finished

### Remediation

The replacement already exists: `FetchWithTimeout` in `internal/httpc/httpc_safe.go` has a bounded client and no callers, and the deprecation comment on `Fetch` points straight at it. Finish the migration. Switch the startup health check in `cmd/app/main.go` to `FetchWithTimeout` and handle the status code and error it returns instead of discarding the result, then delete `Fetch` and its deprecation comment once that call site is gone. Doing this also retires the skip-verify assignment, which lives inside `Fetch`.

### Acceptance criteria

- [ ] `cmd/app/main.go` calls `FetchWithTimeout` and does not discard its error.
- [ ] `Fetch` is deleted from `internal/httpc/httpc.go`, or gains a timeout and a documented caller.
- [ ] The startup health check cannot block for longer than the client timeout.

# Below the cut

## httpc.Fetch swallows both request and body-read errors, returning empty string

```yaml
status: pending
slug: httpc-fetch-swallows-both-request-and-body-read-errors-returning
fingerprint: d887ca1f61883449
tier: A
priority: 4.62
family: error-masking
category: error-masking
debt_type: code
type_id: TD-13
severity: 3
effort: S
diff: NEW
```

### Proof

Fetch (httpc.go:14-20) returns "" on both http.Get error (line 15-17) and io.ReadAll error (line 19, err discarded via `_`), with no logging in either path. The sole caller, main.go:28, does `_ = httpc.Fetch(...)`, discarding the return value entirely. A failed health check (network error, read error, or a real empty body) is indistinguishable and produces no observable signal anywhere in the process.

### Evidence

- `internal/httpc/httpc.go:14-20`

```
resp, err := http.Get(url)
	if err != nil {
		return ""
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	return string(body)
```

## Two overlapping HTTP fetch implementations in httpc package

```yaml
status: pending
slug: two-overlapping-http-fetch-implementations-in-httpc-package
fingerprint: 8f91af0854095dec
tier: B
priority: 3.234
family: duplication
category: duplication
debt_type: code
type_id: TD-05
severity: 3
effort: S
diff: NEW
```

### Proof

Fetch (httpc.go:12-17) and FetchWithTimeout (httpc_safe.go:10-15) both implement GET-then-handle-response against a URL parameter, with divergent behavior (string body vs status code, no timeout vs 5s timeout, TLS bypass vs none). main.go:28 calls only Fetch; FetchWithTimeout is uncalled anywhere. Both bodies are live source (not fixture/generated/vendored), so they are duplicate/overlapping implementations that could drift.

### Evidence

- `internal/httpc/httpc.go:12-17`

```
func Fetch(url string) string {
	http.DefaultTransport.(*http.Transport).TLSClientConfig = &tls.Config{InsecureSkipVerify: true}
	resp, err := http.Get(url)
	if err != nil {
		return ""
	}
```

- `internal/httpc/httpc_safe.go:10-15`

```
func FetchWithTimeout(url string) (int, error) {
	resp, err := client.Get(url)
	if err != nil {
		return 0, err
	}
	defer resp.Body.Close()
```

## store_test.go asserts execution, not behaviour, for Load; Find is untested

```yaml
status: pending
slug: store-test-go-asserts-execution-not-behaviour-for-load-find-is-u
fingerprint: b6586e999c0e6bdd
tier: A
priority: 3.084
family: test-gaps
category: test-gaps
debt_type: test
type_id: TD-04
severity: 4
effort: M
diff: NEW
```

### Proof

TestLoadSmoke (store_test.go:14-17) discards Load's return with `_ =`, never checking parsed map contents or the swallowed-unmarshal-error path (store.go:31-33, fmt.Println only). Find (store.go:37-39) has zero test coverage and concatenates `id` directly into a SQL string, an untested injection-prone path. Glob of internal/store shows only this one test file, and repo-wide grep found no other callers/tests referencing Find or Load, so the gap is real, not just unmapped naming.

### Evidence

- `internal/store/store_test.go:14-17`

```
func TestLoadSmoke(t *testing.T) {
	time.Sleep(10 * time.Millisecond)
	_ = (&Store{path: "x"}).Load("k")
}
```

- `internal/store/store.go:25-39`

```
func (s *Store) Load(key string) map[string]string {
	raw, err := os.ReadFile(s.path)
	if err != nil {
		return nil
	}
	out := map[string]string{}
	if err := json.Unmarshal(raw, &out); err != nil {
		fmt.Println("store: unmarshal failed")
	}
	return out
}

func (s *Store) Find(id string) (*sql.Rows, error) {
	return s.db.Query("SELECT * FROM items WHERE id = '" + id + "'")
}
```

## Runbook describes kill switch as operational control; code only logs

```yaml
status: pending
slug: runbook-describes-kill-switch-as-operational-control-code-only-l
fingerprint: 5be87c92ab0d4b6b
tier: B
priority: 2.8
family: doc-drift
category: doc-drift
debt_type: documentation
type_id: TD-08
severity: 4
effort: S
diff: NEW
```

### Proof

docs/runbook.md:5-7 tells on-call the flag 'stops payments' and is a permanent operational control not to be removed. flags.go:5-6 comment repeats the same operational framing. But main.go:22-24 is the only reader of the flag anywhere in the repo (confirmed by grep for IsEnabled/flags. usage) and it only does log.Println — a repo-wide search found no payment-processing code for it to gate, so the doc's operational claim is unsupported by the code.

### Evidence

- `docs/runbook.md:5-7`

```
`payments.killswitch` in `internal/flags/flags.go` is a permanent operational
kill switch. It is off in normal operation and is flipped by on-call during an
incident; do not remove it as dead code.
```

- `cmd/app/main.go:22-24`

```
if flags.IsEnabled("payments.killswitch") {
		log.Println("payments disabled by kill switch")
	}
```

## stdout write in store library instead of the app's logger

```yaml
status: pending
slug: stdout-write-in-store-library-instead-of-the-app-s-logger
fingerprint: c3cf7df573a74091
tier: B
priority: 2.338
family: pipeline-infra
category: pipeline-infra
debt_type: infrastructure
type_id: null
severity: 2
effort: S
diff: NEW
```

### Proof

main.go uses the standard log package throughout (log.Printf line 18, log.Println line 23, log.Fatal line 26), while store.go:32 uses fmt.Println directly inside library code, confirming the described inconsistency — it cannot be leveled, redirected, or captured via the app's log configuration. Note: Load's only caller found is store_test.go:16 (a discarded smoke-test call), so the write is not currently hit in production traffic, but the pattern itself (library bypassing the app's logging convention) is real and would surface as soon as Load is exercised.

### Evidence

- `internal/store/store.go:31-33`

```
if err := json.Unmarshal(raw, &out); err != nil {
		fmt.Println("store: unmarshal failed")
	}
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

## No CI/CD automation to build, push, or deploy the Docker/k8s artifacts

```yaml
status: pending
slug: no-ci-cd-automation-to-build-push-or-deploy-the-docker-k8s-artif
fingerprint: 67a7969de9b64d00
tier: B
priority: 1.575
family: pipeline-infra
category: pipeline-infra
debt_type: build
type_id: null
severity: 3
effort: M
diff: NEW
```

### Proof

Dockerfile exists at repo root and k8s/deployment.yaml + k8s/service.yaml exist, but ci.yml:1-16 only checks out code, sets up Go, and runs `go test ./...`. No job builds/pushes an image or applies k8s manifests. README.md (3 lines) and docs/runbook.md (kill-switch only) do not mention any deploy process, so release is undocumented and manual.

### Evidence

- `.github/workflows/ci.yml:11-16`

```
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: "1.22"
          cache: true
      - run: go test ./...
```

- `k8s/deployment.yaml:9-10`

```
        - name: app
          image: example/app:latest
```

## Release process gaps

```yaml
status: pending
slug: release-process-gaps
fingerprint: f389a33ddc209bae
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
branch staging unmerged, last commit 2026-03-09 (179 days ago)
```

## Sleep in test with no async work to wait on

```yaml
status: pending
slug: sleep-in-test-with-no-async-work-to-wait-on
fingerprint: 545f2bc5cc2e6fef
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

Load() (store.go:25-35) is pure synchronous file I/O with no goroutine, channel, or timer involved. TestLoadSmoke (store_test.go:14-17) sleeps 10ms before calling it and asserts nothing on the result (`_ =`). There is no async work the sleep could be waiting on, so it is dead latency that only risks flakiness under load, matching the sleep/assert-free pattern exactly.

### Evidence

- `internal/store/store_test.go:14-16`

```
func TestLoadSmoke(t *testing.T) {
	time.Sleep(10 * time.Millisecond)
	_ = (&Store{path: "x"}).Load("k")
```

- `internal/store/store_test.go:14-17`

```
func TestLoadSmoke(t *testing.T) {
	time.Sleep(10 * time.Millisecond)
	_ = (&Store{path: "x"}).Load("k")
}
```

## No CHANGELOG or CONTRIBUTING despite two tagged releases

```yaml
status: pending
slug: no-changelog-or-contributing-despite-two-tagged-releases
fingerprint: 7184d41860800e6d
tier: B
priority: 1.4
family: doc-drift
category: doc-drift
debt_type: documentation
type_id: TD-08
severity: 2
effort: S
diff: NEW
```

### Proof

README.md is 3 lines with no changelog/contributing pointers; globs for CHANGELOG* and CONTRIBUTING* return no files. Two tags exist (v0.1.0 at 1b1cd9e, v0.2.0 at b57194e) per commit log, including notable changes like the builder TLS option (b57194e) and kill switch (1b1cd9e), with no ADR or changelog capturing why.

### Evidence

- `README.md:1-3`

```
# app

Go service with a lookup table, a string dispatcher and a fluent builder.
```

- `.git/refs/tags/v0.1.0:1-1`

```
1b1cd9e60605710db13483c7c69f885d9240a430
```

- `.git/refs/tags/v0.2.0:1-1`

```
b57194e67971162f69e19cefd83afe453f8214d6
```

## go.sum lists a module absent from go.mod requires

```yaml
status: pending
slug: go-sum-lists-a-module-absent-from-go-mod-requires
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

go.mod (lines 1-3) has no require block at all; go.sum (line 1) records github.com/example/dep v1.2.0. Grep for 'github.com/example/dep' across the repo returns only the go.sum line itself, confirming it is unreferenced by any import. This is a genuine manifest/lockfile mismatch, not a monorepo split or migration artifact (single-module repo, 11 Go files total).

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
| payments-kill-switch-has-no-test-verifying-it-changes-behaviour | test-gaps | internal/flags/flags.go | unverified |
| f-290-entry-lookup-table-is-fully-redundant-with-its-own-fallbac | dead-code | internal/lookup/lookup.go | confirm |
| deprecated-but-still-called-httpc-fetch-path-has-no-test | test-gaps | internal/httpc/httpc.go | unverified |
| deprecated-httpc-fetch-still-called-instead-of-fetchwithtimeout | migration | internal/httpc/httpc.go | unverified |
| store-load-logs-unmarshal-failure-without-the-cause-and-returns | error-masking | internal/store/store.go | downgrade |
| string-concatenated-sql-query-on-exported-store-method | security | internal/store/store.go | downgrade |
| internal-shell-package-is-entirely-unimported | dead-code | internal/shell/run.go | confirm |
| shell-out-via-sh-c-with-unenforced-trust-assumption-and-suppress | security | internal/shell/run.go | downgrade |
| crypto-fingerprint-has-no-callers-anywhere-in-the-repository | dead-code | internal/crypto/hash.go | confirm |

# Considered and rejected

- **legacyHandler is reachable only to unconditionally panic** - `internal/dispatch/dispatch.go` - Entry point, script run by name, or runner-discovered test?
- **Deprecated Fetch is still the live call site instead of its replacement** - `internal/httpc/httpc.go` - scout:dead-code mislabels an actively-called function as dead while missing the actually-unused FetchWithTimeout
- **Builder.WithTLS and Config.TLS are set up but never consumed** - `internal/build/builder.go` - golden trap: intentional fixture

# Looks bad but is fine

- `internal/lookup/lookup.go:11` - 290-entry map literal inflates lookup.go's hotspot score and line count, but it is a flat, cohesive lookup table with no branching or nesting — not a complex unit.
- `internal/lookup/lookup.go:1` - 302 lines and highest hotspot score in the repo, but it is one function (PathFor) plus a single static map literal of 290 name-to-path entries. One responsibility, no field clustering, no fan-out to other units — a data table, not a god-class.
- `internal/build/builder.go:9` - Fluent builder pattern (WithName/WithPort/WithTLS/Build chained on *Builder) is wide by design per the family's own trap list, not a god-class.
- `internal/dispatch/dispatch.go:26` - start/stop/status/legacyHandler are trivial same-shaped stub functions but each represents a distinct command with its own reason to change; not duplication.
- `internal/flags/flags.go:5` - payments.killswitch is documented in flags.go and docs/runbook.md as a permanent, deliberately always-false-in-normal-operation kill switch flipped by on-call during incidents; it is not a stale single-value flag.
- `internal/dispatch/dispatch.go:30` - legacyHandler panics with 'not implemented' rather than swallowing an error; a panic surfaces loudly rather than masking failure, so it is not error-masking even though it looks abrupt.
- `cmd/app/main.go:25` - dispatch.Run's error is checked and passed to log.Fatal, which preserves the cause and halts the process; this is a proper process-boundary handling, not masking.
- `internal/lookup/lookup.go:11` - The high hotspot score is driven by a 290-entry static data map (lines 11-302), not by logic. The one real branch in PathFor (lines 4-9) is a trivial fallback string concat; this is glue/config data per the stated trap, not a meaningful test gap.
- `internal/build/builder.go:9` - Fluent builder with only field assignment, no branching or error paths; flagged for untested_change_share=0.5 but is glue/config code the trap says doesn't need unit tests.
- `internal/flags/flags.go:4` - payments.killswitch is a documented, ticketed (runbook-referenced) deliberate deferral toggle, not an unfinished stub.
- `internal/build/builder.go:1` - Builder pattern with chained With* methods is a complete, intentional API, not a half-finished contract.
- `docker-compose.dev.yml:1` - Separate dev compose file alongside docker-compose.yml looks like a dual-manifest, but it is a standard dev-override pattern (different services: mailhog vs redis), not an old/new pair replacing each other.
- `internal/dispatch/dispatch.go:11` - A 'legacy' handler key maps to a panicking legacyHandler, but no code calls it and no working replacement command supersedes it, so it does not show the old-vs-new coexistence pattern this family targets.
- `internal/httpc/httpc.go:1` - Two files (httpc.go, httpc_safe.go) in the same package both wrap net/http, but both use the Go standard library only — no duplicate third-party HTTP client dependency is involved, so this is out of scope for dependency-debt.
- `Dockerfile:1` - golang:1.22 base image matches go.mod's `go 1.22` and CI's go-version 1.22 — no runtime-version disagreement.
- `README.md:1` - Flagged as 533 days stale, but its generic description (lookup table, string dispatcher, fluent builder) still accurately matches internal/lookup, internal/dispatch and internal/build as currently written; no contradicting claim found.
- `docs/runbook.md:1` - Flagged as 272 days stale, but the flag name, file path, and default value it documents (internal/flags/flags.go, payments.killswitch=false) still match the code exactly.
- `internal/lookup/lookup.go:11` - 290-entry hardcoded map scores as a hotspot and is depended on by store, which could look like an unstable god-file many components rely on, but it has exactly one consumer (internal/store/store.go) and the map's values are identical to the function's own fallback pattern 'data/'+name+'.json', so there is no fan-out coupling risk despite the size.
- `cmd/app/main.go:7` - main.go imports five internal packages (build, dispatch, flags, httpc, store), which looks like a coupled hub, but this is the composition root of a single small binary, not a shared library being fanned out to multiple consumers, so high import count here is expected.
- `internal/crypto/hash.go:9` - md5 use has no discoverable caller in the repo; per family rules a weak hash used only for a cache key or checksum is not reportable, and no evidence contradicts that reading.
- `internal/store/store_test.go:8` - if _, err := Open("missing"); err == nil { t.Fatal(...) } is the standard idiomatic Go pattern for asserting an error occurred (no assert library available); it is a single deterministic check, not conditional logic branching test behavior on data.
- `docker-compose.dev.yml:1` - Uses postgres:latest and mailhog/mailhog:latest floating tags, but this is a dev-only compose file, which is the documented trap (expected, not debt).
- `docker-compose.yml:1` - Non-dev compose file pins postgres:16.3 and redis:7.2, so no floating-tag or dev-path-in-prod issue here.
- `internal/dispatch/dispatch.go:7` - Entry point, script run by name, or runner-discovered test?
- `internal/httpc/httpc.go:11` - scout:dead-code mislabels an actively-called function as dead while missing the actually-unused FetchWithTimeout
- `internal/build/builder.go:3` - golden trap: intentional fixture

# Open questions for the maintainer

- `internal/lookup/lookup.go:11` - Is the paths map generated from an external manifest (e.g. a build step not present in this checkout)? If so this table would be generated/fixture data and out of scope for this family.
- `internal/httpc/httpc.go:11` - Was httpc.Fetch scheduled for removal, and is main.go's continued call to it (line 28) tracked work, or an overlooked migration?
- `internal/dispatch/dispatch.go:11` - Is the "legacy" subcommand ever invoked by an external script, CI job, or operator runbook outside this repository?
- `internal/build/builder.go:17` - Was WithTLS added in anticipation of wiring TLS into main.go's builder chain, and is that wiring still pending?
- `internal/httpc/httpc.go:1` - quote not found: invented quote (golden pin)
- `internal/dispatch/dispatch.go:30` - Is legacyHandler's panic intentional (e.g. marks a retired command) or a leftover that should be tested/guarded? No test or comment clarifies intent.
- `:0` - Only one *_test.go file exists in the repo (internal/store/store_test.go); is there an external/integration/e2e suite covering cmd/app, dispatch, or lookup that isn't visible in this checkout?
- `internal/httpc/httpc.go:11` - Is there a tracked ticket or deadline for migrating main.go off httpc.Fetch to FetchWithTimeout, or was the replacement added but never wired up?
- `internal/crypto/hash.go:8` - Fingerprint() using md5 has no in-repo caller; unclear whether any future use is security-sensitive (e.g. auth token) versus a cache key/checksum, which would not be a finding.
- `internal/shell/run.go:6` - No caller of shell.Run was found in the repository; unclear whether external callers exist that could pass untrusted input, which would change severity.
- `.github/workflows/ci.yml:17` - The commented-out lint job at lines 17-20 — is this a planned addition or abandoned config? Not counted as a finding since it doesn't match the four listed symptom categories.

# Not assessed

- Families not run: none
- Tools: the tool probe lands in phase 4, so currency, end-of-life and vulnerability claims are not assessed
- Runtime-only: coverage numbers, flake confirmation, model staleness, rollout state, deploy frequency
- By design: magic literals, convention violations, and class-level metrics that need a parser
