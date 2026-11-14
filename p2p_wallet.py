#!/usr/bin/env python3
"""AetherionEXCAL P2P Wallet — Unified Bitcoin & EXCAL Wallet Application.

A single executable that installs and runs:
- P2P network node with EREPR quantum-inspired gossip protocol
- EXCAL wallet with post-quantum Trifold signatures
- Bitcoin wallet with BIP39/BIP32/BIP44 HD derivation
- CPU mining and Stratum mining server
- Light ledger for both BTC and EXCAL chains
- Encrypted wallet storage (AES-256-GCM + scrypt KDF)
- Desktop icon creation on first run

Features:
- Dual-lane wallet: BTC and EXCAL in one interface
- Encrypted wallet creation with optional passphrase
- P2P networking with automatic peer discovery
- CPU mining for EXCAL blocks
- Stratum mining server for GPU mining
- Light ledger for both chains
- Desktop shortcut creation on first launch
- Onboarding wizard for new users

Usage:
    python p2p_wallet.py

Build (Windows):
    pyinstaller AetherionEXCAL-P2P.spec

Output:
    dist/AetherionEXCAL-P2P.exe
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
from tkinter import messagebox, filedialog, Canvas, PhotoImage, simpledialog

# Import EXCAL components
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
from secp256k1 import generate_keypair, sign_transaction, validate_address

# Import BTC components
from sphinx_os.nexus.btc_wallet_generator import BTCWalletGenerator, base58check_encode

logger = logging.getLogger("p2p_wallet")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COLOR_BG_DEEP = "#0a0a1a"
COLOR_BG_LIGHT = "#12122a"
COLOR_CARD = "#1a1a3a"
COLOR_CARD_HOVER = "#22224a"
COLOR_PURPLE_DARK = "#2a1a4a"
COLOR_PURPLE = "#6a3a9a"
COLOR_CYAN = "#00d4ff"
COLOR_CYAN_DARK = "#006a8a"
COLOR_GOLD = "#ffd700"
COLOR_TEXT = "#e0e0ff"
COLOR_TEXT_DIM = "#8080aa"
COLOR_TEXT_MUTED = "#505070"
COLOR_SUCCESS = "#00ff88"
COLOR_WARNING = "#ffaa00"
COLOR_ERROR = "#ff4444"

WALLET_DIR = Path(os.path.expanduser("~/.excal_p2p_wallet"))
EXCAL_KEYSTORE_FILE = WALLET_DIR / "excal_keystore.json"
BTC_KEYSTORE_FILE = WALLET_DIR / "btc_keystore.json"
WALLET_PROFILES_DIR = WALLET_DIR / "profiles"
APP_VERSION = "3.0.0"
APP_NAME = "AetherionEXCAL P2P Wallet"

# ---------------------------------------------------------------------------
# Desktop Icon Creator
# ---------------------------------------------------------------------------

class DesktopIconCreator:
    """Creates desktop shortcuts and start menu entries."""
    
    @staticmethod
    def create_desktop_shortcut() -> bool:
        """Create a desktop shortcut for the application."""
        try:
            if sys.platform != "win32":
                return False
            
            import pythoncom
            from win32com.shell import shell, shellcon
            
            # Get the executable path
            if hasattr(sys, "_MEIPASS"):
                # PyInstaller runtime
                exe_path = sys.executable
            else:
                # Development mode - skip shortcut creation
                return False
            
            exe_path = os.path.abspath(exe_path)
            if not os.path.exists(exe_path):
                return False
            
            # Get desktop path
            desktop = os.path.join(
                os.environ["USERPROFILE"], "Desktop"
            )
            shortcut_path = os.path.join(desktop, "AetherionEXCAL P2P Wallet.lnk")
            
            # Create shortcut using Windows shell
            pythoncom.CoInitialize()
            try:
                shell.SHGetSpecialFolderLocation(0, shellcon.CSIDL_DESKTOP)
                import win32com.client
                shell = win32com.client.Dispatch("WScript.Shell")
                shortcut = shell.CreateShortCut(shortcut_path)
                shortcut.Targetpath = exe_path
                shortcut.WorkingDirectory = os.path.dirname(exe_path)
                shortcut.Description = "AetherionEXCAL P2P Wallet - Bitcoin & EXCAL"
                shortcut.IconLocation = exe_path + ",0"
                shortcut.save()
                return True
            finally:
                pythoncom.CoUninitialize()
                
        except Exception as e:
            logger.warning(f"Failed to create desktop shortcut: {e}")
            return False
    
    @staticmethod
    def create_start_menu_shortcut() -> bool:
        """Create a Start Menu shortcut for the application."""
        try:
            if sys.platform != "win32":
                return False
            
            if hasattr(sys, "_MEIPASS"):
                exe_path = os.path.abspath(sys.executable)
            else:
                return False
            
            if not os.path.exists(exe_path):
                return False
            
            import win32com.client
            shell = win32com.client.Dispatch("WScript.Shell")
            
            # Get Start Menu path
            start_menu = os.path.join(
                os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs"
            )
            os.makedirs(start_menu, exist_ok=True)
            
            shortcut_path = os.path.join(start_menu, "AetherionEXCAL P2P Wallet.lnk")
            shortcut = shell.CreateShortCut(shortcut_path)
            shortcut.Targetpath = exe_path
            shortcut.WorkingDirectory = os.path.dirname(exe_path)
            shortcut.Description = "AetherionEXCAL P2P Wallet - Bitcoin & EXCAL"
            shortcut.IconLocation = exe_path + ",0"
            shortcut.save()
            return True
            
        except Exception as e:
            logger.warning(f"Failed to create Start Menu shortcut: {e}")
            return False


# ---------------------------------------------------------------------------
# Node Manager
# ---------------------------------------------------------------------------

class NodeManager:
    """Manages the EXCAL fork node RPC server as a background process."""
    
    RPC_PORT = 9432
    
    def __init__(self):
        self.process = None
        self.running = False
        self.server = None
        self.p2p_node = None
        self._stop_event = threading.Event()
        self._health_check_thread = None
        self.chain_file = Path(os.path.dirname(os.path.abspath(__file__))) / "chain.jsonl"
        
        if hasattr(sys, "_MEIPASS"):
            self._meipass = Path(sys._MEIPASS)
            exe_dir = Path(sys.executable).parent
            self.chain_file = exe_dir / "chain.jsonl"
            if not self.chain_file.exists():
                self.chain_file = Path.cwd() / "chain.jsonl"
    
    def start(self) -> bool:
        """Start the fork node RPC server. Returns True if started."""
        if self.running:
            return True
        
        if not self.chain_file.exists():
            try:
                self.chain_file.parent.mkdir(parents=True, exist_ok=True)
                import genesis_fork
                genesis_fork.main()
            except Exception:
                pass
        
        if not self.chain_file.exists():
            return False
        
        try:
            if hasattr(sys, "_MEIPASS"):
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
                self._start_in_thread()
            
            self.running = True
            self._stop_event.clear()
            
            self._health_check_thread = threading.Thread(
                target=self._health_check_loop, daemon=True
            )
            self._health_check_thread.start()
            
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
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
            self.process = None
    
    def is_healthy(self) -> bool:
        """Check if the node is responding to RPC calls."""
        try:
            conn = http.client.HTTPConnection("127.0.0.1", self.RPC_PORT, timeout=2)
            conn.request("POST", "/", json={"jsonrpc": "2.0", "method": "getblockcount", "params": [], "id": 1})
            resp = conn.getresponse()
            return resp.status == 200
        except Exception:
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get node status information."""
        return {
            "running": self.running,
            "healthy": self.is_healthy(),
            "chain_file": str(self.chain_file),
        }
    
    def _health_check_loop(self):
        """Periodically check node health."""
        while not self._stop_event.is_set():
            time.sleep(5)
            if not self.is_healthy():
                self.running = False


# ---------------------------------------------------------------------------
# BTC Balance Checker
# ---------------------------------------------------------------------------

