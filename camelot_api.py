#!/usr/bin/env python3
"""camelot_api.py — Camelot Fair-Rise of Excalibur Game API Gossip Module.

This module provides the bridge between the EXCAL blockchain and the
"Camelot Fair-Rise of Excalibur" game. It enables:

1. Game Transaction Gossip — In-game purchases, item transfers, and
   achievements are gossiped across the P2P network using the "camelot"
   message type, ensuring game state is distributed and verifiable.

2. Payment Verification — The game can verify EXCAL payments for
   in-game purchases through RPC endpoints, enabling real-time
   microtransaction confirmation.

3. Item Registry — In-game items (weapons, armor, artifacts) are registered
   on-chain with unique identifiers, enabling provable ownership and
   cross-session persistence.

4. Achievement Gossip — Player achievements are broadcast to the network
   for leaderboard synchronization and on-chain verification.

5. Webhook System — Game events trigger webhooks to notify external
   services (game servers, analytics, Discord bots).

Protocol — "camelot" P2P message format:
    event_type (1 byte):
        0x01 — purchase: In-game purchase event
        0x02 — item_transfer: Item ownership transfer
        0x03 — achievement: Player achievement unlocked
        0x04 — item_register: New item registered on-chain
        0x05 — player_state: Player state update (position, stats)
        0x06 — quest_event: Quest start/complete event
        0x07 — guild_event: Guild creation/join/leave event
    player_id (32 bytes): SHA-256 hash of player's unique identifier
    timestamp (8 bytes, uint64): Unix timestamp of the event
    amount (8 bytes, uint64): Amount in swords (for purchases/transfers)
    item_id (variable): Item identifier (for item-related events)
    metadata (variable): JSON-encoded additional event data

    Total minimum size: 49 bytes (without item_id and metadata)

Service flag:
    0x40 — NODE_GAME: supports Camelot game gossip protocol

Pure Python, stdlib only. Uses asyncio for non-blocking I/O.
"""
import asyncio
import hashlib
import json
import logging
import struct
import time
import uuid
from collections import defaultdict
from threading import Lock

logger = logging.getLogger("camelot_api")

# --- Constants ---

NODE_GAME = 0x40  # Service flag for game-capable peers

# Event types
EVENT_PURCHASE = 0x01
EVENT_ITEM_TRANSFER = 0x02
EVENT_ACHIEVEMENT = 0x03
EVENT_ITEM_REGISTER = 0x04
EVENT_PLAYER_STATE = 0x05
EVENT_QUEST_EVENT = 0x06
EVENT_GUILD_EVENT = 0x07

EVENT_TYPE_NAMES = {
    EVENT_PURCHASE: "purchase",
    EVENT_ITEM_TRANSFER: "item_transfer",
    EVENT_ACHIEVEMENT: "achievement",
    EVENT_ITEM_REGISTER: "item_register",
    EVENT_PLAYER_STATE: "player_state",
    EVENT_QUEST_EVENT: "quest_event",
    EVENT_GUILD_EVENT: "guild_event",
}

# Rate limits for game gossip (per minute per peer)
GAME_RATE_LIMITS = {
    "camelot": 60,  # Game gossip messages
}

# --- Game Event Encoder/Decoder ---

def encode_camelot_event(event_type, player_id, amount, item_id=None, metadata=None):
    """Encode a Camelot game event into bytes for P2P gossip.
    
    Args:
        event_type: One of EVENT_* constants
        player_id: 32-byte SHA-256 hash of player identifier
        amount: Amount in swords (uint64)
        item_id: Optional item identifier string
        metadata: Optional dict for additional event data
    
    Returns:
        bytes: Encoded event payload
    """
    payload = bytes([event_type])
    
    # Player ID (32 bytes)
    if isinstance(player_id, str):
        player_id = hashlib.sha256(player_id.encode()).digest()
    payload += player_id
    
    # Timestamp (8 bytes)
    payload += struct.pack("<Q", int(time.time()))
    
    # Amount (8 bytes)
    payload += struct.pack("<Q", amount)
    
    # Item ID (variable length)
    if item_id:
        item_bytes = item_id.encode("utf-8")
        payload += struct.pack("<H", len(item_bytes))
        payload += item_bytes
    else:
        payload += struct.pack("<H", 0)
    
    # Metadata (variable length JSON)
    if metadata:
        meta_bytes = json.dumps(metadata).encode("utf-8")
        payload += struct.pack("<I", len(meta_bytes))
        payload += meta_bytes
    else:
        payload += struct.pack("<I", 0)
    
    return payload


