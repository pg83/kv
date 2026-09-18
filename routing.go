package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/binary"
	"io"
	"net/http"
	"net/url"
	"sort"
	"time"
)

type RankedPeer struct {
	peer  PeerConfig
	score [sha256.Size]byte
}

func rankPeers(peers []PeerConfig, bucket string, key string) []PeerConfig {
	ranked := make([]RankedPeer, 0, len(peers))

	for _, peer := range peers {
		ranked = append(ranked, RankedPeer{
			peer:  peer,
			score: peerScore(bucket, key, peer.ID),
		})
	}

	sort.Slice(ranked, func(i int, j int) bool {
		order := bytes.Compare(ranked[i].score[:], ranked[j].score[:])

		if order == 0 {
			return ranked[i].peer.ID < ranked[j].peer.ID
		}

		return order > 0
	})

	result := make([]PeerConfig, len(ranked))

	for i := range ranked {
		result[i] = ranked[i].peer
	}

	return result
}

func peerScore(bucket string, key string, peer string) [sha256.Size]byte {
	data := make([]byte, 0, len(bucket)+len(key)+len(peer)+24)

	data = appendHashPart(data, bucket)
	data = appendHashPart(data, key)
	data = appendHashPart(data, peer)

	return sha256.Sum256(data)
}

func appendHashPart(data []byte, value string) []byte {
	data = binary.BigEndian.AppendUint64(data, uint64(len(value)))

	return append(data, value...)
}

func internalURL(peer PeerConfig, bucket string, action string, key string) string {
	query := url.Values{}

	query.Set("key", key)

	return peer.Endpoint + "/" + url.PathEscape(bucket) + "/" + action + "?" + query.Encode()
}

func forward(client *http.Client, ctx context.Context, peers []PeerConfig, method string, bucket string, action string, key string, value []byte) (int, []byte) {
	for _, peer := range rankPeers(peers, bucket, key) {
		request := throw2(http.NewRequestWithContext(ctx, method, internalURL(peer, bucket, action, key), bytes.NewReader(value)))

		if method == http.MethodPut {
			request.Header.Set("Content-Type", "application/octet-stream")
		}

		response, err := client.Do(request)

		if err != nil {
			continue
		}

		body, err := io.ReadAll(response.Body)

		response.Body.Close()

		if err != nil {
			continue
		}

		if response.StatusCode == http.StatusServiceUnavailable {
			continue
		}

		return response.StatusCode, body
	}

	return http.StatusServiceUnavailable, nil
}

func newHTTPClient() *http.Client {
	return &http.Client{Timeout: time.Second}
}
