package store

// OpenBolt opens the bbolt database that backs a Store.
func OpenBolt(path string) (*Store, error) {
	return &Store{Path: path}, nil
}