def decode_camelot_event(payload):
    """Decode a Camelot game event from bytes.
    
    Args:
        payload: Raw bytes from P2P message
    
    Returns:
        dict: Decoded event with event_type, player_id, timestamp, amount,
              item_id, and metadata fields.
    """
    if len(payload) < 49:
        raise ValueError(f"Camelot event payload too short: {len(payload)} bytes")
    
    offset = 0
    
    # Event type (1 byte)
    event_type = payload[offset]
    offset += 1
    
    # Player ID (32 bytes)
    player_id = payload[offset:offset + 32].hex()
    offset += 32
    
    # Timestamp (8 bytes)
    timestamp = struct.unpack("<Q", payload[offset:offset + 8])[0]
    offset += 8
    
    # Amount (8 bytes)
    amount = struct.unpack("<Q", payload[offset:offset + 8])[0]
    offset += 8
    
    # Item ID (variable)
    item_len = struct.unpack("<H", payload[offset:offset + 2])[0]
    offset += 2
    item_id = None
    if item_len > 0:
        item_id = payload[offset:offset + item_len].decode("utf-8")
        offset += item_len
    
    # Metadata (variable)
    meta_len = struct.unpack("<I", payload[offset:offset + 4])[0]
    offset += 4
    metadata = None
    if meta_len > 0:
        metadata = json.loads(payload[offset:offset + meta_len].decode("utf-8"))
    
    event_type_name = EVENT_TYPE_NAMES.get(event_type, f"unknown_{event_type}")
    
    return {
        "event_type": event_type,
        "event_type_name": event_type_name,
        "player_id": player_id,
        "timestamp": timestamp,
        "amount": amount,
        "item_id": item_id,
        "metadata": metadata,
    }


# --- Game State Store ---

