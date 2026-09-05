package shell

import "os/exec"

// Run executes a shell snippet; callers pass trusted input only.
func Run(snippet string) ([]byte, error) {
	return exec.Command("sh", "-c", snippet).CombinedOutput() //nolint:gosec
}
