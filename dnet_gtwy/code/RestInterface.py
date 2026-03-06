import json
print("dnet_gtwy: RestInterface module imported")
VERSION = "0.124"
try:
    import uasyncio as asyncio
except Exception:
    import asyncio

try:
    import utime as _time
except Exception:
    import time as _time
    
from MicroPyServer import MicroPyServer

from dnet.messaging import MessagingEndpoint
from dnet.messaging import Schema
from dnet.signalling.LighthouseMesh import LighthouseMesh


class RestInterface:
    def __init__(self, mesh=None, endpoint=None, channel=6, host="0.0.0.0", port=80):
        self.channel = int(channel)
        print("RestInterface: __init__ host={} port={} channel={}".format(host, port, self.channel))
        self.host = host
        self.port = int(port)
        self.mesh = mesh or LighthouseMesh(channel=self.channel)
        self._ensure_mesh_channel()
        self._message_log = []
        self._max_message_log = 250
        self._message_seq = 0
        print("RestInterface: version={}".format(VERSION))
        if endpoint is None:
            transport = self.mesh.create_transport(default_peer="broadcast")
            endpoint = MessagingEndpoint(node_id=self.mesh.node_id, transport=transport)
        self.endpoint = endpoint
        self.server = MicroPyServer()
        self._mesh_task = None
        self.setup_routes()

    def _ensure_mesh_channel(self):
        if self.mesh is None:
            return
        try:
            requested_channel = int(self.channel)
        except Exception:
            return
        try:
            current_channel = self.mesh._read_wifi_channel()
            current_channel_int = int(current_channel)
        except Exception:
            current_channel_int = None
            current_channel = None

        if current_channel_int == requested_channel:
            return

        sta_connected = False
        try:
            sta_connected = bool(self.mesh.wlan_sta.isconnected())
        except Exception:
            pass

        if sta_connected:
            print(
                "RestInterface: STA connected on channel {} while requested channel {}. "
                "Skipping mesh channel switch to avoid breaking network reachability.".format(
                    current_channel, requested_channel
                )
            )
            return

        try:
            print(
                "RestInterface: forcing mesh channel {} (current {})".format(
                    requested_channel, current_channel
                )
            )
            configure = getattr(self.mesh, "_configure_wifi_for_espnow", None)
            if configure is not None:
                configure(requested_channel)
            if hasattr(self.mesh, "_peer_channel"):
                self.mesh._peer_channel = requested_channel
                self.mesh._effective_channel = requested_channel
            print(
                "RestInterface: mesh channel set to {}".format(requested_channel)
            )
        except Exception as exc:
            print(
                "RestInterface: could not force mesh channel {} ({})".format(
                    requested_channel, exc
                )
            )

    def setup_routes(self):
        print("RestInterface: registering routes")
        self.server.add_route("/health", self.get_health, "GET")
        self.server.add_route("/status", self.get_espnow_status, "GET")
        self.server.add_route("/espnow/status", self.get_espnow_status, "GET")
        self.server.add_route("/nodes", self.get_nodes, "GET")
        self.server.add_route("/messages", self.get_messages, "GET")
        self.server.add_route("/version", self.get_version, "GET")

    def _drain_pending_messages(self, max_messages=32):
        # Keep registry fresh before servicing read endpoints.
        for _ in range(int(max_messages)):
            try:
                _, message = self.endpoint.poll()
            except Exception:
                # Ignore malformed frames so REST endpoints keep responding.
                continue
            if message is None:
                break

    def _now_ms(self):
        try:
            return _time.ticks_ms()
        except Exception:
            return int(_time.time() * 1000)

    def _coerce_message(self, message):
        try:
            return message.copy()
        except Exception:
            pass
        try:
            return str(message)
        except Exception:
            return repr(message)

    def _capture_message(self, peer_id, message):
        self._message_seq += 1
        entry = {
            "id": self._message_seq,
            "ts_ms": self._now_ms(),
            "peer_id": peer_id,
            "message": self._coerce_message(message),
        }
        self._message_log.append(entry)
        if len(self._message_log) > self._max_message_log:
            self._message_log.pop(0)

    def _on_mesh_message(self, peer_id, message):
        """Capture every inbound message and optionally keep app-level processing narrow."""
        try:
            self._capture_message(peer_id, message)
        except Exception as exc:
            print("RestInterface: message capture failed ({})".format(exc))

        try:
            msg_type = message.get(Schema.F_TYPE)
        except Exception:
            return

        if msg_type in (
            Schema.TYPE_PROFILE,
            Schema.TYPE_ADVERTISE,
        ):
            return

        # Other message types are currently not consumed by gateway logic and are intentionally ignored.
        return

    def get_messages(self, _request):
        print("RestInterface: incoming GET /messages")
        try:
            self._drain_pending_messages(max_messages=128)
        except Exception as exc:
            print("RestInterface: message drain failed in /messages ({})".format(exc))

        messages = list(self._message_log)
        self._message_log = []
        self._send_json_response({"status": "ok", "messages": messages, "version": VERSION})

    def get_version(self, request):
        print("RestInterface: incoming GET /version")
        if request is not None:
            try:
                print("RestInterface: request head={}".format(str(request).split("\r\n", 1)[0]))
            except Exception:
                pass
        self._send_json_response(
            {
                "status": "ok",
                "component": "dnet_gtwy",
                "version": VERSION,
                "service": "dnet_gtwy",
            }
        )

    def get_health(self, _request):
        print("RestInterface: incoming GET /health")
        self._send_json_response({"status": "ok", "service": "dnet_gtwy", "version": VERSION})

    def get_espnow_status(self, request):
        print("RestInterface: incoming GET /espnow/status or /status")
        if request is not None:
            try:
                print("RestInterface: request head={}".format(str(request).split("\r\n", 1)[0]))
            except Exception:
                pass
        try:
            self._drain_pending_messages()
            stats = self.mesh.get_stats()
            data = {
                "status": "ok",
                "node_id": self.mesh.node_id,
                "wifi_channel": self.mesh._read_wifi_channel(),
                "gateway_version": VERSION,
                "espnow": {
                    "tx_packets": int(stats[0]),
                    "tx_responses": int(stats[1]),
                    "tx_failures": int(stats[2]),
                    "rx_packets": int(stats[3]),
                    "rx_dropped": int(stats[4]),
                },
                "known_peers": len(self.mesh._known_peers),
                "rx_queue_depth": len(self.mesh._rx_queue),
            }
            self._send_json_response(data)
        except Exception as exc:
            self._send_json_response({"status": "error", "error": str(exc)}, http_code=500)

    def get_nodes(self, request):
        print("RestInterface: incoming GET /nodes")
        if request is not None:
            try:
                print("RestInterface: request head={}".format(str(request).split("\r\n", 1)[0]))
            except Exception:
                pass
        try:
            self._drain_pending_messages()
            nodes = self.endpoint.registry.all_nodes()
            profiles = []
            for node_id in sorted(nodes.keys()):
                node = nodes[node_id]
                services = node.get("services")
                if services is None:
                    service_ids = node.get("service_ids", [])
                else:
                    service_ids = [entry[Schema.F_SERVICE_ID] for entry in services]
                profiles.append(
                    {
                        "node_id": node_id,
                        "profile_hash": node.get("profile_hash"),
                        "name": node.get("name"),
                        "role": node.get("role"),
                        "firmware": node.get("firmware"),
                        "meta": node.get("meta", {}),
                        "service_ids": service_ids,
                        "last_seen_ms": node.get("last_seen_ms"),
                    }
                )

            data = {
                "status": "ok",
                "count": len(profiles),
                "nodes": profiles,
            }
            self._send_json_response(data)
        except Exception as exc:
            self._send_json_response({"status": "error", "error": str(exc)}, http_code=500)

    def _send_json_response(self, data, http_code=200):
        response = json.dumps(data)
        reason = "OK" if int(http_code) < 400 else "ERROR"
        self.server.send("HTTP/1.1 {} {}\r\n".format(int(http_code), reason))
        self.server.send("X-DistNet-Gateway-Version: {}\r\n".format(VERSION))
        self.server.send("Content-Type: application/json\r\n")
        self.server.send("Access-Control-Allow-Origin: *\r\n")
        self.server.send("Access-Control-Allow-Methods: GET, OPTIONS\r\n")
        self.server.send("Access-Control-Allow-Headers: Content-Type\r\n")
        self.server.send("\r\n")
        self.server.send(response)

    def start(self):
        self._mesh_task = None
        try:
            self._mesh_task = asyncio.create_task(
                self.mesh.run(endpoint=self.endpoint, on_message=self._on_mesh_message)
            )
            print("RestInterface: mesh background task started via asyncio.create_task()")
        except Exception as exc:
            print(
                "RestInterface: create_task failed ({}), trying loop.create_task fallback".format(
                    exc
                )
            )
            try:
                loop = asyncio.get_event_loop()
                self._mesh_task = loop.create_task(
                    self.mesh.run(endpoint=self.endpoint, on_message=self._on_mesh_message)
                )
                print("RestInterface: mesh background task started via event loop")
            except Exception as fallback_exc:
                print(
                    "RestInterface: unable to start mesh in background task ({})".format(
                        fallback_exc
                    )
                )
        try:
            import wifi  # noqa: F401
            import network
            if network is not None and hasattr(network, "WLAN"):
                print("RestInterface: wifi module loaded and WLAN available")
            else:
                print("RestInterface: wifi module loaded; WLAN not available in this runtime")
        except Exception as exc:
            print("RestInterface: wifi import deferred-start skipped/failed ({})".format(exc))

        print(
            "Gateway REST server starting on {}:{} ...".format(
                self.host, self.port
            )
        )
        print("GET /health")
        print("GET /status")
        print("GET /nodes")
        try:
            # Prefer explicit bind when supported by the server implementation.
            self.server.start(self.host, self.port)
        except TypeError:
            try:
                self.server.start(port=self.port)
            except TypeError:
                self.server.start()

    def stop(self):
        stopped = []
        if self._mesh_task is not None:
            try:
                self._mesh_task.cancel()
                stopped.append("mesh_task")
                print("RestInterface: mesh background task cancelled")
            except Exception as exc:
                print("RestInterface: mesh task cancel failed ({})".format(exc))
            self._mesh_task = None
        else:
            print("RestInterface: no active mesh task to stop")

        if hasattr(self.server, "stop"):
            try:
                self.server.stop()
                stopped.append("server")
            except Exception as exc:
                print("RestInterface: server stop failed ({})".format(exc))
        elif hasattr(self.server, "close"):
            try:
                self.server.close()
                stopped.append("server")
            except Exception as exc:
                print("RestInterface: server close failed ({})".format(exc))
        else:
            print("RestInterface: server stop method not available")

        print("RestInterface: stop complete for {}".format(", ".join(stopped) if stopped else "nothing"))
