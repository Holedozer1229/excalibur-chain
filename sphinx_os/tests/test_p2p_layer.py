import asyncio
import socket
import time
import unittest

from p2p_layer import (
    EREPR_EXTENSION,
    EREPR_MAX_HOPS,
    EREPR_MESSAGE_TTL,
    MAX_MESSAGE_SIZE,
    NODE_EREPR,
    NODE_EREPR_V2,
    PeerHandler,
    P2PNode,
    decode_message,
    encode_message,
)


class EmptyChain:
    def getblockcount(self):
        return 0

    def getbestblockhash(self):
        return None

    def getblock(self, block_hash):
        return None


class BlockCaptureChain(EmptyChain):
    def __init__(self):
        self.submitted = None

    def submitblock(self, block):
        self.submitted = block
        return {"hash": "ab" * 32, "height": 1}, None


def unused_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class TestP2PWire(unittest.TestCase):
    def test_message_round_trip_and_size_limit(self):
        message = encode_message("ping", b"12345678")
        command, payload = decode_message(message)
        self.assertEqual((command, payload), ("ping", b"12345678"))

        oversized = (
            b"\x03\x46\x53\x47"
            + b"block".ljust(12, b"\x00")
            + (MAX_MESSAGE_SIZE + 1).to_bytes(4, "little")
        )
        with self.assertRaisesRegex(ValueError, "message too large"):
            decode_message(oversized)

    def test_full_block_body_is_parsed_and_sent_to_consensus_store(self):
        store = BlockCaptureChain()
        node = P2PNode(store, listen_host="127.0.0.1", listen_port=unused_port())
        header = bytes(range(80))
        tx = b"raw transaction"
        payload = header + len(tx).to_bytes(4, "little") + tx

        node._on_new_block("peer", payload)

        self.assertEqual(store.submitted["version"], int.from_bytes(header[:4], "little"))
        self.assertEqual(store.submitted["prev"], header[4:36].hex())
        self.assertEqual(store.submitted["txs"], [tx])

    def test_erepr_accepts_legacy_and_v2_and_rejects_expired_v2(self):
        node = P2PNode(EmptyChain(), listen_host="127.0.0.1", listen_port=unused_port())
        peer = PeerHandler("peer", None, None, node)
        peer.score.services = NODE_EREPR | NODE_EREPR_V2

        v2_payload = node._new_erepr_payload()
        self.assertEqual(len(v2_payload), 52 + EREPR_EXTENSION.size)
        asyncio.run(peer._on_erepr(v2_payload))
        self.assertEqual(node.get_erepr_stats()["gossip_waves_received"], 1)

        legacy_payload = node._new_erepr_payload(extended=False)
        self.assertEqual(len(legacy_payload), 52)
        asyncio.run(peer._on_erepr(legacy_payload))
        self.assertEqual(node.get_erepr_stats()["gossip_waves_received"], 2)

        expired_payload = bytearray(node._new_erepr_payload())
        extension_offset = 52
        fields = list(EREPR_EXTENSION.unpack_from(expired_payload, extension_offset))
        fields[4] = int(time.time()) - EREPR_MESSAGE_TTL - 1
        EREPR_EXTENSION.pack_into(expired_payload, extension_offset, *fields)
        asyncio.run(peer._on_erepr(bytes(expired_payload)))
        self.assertEqual(node.get_erepr_stats()["gossip_waves_received"], 2)

    def test_erepr_relay_increments_hop_and_stops_at_limit(self):
        node = P2PNode(EmptyChain(), listen_host="127.0.0.1", listen_port=unused_port())
        source = PeerHandler("source", None, None, node)
        target = PeerHandler("target", None, None, node)
        source.score.services = NODE_EREPR | NODE_EREPR_V2
        target.score.services = NODE_EREPR | NODE_EREPR_V2
        node.peers = {"source": source, "target": target}
        sent = []
        node._send_erepr_to = lambda peer_id, payload: sent.append((peer_id, payload))

        payload = node._new_erepr_payload()
        resonance_id = payload[:32].hex()
        extension = EREPR_EXTENSION.unpack_from(payload, 52)
        node._on_erepr_resonance(
            "source", resonance_id, 1.0, 0.8,
            origin_node_id=extension[2], sequence=extension[3],
            issued_at=extension[4], hops=0,
        )
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][0], "target")
        relayed = EREPR_EXTENSION.unpack_from(sent[0][1], 52)
        self.assertEqual(relayed[2:5], extension[2:5])
        self.assertEqual(relayed[5], 1)

        second_payload = node._new_erepr_payload()
        second_extension = EREPR_EXTENSION.unpack_from(second_payload, 52)
        node._on_erepr_resonance(
            "source", second_payload[:32].hex(), 1.0, 0.8,
            origin_node_id=second_extension[2], sequence=second_extension[3],
            issued_at=second_extension[4], hops=EREPR_MAX_HOPS,
        )
        self.assertEqual(len(sent), 1)


class TestP2PHandshake(unittest.TestCase):
    def test_seed_and_inbound_peer_complete_handshake(self):
        first = P2PNode(
            EmptyChain(), listen_host="127.0.0.1", listen_port=unused_port()
        )
        second = P2PNode(
            EmptyChain(),
            seed_peers=[("127.0.0.1", first.listen_port)],
            listen_host="127.0.0.1",
            listen_port=unused_port(),
        )
        try:
            first.start()
            second.seed_peers = [("127.0.0.1", first.listen_port)]
            second.start()
            deadline = time.time() + 5
            while time.time() < deadline:
                if (
                    first.get_peer_count()
                    and second.get_peer_count()
                    and all(peer.score.user_agent for peer in first.peers.values())
                    and all(peer.score.user_agent for peer in second.peers.values())
                    and first.get_erepr_stats()["gossip_waves_received"]
                    and second.get_erepr_stats()["gossip_waves_received"]
                ):
                    break
                time.sleep(0.05)
            self.assertEqual(first.get_peer_count(), 1)
            self.assertEqual(second.get_peer_count(), 1)
            self.assertTrue(next(iter(first.peers.values())).score.user_agent)
            self.assertTrue(next(iter(second.peers.values())).score.user_agent)
            self.assertTrue(first.get_erepr_stats()["gossip_waves_received"])
            self.assertTrue(second.get_erepr_stats()["gossip_waves_received"])
            self.assertTrue(
                next(iter(first.peers.values())).score.services & NODE_EREPR_V2
            )
        finally:
            second.stop()
            first.stop()


if __name__ == "__main__":
    unittest.main()
