import time

from . import schema


class ServiceRegistry:
    """
    In-memory registry for capability discovery.
    Works with both short advertisements and full profiles.
    """

    def __init__(self):
        self._nodes = {}
        self._service_to_nodes = {}

    def register_advertisement(self, msg, seen_at_ms=None):
        node_id = msg[schema.F_NODE_ID]
        profile_hash = msg[schema.F_PROFILE_HASH]
        services = msg[schema.F_SERVICES]
        if seen_at_ms is None:
            seen_at_ms = self._now_ms()

        node = self._nodes.get(node_id, {})
        node["node_id"] = node_id
        node["profile_hash"] = profile_hash
        node["service_ids"] = list(services)
        node["last_seen_ms"] = int(seen_at_ms)
        self._nodes[node_id] = node

        for service_id in services:
            providers = self._service_to_nodes.get(service_id, set())
            providers.add(node_id)
            self._service_to_nodes[service_id] = providers

    def register_profile(self, msg, seen_at_ms=None):
        node_id = msg[schema.F_NODE_ID]
        if seen_at_ms is None:
            seen_at_ms = self._now_ms()

        node = self._nodes.get(node_id, {})
        node["node_id"] = node_id
        node["profile_hash"] = msg[schema.F_PROFILE_HASH]
        node["last_seen_ms"] = int(seen_at_ms)
        node["name"] = msg.get(schema.F_NODE_NAME)
        node["role"] = msg.get(schema.F_ROLE)
        node["firmware"] = msg.get(schema.F_FIRMWARE)
        node["meta"] = msg.get(schema.F_META, {})
        node["services"] = list(msg[schema.F_SERVICES])
        node["service_ids"] = [entry[schema.F_SERVICE_ID] for entry in node["services"]]
        self._nodes[node_id] = node

        for service_id in node["service_ids"]:
            providers = self._service_to_nodes.get(service_id, set())
            providers.add(node_id)
            self._service_to_nodes[service_id] = providers

    def find_service(self, service_id):
        """
        Query API:
        Return candidate providers for a service id.
        """
        providers = self._service_to_nodes.get(int(service_id), set())
        results = []
        for node_id in providers:
            node = self._nodes.get(node_id)
            if not node:
                continue
            results.append(
                {
                    "node_id": node["node_id"],
                    "profile_hash": node.get("profile_hash"),
                    "name": node.get("name"),
                    "role": node.get("role"),
                    "last_seen_ms": node.get("last_seen_ms"),
                }
            )
        results.sort(key=lambda r: (r["last_seen_ms"] or 0), reverse=True)
        return results

    def get_node(self, node_id):
        return self._nodes.get(node_id)

    def all_nodes(self):
        return dict(self._nodes)

    @staticmethod
    def _now_ms():
        return int(time.time() * 1000)
