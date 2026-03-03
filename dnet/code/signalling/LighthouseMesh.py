try:
    from micropython import const
except Exception:
    def const(value):
        return value

import ubinascii
import network
import aioespnow
try:
    import utime as time
except Exception:
    import time
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
    ESPNOW_MAX_PAYLOAD_BYTES = const(250)

    # Fragment header: magic(2) + version(1) + msg_id(2) + total(1) + index(1)
    _FRAG_MAGIC = b"\x7fM"
    _FRAG_VERSION = const(1)
    _FRAG_HEADER_BYTES = const(7)
    _FRAG_PAYLOAD_MAX_BYTES = const(ESPNOW_MAX_PAYLOAD_BYTES - _FRAG_HEADER_BYTES)
    _FRAG_REASSEMBLY_TIMEOUT_MS = const(30000)

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # Optional: Add an initialized flag to prevent re-initialization of __init__
            cls._initialized = False 
        return cls._instance

    def __init__(self, peers=None, debug=False):
        # Mirror class constants onto the instance for MicroPython variants
        # that don't reliably resolve class attributes via `self`.
        self.BROADCAST_TARGET = b"\xff\xff\xff\xff\xff\xff"
        self.ESPNOW_MAX_PAYLOAD_BYTES = 250
        self._FRAG_MAGIC = b"\x7fM"
        self._FRAG_VERSION = 1
        self._FRAG_HEADER_BYTES = 7
        self._FRAG_REASSEMBLY_TIMEOUT_MS = 30000
        self._logger = None
        self._debug = bool(debug)
        self._init_logger()
        # Keep a concrete instance field for compatibility with MicroPython.
        self._FRAG_PAYLOAD_MAX_BYTES = int(self.ESPNOW_MAX_PAYLOAD_BYTES) - int(self._FRAG_HEADER_BYTES)
        self._irq_count = 0
        self._irq_packets_drained = 0
        self._fallback_recv_count = 0
        self._fallback_empty_count = 0

        # Bring up STA mode so ESP-NOW can operate.
        self.wlan_sta = network.WLAN(network.STA_IF)
        self.wlan_sta.active(True)
        self.wlan_sta.disconnect()

        # Canonical node id is the local MAC as lowercase hex.
        self.wlan_mac = self.wlan_sta.config("mac")
        self.node_id = self.mac_to_node_id(self.wlan_mac)
        self._log_info(
            "mesh init node_id={} mac={}".format(self.node_id, self.mac_to_node_id(self.wlan_mac))
        )
        self._log_debug("mesh init debug={} peers_arg={}".format(self._debug, peers))

        # ESP-NOW transport endpoint.
        self.espnow = aioespnow.AIOESPNow()
        self.espnow.active(True)

        # Peer cache and IRQ->async receive buffering.
        self._known_peers = set()
        self._rx_queue = []
        self._max_rx_queue = 32
        self._rx_event = None
        self._tx_message_id = 0
        self._fragment_buffers = {}
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
            if len(payload) <= self.ESPNOW_MAX_PAYLOAD_BYTES:
                self.espnow.send(target, payload)
            else:
                self._send_fragmented(target, payload)
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
            self._fallback_empty_count += 1
            if self._fallback_empty_count <= 3 or (self._fallback_empty_count % 25) == 0:
                self._log_info(
                    "recv fallback empty timeout_ms={} irq_count={} queue={} stats={}".format(
                        timeout_ms, self._irq_count, len(self._rx_queue), self.get_stats()
                    )
                )
            return None, None
        self._fallback_recv_count += 1
        payload = self._ingest_rx_packet(mac, msg)
        if payload is None:
            self._log_info(
                "recv fallback fragment peer={} bytes={} awaiting_more".format(
                    self.mac_to_node_id(mac), len(msg)
                )
            )
            return None, None
        self._log_info(
            "recv fallback packet peer={} bytes={} fallback_recv={} irq_count={}".format(
                self.mac_to_node_id(mac), len(payload), self._fallback_recv_count, self._irq_count
            )
        )
        return mac, payload

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
        self._log_info("interrupt rx enabled callback={}".format(self._on_espnow_irq))
        self._log_info("initial espnow stats={}".format(self.get_stats()))

    def disable_interrupt_rx(self):
        """Disable ESP-NOW interrupt callback."""
        self.espnow.irq(None)
        self._log_info("interrupt rx disabled")

    def _on_espnow_irq(self, *_):
        # ISR entry: move pending frames from driver FIFO into local queue.
        self._irq_count += 1
        if self._irq_count <= 5 or (self._irq_count % 25) == 0:
            self._log_info(
                "irq entry count={} queue={} stats={}".format(
                    self._irq_count, len(self._rx_queue), self.get_stats()
                )
            )
        self._drain_incoming()

    def _drain_incoming(self):
        """Drain all immediately available packets from ESP-NOW."""
        drained = 0
        while True:
            mac, msg = self.espnow.irecv(timeout_ms=0)
            if mac is None or msg is None:
                break
            payload = self._ingest_rx_packet(mac, msg)
            if payload is None:
                continue
            if len(self._rx_queue) >= self._max_rx_queue:
                # Drop oldest packet to make room for newest packet.
                self._rx_queue.pop(0)
                self._log_error("rx queue overflow, dropping oldest packet")
            self._rx_queue.append((mac, payload))
            drained += 1
            self._log_info(
                "irq packet peer={} raw_bytes={} payload_bytes={} queue={}".format(
                    self.mac_to_node_id(mac), len(msg), len(payload), len(self._rx_queue)
                )
            )
        if drained:
            self._irq_packets_drained += drained
            self._log_info(
                "irq drained {} packet(s) total_drained={} queue={}".format(
                    drained, self._irq_packets_drained, len(self._rx_queue)
                )
            )
        self._signal_rx_event()

    def _next_message_id(self):
        self._tx_message_id = (self._tx_message_id + 1) & 0xFFFF
        return self._tx_message_id

    def _send_fragmented(self, target, payload):
        max_payload = self._FRAG_PAYLOAD_MAX_BYTES
        total = (len(payload) + max_payload - 1) // max_payload
        if total > 255:
            raise ValueError("payload too large for fragmentation: {} bytes".format(len(payload)))

        msg_id = self._next_message_id()
        for index in range(total):
            start = index * max_payload
            end = start + max_payload
            part = payload[start:end]
            header = bytes(
                (
                    self._FRAG_MAGIC[0],
                    self._FRAG_MAGIC[1],
                    self._FRAG_VERSION,
                    (msg_id >> 8) & 0xFF,
                    msg_id & 0xFF,
                    total,
                    index,
                )
            )
            self.espnow.send(target, header + part)
        self._log_debug(
            "fragmented send target={} bytes={} chunks={}".format(
                self.mac_to_node_id(target), len(payload), total
            )
        )

    def _ingest_rx_packet(self, mac, msg):
        self._expire_fragment_buffers()
        frag = self._parse_fragment(msg)
        if frag is None:
            return msg
        if frag is False:
            return None

        msg_id, total, index, part = frag
        key = (mac, msg_id)
        now = self._now_ms()
        entry = self._fragment_buffers.get(key)
        if entry is None or entry["total"] != total:
            entry = {"total": total, "parts": {}, "updated_ms": now}
            self._fragment_buffers[key] = entry

        entry["parts"][index] = part
        entry["updated_ms"] = now

        if len(entry["parts"]) < total:
            return None

        assembled = bytearray()
        for i in range(total):
            if i not in entry["parts"]:
                return None
            assembled.extend(entry["parts"][i])
        del self._fragment_buffers[key]
        return bytes(assembled)

    def _parse_fragment(self, msg):
        if len(msg) < self._FRAG_HEADER_BYTES:
            return None
        if msg[0:2] != self._FRAG_MAGIC:
            return None
        if msg[2] != self._FRAG_VERSION:
            self._log_error("dropping fragment with unsupported version={}".format(msg[2]))
            return False

        msg_id = (msg[3] << 8) | msg[4]
        total = msg[5]
        index = msg[6]
        if total == 0 or index >= total:
            self._log_error("dropping malformed fragment id={} idx={}/{}".format(msg_id, index, total))
            return False
        return msg_id, total, index, msg[self._FRAG_HEADER_BYTES:]

    def _expire_fragment_buffers(self):
        if not self._fragment_buffers:
            return
        now = self._now_ms()
        stale = []
        for key, entry in self._fragment_buffers.items():
            if self._ticks_diff(now, entry["updated_ms"]) > self._FRAG_REASSEMBLY_TIMEOUT_MS:
                stale.append(key)
        for key in stale:
            del self._fragment_buffers[key]
        if stale:
            self._log_error("dropped {} stale fragment buffer(s)".format(len(stale)))

    def _now_ms(self):
        if hasattr(time, "ticks_ms"):
            return time.ticks_ms()
        return int(time.time() * 1000)

    def _ticks_diff(self, newer, older):
        if hasattr(time, "ticks_diff"):
            return time.ticks_diff(newer, older)
        return newer - older

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

    def _log_info(self, msg):
        if self._logger is not None and hasattr(self._logger, "info"):
            self._logger.info(msg)
            return
        print("INFO LighthouseMesh: {}".format(msg))

    def _log_error(self, msg):
        if self._logger is not None and hasattr(self._logger, "error"):
            self._logger.error(msg)
            return
        print("ERROR LighthouseMesh: {}".format(msg))
