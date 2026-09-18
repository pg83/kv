# kv

Small in-memory sharded key/value cache.

Every node has the same peer and bucket configuration. Public requests use
rendezvous hashing over the bucket, key, and peer ID. Local requests operate
on a per-bucket LRU. A failed peer is skipped; a `404` is final.

## Configuration

```json
{
  "listen": ":8080",
  "peers": [
    {"id": "lab1", "endpoint": "http://lab1:8080"},
    {"id": "lab2", "endpoint": "http://lab2:8080"},
    {"id": "lab3", "endpoint": "http://lab3:8080"}
  ],
  "buckets": {
    "default": 67108864
  }
}
```

Bucket capacity is local to each node and counts `len(key) + len(value)`.

## API

External API:

```text
GET /v1/{bucket}/get?key=...
PUT /v1/{bucket}/put?key=...
```

Internal API on the same port:

```text
GET /{bucket}/get?key=...
PUT /{bucket}/put?key=...
```

Values are raw request and response bodies. A successful `put` returns `204`,
a missing value returns `404`, and a value larger than its bucket returns
`413` without replacing an existing value.

## Build and test

```sh
./build
./build test
./build -Drace test
./build -Dcoverage coverage
./lint.sh
```
