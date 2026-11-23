"""Free Hugging Face Gradio Space for the EXCAL Rosetta API.
Read-only. No wallet, mempool, transaction submission, or peer relay.
If no pre-existing chain file is mounted, report that honestly and never
let ChainState silently create a synthetic genesis.
"""
import os
from pathlib import Path
import gradio as gr
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import uvicorn

DATA_DIR = Path(os.environ.get("EXCAL_DATA_DIR", "/data/chaindata"))
NETWORK = os.environ.get("EXCAL_ROSETTA_NETWORK", "mainnet")
CHAIN_NETWORK = os.environ.get("EXCAL_CHAIN_NETWORK", "fork")
CHAIN_FILE = DATA_DIR / "chain.jsonl"
adapter = None
startup_error = None
if CHAIN_FILE.is_file() and CHAIN_FILE.stat().st_size > 0:
    try:
        from chainstate import ChainState
        from rosetta.excal_rosetta import ExcalRosetta
        chainstate = ChainState(str(DATA_DIR), net=CHAIN_NETWORK).load()
        # Deliberately omit mempool and Node: public Space is read-only.
        adapter = ExcalRosetta(chainstate, network=NETWORK)
    except Exception as exc:
        startup_error = f"Chain data was found but ChainState failed to load: {type(exc).__name__}: {exc}"
else:
    startup_error = (
        f"No existing non-empty {CHAIN_FILE} was found. Provide verified EXCAL chain data "
        "at EXCAL_DATA_DIR. This Space will not create a synthetic genesis or claim a tip."
    )

if adapter is not None:
    height = adapter._tip()[0]
    status = f"**EXCAL Rosetta is ready — read-only.** Network: `{NETWORK}`. Chain height: `{height}`."
else:
    status = f"**Waiting for verified chain data.**\n\n{startup_error}"
demo = gr.Blocks(title="EXCAL Rosetta API")
with demo:
    gr.Markdown("# ⚔️ EXCAL Rosetta API\nPublic read-only Rosetta Data API experiment on Hugging Face Spaces.")
    gr.Markdown(status)
    gr.Markdown("Endpoints: `/network/list`, `/network/options`, `/network/status`, `/block`, `/block/transaction`, `/account/balance`, `/health`.\n\nNo signing keys, wallet, mempool admission, transaction submission, or P2P relay are exposed.")

api = FastAPI(title="EXCAL Rosetta API", version="1.0.0")
@api.get("/health")
async def health():
    if adapter is None:
        return JSONResponse(status_code=503, content={"ok": False, "state": "waiting_for_chain_data", "error": startup_error})
    try:
        height, block_hash = adapter._tip()
        shown_hash = block_hash.hex() if isinstance(block_hash, bytes) else str(block_hash)
        return {"ok": True, "state": "read_only", "height": height, "block_hash": shown_hash}
    except Exception as exc:
        return JSONResponse(status_code=503, content={"ok": False, "error": str(exc)[:200]})

@api.post("/{endpoint:path}")
async def rosetta_endpoint(endpoint: str, request: Request):
    if adapter is None:
        raise HTTPException(status_code=503, detail=startup_error)
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError("request body must be a JSON object")
        code, result = adapter.handle("/" + endpoint, body)
        return JSONResponse(status_code=code, content=result)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)[:256])

app = gr.mount_gradio_app(api, demo, path="/")
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "7860")))
