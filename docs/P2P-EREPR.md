# P2P EREPR operation

`fork_node.py` starts the P2P listener on port 9433 along with its RPC server.
Do not start another `p2p_layer.py` process on that same port. The standalone
P2P command is for a separate listener and should use its own `--p2p-port`.

## Configure connectivity

The default seed list is empty. A node with no seeds can accept inbound peers,
but it cannot initiate discovery until a peer connects. Add seed addresses to
`config.json`:

```json
{
  "p2p": {
    "listen_host": "0.0.0.0",
    "listen_port": 9433,
    "advertise_host": "REPLACE_WITH_REACHABLE_IP",
    "allow_private_peers": false,
    "seed_peers": ["seed.example.org:9433"]
  }
}
```

Replace the advertise-host placeholder with the node's reachable IP address.

To bootstrap a new network, run the first node on a host with a reachable
public IP, set that IP as `advertise_host`, and allow inbound TCP on port 9433.
Then add that node's `public-ip:9433` to `seed_peers` on each other node. A
seed is a running node address, so do not use a placeholder or an address until
the host is configured and reachable.

Or set `FORK_P2P_SEEDS=host:port,host:port`. The environment setting overrides
`config.json`. Use brackets for IPv6 endpoints, such as `[2001:db8::10]:9433`.
Set `FORK_P2P_ADVERTISE_HOST` when a node's reachable address differs from its
local socket address. Open/forward TCP port 9433 for inbound connections.

Peer-advertised private and loopback addresses are kept out of automatic
dialing by default. For a trusted LAN, set `allow_private_peers` to `true` or
`FORK_P2P_ALLOW_PRIVATE=1`. Explicit seed addresses may be private.

## EREPR message flow

After the version/verack handshake, EREPR-capable peers send an initial
announcement. The bounded payload carries a message ID, phase, amplitude, and
up to 64 IP/port entries. Receivers validate the payload, remember new
addresses, suppress repeated message IDs for 15 minutes, and relay unseen
announcements with 0.85 amplitude decay. The `NODE_EREPR_V2` service flag
negotiates an optional envelope containing the origin node ID, sequence,
creation time, and hop count. V2 messages are checked for a matching message
ID, a five-minute lifetime, and a 12-hop maximum. Nodes send the original
payload format to peers that do not advertise the v2 flag, preserving
compatibility with older EREPR implementations. Known seeds and eligible
advertised peers are retried during periodic maintenance; failed seeds do not
prevent later seed entries from being tried.

The resonance fields are routing metadata. This socket implementation does
not perform the HMAC echo confirmation or shared-secret bonding described by
the separate `sphinx_os.nexus.erepr_protocol` module. It does not authenticate
or encrypt EREPR messages.

## Inspect the node

The RPC methods `getpeerinfo`, `getnetworkhealth`, and `getereprstats` expose
connected peers, discovered addresses, and sent/received gossip counts.

If the node stays at zero peers, verify that it has at least one configured
seed or that TCP 9433 is reachable from another node. `getereprstats` reports
the configured seed count and current EREPR peer count.
