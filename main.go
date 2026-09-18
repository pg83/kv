package main

import (
	"errors"
	"flag"
	"log/slog"
	"net"
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
	server := &http.Server{Handler: node.handler()}
	listeners := make([]net.Listener, 0, len(cfg.Listen))

	for _, address := range cfg.Listen {
		listener := throw2(chaosCall2("listen", func() (net.Listener, error) {
			return net.Listen("tcp", address)
		}))

		defer listener.Close()

		listeners = append(listeners, listener)
	}

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

	results := make(chan error, len(listeners))

	for _, listener := range listeners {
		log.Info("listening", "addr", listener.Addr())

		go func() {
			try(func() {
				throw(chaosCall("serve", func() error {
					return server.Serve(listener)
				}))
			}).catch(func(err *Exception) {
				results <- err.asError()
			})
		}()
	}

	remaining := len(listeners)

	var err error

	select {
	case <-signals:
	case err = <-results:
		remaining--
	}

	closeErr := chaosCall("close server", server.Close)

	_ = server.Close()

	for range remaining {
		serveErr := <-results

		if !errors.Is(serveErr, http.ErrServerClosed) {
			err = serveErr
		}
	}

	throw(errors.Join(err, closeErr))
}

func printUsage() {
	throw2(chaosCall2("write stderr", func() (int, error) {
		return os.Stderr.WriteString("Usage: kv run -c config.json\n")
	}))
}
