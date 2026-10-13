package main

import (
	"fmt"
	"os"

	"github.com/acme/drift-cli/internal/cli"
)

func main() {
	opts, err := cli.Parse(os.Args[1:])
	if err != nil {
		os.Exit(2)
	}
	fmt.Fprintln(os.Stdout, opts.Output, cli.Home())
}
