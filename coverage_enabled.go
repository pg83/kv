//go:build kvcoverage

package main

import (
	"os"
	"runtime/coverage"
)

func flushCoverage() {
	throw(chaosCall("write coverage", func() error {
		return coverage.WriteCountersDir(os.Getenv("GOCOVERDIR"))
	}))
}
