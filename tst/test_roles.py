#!/usr/bin/env python3

import concurrent.futures

from lib import Lab


def scenario():
    lab = Lab(env={"KV_CHAOS": "", "KV_CHAOS_SEED": ""})

    try:
        for index in range(3):
            lab.start_back(index)

        assert lab.put(0, "default", "local", b"backend-only", internal=True)[0] == 204
        assert lab.get(0, "default", "local", internal=True) == (200, b"backend-only")

        for index in range(3):
            lab.start_front(index)
            assert lab.request(index, "PUT", "/v1/default/put?key=wrong-back-route", b"value")[0] == 404
            assert lab.get(index, "default", "wrong-back-route", internal=True)[0] == 404
            assert lab.request(index, "PUT", "/default/put?key=wrong-front-route", b"value", front=True)[0] == 404
            assert lab.request(index, "GET", "/default/get?key=local", front=True)[0] == 404
            assert lab.request(index, "GET", "/v1/default/get", front=True)[0] == 400

        assert lab.put(0, "default", "shared", b"persist-across-front-restart")[0] == 204
        holders = [index for index in range(3) if lab.get(index, "default", "shared", internal=True)[0] == 200]
        assert len(holders) == 1

        for index in range(3):
            lab.stop_front(index)

        assert lab.get(holders[0], "default", "shared", internal=True) == (200, b"persist-across-front-restart")

        for index in range(3):
            lab.start_front(index)
            assert lab.get(index, "default", "shared") == (200, b"persist-across-front-restart")

        def client(worker):
            for index in range(30):
                key = f"client-{worker}-{index}"
                value = key.encode()
                assert lab.put(worker % 3, "default", key, value)[0] == 204
                assert lab.get((worker + 1) % 3, "default", key) == (200, value)

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(client, range(4)))

        owner = holders[0]
        lab.stop_back(owner)
        assert lab.get(owner, "default", "shared")[0] == 404
        assert lab.put(owner, "default", "shared", b"fallback")[0] == 204
        assert lab.get((owner + 1) % 3, "default", "shared") == (200, b"fallback")

        for index in range(3):
            lab.stop_back(index)

        for index in range(3):
            assert lab.get(index, "default", "shared")[0] == 503
            assert lab.put(index, "default", "shared", b"no-local-storage")[0] == 503
            assert lab.request(index, "GET", "/metrics", front=True)[0] == 200

        lab.stop_front(0)
        lab.start_front(0)
        assert lab.get(0, "default", "shared")[0] == 503
    finally:
        lab.close()


if __name__ == "__main__":
    scenario()
