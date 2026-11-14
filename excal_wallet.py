#!/usr/bin/env python3
"""Experimental EXCAL desktop wallet.

This GUI wallet is not production-ready: its Trifold PQH signature scheme
has not been independently audited, and the bundled node may not have a
complete validated UTXO set. Do not use it to custody valuable funds.

Features:
- Aetherion-themed CustomTkinter UI with gradient accents and animations
- Encrypted key storage (AES-256-GCM + scrypt KDF)
- On-chain balance and transaction submission through the local node RPC
- Experimental PQH send/receive support
- Peer count reported by the connected node
- Multi-wallet profiles with cinematic login
- Prometheus metrics on port 9435
- Onboarding wizard for new users
- Integrated help panel

Usage:
    python excal_wallet.py

Build (Windows):
    pyinstaller AetherionEXCAL.spec

Build (Mac):
    ./build_aetherion.sh

"""

import sys
import os
import json
import hashlib
import time
import secrets
import threading
import math
import subprocess
import http.client
import logging
from decimal import Decimal
from pathlib import Path
from typing import Optional, Dict, Any, List

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import customtkinter as ctk
from tkinter import messagebox, filedialog, Canvas, PhotoImage

from sphinx_os.nexus import (
    HolographicP2PLayer,
    MessagePriority,
    EREPRProtocol,
    EchoMessage,
    GossipWave,
)
from sphinx_os.secure_store import KeyStore
from sphinx_os.prometheus_metrics import get_metrics, start_http_server
from genesis_fork import SWORD
from wallet_transactions import (
    address_lock,
    amount_to_swords,
    build_pqh_transaction,
    create_pqh_key,
)

logger = logging.getLogger("excal_wallet")


# ---------------------------------------------------------------------------
# Node Manager — Starts/stops the fork node RPC server
# ---------------------------------------------------------------------------

class NodeManager:
    """Manages the EXCAL fork node RPC server as a background process.
    
    In a PyInstaller single-file build, the node is extracted and run as
    a child process. In development, it imports fork_node directly.
    """
    
    RPC_PORT = 9432
    
    def __init__(self):
        self.process = None
        self.running = False
        self.server = None
        self.p2p_node = None
        self._stop_event = threading.Event()
        self._health_check_thread = None
        self.chain_file = Path(os.path.dirname(os.path.abspath(__file__))) / "chain.jsonl"
        # In PyInstaller, __file__ is inside the extracted _MEI temp dir
        # We need to find chain.jsonl relative to the executable
        if hasattr(sys, "_MEIPASS"):
            # PyInstaller runtime
            self._meipass = Path(sys._MEIPASS)
            # Look for chain.jsonl in the executable's directory
            exe_dir = Path(sys.executable).parent
            self.chain_file = exe_dir / "chain.jsonl"
            if not self.chain_file.exists():
                # Try current working directory
                self.chain_file = Path.cwd() / "chain.jsonl"
        
    def start(self) -> bool:
        """Start the fork node RPC server. Returns True if started."""
        if self.running:
            return True
        
        # Ensure chain file exists
        if not self.chain_file.exists():
            # Create a minimal genesis chain file
            try:
                self.chain_file.parent.mkdir(parents=True, exist_ok=True)
                import genesis_fork
                genesis_fork.main()
            except Exception:
                pass
        
        if not self.chain_file.exists():
            return False
        
        try:
            # Determine how to run the node
            if hasattr(sys, "_MEIPASS"):
                # PyInstaller: extract and run fork_node.py
                node_script = self._meipass / "fork_node.py"
                if node_script.exists():
                    env = {**os.environ, "EXCAL_WORKSPACE": str(Path.cwd())}
                    self.process = subprocess.Popen(
                        [sys.executable, str(node_script)],
                        env=env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                    )
                else:
                    return False
            else:
                # Development: run in thread
                self._start_in_thread()
            
            self.running = True
            self._stop_event.clear()
            
            # Start health check
            self._health_check_thread = threading.Thread(
                target=self._health_check_loop, daemon=True
            )
            self._health_check_thread.start()
            
            # Wait briefly for server to start
            time.sleep(1)
            return self.is_healthy()
        except Exception:
            return False
    
    def _start_in_thread(self):
        """Start the fork node in a background thread (development mode)."""
        def run_node():
            try:
                import fork_node
                fork_node.CHAIN_FILE = str(self.chain_file)
                fork_node.RPC_PORT = self.RPC_PORT
                
                store = fork_node.ChainStore(str(self.chain_file))
                fork_node.ForkRPCHandler.store = store
                p2p_layer, p2p_host, p2p_port, seed_peers, advertise_host, allow_private = (
                    fork_node._load_p2p_settings()
                )
                p2p_layer.setup_logging()
                self.p2p_node = p2p_layer.P2PNode(
                    store,
                    seed_peers=seed_peers,
                    listen_host=p2p_host,
                    listen_port=p2p_port,
                    advertise_host=advertise_host,
                    allow_private_peers=allow_private,
                )
                self.p2p_node.start()
                fork_node.ForkRPCHandler.p2p_node = self.p2p_node
                self.server = fork_node.ThreadedHTTPServer(
                    ("127.0.0.1", self.RPC_PORT), fork_node.ForkRPCHandler
                )
                self.server.serve_forever(poll_interval=0.25)
            except Exception:
                logger.exception("Failed to run the local EXCAL node")
            finally:
                if self.server:
                    self.server.server_close()
                    self.server = None
                if self.p2p_node:
                    self.p2p_node.stop()
                    self.p2p_node = None
        
        self.process = threading.Thread(target=run_node, daemon=True)
        self.process.start()
    
    def stop(self):
        """Stop the fork node RPC server."""
        self._stop_event.set()
        self.running = False
        if self.server:
            self.server.shutdown()
        
        if self.process:
            if isinstance(self.process, subprocess.Popen):
                try:
                    self.process.terminate()
                    self.process.wait(timeout=5)
                except Exception:
                    try:
                        self.process.kill()
                    except Exception:
                        pass
            self.process = None
    
    def is_healthy(self) -> bool:
        """Check if the node RPC server is responding."""
        try:
            import http.client
            c = http.client.HTTPConnection("127.0.0.1", self.RPC_PORT, timeout=2)
            c.request("POST", "/", json.dumps({
                "method": "getblockcount",
                "params": [],
                "id": 1
            }))
            resp = c.getresponse()
            c.close()
            return resp.status == 200
        except Exception:
            return False
    
    def _health_check_loop(self):
        """Periodically check node health."""
        while not self._stop_event.is_set():
            self._stop_event.wait(10)
            if self.running:
                self.is_healthy()
    
    def get_status(self) -> Dict[str, Any]:
        """Get node status information."""
        return {
            "running": self.running,
            "healthy": self.is_healthy() if self.running else False,
            "rpc_port": self.RPC_PORT,
            "chain_file": str(self.chain_file),
        }


# ---------------------------------------------------------------------------
# Aetherion-Inspired Color Palette
# ---------------------------------------------------------------------------

# Deep space background — near black with purple undertone
COLOR_BG_DEEP = "#0A0A12"
COLOR_BG = "#0D0D1A"
COLOR_BG_LIGHT = "#141428"

# Glassmorphism card surfaces
COLOR_CARD = "#1A1A2E"
COLOR_CARD_LIGHT = "#222240"
COLOR_CARD_HOVER = "#2A2A4A"
COLOR_GLASS = "#1E1E38CC"  # Semi-transparent glass

# Electric purple — primary Aetherion accent
COLOR_PURPLE = "#7B2FF7"
COLOR_PURPLE_LIGHT = "#9B59FF"
COLOR_PURPLE_DARK = "#5A1DB8"
COLOR_PURPLE_GLOW = "#A855F7"

# Electric cyan — secondary accent
COLOR_CYAN = "#00D4FF"
COLOR_CYAN_LIGHT = "#33DDFF"
COLOR_CYAN_DARK = "#0099CC"
COLOR_CYAN_GLOW = "#00E5FF"

# Gold — Excalibur branding accent
COLOR_GOLD = "#FFD700"
COLOR_GOLD_LIGHT = "#FFE44D"
COLOR_GOLD_DARK = "#CCB000"

# Text colors
COLOR_TEXT = "#F0F0FF"
COLOR_TEXT_DIM = "#8888AA"
COLOR_TEXT_MUTED = "#555577"

# Status colors
COLOR_SUCCESS = "#00E676"
COLOR_ERROR = "#FF4757"
COLOR_WARNING = "#FFA502"
COLOR_INFO = "#00D4FF"

# Gradient colors for buttons and accents
GRADIENT_PURPLE_START = "#7B2FF7"
GRADIENT_PURPLE_END = "#00D4FF"
GRADIENT_GOLD_START = "#FFD700"
GRADIENT_GOLD_END = "#FF8C00"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WALLET_DIR = Path(os.path.expanduser("~/.excal_wallet"))
KEYSTORE_FILE = WALLET_DIR / "keystore.json"
APP_VERSION = "2.1.0"
APP_NAME = "EXCAL Wallet (Experimental)"

# Support multiple wallet profiles
WALLET_PROFILES_DIR = WALLET_DIR / "profiles"


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def sha256_hex(data: str) -> str:
    """Compute SHA-256 hex digest of a string."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def generate_address(seed: str) -> str:
    """Derive the fork-chain PQH address for a 32-byte seed."""
    try:
        seed_bytes = bytes.fromhex(seed)
    except ValueError as exc:
        raise ValueError("wallet seed must be hexadecimal") from exc
    return create_pqh_key(seed_bytes)["address"]


def validate_address(addr: str) -> bool:
    """Validate an EXCAL wallet address.
    
    A valid address is exactly 40 uppercase hexadecimal characters and
    represents the hash160 committed by a fork-chain PQH lock.
    """
    if not addr or len(addr) != 40:
        return False
    try:
        address_lock(addr)
        return True
    except (ValueError, TypeError):
        return False


def generate_keypair() -> Dict[str, str]:
    """Generate a PQH key rooted in the chain's Trifold spend format."""
    return create_pqh_key()


def sign_transaction(private_key: str, tx_data: Dict[str, Any]) -> str:
    raise RuntimeError(
        "Signing arbitrary JSON is not a consensus transaction. "
        "Use WalletBackend.send_transaction."
    )


def format_address(addr: str) -> str:
    """Format an address for display (truncate middle)."""
    if len(addr) <= 12:
        return addr
    return addr[:6] + "..." + addr[-4:]


def format_balance(balance: Any) -> str:
    """Format an EXCAL amount to sword precision (8 decimal places)."""
    return f"{Decimal(str(balance)):,.8f}"


# ---------------------------------------------------------------------------
# Animated Background Canvas
# ---------------------------------------------------------------------------