class BTCBalanceChecker:
    """Checks Bitcoin balance via mempool.space API."""
    
    API_URL = "mempool.space"
    
    @staticmethod
    def get_balance(address: str) -> Dict[str, Any]:
        """Get BTC balance for an address.
        
        Returns:
            Dict with 'confirmed', 'unconfirmed', 'total' (in satoshis)
        """
        try:
            conn = http.client.HTTPConnection(BTCBalanceChecker.API_URL)
            conn.request("GET", f"/api/address/{address}")
            resp = conn.getresponse()
            data = json.loads(resp.read().decode())
            
            return {
                "confirmed": data.get("chain_stats", {}).get("funded_balance", 0),
                "unconfirmed": data.get("mempool_stats", {}).get("funded_balance", 0),
                "total": data.get("chain_stats", {}).get("funded_balance", 0) + 
                        data.get("mempool_stats", {}).get("funded_balance", 0),
                "received": data.get("chain_stats", {}).get("funded_balance", 0),
                "sent": data.get("chain_stats", {}).get("spent_balance", 0),
            }
        except Exception as e:
            logger.warning(f"Failed to fetch BTC balance: {e}")
            return {"confirmed": 0, "unconfirmed": 0, "total": 0, "received": 0, "sent": 0}
    
    @staticmethod
    def get_transactions(address: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent transactions for an address."""
        try:
            conn = http.client.HTTPConnection(BTCBalanceChecker.API_URL)
            conn.request("GET", f"/api/address/{address}/txs/chain?limit={limit}")
            resp = conn.getresponse()
            data = json.loads(resp.read().decode())
            
            txs = []
            for tx in data[:limit]:
                txs.append({
                    "txid": tx.get("txid", ""),
                    "value": tx.get("value", 0),
                    "fee": tx.get("fee", 0),
                    "block_height": tx.get("status", {}).get("block_height", -1),
                    "timestamp": tx.get("status", {}).get("block_time", 0),
                })
            return txs
        except Exception as e:
            logger.warning(f"Failed to fetch BTC transactions: {e}")
            return []


# ---------------------------------------------------------------------------
# Wallet Backend (Dual Lane: EXCAL + BTC)
# ---------------------------------------------------------------------------

class DualWalletBackend:
    """Backend logic for dual-lane wallet (EXCAL + BTC)."""
    
    def __init__(self, profile: str = "default"):
        self.profile = profile
        self.excal_keystore: Optional[KeyStore] = None
        self.btc_wallet: Optional[Dict[str, Any]] = None
        self._passphrase: Optional[str] = None
        self._initialized = False
        self.p2p = None
        self.erepr = None
        
        if profile == "default":
            self.excal_keystore_path = EXCAL_KEYSTORE_FILE
            self.btc_keystore_path = BTC_KEYSTORE_FILE
        else:
            if (not profile or profile in (".", "..")
                    or any(char not in
                           "abcdefghijklmnopqrstuvwxyz"
                           "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                           "0123456789_-" for char in profile)):
                raise ValueError("Invalid wallet profile name")
            self.excal_keystore_path = WALLET_PROFILES_DIR / f"{profile}_excal.json"
            self.btc_keystore_path = WALLET_PROFILES_DIR / f"{profile}_btc.json"
    
    @staticmethod
    def list_profiles() -> List[Dict[str, str]]:
        """List available wallet profiles."""
        profiles = []
        if EXCAL_KEYSTORE_FILE.exists():
            profiles.append({"name": "default", "label": "Default"})
        if WALLET_PROFILES_DIR.exists():
            for f in WALLET_PROFILES_DIR.glob("*_excal.json"):
                name = f.stem.replace("_excal", "")
                profiles.append({"name": name, "label": name.title()})
        return profiles
    
    def excal_wallet_exists(self) -> bool:
        """Check if an EXCAL wallet exists for this profile."""
        return self.excal_keystore_path.exists()
    
    def btc_wallet_exists(self) -> bool:
        """Check if a BTC wallet exists for this profile."""
        return self.btc_keystore_path.exists()
    
    def create_excal_wallet(self, passphrase: str):
        """Create a new EXCAL wallet."""
        if self.excal_wallet_exists():
            raise FileExistsError("EXCAL wallet already exists")
        
        self.excal_keystore_path.parent.mkdir(parents=True, exist_ok=True)
        self.excal_keystore = KeyStore.create(passphrase, str(self.excal_keystore_path))
        self._passphrase = passphrase
        
        kp = generate_keypair()
        self.excal_keystore.add_key(kp["private_key"], kp["public_key"], kp["address"], "Main Key")
        self.excal_keystore.save(str(self.excal_keystore_path))
        self._initialized = True
        self.initialize_p2p()
    
    def create_btc_wallet(self, passphrase: str = None) -> Dict[str, str]:
        """Create a new BTC wallet with optional encryption.
        
        Returns:
            Dict with mnemonic, address, and encrypted storage info
        """
        self.btc_keystore_path.parent.mkdir(parents=True, exist_ok=True)
        
        generator = BTCWalletGenerator()
        wallet = generator.generate_wallet()
        
        # Store wallet data
        btc_data = {
            "mnemonic": wallet.mnemonic,
            "address": wallet.address,
            "derivation_path": wallet.derivation_path,
            "created_at": time.time(),
        }
        
        # Encrypt if passphrase provided
        if passphrase:
            encrypted = self._encrypt_btc_data(btc_data, passphrase)
            with open(self.btc_keystore_path, 'w') as f:
                json.dump(encrypted, f)
        else:
            # Store unencrypted with warning
            with open(self.btc_keystore_path, 'w') as f:
                json.dump(btc_data, f)
        
        self.btc_wallet = btc_data
        return {
            "mnemonic": wallet.mnemonic,
            "address": wallet.address,
            "public_key": wallet.public_key.hex(),
        }
    
    def _encrypt_btc_data(self, data: Dict, passphrase: str) -> Dict:
        """Encrypt BTC wallet data with passphrase."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
        import base64
        
        salt = os.urandom(16)
        kdf = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1)
        key = kdf.derive(passphrase.encode())
        
        aesgcm = AESGCM(key)
        plaintext = json.dumps(data).encode()
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        
        return {
            "salt": base64.b64encode(salt).decode(),
            "nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(ciphertext).decode(),
        }
    
    def _decrypt_btc_data(self, encrypted: Dict, passphrase: str) -> Dict:
        """Decrypt BTC wallet data with passphrase."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
        import base64
        
        salt = base64.b64decode(encrypted["salt"])
        nonce = base64.b64decode(encrypted["nonce"])
        ciphertext = base64.b64decode(encrypted["ciphertext"])
        
        kdf = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1)
        key = kdf.derive(passphrase.encode())
        
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return json.loads(plaintext.decode())
    
    def open_excal_wallet(self, passphrase: str):
        """Open an existing EXCAL wallet."""
        self.excal_keystore = KeyStore.load(str(self.excal_keystore_path), passphrase)
        self._passphrase = passphrase
        self._initialized = True
        self.initialize_p2p()
    
    def open_btc_wallet(self, passphrase: str = None) -> Dict[str, str]:
        """Open an existing BTC wallet.
        
        Returns:
            Dict with address and mnemonic (if unencrypted)
        """
        with open(self.btc_keystore_path, 'r') as f:
            data = json.load(f)
        
        # Check if encrypted
        if "ciphertext" in data:
            if not passphrase:
                raise ValueError("BTC wallet is encrypted, passphrase required")
            data = self._decrypt_btc_data(data, passphrase)
        
        self.btc_wallet = data
        return {
            "address": data["address"],
            "mnemonic": data.get("mnemonic", ""),
        }
    
    def get_excal_address(self) -> Optional[str]:
        """Get the primary EXCAL wallet address."""
        if not self.excal_keystore or not self.excal_keystore.keys:
            return None
        return self.excal_keystore.keys[0].address
    
    def get_btc_address(self) -> Optional[str]:
        """Get the BTC wallet address."""
        if not self.btc_wallet:
            return None
        return self.btc_wallet.get("address")
    
    def get_excal_balance(self) -> int:
        """Get EXCAL balance in swords."""
        try:
            address = self.get_excal_address()
            if not address:
                return 0
            
            response = self._rpc("getbalance", [address])
            if isinstance(response, dict):
                return response.get("balance", 0)
            return 0
        except Exception:
            return 0
    
    def get_btc_balance(self) -> Dict[str, Any]:
        """Get BTC balance via mempool.space API."""
        address = self.get_btc_address()
        if not address:
            return {"confirmed": 0, "unconfirmed": 0, "total": 0}
        return BTCBalanceChecker.get_balance(address)
    
    def get_excal_transactions(self) -> List[Dict[str, Any]]:
        """Get EXCAL transaction history."""
        try:
            address = self.get_excal_address()
            if not address:
                return []
            
            response = self._rpc("gettransactions", [address])
            if isinstance(response, dict):
                return response.get("transactions", [])
            return []
        except Exception:
            return []
    
    def get_btc_transactions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get BTC transaction history via mempool.space API."""
        address = self.get_btc_address()
        if not address:
            return []
        return BTCBalanceChecker.get_transactions(address, limit)
    
    def send_excal(self, to_address: str, amount: float) -> Dict[str, Any]:
        """Send EXCAL to an address."""
        if not self.excal_keystore:
            raise RuntimeError("EXCAL wallet not unlocked")
        
        try:
            tx = build_pqh_transaction(
                self.excal_keystore.keys[0].private_key,
                to_address,
                amount_to_swords(amount),
            )
            result = self._rpc("sendrawtransaction", [tx])
            return result
        except Exception as e:
            return {"error": str(e)}
    
    def initialize_p2p(self):
        """Initialize P2P networking."""
        try:
            self.p2p = HolographicP2PLayer()
            self.erepr = EREPRProtocol(self.p2p)
        except Exception as e:
            logger.warning(f"Failed to initialize P2P: {e}")
    
    def _rpc(self, method: str, params: list = None) -> Any:
        """Make an RPC call to the local node."""
        try:
            conn = http.client.HTTPConnection("127.0.0.1", NodeManager.RPC_PORT, timeout=5)
            payload = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params or [],
                "id": 1,
            }
            conn.request("POST", "/", json=payload)
            resp = conn.getresponse()
            data = json.loads(resp.read().decode())
            return data.get("result", data.get("error", {}))
        except Exception as e:
            logger.warning(f"RPC call failed: {method} - {e}")
            return {"error": str(e)}
    
    def close(self):
        """Close the wallet."""
        self.excal_keystore = None
        self.btc_wallet = None
        self._passphrase = None
        self._initialized = False


# ---------------------------------------------------------------------------
# UI Components
# ---------------------------------------------------------------------------

