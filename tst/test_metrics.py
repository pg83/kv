#!/usr/bin/env python3

import concurrent.futures
import http.client
import json
import os
import re
import socket

from lib import Lab, free_port


def samples(data):
    assert data.endswith(b"\n")
    result = {}

    for line in data.decode().splitlines():
        if line.startswith("#"):
            continue

        match = re.fullmatch(r'(\w+)(?:\{(.*)\})? ([^ ]+)', line)
        assert match, line
        name, raw, value = match.groups()
        labels = {}

        while raw:
            label = re.match(r'(\w+)="((?:\\[\\"n]|[^"\\])*)"(?:,|$)', raw)
            assert label, raw
            key, encoded = label.groups()
            labels[key] = re.sub(r'\\([\\"n])', lambda m: '\n' if m[1] == 'n' else m[1], encoded)
            raw = raw[label.end():]

        identity = name, tuple(sorted(labels.items()))
        assert identity not in result, identity
        result[identity] = float(value)

    return result


def metric(values, name, **labels):
    return values[name, tuple(sorted(labels.items()))]


def scrape(lab, port=None, front=False):
    ports = lab.front_ports if front else lab.ports
    connection = http.client.HTTPConnection("127.0.0.1", ports[0] if port is None else port, timeout=5)
    connection.request("GET", "/metrics")
    response = connection.getresponse()
    assert response.status == 200
    assert response.getheader("Content-Type") == "text/plain; version=0.0.4; charset=utf-8"
    data = response.read()
    connection.close()
    return samples(data)


def scenario():
    lab = Lab(env={"KV_CHAOS": "", "KV_CHAOS_SEED": ""})
    alias = free_port()
    front_alias = free_port()
    unusual = 'quoted"\\bucket\nname'
    config = json.loads(lab.back_configs[0].read_text())
    config["listen"] = [f"127.0.0.1:{lab.ports[0]}", f"127.0.0.1:{alias}"]
    config["buckets"][unusual] = 100
    lab.back_configs[0].write_text(json.dumps(config))
    lab.front_configs[0].write_text(json.dumps({
        "listen": [f"127.0.0.1:{lab.front_ports[0]}", f"127.0.0.1:{front_alias}"],
        "peers": lab.peers[:1],
    }))

    try:
        lab.start(0)
        before = scrape(lab)
        assert metric(before, "kv_bucket_items", bucket="small") == 0
        assert metric(before, "kv_bucket_hits_total", bucket="small") == 0
        assert metric(before, "kv_bucket_capacity_bytes", bucket=unusual) == 100
        assert before == scrape(lab, alias)
        assert scrape(lab, front=True) == {}

        assert lab.put(0, "small", "a", b"111", internal=True)[0] == 204
        assert lab.put(0, "small", "b", b"222", internal=True)[0] == 204
        assert lab.request(0, "GET", "/small/get?key=a", port=alias) == (200, b"111")
        assert lab.put(0, "small", "c", b"333", internal=True)[0] == 204
        assert lab.get(0, "small", "b", internal=True)[0] == 404
        assert lab.put(0, "small", "a", b"123456", internal=True)[0] == 204
        assert lab.put(0, "small", "a", b"12345678", internal=True)[0] == 413
        assert lab.get(0, "small", "a", internal=True) == (200, b"123456")
        assert lab.get(0, "small", "c", internal=True)[0] == 404
        assert lab.request(0, "GET", "/small/get")[0] == 400

        for index in range(20):
            assert lab.get(0, f"unknown-{index}", "private-key", internal=True)[0] == 404

        assert lab.put(0, "default", "routed", b"value")[0] == 204
        assert lab.request(0, "GET", "/v1/default/get?key=routed", port=front_alias) == (200, b"value")
        after = scrape(lab)
        front_after = scrape(lab, front=True)
        assert after == scrape(lab, alias)
        assert front_after == scrape(lab, front_alias)
        assert not any(name.startswith("kv_bucket_") for name, _ in front_after)
        expected = {
            "capacity_bytes": 8, "bytes": 7, "items": 1, "hits_total": 2,
            "misses_total": 2, "puts_total": 4, "evictions_total": 2,
            "rejected_puts_total": 1,
        }

        for suffix, value in expected.items():
            assert metric(after, f"kv_bucket_{suffix}", bucket="small") == value

        assert metric(after, "kv_http_requests_total", scope="internal", operation="put", code="413") == 1
        assert metric(after, "kv_http_requests_total", scope="internal", operation="get", code="400") == 1
        assert metric(front_after, "kv_http_requests_total", scope="external", operation="put", code="204") == 1
        assert metric(front_after, "kv_http_requests_total", scope="external", operation="get", code="200") == 1
        assert "private-key" not in repr(after)
        assert "unknown-" not in repr(after)

        for (name, labels), count in after.items():
            if name != "kv_http_requests_total":
                continue

            labels = dict(labels)
            assert metric(after, "kv_http_request_duration_seconds_count", **labels) == count
            assert metric(after, "kv_http_request_duration_seconds_sum", **labels) >= 0
            cumulative = 0

            for bound in ("0.001", "0.005", "0.01", "0.025", "0.05", "0.1", "0.25", "0.5", "1", "2.5", "5", "+Inf"):
                current = metric(after, "kv_http_request_duration_seconds_bucket", le=bound, **labels)
                assert cumulative <= current <= count
                cumulative = current

            assert cumulative == count

        def hammer(worker):
            for index in range(50):
                if worker == 0:
                    scrape(lab, alias)
                    scrape(lab, front_alias)
                else:
                    assert lab.put(0, "default", f"worker-{worker}", b"value", internal=True)[0] == 204
                    assert lab.get(0, "default", f"worker-{worker}", internal=True)[0] == 200

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(hammer, range(4)))

        processes = [lab.back_processes[0], lab.front_processes[0]]
        lab.stop(0)
        assert all(process.returncode == 0 for process in processes)

        for port in (lab.ports[0], alias, lab.front_ports[0], front_alias):
            with socket.socket() as connection:
                assert connection.connect_ex(("127.0.0.1", port)) != 0
    finally:
        lab.close()


def close_failure():
    if not os.environ.get("KV_CHAOS"):
        return

    lab = Lab(env={"KV_CHAOS": "close server:1", "KV_CHAOS_SEED": "1"})

    try:
        lab.start(0)
        processes = [lab.back_processes[0], lab.front_processes[0]]
        lab.stop(0)
        assert all(process.returncode == 1 for process in processes)
    finally:
        lab.close()


if __name__ == "__main__":
    scenario()
    close_failure()
