# kv

[![CI](https://github.com/pg83/kv/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/pg83/kv/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/pg83/kv/branch/main/graph/badge.svg)](https://app.codecov.io/gh/pg83/kv/tree/main)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Small in-memory sharded key/value cache.

`kv back` stores values in a per-bucket LRU. `kv front` exposes the client API
and forwards requests using rendezvous hashing over the bucket, key, and peer
ID. Only fronts know the full backend list. Fronts keep no KV data and can be
restarted or scaled independently of storage. A failed backend is skipped;
a `404` is final. Values are neither replicated nor persisted.

## Configuration

Run storage with `kv back -c back.json`:

```json
{
  "listen": ["127.0.0.1:8062", "192.168.103.16:8062"],
  "buckets": {
    "default": 67108864
  }
}
```

Run the stateless API with `kv front -c front.json`:

```json
{
  "listen": ["127.0.0.1:8061", "192.168.100.16:8061"],
  "peers": [
    {"id": "lab1", "endpoint": "http://192.168.103.16:8062"},
    {"id": "lab2", "endpoint": "http://192.168.103.17:8062"},
    {"id": "lab3", "endpoint": "http://192.168.103.18:8062"}
  ]
}
```

Bucket capacity is local to each node and counts `len(key) + len(value)`.

`listen` accepts a nonempty list of distinct addresses, or a single string for
compatibility. Each process uses its own private IP in `listen`; the backend
list is identical on every front. Backends should configure the same buckets.
All listeners of a process share its state and routes. Startup
fails if any address cannot be bound. SIGINT or SIGTERM closes all listeners.
Local clients use `http://127.0.0.1:8061/v1/...`; fronts reach backends through
their Gofra endpoints. Fronts do not need a backend on the same machine.

Release 2 replaces `kv run` and its combined configuration with these two
commands. A backend config accepts only `listen` and `buckets`; a front config
accepts only `listen` and `peers`. Unknown fields and trailing JSON are rejected.

## API

Client API, served only by `kv front`:

```text
GET /v1/{bucket}/get?key=...
PUT /v1/{bucket}/put?key=...
```

Storage API, served only by `kv back`:

```text
GET /{bucket}/get?key=...
PUT /{bucket}/put?key=...
```

Values are raw request and response bodies. A successful `put` returns `204`,
a missing value returns `404`, and a value larger than its bucket returns
`413` without replacing an existing value.

## Prometheus

`GET /metrics` on any listener exports Prometheus text format without additional
dependencies. Scrape each process once: `127.0.0.1:8061` for the front and
`127.0.0.1:8062` for the backend.

- `kv_http_requests_total` and `kv_http_request_duration_seconds` (histogram):
  completed API requests, labelled by `scope` (`external` or `internal`),
  `operation` (`get` or `put`), and HTTP `code`. External duration includes
  forwarding. A forwarded request is also counted as internal at its destination.
- `kv_bucket_capacity_bytes`, `kv_bucket_bytes`, `kv_bucket_items`: local capacity,
  stored key and value bytes, and entry count, labelled by configured `bucket`;
  exported only by backends.
- `kv_bucket_hits_total`, `kv_bucket_misses_total`, `kv_bucket_puts_total`,
  `kv_bucket_evictions_total`, `kv_bucket_rejected_puts_total`: local cache
  activity, labelled by configured `bucket`, exported only by backends.

Counters reset on restart. Request series appear after their first observation.
Scrapes and unmatched routes are excluded from request metrics. Keys and unknown
bucket names never become metric labels. Byte gauges exclude memory overhead.

## Build and test

```sh
./build
./build test
./build chaos
./build -Drace test
./build -Dcoverage coverage
./build -Dcoverage chaos coverage-chaos
./lint.sh
```

`kv-chaos` reads failure rates from `KV_CHAOS`; for example,
`KV_CHAOS="http call:5,read response:7"`. `KV_CHAOS_SEED` makes the sequence
repeatable.