class AnimatedBackground(Canvas):
    """Canvas that draws animated orbital rings and particles."""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=COLOR_BG_DEEP, highlightthickness=0, **kwargs)
        self.particles = []
        self.rings = []
        self._create_particles()
        self._create_rings()
        self.after(50, self._animate)
    
    def _create_particles(self):
        for _ in range(50):
            x = secrets.randbelow(800)
            y = secrets.randbelow(600)
            r = secrets.randbelow(3) + 1
            color = secrets.choice([COLOR_CYAN, COLOR_PURPLE, COLOR_GOLD])
            self.particles.append({"x": x, "y": y, "r": r, "color": color,
                                   "dx": (secrets.randbelow(20) - 10) / 100,
                                   "dy": (secrets.randbelow(20) - 10) / 100})
    
    def _create_rings(self):
        for i in range(3):
            self.rings.append({"radius": 100 + i * 50, "angle": i * 60})
    
    def _animate(self):
        self.delete("all")
        
        # Draw rings
        cx, cy = 400, 300
        for ring in self.rings:
            ring["angle"] += 0.5
            r = ring["radius"] + math.sin(ring["angle"] / 30) * 10
            self.create_oval(cx - r, cy - r, cx + r, cy + r,
                           outline=COLOR_PURPLE_DARK, width=1)
        
        # Draw particles
        for p in self.particles:
            p["x"] += p["dx"]
            p["y"] += p["dy"]
            if p["x"] < 0 or p["x"] > 800:
                p["dx"] *= -1
            if p["y"] < 0 or p["y"] > 600:
                p["dy"] *= -1
            self.create_oval(p["x"], p["y"], p["x"] + p["r"], p["y"] + p["r"],
                           fill=p["color"], outline="")
        
        self.after(50, self._animate)


class GradientButton(ctk.CTkFrame):
    """A button with gradient background effect."""
    
    def __init__(self, parent, text, command=None, **kwargs):
        kwargs.setdefault("fg_color", COLOR_CARD)
        kwargs.setdefault("corner_radius", 12)
        super().__init__(parent, **kwargs)
        
        self.configure(border_width=1, border_color=COLOR_CYAN_DARK)
        
        self.label = ctk.CTkLabel(self, text=text, font=("Segoe UI", 12, "bold"),
                                  text_color=COLOR_CYAN)
        self.label.pack(expand=True, pady=8)
        
        self.bind("<Button-1>", lambda e: (command() if command else None))
        self.bind("<Enter>", lambda e: self.configure(fg_color=COLOR_CARD_HOVER))
        self.bind("<Leave>", lambda e: self.configure(fg_color=COLOR_CARD))


class GlowLabel(ctk.CTkLabel):
    """Label with animated glow effect."""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._glow_phase = 0
        self._animate_glow()
    
    def _animate_glow(self):
        self._glow_phase += 0.05
        alpha = (math.sin(self._glow_phase) + 1) / 2
        # Simplified glow effect
        self.after(50, self._animate_glow)


class GlassCard(ctk.CTkFrame):
    """A card with glassmorphism-like appearance."""
    
    def __init__(self, parent, corner_radius=16, **kwargs):
        kwargs.setdefault("fg_color", COLOR_CARD)
        kwargs.setdefault("corner_radius", corner_radius)
        super().__init__(parent, **kwargs)
        self.configure(border_width=1, border_color=COLOR_PURPLE_DARK)


# ---------------------------------------------------------------------------
# Dashboard Tab
# ---------------------------------------------------------------------------

class DashboardTab(ctk.CTkFrame):
    """Dashboard showing both BTC and EXCAL balances."""
    
    def __init__(self, parent, backend: DualWalletBackend):
        super().__init__(parent, fg_color="transparent")
        self.backend = backend
        
        # Title
        ctk.CTkLabel(self, text="⚔️  Dashboard", font=("Segoe UI", 20, "bold"),
                     text_color=COLOR_GOLD).pack(pady=(10, 20))
        
        # Dual balance cards
        balance_frame = ctk.CTkFrame(self, fg_color="transparent")
        balance_frame.pack(fill="x", padx=20)
        
        # EXCAL Balance Card
        self.excal_card = GlassCard(balance_frame, corner_radius=16)
        self.excal_card.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        ctk.CTkLabel(self.excal_card, text="EXCAL Balance", font=("Segoe UI", 14),
                     text_color=COLOR_CYAN).pack(pady=(10, 5))
        self.excal_balance_label = ctk.CTkLabel(self.excal_card, text="0.00000000 EXCAL",
                                                font=("Segoe UI", 24, "bold"),
                                                text_color=COLOR_TEXT)
        self.excal_balance_label.pack(pady=5)
        self.excal_address_label = ctk.CTkLabel(self.excal_card, text="",
                                                font=("Segoe UI", 10),
                                                text_color=COLOR_TEXT_MUTED, wraplength=250)
        self.excal_address_label.pack(pady=5)
        
        # BTC Balance Card
        self.btc_card = GlassCard(balance_frame, corner_radius=16)
        self.btc_card.pack(side="right", fill="both", expand=True, padx=(10, 0))
        
        ctk.CTkLabel(self.btc_card, text="BTC Balance", font=("Segoe UI", 14),
                     text_color=COLOR_GOLD).pack(pady=(10, 5))
        self.btc_balance_label = ctk.CTkLabel(self.btc_card, text="0.00000000 BTC",
                                              font=("Segoe UI", 24, "bold"),
                                              text_color=COLOR_TEXT)
        self.btc_balance_label.pack(pady=5)
        self.btc_address_label = ctk.CTkLabel(self.btc_card, text="",
                                              font=("Segoe UI", 10),
                                              text_color=COLOR_TEXT_MUTED, wraplength=250)
        self.btc_address_label.pack(pady=5)
        
        # Network info
        info_frame = ctk.CTkFrame(self, fg_color="transparent")
        info_frame.pack(fill="x", padx=20, pady=20)
        
        self.node_status_label = ctk.CTkLabel(info_frame, text="Node: Connecting...",
                                              font=("Segoe UI", 12),
                                              text_color=COLOR_WARNING)
        self.node_status_label.pack(side="left", padx=10)
        
        self.peer_count_label = ctk.CTkLabel(info_frame, text="Peers: 0",
                                             font=("Segoe UI", 12),
                                             text_color=COLOR_TEXT_DIM)
        self.peer_count_label.pack(side="left", padx=10)
        
        self.block_height_label = ctk.CTkLabel(info_frame, text="Block: 0",
                                               font=("Segoe UI", 12),
                                               text_color=COLOR_TEXT_DIM)
        self.block_height_label.pack(side="left", padx=10)
    
    def refresh(self):
        """Refresh balance and status displays."""
        # EXCAL balance
        try:
            balance = self.backend.get_excal_balance()
            excal_amount = balance / SWORD
            self.excal_balance_label.configure(text=f"{excal_amount:.8f} EXCAL")
            
            address = self.backend.get_excal_address()
            if address:
                self.excal_address_label.configure(text=f"Address: {address[:20]}...")
        except Exception:
            pass
        
        # BTC balance
        try:
            btc_balance = self.backend.get_btc_balance()
            btc_amount = btc_balance.get("total", 0) / 1e8
            self.btc_balance_label.configure(text=f"{btc_amount:.8f} BTC")
            
            address = self.backend.get_btc_address()
            if address:
                self.btc_address_label.configure(text=f"Address: {address[:20]}...")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Send/Receive Tab
# ---------------------------------------------------------------------------

