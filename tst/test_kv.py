#!/usr/bin/env python3

import concurrent.futures
import hashlib
import http.server
import json
import os
import socket
import threading

from lib import Lab


def part(value):
    raw = value.encode()
    return len(raw).to_bytes(8, "big") + raw


def rank(peers, bucket, key):
    def score(peer):
        return hashlib.sha256(part(bucket) + part(key) + part(peer["id"])).digest()

    return sorted(peers, key=score, reverse=True)


def key_for(peers, owner, prefix):
    for index in range(10000):
        key = f"{prefix}-{index}"

        if rank(peers, "default", key)[0]["id"] == owner:
            return key

    raise AssertionError(f"no key for {owner}")


def peer_index(peers, ident):
    return next(index for index, peer in enumerate(peers) if peer["id"] == ident)


class Unavailable(http.server.BaseHTTPRequestHandler):
    def respond(self):
        self.send_response(503)
        self.end_headers()

    do_GET = respond
    do_PUT = respond

    def log_message(self, *_args):
        pass


class BrokenResponse(http.server.BaseHTTPRequestHandler):
    def respond(self):
        self.send_response(200)
        self.send_header("Content-Length", "10")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(b"x")
        self.close_connection = True

    do_GET = respond
    do_PUT = respond

    def log_message(self, *_args):
        pass


def write_config(lab, index, peers):
    lab.peers = peers
    lab.configs[index].write_text(json.dumps({
        "listen": f"127.0.0.1:{lab.ports[index]}",
        "peers": peers,
        "buckets": {"default": 1048576, "small": 8},
    }))


def normal_scenario():
    lab = Lab()
    chaotic = bool(os.environ.get("KV_CHAOS"))

    try:
        lab.start_all()

        for peer in lab.peers:
            key = key_for(lab.peers, peer["id"], "shard")
            value = peer["id"].encode()
            assert lab.put(0, "default", key, value) == (204, b"")
            holders = []

            for candidate in lab.peers:
                index = peer_index(lab.peers, candidate["id"])
                status, body = lab.get(index, "default", key, internal=True)

                if status == 200:
                    assert (status, body) == (200, value)
                    holders.append(candidate["id"])
                else:
                    assert status == 404

            if chaotic:
                assert holders
                status, body = lab.get(0, "default", key)
                assert status in (200, 404, 503)

                if status == 200:
                    assert body == value
            else:
                assert holders == [peer["id"]]

        fallback_key = key_for(lab.peers, "lab1", "fallback")
        fallback_order = rank(lab.peers, "default", fallback_key)
        fallback_index = peer_index(lab.peers, fallback_order[1]["id"])
        lab.stop(0)
        assert lab.put(1, "default", fallback_key, b"fallback") == (204, b"")
        fallback_holders = [
            index for index in (1, 2)
            if lab.get(index, "default", fallback_key, internal=True) == (200, b"fallback")
        ]
        assert fallback_holders

        if not chaotic:
            assert fallback_holders == [fallback_index]
            assert lab.get(1, "default", fallback_key) == (200, b"fallback")

        lab.start(0)

        if not chaotic:
            assert lab.get(1, "default", fallback_key)[0] == 404
            assert lab.get(fallback_index, "default", fallback_key, internal=True) == (200, b"fallback")

        store = 1
        assert lab.put(store, "small", "a", b"111", internal=True) == (204, b"")
        assert lab.put(store, "small", "b", b"222", internal=True) == (204, b"")
        assert lab.get(store, "small", "a", internal=True) == (200, b"111")
        assert lab.put(store, "small", "c", b"333", internal=True) == (204, b"")
        assert lab.get(store, "small", "b", internal=True)[0] == 404
        assert lab.get(store, "small", "a", internal=True) == (200, b"111")
        assert lab.get(store, "small", "c", internal=True) == (200, b"333")
        assert lab.put(store, "small", "a", b"123456", internal=True) == (204, b"")
        assert lab.get(store, "small", "c", internal=True)[0] == 404
        assert lab.put(store, "small", "a", b"12345678", internal=True)[0] == 413
        assert lab.get(store, "small", "a", internal=True) == (200, b"123456")
        assert lab.get(store, "missing", "a", internal=True)[0] == 404
        assert lab.put(store, "missing", "a", b"value", internal=True)[0] == 404
        assert lab.request(store, "GET", "/small/get")[0] == 400
        assert lab.request(store, "GET", "/small/get?key=a&key=b")[0] == 400

        with socket.create_connection(("127.0.0.1", lab.ports[store])) as connection:
            connection.sendall(
                b"PUT /default/put?key=broken HTTP/1.1\r\n"
                b"Host: localhost\r\n"
                b"Transfer-Encoding: chunked\r\n"
                b"Connection: close\r\n\r\n"
                b"not-a-size\r\n"
            )
            connection.shutdown(socket.SHUT_WR)
            response = connection.recv(4096)
            assert b" 500 " in response

        def hammer(worker):
            for iteration in range(100):
                key = f"concurrent-{iteration % 8}"
                value = f"{worker}-{iteration}".encode()
                assert lab.put(2, "default", key, value, internal=True)[0] == 204
                assert lab.get(2, "default", key, internal=True)[0] == 200

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(hammer, range(8)))

        if chaotic:
            assert lab.chaos_seen()
    finally:
        lab.close()


