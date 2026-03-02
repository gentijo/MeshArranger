try:
    from micropython import const
except Exception:
    def const(value):
        return value

import ubinascii
import network
import aioespnow

try:
    import uasyncio as asyncio
except Exception:
    import asyncio


class LighthouseMesh:
    BROADCAST_TARGET = const(b"\xff\xff\xff\xff\xff\xff")

    def __init__(self, peers=None, use_broadcast=True):
        self.wlan_sta = network.WLAN(network.STA_IF)
        self.wlan_sta.active(True)
        self.wlan_sta.disconnect()

        self.wlan_mac = self.wlan_sta.config("mac")
        self.node_id = self.mac_to_node_id(self.wlan_mac)

        self.espnow = aioespnow.AIOESPNow()
        self.espnow.active(True)

        self._known_peers = set()
        self._rx_queue = []
        self._max_rx_queue = 32
        self._rx_event = None
        self.use_broadcast = bool(use_broadcast)
        self.default_peer = self.BROADCAST_TARGET if self.use_broadcast else None

        self.add_peer(self.BROADCAST_TARGET)
        for peer in peers or []:
            self.add_peer(peer)
            if not self.use_broadcast and self.default_peer is None:
                self.default_peer = self.resolve_peer(peer)

        self._init_rx_event()
        self.enable_interrupt_rx()

    @staticmethod
    def mac_to_node_id(mac_bytes):
        return ubinascii.hexlify(mac_bytes).decode()

    @staticmethod
    def node_id_to_mac(node_id):
        if isinstance(node_id, bytes):
            return node_id
        cleaned = node_id.replace(":", "").replace("-", "").lower()
        return ubinascii.unhexlify(cleaned)

    def add_peer(self, peer):
        mac = self.resolve_peer(peer)
        if mac in self._known_peers:
            return
        self.espnow.add_peer(mac)
        self._known_peers.add(mac)

    def resolve_peer(self, peer):
        if peer is None:
            if self.default_peer is None:
                raise ValueError("peer is required when no default peer is configured")
            return self.default_peer
        if peer in ("*", "broadcast"):
            return self.BROADCAST_TARGET
        if isinstance(peer, str):
            return self.node_id_to_mac(peer)
        return peer

    def send_raw(self, peer, payload):
        target = self.resolve_peer(peer)
        self.add_peer(target)
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        self.espnow.send(target, payload)

    def recv_raw(self, timeout_ms=0):
        if self._rx_queue:
            return self._rx_queue.pop(0)

        # Fallback in case IRQ has not been set up by platform.
        mac, msg = self.espnow.irecv(timeout_ms=timeout_ms)
        if mac is None or msg is None:
            return None, None
        return mac, msg

    def create_transport(self, default_peer=None):
        from dnet.signalling.LighthouseTransport import LighthouseMeshTransport

        return LighthouseMeshTransport(self, default_peer=default_peer)

    async def run(self, endpoint=None, on_message=None, poll_ms=20):
        while True:
            await self._wait_for_rx(poll_ms)
            if endpoint is None:
                while True:
                    peer, payload = self.recv_raw(timeout_ms=0)
                    if payload is None:
                        break
                    if on_message:
                        on_message(self.mac_to_node_id(peer), payload)
            else:
                while True:
                    peer_id, message = endpoint.poll()
                    if message is None:
                        break
                    if on_message:
                        on_message(peer_id, message)

    def get_stats(self):
        return self.espnow.stats()

    def print_stats(self):
        stats = self.get_stats()
        print("\nESP-NOW Statistics:")
        print("  Packets Sent: {}".format(stats[0]))
        print("  Packets Delivered: {}".format(stats[1]))
        print("  Packets Dropped (TX): {}".format(stats[2]))
        print("  Packets Received: {}".format(stats[3]))
        print("  Packets Dropped (RX): {}".format(stats[4]))

    def enable_interrupt_rx(self):
        self.espnow.irq(self._on_espnow_irq)

    def disable_interrupt_rx(self):
        self.espnow.irq(None)

    def _on_espnow_irq(self, *_):
        self._drain_incoming()

    def _drain_incoming(self):
        while True:
            mac, msg = self.espnow.irecv(timeout_ms=0)
            if mac is None or msg is None:
                break
            if len(self._rx_queue) >= self._max_rx_queue:
                self._rx_queue.pop(0)
            self._rx_queue.append((mac, msg))
        self._signal_rx_event()

    def _init_rx_event(self):
        try:
            self._rx_event = asyncio.Event()
        except Exception:
            self._rx_event = None

    def _signal_rx_event(self):
        if self._rx_event is None:
            return
        try:
            self._rx_event.set()
        except Exception:
            pass

    async def _wait_for_rx(self, poll_ms):
        if self._rx_queue:
            return
        if self._rx_event is not None:
            try:
                await self._rx_event.wait()
                self._rx_event.clear()
                return
            except Exception:
                pass
        try:
            await asyncio.sleep_ms(poll_ms)
        except AttributeError:
            await asyncio.sleep(poll_ms / 1000.0)