class SendReceiveTab(ctk.CTkFrame):
    """Send and receive both BTC and EXCAL."""
    
    def __init__(self, parent, backend: DualWalletBackend):
        super().__init__(parent, fg_color="transparent")
        self.backend = backend
        
        # Tab selection
        ctk.CTkLabel(self, text="⚡ Send / Receive", font=("Segoe UI", 20, "bold"),
                     text_color=COLOR_GOLD).pack(pady=(10, 20))
        
        # Lane selector
        lane_frame = ctk.CTkFrame(self, fg_color="transparent")
        lane_frame.pack(pady=10)
        
        self.btc_btn = ctk.CTkButton(lane_frame, text="🪙 BTC Lane",
                                     command=lambda: self._show_lane("btc"),
                                     fg_color=COLOR_CARD, hover_color=COLOR_CARD_HOVER,
                                     text_color=COLOR_GOLD, width=120)
        self.btc_btn.pack(side="left", padx=10)
        
        self.excal_btn = ctk.CTkButton(lane_frame, text="⚔️  EXCAL Lane",
                                       command=lambda: self._show_lane("excal"),
                                       fg_color=COLOR_CARD, hover_color=COLOR_CARD_HOVER,
                                       text_color=COLOR_CYAN, width=120)
        self.excal_btn.pack(side="left", padx=10)
        
        # Send frame
        self.send_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.send_frame.pack(fill="x", padx=20, pady=20)
        
        GlassCard(self.send_frame).pack(fill="x", pady=10)
        
        self.to_entry = ctk.CTkEntry(self.send_frame, placeholder_text="Recipient address",
                                     font=("Segoe UI", 14), height=40)
        self.to_entry.pack(fill="x", pady=10)
        
        self.amount_entry = ctk.CTkEntry(self.send_frame, placeholder_text="Amount",
                                         font=("Segoe UI", 14), height=40)
        self.amount_entry.pack(fill="x", pady=10)
        
        self.send_btn = ctk.CTkButton(self.send_frame, text="Send", command=self._send,
                                      fg_color=COLOR_CYAN_DARK, hover_color=COLOR_CYAN,
                                      text_color=COLOR_TEXT, height=40, font=("Segoe UI", 14, "bold"))
        self.send_btn.pack(pady=10)
        
        # Receive frame
        receive_frame = ctk.CTkFrame(self, fg_color="transparent")
        receive_frame.pack(fill="x", padx=20, pady=20)
        
        GlassCard(receive_frame).pack(fill="x", pady=10)
        
        self.receive_address_label = ctk.CTkLabel(receive_frame, text="No wallet created",
                                                  font=("Segoe UI", 12),
                                                  text_color=COLOR_TEXT_MUTED, wraplength=400)
        self.receive_address_label.pack(pady=10)
        
        self.copy_btn = ctk.CTkButton(receive_frame, text="Copy Address",
                                      command=self._copy_address,
                                      fg_color=COLOR_PURPLE, hover_color=COLOR_PURPLE_DARK,
                                      text_color=COLOR_TEXT, height=35)
        self.copy_btn.pack(pady=5)
        
        self.current_lane = "excal"
        self._show_lane("excal")
    
    def _show_lane(self, lane: str):
        """Switch between BTC and EXCAL lanes."""
        self.current_lane = lane
        if lane == "btc":
            self.btc_btn.configure(fg_color=COLOR_GOLD)
            self.excal_btn.configure(fg_color=COLOR_CARD)
            self.send_btn.configure(fg_color=COLOR_GOLD, text="Send BTC")
        else:
            self.excal_btn.configure(fg_color=COLOR_CYAN)
            self.btc_btn.configure(fg_color=COLOR_CARD)
            self.send_btn.configure(fg_color=COLOR_CYAN_DARK, text="Send EXCAL")
        
        # Update receive address
        if lane == "btc":
            addr = self.backend.get_btc_address()
        else:
            addr = self.backend.get_excal_address()
        
        if addr:
            self.receive_address_label.configure(text=addr)
        else:
            self.receive_address_label.configure(text=f"No {lane.upper()} wallet created")
    
    def _send(self):
        """Send coins."""
        to = self.to_entry.get().strip()
        amount_str = self.amount_entry.get().strip()
        
        if not to or not amount_str:
            messagebox.showerror("Error", "Please fill in all fields")
            return
        
        try:
            amount = float(amount_str)
        except ValueError:
            messagebox.showerror("Error", "Invalid amount")
            return
        
        if self.current_lane == "excal":
            result = self.backend.send_excal(to, amount)
            if "error" in result:
                messagebox.showerror("Error", result["error"])
            else:
                messagebox.showinfo("Success", f"Sent {amount} EXCAL to {to[:20]}...")
                self.to_entry.delete(0, "end")
                self.amount_entry.delete(0, "end")
        else:
            messagebox.showinfo("Info", "BTC sending requires external transaction builder. "
                                       "Use the BTC address to receive funds.")
    
    def _copy_address(self):
        """Copy receive address to clipboard."""
        if self.current_lane == "btc":
            addr = self.backend.get_btc_address()
        else:
            addr = self.backend.get_excal_address()
        
        if addr:
            self.clipboard_clear()
            self.clipboard_append(addr)
            messagebox.showinfo("Copied", "Address copied to clipboard")


# ---------------------------------------------------------------------------
# Transactions Tab
# ---------------------------------------------------------------------------

class TransactionsTab(ctk.CTkFrame):
    """Transaction history for both BTC and EXCAL."""
    
    def __init__(self, parent, backend: DualWalletBackend):
        super().__init__(parent, fg_color="transparent")
        self.backend = backend
        
        ctk.CTkLabel(self, text="📜 Transactions", font=("Segoe UI", 20, "bold"),
                     text_color=COLOR_GOLD).pack(pady=(10, 20))
        
        # Lane selector
        lane_frame = ctk.CTkFrame(self, fg_color="transparent")
        lane_frame.pack(pady=10)
        
        ctk.CTkButton(lane_frame, text="🪙 BTC", command=lambda: self._show("btc"),
                      fg_color=COLOR_CARD, hover_color=COLOR_CARD_HOVER,
                      text_color=COLOR_GOLD, width=100).pack(side="left", padx=10)
        
        ctk.CTkButton(lane_frame, text="⚔️  EXCAL", command=lambda: self._show("excal"),
                      fg_color=COLOR_CARD, hover_color=COLOR_CARD_HOVER,
                      text_color=COLOR_CYAN, width=100).pack(side="left", padx=10)
        
        # Transaction list
        self.tx_frame = ctk.CTkFrame(self, fg_color=COLOR_CARD, corner_radius=12,
                                     border_width=1, border_color=COLOR_PURPLE_DARK)
        self.tx_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        self.tx_listbox = ctk.CTkScrollableFrame(self.tx_frame, fg_color="transparent")
        self.tx_listbox.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.current_lane = "excal"
        self._show("excal")
    
    def _show(self, lane: str):
        """Show transactions for the selected lane."""
        self.current_lane = lane
        
        # Clear existing
        for widget in self.tx_listbox.winfo_children():
            widget.destroy()
        
        if lane == "btc":
            txs = self.backend.get_btc_transactions()
        else:
            txs = self.backend.get_excal_transactions()
        
        if not txs:
            ctk.CTkLabel(self.tx_listbox, text="No transactions yet",
                        font=("Segoe UI", 14), text_color=COLOR_TEXT_MUTED).pack(pady=20)
            return
        
        for tx in txs[:20]:  # Show last 20
            card = GlassCard(self.tx_listbox, corner_radius=8)
            card.pack(fill="x", pady=2)
            
            txid = tx.get("txid", "")[:16]
            value = tx.get("value", 0)
            if lane == "btc":
                value_str = f"{value / 1e8:.8f} BTC"
            else:
                value_str = f"{value / SWORD:.8f} EXCAL"
            
            ctk.CTkLabel(card, text=f"{txid}...", font=("Segoe UI", 10),
                         text_color=COLOR_CYAN).pack(side="left", padx=10)
            ctk.CTkLabel(card, text=value_str, font=("Segoe UI", 10),
                         text_color=COLOR_TEXT).pack(side="right", padx=10)
    
    def refresh(self):
        """Refresh transaction list."""
        self._show(self.current_lane)


# ---------------------------------------------------------------------------
# Peers Tab
# ---------------------------------------------------------------------------

class PeersTab(ctk.CTkFrame):
    """P2P network peers display."""
    
    def __init__(self, parent, backend: DualWalletBackend):
        super().__init__(parent, fg_color="transparent")
        self.backend = backend
        
        ctk.CTkLabel(self, text="🌐 P2P Network", font=("Segoe UI", 20, "bold"),
                     text_color=COLOR_GOLD).pack(pady=(10, 20))
        
        self.peer_frame = ctk.CTkFrame(self, fg_color=COLOR_CARD, corner_radius=12,
                                       border_width=1, border_color=COLOR_PURPLE_DARK)
        self.peer_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        self.peer_listbox = ctk.CTkScrollableFrame(self.peer_frame, fg_color="transparent")
        self.peer_listbox.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.peer_count = 0
        self._refresh_peers()
    
    def _refresh_peers(self):
        """Refresh peer list from node."""
        for widget in self.peer_listbox.winfo_children():
            widget.destroy()
        
        try:
            response = self.backend._rpc("getpeers")
            if isinstance(response, dict):
                peers = response.get("peers", [])
                self.peer_count = len(peers)
                
                for peer in peers[:50]:
                    card = GlassCard(self.peer_listbox, corner_radius=8)
                    card.pack(fill="x", pady=2)
                    
                    host = peer.get("host", "unknown")
                    ctk.CTkLabel(card, text=host, font=("Segoe UI", 10),
                                 text_color=COLOR_CYAN).pack(side="left", padx=10)
                    
                    status = peer.get("status", "unknown")
                    color = COLOR_SUCCESS if status == "connected" else COLOR_WARNING
                    ctk.CTkLabel(card, text=status, font=("Segoe UI", 10),
                                 text_color=color).pack(side="right", padx=10)
        except Exception:
            ctk.CTkLabel(self.peer_listbox, text="Unable to fetch peers",
                        font=("Segoe UI", 14), text_color=COLOR_TEXT_MUTED).pack(pady=20)
    
    def refresh(self):
        """Refresh peer display."""
        self._refresh_peers()


# ---------------------------------------------------------------------------
# Mining Tab
# ---------------------------------------------------------------------------