class GameStateStore:
    """Thread-safe in-memory store for game state.
    
    Maintains:
    - Registered items with ownership tracking
    - Player achievement records
    - Payment verification cache
    - Event history for gossip replay
    - Webhook callback registry
    """
    
    def __init__(self):
        self.lock = Lock()
        
        # Item registry: {item_id: {owner, metadata, registered_at}}
        self.items = {}
        
        # Player achievements: {player_id: [{achievement, timestamp}]}
        self.achievements = defaultdict(list)
        
        # Payment verification cache: {payment_hash: {status, amount, confirmed_at}}
        self.payments = {}
        
        # Event history (last N events for gossip replay)
        self.event_history = []
        self.max_history = 10000
        
        # Webhook callbacks: {event_type: [url1, url2, ...]}
        self.webhooks = defaultdict(list)
        
        # Guild registry: {guild_id: {name, members, created_at}}
        self.guilds = {}
        
        # Quest state: {quest_id: {name, status, player_id, completed_at}}
        self.quests = {}
        
        # Statistics
        self.stats = {
            "total_events": 0,
            "total_purchases": 0,
            "total_items_registered": 0,
            "total_achievements": 0,
            "total_payments_verified": 0,
            "start_time": time.time(),
        }
    
    def register_item(self, item_id, owner_id, metadata=None):
        """Register a new in-game item.
        
        Args:
            item_id: Unique item identifier string
            owner_id: Player ID (32-byte hex string)
            metadata: Optional dict with item properties (name, type, rarity, stats)
        
        Returns:
            dict: Registration result with item_id and status
        """
        with self.lock:
            if item_id in self.items:
                return {"status": "error", "message": f"Item {item_id} already registered"}
            
            self.items[item_id] = {
                "item_id": item_id,
                "owner_id": owner_id,
                "metadata": metadata or {},
                "registered_at": int(time.time()),
                "transfer_count": 0,
            }
            self.stats["total_items_registered"] += 1
            
            logger.info(f"Item registered: {item_id} -> {owner_id[:16]}...")
            return {"status": "registered", "item_id": item_id}
    
    def transfer_item(self, item_id, new_owner_id, transaction_hash=None):
        """Transfer item ownership.
        
        Args:
            item_id: Item identifier
            new_owner_id: New owner's player ID
            transaction_hash: Optional on-chain transaction hash for verification
        
        Returns:
            dict: Transfer result
        """
        with self.lock:
            item = self.items.get(item_id)
            if not item:
                return {"status": "error", "message": f"Item {item_id} not found"}
            
            old_owner = item["owner_id"]
            item["owner_id"] = new_owner_id
            item["transfer_count"] += 1
            item["last_transfer_at"] = int(time.time())
            if transaction_hash:
                item["last_transaction"] = transaction_hash
            
            logger.info(f"Item transferred: {item_id} {old_owner[:16]}... -> {new_owner_id[:16]}...")
            return {
                "status": "transferred",
                "item_id": item_id,
                "from": old_owner,
                "to": new_owner_id,
            }
    
    def get_item(self, item_id):
        """Look up an item by ID.
        
        Returns:
            dict or None: Item data or None if not found
        """
        with self.lock:
            return self.items.get(item_id)
    
    def get_items_by_owner(self, owner_id):
        """Get all items owned by a player.
        
        Returns:
            list: List of item dicts owned by the player
        """
        with self.lock:
            return [item for item in self.items.values() if item["owner_id"] == owner_id]
    
    def record_achievement(self, player_id, achievement_name, metadata=None):
        """Record a player achievement.
        
        Args:
            player_id: Player's unique identifier
            achievement_name: Name of the achievement
            metadata: Optional additional data
        
        Returns:
            dict: Achievement record
        """
        with self.lock:
            record = {
                "achievement": achievement_name,
                "timestamp": int(time.time()),
                "metadata": metadata or {},
            }
            self.achievements[player_id].append(record)
            self.stats["total_achievements"] += 1
            
            logger.info(f"Achievement: {player_id[:16]}... -> {achievement_name}")
            return record
    
    def get_achievements(self, player_id):
        """Get all achievements for a player.
        
        Returns:
            list: List of achievement records
        """
        with self.lock:
            return list(self.achievements.get(player_id, []))
    
    def verify_payment(self, payment_hash, amount, confirmed_at=None):
        """Record a verified payment.
        
        Args:
            payment_hash: Unique payment identifier (transaction hash)
            amount: Amount in swords
            confirmed_at: Optional confirmation timestamp
        
        Returns:
            dict: Payment verification result
        """
        with self.lock:
            self.payments[payment_hash] = {
                "payment_hash": payment_hash,
                "amount": amount,
                "status": "confirmed",
                "confirmed_at": confirmed_at or int(time.time()),
            }
            self.stats["total_payments_verified"] += 1
            
            logger.info(f"Payment verified: {payment_hash[:16]}... amount={amount}")
            return {
                "status": "confirmed",
                "payment_hash": payment_hash,
                "amount": amount,
            }
    
    def get_payment_status(self, payment_hash):
        """Check the status of a payment.
        
        Returns:
            dict or None: Payment status or None if not found
        """
        with self.lock:
            payment = self.payments.get(payment_hash)
            if payment:
                return {
                    "status": payment["status"],
                    "amount": payment["amount"],
                    "confirmed_at": payment["confirmed_at"],
                }
            return None
    
    def register_webhook(self, event_type, url):
        """Register a webhook callback for an event type.
        
        Args:
            event_type: Event type constant or name
            url: Webhook URL to call
        
        Returns:
            dict: Registration result
        """
        with self.lock:
            if url not in self.webhooks[event_type]:
                self.webhooks[event_type].append(url)
            logger.info(f"Webhook registered: {event_type} -> {url}")
            return {"status": "registered", "event_type": event_type, "url": url}
    
    def get_webhooks(self, event_type=None):
        """Get registered webhooks.
        
        Args:
            event_type: Optional filter by event type
        
        Returns:
            dict or list: Webhooks by event type or all webhooks
        """
        with self.lock:
            if event_type is not None:
                return list(self.webhooks.get(event_type, []))
            return dict(self.webhooks)
    
    def record_event(self, event):
        """Record a game event in history.
        
        Args:
            event: Decoded event dict from decode_camelot_event()
        """
        with self.lock:
            self.event_history.append(event)
            if len(self.event_history) > self.max_history:
                self.event_history = self.event_history[-self.max_history:]
            
            self.stats["total_events"] += 1
            
            event_type = event.get("event_type")
            if event_type == EVENT_PURCHASE:
                self.stats["total_purchases"] += 1
    
    def get_event_history(self, limit=100, event_type=None):
        """Get recent event history.
        
        Args:
            limit: Maximum number of events to return
            event_type: Optional filter by event type
        
        Returns:
            list: Recent events
        """
        with self.lock:
            events = self.event_history
            if event_type is not None:
                events = [e for e in events if e.get("event_type") == event_type]
            return events[-limit:]
    
    def get_stats(self):
        """Get game statistics.
        
        Returns:
            dict: Current game statistics
        """
        with self.lock:
            stats = dict(self.stats)
            stats["uptime_seconds"] = int(time.time() - self.stats["start_time"])
            stats["registered_items"] = len(self.items)
            stats["registered_players"] = len(self.achievements)
            stats["active_webhooks"] = sum(len(urls) for urls in self.webhooks.values())
            return stats
    
    def register_guild(self, guild_id, name, founder_id, metadata=None):
        """Register a new guild.
        
        Args:
            guild_id: Unique guild identifier
            name: Guild display name
            founder_id: Founder's player ID
            metadata: Optional guild metadata
        
        Returns:
            dict: Guild registration result
        """
        with self.lock:
            if guild_id in self.guilds:
                return {"status": "error", "message": f"Guild {guild_id} already exists"}
            
            self.guilds[guild_id] = {
                "guild_id": guild_id,
                "name": name,
                "founder_id": founder_id,
                "members": [founder_id],
                "metadata": metadata or {},
                "created_at": int(time.time()),
            }
            return {"status": "created", "guild_id": guild_id}
    
    def join_guild(self, guild_id, player_id):
        """Add a player to a guild.
        
        Returns:
            dict: Join result
        """
        with self.lock:
            guild = self.guilds.get(guild_id)
            if not guild:
                return {"status": "error", "message": f"Guild {guild_id} not found"}
            
            if player_id not in guild["members"]:
                guild["members"].append(player_id)
            
            return {"status": "joined", "guild_id": guild_id}
    
    def get_guild(self, guild_id):
        """Look up a guild by ID.
        
        Returns:
            dict or None: Guild data or None
        """
        with self.lock:
            return self.guilds.get(guild_id)
    
    def record_quest(self, quest_id, name, player_id, status, completed_at=None):
        """Record a quest event.
        
        Args:
            quest_id: Unique quest identifier
            name: Quest name
            player_id: Player's ID
            status: "started" or "completed"
            completed_at: Optional completion timestamp
        
        Returns:
            dict: Quest record
        """
        with self.lock:
            self.quests[quest_id] = {
                "quest_id": quest_id,
                "name": name,
                "player_id": player_id,
                "status": status,
                "created_at": int(time.time()),
                "completed_at": completed_at or (int(time.time()) if status == "completed" else None),
            }
            return {"status": status, "quest_id": quest_id}


