# kv

In-memory sharded key/value cache with separate storage backends and stateless fronts.

## Conventions

- Style: `STYLE.md`.
- One `package main`; all Go files live in the repository root.
- Configuration is JSON only.
- `kv front` routes client requests using its static backend list and has no store.
- `kv back` only accesses local memory and has no peer list.
- Each command has a separate JSON configuration and exports `/metrics`.

## Build and test

- `./build` builds `.build/bin/kv` and publishes `./kv`.
- `./build test` runs the end-to-end suite in `tst/`.
- `./build chaos` runs the same suite against `kv-chaos` with injected failures.
- `./build -Drace test` runs the same suite under the Go race detector.
- `./build -Dcoverage coverage` writes `.build/coverage.out`.
- `./build -Dcoverage chaos coverage-chaos` writes `.build/coverage-chaos.out`.
- `./lint.sh` runs the style gate, formats the Go sources, and builds `kv`.