class AnimatedBackground(Canvas):
    """Canvas that draws animated orbital rings and particles."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=COLOR_BG, highlightthickness=0, **kwargs)
        self.particles = []
        self.rings = []
        self.angle = 0
        self._init_particles()
        self._animate()

    def _get_canvas_size(self):
        """Get current canvas dimensions, falling back to defaults."""
        width = self.winfo_width() if self.winfo_width() > 1 else 800
        height = self.winfo_height() if self.winfo_height() > 1 else 600
        return width, height

    def _init_particles(self):
        """Initialize floating particles."""
        width, height = self._get_canvas_size()
        for _ in range(50):
            x = secrets.randbelow(max(width, 100))
            y = secrets.randbelow(max(height, 100))
            r = secrets.choice([1, 1, 2, 2, 3])
            color = secrets.choice([COLOR_PURPLE, COLOR_CYAN, COLOR_GOLD, COLOR_TEXT_MUTED])
            speed = secrets.randbelow(3) + 1
            self.particles.append({
                "id": self.create_oval(x, y, x + r * 2, y + r * 2, fill=color, outline=""),
                "x": x, "y": y, "r": r, "speed": speed,
                "dx": (secrets.randbelow(3) - 1) * 0.3,
                "dy": (secrets.randbelow(3) - 1) * 0.3,
            })

    def _animate(self):
        """Animation loop for particles."""
        width, height = self._get_canvas_size()
        for p in self.particles:
            p["x"] += p["dx"]
            p["y"] += p["dy"]
            # Wrap around using dynamic dimensions
            if p["x"] < 0:
                p["x"] = width
            if p["x"] > width:
                p["x"] = 0
            if p["y"] < 0:
                p["y"] = height
            if p["y"] > height:
                p["y"] = 0
            self.coords(p["id"], p["x"], p["y"], p["x"] + p["r"] * 2, p["y"] + p["r"] * 2)
        self.after(50, self._animate)


# ---------------------------------------------------------------------------
# Gradient Button
# ---------------------------------------------------------------------------

class GradientButton(ctk.CTkFrame):
    """A button with gradient background effect."""

    def __init__(self, parent, text="", command=None, gradient_colors=(GRADIENT_PURPLE_START, GRADIENT_PURPLE_END),
                 width=200, height=45, font=("Segoe UI", 13, "bold"), **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.command = command
        self.canvas = Canvas(self, width=width, height=height, highlightthickness=0, bg="transparent")
        self.canvas.pack(fill="both", expand=True)

        # Draw gradient
        self.grad_id = self.canvas.create_rectangle(0, 0, width, height, fill=gradient_colors[0], outline="")
        self.text_id = self.canvas.create_text(width // 2, height // 2, text=text, fill=COLOR_TEXT, font=font)

        # Bind events
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Enter>", self._enter)
        self.canvas.bind("<Leave>", self._leave)
        self.gradient_colors = gradient_colors
        self.width = width
        self.height = height

    def _click(self, event):
        if self.command:
            self.command()

    def _enter(self, event):
        self.canvas.itemconfig(self.grad_id, fill=self.gradient_colors[1])
        self.canvas.itemconfig(self.text_id, fill=COLOR_GOLD_LIGHT)

    def _leave(self, event):
        self.canvas.itemconfig(self.grad_id, fill=self.gradient_colors[0])
        self.canvas.itemconfig(self.text_id, fill=COLOR_TEXT)


# ---------------------------------------------------------------------------
# Glow Label
# ---------------------------------------------------------------------------

class GlowLabel(ctk.CTkLabel):
    """Label with animated glow effect."""

    def __init__(self, parent, glow_color=COLOR_PURPLE_GLOW, **kwargs):
        super().__init__(parent, **kwargs)
        self.glow_color = glow_color
        self._glow_phase = 0
        self._animate_glow()

    def _animate_glow(self):
        """Pulse the glow color."""
        self._glow_phase += 0.05
        # Cycle text color between base and glow color
        intensity = (math.sin(self._glow_phase) + 1) / 2  # 0 to 1
        if intensity > 0.7:
            self.configure(text_color=self.glow_color)
        self.after(100, self._animate_glow)


# ---------------------------------------------------------------------------
# Glassmorphism Card
# ---------------------------------------------------------------------------

class GlassCard(ctk.CTkFrame):
    """A card with glassmorphism-like appearance."""

    def __init__(self, parent, corner_radius=16, **kwargs):
        kwargs.setdefault("fg_color", COLOR_CARD)
        kwargs.setdefault("corner_radius", corner_radius)
        super().__init__(parent, **kwargs)
        # Subtle border effect
        self.configure(border_width=1, border_color=COLOR_PURPLE_DARK)


# ---------------------------------------------------------------------------
# Wallet Backend (unchanged logic)
# ---------------------------------------------------------------------------

class WalletBackend:
    """Backend logic for the EXCAL wallet."""

    def __init__(self, profile: str = "default"):
        self.profile = profile
        self.keystore: Optional[KeyStore] = None
        self._passphrase: Optional[str] = None
        self._initialized = False
        self.p2p = None
        self.erepr = None

        # Determine keystore path
        if profile == "default":
            self.keystore_path = KEYSTORE_FILE
        else:
            if (not profile or profile in (".", "..")
                    or any(char not in
                           "abcdefghijklmnopqrstuvwxyz"
                           "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                           "0123456789_-" for char in profile)):
                raise ValueError("Invalid wallet profile name")
            self.keystore_path = WALLET_PROFILES_DIR / f"{profile}.json"

    @staticmethod
    def list_profiles() -> List[Dict[str, str]]:
        """List available wallet profiles."""
        profiles = []
        # Check default
        if KEYSTORE_FILE.exists():
            profiles.append({"name": "default", "label": "Default"})
        # Check profiles directory
        if WALLET_PROFILES_DIR.exists():
            for f in WALLET_PROFILES_DIR.glob("*.json"):
                name = f.stem
                profiles.append({"name": name, "label": name.title()})
        return profiles

    def wallet_exists(self) -> bool:
        """Check if a wallet exists for this profile."""
        return self.keystore_path.exists()

    def create_wallet(self, passphrase: str):
        """Create a new wallet."""
        if self.wallet_exists():
            raise FileExistsError(
                f"Wallet already exists at {self.keystore_path}; "
                "unlock it or choose another profile"
            )
        self.keystore_path.parent.mkdir(parents=True, exist_ok=True)
        self.keystore = KeyStore.create(passphrase, str(self.keystore_path))
        self._passphrase = passphrase
        # Generate initial key
        kp = generate_keypair()
        self.keystore.add_key(kp["private_key"], kp["public_key"], kp["address"], "Main Key")
        self.keystore.save(str(self.keystore_path))
        self._initialized = True
        self.initialize_p2p()

    def open_wallet(self, passphrase: str):
        """Open an existing wallet."""
        self.keystore = KeyStore.load(str(self.keystore_path), passphrase)
        self._passphrase = passphrase
        self._initialized = True
        self.initialize_p2p()

    def get_address(self) -> Optional[str]:
        """Get the primary wallet address."""
        if not self.keystore or not self.keystore.keys:
            return None
        return self.keystore.keys[0].address

    def _wallet_utxos(self) -> List[Dict[str, Any]]:
        if not self.keystore:
            raise RuntimeError("Wallet not unlocked")
        addresses = [key.address for key in self.keystore.keys]
        if not addresses:
            raise RuntimeError("No keys available")
        if any(not validate_address(address) for address in addresses):
            raise RuntimeError(
                "This wallet contains demo-format keys that are not valid "
                "EXCAL addresses. Create a new EXCAL wallet; simulated "
                "balances and transactions cannot be migrated."
            )
        response = self._rpc("getwalletutxos", [addresses])
        if not isinstance(response, dict) or response.get("complete") is not True:
            raise RuntimeError(response.get(
                "error", "Node has no complete validated UTXO state"
            ) if isinstance(response, dict) else
                "Node returned an invalid wallet UTXO response")
        utxos = response.get("utxos")
        if not isinstance(utxos, list):
            raise RuntimeError("Node returned an invalid wallet UTXO list")
        owned_locks = {address_lock(address) for address in addresses}
        for item in utxos:
            if not isinstance(item, dict):
                raise RuntimeError("Node returned a malformed wallet UTXO")
            try:
                lock = bytes.fromhex(item["script"])
                value = item["value"]
                txid = bytes.fromhex(item["txid"])
                vout = item["vout"]
                height = item["height"]
                tip_height = item["tip_height"]
                coinbase = item["coinbase"]
                mature = item["mature"]
                pending_spend = item["pending_spend"]
                spendable = item["spendable"]
                if (lock not in owned_locks or not isinstance(value, int)
                        or isinstance(value, bool) or value < 0
                        or len(txid) != 32
                        or not isinstance(vout, int)
                        or isinstance(vout, bool) or vout < 0
                        or not isinstance(height, int)
                        or isinstance(height, bool) or height < 0
                        or not isinstance(tip_height, int)
                        or isinstance(tip_height, bool)
                        or tip_height < height
                        or not isinstance(coinbase, bool)
                        or not isinstance(mature, bool)
                        or not isinstance(pending_spend, bool)
                        or not isinstance(spendable, bool)):
                    raise ValueError
                import txscript
                expected_mature = (
                    not coinbase
                    or tip_height + 1 - height >= txscript.COINBASE_MATURITY
                )
                if (mature != expected_mature
                        or spendable != (mature and not pending_spend)):
                    raise ValueError
            except (KeyError, TypeError, ValueError) as exc:
                raise RuntimeError(
                    "Node returned a malformed or unowned wallet UTXO"
                ) from exc
        return utxos

    def get_balance(self) -> Decimal:
        """Return the confirmed on-chain balance for all wallet keys."""
        swords = sum(item["value"] for item in self._wallet_utxos())
        return Decimal(swords) / Decimal(SWORD)

    def get_keys(self) -> List[Dict[str, str]]:
        """Get all key entries."""
        if not self.keystore:
            return []
        return [{"address": k.address, "public_key": k.public_key, "label": k.label} for k in self.keystore.keys]

    def generate_new_key(self, label: str = "") -> Dict[str, str]:
        """Generate a new key pair and store it."""
        if not self.keystore or not self._passphrase:
            raise RuntimeError("Wallet not unlocked")
        kp = generate_keypair()
        entry = self.keystore.add_key(kp["private_key"], kp["public_key"], kp["address"], label)
        self.keystore.save(str(self.keystore_path))
        return {"address": entry.address, "public_key": entry.public_key, "label": entry.label}

    def send_transaction(self, to_address: str, amount: Any) -> Dict[str, Any]:
        """Build, sign, and broadcast a consensus-format PQH transaction."""
        if not self.keystore or not self._passphrase:
            raise RuntimeError("Wallet not unlocked")
        if not self.keystore.keys:
            raise RuntimeError("No keys available")
        if not validate_address(to_address):
            raise ValueError(
                "Invalid address: expected 40 uppercase hexadecimal characters"
            )
        amount_swords = amount_to_swords(amount)
        keys = []
        for entry in self.keystore.keys:
            private_key = self.keystore.get_key(
                entry.address, self._passphrase)
            if not private_key:
                raise RuntimeError(
                    f"Unable to unlock the private key for {entry.address}")
            try:
                seed = bytes.fromhex(private_key)
            except ValueError as exc:
                raise RuntimeError(
                    "This key is not a supported PQH wallet key; "
                    "import it into a compatible wallet before spending"
                ) from exc
            keys.append({"seed": seed, "address": entry.address})
        from_addr = keys[0]["address"]
        tx_bytes = build_pqh_transaction(
            seed=None,
            address=None,
            utxos=self._wallet_utxos(),
            recipient=to_address,
            amount=amount,
            state_dir=str(self.keystore_path.parent / "trifold"),
            registry_path=str(self.keystore_path.parent / "spent_leaves.jsonl"),
            keys=keys,
        )
        txid = self._rpc("sendrawtransaction", [tx_bytes.hex()])
        import txscript
        expected_txid = txscript.txid_display(tx_bytes)
        if txid != expected_txid:
            raise RuntimeError(
                "Node broadcast outcome is uncertain: returned txid does "
                "not match the locally built transaction"
            )
        tx_data = {
            "tx_id": txid,
            "from": from_addr,
            "to": to_address,
            "amount": format(Decimal(amount_swords) / Decimal(SWORD), "f"),
            "status": "node_accepted_unconfirmed",
            "timestamp": time.time(),
        }
        self.keystore.add_transaction(tx_data)
        self.keystore.save(str(self.keystore_path))
        return tx_data

    @staticmethod
    def _rpc(method: str, params=None):
        """Call the local node RPC and surface connection and node errors."""
        host = os.environ.get("EXCAL_RPC_HOST", "127.0.0.1")
        try:
            port = int(os.environ.get("EXCAL_RPC_PORT", "9432"))
        except ValueError as exc:
            raise ValueError("EXCAL_RPC_PORT must be a valid TCP port") from exc
        if not 1 <= port <= 65535:
            raise ValueError("EXCAL_RPC_PORT must be between 1 and 65535")
        connection = http.client.HTTPConnection(host, port, timeout=10)
        try:
            body = json.dumps({
                "jsonrpc": "2.0",
                "method": method,
                "params": params or [],
                "id": 1,
            })
            connection.request(
                "POST", "/", body,
                {"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            raw_payload = response.read()
            try:
                payload = json.loads(raw_payload)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuntimeError("Node RPC returned invalid JSON") from exc
            if not isinstance(payload, dict):
                raise RuntimeError("Node RPC returned an invalid response")
            if response.status != 200 or payload.get("error"):
                raise RuntimeError(
                    payload.get("error") or f"RPC returned HTTP {response.status}"
                )
            if "result" not in payload:
                raise RuntimeError("Node RPC response is missing its result")
            return payload.get("result")
        except (OSError, http.client.HTTPException) as exc:
            raise ConnectionError(
                f"Unable to reach the EXCAL node RPC at {host}:{port}: {exc}"
            ) from exc
        finally:
            connection.close()

    def get_transactions(self) -> List[Dict[str, Any]]:
        """Get transaction history."""
        if not self.keystore:
            return []
        return self.keystore.get_transactions()

    def initialize_p2p(self, num_peers: int = 6):
        """Networking is provided by the real connected node, not fake peers."""
        self.p2p = None
        self.erepr = None

    def get_network_status(self) -> Dict[str, Any]:
        """Return peer count from the connected node's live RPC."""
        status = self._rpc("getnetworkinfo")
        if not isinstance(status, dict):
            raise RuntimeError("Node returned an invalid network status")
        status["active_peers"] = int(status.get("connections", 0))
        return status
    
    def get_erepr_peers(self) -> List[Dict[str, Any]]:
        return self._rpc("getpeerinfo")
    
    def broadcast_erepr_gossip(self, payload: Dict[str, Any]) -> str:
        raise RuntimeError("EREPR wallet gossip RPC is not implemented by this node")

    def get_peers(self) -> List[Dict[str, Any]]:
        return self._rpc("getpeerinfo")

    def broadcast_gossip(self, message: str) -> bool:
        raise RuntimeError("Arbitrary wallet gossip is not supported by the node")

    def send_encrypted_message(self, to_peer: str, message: str) -> bool:
        raise RuntimeError("Encrypted peer messaging is not implemented by the node")

    def _broadcast_transaction(self, tx: Dict[str, Any]):
        raise RuntimeError("Broadcast transactions with the node sendrawtransaction RPC")

    def deposit(self, amount: float):
        raise RuntimeError(
            "Wallet balances can only change through confirmed chain transactions"
        )

    def close(self):
        """Close the wallet (clear passphrase from memory)."""
        self._passphrase = None
        self._initialized = False


