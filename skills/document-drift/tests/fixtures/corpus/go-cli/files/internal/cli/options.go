package cli

import (
	"flag"
	"fmt"
)

const usage = "usage: drift [--output FILE] [--verbose] <repo>"

// Options holds the parsed command line.
type Options struct {
	Output  string
	Verbose bool
}

// Parse reads the command line options.
func Parse(args []string) (Options, error) {
	var opts Options
	fs := flag.NewFlagSet("drift", flag.ContinueOnError)
	fs.StringVar(&opts.Output, "output", "", "write the report to this file")
	fs.BoolVar(&opts.Verbose, "verbose", false, "print each file as it is read")
	fs.Usage = func() { fmt.Fprintln(fs.Output(), usage) }
	err := fs.Parse(args)
	return opts, err
}
