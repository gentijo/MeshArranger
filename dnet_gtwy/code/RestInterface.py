import json

from MicroPyServer import MicroPyServer

from dnet.messaging import MessagingEndpoint
from dnet.messaging import Schema
from dnet.signalling.LighthouseMesh import LighthouseMesh


class RestInterface:
    def __init__(self, mesh=None, endpoint=None, channel=6):
        self.mesh = mesh or LighthouseMesh(channel=channel)
        if endpoint is None:
            transport = self.mesh.create_transport(default_peer="broadcast")
            endpoint = MessagingEndpoint(node_id=self.mesh.node_id, transport=transport)
        self.endpoint = endpoint
        self.server = MicroPyServer()
        self.setup_routes()

    def setup_routes(self):
        self.server.add_route("/espnow/status", self.get_espnow_status, "GET")
        self.server.add_route("/nodes", self.get_nodes, "GET")

    def _drain_pending_messages(self, max_messages=32):
        # Keep registry fresh before servicing read endpoints.
        for _ in range(int(max_messages)):
            _, message = self.endpoint.poll()
            if message is None:
                break

    def get_espnow_status(self, _request):
        self._drain_pending_messages()
        stats = self.mesh.get_stats()
        data = {
            "status": "ok",
            "node_id": self.mesh.node_id,
            "wifi_channel": self.mesh._read_wifi_channel(),
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

    def get_nodes(self, _request):
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

    def _send_json_response(self, data, http_code=200):
        response = json.dumps(data)
        self.server.send("HTTP/1.1 {} OK\r\n".format(int(http_code)))
        self.server.send("Content-Type: application/json\r\n")
        self.server.send("Access-Control-Allow-Origin: *\r\n")
        self.server.send("Access-Control-Allow-Methods: GET, OPTIONS\r\n")
        self.server.send("Access-Control-Allow-Headers: Content-Type\r\n")
        self.server.send("\r\n")
        self.server.send(response)

    def start(self):
        print("Gateway REST server listening on port 80")
        print("GET /espnow/status")
        print("GET /nodes")
        self.server.start()
