package dispatch

import "errors"

type handler func(args []string) error

var handlers = map[string]handler{
	"start":  start,
	"stop":   stop,
	"status": status,
	"legacy": legacyHandler,
}

// Run dispatches by command name; handlers are reached only through this map.
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

func start(args []string) error  { return nil }
func stop(args []string) error   { return nil }
func status(args []string) error { return nil }

func legacyHandler(args []string) error {
	panic("not implemented")
}
