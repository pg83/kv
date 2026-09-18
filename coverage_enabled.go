//go:build kvcoverage

package main

import (
	"os"
	"runtime/coverage"
)

func flushCoverage() {
	throw(coverage.WriteCountersDir(os.Getenv("GOCOVERDIR")))
}
