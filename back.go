package main

import (
	"log/slog"
	"net/http"
)

type Back struct {
	*Server
	store *Store
}

func newBack(cfg *BackConfig, log *slog.Logger) *Back {
	return &Back{Server: newServer(log), store: newStore(cfg.Buckets)}
}

func (b *Back) handler() http.Handler {
	mux := b.mux(b.store)

	mux.HandleFunc("GET /{bucket}/get", b.metrics.track("internal", "get", b.guard(b.get)))
	mux.HandleFunc("PUT /{bucket}/put", b.metrics.track("internal", "put", b.guard(b.put)))

	return mux
}

func (b *Back) get(w http.ResponseWriter, request *http.Request) {
	key := requestKey(request)
	bucket := b.store.bucket(request.PathValue("bucket"))

	if bucket == nil {
		throwHTTP(http.StatusNotFound, "")
	}

	value, found := bucket.get(key)

	if !found {
		throwHTTP(http.StatusNotFound, "")
	}

	writeResult(w, http.StatusOK, value)
}

func (b *Back) put(w http.ResponseWriter, request *http.Request) {
	key := requestKey(request)
	bucket := b.store.bucket(request.PathValue("bucket"))

	if bucket == nil {
		throwHTTP(http.StatusNotFound, "")
	}

	value := readRequest(request)

	if !bucket.put(key, value) {
		throwHTTP(http.StatusRequestEntityTooLarge, "")
	}

	writeHeader(w, http.StatusNoContent)
}
