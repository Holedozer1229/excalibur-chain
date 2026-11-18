#!/usr/bin/env python3
"""
cpu_miner.py - Windows-compatible CPU miner for the Excalibur fork.

Connects to stratum_fork.py as a stratum client and mines using
multiple threads.  Pure Python SHA-256d hashing is limited to
~0.15-0.30 MH/s per thread due to Python's GIL.  For practical
mining speeds, point a GPU stratum miner at 127.0.0.1:9434 instead.

  fork_node (RPC:9432) <-- stratum_fork (9434) <-- cpu_miner (this)

Config (env):
  STRATUM_HOST  - stratum server host (default 127.0.0.1)
  STRATUM_PORT  - stratum server port (default 9434)
  MINER_THREADS - number of hashing threads (default = CPU count)
  MINER_WORKER  - worker name (default "cpu-0")
"""
import hashlib
import json
import os
import socket
import struct
import threading
import time

HOST = os.environ.get("STRATUM_HOST", "127.0.0.1")
PORT = int(os.environ.get("STRATUM_PORT", "9434"))
THREADS = int(os.environ.get("MINER_THREADS", 0)) or os.cpu_count() or 4
WORKER = os.environ.get("MINER_WORKER", f"cpu-{os.getpid() % 100}")


def wordswap(b):
    return b"".join(b[i:i + 4][::-1] for i in range(0, len(b), 4))


def log(*a):
    print(time.strftime("%H:%M:%S"), f"[{WORKER}]", *a, flush=True)


class StratumClient:
    def __init__(self):
        self.sock = None
        self.buf = b""
        self.extranonce1 = b""
        self.current_job = None
        self.lock = threading.Lock()
        self.new_job_event = threading.Event()
        self.stop_event = threading.Event()

    def connect(self):
        self.sock = socket.create_connection((HOST, PORT), timeout=30)
        self.sock.settimeout(5.0)
        log(f"connected to {HOST}:{PORT}")

    def send(self, msg):
        self.sock.sendall((json.dumps(msg) + "\n").encode())

    def recv_line(self):
        while b"\n" not in self.buf:
            try:
                chunk = self.sock.recv(4096)
                if not chunk:
                    raise ConnectionError("disconnected")
                self.buf += chunk
            except socket.timeout:
                return None
        line, self.buf = self.buf.split(b"\n", 1)
        return line.decode()

    def subscribe(self):
        self.send({"id": 1, "method": "mining.subscribe", "params": []})
        resp = self._recv_response()
        if resp and "result" in resp and resp["result"]:
            self.extranonce1 = bytes.fromhex(resp["result"][1])
            log(f"subscribed, extranonce1={self.extranonce1.hex()}")

    def authorize(self):
        self.send({"id": 2, "method": "mining.authorize", "params": [WORKER, ""]})
        resp = self._recv_response()
        if resp and resp.get("result"):
            log("authorized")

    def _recv_response(self):
        for _ in range(30):
            line = self.recv_line()
            if line is None:
                return None
            msg = json.loads(line)
            if "id" in msg and msg["id"] is not None:
                return msg
            self._handle_push(msg)
        return None

    def _handle_push(self, msg):
        method = msg.get("method", "")
        params = msg.get("params", [])
        if method == "mining.notify":
            self._new_job(params)

    def _new_job(self, params):
        if len(params) < 8:
            return
        job_id = params[0]
        prevhash = wordswap(bytes.fromhex(params[1]))
        coinb1 = bytes.fromhex(params[2])
        coinb2 = bytes.fromhex(params[3])
        version = int(params[5], 16) if len(params) > 5 else 1
        bits = int(params[6], 16)
        ntime = int(params[7], 16)
        exp = bits >> 24
        mant = bits & 0xFFFFFF
        target = (mant >> (8 * (3 - exp))) if exp <= 3 else (mant << (8 * (exp - 3)))
        job = {
            "job_id": job_id, "prevhash": prevhash,
            "coinb1": coinb1, "coinb2": coinb2,
            "version": version, "bits": bits, "ntime": ntime, "target": target,
        }
        with self.lock:
            self.current_job = job
        self.new_job_event.set()

    def listen_loop(self):
        while not self.stop_event.is_set():
            line = self.recv_line()
            if line is None:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "id" in msg and msg["id"] is not None:
                continue
            self._handle_push(msg)

    def submit(self, job_id, en2, ntime, nonce):
        self.send({
            "id": 10, "method": "mining.submit",
            "params": [WORKER, job_id, en2.hex(), f"{ntime:08x}", f"{nonce:08x}"]
        })
        resp = self._recv_response()
        if resp and resp.get("result"):
            log(f"share accepted (job {job_id})")
            return True
        return False

    def get_current_job(self):
        with self.lock:
            return self.current_job

    def close(self):
        self.stop_event.set()
        try:
            self.sock.close()
        except Exception:
            pass


