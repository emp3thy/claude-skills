package store

import (
	"testing"
	"time"
)

func TestOpenMissing(t *testing.T) {
	if _, err := Open("missing"); err == nil {
		t.Fatal("expected error")
	}
}

func TestLoadSmoke(t *testing.T) {
	time.Sleep(10 * time.Millisecond)
	_ = (&Store{path: "x"}).Load("k")
}
