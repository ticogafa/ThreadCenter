import argparse
import json
import os
import queue
import selectors
import socket
import struct
import threading
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import Process, Queue as MPQueue, Event as MPEvent


# Message framing: 4-byte big-endian length prefix followed by JSON payload
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


def cpu_bound_task(n):
    # Simple CPU bound workload
    acc = 0
    a, b = 0, 1
    for _ in range(max(1, int(n))):
        a, b = b, (a + b) % 10_000_019
        acc = (acc + a * 31 + b * 17) % 1_000_000_007
    return acc


class WorkerProcess(Process):
    def __init__(self, task_q, result_q, stop_event):
        super().__init__(daemon=True)
        self.task_q = task_q
        self.result_q = result_q
        self.stop_event = stop_event

    def run(self):
        while not self.stop_event.is_set():
            try:
                task = self.task_q.get(timeout=0.5)
            except queue.Empty:
                continue
            if task is None:  # poison pill
                break
            req_id, n = task
            try:
                res = cpu_bound_task(n)
                self.result_q.put((req_id, res, None))
            except Exception as e:
                self.result_q.put((req_id, None, f"error: {e}"))


class DistributedServer:
    def __init__(self, host, port, workers):
        self.host = host
        self.port = port
        self.sel = selectors.DefaultSelector()
        self.thread_pool = ThreadPoolExecutor(max_workers=32)
        self.task_q = MPQueue()
        self.result_q = MPQueue()
        self.stop_event = MPEvent()
        self.workers = [WorkerProcess(self.task_q, self.result_q, self.stop_event) for _ in range(int(workers))]
        self.lock = threading.Lock()
        self.pending = {}
        self._result_thread = None

    def start(self):
        for p in self.workers:
            p.start()

        # background thread to dispatch process results back to clients
        self._result_thread = threading.Thread(target=self._result_dispatch_loop, name="result-dispatch", daemon=True)
        self._result_thread.start()

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.host, self.port))
            s.listen()
            s.setblocking(False)
            self.sel.register(s, selectors.EVENT_READ, self._accept)
            print(f"Server listening on {self.host}:{self.port} with {len(self.workers)} workers")
            try:
                while True:
                    for key, _ in self.sel.select(timeout=1.0):
                        callback = key.data
                        callback(key.fileobj)
            except KeyboardInterrupt:
                print("Shutting down...")
            finally:
                self._shutdown()

    def _accept(self, server_sock):
        conn, addr = server_sock.accept()
        conn.setblocking(True)  # handle each client with a thread
        print(f"Accepted from {addr}")
        self.thread_pool.submit(self._client_loop, conn, addr)

    def _client_loop(self, conn, addr):
        try:
            while True:
                try:
                    msg = recv_msg(conn)
                except ConnectionError:
                    break
                # Expected msg: {"id": str, "cmd": "compute", "n": int}
                req_id = str(msg.get("id"))
                cmd = msg.get("cmd")
                if cmd == "compute":
                    n = int(msg.get("n", 1000000))
                    with self.lock:
                        self.pending[req_id] = conn
                    # send to process pool via MP queue (IPC)
                    self.task_q.put((req_id, n))
                elif cmd == "ping":
                    send_msg(conn, {"id": req_id, "ok": True, "pong": True})
                else:
                    send_msg(conn, {"id": req_id, "error": "unknown command"})
        finally:
            # cleanup any pending entries for this conn
            to_remove = []
            with self.lock:
                for rid, c in list(self.pending.items()):
                    if c is conn:
                        to_remove.append(rid)
                for rid in to_remove:
                    self.pending.pop(rid, None)
            try:
                conn.close()
            except Exception:
                pass
            print(f"Closed {addr}")

    def _result_dispatch_loop(self):
        while not self.stop_event.is_set():
            try:
                req_id, res, err = self.result_q.get(timeout=0.5)
            except queue.Empty:
                continue
            with self.lock:
                conn = self.pending.pop(str(req_id), None)
            if conn is not None:
                try:
                    if err:
                        send_msg(conn, {"id": req_id, "error": err})
                    else:
                        send_msg(conn, {"id": req_id, "result": res})
                except Exception:
                    try:
                        conn.close()
                    except Exception:
                        pass

    def _shutdown(self):
        self.stop_event.set()
        # poison pills for processes
        for _ in self.workers:
            self.task_q.put(None)
        for p in self.workers:
            try:
                p.join(timeout=2)
            except Exception:
                pass
        try:
            self.thread_pool.shutdown(wait=True, cancel_futures=True)
        except Exception:
            pass
        try:
            self.sel.close()
        except Exception:
            pass


def parse_args():
    ap = argparse.ArgumentParser(description="ThreadCenter Distributed Server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5050)
    ap.add_argument("--workers", type=int, default=max(2, (os.cpu_count() or 2) // 2))
    return ap.parse_args()


def main():
    args = parse_args()
    server = DistributedServer(args.host, args.port, workers=args.workers)
    server.start()


if __name__ == "__main__":
    # Important for Windows multiprocessing (spawn)
    main()
