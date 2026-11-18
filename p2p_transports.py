"""Optional local mDNS discovery for SkyNet P2P nodes."""

import ipaddress
import logging

logger = logging.getLogger("p2p")

SERVICE_TYPE = "_excal-p2p._tcp.local."
SERVICE_PROTOCOL = "excal-p2p-v1"


def _local_addresses():
    import ifaddr

    addresses = set()
    for adapter in ifaddr.get_adapters():
        for item in adapter.ips:
            value = item.ip[0] if isinstance(item.ip, tuple) else item.ip
            try:
                address = ipaddress.ip_address(value)
            except ValueError:
                continue
            if (
                address.is_unspecified
                or address.is_loopback
                or address.is_multicast
                or address.is_link_local
            ):
                continue
            addresses.add(address.packed)
    return sorted(addresses)


class LocalPeerDiscovery:
    """Advertise a node and report matching peers discovered on the LAN."""

    def __init__(self, node_id, port, on_peer):
        self.node_id = node_id.hex()
        self.port = int(port)
        self.on_peer = on_peer
        self._zeroconf = None
        self._browser = None
        self._info = None

    def start(self):
        try:
            from zeroconf import ServiceBrowser, ServiceInfo, ServiceStateChange, Zeroconf
        except ImportError as exc:
            raise RuntimeError(
                "mDNS discovery requires the 'zeroconf' package."
            ) from exc

        self._zeroconf = Zeroconf()
        self._added_state = ServiceStateChange.Added
        self._updated_state = ServiceStateChange.Updated
        addresses = _local_addresses()
        if not addresses:
            self._zeroconf.close()
            self._zeroconf = None
            raise RuntimeError("mDNS discovery found no usable local interface addresses.")
        self._info = ServiceInfo(
            SERVICE_TYPE,
            f"{self.node_id[:16]}.{SERVICE_TYPE}",
            addresses=addresses,
            port=self.port,
            properties={
                b"node_id": self.node_id.encode("ascii"),
                b"protocol": SERVICE_PROTOCOL.encode("ascii"),
            },
        )
        self._zeroconf.register_service(self._info)
        self._browser = ServiceBrowser(self._zeroconf, SERVICE_TYPE, handlers=[self._on_change])

    def _on_change(self, zeroconf, service_type, name, state_change):
        if state_change not in (self._added_state, self._updated_state):
            return
        try:
            info = zeroconf.get_service_info(service_type, name, timeout=1500)
            if not info or info.properties.get(b"protocol") != SERVICE_PROTOCOL.encode("ascii"):
                return
            remote_id = info.properties.get(b"node_id", b"").decode("ascii")
            if not remote_id or remote_id == self.node_id:
                return
            for value in info.parsed_addresses():
                address = ipaddress.ip_address(value)
                if address.is_unspecified or address.is_multicast or address.is_loopback:
                    continue
                self.on_peer(str(address), info.port, remote_id)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            logger.debug("Ignoring invalid mDNS peer announcement %s: %s", name, exc)

    def close(self):
        if self._zeroconf is None:
            return
        try:
            if self._info is not None:
                self._zeroconf.unregister_service(self._info)
        finally:
            self._zeroconf.close()
            self._zeroconf = None
            self._browser = None
            self._info = None
