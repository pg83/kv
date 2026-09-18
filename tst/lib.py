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
    def __init__(self, env=None):
        self.dir = Path(tempfile.mkdtemp(prefix="kv-lab-"))
        self.env = env or {}
        self.ports = [free_port() for _ in range(3)]
        self.front_ports = [free_port() for _ in range(3)]
        self.peers = [
            {"id": f"lab{i + 1}", "endpoint": f"http://127.0.0.1:{port}"}
            for i, port in enumerate(self.ports)
        ]
        self.back_configs = []
        self.front_configs = []
        self.back_processes = [None, None, None]
        self.front_processes = [None, None, None]
        self.logs = []
        self.serial = 0

        for i, port in enumerate(self.ports):
            config = {
                "listen": f"127.0.0.1:{port}",
                "buckets": {"default": 1048576, "small": 8},
            }
            path = self.dir / f"back{i + 1}.json"
            path.write_text(json.dumps(config))
            self.back_configs.append(path)
            path = self.dir / f"front{i + 1}.json"
            path.write_text(json.dumps({
                "listen": f"127.0.0.1:{self.front_ports[i]}",
                "peers": self.peers,
            }))
            self.front_configs.append(path)

    def environment(self, extra=None):
        env = os.environ.copy()
        env.update(self.env)

        if extra:
            env.update(extra)

        coverage = env.get("GOCOVERDIR")

        if coverage:
            directory = Path(coverage) / f"daemon-{self.dir.name}-{self.serial}"
            directory.mkdir(parents=True)
            env["GOCOVERDIR"] = str(directory)

        self.serial += 1

        return env

    def command(self, *args, env=None):
        return subprocess.run(
            [KV, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self.environment(env),
            timeout=10,
        )

    def start(self, index):
        self.start_back(index)
        self.start_front(index)

    def start_back(self, index):
        self.start_role(index, "back", self.back_configs, self.back_processes)

    def start_front(self, index):
        self.start_role(index, "front", self.front_configs, self.front_processes)

    def start_role(self, index, role, configs, processes):
        log = open(self.dir / f"{role}{index + 1}-{self.serial}.log", "wb")
        process = subprocess.Popen(
            [KV, role, "-c", configs[index]],
            stdout=log,
            stderr=log,
            env=self.environment(),
        )
        processes[index] = process
        self.logs.append(log)
        deadline = time.monotonic() + 5

        while time.monotonic() < deadline:
            if process.poll() is not None:
                log.flush()
                raise AssertionError(f"lab{index + 1} exited: {Path(log.name).read_text()}")

            try:
                path = "/metrics" if role == "front" else "/default/get?key=ready"
                self.request(index, "GET", path, front=role == "front")

                return
            except OSError:
                time.sleep(0.01)

        raise AssertionError(f"lab{index + 1} did not start")

    def start_all(self):
        for index in range(3):
            self.start(index)

    def stop(self, index):
        self.stop_front(index)
        self.stop_back(index)

    def stop_back(self, index):
        self.stop_role(index, self.back_processes)

    def stop_front(self, index):
        self.stop_role(index, self.front_processes)

    def stop_role(self, index, processes):
        process = processes[index]

        if process is None:
            return

        if process.poll() is None:
            process.terminate()

            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

        processes[index] = None

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

    def request(self, index, method, path, body=None, *, port=None, front=False):
        ports = self.front_ports if front else self.ports
        connection = http.client.HTTPConnection("127.0.0.1", ports[index] if port is None else port, timeout=5)
        connection.request(method, path, body=body)
        response = connection.getresponse()
        data = response.read()
        status = response.status
        connection.close()
        return status, data

    def operation(self, index, internal, method, bucket, action, key, value=None):
        prefix = "" if internal else "/v1"
        path = f"{prefix}/{urllib.parse.quote(bucket, safe='')}/{action}?{urllib.parse.urlencode({'key': key})}"
        return self.request(index, method, path, value, front=not internal)

    def get(self, index, bucket, key, internal=False):
        return self.operation(index, internal, "GET", bucket, "get", key)

    def put(self, index, bucket, key, value, internal=False):
        return self.operation(index, internal, "PUT", bucket, "put", key, value)
