package main

import (
	"errors"
	"io"
	"log/slog"
	"net/http"
)

type Server struct {
	log     *slog.Logger
	metrics *Metrics
}

func newServer(log *slog.Logger) *Server {
	return &Server{
		log:     log,
		metrics: newMetrics(),
	}
}

func (s *Server) mux(store *Store) *http.ServeMux {
	mux := http.NewServeMux()

	mux.HandleFunc("GET /metrics", s.guard(func(w http.ResponseWriter, request *http.Request) {
		s.metrics.serve(w, store)
	}))

	return mux
}

func (s *Server) guard(cb http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, request *http.Request) {
		try(func() {
			cb(w, request)
		}).catch(func(err *Exception) {
			var httpErr *HTTPException

			if errors.As(err.asError(), &httpErr) {
				httpErr.write(w)

				return
			}

			s.log.Error("request failed", "err", err)
			newHTTPException(http.StatusInternalServerError, "").write(w)
		})
	}
}

func requestKey(request *http.Request) string {
	values, found := request.URL.Query()["key"]

	if !found || len(values) != 1 {
		throwHTTP(http.StatusBadRequest, "one key parameter is required")
	}

	return values[0]
}

func writeResult(w http.ResponseWriter, status int, body []byte) {
	if status >= http.StatusBadRequest {
		throwHTTP(status, "")
	}

	if status == http.StatusOK {
		w.Header().Set("Content-Type", "application/octet-stream")
	}

	writeHeader(w, status)

	if len(body) != 0 {
		_, _ = chaosCall2("write response", func() (int, error) {
			return w.Write(body)
		})
	}
}

func readRequest(request *http.Request) []byte {
	return throw2(chaosCall2("read request", func() ([]byte, error) {
		return io.ReadAll(request.Body)
	}))
}

func writeHeader(w http.ResponseWriter, status int) {
	throw(chaosCall("write header", func() error {
		w.WriteHeader(status)

		return nil
	}))
}
