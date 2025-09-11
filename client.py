import argparse
import json
import socket
import struct
import threading
import time
import uuid


def recv_exact(conn, n):
    data = bytearray()
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            raise ConnectionError("socket closed")
        data.extend(chunk)
    return bytes(data)


def recv_msg(conn):
    raw_len = recv_exact(conn, 4)
    (length,) = struct.unpack("!I", raw_len)
    payload = recv_exact(conn, length)
    return json.loads(payload.decode("utf-8"))


def send_msg(conn, obj):
    payload = json.dumps(obj).encode("utf-8")
    header = struct.pack("!I", len(payload))
    conn.sendall(header + payload)


class Client:
    def __init__(self, host, port, concurrency, requests, size):
        self.host = host
        self.port = port
        self.concurrency = int(concurrency)
        self.requests = int(requests)
        self.size = int(size)
        self.results = []
        self.lock = threading.Lock()

    def run(self):
        threads = []
        start = time.perf_counter()
        for i in range(self.concurrency):
            t = threading.Thread(target=self._worker, name=f"client-worker-{i}")
            t.start()
            threads.append(t)
        for t in threads:
            t.join()
        elapsed = time.perf_counter() - start
        print(f"Done: {len(self.results)} responses in {elapsed:.3f}s")

    def _worker(self):
        with socket.create_connection((self.host, self.port), timeout=5) as conn:
            for _ in range(self.requests):
                rid = str(uuid.uuid4())
                send_msg(conn, {"id": rid, "cmd": "compute", "n": self.size})
                resp = recv_msg(conn)
                with self.lock:
                    self.results.append(resp)


def parse_args():
    ap = argparse.ArgumentParser(description="ThreadCenter Client")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5050)
    ap.add_argument("--concurrency", type=int, default=4, help="client threads")
    ap.add_argument("--requests", type=int, default=5, help="requests per thread")
    ap.add_argument("--size", type=int, default=500000, help="CPU size parameter")
    return ap.parse_args()


def main():
    args = parse_args()
    client = Client(args.host, args.port, args.concurrency, args.requests, args.size)
    client.run()


if __name__ == "__main__":
    main()
