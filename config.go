package main

import (
	"encoding/json"
	"net/url"
	"os"
	"strings"
)

type PeerConfig struct {
	ID       string `json:"id"`
	Endpoint string `json:"endpoint"`
}

type Config struct {
	Listen  string           `json:"listen"`
	Peers   []PeerConfig     `json:"peers"`
	Buckets map[string]int64 `json:"buckets"`
}

func loadConfig(path string) *Config {
	data := throw2(chaosCall2("read config", func() ([]byte, error) {
		return os.ReadFile(path)
	}))

	cfg := &Config{}

	throw(chaosCall("decode config", func() error {
		return json.Unmarshal(data, cfg)
	}))

	cfg.validate()

	return cfg
}

func (c *Config) validate() {
	if c.Listen == "" {
		throwFmt("listen is required")
	}

	if len(c.Peers) == 0 {
		throwFmt("at least one peer is required")
	}

	ids := map[string]bool{}
	endpoints := map[string]bool{}

	for i := range c.Peers {
		peer := &c.Peers[i]

		if peer.ID == "" {
			throwFmt("peer id is required")
		}

		if ids[peer.ID] {
			throwFmt("duplicate peer id %q", peer.ID)
		}

		parsed := throw2(chaosCall2("parse endpoint", func() (*url.URL, error) {
			return url.Parse(peer.Endpoint)
		}))

		if (parsed.Scheme != "http" && parsed.Scheme != "https") || parsed.Host == "" {
			throwFmt("bad endpoint %q", peer.Endpoint)
		}

		if (parsed.Path != "" && parsed.Path != "/") || parsed.RawQuery != "" || parsed.Fragment != "" {
			throwFmt("endpoint must not contain a path, query, or fragment: %q", peer.Endpoint)
		}

		peer.Endpoint = strings.TrimRight(peer.Endpoint, "/")

		if endpoints[peer.Endpoint] {
			throwFmt("duplicate peer endpoint %q", peer.Endpoint)
		}

		ids[peer.ID] = true
		endpoints[peer.Endpoint] = true
	}

	if len(c.Buckets) == 0 {
		throwFmt("at least one bucket is required")
	}

	for name, size := range c.Buckets {
		if name == "" || strings.Contains(name, "/") {
			throwFmt("bad bucket name %q", name)
		}

		if size <= 0 {
			throwFmt("bucket %q size must be positive", name)
		}
	}
}
