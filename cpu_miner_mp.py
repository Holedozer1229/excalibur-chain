#!/usr/bin/env python3
"""
cpu_miner_mp.py - Windows CPU miner with true parallel SHA-256d hashing.

Uses multiprocessing (spawn) to bypass Python's GIL, giving linear speedup
across CPU cores. Each worker process runs a tight hash loop with zero IPC
overhead — job data is passed once at spawn, results flow back via pipe.

Keeps standard SHA-256d PoW for BTC atomic swap compatibility.

  fork_node (RPC:9432) <-- stratum_fork (9434) <-- cpu_miner_mp (this)

Config (env):
  STRATUM_HOST  - stratum server host (default 127.0.0.1)
  STRATUM_PORT  - stratum server port (default 9434)
  MINER_THREADS - number of worker processes (default = CPU count)
  MINER_WORKER  - worker name (default "cpu-mp-0")
"""
import hashlib
import json
import multiprocessing as mp
import os
import socket
import struct
import time

HOST = os.environ.get("STRATUM_HOST", "127.0.0.1")
PORT = int(os.environ.get("STRATUM_PORT", "9434"))
THREADS = int(os.environ.get("MINER_THREADS", 0)) or os.cpu_count() or 4
WORKER = os.environ.get("MINER_WORKER", f"cpu-mp-{os.getpid() % 100}")


def wordswap(b):
    return b"".join(b[i:i + 4][::-1] for i in range(0, len(b), 4))


def log(*a):
    print(time.strftime("%H:%M:%S"), f"[{WORKER}]", *a, flush=True)


# ---------------------------------------------------------------------------
# Worker process: tight hash loop, zero IPC overhead during hashing
# ---------------------------------------------------------------------------

def hash_worker(worker_id, stride, job_data, result_pipe):
    """
    Worker process that hashes continuously.
    
    job_data: (prefix_bytes, target_int, job_id_str)
    result_pipe: send-only end of a pipe to main process
    
    The worker hashes nonces: worker_id, worker_id+stride, worker_id+2*stride, ...
    When it finds a valid nonce, it sends (job_id, nonce) through the pipe.
    Every 500k hashes it sends a stats update.
    """
    prefix, target, job_id = job_data
    nonce = worker_id
    hashes = 0
    
    while True:
        # SHA-256d — tight loop, no IPC
        header = prefix + nonce.to_bytes(4, 'little')
        h = hashlib.sha256(hashlib.sha256(header).digest()).digest()
        
        if int.from_bytes(h, "big") <= target:
            try:
                result_pipe.send(("share", job_id, nonce))
            except Exception:
                return  # Pipe broken, exit
        
        hashes += 1
        if hashes % 500000 == 0:
            try:
                result_pipe.send(("stats", hashes))
            except Exception:
                return
        
        nonce += stride
        if nonce < 0:
            # Overflow — wrap around
            nonce = worker_id


# ---------------------------------------------------------------------------
# Stratum client (main process)
# ---------------------------------------------------------------------------

class StratumClient:
    def __init__(self):
        self.sock = None
        self.buf = b""
        self.extranonce1 = b""
        self.current_job = None
    
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
        
        en2 = struct.pack("<I", 0)
        coinbase = coinb1 + self.extranonce1 + en2 + coinb2
        h1 = hashlib.sha256(coinbase).digest()
        merkle = hashlib.sha256(h1).digest()
        
        prefix = (struct.pack("<I", version)
                  + prevhash + merkle
                  + struct.pack("<II", ntime, bits))
        
        self.current_job = {
            "job_id": job_id,
            "target": target,
            "prefix": prefix,
            "bits": bits,
            "ntime": ntime,
            "en2": en2,
        }
    
    def listen_loop(self):
        while True:
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
    
    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