# --- Webhook Dispatcher ---

async def dispatch_webhook(store, event_type, event_data):
    """Dispatch webhooks for a game event.
    
    Args:
        store: GameStateStore instance
        event_type: Event type constant
        event_data: Event data dict
    """
    urls = store.get_webhooks(event_type)
    if not urls:
        return
    
    import urllib.request
    import urllib.error
    
    payload = json.dumps({
        "event_type": EVENT_TYPE_NAMES.get(event_type, f"unknown_{event_type}"),
        "event_data": event_data,
        "timestamp": int(time.time()),
    }).encode("utf-8")
    
    for url in urls:
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            # Non-blocking webhook — don't block on failure
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _send_webhook, req)
            logger.info(f"Webhook dispatched: {url}")
        except Exception as e:
            logger.warning(f"Webhook failed: {url} — {e}")


def _send_webhook(req):
    """Send a single webhook request (runs in executor)."""
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()
    except Exception:
        pass  # Webhooks are best-effort


# --- Gossip Handler for P2P Layer ---

async def handle_camelot_gossip(node, peer_id, payload):
    """Handle a "camelot" P2P gossip message.
    
    This function is designed to be called from p2p_layer.py's ConnectionHandler.
    It decodes the game event, records it, and broadcasts to other game-capable peers.
    
    Args:
        node: P2PNode instance with .peers dict and .game_store attribute
        peer_id: Sending peer's identifier
        payload: Raw bytes of the camelot message
    """
    try:
        event = decode_camelot_event(payload)
    except ValueError as e:
        logger.warning(f"[{peer_id}] Invalid camelot event: {e}")
        return
    
    event_type_name = event.get("event_type_name", "unknown")
    player_id = event.get("player_id", "unknown")[:16]
    logger.info(
        f"[{peer_id}] Camelot gossip: type={event_type_name} "
        f"player={player_id}... amount={event.get('amount', 0)}"
    )
    
    # Get the game store from the node
    store = getattr(node, "game_store", None)
    if not store:
        logger.warning("No game store attached to node, skipping event processing")
        return
    
    # Process event by type
    event_type = event.get("event_type")
    metadata = event.get("metadata", {})
    
    if event_type == EVENT_PURCHASE:
        # Record payment verification
        payment_hash = metadata.get("payment_hash", hashlib.sha256(
            f"{player_id}-{event.get('timestamp')}-{event.get('amount')}".encode()
        ).hexdigest())
        store.verify_payment(payment_hash, event.get("amount", 0))
    
    elif event_type == EVENT_ITEM_TRANSFER:
        # Transfer item ownership
        item_id = event.get("item_id")
        if item_id:
            new_owner = event.get("player_id", "")
            store.transfer_item(item_id, new_owner)
    
    elif event_type == EVENT_ACHIEVEMENT:
        # Record achievement
        achievement_name = metadata.get("achievement", "unknown")
        store.record_achievement(event.get("player_id", ""), achievement_name, metadata)
    
    elif event_type == EVENT_ITEM_REGISTER:
        # Register new item
        item_id = event.get("item_id")
        if item_id:
            store.register_item(item_id, event.get("player_id", ""), metadata)
    
    elif event_type == EVENT_QUEST_EVENT:
        # Record quest event
        quest_id = metadata.get("quest_id", str(uuid.uuid4()))
        quest_name = metadata.get("quest_name", "unknown")
        quest_status = metadata.get("status", "started")
        store.record_quest(quest_id, quest_name, event.get("player_id", ""), quest_status)
    
    elif event_type == EVENT_GUILD_EVENT:
        # Handle guild events
        action = metadata.get("action", "")
        guild_id = metadata.get("guild_id", "")
        
        if action == "create":
            store.register_guild(
                guild_id,
                metadata.get("name", "Unknown Guild"),
                event.get("player_id", ""),
                metadata,
            )
        elif action == "join":
            store.join_guild(guild_id, event.get("player_id", ""))
    
    # Record event in history
    store.record_event(event)
    
    # Dispatch webhooks
    asyncio.create_task(dispatch_webhook(store, event_type, event))
    
    # Broadcast to other game-capable peers
    asyncio.create_task(broadcast_camelot_to_peers(node, peer_id, payload))


