# Runbook

## Kill switch

`payments.killswitch` in `internal/flags/flags.go` is a permanent operational
kill switch. It is off in normal operation and is flipped by on-call during an
incident; do not remove it as dead code.
