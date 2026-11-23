#!/usr/bin/env python3
"""Hugging Face Spaces entrypoint for the EXCAL Rosetta API.

Fails closed when no existing chain data is mounted; never creates a fake genesis.
"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "7860"))
DATA_DIR = os.environ.get("EXCAL_DATA_DIR", "/data/chaindata")
NETWORK = os.environ.get("EXCAL_ROSETTA_NETWORK", "mainnet")
CHAIN_NETWORK = os.environ.get("EXCAL_CHAIN_NETWORK", "fork")


def has_chain_data():
    path = os.path.join(DATA_DIR, "chain.jsonl")
    return os.path.isfile(path) and os.path.getsize(path) > 0


if has_chain_data():
    from chainstate import ChainState
    from rosetta.excal_rosetta import serve
    chainstate = ChainState(DATA_DIR, net=CHAIN_NETWORK).load()
    # Read-only mode: do not attach wallet, mempool, or node submit/relay interfaces.
    serve(chainstate, host="0.0.0.0", port=PORT, network=NETWORK)
else:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            payload = {
                "ok": False,
                "service": "EXCAL Rosetta API",
                "state": "waiting_for_chain_data",
                "chain_data_dir": DATA_DIR,
                "message": "No existing chain.jsonl found. Mount or provide verified EXCAL chain data; this service will not create a synthetic genesis or report a fabricated tip.",
            }
            raw = json.dumps(payload).encode()
            self.send_response(503 if self.path == "/health" else 503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
