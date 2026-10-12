package cli

import "os"

// Home is the directory drift keeps its state in.
func Home() string {
	if dir := os.Getenv("DRIFT_HOME"); dir != "" {
		return dir
	}
	return ".drift"
}