def run_miner_cycle(client):
    """
    Run one mining cycle: spawn workers, collect results until new job arrives.
    Returns (total_hashes, shares_found, blocks_found).
    """
    job = client.current_job
    if not job:
        return 0, 0, 0
    
    job_id = job["job_id"]
    prefix = job["prefix"]
    target = job["target"]
    en2 = job["en2"]
    ntime = job["ntime"]
    
    # Create pipes for each worker
    pipes = []
    workers = []
    for i in range(THREADS):
        parent_conn, child_conn = mp.Pipe(duplex=False)
        p = mp.Process(
            target=hash_worker,
            args=(i, THREADS, (prefix, target, job_id), child_conn),
            daemon=True
        )
        p.start()
        child_conn.close()  # Worker has its end; close parent's copy
        workers.append(p)
        pipes.append(parent_conn)
    
    total_hashes = 0
    shares = 0
    blocks = 0
    start = time.time()
    
    # Collect results from all workers
    while True:
        # Check for new job (non-blocking via socket timeout)
        line = client.recv_line()
        if line:
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                msg = None
            
            if msg and msg.get("method") == "mining.notify":
                client._handle_push(msg)
                if client.current_job["job_id"] != job_id:
                    # New job — terminate workers and restart
                    break
        
        # Collect results from workers (non-blocking)
        for pipe in pipes:
            while pipe.poll():
                try:
                    result = pipe.recv()
                except Exception:
                    continue
                
                if result[0] == "stats":
                    total_hashes += result[1]
                elif result[0] == "share":
                    _, share_job_id, nonce = result
                    ok = client.submit(share_job_id, en2, ntime, nonce)
                    shares += 1
                    if ok:
                        blocks += 1
                        log(f"BLOCK FOUND! nonce={nonce}")
        
        # Safety: if all workers died, break
        if not any(w.is_alive() for w in workers):
            break
        
        # Periodic stats
        elapsed = time.time() - start
        if elapsed > 5:
            hr = total_hashes / elapsed if elapsed > 0 else 0
            log(f"hashrate: {hr/1e6:.2f} MH/s  "
                  f"cycle: H={total_hashes} S={shares} B={blocks}")
            start = time.time()
    
    # Terminate workers
    for p in workers:
        p.terminate()
        p.join(timeout=1)
    
    return total_hashes, shares, blocks


def main():
    log(f"CPU miner (multiprocessing) starting: {THREADS} workers, worker={WORKER} (non-stop)")
    global_start = time.time()
    reconnect_delay = 1
    grand_total_hashes = 0
    grand_total_shares = 0
    grand_total_blocks = 0
    
    mp.set_start_method("spawn", force=True)
    
    while True:
        client = StratumClient()
        
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
                
                # Start listener in a thread for job notifications
                import threading
                listener = threading.Thread(target=client.listen_loop, daemon=True)
                listener.start()
                
                log("waiting for first job...")
                for _ in range(60):
                    job = client.current_job
                    if job:
                        log(f"first job: {job['job_id']} bits {job['bits']:#010x}")
                        break
                    time.sleep(1)
                else:
                    log("timeout waiting for first job - reconnecting")
                    client.close()
                    reconnect_delay = 1
                    break
                
                log(f"mining with {THREADS} worker processes...")
                
                # Mining loop: run cycles until disconnect
                try:
                    while True:
                        h, s, b = run_miner_cycle(client)
                        grand_total_hashes += h
                        grand_total_shares += s
                        grand_total_blocks += b
                        
                        if not client.current_job:
                            break
                        
                        elapsed = time.time() - global_start
                        hr = grand_total_hashes / elapsed if elapsed > 0 else 0
                        log(f"total: {hr/1e6:.2f} MH/s  "
                              f"H={grand_total_hashes} S={grand_total_shares} B={grand_total_blocks}")
                except KeyboardInterrupt:
                    log("stopping...")
                    break
        
        except KeyboardInterrupt:
            log("stopping...")
        
        client.close()
        
        log(f"reconnecting in {reconnect_delay}s...")
        time.sleep(reconnect_delay)
        reconnect_delay = min(reconnect_delay * 2, 30)


if __name__ == "__main__":
    main()
