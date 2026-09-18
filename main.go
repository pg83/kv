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
		case "front", "back":
			armChaos()

			fs := flag.NewFlagSet(args[1], flag.ContinueOnError)
			config := fs.String("c", "", "config file")

			throw(chaosCall("parse flags", func() error {
				return fs.Parse(args[2:])
			}))

			if args[1] == "back" {
				cfg := &BackConfig{}

				loadConfig(*config, cfg)
				cfg.validate()
				runServer(cfg.Listen, newBack(cfg, log).handler(), log)
			} else {
				cfg := &FrontConfig{}

				loadConfig(*config, cfg)
				cfg.validate()
				runServer(cfg.Listen, newFront(cfg, log).handler(), log)
			}
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

func runServer(addresses ListenAddresses, handler http.Handler, log *slog.Logger) {
	server := &http.Server{Handler: handler}
	listeners := make([]net.Listener, 0, len(addresses))

	for _, address := range addresses {
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
		return os.Stderr.WriteString("Usage: kv back -c back.json | kv front -c front.json\n")
	}))
}