class HasherThread(threading.Thread):
    def __init__(self, client, thread_id):
        super().__init__(daemon=True)
        self.client = client
        self.thread_id = thread_id
        self.hashes = 0
        self.shares = 0
        self.blocks = 0
        self._lock = threading.Lock()

    def _inc(self, n):
        with self._lock:
            self.hashes += n

    def run(self):
        en1 = self.client.extranonce1
        en2 = struct.pack("<I", self.thread_id + 1)
        stride = THREADS

        while not self.client.stop_event.is_set():
            job = self.client.get_current_job()
            if job is None:
                self.client.new_job_event.wait(timeout=0.5)
                self.client.new_job_event.clear()
                continue

            current_id = job["job_id"]
            coinbase = job["coinb1"] + en1 + en2 + job["coinb2"]
            h1 = hashlib.sha256(coinbase).digest()
            merkle = hashlib.sha256(h1).digest()
            prefix = (struct.pack("<I", job["version"])
                      + job["prevhash"] + merkle
                      + struct.pack("<II", job["ntime"], job["bits"]))
            target = job["target"]

            nonce = self.thread_id
            batch = 0
            local = 0
            while not self.client.stop_event.is_set():
                if batch % 10000 == 0:
                    nj = self.client.get_current_job()
                    if nj and nj["job_id"] != current_id:
                        self.client.new_job_event.clear()
                        break

                header = prefix + nonce.to_bytes(4, 'little')
                h = hashlib.sha256(hashlib.sha256(header).digest()).digest()
                if int.from_bytes(h, "big") <= target:
                    ok = self.client.submit(current_id, en2, job["ntime"], nonce)
                    if ok:
                        with self._lock:
                            self.blocks += 1
                        log(f"BLOCK FOUND! nonce={nonce}")
                    with self._lock:
                        self.shares += 1
                    nj = self.client.get_current_job()
                    if nj and nj["job_id"] != current_id:
                        self.client.new_job_event.clear()
                        break
                local += 1
                # Update global counter every 100k hashes for live stats
                if local >= 100000:
                    self._inc(local)
                    local = 0
                nonce += stride
                batch += 1
                if batch > 0x80000000:
                    break
            self._inc(local)

    def stats(self):
        with self._lock:
            return f"H={self.hashes} S={self.shares} B={self.blocks}"


def main():
    log(f"CPU miner starting: {THREADS} threads, worker={WORKER} (non-stop)")
    global_start = time.time()
    reconnect_delay = 1

    while True:
        client = StratumClient()
        hashers = [HasherThread(client, i) for i in range(THREADS)]

        try:
            while True:
                try:
                    client.connect()
                    client.subscribe()
                    client.authorize()
                except (ConnectionRefusedError, ConnectionError, OSError) as e:
                    log(f"connection failed: {e} - retrying in {reconnect_delay}s")
                    time.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, 30)
                    break

                listener = threading.Thread(target=client.listen_loop, daemon=True)
                listener.start()

                log("waiting for first job...")
                for _ in range(60):
                    job = client.get_current_job()
                    if job:
                        client.new_job_event.clear()
                        log(f"first job: {job['job_id']} bits {job['bits']:#010x}")
                        break
                    time.sleep(1)
                else:
                    log("timeout waiting for first job - reconnecting")
                    client.close()
                    reconnect_delay = 1
                    break

                for h in hashers:
                    if not h.is_alive():
                        h.start()
                        time.sleep(0.05)

                log(f"mining with {THREADS} threads...")

                try:
                    while not client.stop_event.is_set():
                        time.sleep(5)
                        elapsed = time.time() - global_start
                        th = sum(h.hashes for h in hashers)
                        ts = sum(h.shares for h in hashers)
                        tb = sum(h.blocks for h in hashers)
                        hr = th / elapsed if elapsed > 0 else 0
                        st = "; ".join(h.stats() for h in hashers[:4])
                        if len(hashers) > 4:
                            st += f" ... ({len(hashers)} threads)"
                        log(f"hashrate: {hr/1e6:.2f} MH/s  "
                              f"total: H={th} S={ts} B={tb}  [{st}]")
                except KeyboardInterrupt:
                    log("stopping...")
                    client.stop_event.set()
                    break

        except KeyboardInterrupt:
            log("stopping...")
            client.stop_event.set()

        client.close()
        for h in hashers:
            if h.is_alive():
                h.join(timeout=2)

        if client.stop_event.is_set():
            log("miner stopped")
            return

        log(f"reconnecting in {reconnect_delay}s...")
        time.sleep(reconnect_delay)
        reconnect_delay = min(reconnect_delay * 2, 30)


if __name__ == "__main__":
    main()
