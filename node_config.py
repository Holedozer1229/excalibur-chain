"""Safe network-facing defaults for EXCAL node services."""


def resolve_p2p_host(network: str, override: str | None = None) -> str:
    """Return the P2P bind host; only the public fork network binds publicly.

    RPC is configured separately and remains loopback-only by default.
    """
    if override is not None:
        host = override.strip()
        if not host:
            raise ValueError("P2P host override cannot be empty")
        return host
    return "0.0.0.0" if network == "fork" else "127.0.0.1"
