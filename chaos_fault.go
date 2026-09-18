//go:build kvchaos

package main

import (
	"log/slog"
	"os"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
)

var chaosFaults = map[string]error{
	"close response": syscall.EIO,
	"close server":   syscall.EIO,
	"decode config":  syscall.EINVAL,
	"http call":      syscall.ECONNREFUSED,
	"new request":    syscall.EINVAL,
	"notify signals": syscall.EIO,
	"parse endpoint": syscall.EINVAL,
	"parse flags":    syscall.EINVAL,
	"read config":    syscall.EIO,
	"read request":   syscall.EIO,
	"read response":  syscall.EIO,
	"serve":          syscall.EADDRINUSE,
	"stop signals":   syscall.EIO,
	"write coverage": syscall.EIO,
	"write response": syscall.EPIPE,
	"write header":   syscall.EPIPE,
	"write stderr":   syscall.EIO,
}

type FaultChaos struct {
	seed     uint64
	rates    map[string]uint64
	calls    sync.Map
	announce sync.Once
}

func armChaos() {
	chaos = newFaultChaos()
}

func newFaultChaos() Chaos {
	spec := os.Getenv("KV_CHAOS")
	fault := &FaultChaos{seed: 1, rates: map[string]uint64{}}

	if seed := os.Getenv("KV_CHAOS_SEED"); seed != "" {
		fault.seed = uint64(throw2(strconv.ParseUint(seed, 10, 64)))
	}

	if spec == "" {
		return fault
	}

	for _, item := range strings.Split(spec, ",") {
		if stripped, found := strings.CutPrefix(item, "-"); found {
			delete(fault.rates, stripped)

			continue
		}

		name, rate := item, uint64(100)

		if at := strings.LastIndex(item, ":"); at >= 0 {
			name, rate = item[:at], throw2(strconv.ParseUint(item[at+1:], 10, 64))
		}

		if rate == 0 {
			throwFmt("chaos point %q needs a rate above zero", name)
		}

		if name == "all" {
			for point := range chaosFaults {
				fault.rates[point] = rate
			}

			continue
		}

		if _, found := chaosFaults[name]; !found {
			throwFmt("unknown chaos point %q", name)
		}

		fault.rates[name] = rate
	}

	return fault
}

func (c *FaultChaos) call(what string, cb func() error) error {
	rate := c.rates[what]

	if rate == 0 {
		return cb()
	}

	counter, _ := c.calls.LoadOrStore(what, &atomic.Uint64{})
	number := counter.(*atomic.Uint64).Add(1)

	c.announce.Do(func() {
		slog.Warn("chaos armed", "seed", c.seed, "points", len(c.rates))
	})

	if (number+chaosMix(c.seed, what, 0))%rate != 0 {
		return cb()
	}

	err := chaosFaults[what]

	slog.Warn("chaos", "at", what, "call", number, "err", err)

	return err
}

func chaosMix(seed uint64, what string, call uint64) uint64 {
	hash := seed ^ 14695981039346656037
	data := append([]byte(what), byte(call), byte(call>>8), byte(call>>16), byte(call>>24))

	for _, value := range data {
		hash = (hash ^ uint64(value)) * 1099511628211
	}

	return hash >> 7
}