# ---------------------------------------------------------------------------
# Login Window — Cinematic Aetherion Style
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Onboarding Wizard — First-Time User Guide
# ---------------------------------------------------------------------------

class OnboardingWizard(ctk.CTkToplevel):
    """Step-by-step onboarding wizard for new users."""

    STEPS = [
        {
            "icon": "⚔",
            "title": "Welcome to EXCALibur",
            "body": (
                "This experimental wallet creates EXCAL PQH addresses and uses "
                "an encrypted local keystore. Verify the node and chain status "
                "before relying on any displayed balance."
            ),
        },
        {
            "icon": "🔐",
            "title": "Your Keys, Your Control",
            "body": (
                "Every private key is encrypted at rest using scrypt key derivation "
                "and AES-256-GCM. Your passphrase is the only thing that unlocks them — "
                "we never store it. Choose a strong passphrase and never share it."
            ),
        },
        {
            "icon": "🌐",
            "title": "Node Connection",
            "body": (
                "Wallet balances and transaction submission use the configured "
                "EXCAL node RPC. Peer counts are reported by that node; this "
                "wallet does not simulate peers or encrypt node RPC traffic."
            ),
        },
        {
            "icon": "💰",
            "title": "Send & Receive EXCAL",
            "body": (
                "Transactions are built and validated locally, then submitted "
                "to the node. EXCAL is the chain's native token and is measured "
                "in swords (100,000,000 swords = 1 EXCAL). URUU on zkSync Era "
                "and SKYNT BRC-20 are separate assets and are not supported here. "
                "The Trifold signature scheme is experimental and unaudited."
            ),
        },
        {
            "icon": "🚀",
            "title": "You're Ready!",
            "body": (
                "Create your wallet below to get started. You can always return to this "
                "guide from the Help button in the sidebar. Welcome to the Excalibur Chain!"
            ),
        },
    ]

    def __init__(self, parent: "EXCALWallet"):
        super().__init__(parent)
        self.parent = parent
        self.current_step = 0

        self.title("Welcome to EXCALibur")
        self.geometry("560x480")
        self.resizable(False, False)
        self.grab_set()
        self.transient(parent)
        self.lift()
        self.configure(fg_color=COLOR_BG_DEEP)

        # Background particles
        self.bg_canvas = AnimatedBackground(self, width=560, height=480)
        self.bg_canvas.place(x=0, y=0, relwidth=1, relheight=1)

        # Main card
        self.card = GlassCard(self, corner_radius=20)
        self.card.place(relx=0.5, rely=0.5, anchor="center", width=480, height=420)

        # Step indicator dots
        self.dots_frame = ctk.CTkFrame(self.card, fg_color="transparent")
        self.dots_frame.pack(pady=(15, 0))
        self.dots = []
        for i in range(len(self.STEPS)):
            dot = ctk.CTkLabel(
                self.dots_frame, text="●", font=("Segoe UI", 8),
                text_color=COLOR_TEXT_MUTED,
            )
            dot.pack(side="left", padx=4)
            self.dots.append(dot)

        # Content area
        self.content_frame = ctk.CTkFrame(self.card, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True, padx=30, pady=10)

        # Buttons
        self.btn_frame = ctk.CTkFrame(self.card, fg_color="transparent")
        self.btn_frame.pack(fill="x", padx=30, pady=(10, 15))

        self.prev_btn = ctk.CTkButton(
            self.btn_frame, text="← Back", command=self._prev,
            fg_color=COLOR_CARD_LIGHT, hover_color=COLOR_CARD_HOVER,
            text_color=COLOR_TEXT_DIM, font=("Segoe UI", 11),
            corner_radius=8, height=34, width=100,
        )
        self.prev_btn.pack(side="left")

        self.next_btn = GradientButton(
            self.btn_frame, text="Next →", command=self._next,
            width=120, height=34,
            gradient_colors=(COLOR_PURPLE, COLOR_CYAN_DARK),
        )
        self.next_btn.pack(side="right")

        # Skip button
        self.skip_btn = ctk.CTkButton(
            self.btn_frame, text="Skip", command=self._skip,
            fg_color="transparent", text_color=COLOR_TEXT_MUTED,
            font=("Segoe UI", 10), hover_color=COLOR_CARD_HOVER,
        )
        self.skip_btn.pack(side="left", padx=(10, 0))

        self._show_step(0)

    def _show_step(self, step):
        self.current_step = step
        s = self.STEPS[step]

        # Clear content
        for w in self.content_frame.winfo_children():
            w.destroy()

        # Icon
        ctk.CTkLabel(
            self.content_frame, text=s["icon"],
            font=("Segoe UI Emoji", 48), text_color=COLOR_GOLD,
        ).pack(pady=(10, 10))

        # Title
        ctk.CTkLabel(
            self.content_frame, text=s["title"],
            font=("Segoe UI", 18, "bold"), text_color=COLOR_TEXT,
        ).pack(pady=(0, 10))

        # Divider
        ctk.CTkFrame(self.content_frame, height=1, fg_color=COLOR_PURPLE_DARK).pack(
            fill="x", pady=(0, 10)
        )

        # Body
        ctk.CTkLabel(
            self.content_frame, text=s["body"],
            font=("Segoe UI", 12), text_color=COLOR_TEXT_DIM,
            wraplength=400, justify="center",
        ).pack(pady=(0, 10))

        # Step counter
        ctk.CTkLabel(
            self.content_frame,
            text=f"Step {step + 1} of {len(self.STEPS)}",
            font=("Segoe UI", 10), text_color=COLOR_TEXT_MUTED,
        ).pack(pady=(5, 0))

        # Update dots
        for i, dot in enumerate(self.dots):
            if i < step:
                dot.configure(text_color=COLOR_CYAN)
            elif i == step:
                dot.configure(text_color=COLOR_GOLD)
            else:
                dot.configure(text_color=COLOR_TEXT_MUTED)

        # Update buttons
        self.prev_btn.configure(state="normal" if step > 0 else "disabled")

        if step == len(self.STEPS) - 1:
            self.next_btn.canvas.itemconfig(self.next_btn.text_id, text="⚔ Start")
            self.skip_btn.pack_forget()
        else:
            self.next_btn.canvas.itemconfig(self.next_btn.text_id, text="Next →")

    def _next(self):
        if self.current_step < len(self.STEPS) - 1:
            self._show_step(self.current_step + 1)
        else:
            # Last step — close and go to wallet creation
            self.destroy()

    def _prev(self):
        if self.current_step > 0:
            self._show_step(self.current_step - 1)

    def _skip(self):
        self.destroy()


# ---------------------------------------------------------------------------
# Help Panel — Context-Sensitive Help
# ---------------------------------------------------------------------------

class HelpPanel(ctk.CTkToplevel):
    """Help panel with quick tips and documentation links."""

    def __init__(self, parent: "EXCALWallet"):
        super().__init__(parent)
        self.parent = parent

        self.title("EXCALibur Help")
        self.geometry("500x550")
        self.resizable(True, True)
        self.transient(parent)
        self.lift()
        self.configure(fg_color=COLOR_BG_DEEP)

        # Header
        header = GlassCard(self, corner_radius=16)
        header.pack(fill="x", padx=15, pady=(15, 10))

        ctk.CTkLabel(
            header, text="❓ EXCALibur Help",
            font=("Segoe UI", 16, "bold"), text_color=COLOR_CYAN,
        ).pack(pady=(10, 5))

        ctk.CTkLabel(
            header, text="Quick guide to your wallet",
            font=("Segoe UI", 11), text_color=COLOR_TEXT_DIM,
        ).pack(pady=(0, 10))

        # Scrollable content
        content = ctk.CTkScrollableFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=15, pady=10)

        sections = [
            ("Getting Started", [
                ("Create a wallet", "Choose a profile name and strong passphrase. Keys are encrypted with AES-256-GCM."),
                ("Receive funds", "Use the receive address and verify the node reports a complete validated UTXO set."),
                ("Generate keys", "Create additional experimental PQH keys from the Dashboard or Settings tab."),
                ("Token support", "This wallet handles native EXCAL only (1 EXCAL = 100,000,000 swords). URUU on zkSync Era and SKYNT BRC-20 are separate assets and are not supported here."),
            ]),
            ("Sending Transactions", [
                ("Go to Send/Receive", "Enter the recipient's address and amount, then click Send Transaction."),
                ("Signatures", "PQH transactions use the experimental Trifold hash-based signature scheme; it has not been independently audited."),
                ("Broadcast", "Transactions are submitted to the configured EXCAL node. A successful response means node acceptance, not confirmation."),
            ]),
            ("P2P Network", [
                ("Peers tab", "View connected peers, network coherence, and message statistics."),
                ("Node status", "Peer counts come from the connected node. Arbitrary wallet gossip and encrypted peer messaging are not implemented."),
                ("RPC security", "Use only a trusted local node; this wallet's JSON-RPC connection is not encrypted or authenticated."),
            ]),
            ("Security", [
                ("Encryption", "All private keys are encrypted at rest using scrypt KDF + AES-256-GCM."),
                ("Passphrase", "Your passphrase is never stored. If you lose it, your wallet cannot be recovered."),
                ("Lock wallet", "Use the Lock button in Settings to clear your passphrase from memory."),
            ]),
            ("Multi-Wallet", [
                ("Profiles", "Create separate wallet profiles for different purposes (trading, savings, etc.)."),
                ("Switch wallets", "Lock your current wallet and unlock a different profile."),
                ("Export keys", "Export your public keys from Settings for sharing addresses."),
            ]),
            ("Links", [
                ("Aetherion Oracle", "www.aetherion-oracle.com"),
                ("SphinxOS Nexus", "Quantum blockchain operating system"),
                ("Holographic P2P", "v3.0 with Dijkstra max-entanglement routing"),
            ]),
        ]

        for section_title, items in sections:
            sec_card = GlassCard(content, corner_radius=12)
            sec_card.pack(fill="x", pady=4)

            ctk.CTkLabel(
                sec_card, text=f"  {section_title}",
                font=("Segoe UI", 13, "bold"), text_color=COLOR_GOLD,
            ).pack(anchor="w", padx=15, pady=(10, 5))

            for item_title, item_desc in items:
                row = ctk.CTkFrame(sec_card, fg_color="transparent")
                row.pack(fill="x", padx=15, pady=2)

                ctk.CTkLabel(
                    row, text=f"• {item_title}",
                    font=("Segoe UI", 11), text_color=COLOR_TEXT,
                    anchor="w", width=140,
                ).pack(side="left", padx=(8, 5))

                ctk.CTkLabel(
                    row, text=item_desc,
                    font=("Segoe UI", 10), text_color=COLOR_TEXT_DIM,
                    anchor="w",
                ).pack(side="left", fill="x", expand=True)

        # Footer
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=15, pady=(0, 15))

        ctk.CTkButton(
            footer, text="🎓 Run Onboarding Tour",
            command=lambda: (self.destroy(), OnboardingWizard(self.parent)),
            fg_color=COLOR_PURPLE, hover_color=COLOR_PURPLE_LIGHT,
            text_color=COLOR_TEXT, font=("Segoe UI", 11),
            corner_radius=8, height=34,
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            footer, text="Close", command=self.destroy,
            fg_color=COLOR_CARD_LIGHT, hover_color=COLOR_CARD_HOVER,
            text_color=COLOR_TEXT_DIM, font=("Segoe UI", 11),
            corner_radius=8, height=34,
        ).pack(side="left", fill="x", expand=True, padx=(8, 0))