class MiningTab(ctk.CTkFrame):
    """CPU mining controls and GPU stratum configuration."""
    
    def __init__(self, parent, backend: DualWalletBackend):
        super().__init__(parent, fg_color="transparent")
        self.backend = backend
        self._miner_process = None
        self._stratum_process = None
        self.mining = False
        self.stratum_running = False
        
        ctk.CTkLabel(self, text="⛏ Mining", font=("Segoe UI", 20, "bold"),
                     text_color=COLOR_GOLD).pack(pady=(10, 20))
        
        # CPU Mining Section
        cpu_frame = GlassCard(self, corner_radius=16)
        cpu_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(cpu_frame, text="CPU Mining (EXCAL)", font=("Segoe UI", 16, "bold"),
                     text_color=COLOR_CYAN).pack(pady=(10, 5))
        
        self.cpu_status_label = ctk.CTkLabel(cpu_frame, text="Stopped", font=("Segoe UI", 12),
                                             text_color=COLOR_WARNING)
        self.cpu_status_label.pack(pady=5)
        
        self.cpu_thread_entry = ctk.CTkEntry(cpu_frame, placeholder_text="Threads (default: 1)",
                                             font=("Segoe UI", 12), width=150)
        self.cpu_thread_entry.pack(pady=5)
        
        self.cpu_mine_btn = ctk.CTkButton(cpu_frame, text="Start Mining",
                                          command=self._toggle_cpu_mining,
                                          fg_color=COLOR_SUCCESS, hover_color=COLOR_CYAN_DARK,
                                          text_color=COLOR_TEXT, height=35)
        self.cpu_mine_btn.pack(pady=10)
        
        # Stratum Section
        stratum_frame = GlassCard(self, corner_radius=16)
        stratum_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(stratum_frame, text="Stratum Server (GPU Mining)", font=("Segoe UI", 16, "bold"),
                     text_color=COLOR_GOLD).pack(pady=(10, 5))
        
        self.stratum_status_label = ctk.CTkLabel(stratum_frame, text="Stopped", font=("Segoe UI", 12),
                                                 text_color=COLOR_WARNING)
        self.stratum_status_label.pack(pady=5)
        
        ctk.CTkLabel(stratum_frame, text="Port: 9434", font=("Segoe UI", 10),
                     text_color=COLOR_TEXT_MUTED).pack(pady=5)
        
        self.stratum_btn = ctk.CTkButton(stratum_frame, text="Start Stratum Server",
                                         command=self._toggle_stratum,
                                         fg_color=COLOR_GOLD, hover_color=COLOR_PURPLE,
                                         text_color=COLOR_TEXT, height=35)
        self.stratum_btn.pack(pady=10)
        
        # Mining stats
        stats_frame = GlassCard(self, corner_radius=16)
        stats_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(stats_frame, text="Mining Statistics", font=("Segoe UI", 16, "bold"),
                     text_color=COLOR_TEXT).pack(pady=(10, 5))
        
        self.hashrate_label = ctk.CTkLabel(stats_frame, text="Hashrate: 0 H/s", font=("Segoe UI", 12),
                                           text_color=COLOR_TEXT_DIM)
        self.hashrate_label.pack(pady=5)
        
        self.blocks_label = ctk.CTkLabel(stats_frame, text="Blocks mined: 0", font=("Segoe UI", 12),
                                         text_color=COLOR_TEXT_DIM)
        self.blocks_label.pack(pady=5)
    
    def _toggle_cpu_mining(self):
        """Toggle CPU mining."""
        if not self.mining:
            threads = self.cpu_thread_entry.get().strip() or "1"
            try:
                threads = int(threads)
            except ValueError:
                threads = 1
            
            try:
                if hasattr(sys, "_MEIPASS"):
                    miner_script = Path(sys._MEIPASS) / "cpu_miner.py"
                else:
                    miner_script = Path(os.path.dirname(os.path.abspath(__file__))) / "cpu_miner.py"
                
                self._miner_process = subprocess.Popen(
                    [sys.executable, str(miner_script), "--threads", str(threads)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                self.mining = True
                self.cpu_status_label.configure(text="Mining...", text_color=COLOR_SUCCESS)
                self.cpu_mine_btn.configure(text="Stop Mining", fg_color=COLOR_ERROR)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to start mining: {e}")
        else:
            if self._miner_process:
                self._miner_process.terminate()
                self._miner_process = None
            self.mining = False
            self.cpu_status_label.configure(text="Stopped", text_color=COLOR_WARNING)
            self.cpu_mine_btn.configure(text="Start Mining", fg_color=COLOR_SUCCESS)
    
    def _toggle_stratum(self):
        """Toggle Stratum mining server."""
        if not self.stratum_running:
            try:
                if hasattr(sys, "_MEIPASS"):
                    stratum_script = Path(sys._MEIPASS) / "stratum_fork.py"
                else:
                    stratum_script = Path(os.path.dirname(os.path.abspath(__file__))) / "stratum_fork.py"
                
                self._stratum_process = subprocess.Popen(
                    [sys.executable, str(stratum_script)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                self.stratum_running = True
                self.stratum_status_label.configure(text="Running on port 9434", text_color=COLOR_SUCCESS)
                self.stratum_btn.configure(text="Stop Stratum Server", fg_color=COLOR_ERROR)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to start Stratum: {e}")
        else:
            if self._stratum_process:
                self._stratum_process.terminate()
                self._stratum_process = None
            self.stratum_running = False
            self.stratum_status_label.configure(text="Stopped", text_color=COLOR_WARNING)
            self.stratum_btn.configure(text="Start Stratum Server", fg_color=COLOR_GOLD)
    
    def stop_all(self):
        """Stop all mining processes."""
        if self._miner_process:
            self._miner_process.terminate()
            self._miner_process = None
        if self._stratum_process:
            self._stratum_process.terminate()
            self._stratum_process = None
        self.mining = False
        self.stratum_running = False


# ---------------------------------------------------------------------------
# Settings Tab
# ---------------------------------------------------------------------------

class SettingsTab(ctk.CTkFrame):
    """Settings, node management, and about."""
    
    def __init__(self, parent, backend: DualWalletBackend):
        super().__init__(parent, fg_color="transparent")
        self.backend = backend
        
        ctk.CTkLabel(self, text="⚙ Settings", font=("Segoe UI", 20, "bold"),
                     text_color=COLOR_GOLD).pack(pady=(10, 20))
        
        # Node settings
        node_frame = GlassCard(self, corner_radius=16)
        node_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(node_frame, text="Node Settings", font=("Segoe UI", 16, "bold"),
                     text_color=COLOR_CYAN).pack(pady=(10, 5))
        
        self.node_status_label = ctk.CTkLabel(node_frame, text="Checking...", font=("Segoe UI", 12),
                                              text_color=COLOR_TEXT_MUTED)
        self.node_status_label.pack(pady=5)
        
        ctk.CTkButton(node_frame, text="Restart Node", command=self._restart_node,
                      fg_color=COLOR_PURPLE, hover_color=COLOR_PURPLE_DARK,
                      text_color=COLOR_TEXT, height=35).pack(pady=10)
        
        # Wallet settings
        wallet_frame = GlassCard(self, corner_radius=16)
        wallet_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(wallet_frame, text="Wallet Security", font=("Segoe UI", 16, "bold"),
                     text_color=COLOR_GOLD).pack(pady=(10, 5))
        
        ctk.CTkButton(wallet_frame, text="Change Passphrase", command=self._change_passphrase,
                      fg_color=COLOR_CARD_HOVER, hover_color=COLOR_PURPLE,
                      text_color=COLOR_TEXT, height=35).pack(pady=5)
        
        ctk.CTkButton(wallet_frame, text="Export Backup", command=self._export_backup,
                      fg_color=COLOR_CARD_HOVER, hover_color=COLOR_PURPLE,
                      text_color=COLOR_TEXT, height=35).pack(pady=5)
        
        ctk.CTkButton(wallet_frame, text="Lock Wallet", command=self._lock_wallet,
                      fg_color=COLOR_ERROR, hover_color=COLOR_WARNING,
                      text_color=COLOR_TEXT, height=35).pack(pady=5)
        
        # About
        about_frame = GlassCard(self, corner_radius=16)
        about_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(about_frame, text="About", font=("Segoe UI", 16, "bold"),
                     text_color=COLOR_TEXT).pack(pady=(10, 5))
        
        ctk.CTkLabel(about_frame, text=f"{APP_NAME} v{APP_VERSION}", font=("Segoe UI", 12),
                     text_color=COLOR_GOLD).pack(pady=5)
        
        ctk.CTkLabel(about_frame, text="Post-Quantum Bitcoin Fork Wallet", font=("Segoe UI", 10),
                     text_color=COLOR_TEXT_MUTED).pack(pady=5)
        
        ctk.CTkLabel(about_frame, text="AES-256-GCM Encrypted | Trifold PQ Signatures", font=("Segoe UI", 10),
                     text_color=COLOR_SUCCESS).pack(pady=5)
        
        self._update_node_status()
    
    def _update_node_status(self):
        """Update node status display."""
        try:
            from excal_wallet import NodeManager
            status = NodeManager().get_status()
            if status.get("healthy"):
                self.node_status_label.configure(text="Node: Running", text_color=COLOR_SUCCESS)
            else:
                self.node_status_label.configure(text="Node: Stopped", text_color=COLOR_WARNING)
        except Exception:
            self.node_status_label.configure(text="Node: Unknown", text_color=COLOR_TEXT_MUTED)
    
    def _restart_node(self):
        """Restart the node."""
        messagebox.showinfo("Info", "Node restart requires application restart. Please close and reopen.")
    
    def _change_passphrase(self):
        """Change wallet passphrase."""
        messagebox.showinfo("Info", "Passphrase change requires wallet re-encryption. "
                                   "Please export backup and create new wallet.")
    
    def _export_backup(self):
        """Export wallet backup."""
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile="excal_wallet_backup.json"
        )
        if path:
            try:
                backup = {
                    "excal_keystore_path": str(self.backend.excal_keystore_path),
                    "btc_keystore_path": str(self.backend.btc_keystore_path),
                    "created_at": time.time(),
                }
                with open(path, 'w') as f:
                    json.dump(backup, f, indent=2)
                messagebox.showinfo("Success", "Backup exported successfully")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export: {e}")
    
    def _lock_wallet(self):
        """Lock the wallet."""
        self.backend.close()
        self.event_generate("<<LockWallet>>")
    
    def refresh(self):
        """Refresh settings display."""
        self._update_node_status()


# ---------------------------------------------------------------------------
# Login Window
# ---------------------------------------------------------------------------

class LoginWindow(ctk.CTkToplevel):
    """Login/create wallet window with dual-lane support."""
    
    def __init__(self, parent, backend: DualWalletBackend):
        super().__init__(parent)
        self.backend = backend
        self.parent = parent
        
        self.title("AetherionEXCAL Wallet Login")
        self.geometry("500x600")
        self.resizable(False, False)
        self.configure(fg_color=COLOR_BG_DEEP)
        
        # Center on parent
        self.transient(parent)
        self.grab_set()
        
        # Animated background
        bg = AnimatedBackground(self)
        bg.place(x=0, y=0, relwidth=1, relheight=1)
        
        # Content frame
        content = ctk.CTkFrame(self, fg_color=COLOR_CARD, corner_radius=20)
        content.place(relx=0.5, rely=0.5, anchor="center", width=400, height=500)
        
        # Logo
        ctk.CTkLabel(content, text="⚔", font=("Segoe UI Emoji", 48),
                     text_color=COLOR_GOLD).pack(pady=(20, 10))
        
        ctk.CTkLabel(content, text="AetherionEXCAL", font=("Segoe UI", 24, "bold"),
                     text_color=COLOR_GOLD).pack(pady=5)
        
        ctk.CTkLabel(content, text="P2P Wallet v3.0.0", font=("Segoe UI", 12),
                     text_color=COLOR_TEXT_MUTED).pack(pady=5)
        
        # Passphrase entry
        ctk.CTkLabel(content, text="Passphrase", font=("Segoe UI", 12),
                     text_color=COLOR_TEXT).pack(pady=(10, 5))
        
        self.passphrase_entry = ctk.CTkEntry(content, show="*", font=("Segoe UI", 14),
                                             height=40, corner_radius=10)
        self.passphrase_entry.pack(fill="x", padx=30, pady=5)
        
        self.passphrase_entry.bind("<Return>", lambda e: self._login())
        
        # Buttons
        btn_frame = ctk.CTkFrame(content, fg_color="transparent")
        btn_frame.pack(fill="x", padx=30, pady=20)
        
        ctk.CTkButton(btn_frame, text="Login", command=self._login,
                      fg_color=COLOR_CYAN_DARK, hover_color=COLOR_CYAN,
                      text_color=COLOR_TEXT, height=40, font=("Segoe UI", 14, "bold")).pack(
            fill="x", pady=5)
        
        ctk.CTkButton(btn_frame, text="Create New Wallet", command=self._create_wallet,
                      fg_color=COLOR_SUCCESS, hover_color=COLOR_PURPLE,
                      text_color=COLOR_TEXT, height=40, font=("Segoe UI", 14, "bold")).pack(
            fill="x", pady=5)
        
        # Wallet type selection
        type_frame = ctk.CTkFrame(content, fg_color="transparent")
        type_frame.pack(fill="x", padx=30, pady=10)
        
        ctk.CTkLabel(type_frame, text="Wallet Type:", font=("Segoe UI", 12),
                     text_color=COLOR_TEXT).pack(pady=5)
        
        self.wallet_type_var = ctk.StringVar(value="both")
        ctk.CTkRadioButton(type_frame, text="EXCAL Only", variable=self.wallet_type_var,
                          value="excal", fg_color=COLOR_CYAN, text_color=COLOR_TEXT).pack(
            anchor="w", padx=20, pady=2)
        ctk.CTkRadioButton(type_frame, text="BTC Only", variable=self.wallet_type_var,
                          value="btc", fg_color=COLOR_GOLD, text_color=COLOR_TEXT).pack(
            anchor="w", padx=20, pady=2)
        ctk.CTkRadioButton(type_frame, text="Both (Dual Lane)", variable=self.wallet_type_var,
                          value="both", fg_color=COLOR_PURPLE, text_color=COLOR_TEXT).pack(
            anchor="w", padx=20, pady=2)
        
        # Encryption option
        self.encrypt_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(type_frame, text="Encrypt BTC wallet with passphrase",
                       variable=self.encrypt_var, fg_color=COLOR_GOLD,
                       text_color=COLOR_TEXT).pack(anchor="w", padx=20, pady=5)
    
    def _login(self):
        """Login with passphrase."""
        passphrase = self.passphrase_entry.get().strip()
        if not passphrase:
            messagebox.showerror("Error", "Please enter passphrase")
            return
        
        try:
            wallet_type = self.wallet_type_var.get()
            
            if wallet_type in ("excal", "both"):
                if self.backend.excal_wallet_exists():
                    self.backend.open_excal_wallet(passphrase)
                else:
                    messagebox.showerror("Error", "EXCAL wallet not found. Create new wallet.")
                    return
            
            if wallet_type in ("btc", "both"):
                if self.backend.btc_wallet_exists():
                    encrypt = self.encrypt_var.get()
                    self.backend.open_btc_wallet(passphrase if encrypt else None)
                else:
                    if wallet_type == "btc":
                        messagebox.showerror("Error", "BTC wallet not found. Create new wallet.")
                        return
            
            self.destroy()
            self.parent.on_wallet_opened()
            
        except Exception as e:
            messagebox.showerror("Error", f"Login failed: {e}")
    
    def _create_wallet(self):
        """Create new wallet."""
        passphrase = self.passphrase_entry.get().strip()
        if not passphrase:
            messagebox.showerror("Error", "Please enter a passphrase")
            return
        
        if len(passphrase) < 8:
            messagebox.showerror("Error", "Passphrase must be at least 8 characters")
            return
        
        # Confirm
        confirm = messagebox.askyesno("Create Wallet", 
            "This will create a new wallet. Make sure you remember your passphrase!\n\n"
            "For BTC wallet, you will also receive a 12-word mnemonic - save it securely!")
        
        if not confirm:
            return
        
        try:
            wallet_type = self.wallet_type_var.get()
            
            if wallet_type in ("excal", "both"):
                if self.backend.excal_wallet_exists():
                    messagebox.showwarning("Warning", "EXCAL wallet already exists. Opening existing wallet.")
                    self.backend.open_excal_wallet(passphrase)
                else:
                    self.backend.create_excal_wallet(passphrase)
                    messagebox.showinfo("Success", "EXCAL wallet created!")
            
            if wallet_type in ("btc", "both"):
                if self.backend.btc_wallet_exists():
                    messagebox.showwarning("Warning", "BTC wallet already exists. Opening existing wallet.")
                    encrypt = self.encrypt_var.get()
                    self.backend.open_btc_wallet(passphrase if encrypt else None)
                else:
                    encrypt = self.encrypt_var.get()
                    result = self.backend.create_btc_wallet(passphrase if encrypt else None)
                    
                    # Show mnemonic to user
                    mnemonic = result["mnemonic"]
                    address = result["address"]
                    
                    # Display mnemonic in a special window
                    mnemonic_window = ctk.CTkToplevel(self)
                    mnemonic_window.title("⚠️  SAVE YOUR BTC MNEMONIC")
                    mnemonic_window.geometry("500x400")
                    mnemonic_window.configure(fg_color=COLOR_BG_DEEP)
                    mnemonic_window.transient(self)
                    mnemonic_window.grab_set()
                    
                    ctk.CTkLabel(mnemonic_window, 
                                text="⚠️  SAVE THESE 12 WORDS ⚠️",
                                font=("Segoe UI", 18, "bold"),
                                text_color=COLOR_ERROR).pack(pady=(20, 10))
                    
                    ctk.CTkLabel(mnemonic_window,
                                text="This is your ONLY backup. If lost, BTC cannot be recovered!",
                                font=("Segoe UI", 12),
                                text_color=COLOR_WARNING,
                                wraplength=400).pack(pady=5)
                    
                    # Mnemonic display
                    mnemonic_frame = GlassCard(mnemonic_window, corner_radius=12)
                    mnemonic_frame.pack(fill="both", expand=True, padx=30, pady=10)
                    
                    text_box = ctk.Text(mnemonic_frame, wrap="word", font=("Consolas", 14),
                                       bg=COLOR_CARD, fg=COLOR_GOLD, insertbackground=COLOR_GOLD)
                    text_box.pack(fill="both", expand=True, padx=10, pady=10)
                    text_box.insert("1.0", mnemonic)
                    text_box.config(state="disabled")
                    
                    ctk.CTkLabel(mnemonic_window,
                                text=f"BTC Address: {address}",
                                font=("Segoe UI", 10),
                                text_color=COLOR_TEXT_MUTED,
                                wraplength=400).pack(pady=5)
                    
                    def close_mnemonic():
                        mnemonic_window.destroy()
                    
                    ctk.CTkButton(mnemonic_window, text="I Have Saved My Mnemonic",
                                 command=close_mnemonic,
                                 fg_color=COLOR_SUCCESS, hover_color=COLOR_CYAN_DARK,
                                 text_color=COLOR_TEXT, height=40,
                                 font=("Segoe UI", 12, "bold")).pack(pady=10)
                    
                    # Wait for user to acknowledge
                    self.wait_window(mnemonic_window)
                    messagebox.showinfo("Success", "BTC wallet created!")
            
            self.destroy()
            self.parent.on_wallet_opened()
            
        except Exception as e:
            messagebox.showerror("Error", f"Wallet creation failed: {e}")


# ---------------------------------------------------------------------------
# Onboarding Wizard
# ---------------------------------------------------------------------------

class OnboardingWizard(ctk.CTkToplevel):
    """Step-by-step onboarding wizard for new users."""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        
        self.title("Welcome to AetherionEXCAL")
        self.geometry("600x500")
        self.resizable(False, False)
        self.configure(fg_color=COLOR_BG_DEEP)
        
        self.transient(parent)
        self.grab_set()
        
        self.current_step = 0
        self.steps = [
            self._step_welcome,
            self._step_features,
            self._step_dual_lane,
            self._step_security,
            self._step_complete,
        ]
        
        self._show_step()
    
    def _show_step(self):
        """Show current step."""
        for widget in self.winfo_children():
            widget.destroy()
        
        if self.current_step < len(self.steps):
            self.steps[self.current_step]()
        else:
            self.destroy()
    
    def _step_welcome(self):
        """Welcome step."""
        ctk.CTkLabel(self, text="⚔️", font=("Segoe UI Emoji", 64),
                     text_color=COLOR_GOLD).pack(pady=(30, 20))
        
        ctk.CTkLabel(self, text="Welcome to AetherionEXCAL", font=("Segoe UI", 24, "bold"),
                     text_color=COLOR_GOLD).pack(pady=10)
        
        ctk.CTkLabel(self, text="Post-Quantum Bitcoin Fork Wallet", font=("Segoe UI", 14),
                     text_color=COLOR_TEXT_MUTED).pack(pady=5)
        
        ctk.CTkButton(self, text="Next →", command=self._next,
                      fg_color=COLOR_CYAN_DARK, hover_color=COLOR_CYAN,
                      text_color=COLOR_TEXT, height=40, width=150,
                      font=("Segoe UI", 14, "bold")).pack(pady=30)
    
    def _step_features(self):
        """Features step."""
        ctk.CTkLabel(self, text="Features", font=("Segoe UI", 20, "bold"),
                     text_color=COLOR_GOLD).pack(pady=(20, 10))
        
        features = [
            ("🪙", "Bitcoin Wallet", "BIP39/BIP32 HD wallet with encrypted storage"),
            ("⚔️", "EXCAL Wallet", "Post-quantum Trifold signatures"),
            ("🌐", "P2P Network", "Quantum-inspired EREPR gossip protocol"),
            ("⛏", "Mining", "CPU mining + Stratum server for GPU"),
            ("🔒", "Encryption", "AES-256-GCM + scrypt KDF"),
        ]
        
        for icon, title, desc in features:
            card = GlassCard(self, corner_radius=12)
            card.pack(fill="x", padx=40, pady=5)
            
            ctk.CTkLabel(card, text=icon, font=("Segoe UI Emoji", 20),
                         text_color=COLOR_CYAN).pack(side="left", padx=15, pady=10)
            
            text_frame = ctk.CTkFrame(card, fg_color="transparent")
            text_frame.pack(side="left", fill="both", expand=True)
            
            ctk.CTkLabel(text_frame, text=title, font=("Segoe UI", 14, "bold"),
                         text_color=COLOR_TEXT).pack(anchor="w")
            ctk.CTkLabel(text_frame, text=desc, font=("Segoe UI", 10),
                         text_color=COLOR_TEXT_MUTED).pack(anchor="w")
        
        ctk.CTkButton(self, text="Next →", command=self._next,
                      fg_color=COLOR_CYAN_DARK, hover_color=COLOR_CYAN,
                      text_color=COLOR_TEXT, height=40, width=150,
                      font=("Segoe UI", 14, "bold")).pack(pady=20)
    
    def _step_dual_lane(self):
        """Dual lane explanation."""
        ctk.CTkLabel(self, text="Dual-Lane Wallet", font=("Segoe UI", 20, "bold"),
                     text_color=COLOR_GOLD).pack(pady=(20, 10))
        
        ctk.CTkLabel(self, text="Manage both Bitcoin and EXCAL in one wallet", font=("Segoe UI", 14),
                     text_color=COLOR_TEXT_MUTED, wraplength=400).pack(pady=10)
        
        # BTC lane
        btc_card = GlassCard(self, corner_radius=12)
        btc_card.pack(fill="x", padx=40, pady=10)
        
        ctk.CTkLabel(btc_card, text="🪙 BTC Lane", font=("Segoe UI", 16, "bold"),
                     text_color=COLOR_GOLD).pack(pady=10)
        ctk.CTkLabel(btc_card, text="• BIP39 12-word mnemonic\n• BIP32/BIP44 HD derivation\n• "
                     "Base58Check P2PKH addresses\n• Balance check via mempool.space",
                     font=("Segoe UI", 11), text_color=COLOR_TEXT_DIM).pack(pady=5)
        
        # EXCAL lane
        excal_card = GlassCard(self, corner_radius=12)
        excal_card.pack(fill="x", padx=40, pady=10)
        
        ctk.CTkLabel(excal_card, text="⚔️  EXCAL Lane", font=("Segoe UI", 16, "bold"),
                     text_color=COLOR_CYAN).pack(pady=10)
        ctk.CTkLabel(excal_card, text="• Post-quantum Trifold signatures\n• "
                     "Lamport One-Time Signatures\n• Ternary Merkle trees\n• "
                     "Integrated mining and P2P",
                     font=("Segoe UI", 11), text_color=COLOR_TEXT_DIM).pack(pady=5)
        
        ctk.CTkButton(self, text="Next →", command=self._next,
                      fg_color=COLOR_CYAN_DARK, hover_color=COLOR_CYAN,
                      text_color=COLOR_TEXT, height=40, width=150,
                      font=("Segoe UI", 14, "bold")).pack(pady=20)
    
    def _step_security(self):
        """Security explanation."""
        ctk.CTkLabel(self, text="Security", font=("Segoe UI", 20, "bold"),
                     text_color=COLOR_GOLD).pack(pady=(20, 10))
        
        ctk.CTkLabel(self, text="Your wallet is protected by multiple layers of security",
                     font=("Segoe UI", 14), text_color=COLOR_TEXT_MUTED,
                     wraplength=400).pack(pady=10)
        
        security_items = [
            ("🔐", "AES-256-GCM Encryption", "Military-grade encryption for wallet data"),
            ("🔑", "scrypt Key Derivation", "Slow KDF protects against brute force"),
            ("⚔️", "Post-Quantum Signatures", "Protected against quantum computer attacks"),
            ("🛡", "Trifold Lockbox", "Hash-based one-time signatures"),
        ]
        
        for icon, title, desc in security_items:
            card = GlassCard(self, corner_radius=12)
            card.pack(fill="x", padx=40, pady=5)
            
            ctk.CTkLabel(card, text=icon, font=("Segoe UI Emoji", 20),
                         text_color=COLOR_SUCCESS).pack(side="left", padx=15, pady=10)
            
            text_frame = ctk.CTkFrame(card, fg_color="transparent")
            text_frame.pack(side="left", fill="both", expand=True)
            
            ctk.CTkLabel(text_frame, text=title, font=("Segoe UI", 13, "bold"),
                         text_color=COLOR_TEXT).pack(anchor="w")
            ctk.CTkLabel(text_frame, text=desc, font=("Segoe UI", 10),
                         text_color=COLOR_TEXT_MUTED).pack(anchor="w")
        
        ctk.CTkButton(self, text="Next →", command=self._next,
                      fg_color=COLOR_CYAN_DARK, hover_color=COLOR_CYAN,
                      text_color=COLOR_TEXT, height=40, width=150,
                      font=("Segoe UI", 14, "bold")).pack(pady=20)
    
    def _step_complete(self):
        """Complete step."""
        ctk.CTkLabel(self, text="✓", font=("Segoe UI", 64),
                     text_color=COLOR_SUCCESS).pack(pady=(30, 20))
        
        ctk.CTkLabel(self, text="Ready to Start!", font=("Segoe UI", 24, "bold"),
                     text_color=COLOR_GOLD).pack(pady=10)
        
        ctk.CTkLabel(self, text="Your wallet is ready. Start by checking your balance "
                     "or sending/receiving coins.",
                     font=("Segoe UI", 14), text_color=COLOR_TEXT_MUTED,
                     wraplength=400).pack(pady=20)
        
        ctk.CTkButton(self, text="Get Started", command=self._close,
                      fg_color=COLOR_SUCCESS, hover_color=COLOR_CYAN_DARK,
                      text_color=COLOR_TEXT, height=40, width=200,
                      font=("Segoe UI", 14, "bold")).pack(pady=20)
    
    def _next(self):
        """Go to next step."""
        self.current_step += 1
        self._show_step()
    
    def _close(self):
        """Close wizard."""
        self.destroy()


# ---------------------------------------------------------------------------
# Help Panel
# ---------------------------------------------------------------------------

class HelpPanel(ctk.CTkToplevel):
    """Help panel with quick tips and documentation links."""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Help & Guide")
        self.geometry("500x600")
        self.configure(fg_color=COLOR_BG_DEEP)
        
        self.transient(parent)
        
        ctk.CTkLabel(self, text="❓ Help & Guide", font=("Segoe UI", 20, "bold"),
                     text_color=COLOR_GOLD).pack(pady=(20, 10))
        
        help_frame = ctk.CTkScrollableFrame(self, fg_color="transparent", width=450, height=500)
        help_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        # Getting started
        ctk.CTkLabel(help_frame, text="Getting Started", font=("Segoe UI", 16, "bold"),
                     text_color=COLOR_CYAN).pack(pady=(10, 5))
        
        tips = [
            "1. Create a wallet with a strong passphrase",
            "2. Save your BTC mnemonic securely (12 words)",
            "3. Your EXCAL wallet is encrypted with AES-256-GCM",
            "4. Use the Dashboard to check balances",
            "5. Send/Receive tab for transactions",
            "6. Mining tab to start CPU or GPU mining",
            "7. Settings tab for wallet management",
        ]
        
        for tip in tips:
            ctk.CTkLabel(help_frame, text=tip, font=("Segoe UI", 11),
                         text_color=COLOR_TEXT_DIM, anchor="w").pack(fill="x", pady=2, padx=10)
        
        # Security tips
        ctk.CTkLabel(help_frame, text="Security Tips", font=("Segoe UI", 16, "bold"),
                     text_color=COLOR_GOLD).pack(pady=(20, 5))
        
        security_tips = [
            "• Never share your passphrase or mnemonic",
            "• Store your BTC mnemonic offline (write it down)",
            "• Enable encryption for your BTC wallet",
            "• Regularly export wallet backups",
            "• Lock your wallet when not in use",
        ]
        
        for tip in security_tips:
            ctk.CTkLabel(help_frame, text=tip, font=("Segoe UI", 11),
                         text_color=COLOR_TEXT_DIM, anchor="w").pack(fill="x", pady=2, padx=10)
        
        # Links
        ctk.CTkLabel(help_frame, text="Resources", font=("Segoe UI", 16, "bold"),
                     text_color=COLOR_PURPLE).pack(pady=(20, 5))
        
        resources = [
            "Website: https://www.aetherion-oracle.com",
            "GitHub: https://github.com/aetherion/excalibur-chain",
            "Documentation: See README.md",
        ]
        
        for resource in resources:
            ctk.CTkLabel(help_frame, text=resource, font=("Segoe UI", 11),
                         text_color=COLOR_CYAN, anchor="w").pack(fill="x", pady=2, padx=10)
        
        ctk.CTkButton(self, text="Close", command=self.destroy,
                      fg_color=COLOR_CARD, hover_color=COLOR_CARD_HOVER,
                      text_color=COLOR_TEXT, height=35, width=150).pack(pady=20)


# ---------------------------------------------------------------------------
# Main Application
# ---------------------------------------------------------------------------

class P2PWalletApp(ctk.CTk):
    """Main P2P Wallet application with dual-lane BTC/EXCAL support.
    
    Unified installer: starts the fork node, P2P network, and wallet GUI
    from a single executable. Creates desktop icon on first run.
    """
    
    def __init__(self):
        super().__init__()
        self.backend = DualWalletBackend()
        self.node_manager = NodeManager()
        
        # Appearance
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        
        # Window
        self.title(APP_NAME)
        self.geometry("1100x750")
        self.minsize(1000, 650)
        self.configure(fg_color=COLOR_BG_DEEP)
        
        # Create desktop icon on first run (only in PyInstaller mode)
        if hasattr(sys, "_MEIPASS"):
            threading.Thread(target=self._create_desktop_icon, daemon=True).start()
        
        # Start the fork node on launch
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
        
        ctk.CTkLabel(logo_frame, text="⚔", font=("Segoe UI Emoji", 32),
                     text_color=COLOR_GOLD).pack(side="left", padx=(15, 5))
        
        ctk.CTkLabel(logo_frame, text="EXCALibur", font=("Segoe UI", 16, "bold"),
                     text_color=COLOR_TEXT).pack(side="left")
        
        # Version badge
        ctk.CTkLabel(sidebar, text=f"v{APP_VERSION}", font=("Segoe UI", 9),
                     text_color=COLOR_TEXT_MUTED).pack(pady=(0, 15))
        
        # Divider
        ctk.CTkFrame(sidebar, height=1, fg_color=COLOR_PURPLE_DARK).pack(fill="x", padx=15, pady=(0, 15))
        
        # Status indicators
        self.status_indicator = ctk.CTkLabel(sidebar, text="● Locked", font=("Segoe UI", 10),
                                             text_color=COLOR_WARNING)
        self.status_indicator.pack(pady=(0, 5))
        
        self.node_status_indicator = ctk.CTkLabel(sidebar, text="◌ Node: Starting...",
                                                  font=("Segoe UI", 9),
                                                  text_color=COLOR_TEXT_MUTED)
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
            btn = ctk.CTkButton(sidebar, text=f"{icon}  {name}",
                               command=lambda n=name: self._switch_tab(n),
                               width=190, height=40, fg_color="transparent",
                               hover_color=COLOR_CARD_HOVER, font=("Segoe UI", 12),
                               text_color=COLOR_TEXT_DIM, anchor="w")
            btn.pack(pady=2, padx=10)
            self.nav_buttons.append((btn, name))
        
        # Sidebar footer
        footer = ctk.CTkFrame(sidebar, height=80, fg_color="transparent")
        footer.pack(side="bottom", fill="x", pady=(0, 10))
        footer.pack_propagate(False)
        
        ctk.CTkButton(footer, text="❓  Help & Guide", command=self._show_help,
                      fg_color=COLOR_CARD, hover_color=COLOR_CARD_HOVER,
                      border_width=1, border_color=COLOR_CYAN_DARK,
                      text_color=COLOR_CYAN, font=("Segoe UI", 10),
                      corner_radius=8, height=32).pack(fill="x", padx=15, pady=(5, 3))
        
        ctk.CTkLabel(footer, text="Aetherion Oracle", font=("Segoe UI", 9),
                     text_color=COLOR_TEXT_MUTED).pack(pady=2)
        ctk.CTkLabel(footer, text="BTC + EXCAL Dual Lane", font=("Segoe UI", 9),
                     text_color=COLOR_GOLD).pack(pady=2)
        ctk.CTkLabel(footer, text="AES-256-GCM Encrypted", font=("Segoe UI", 9),
                     text_color=COLOR_SUCCESS).pack(pady=2)
        
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
        
        # Show login window
        self.show_login_window()
    
    def _create_desktop_icon(self):
        """Create desktop icon on first run."""
        time.sleep(2)  # Wait for app to start
        DesktopIconCreator.create_desktop_shortcut()
        DesktopIconCreator.create_start_menu_shortcut()
    
    def show_login_window(self):
        """Show the login window."""
        self.login_window = LoginWindow(self, self.backend)
        self.wait_window(self.login_window)
    
    def show_login(self):
        """Show login after lock."""
        for widget in self.content_frame.winfo_children():
            widget.pack_forget()
        self.show_login_window()
    
    def _start_node(self):
        """Start the fork node RPC server."""
        started = self.node_manager.start()
        if started:
            self.after(0, lambda: self.node_status_indicator.configure(
                text="● Node: Running", text_color=COLOR_SUCCESS))
        else:
            self.after(0, lambda: self.node_status_indicator.configure(
                text="◌ Node: Failed", text_color=COLOR_ERROR))
    
    def on_wallet_opened(self):
        """Called when wallet is successfully opened."""
        self.status_indicator.configure(text="● Unlocked", text_color=COLOR_SUCCESS)
        threading.Thread(target=self._init_p2p, daemon=True).start()
        self._switch_tab("Dashboard")
        
        # Start Prometheus metrics server
        threading.Thread(target=self._start_prometheus, daemon=True).start()
        
        # Update node status periodically
        threading.Thread(target=self._node_status_loop, daemon=True).start()
        
        # Show onboarding for new wallets
        try:
            txs = self.backend.get_excal_transactions()
            if not txs:
                self.after(500, self._show_onboarding)
        except Exception:
            pass
    
    def _node_status_loop(self):
        """Periodically update node status."""
        while True:
            time.sleep(5)
            self.after(0, self._update_node_status)
    
    def _update_node_status(self):
        """Update node status display."""
        status = self.node_manager.get_status()
        if status["running"] and status["healthy"]:
            self.node_status_indicator.configure(text="● Node: Running", text_color=COLOR_SUCCESS)
        elif status["running"]:
            self.node_status_indicator.configure(text="◌ Node: Connecting...", text_color=COLOR_WARNING)
        else:
            self.node_status_indicator.configure(text="◌ Node: Stopped", text_color=COLOR_TEXT_MUTED)
    
    def _start_prometheus(self):
        """Start Prometheus metrics server."""
        try:
            start_http_server(9435)
        except Exception:
            pass
    
    def _init_p2p(self):
        """Initialize P2P networking."""
        try:
            self.backend.initialize_p2p()
        except Exception:
            pass
    
    def _on_lock(self, event=None):
        """Handle wallet lock."""
        self.backend.close()
        self.status_indicator.configure(text="● Locked", text_color=COLOR_WARNING)
        self.show_login()
    
    def _show_help(self):
        """Open help panel."""
        HelpPanel(self)
    
    def _show_onboarding(self):
        """Show onboarding wizard."""
        OnboardingWizard(self)
    
    def _switch_tab(self, tab_name: str):
        """Switch to a tab."""
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
    
    def on_exit(self):
        """Clean shutdown."""
        self.node_manager.stop()
        mining_tab = self.tabs.get("Mining")
        if mining_tab and hasattr(mining_tab, "stop_all"):
            mining_tab.stop_all()
    
    def destroy(self):
        """Override destroy to clean up."""
        self.on_exit()
        super().destroy()


def main():
    """Main entry point."""
    # Create wallet directory
    WALLET_DIR.mkdir(parents=True, exist_ok=True)
    
    # Launch GUI
    app = P2PWalletApp()
    app.mainloop()


if __name__ == "__main__":
    main()
