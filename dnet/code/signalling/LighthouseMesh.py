try:
    from micropython import const
except Exception:
    def const(value):
        return value

import ubinascii
import network
import aioespnow
try:
    import logging
except Exception:
    logging = None

try:
    import uasyncio as asyncio
except Exception:
    import asyncio


class LighthouseMesh:
    """ESP-NOW mesh adapter with interrupt-driven RX queueing."""
    BROADCAST_TARGET = const(b"\xff\xff\xff\xff\xff\xff")

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # Optional: Add an initialized flag to prevent re-initialization of __init__
            cls._initialized = False 
        return cls._instance

    def __init__(self, peers=None, debug=False):
        self._logger = None
        self._debug = bool(debug)
        self._init_logger()

        # Bring up STA mode so ESP-NOW can operate.
        self.wlan_sta = network.WLAN(network.STA_IF)
        self.wlan_sta.active(True)
        self.wlan_sta.disconnect()

        # Canonical node id is the local MAC as lowercase hex.
        self.wlan_mac = self.wlan_sta.config("mac")
        self.node_id = self.mac_to_node_id(self.wlan_mac)
        self._log_debug("mesh init node_id={}".format(self.node_id))

        # ESP-NOW transport endpoint.
        self.espnow = aioespnow.AIOESPNow()
        self.espnow.active(True)

        # Peer cache and IRQ->async receive buffering.
        self._known_peers = set()
        self._rx_queue = []
        self._max_rx_queue = 32
        self._rx_event = None
        self.use_broadcast = True
        self.default_peer = self.BROADCAST_TARGET

   #     self.add_peer(self.BROADCAST_TARGET)

        # Async event is signaled by ISR drain when new packets arrive.
        self._init_rx_event()
        self.enable_interrupt_rx()

    @staticmethod
    def mac_to_node_id(mac_bytes):
        """Convert raw MAC bytes to 12-char hex node id."""
        return ubinascii.hexlify(mac_bytes).decode()

    @staticmethod
    def node_id_to_mac(node_id):
        """Convert node id text (plain/colon/dash) into raw MAC bytes."""
        if isinstance(node_id, bytes):
            return node_id
        cleaned = node_id.replace(":", "").replace("-", "").lower()
        return ubinascii.unhexlify(cleaned)

    def add_peer(self, peer):
        """Register a peer once with ESP-NOW."""
        mac = self.resolve_peer(peer)
        if mac in self._known_peers:
            return
        try:
            self.espnow.add_peer(mac)
        except Exception as exc:
            self._log_error("add_peer failed peer={} err={}".format(peer, exc))
            raise
        self._known_peers.add(mac)
        self._log_debug("peer added {}".format(self.mac_to_node_id(mac)))

    def resolve_peer(self, peer):
        """Resolve alias/node-id/bytes peer forms to raw MAC bytes."""
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
        """Send bytes (or utf-8 string) to the resolved peer."""
        target = self.resolve_peer(peer)
        self.add_peer(target)
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        try:
            self.espnow.send(target, payload)
        except Exception as exc:
            self._log_error(
                "send failed target={} bytes={} err={}".format(
                    self.mac_to_node_id(target), len(payload), exc
                )
            )
            raise
        self._log_debug(
            "send ok target={} bytes={}".format(self.mac_to_node_id(target), len(payload))
        )

    def recv_raw(self, timeout_ms=0):
        """Read one queued packet; fallback to direct irecv if queue is empty."""
        if self._rx_queue:
            return self._rx_queue.pop(0)

        # Fallback in case IRQ has not been set up by platform.
        mac, msg = self.espnow.irecv(timeout_ms=timeout_ms)
        if mac is None or msg is None:
            return None, None
        self._log_debug("recv fallback peer={} bytes={}".format(self.mac_to_node_id(mac), len(msg)))
        return mac, msg

    def create_transport(self, default_peer=None):
        """Build transport adapter used by dnet.messaging.MessagingEndpoint."""
        from dnet.signalling.LighthouseTransport import LighthouseMeshTransport

        return LighthouseMeshTransport(self, default_peer=default_peer)

    async def run(self, endpoint=None, on_message=None, poll_ms=20):
        # Wait for RX signal, then drain all currently queued packets.
        self._log_debug("run loop started endpoint={}".format(endpoint is not None))
        while True:
            await self._wait_for_rx(poll_ms)
            if endpoint is None:
                while True:
                    peer, payload = self.recv_raw(timeout_ms=0)
                    if payload is None:
                        break
                    if on_message:
                        try:
                            on_message(self.mac_to_node_id(peer), payload)
                        except Exception as exc:
                            self._log_error("on_message(raw) failed err={}".format(exc))
            else:
                while True:
                    try:
                        peer_id, message = endpoint.poll()
                    except Exception as exc:
                        self._log_error("endpoint.poll failed err={}".format(exc))
                        break
                    if message is None:
                        break
                    if on_message:
                        try:
                            on_message(peer_id, message)
                        except Exception as exc:
                            self._log_error("on_message(decoded) failed err={}".format(exc))

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
        """Enable ESP-NOW interrupt callback for incoming packets."""
        self.espnow.irq(self._on_espnow_irq)
        self._log_debug("interrupt rx enabled")

    def disable_interrupt_rx(self):
        """Disable ESP-NOW interrupt callback."""
        self.espnow.irq(None)
        self._log_debug("interrupt rx disabled")

    def _on_espnow_irq(self, *_):
        # ISR entry: move pending frames from driver FIFO into local queue.
        self._drain_incoming()

    def _drain_incoming(self):
        """Drain all immediately available packets from ESP-NOW."""
        drained = 0
        while True:
            mac, msg = self.espnow.irecv(timeout_ms=0)
            if mac is None or msg is None:
                break
            if len(self._rx_queue) >= self._max_rx_queue:
                # Drop oldest packet to make room for newest packet.
                self._rx_queue.pop(0)
                self._log_error("rx queue overflow, dropping oldest packet")
            self._rx_queue.append((mac, msg))
            drained += 1
        if drained:
            self._log_debug("irq drained {} packet(s), queue={}".format(drained, len(self._rx_queue)))
        self._signal_rx_event()

    def _init_rx_event(self):
        """Create async event primitive when available on current runtime."""
        try:
            self._rx_event = asyncio.Event()
        except Exception:
            self._rx_event = None

    def _signal_rx_event(self):
        """Wake run loop when IRQ has queued data."""
        if self._rx_event is None:
            return
        try:
            self._rx_event.set()
        except Exception:
            pass

    async def _wait_for_rx(self, poll_ms):
        """Wait for queued data/event, otherwise sleep for poll interval."""
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

    def _init_logger(self):
        if logging is None:
            return
        try:
            self._logger = logging.getLogger("dnet.LighthouseMesh")
            if hasattr(self._logger, "setLevel"):
                self._logger.setLevel(logging.DEBUG if self._debug else logging.INFO)
        except Exception:
            self._logger = None

    def _log_debug(self, msg):
        if self._logger is not None and hasattr(self._logger, "debug"):
            self._logger.debug(msg)
            return
        if self._debug:
            print("DEBUG LighthouseMesh: {}".format(msg))

    def _log_error(self, msg):
        if self._logger is not None and hasattr(self._logger, "error"):
            self._logger.error(msg)
            return
        print("ERROR LighthouseMesh: {}".format(msg))