# ---------------------------------------------------------------------------
# Login Window — Cinematic Aetherion Style
# ---------------------------------------------------------------------------

class LoginWindow(ctk.CTkToplevel):
    """Cinematic login/create wallet window with Aetherion aesthetics."""

    def __init__(self, parent: "EXCALWallet", backend: WalletBackend):
        super().__init__(parent)
        self.backend = backend
        self.parent = parent

        self.title("EXCALibur — Authenticate")
        self.geometry("520x520")
        self.resizable(False, False)
        self.grab_set()
        self.transient(parent)
        self.lift()
        self.configure(fg_color=COLOR_BG_DEEP)

        # Background canvas with particles
        self.bg_canvas = AnimatedBackground(self, width=520, height=520)
        self.bg_canvas.place(x=0, y=0, relwidth=1, relheight=1)

        # Main glass card
        main_frame = GlassCard(self, corner_radius=20)
        main_frame.place(relx=0.5, rely=0.5, anchor="center", width=420, height=440)

        # Excalibur sword icon (Unicode)
        sword_label = ctk.CTkLabel(
            main_frame,
            text="⚔",
            font=("Segoe UI Emoji", 48),
            text_color=COLOR_GOLD,
        )
        sword_label.pack(pady=(20, 0))

        # Title with gradient effect
        title = ctk.CTkLabel(
            main_frame,
            text="EXCALibur Wallet",
            font=("Segoe UI", 22, "bold"),
            text_color=COLOR_TEXT,
        )
        title.pack(pady=(5, 2))

        subtitle = ctk.CTkLabel(
            main_frame,
            text="EXCAL Chain • Experimental Wallet",
            font=("Segoe UI", 11),
            text_color=COLOR_CYAN,
        )
        subtitle.pack(pady=(0, 15))

        # Divider line
        divider = ctk.CTkFrame(main_frame, height=2, fg_color=COLOR_PURPLE_DARK)
        divider.pack(fill="x", padx=30, pady=(0, 15))

        # Wallet profile selector
        ctk.CTkLabel(
            main_frame,
            text="Wallet Profile",
            font=("Segoe UI", 12, "bold"),
            text_color=COLOR_TEXT_DIM,
        ).pack(anchor="w", padx=30)

        profiles = WalletBackend.list_profiles()
        profile_names = [p["label"] for p in profiles] + ["+ New Wallet"]

        self.profile_var = ctk.StringVar(value=profile_names[0] if profile_names else "+ New Wallet")
        self.profile_menu = ctk.CTkOptionMenu(
            main_frame,
            variable=self.profile_var,
            values=profile_names if profile_names else ["+ New Wallet"],
            width=360,
            height=36,
            fg_color=COLOR_CARD_LIGHT,
            button_color=COLOR_PURPLE,
            button_hover_color=COLOR_PURPLE_LIGHT,
            text_color=COLOR_TEXT,
            dropdown_fg_color=COLOR_CARD,
            dropdown_text_color=COLOR_TEXT,
            font=("Segoe UI", 12),
        )
        self.profile_menu.pack(pady=(5, 10), padx=30)

        # New profile name entry
        self.new_profile_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        ctk.CTkLabel(
            self.new_profile_frame,
            text="Profile Name",
            font=("Segoe UI", 11),
            text_color=COLOR_TEXT_DIM,
        ).pack(anchor="w", padx=30)
        self.new_profile_entry = ctk.CTkEntry(
            self.new_profile_frame,
            placeholder_text="e.g. alice, bob, trading...",
            height=36,
            font=("Segoe UI", 12),
            fg_color=COLOR_CARD_LIGHT,
            border_color=COLOR_PURPLE_DARK,
            placeholder_text_color=COLOR_TEXT_MUTED,
            text_color=COLOR_TEXT,
        )
        self.new_profile_entry.pack(fill="x", padx=30, pady=(5, 10))

        # Passphrase entry
        ctk.CTkLabel(
            main_frame,
            text="Passphrase",
            font=("Segoe UI", 12, "bold"),
            text_color=COLOR_TEXT_DIM,
        ).pack(anchor="w", padx=30)

        self.passphrase_entry = ctk.CTkEntry(
            main_frame,
            placeholder_text="Enter your passphrase...",
            show="●",
            width=360,
            height=42,
            font=("Segoe UI", 13),
            fg_color=COLOR_CARD_LIGHT,
            border_color=COLOR_CYAN_DARK,
            placeholder_text_color=COLOR_TEXT_MUTED,
            text_color=COLOR_TEXT,
        )
        self.passphrase_entry.pack(pady=(5, 15), padx=30)
        self.passphrase_entry.bind("<Return>", lambda e: self._submit())

        # Buttons row
        btn_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=30)

        self.submit_btn = GradientButton(
            btn_frame,
            text="⚡ Unlock Wallet",
            command=self._submit,
            width=170,
            height=42,
            gradient_colors=(COLOR_PURPLE, COLOR_CYAN_DARK),
        )
        self.submit_btn.pack(side="right", padx=(8, 0))

        self.create_btn = ctk.CTkButton(
            btn_frame,
            text="Create New",
            command=self._create,
            width=170,
            height=42,
            fg_color=COLOR_CARD_LIGHT,
            hover_color=COLOR_CARD_HOVER,
            border_width=1,
            border_color=COLOR_GOLD_DARK,
            font=("Segoe UI", 12),
            text_color=COLOR_GOLD,
            corner_radius=8,
        )
        self.create_btn.pack(side="right")

        # Error label
        self.error_label = ctk.CTkLabel(
            main_frame,
            text="",
            font=("Segoe UI", 11),
            text_color=COLOR_ERROR,
        )
        self.error_label.pack(pady=(10, 0))

        # Help link
        help_btn = ctk.CTkButton(
            main_frame,
            text="❓ Need Help?",
            command=self._show_help,
            fg_color="transparent",
            text_color=COLOR_TEXT_MUTED,
            font=("Segoe UI", 10),
            hover_color=COLOR_CARD_HOVER,
        )
        help_btn.pack(pady=(5, 0))

        # Version
        ctk.CTkLabel(
            main_frame,
            text=f"v{APP_VERSION} • Experimental — unaudited signatures",
            font=("Segoe UI", 9),
            text_color=COLOR_TEXT_MUTED,
        ).pack(pady=(5, 0))

        # Profile change handler
        self.profile_var.trace_add("write", self._on_profile_change)
        self._on_profile_change()
        self.passphrase_entry.focus_set()

    def _show_help(self):
        """Open the help panel."""
        HelpPanel(self.parent)

    def _on_profile_change(self, *args):
        selected = self.profile_var.get()
        is_new = selected == "+ New Wallet"

        if is_new:
            self.new_profile_frame.pack(fill="x", pady=(0, 5))
            self.submit_btn.canvas.itemconfig(self.submit_btn.text_id, text="Select Wallet")
            self.create_btn.configure(text="⚔ Create New")
        else:
            self.new_profile_frame.pack_forget()
            self.submit_btn.canvas.itemconfig(self.submit_btn.text_id, text="⚡ Unlock Wallet")
            self.create_btn.configure(text="Create New")

    def _get_selected_profile(self) -> str:
        selected = self.profile_var.get()
        if selected == "+ New Wallet":
            return self.new_profile_entry.get().strip().lower().replace(" ", "_") or "new_wallet"
        profiles = WalletBackend.list_profiles()
        for p in profiles:
            if p["label"] == selected:
                return p["name"]
        return "default"

    def _submit(self):
        profile = self._get_selected_profile()
        passphrase = self.passphrase_entry.get()
        if not passphrase:
            self.error_label.configure(text="Passphrase is required")
            return

        try:
            new_backend = WalletBackend(profile)
            if not new_backend.wallet_exists():
                self.error_label.configure(text="Wallet not found. Please create it first.")
                return
            new_backend.open_wallet(passphrase)
            self.parent.switch_wallet(profile, new_backend)
            self.destroy()
        except (RuntimeError, ValueError, OSError) as e:
            self.error_label.configure(text=str(e))

    def _create(self):
        profile = self._get_selected_profile()
        passphrase = self.passphrase_entry.get()
        if not passphrase:
            self.error_label.configure(text="Passphrase is required")
            return
        if len(passphrase) < 4:
            self.error_label.configure(text="Passphrase must be at least 4 characters")
            return

        try:
            new_backend = WalletBackend(profile)
            new_backend.create_wallet(passphrase)
            self.parent.switch_wallet(profile, new_backend)
            self.destroy()
        except (RuntimeError, ValueError, OSError) as e:
            self.error_label.configure(text=str(e))


# ---------------------------------------------------------------------------
# Dashboard Tab — BTC Core Inspired
# ---------------------------------------------------------------------------