async def broadcast_camelot_to_peers(node, origin_peer_id, payload):
    """Broadcast a camelot event to other game-capable peers.
    
    Args:
        node: P2PNode instance
        origin_peer_id: Origin peer to exclude
        payload: Raw camelot message bytes
    """
    for pid, peer in node.peers.items():
        if pid != origin_peer_id and (peer.score.services & NODE_GAME):
            try:
                from p2p_layer import encode_message
                msg = encode_message("camelot", payload)
                peer.writer.write(msg)
                await peer.writer.drain()
            except (ConnectionResetError, OSError) as e:
                logger.warning(f"[{pid}] Camelot broadcast failed: {e}")


# --- RPC Helper Functions ---

def rpc_game_get_balance(store, player_id):
    """Get a player's game balance (items owned, achievements).
    
    Args:
        store: GameStateStore instance
        player_id: Player's unique identifier
    
    Returns:
        dict: Player's game balance information
    """
    if isinstance(player_id, str) and len(player_id) == 64:
        # Already a hex hash
        pass
    else:
        player_id = hashlib.sha256(str(player_id).encode()).hexdigest()
    
    items = store.get_items_by_owner(player_id)
    achievements = store.get_achievements(player_id)
    
    return {
        "player_id": player_id,
        "items_owned": len(items),
        "items": items,
        "achievements_count": len(achievements),
        "achievements": achievements,
    }


