package store

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"os"

	"example.com/app/internal/lookup"
)

type Store struct {
	path string
	db   *sql.DB
}

func Open(name string) (*Store, error) {
	path := lookup.PathFor(name)
	if _, err := os.Stat(path); err != nil {
		return nil, err
	}
	return &Store{path: path}, nil
}

func (s *Store) Load(key string) map[string]string {
	raw, err := os.ReadFile(s.path)
	if err != nil {
		return nil
	}
	out := map[string]string{}
	if err := json.Unmarshal(raw, &out); err != nil {
		fmt.Println("store: unmarshal failed")
	}
	return out
}

func (s *Store) Find(id string) (*sql.Rows, error) {
	return s.db.Query("SELECT * FROM items WHERE id = '" + id + "'")
}

func (s *Store) Close() {}