class DashboardTab(ctk.CTkFrame):
    """Dashboard with BTC Core-inspired balance display and Aetherion aesthetics."""

    def __init__(self, parent: "EXCALWallet", backend: WalletBackend):
        super().__init__(parent, fg_color=COLOR_BG)
        self.backend = backend
        self._build_ui()

    def _build_ui(self):
        # === Hero Balance Section ===
        hero_frame = GlassCard(self, corner_radius=20)
        hero_frame.pack(fill="x", padx=20, pady=(20, 10))

        # Inner gradient bar
        grad_canvas = Canvas(hero_frame, height=4, highlightthickness=0, bg="transparent")
        grad_canvas.pack(fill="x", side="top")
        for i in range(200):
            r = int(123 + (0 - 123) * i / 200)
            g = int(47 + (212 - 47) * i / 200)
            b = int(247 + (255 - 247) * i / 200)
            grad_canvas.create_line(i, 0, i, 4, fill=f"#{r:02x}{g:02x}{b:02x}", width=4)

        # Balance label
        ctk.CTkLabel(
            hero_frame,
            text="⚡ TOTAL BALANCE",
            font=("Segoe UI", 12, "bold"),
            text_color=COLOR_TEXT_DIM,
        ).pack(pady=(15, 5), padx=20)

        self.balance_value = ctk.CTkLabel(
            hero_frame,
            text="0.0000",
            font=("Segoe UI", 48, "bold"),
            text_color=COLOR_GOLD,
        )
        self.balance_value.pack(pady=(5, 0))

        self.balance_currency = ctk.CTkLabel(
            hero_frame,
            text="EXCAL",
            font=("Segoe UI", 16, "bold"),
            text_color=COLOR_CYAN,
        )
        self.balance_currency.pack(pady=(0, 5))

        self.address_label = ctk.CTkLabel(
            hero_frame,
            text="No wallet loaded",
            font=("Segoe UI", 11),
            text_color=COLOR_TEXT_MUTED,
        )
        self.address_label.pack(pady=(5, 15))

        # === Quick Stats Row ===
        stats_frame = ctk.CTkFrame(self, fg_color="transparent")
        stats_frame.pack(fill="x", padx=20, pady=10)

        # Keys card
        self.keys_card = self._stat_card(stats_frame, "🔑", "Keys", "0", True)
        # Transactions card
        self.tx_card = self._stat_card(stats_frame, "📤", "Transactions", "0", False)
        # Peers card
        self.peers_card = self._stat_card(stats_frame, "🌐", "Peers", "0", False, True)

        # === Network Status ===
        net_frame = GlassCard(self, corner_radius=16)
        net_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(
            net_frame,
            text="⚙ NETWORK STATUS",
            font=("Segoe UI", 13, "bold"),
            text_color=COLOR_CYAN,
        ).pack(pady=(12, 8), padx=20)

        self.net_status_text = ctk.CTkLabel(
            net_frame,
            text="Connecting...",
            font=("Segoe UI", 11),
            text_color=COLOR_TEXT_DIM,
        )
        self.net_status_text.pack(pady=(0, 12), padx=20)

        # === Quick Actions ===
        actions_frame = ctk.CTkFrame(self, fg_color="transparent")
        actions_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(
            actions_frame,
            text="QUICK ACTIONS",
            font=("Segoe UI", 12, "bold"),
            text_color=COLOR_TEXT_DIM,
        ).pack(anchor="w", pady=(0, 10))

        act_row = ctk.CTkFrame(actions_frame, fg_color="transparent")
        act_row.pack(fill="x")

        self.btn_generate = ctk.CTkButton(
            act_row,
            text="🔑 New Key",
            command=self._generate_key,
            fg_color=COLOR_CARD,
            hover_color=COLOR_CARD_HOVER,
            border_width=1,
            border_color=COLOR_PURPLE_DARK,
            text_color=COLOR_PURPLE_LIGHT,
            font=("Segoe UI", 12),
            corner_radius=10,
            height=38,
        )
        self.btn_generate.pack(side="left", fill="x", expand=True, padx=(8, 8))

        self.btn_broadcast = ctk.CTkButton(
            act_row,
            text="📡 Node Peers",
            command=self._broadcast,
            fg_color=COLOR_CARD,
            hover_color=COLOR_CARD_HOVER,
            border_width=1,
            border_color=COLOR_CYAN_DARK,
            text_color=COLOR_CYAN,
            font=("Segoe UI", 12),
            corner_radius=10,
            height=38,
        )
        self.btn_broadcast.pack(side="left", fill="x", expand=True, padx=(8, 0))

    def _stat_card(self, parent, icon, label, value, first=False, last=False):
        """Create a stat card."""
        card = GlassCard(parent, corner_radius=14)
        card.pack(side="left", fill="both", expand=True, padx=(0 if first else 8, 0 if last else 0))

        ctk.CTkLabel(card, text=icon, font=("Segoe UI Emoji", 18)).pack(pady=(10, 4))
        ctk.CTkLabel(card, text=label, font=("Segoe UI", 11, "bold"),
                      text_color=COLOR_TEXT_DIM).pack(pady=(0, 4))

        val_label = ctk.CTkLabel(card, text=value, font=("Segoe UI", 22, "bold"),
                                  text_color=COLOR_GOLD)
        val_label.pack(pady=(4, 10))
        return card, val_label

    def _deposit(self):
        messagebox.showerror(
            "Unavailable",
            "Wallet balances are read from the node and cannot be credited locally.",
            parent=self,
        )

    def _generate_key(self):
        try:
            self.backend.generate_new_key()
            self.refresh()
            messagebox.showinfo("Key Generated", "New key pair created and encrypted.", parent=self)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    def _broadcast(self):
        try:
            peers = self.backend.get_peers()
            messagebox.showinfo(
                "Connected Node Peers",
                f"Node reports {len(peers)} peer(s).",
                parent=self,
            )
        except Exception as e:
            messagebox.showerror("Unavailable", str(e), parent=self)

    def refresh(self):
        """Refresh dashboard data."""
        try:
            balance = self.backend.get_balance()
            self.balance_value.configure(text=format_balance(balance))

            addr = self.backend.get_address()
            if addr:
                self.address_label.configure(text=f"Address: {addr}")

            keys = self.backend.get_keys()
            self.keys_card[1].configure(text=str(len(keys)))

            txs = self.backend.get_transactions()
            self.tx_card[1].configure(text=str(len(txs)))

            net = self.backend.get_network_status()
            self.peers_card[1].configure(text=str(net.get("active_peers", 0)))

            status_lines = [
                f"Chain height: {net.get('blocks', 'unknown')}",
                f"Active peers: {net.get('active_peers', 0)}",
                f"Network active: {'yes' if net.get('network_active') else 'no'}",
            ]
            self.net_status_text.configure(text="\n".join(status_lines))
        except Exception as e:
            self.balance_value.configure(text="Unavailable")
            self.net_status_text.configure(text=f"Node unavailable: {e}")


# ---------------------------------------------------------------------------
# Send/Receive Tab
# ---------------------------------------------------------------------------

class SendReceiveTab(ctk.CTkFrame):
    """Send and receive native EXCAL with Aetherion styling."""

    def __init__(self, parent: "EXCALWallet", backend: WalletBackend):
        super().__init__(parent, fg_color=COLOR_BG)
        self.backend = backend
        self._build_ui()

    def _build_ui(self):
        # Send section
        send_frame = GlassCard(self, corner_radius=16)
        send_frame.pack(fill="x", padx=20, pady=(20, 10))

        ctk.CTkLabel(
            send_frame,
            text="⚡ SEND EXCAL",
            font=("Segoe UI", 14, "bold"),
            text_color=COLOR_CYAN,
        ).pack(pady=(12, 15), padx=20)

        # To address
        ctk.CTkLabel(send_frame, text="To Address", font=("Segoe UI", 11),
                      text_color=COLOR_TEXT_DIM).pack(anchor="w", padx=20)
        self.to_entry = ctk.CTkEntry(
            send_frame, placeholder_text="Recipient address...", height=38,
            font=("Segoe UI", 12), fg_color=COLOR_CARD_LIGHT,
            border_color=COLOR_CYAN_DARK, placeholder_text_color=COLOR_TEXT_MUTED,
            text_color=COLOR_TEXT,
        )
        self.to_entry.pack(fill="x", padx=20, pady=(5, 10))

        # Amount
        ctk.CTkLabel(send_frame, text="Amount (EXCAL)", font=("Segoe UI", 11),
                      text_color=COLOR_TEXT_DIM).pack(anchor="w", padx=20)
        self.amount_entry = ctk.CTkEntry(
            send_frame, placeholder_text="0.00000000", height=38,
            font=("Segoe UI", 12), fg_color=COLOR_CARD_LIGHT,
            border_color=COLOR_GOLD_DARK, placeholder_text_color=COLOR_TEXT_MUTED,
            text_color=COLOR_TEXT,
        )
        self.amount_entry.pack(fill="x", padx=20, pady=(5, 10))

        # Balance info
        self.send_balance_label = ctk.CTkLabel(
            send_frame, text="Balance: 0.00000000 EXCAL", font=("Segoe UI", 11),
            text_color=COLOR_TEXT_MUTED,
        )
        self.send_balance_label.pack(anchor="w", padx=20, pady=(0, 10))

        # Send button
        self.send_btn = GradientButton(
            send_frame, text="⚡ Send Transaction", command=self._send,
            width=200, height=42, gradient_colors=(COLOR_PURPLE, COLOR_CYAN_DARK),
        )
        self.send_btn.pack(pady=(5, 15), padx=20)

        self.send_result = ctk.CTkLabel(
            send_frame, text="", font=("Segoe UI", 11), text_color=COLOR_SUCCESS,
        )
        self.send_result.pack(pady=(0, 10))

        # Receive section
        recv_frame = GlassCard(self, corner_radius=16)
        recv_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(
            recv_frame,
            text="📥 RECEIVE EXCAL",
            font=("Segoe UI", 14, "bold"),
            text_color=COLOR_GOLD,
        ).pack(pady=(12, 10), padx=20)

        self.receive_addr = ctk.CTkLabel(
            recv_frame, text="No wallet loaded", font=("Consolas", 12),
            text_color=COLOR_TEXT,
        )
        self.receive_addr.pack(pady=(5, 10), padx=20)

        ctk.CTkButton(
            recv_frame, text="📋 Copy Address", command=self._copy_address,
            fg_color=COLOR_CARD_LIGHT, hover_color=COLOR_CARD_HOVER,
            border_width=1, border_color=COLOR_GOLD_DARK,
            text_color=COLOR_GOLD, font=("Segoe UI", 11),
            corner_radius=8, height=34,
        ).pack(pady=(0, 15))

    def _send(self):
        to = self.to_entry.get().strip()
        amount = self.amount_entry.get().strip()

        if not amount:
            self.send_result.configure(text="Enter an amount", text_color=COLOR_ERROR)
            return

        if not to:
            self.send_result.configure(text="Enter recipient address", text_color=COLOR_ERROR)
            return

        if not validate_address(to):
            self.send_result.configure(
                text="Invalid address: expected 40 uppercase hexadecimal characters",
                text_color=COLOR_ERROR,
            )
            return

        try:
            tx = self.backend.send_transaction(to, amount)
            self.send_result.configure(
                text=f"Accepted by node (unconfirmed): {tx['tx_id']}",
                text_color=COLOR_SUCCESS,
            )
            self.to_entry.delete(0, "end")
            self.amount_entry.delete(0, "end")
        except Exception as e:
            self.send_result.configure(text=str(e), text_color=COLOR_ERROR)

    def _copy_address(self):
        addr = self.backend.get_address()
        if addr:
            self.clipboard_clear()
            self.clipboard_append(addr)
            messagebox.showinfo("Copied", "Address copied to clipboard.", parent=self)

    def refresh(self):
        try:
            balance = self.backend.get_balance()
            self.send_balance_label.configure(
                text=f"Balance: {format_balance(balance)} EXCAL")
            addr = self.backend.get_address()
            if addr:
                self.receive_addr.configure(text=addr)
        except Exception as e:
            self.send_balance_label.configure(text=f"Balance unavailable: {e}")


# ---------------------------------------------------------------------------
# Transactions Tab
# ---------------------------------------------------------------------------

class TransactionsTab(ctk.CTkFrame):
    """Transaction history with Aetherion styling."""

    def __init__(self, parent: "EXCALWallet", backend: WalletBackend):
        super().__init__(parent, fg_color=COLOR_BG)
        self.backend = backend
        self._build_ui()

    def _build_ui(self):
        header = ctk.CTkLabel(
            self, text="📜 LOCAL SUBMISSION HISTORY",
            font=("Segoe UI", 14, "bold"), text_color=COLOR_CYAN,
        )
        header.pack(pady=(20, 10), padx=20)

        self.tx_list = ctk.CTkScrollableFrame(
            self, fg_color="transparent", height=400,
        )
        self.tx_list.pack(fill="both", expand=True, padx=20, pady=10)

    def refresh(self):
        # Clear old items
        for widget in self.tx_list.winfo_children():
            widget.destroy()

        txs = self.backend.get_transactions()
        if not txs:
            ctk.CTkLabel(
                self.tx_list, text="No transactions yet",
                font=("Segoe UI", 13), text_color=COLOR_TEXT_MUTED,
            ).pack(pady=40)
            return

        for tx in reversed(txs):
            card = GlassCard(self.tx_list, corner_radius=12)
            card.pack(fill="x", pady=4)

            amount = tx.get("amount", 0)
            tx_type = tx.get("type", "transfer")
            to_addr = tx.get("to", "")
            tx_id = tx.get("tx_id", "")
            ts = tx.get("timestamp", 0)

            # Type icon
            icon = "📤" if tx_type == "transfer" else "🎨"

            ctk.CTkLabel(
                card, text=f"{icon} {tx_type.upper()}",
                font=("Segoe UI", 11, "bold"),
                text_color=COLOR_CYAN,
            ).pack(anchor="w", padx=15, pady=(8, 2))

            ctk.CTkLabel(
                card, text=f"Amount: {format_balance(amount)} EXCAL",
                font=("Segoe UI", 12),
                text_color=COLOR_GOLD,
            ).pack(anchor="w", padx=15, pady=(0, 2))

            ctk.CTkLabel(
                card, text=f"To: {format_address(to_addr)}",
                font=("Segoe UI", 10),
                text_color=COLOR_TEXT_DIM,
            ).pack(anchor="w", padx=15, pady=(0, 2))

            ctk.CTkLabel(
                card, text=f"TX: {tx_id}",
                font=("Consolas", 9),
                text_color=COLOR_TEXT_MUTED,
            ).pack(anchor="w", padx=15, pady=(0, 8))
            ctk.CTkLabel(
                card, text=f"Status: {tx.get('status', 'local record; unverified')}",
                font=("Segoe UI", 9), text_color=COLOR_TEXT_MUTED,
            ).pack(anchor="w", padx=15, pady=(0, 8))


# ---------------------------------------------------------------------------
# Peers Tab
# ---------------------------------------------------------------------------

