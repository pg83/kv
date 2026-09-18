package main

import (
	"context"
	"errors"
	"flag"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
)

func main() {
	defer flushCoverage()

	log := slog.New(slog.NewTextHandler(os.Stderr, nil))

	slog.SetDefault(log)

	if len(os.Args) < 2 {
		printUsage()
		os.Exit(1)
	}

	try(func() {
		switch os.Args[1] {
		case "run":
			fs := flag.NewFlagSet("run", flag.ExitOnError)
			config := fs.String("c", "", "config file")

			throw(fs.Parse(os.Args[2:]))
			runNode(loadConfig(*config), log)
		default:
			printUsage()
			os.Exit(1)
		}
	}).catch(func(err *Exception) {
		log.Error("error", "err", err)
		os.Exit(1)
	})
}

func runNode(cfg *Config, log *slog.Logger) {
	node := newNode(cfg, log)
	server := &http.Server{Addr: cfg.Listen, Handler: node.handler()}
	signals := make(chan os.Signal, 1)
	stopped := make(chan struct{})

	signal.Notify(signals, syscall.SIGINT, syscall.SIGTERM)

	defer signal.Stop(signals)

	go func() {
		defer close(stopped)

		try(func() {
			<-signals

			ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)

			defer cancel()

			throw(server.Shutdown(ctx))
		}).catch(func(err *Exception) {
			log.Error("shutdown failed", "err", err)
		})
	}()

	log.Info("listening", "addr", cfg.Listen)

	err := server.ListenAndServe()

	if errors.Is(err, http.ErrServerClosed) {
		<-stopped

		return
	}

	throw(err)
}

func printUsage() {
	os.Stderr.WriteString("Usage: kv run -c config.json\n")
}
