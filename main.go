package main

import (
	"errors"
	"flag"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
)

func main() {
	log := slog.New(slog.NewTextHandler(os.Stderr, nil))

	slog.SetDefault(log)
	code := run(os.Args, log)

	flushCoverage()
	os.Exit(code)
}

func run(args []string, log *slog.Logger) (code int) {
	if len(args) < 2 {
		printUsage()

		return 1
	}

	try(func() {
		switch args[1] {
		case "run":
			armChaos()

			fs := flag.NewFlagSet("run", flag.ContinueOnError)
			config := fs.String("c", "", "config file")

			throw(chaosCall("parse flags", func() error {
				return fs.Parse(args[2:])
			}))

			runNode(loadConfig(*config), log)
		default:
			printUsage()
			code = 1
		}
	}).catch(func(err *Exception) {
		log.Error("error", "err", err)
		code = 1
	})

	return code
}

func runNode(cfg *Config, log *slog.Logger) {
	node := newNode(cfg, log)
	server := &http.Server{Addr: cfg.Listen, Handler: node.handler()}
	signals := make(chan os.Signal, 1)

	throw(chaosCall("notify signals", func() error {
		signal.Notify(signals, syscall.SIGINT, syscall.SIGTERM)

		return nil
	}))

	defer func() {
		_ = chaosCall("stop signals", func() error {
			signal.Stop(signals)

			return nil
		})
	}()

	go func() {
		<-signals
		throw(chaosCall("close server", server.Close))
	}()

	log.Info("listening", "addr", cfg.Listen)

	err := chaosCall("serve", func() error {
		return server.ListenAndServe()
	})

	if errors.Is(err, http.ErrServerClosed) {
		return
	}

	throw(err)
}

func printUsage() {
	throw2(chaosCall2("write stderr", func() (int, error) {
		return os.Stderr.WriteString("Usage: kv run -c config.json\n")
	}))
}
