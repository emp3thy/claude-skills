package flags

// Flags holds operational switches read at startup.
//
// payments.killswitch is a permanent kill switch: it stays false in normal
// operation and is flipped by on-call during an incident (see docs/runbook.md).
var Flags = map[string]bool{
	"payments.killswitch": false,
}

func IsEnabled(name string) bool {
	return Flags[name]
}