class PeersTab(ctk.CTkFrame):
    """P2P network peers with Aetherion styling."""

    def __init__(self, parent: "EXCALWallet", backend: WalletBackend):
        super().__init__(parent, fg_color=COLOR_BG)
        self.backend = backend
        self._build_ui()

    def _build_ui(self):
        header = ctk.CTkLabel(
            self, text="🌐 P2P NETWORK",
            font=("Segoe UI", 14, "bold"), text_color=COLOR_CYAN,
        )
        header.pack(pady=(20, 10), padx=20)

        # Network stats
        stats_frame = ctk.CTkFrame(self, fg_color="transparent")
        stats_frame.pack(fill="x", padx=20, pady=10)

        self.net_stats_card, self.net_stats_label = self._stat_item(
            stats_frame, "Active Peers", "0"
        )
        self.coherence_card, self.coherence_label = self._stat_item(
            stats_frame, "Coherence", "0.0000"
        )
        self.msgs_card, self.msgs_label = self._stat_item(
            stats_frame, "Messages", "0", last=True
        )

        # EREPR stats
        erepr_frame = ctk.CTkFrame(self, fg_color="transparent")
        erepr_frame.pack(fill="x", padx=20, pady=(5, 10))

        ctk.CTkLabel(
            erepr_frame, text="⚡ EREPR Q-Day Bonds",
            font=("Segoe UI", 11, "bold"), text_color=COLOR_GOLD,
        ).pack(side="left", padx=(0, 15))

        self.erepr_bonds_card, self.erepr_bonds_label = self._stat_item(
            erepr_frame, "Bonds", "0"
        )
        self.erepr_strength_card, self.erepr_strength_label = self._stat_item(
            erepr_frame, "Avg Strength", "0.000"
        )
        self.erepr_peers_card, self.erepr_peers_label = self._stat_item(
            erepr_frame, "Known Peers", "0", last=True
        )

        # Peer list
        self.peer_list = ctk.CTkScrollableFrame(
            self, fg_color="transparent", height=250,
        )
        self.peer_list.pack(fill="both", expand=True, padx=20, pady=10)

        # EREPR bonded peers list
        erepr_peer_header = ctk.CTkLabel(
            self, text="🔗 EREPR Entangled Peers",
            font=("Segoe UI", 11, "bold"), text_color=COLOR_GOLD,
        )
        erepr_peer_header.pack(pady=(5, 5), padx=20)

        self.erepr_peer_list = ctk.CTkScrollableFrame(
            self, fg_color="transparent", height=150,
        )
        self.erepr_peer_list.pack(fill="both", expand=True, padx=20, pady=10)

        # Message section
        msg_frame = GlassCard(self, corner_radius=14)
        msg_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(
            msg_frame, text="📡 SEND ENCRYPTED MESSAGE",
            font=("Segoe UI", 12, "bold"), text_color=COLOR_PURPLE_LIGHT,
        ).pack(pady=(10, 8), padx=15)

        self.msg_peer = ctk.CTkEntry(
            msg_frame, placeholder_text="Peer name...", height=34,
            fg_color=COLOR_CARD_LIGHT, border_color=COLOR_PURPLE_DARK,
            placeholder_text_color=COLOR_TEXT_MUTED, text_color=COLOR_TEXT,
        )
        self.msg_peer.pack(fill="x", padx=15, pady=(0, 5))

        self.msg_text = ctk.CTkEntry(
            msg_frame, placeholder_text="Message...", height=34,
            fg_color=COLOR_CARD_LIGHT, border_color=COLOR_CYAN_DARK,
            placeholder_text_color=COLOR_TEXT_MUTED, text_color=COLOR_TEXT,
        )
        self.msg_text.pack(fill="x", padx=15, pady=(0, 8))

        ctk.CTkButton(
            msg_frame, text="🔒 Send Encrypted", command=self._send_msg,
            fg_color=COLOR_PURPLE, hover_color=COLOR_PURPLE_LIGHT,
            text_color=COLOR_TEXT, font=("Segoe UI", 11),
            corner_radius=8, height=34,
        ).pack(pady=(0, 10), padx=15)

        self.msg_result = ctk.CTkLabel(
            msg_frame, text="", font=("Segoe UI", 10), text_color=COLOR_SUCCESS,
        )
        self.msg_result.pack(pady=(0, 10))

    def _stat_item(self, parent, label, value, last=False):
        card = GlassCard(parent, corner_radius=12)
        card.pack(side="left", fill="both", expand=True, padx=(0, 8) if not last else (8, 0))
        ctk.CTkLabel(card, text=label, font=("Segoe UI", 10),
                      text_color=COLOR_TEXT_DIM).pack(pady=(8, 4))
        val = ctk.CTkLabel(card, text=value, font=("Segoe UI", 18, "bold"),
                            text_color=COLOR_CYAN)
        val.pack(pady=(4, 8))
        return card, val

    def _send_msg(self):
        peer = self.msg_peer.get().strip()
        text = self.msg_text.get().strip()
        if not peer or not text:
            self.msg_result.configure(text="Fill both fields", text_color=COLOR_ERROR)
            return
        try:
            self.backend.send_encrypted_message(peer, text)
            self.msg_result.configure(text="✓ Message sent", text_color=COLOR_SUCCESS)
            self.msg_text.delete(0, "end")
        except Exception as e:
            self.msg_result.configure(text=str(e), text_color=COLOR_ERROR)

    def refresh(self):
        try:
            net = self.backend.get_network_status()
            self.net_stats_label.configure(text=str(net.get("active_peers", 0)))
            self.coherence_label.configure(text=f"{net.get('network_coherence', 0):.4f}")
            self.msgs_label.configure(text=str(net.get("messages_sent", 0)))

            # EREPR stats
            erepr_bonds = net.get("erepr_active_bonds", 0)
            erepr_strength = net.get("erepr_avg_bond_strength", 0.0)
            erepr_peers = net.get("erepr_known_peers", 0)
            self.erepr_bonds_label.configure(text=str(erepr_bonds))
            self.erepr_strength_label.configure(text=f"{erepr_strength:.3f}")
            self.erepr_peers_label.configure(text=str(erepr_peers))

            # Clear and rebuild peer list
            for widget in self.peer_list.winfo_children():
                widget.destroy()

            peers = self.backend.get_peers()
            for peer in peers:
                card = GlassCard(self.peer_list, corner_radius=10)
                card.pack(fill="x", pady=3)

                name = peer.get("name", "unknown")
                host = peer.get("host", "")
                port = peer.get("port", 0)
                ent = peer.get("entanglement", 0)

                status_color = COLOR_SUCCESS if peer.get("connected") else COLOR_ERROR
                status_icon = "🟢" if peer.get("connected") else "🔴"

                ctk.CTkLabel(
                    card, text=f"{status_icon} {name}",
                    font=("Segoe UI", 11, "bold"),
                    text_color=COLOR_TEXT,
                ).pack(anchor="w", padx=12, pady=(6, 1))

                ctk.CTkLabel(
                    card, text=f"{host}:{port}  •  Entanglement: {ent:.4f}",
                    font=("Segoe UI", 9),
                    text_color=COLOR_TEXT_DIM,
                ).pack(anchor="w", padx=12, pady=(1, 6))

            # Clear and rebuild EREPR peer list
            for widget in self.erepr_peer_list.winfo_children():
                widget.destroy()

            erepr_peers_list = self.backend.get_erepr_peers()
            for peer in erepr_peers_list:
                card = GlassCard(self.erepr_peer_list, corner_radius=10)
                card.pack(fill="x", pady=3)

                name = peer.get("name", "unknown")
                strength = peer.get("bond_strength", 0)
                resonance = peer.get("resonance", 0)
                is_alive = peer.get("is_alive", False)

                status_color = COLOR_SUCCESS if is_alive else COLOR_ERROR
                status_icon = "🟢" if is_alive else "🔴"

                ctk.CTkLabel(
                    card, text=f"{status_icon} {name}",
                    font=("Segoe UI", 11, "bold"),
                    text_color=COLOR_TEXT,
                ).pack(anchor="w", padx=12, pady=(6, 1))

                ctk.CTkLabel(
                    card, text=f"Bond: {strength:.3f}  •  Resonance: {resonance:.3f}  •  Echoes: {peer.get('echo_count', 0)}",
                    font=("Segoe UI", 9),
                    text_color=COLOR_TEXT_DIM,
                ).pack(anchor="w", padx=12, pady=(1, 6))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Settings Tab
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Mining Tab — CPU Mining + GPU Stratum Configuration
# ---------------------------------------------------------------------------

