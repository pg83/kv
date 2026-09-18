#!/usr/bin/env python3

import json
import os
import socket

from lib import Lab


def config(**changes):
    value = {
        "listen": "127.0.0.1:1",
        "peers": [
            {"id": "one", "endpoint": "http://127.0.0.1:1"},
            {"id": "two", "endpoint": "http://127.0.0.1:2"},
        ],
        "buckets": {"default": 1024},
    }
    value.update(changes)
    return value


def run_config(lab, name, value, env=None):
    path = lab.dir / f"{name}.json"

    if isinstance(value, str):
        path.write_text(value)
    else:
        path.write_text(json.dumps(value))

    return lab.command("run", "-c", path, env=env)


def fails(result):
    assert result.returncode == 1, (result.stdout, result.stderr)


def main():
    lab = Lab()
    quiet = {"KV_CHAOS": "", "KV_CHAOS_SEED": ""}

    try:
        fails(lab.command())
        fails(lab.command("unknown"))
        fails(lab.command("run", "-unknown", env=quiet))
        fails(lab.command("run", "-c", lab.dir / "absent.json", env=quiet))
        fails(run_config(lab, "json", "{", quiet))

        invalid = {
            "listen": config(listen=""),
            "peers": config(peers=[]),
            "peer-id": config(peers=[{"id": "", "endpoint": "http://127.0.0.1:1"}]),
            "duplicate-id": config(peers=[
                {"id": "one", "endpoint": "http://127.0.0.1:1"},
                {"id": "one", "endpoint": "http://127.0.0.1:2"},
            ]),
            "parse-endpoint": config(peers=[{"id": "one", "endpoint": "%"}]),
            "bad-endpoint": config(peers=[{"id": "one", "endpoint": "ftp://host"}]),
            "endpoint-path": config(peers=[{"id": "one", "endpoint": "http://host/path"}]),
            "duplicate-endpoint": config(peers=[
                {"id": "one", "endpoint": "http://127.0.0.1:1/"},
                {"id": "two", "endpoint": "http://127.0.0.1:1"},
            ]),
            "buckets": config(buckets={}),
            "bucket-name": config(buckets={"bad/name": 1}),
            "bucket-size": config(buckets={"default": 0}),
        }

        for name, value in invalid.items():
            fails(run_config(lab, name, value, quiet))

        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]

        try:
            fails(run_config(lab, "busy", config(listen=f"127.0.0.1:{port}"), quiet))
        finally:
            listener.close()

        if os.environ.get("KV_CHAOS"):
            missing = lab.dir / "still-absent.json"
            maximum = "18446744073709551615"
            cases = [
                {"KV_CHAOS": "http call:0", "KV_CHAOS_SEED": "1"},
                {"KV_CHAOS": "unknown:1", "KV_CHAOS_SEED": "1"},
                {"KV_CHAOS": "http call:no", "KV_CHAOS_SEED": "1"},
                {"KV_CHAOS": "", "KV_CHAOS_SEED": "no"},
                {
                    "KV_CHAOS": f"all:{maximum},-write coverage,-read config,http call",
                    "KV_CHAOS_SEED": "1",
                },
                {"KV_CHAOS": "parse flags:1", "KV_CHAOS_SEED": "1"},
                {"KV_CHAOS": "notify signals:1", "KV_CHAOS_SEED": "1"},
                {"KV_CHAOS": "serve:1", "KV_CHAOS_SEED": "1"},
            ]

            for index, env in enumerate(cases):
                if index < 6:
                    result = lab.command("run", "-c", missing, env=env)
                else:
                    result = run_config(lab, f"chaos-{index}", config(), env)

                fails(result)
    finally:
        lab.close()


if __name__ == "__main__":
    main()
