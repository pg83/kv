package main

import (
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
			n.log.Error("request failed", "err", err)
			http.Error(w, http.StatusText(http.StatusInternalServerError), http.StatusInternalServerError)
		})
	}
}

func requestKey(w http.ResponseWriter, request *http.Request) (string, bool) {
	values, found := request.URL.Query()["key"]

	if !found || len(values) != 1 {
		http.Error(w, "one key parameter is required", http.StatusBadRequest)

		return "", false
	}

	return values[0], true
}

func (n *Node) externalGet(w http.ResponseWriter, request *http.Request) {
	key, ok := requestKey(w, request)

	if !ok {
		return
	}

	bucket := request.PathValue("bucket")
	status, body := forward(n.client, request.Context(), n.peers, http.MethodGet, bucket, "get", key, nil)

	writeResult(w, status, body)
}

func (n *Node) externalPut(w http.ResponseWriter, request *http.Request) {
	key, ok := requestKey(w, request)

	if !ok {
		return
	}

	value := throw2(io.ReadAll(request.Body))
	bucket := request.PathValue("bucket")
	status, body := forward(n.client, request.Context(), n.peers, http.MethodPut, bucket, "put", key, value)

	writeResult(w, status, body)
}

func (n *Node) internalGet(w http.ResponseWriter, request *http.Request) {
	key, ok := requestKey(w, request)

	if !ok {
		return
	}

	bucket := n.store.bucket(request.PathValue("bucket"))

	if bucket == nil {
		http.NotFound(w, request)

		return
	}

	value, found := bucket.get(key)

	if !found {
		http.NotFound(w, request)

		return
	}

	writeResult(w, http.StatusOK, value)
}

func (n *Node) internalPut(w http.ResponseWriter, request *http.Request) {
	key, ok := requestKey(w, request)

	if !ok {
		return
	}

	bucket := n.store.bucket(request.PathValue("bucket"))

	if bucket == nil {
		http.NotFound(w, request)

		return
	}

	value := throw2(io.ReadAll(request.Body))

	if !bucket.put(key, value) {
		http.Error(w, http.StatusText(http.StatusRequestEntityTooLarge), http.StatusRequestEntityTooLarge)

		return
	}

	w.WriteHeader(http.StatusNoContent)
}

func writeResult(w http.ResponseWriter, status int, body []byte) {
	if status == http.StatusOK {
		w.Header().Set("Content-Type", "application/octet-stream")
	}

	w.WriteHeader(status)

	if len(body) != 0 {
		_, _ = w.Write(body)
	}
}