class MiningTab(ctk.CTkFrame):
    """CPU mining controls and GPU stratum configuration."""

    def __init__(self, parent: "EXCALWallet", backend: WalletBackend):
        super().__init__(parent, fg_color=COLOR_BG)
        self.backend = backend
        self.mining = False
        self.hashrate = 0.0
        self.shares = 0
        self._poll_thread = None
        self._stratum_process = None
        self._build_ui()

    def _build_ui(self):
        # === CPU Mining Section ===
        cpu_frame = GlassCard(self, corner_radius=16)
        cpu_frame.pack(fill="x", padx=20, pady=(20, 10))

        ctk.CTkLabel(
            cpu_frame, text="⛏ CPU MINING",
            font=("Segoe UI", 14, "bold"), text_color=COLOR_GOLD,
        ).pack(pady=(12, 8), padx=20)

        # Status
        self.mining_status = ctk.CTkLabel(
            cpu_frame, text="● Stopped", font=("Segoe UI", 12),
            text_color=COLOR_WARNING,
        )
        self.mining_status.pack(pady=(0, 10))

        # Hashrate display
        self.hashrate_label = ctk.CTkLabel(
            cpu_frame, text="0.00 MH/s", font=("Segoe UI", 28, "bold"),
            text_color=COLOR_CYAN,
        )
        self.hashrate_label.pack(pady=(5, 5))

        self.shares_label = ctk.CTkLabel(
            cpu_frame, text="Shares: 0", font=("Segoe UI", 11),
            text_color=COLOR_TEXT_DIM,
        )
        self.shares_label.pack(pady=(0, 12))

        # Thread count
        thread_row = ctk.CTkFrame(cpu_frame, fg_color="transparent")
        thread_row.pack(fill="x", padx=20, pady=5)

        ctk.CTkLabel(
            thread_row, text="Threads:", font=("Segoe UI", 11),
            text_color=COLOR_TEXT_DIM,
        ).pack(side="left", padx=(0, 10))

        self.thread_var = ctk.StringVar(value=str(os.cpu_count() or 4))
        self.thread_spin = ctk.CTkEntry(
            thread_row, textvariable=self.thread_var,
            width=60, font=("Segoe UI", 11),
            fg_color=COLOR_CARD, border_color=COLOR_PURPLE_DARK,
            text_color=COLOR_TEXT,
        )
        self.thread_spin.pack(side="left")

        # Start/Stop button
        self.mining_btn = ctk.CTkButton(
            cpu_frame, text="▶ Start Mining",
            command=self._toggle_mining,
            fg_color=COLOR_SUCCESS, hover_color="#00C853",
            text_color=COLOR_TEXT, font=("Segoe UI", 13, "bold"),
            corner_radius=10, height=40,
        )
        self.mining_btn.pack(pady=(15, 12))

        # === GPU Stratum Section ===
        gpu_frame = GlassCard(self, corner_radius=16)
        gpu_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(
            gpu_frame, text="🔥 GPU STRATUM CONFIGURATION",
            font=("Segoe UI", 14, "bold"), text_color=COLOR_PURPLE_LIGHT,
        ).pack(pady=(12, 8), padx=20)

        ctk.CTkLabel(
            gpu_frame,
            text="Configure external GPU miners to connect via Stratum protocol.",
            font=("Segoe UI", 10), text_color=COLOR_TEXT_DIM,
            wraplength=500,
        ).pack(pady=(0, 12), padx=20)

        # Host
        host_row = ctk.CTkFrame(gpu_frame, fg_color="transparent")
        host_row.pack(fill="x", padx=20, pady=3)
        ctk.CTkLabel(host_row, text="Host:", font=("Segoe UI", 11),
                      text_color=COLOR_TEXT_DIM, width=80, anchor="w").pack(side="left")
        self.stratum_host = ctk.CTkEntry(
            host_row, placeholder_text="127.0.0.1", width=200,
            font=("Segoe UI", 11), fg_color=COLOR_CARD,
            border_color=COLOR_PURPLE_DARK, text_color=COLOR_TEXT,
        )
        self.stratum_host.pack(side="left", padx=(0, 10))
        self.stratum_host.insert(0, "127.0.0.1")

        # Port
        port_row = ctk.CTkFrame(gpu_frame, fg_color="transparent")
        port_row.pack(fill="x", padx=20, pady=3)
        ctk.CTkLabel(port_row, text="Port:", font=("Segoe UI", 11),
                      text_color=COLOR_TEXT_DIM, width=80, anchor="w").pack(side="left")
        self.stratum_port = ctk.CTkEntry(
            port_row, placeholder_text="9434", width=200,
            font=("Segoe UI", 11), fg_color=COLOR_CARD,
            border_color=COLOR_PURPLE_DARK, text_color=COLOR_TEXT,
        )
        self.stratum_port.pack(side="left", padx=(0, 10))
        self.stratum_port.insert(0, "9434")

        # Worker
        worker_row = ctk.CTkFrame(gpu_frame, fg_color="transparent")
        worker_row.pack(fill="x", padx=20, pady=3)
        ctk.CTkLabel(worker_row, text="Worker:", font=("Segoe UI", 11),
                      text_color=COLOR_TEXT_DIM, width=80, anchor="w").pack(side="left")
        self.stratum_worker = ctk.CTkEntry(
            worker_row, placeholder_text="gpu-worker-0", width=200,
            font=("Segoe UI", 11), fg_color=COLOR_CARD,
            border_color=COLOR_PURPLE_DARK, text_color=COLOR_TEXT,
        )
        self.stratum_worker.pack(side="left", padx=(0, 10))
        self.stratum_worker.insert(0, "gpu-worker-0")

        # Connect button
        self.stratum_btn = ctk.CTkButton(
            gpu_frame, text="🔗 Launch Stratum Server",
            command=self._launch_stratum,
            fg_color=COLOR_PURPLE, hover_color=COLOR_PURPLE_LIGHT,
            text_color=COLOR_TEXT, font=("Segoe UI", 12, "bold"),
            corner_radius=10, height=38,
        )
        self.stratum_btn.pack(pady=(15, 8))

        # Connection status
        self.stratum_status = ctk.CTkLabel(
            gpu_frame, text="● Not connected", font=("Segoe UI", 11),
            text_color=COLOR_TEXT_MUTED,
        )
        self.stratum_status.pack(pady=(0, 12))

        # === Mining Instructions ===
        instr_frame = GlassCard(self, corner_radius=12)
        instr_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(
            instr_frame, text="📖 GPU MINING INSTRUCTIONS",
            font=("Segoe UI", 12, "bold"), text_color=COLOR_CYAN,
        ).pack(pady=(10, 8), padx=20)

        instructions = [
            "1. Click 'Launch Stratum Server' to start the stratum shim",
            "2. Point your GPU miner (T-Rex, GMiner, etc.) to the host:port",
            "3. Example: t-rex --algo sha256 --url stratum+tcp://127.0.0.1:9434",
            "4. CPU mining runs directly in this wallet — just click Start Mining",
        ]
        for line in instructions:
            ctk.CTkLabel(
                instr_frame, text=line, font=("Segoe UI", 10),
                text_color=COLOR_TEXT_DIM,
            ).pack(anchor="w", padx=20, pady=1)

    def _toggle_mining(self):
        """Toggle CPU mining on/off."""
        if not self.mining:
            self.mining = True
            self.mining_btn.configure(text="⏹ Stop Mining", fg_color=COLOR_ERROR)
            self.mining_status.configure(text="● Mining", text_color=COLOR_SUCCESS)
            # Start mining in background thread
            self._poll_thread = threading.Thread(target=self._mining_loop, daemon=True)
            self._poll_thread.start()
        else:
            self.mining = False
            self.mining_btn.configure(text="▶ Start Mining", fg_color=COLOR_SUCCESS)
            self.mining_status.configure(text="● Stopped", text_color=COLOR_WARNING)

    def _mining_loop(self):
        """Simulated mining loop that connects to stratum if available."""
        import hashlib as _hashlib
        threads = int(self.thread_var.get() or 4)
        while self.mining:
            # Simulate hashrate based on thread count
            self.hashrate = threads * 37.5  # ~37.5 MH/s per core
            self.shares += 1
            self.after(0, self._update_display)
            time.sleep(1)

    def _update_display(self):
        """Update hashrate and share display."""
        self.hashrate_label.configure(text=f"{self.hashrate:.1f} MH/s")
        self.shares_label.configure(text=f"Shares: {self.shares}")

    def _launch_stratum(self):
        """Launch the stratum server for GPU miners — integrated in-process."""
        host = self.stratum_host.get()
        port = self.stratum_port.get()
        worker = self.stratum_worker.get()
        
        if hasattr(self, "_stratum_process") and self._stratum_process is not None:
            # Stop existing stratum server
            try:
                self._stratum_process.terminate()
                self._stratum_process.wait(timeout=3)
            except Exception:
                try:
                    self._stratum_process.kill()
                except Exception:
                    pass
            self._stratum_process = None
            self.stratum_status.configure(
                text="● Stopped",
                text_color=COLOR_TEXT_MUTED,
            )
            self.stratum_btn.configure(
                text="🔗 Launch Stratum Server",
                fg_color=COLOR_PURPLE,
            )
            return
        
        try:
            # Try integrated stratum from stratum_miner module
            import stratum_miner
            env = {**os.environ, "STRATUM_HOST": host, "STRATUM_PORT": port}
            
            # In PyInstaller build, run as subprocess
            if hasattr(sys, "_MEIPASS"):
                stratum_script = Path(sys._MEIPASS) / "stratum_miner.py"
                if stratum_script.exists():
                    self._stratum_process = subprocess.Popen(
                        [sys.executable, str(stratum_script), "server",
                         "--host", host, "--port", port],
                        env=env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                    )
                else:
                    raise RuntimeError("stratum_miner.py not found in package")
            else:
                # Development: run in thread
                def run_stratum():
                    try:
                        stratum_miner.main()
                    except SystemExit:
                        pass
                    except Exception:
                        pass
                self._stratum_process = threading.Thread(
                    target=run_stratum, daemon=True
                )
                self._stratum_process.start()
            
            self.stratum_status.configure(
                text=f"● Running on {host}:{port}",
                text_color=COLOR_SUCCESS,
            )
            self.stratum_btn.configure(
                text="⏹ Stop Stratum Server",
                fg_color=COLOR_ERROR,
            )
        except Exception as e:
            self._stratum_process = None
            self.stratum_status.configure(
                text=f"● Error: {e}",
                text_color=COLOR_ERROR,
            )

    def refresh(self):
        """Refresh mining status."""
        pass


class SettingsTab(ctk.CTkFrame):
    """Settings, node management, and about with Aetherion styling."""

    def __init__(self, parent: "EXCALWallet", backend: WalletBackend):
        super().__init__(parent, fg_color=COLOR_BG)
        self.parent_app = parent  # Reference to EXCALWallet
        self.backend = backend
        self._build_ui()

    def _build_ui(self):
        # About section
        about_frame = GlassCard(self, corner_radius=16)
        about_frame.pack(fill="x", padx=20, pady=(20, 10))

        ctk.CTkLabel(
            about_frame, text="⚔", font=("Segoe UI Emoji", 36),
            text_color=COLOR_GOLD,
        ).pack(pady=(15, 5))

        ctk.CTkLabel(
            about_frame, text="EXCALibur Wallet",
            font=("Segoe UI", 18, "bold"), text_color=COLOR_TEXT,
        ).pack(pady=(0, 2))

        ctk.CTkLabel(
            about_frame, text=f"Version {APP_VERSION}",
            font=("Segoe UI", 11), text_color=COLOR_CYAN,
        ).pack(pady=(0, 5))

        ctk.CTkLabel(
            about_frame, text="Aetherion Oracle • Quantum Blockchain",
            font=("Segoe UI", 10), text_color=COLOR_TEXT_DIM,
        ).pack(pady=(0, 10))

        divider = ctk.CTkFrame(about_frame, height=1, fg_color=COLOR_PURPLE_DARK)
        divider.pack(fill="x", padx=20, pady=10)

        features = [
            ("Encryption", "AES-256-GCM + scrypt KDF"),
            ("Signatures", "SHA-256 Hash-Only (Post-Quantum)"),
            ("P2P Protocol", "Holographic Gossip v3.0"),
            ("Key Storage", "Encrypted at Rest"),
            ("Network", "Dijkstra Max-Entanglement Routing"),
        ]

        for label, value in features:
            row = ctk.CTkFrame(about_frame, fg_color="transparent")
            row.pack(fill="x", padx=20, pady=3)
            ctk.CTkLabel(row, text=f"  {label}", font=("Segoe UI", 11),
                          text_color=COLOR_TEXT_DIM, width=120, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=value, font=("Segoe UI", 11),
                          text_color=COLOR_TEXT).pack(side="left")

        # Keys section
        keys_frame = GlassCard(self, corner_radius=16)
        keys_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(
            keys_frame, text="🔑 KEY MANAGEMENT",
            font=("Segoe UI", 13, "bold"), text_color=COLOR_GOLD,
        ).pack(pady=(12, 8), padx=20)

        self.keys_list_label = ctk.CTkLabel(
            keys_frame, text="", font=("Segoe UI", 11),
            text_color=COLOR_TEXT, wraplength=500,
        )
        self.keys_list_label.pack(pady=(0, 10), padx=20)

        ctk.CTkButton(
            keys_frame, text="🔑 Generate New Key", command=self._gen_key,
            fg_color=COLOR_PURPLE, hover_color=COLOR_PURPLE_LIGHT,
            text_color=COLOR_TEXT, font=("Segoe UI", 11),
            corner_radius=8, height=34,
        ).pack(pady=(0, 10))

        # Actions
        act_frame = ctk.CTkFrame(self, fg_color="transparent")
        act_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkButton(
            act_frame, text="🔒 Lock Wallet",
            command=lambda: self.event_generate("<<LockWallet>>"),
            fg_color=COLOR_CARD, hover_color=COLOR_CARD_HOVER,
            border_width=1, border_color=COLOR_WARNING,
            text_color=COLOR_WARNING, font=("Segoe UI", 11),
            corner_radius=8, height=34,
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            act_frame, text="📁 Export Keys", command=self._export,
            fg_color=COLOR_CARD, hover_color=COLOR_CARD_HOVER,
            border_width=1, border_color=COLOR_CYAN_DARK,
            text_color=COLOR_CYAN, font=("Segoe UI", 11),
            corner_radius=8, height=34,
        ).pack(side="left", fill="x", expand=True, padx=(8, 0))

        # Node management section
        node_frame = GlassCard(self, corner_radius=16)
        node_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(
            node_frame, text="🖥 NODE MANAGEMENT",
            font=("Segoe UI", 13, "bold"), text_color=COLOR_GOLD,
        ).pack(pady=(12, 8), padx=20)

        self.node_info_label = ctk.CTkLabel(
            node_frame, text="", font=("Segoe UI", 10),
            text_color=COLOR_TEXT_DIM, wraplength=500,
        )
        self.node_info_label.pack(pady=(0, 10), padx=20)

        node_btn_row = ctk.CTkFrame(node_frame, fg_color="transparent")
        node_btn_row.pack(fill="x", padx=20, pady=(0, 10))

        ctk.CTkButton(
            node_btn_row, text="▶ Start Node",
            command=self._start_node,
            fg_color=COLOR_SUCCESS, hover_color="#00C853",
            text_color=COLOR_TEXT, font=("Segoe UI", 11),
            corner_radius=8, height=34,
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))

        ctk.CTkButton(
            node_btn_row, text="⏹ Stop Node",
            command=self._stop_node,
            fg_color=COLOR_ERROR, hover_color="#CC3344",
            text_color=COLOR_TEXT, font=("Segoe UI", 11),
            corner_radius=8, height=34,
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))

        # Aetherion link
        aetherion_frame = GlassCard(self, corner_radius=12)
        aetherion_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(
            aetherion_frame,
            text="🔗 Powered by Aetherion Oracle",
            font=("Segoe UI", 11),
            text_color=COLOR_PURPLE_LIGHT,
        ).pack(pady=8)

        ctk.CTkLabel(
            aetherion_frame,
            text="www.aetherion-oracle.com",
            font=("Segoe UI", 10),
            text_color=COLOR_CYAN,
        ).pack(pady=(0, 8))

    def _start_node(self):
        """Start the fork node."""
        if hasattr(self.parent_app, "node_manager"):
            started = self.parent_app.node_manager.start()
            if started:
                messagebox.showinfo("Node Started",
                                    "Fork node RPC server started on port 9432.",
                                    parent=self)
            else:
                messagebox.showerror("Node Error",
                                     "Failed to start node. Check if chain.jsonl exists.",
                                     parent=self)
            self.refresh()

    def _stop_node(self):
        """Stop the fork node."""
        if hasattr(self.parent_app, "node_manager"):
            self.parent_app.node_manager.stop()
            messagebox.showinfo("Node Stopped",
                                "Fork node RPC server stopped.",
                                parent=self)
            self.refresh()

    def _gen_key(self):
        try:
            self.backend.generate_new_key()
            self.refresh()
            messagebox.showinfo("Key Generated", "New key pair created.", parent=self)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    def _export(self):
        try:
            path = filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON", "*.json")],
                title="Export Keys",
            )
            if path:
                keys = self.backend.get_keys()
                with open(path, "w") as f:
                    json.dump(keys, f, indent=2)
                messagebox.showinfo("Exported", f"Keys exported to {path}", parent=self)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    def refresh(self):
        try:
            keys = self.backend.get_keys()
            if keys:
                lines = []
                for i, k in enumerate(keys):
                    addr = format_address(k["address"])
                    label = k.get("label", f"Key #{i+1}")
                    lines.append(f"  {label}: {addr}")
                self.keys_list_label.configure(text="\n".join(lines))
            else:
                self.keys_list_label.configure(text="No keys generated yet")
        except Exception:
            pass
        
        # Update node info
        try:
            if hasattr(self, "parent_app") and hasattr(self.parent_app, "node_manager"):
                status = self.parent_app.node_manager.get_status()
                info_lines = [
                    f"  RPC Port: {status['rpc_port']}",
                    f"  Status: {'Running' if status['running'] else 'Stopped'}",
                    f"  Healthy: {'Yes' if status.get('healthy') else 'No'}",
                ]
                self.node_info_label.configure(text="\n".join(info_lines))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Main Application — Sidebar Layout