def rpc_game_verify_payment(store, payment_hash):
    """Verify a game payment.
    
    Args:
        store: GameStateStore instance
        payment_hash: Payment transaction hash
    
    Returns:
        dict or None: Payment status or None if not found
    """
    return store.get_payment_status(payment_hash)


def rpc_game_register_item(store, item_id, owner_id, metadata=None):
    """Register a new in-game item.
    
    Args:
        store: GameStateStore instance
        item_id: Unique item identifier
        owner_id: Owner's player ID
        metadata: Optional item metadata
    
    Returns:
        dict: Registration result
    """
    if isinstance(owner_id, str) and len(owner_id) == 64:
        pass
    else:
        owner_id = hashlib.sha256(str(owner_id).encode()).hexdigest()
    
    return store.register_item(item_id, owner_id, metadata)


def rpc_game_gossip_event(store, event_type, player_id, amount, item_id=None, metadata=None):
    """Create and gossip a game event.
    
    Args:
        store: GameStateStore instance
        event_type: Event type constant
        player_id: Player identifier
        amount: Amount in swords
        item_id: Optional item identifier
        metadata: Optional metadata dict
    
    Returns:
        dict: Gossip result
    """
    payload = encode_camelot_event(event_type, player_id, amount, item_id, metadata)
    event = decode_camelot_event(payload)
    store.record_event(event)
    
    return {
        "status": "gossiped",
        "event": event,
    }


# --- Standalone Game API Server ---

