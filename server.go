package main

import (
	"errors"
	"io"
	"log/slog"
	"net/http"
)

type Node struct {
	store  *Store
	peers  []PeerConfig
	client *http.Client
	log    *slog.Logger
}

func newNode(cfg *Config, log *slog.Logger) *Node {
	return &Node{
		store:  newStore(cfg.Buckets),
		peers:  cfg.Peers,
		client: newHTTPClient(),
		log:    log,
	}
}

func (n *Node) handler() http.Handler {
	mux := http.NewServeMux()

	mux.HandleFunc("GET /v1/{bucket}/get", n.guard(n.externalGet))
	mux.HandleFunc("PUT /v1/{bucket}/put", n.guard(n.externalPut))
	mux.HandleFunc("GET /{bucket}/get", n.guard(n.internalGet))
	mux.HandleFunc("PUT /{bucket}/put", n.guard(n.internalPut))

	return mux
}

func (n *Node) guard(cb http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, request *http.Request) {
		try(func() {
			cb(w, request)
		}).catch(func(err *Exception) {
			var httpErr *HTTPException

			if errors.As(err.asError(), &httpErr) {
				httpErr.write(w)

				return
			}

			n.log.Error("request failed", "err", err)
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

func (n *Node) externalGet(w http.ResponseWriter, request *http.Request) {
	key := requestKey(request)
	bucket := request.PathValue("bucket")
	status, body := forward(n.client, request.Context(), n.peers, http.MethodGet, bucket, "get", key, nil)

	writeResult(w, status, body)
}

func (n *Node) externalPut(w http.ResponseWriter, request *http.Request) {
	key := requestKey(request)
	value := throw2(io.ReadAll(request.Body))
	bucket := request.PathValue("bucket")
	status, body := forward(n.client, request.Context(), n.peers, http.MethodPut, bucket, "put", key, value)

	writeResult(w, status, body)
}

func (n *Node) internalGet(w http.ResponseWriter, request *http.Request) {
	key := requestKey(request)
	bucket := n.store.bucket(request.PathValue("bucket"))

	if bucket == nil {
		throwHTTP(http.StatusNotFound, "")
	}

	value, found := bucket.get(key)

	if !found {
		throwHTTP(http.StatusNotFound, "")
	}

	writeResult(w, http.StatusOK, value)
}

func (n *Node) internalPut(w http.ResponseWriter, request *http.Request) {
	key := requestKey(request)
	bucket := n.store.bucket(request.PathValue("bucket"))

	if bucket == nil {
		throwHTTP(http.StatusNotFound, "")
	}

	value := throw2(io.ReadAll(request.Body))

	if !bucket.put(key, value) {
		throwHTTP(http.StatusRequestEntityTooLarge, "")
	}

	w.WriteHeader(http.StatusNoContent)
}

func writeResult(w http.ResponseWriter, status int, body []byte) {
	if status >= http.StatusBadRequest {
		throwHTTP(status, "")
	}

	if status == http.StatusOK {
		w.Header().Set("Content-Type", "application/octet-stream")
	}

	w.WriteHeader(status)

	if len(body) != 0 {
		_, _ = w.Write(body)
	}
}
