package main

import (
	"log/slog"
	"net/http"
)

type Front struct {
	*Server
	peers  []PeerConfig
	client *http.Client
}

func newFront(cfg *FrontConfig, log *slog.Logger) *Front {
	return &Front{Server: newServer(log), peers: cfg.Peers, client: newHTTPClient()}
}

func (f *Front) handler() http.Handler {
	mux := f.mux(nil)

	mux.HandleFunc("GET /v1/{bucket}/get", f.metrics.track("external", "get", f.guard(f.get)))
	mux.HandleFunc("PUT /v1/{bucket}/put", f.metrics.track("external", "put", f.guard(f.put)))

	return mux
}

func (f *Front) get(w http.ResponseWriter, request *http.Request) {
	key := requestKey(request)
	bucket := request.PathValue("bucket")
	status, body := forward(f.client, request.Context(), f.peers, http.MethodGet, bucket, "get", key, nil)

	writeResult(w, status, body)
}

func (f *Front) put(w http.ResponseWriter, request *http.Request) {
	key := requestKey(request)
	value := readRequest(request)
	bucket := request.PathValue("bucket")
	status, body := forward(f.client, request.Context(), f.peers, http.MethodPut, bucket, "put", key, value)

	writeResult(w, status, body)
}
