# kv

In-memory sharded key/value cache with three static peers and a per-bucket LRU.

## Conventions

- Style: `STYLE.md`.
- One `package main`; all Go files live in the repository root.
- Configuration is JSON only.
- External handlers route; internal handlers only access local memory.

## Build and test

- `./build` builds `.build/bin/kv` and publishes `./kv`.
- `./build test` runs the end-to-end suite in `tst/`.
- `./build chaos` runs the same suite against `kv-chaos` with injected failures.
- `./build -Drace test` runs the same suite under the Go race detector.
- `./build -Dcoverage coverage` writes `.build/coverage.out`.
- `./build -Dcoverage chaos coverage-chaos` writes `.build/coverage-chaos.out`.
- `./lint.sh` runs the style gate, formats the Go sources, and builds `kv`.