def unavailable_scenario():
    lab = Lab(env={"KV_CHAOS": "", "KV_CHAOS_SEED": ""})
    peers = [{"id": "down", "endpoint": f"http://127.0.0.1:{lab.ports[1]}"}]
    write_config(lab, 0, peers)

    try:
        lab.start(0)
        assert lab.get(0, "default", "key") == (503, b"Service Unavailable\n")
    finally:
        lab.close()


def retry_scenario():
    upstream = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Unavailable)
    broken = http.server.ThreadingHTTPServer(("127.0.0.1", 0), BrokenResponse)
    threads = [
        threading.Thread(target=upstream.serve_forever),
        threading.Thread(target=broken.serve_forever),
    ]

    for thread in threads:
        thread.start()

    lab = Lab(env={"KV_CHAOS": "", "KV_CHAOS_SEED": ""})
    peers = [
        {"id": "unavailable", "endpoint": f"http://127.0.0.1:{upstream.server_port}"},
        {"id": "broken", "endpoint": f"http://127.0.0.1:{broken.server_port}"},
        {"id": "local", "endpoint": f"http://127.0.0.1:{lab.ports[0]}"},
    ]
    write_config(lab, 0, peers)

    try:
        lab.start(0)
        key = key_for(peers, "unavailable", "retry")
        assert lab.put(0, "default", key, b"value") == (204, b"")
        assert lab.get(0, "default", key, internal=True) == (200, b"value")

        key = key_for(peers, "broken", "broken")
        assert lab.put(0, "default", key, b"value") == (204, b"")
        assert lab.get(0, "default", key, internal=True) == (200, b"value")
    finally:
        lab.close()

        for server in (upstream, broken):
            server.shutdown()
            server.server_close()

        for thread in threads:
            thread.join()


def handler_failure_scenario():
    if not os.environ.get("KV_CHAOS"):
        return

    lab = Lab(env={"KV_CHAOS": "read request:1", "KV_CHAOS_SEED": "1"})

    try:
        lab.start(0)
        assert lab.put(0, "default", "key", b"value", internal=True)[0] == 500
    finally:
        lab.close()


def request_failure_scenario():
    if not os.environ.get("KV_CHAOS"):
        return

    lab = Lab(env={"KV_CHAOS": "new request:1", "KV_CHAOS_SEED": "1"})

    try:
        lab.start(0)
        assert lab.get(0, "default", "key")[0] == 503
    finally:
        lab.close()


def main():
    normal_scenario()
    unavailable_scenario()
    retry_scenario()
    handler_failure_scenario()
    request_failure_scenario()


if __name__ == "__main__":
    main()
