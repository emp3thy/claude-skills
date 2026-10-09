package cli

import "flag"

// Run parses the command line options and returns an exit code.
func Run(args []string) int {
	fs := flag.NewFlagSet("drift", flag.ContinueOnError)
	if err := fs.Parse(args); err != nil {
		return 2
	}
	return 0
}
