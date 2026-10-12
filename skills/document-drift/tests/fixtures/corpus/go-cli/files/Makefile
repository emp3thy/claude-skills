.PHONY: build lint release

build:
	go build -o bin/drift ./cmd/drift

lint:
	go vet ./...

release: build
	tar -czf drift.tar.gz -C bin drift
