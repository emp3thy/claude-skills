package main

import (
	"log"
	"os"

	"example.com/app/internal/build"
	"example.com/app/internal/dispatch"
	"example.com/app/internal/flags"
	"example.com/app/internal/httpc"
	"example.com/app/internal/store"
)

func main() {
	cfg := build.NewConfig().WithName("app").WithPort(8080).Build()
	s, err := store.Open(cfg.Name)
	if err != nil {
		log.Printf("open store: %v", err)
		os.Exit(1)
	}
	defer s.Close()
	if flags.IsEnabled("payments.killswitch") {
		log.Println("payments disabled by kill switch")
	}
	if err := dispatch.Run(os.Args[1:]); err != nil {
		log.Fatal(err)
	}
	_ = httpc.Fetch("https://example.com/health")
}