class GameAPIHandler:
    """HTTP handler for game API endpoints.
    
    Provides REST-like JSON endpoints for game integration:
    - POST /api/game/register_item — Register an in-game item
    - POST /api/game/transfer_item — Transfer item ownership
    - GET  /api/game/item/<item_id> — Look up an item
    - GET  /api/game/items/<player_id> — Get player's items
    - POST /api/game/achievement — Record an achievement
    - GET  /api/game/achievements/<player_id> — Get player achievements
    - POST /api/game/verify_payment — Verify a payment
    - GET  /api/game/payment/<hash> — Check payment status
    - POST /api/game/gossip — Gossip a game event
    - GET  /api/game/stats — Get game statistics
    - GET  /api/game/events — Get recent event history
    - POST /api/game/webhook — Register a webhook
    - POST /api/game/guild — Register/join a guild
    - POST /api/game/quest — Record a quest event
    """
    
    def __init__(self, store):
        self.store = store
    
    def handle_request(self, method, path, body=None):
        """Handle an API request.
        
        Args:
            method: HTTP method (GET, POST)
            path: Request path
            body: Optional JSON body dict
        
        Returns:
            tuple: (status_code, response_dict)
        """
        try:
            # Item endpoints
            if path.startswith("/api/game/item/"):
                item_id = path[len("/api/game/item/"):]
                if method == "GET":
                    item = self.store.get_item(item_id)
                    if item:
                        return (200, item)
                    return (404, {"error": f"Item {item_id} not found"})
            
            if path.startswith("/api/game/items/"):
                player_id = path[len("/api/game/items/"):]
                if method == "GET":
                    items = self.store.get_items_by_owner(player_id)
                    return (200, {"items": items, "count": len(items)})
            
            # Achievement endpoints
            if path.startswith("/api/game/achievements/"):
                player_id = path[len("/api/game/achievements/"):]
                if method == "GET":
                    achievements = self.store.get_achievements(player_id)
                    return (200, {"achievements": achievements, "count": len(achievements)})
            
            # Payment endpoints
            if path.startswith("/api/game/payment/"):
                payment_hash = path[len("/api/game/payment/"):]
                if method == "GET":
                    status = self.store.get_payment_status(payment_hash)
                    if status:
                        return (200, status)
                    return (404, {"error": "Payment not found"})
            
            # POST endpoints
            if method == "POST" and body:
                if path == "/api/game/register_item":
                    return (200, rpc_game_register_item(
                        self.store,
                        body.get("item_id", ""),
                        body.get("owner_id", ""),
                        body.get("metadata"),
                    ))
                
                elif path == "/api/game/transfer_item":
                    return (200, self.store.transfer_item(
                        body.get("item_id", ""),
                        body.get("new_owner_id", ""),
                        body.get("transaction_hash"),
                    ))
                
                elif path == "/api/game/achievement":
                    return (200, self.store.record_achievement(
                        body.get("player_id", ""),
                        body.get("achievement", ""),
                        body.get("metadata"),
                    ))
                
                elif path == "/api/game/verify_payment":
                    return (200, self.store.verify_payment(
                        body.get("payment_hash", ""),
                        body.get("amount", 0),
                    ))
                
                elif path == "/api/game/gossip":
                    return (200, rpc_game_gossip_event(
                        self.store,
                        body.get("event_type", 0),
                        body.get("player_id", ""),
                        body.get("amount", 0),
                        body.get("item_id"),
                        body.get("metadata"),
                    ))
                
                elif path == "/api/game/webhook":
                    return (200, self.store.register_webhook(
                        body.get("event_type", ""),
                        body.get("url", ""),
                    ))
                
                elif path == "/api/game/guild":
                    action = body.get("action", "")
                    if action == "create":
                        return (200, self.store.register_guild(
                            body.get("guild_id", ""),
                            body.get("name", ""),
                            body.get("founder_id", ""),
                            body.get("metadata"),
                        ))
                    elif action == "join":
                        return (200, self.store.join_guild(
                            body.get("guild_id", ""),
                            body.get("player_id", ""),
                        ))
                    else:
                        return (400, {"error": "Unknown guild action"})
                
                elif path == "/api/game/quest":
                    return (200, self.store.record_quest(
                        body.get("quest_id", ""),
                        body.get("name", ""),
                        body.get("player_id", ""),
                        body.get("status", "started"),
                    ))
            
            # Stats and events
            if path == "/api/game/stats" and method == "GET":
                return (200, self.store.get_stats())
            
            if path == "/api/game/events" and method == "GET":
                limit = 100
                return (200, {"events": self.store.get_event_history(limit)})
            
            # Default
            return (404, {"error": f"Unknown endpoint: {method} {path}"})
        
        except Exception as e:
            logger.error(f"Game API error: {e}")
            return (500, {"error": str(e)})


# --- Main entry point for standalone game API server ---

def main():
    """Run a standalone game API server for testing."""
    import http.server
    
    store = GameStateStore()
    handler = GameAPIHandler(store)
    
    class CamelotHTTPHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            logger.info(format % args)
        
        def do_GET(self):
            status, result = handler.handle_request("GET", self.path)
            body = json.dumps(result).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        
        def do_POST(self):
            content_length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(content_length)
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                body = {}
            
            status, result = handler.handle_request("POST", self.path, body)
            resp_body = json.dumps(result).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp_body)))
            self.end_headers()
            self.wfile.write(resp_body)
    
    port = 9436
    server = http.server.ThreadingHTTPServer(("0.0.0.0", port), CamelotHTTPHandler)
    print(f"🎮 Camelot Game API listening on 0.0.0.0:{port}")
    print("   Endpoints:")
    print("   • POST /api/game/register_item")
    print("   • POST /api/game/transfer_item")
    print("   • GET  /api/game/item/<item_id>")
    print("   • GET  /api/game/items/<player_id>")
    print("   • POST /api/game/achievement")
    print("   • GET  /api/game/achievements/<player_id>")
    print("   • POST /api/game/verify_payment")
    print("   • GET  /api/game/payment/<hash>")
    print("   • POST /api/game/gossip")
    print("   • GET  /api/game/stats")
    print("   • GET  /api/game/events")
    print("   • POST /api/game/webhook")
    print("   • POST /api/game/guild")
    print("   • POST /api/game/quest")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Camelot Game API...")
        server.shutdown()


if __name__ == "__main__":
    main()