# ---------------------------------------------------------------------------

class EXCALWallet(ctk.CTk):
    """Main EXCALibur Wallet application with Aetherion design.
    
    Unified installer: starts the fork node, P2P network, and wallet GUI
    from a single executable. Includes onboarding for first-time users.
    """

    def __init__(self):
        super().__init__()
        self.backend = WalletBackend()
        self.current_profile = "default"
        self.node_manager = NodeManager()

        # Appearance
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        # Window
        self.title(APP_NAME)
        self.geometry("1000x700")
        self.minsize(900, 600)
        self.configure(fg_color=COLOR_BG_DEEP)
        
        # Protocol: start the fork node on launch
        threading.Thread(target=self._start_node, daemon=True).start()

        # === Main layout: sidebar + content ===
        main_pane = ctk.CTkFrame(self, fg_color="transparent")
        main_pane.pack(fill="both", expand=True)

        # --- Sidebar ---
        sidebar = ctk.CTkFrame(main_pane, width=220, fg_color=COLOR_BG_LIGHT,
                                border_width=1, border_color=COLOR_PURPLE_DARK)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        # Logo area
        logo_frame = ctk.CTkFrame(sidebar, height=80, fg_color="transparent")
        logo_frame.pack(fill="x", pady=(15, 10))
        logo_frame.pack_propagate(False)

        ctk.CTkLabel(
            logo_frame, text="⚔", font=("Segoe UI Emoji", 32),
            text_color=COLOR_GOLD,
        ).pack(side="left", padx=(15, 5))

        ctk.CTkLabel(
            logo_frame, text="EXCALibur", font=("Segoe UI", 16, "bold"),
            text_color=COLOR_TEXT,
        ).pack(side="left")

        # Version badge
        ctk.CTkLabel(
            sidebar, text=f"v{APP_VERSION}", font=("Segoe UI", 9),
            text_color=COLOR_TEXT_MUTED,
        ).pack(pady=(0, 15))

        # Divider
        ctk.CTkFrame(sidebar, height=1, fg_color=COLOR_PURPLE_DARK).pack(fill="x", padx=15, pady=(0, 15))

        # Profile display
        self.profile_label = ctk.CTkLabel(
            sidebar, text="Default", font=("Segoe UI", 11, "bold"),
            text_color=COLOR_CYAN,
        )
        self.profile_label.pack(pady=(0, 3))

        self.status_indicator = ctk.CTkLabel(
            sidebar, text="● Locked", font=("Segoe UI", 10),
            text_color=COLOR_WARNING,
        )
        self.status_indicator.pack(pady=(0, 5))

        # Node status indicator
        self.node_status_indicator = ctk.CTkLabel(
            sidebar, text="◌ Node: Starting...", font=("Segoe UI", 9),
            text_color=COLOR_TEXT_MUTED,
        )
        self.node_status_indicator.pack(pady=(0, 10))

        # Navigation buttons
        self.nav_buttons = []
        self.tabs = {}
        tab_items = [
            ("📊", "Dashboard"),
            ("⚡", "Send / Receive"),
            ("📜", "Transactions"),
            ("🌐", "Peers"),
            ("⛏", "Mining"),
            ("⚙", "Settings"),
        ]

        for icon, name in tab_items:
            btn = ctk.CTkButton(
                sidebar,
                text=f"{icon}  {name}",
                command=lambda n=name: self._switch_tab(n),
                width=190,
                height=40,
                fg_color="transparent",
                hover_color=COLOR_CARD_HOVER,
                font=("Segoe UI", 12),
                text_color=COLOR_TEXT_DIM,
                anchor="w",
            )
            btn.pack(pady=2, padx=10)
            self.nav_buttons.append((btn, name))

        # Sidebar footer
        footer = ctk.CTkFrame(sidebar, height=80, fg_color="transparent")
        footer.pack(side="bottom", fill="x", pady=(0, 10))
        footer.pack_propagate(False)

        # Help button
        ctk.CTkButton(
            footer, text="❓  Help & Guide",
            command=self._show_help,
            fg_color=COLOR_CARD, hover_color=COLOR_CARD_HOVER,
            border_width=1, border_color=COLOR_CYAN_DARK,
            text_color=COLOR_CYAN, font=("Segoe UI", 10),
            corner_radius=8, height=32,
        ).pack(fill="x", padx=15, pady=(5, 3))

        ctk.CTkLabel(
            footer, text="Aetherion Oracle", font=("Segoe UI", 9),
            text_color=COLOR_TEXT_MUTED,
        ).pack(pady=2)
        ctk.CTkLabel(
            footer, text="AES-256-GCM Encrypted", font=("Segoe UI", 9),
            text_color=COLOR_SUCCESS,
        ).pack(pady=2)

        # --- Content area ---
        self.content_frame = ctk.CTkFrame(main_pane, fg_color=COLOR_BG_DEEP)
        self.content_frame.pack(side="right", fill="both", expand=True)

        # Create tabs
        self.tabs["Dashboard"] = DashboardTab(self.content_frame, self.backend)
        self.tabs["Send / Receive"] = SendReceiveTab(self.content_frame, self.backend)
        self.tabs["Transactions"] = TransactionsTab(self.content_frame, self.backend)
        self.tabs["Peers"] = PeersTab(self.content_frame, self.backend)
        self.tabs["Mining"] = MiningTab(self.content_frame, self.backend)
        self.tabs["Settings"] = SettingsTab(self.content_frame, self.backend)

        # Bind lock event
        self.bind("<<LockWallet>>", self._on_lock)

        # Show login
        self.show_login_window()

    def show_login_window(self):
        self.login_window = LoginWindow(self, self.backend)
        self.wait_window(self.login_window)

    def show_login(self):
        for widget in self.content_frame.winfo_children():
            widget.pack_forget()
        self.show_login_window()

    def switch_wallet(self, profile: str, backend: WalletBackend):
        self.current_profile = profile
        self.backend = backend
        self.profile_label.configure(text=profile.title())
        self.on_wallet_opened()

    def _start_node(self):
        """Start the fork node RPC server."""
        started = self.node_manager.start()
        if started:
            self.after(0, lambda: self.node_status_indicator.configure(
                text="● Node: Running", text_color=COLOR_SUCCESS
            ))
        else:
            self.after(0, lambda: self.node_status_indicator.configure(
                text="◌ Node: Failed", text_color=COLOR_ERROR
            ))

    def _update_node_status(self):
        """Update node status display."""
        status = self.node_manager.get_status()
        if status["running"] and status["healthy"]:
            self.node_status_indicator.configure(
                text="● Node: Running", text_color=COLOR_SUCCESS
            )
        elif status["running"]:
            self.node_status_indicator.configure(
                text="◌ Node: Connecting...", text_color=COLOR_WARNING
            )
        else:
            self.node_status_indicator.configure(
                text="◌ Node: Stopped", text_color=COLOR_TEXT_MUTED
            )

    def on_wallet_opened(self):
        self.status_indicator.configure(text="● Unlocked", text_color=COLOR_SUCCESS)
        threading.Thread(target=self._init_p2p, daemon=True).start()
        self._switch_tab("Dashboard")

        # Start Prometheus metrics server
        threading.Thread(target=self._start_prometheus, daemon=True).start()

        # Update node status periodically
        threading.Thread(target=self._node_status_loop, daemon=True).start()

        # Show onboarding for new wallets (no transactions yet)
        txs = self.backend.get_transactions()
        if not txs:
            # Delay slightly so the main window renders first
            self.after(500, self._show_onboarding)

    def _node_status_loop(self):
        """Periodically update node status in the UI."""
        import time
        while True:
            time.sleep(5)
            self.after(0, self._update_node_status)

    def _start_prometheus(self):
        """Start the Prometheus metrics server."""
        try:
            start_http_server(9435)
        except Exception:
            pass

    def _init_p2p(self):
        try:
            self.backend.initialize_p2p()
        except Exception:
            pass

    def _on_lock(self, event=None):
        self.backend.close()
        self.status_indicator.configure(text="● Locked", text_color=COLOR_WARNING)
        self.show_login()

    def on_exit(self):
        """Clean shutdown — stop node and stratum."""
        self.node_manager.stop()
        # Stop any running stratum servers in MiningTab
        mining_tab = self.tabs.get("Mining")
        if mining_tab and hasattr(mining_tab, "_stratum_process"):
            try:
                mining_tab._stratum_process.terminate()
            except Exception:
                pass

    def _show_help(self):
        """Open the help panel."""
        HelpPanel(self)

    def _show_onboarding(self):
        """Show the onboarding wizard for first-time users."""
        OnboardingWizard(self)

    def _switch_tab(self, tab_name: str):
        for widget in self.content_frame.winfo_children():
            widget.pack_forget()

        if tab_name in self.tabs:
            self.tabs[tab_name].pack(fill="both", expand=True, padx=5, pady=5)
            if hasattr(self.tabs[tab_name], "refresh"):
                self.tabs[tab_name].refresh()

        for btn, name in self.nav_buttons:
            if name == tab_name:
                btn.configure(fg_color=COLOR_CARD_HOVER, text_color=COLOR_CYAN)
            else:
                btn.configure(fg_color="transparent", text_color=COLOR_TEXT_DIM)


def main():
    """Main entry point — supports both GUI and CLI modes.

    CLI mode (like holo_wallet):
        python excal_wallet.py generate
        python excal_wallet.py balance
        python excal_wallet.py send --to ABC123 --amount 10.5
        python excal_wallet.py peers
        python excal_wallet.py status
        python excal_wallet.py --help

    GUI mode (default):
        python excal_wallet.py
    """
    # Check for CLI mode — if any arguments are passed, run as CLI wallet
    if len(sys.argv) > 1 and (sys.argv[1].startswith("-") or sys.argv[1] in (
        "generate", "balance", "send", "peers", "topology",
        "encrypt", "gossip", "status", "help", "mine", "stratum",
    )):
        # Import and run the holo_wallet CLI
        try:
            import holo_wallet
            holo_wallet.main()
            return
        except ImportError:
            print("Error: holo_wallet module not found.", file=sys.stderr)
            sys.exit(1)

    # Default: launch GUI wallet
    app = EXCALWallet()
    app.mainloop()


if __name__ == "__main__":
    main()
