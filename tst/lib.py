import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.parse


KV = Path(os.environ["KV_TEST_BINARY"]).resolve()


def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class Lab:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="kv-lab-"))
        self.ports = [free_port() for _ in range(3)]
        self.peers = [
            {"id": f"lab{i + 1}", "endpoint": f"http://127.0.0.1:{port}"}
            for i, port in enumerate(self.ports)
        ]
        self.configs = []
        self.processes = [None, None, None]
        self.logs = []
        self.serial = 0

        for i, port in enumerate(self.ports):
            config = {
                "listen": f"127.0.0.1:{port}",
                "peers": self.peers,
                "buckets": {"default": 1048576, "small": 8},
            }
            path = self.dir / f"lab{i + 1}.json"
            path.write_text(json.dumps(config))
            self.configs.append(path)

    def start(self, index):
        env = os.environ.copy()
        coverage = env.get("GOCOVERDIR")

        if coverage:
            directory = Path(coverage) / f"daemon-{self.serial}"
            directory.mkdir(parents=True)
            env["GOCOVERDIR"] = str(directory)

        self.serial += 1
        log = open(self.dir / f"lab{index + 1}-{self.serial}.log", "wb")
        process = subprocess.Popen(
            [KV, "run", "-c", self.configs[index]],
            stdout=log,
            stderr=log,
            env=env,
        )
        self.processes[index] = process
        self.logs.append(log)
        deadline = time.monotonic() + 5

        while time.monotonic() < deadline:
            if process.poll() is not None:
                log.flush()
                raise AssertionError(f"lab{index + 1} exited: {Path(log.name).read_text()}")

            try:
                self.request(index, "GET", "/default/get?key=ready")

                return
            except OSError:
                time.sleep(0.01)

        raise AssertionError(f"lab{index + 1} did not start")

    def start_all(self):
        for index in range(3):
            self.start(index)

    def stop(self, index):
        process = self.processes[index]

        if process is None:
            return

        if process.poll() is None:
            process.terminate()

            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

        self.processes[index] = None

    def close(self):
        for index in range(3):
            self.stop(index)

        for log in self.logs:
            log.close()

    def chaos_seen(self):
        for log in self.logs:
            log.flush()

            if b"level=WARN msg=chaos " in Path(log.name).read_bytes():
                return True

        return False

    def request(self, index, method, path, body=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.ports[index], timeout=5)
        connection.request(method, path, body=body)
        response = connection.getresponse()
        data = response.read()
        status = response.status
        connection.close()
        return status, data

    def operation(self, index, internal, method, bucket, action, key, value=None):
        prefix = "" if internal else "/v1"
        path = f"{prefix}/{urllib.parse.quote(bucket, safe='')}/{action}?{urllib.parse.urlencode({'key': key})}"
        return self.request(index, method, path, value)

    def get(self, index, bucket, key, internal=False):
        return self.operation(index, internal, "GET", bucket, "get", key)

    def put(self, index, bucket, key, value, internal=False):
        return self.operation(index, internal, "PUT", bucket, "put", key, value)
