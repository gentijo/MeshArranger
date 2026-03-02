try:
    from dnet.messaging import MessageCodec, MessagingEndpoint
except Exception:
    # Allows running under CPython without importing dnet/__init__.py.
    from messaging import MessageCodec, MessagingEndpoint


class MemoryTransport:
    def __init__(self):
        self.queue = []

    def send(self, peer_id, payload):
        self.queue.append((peer_id, payload))

    def recv(self):
        if not self.queue:
            return None, None
        return self.queue.pop(0)


def run_demo():
    tx = MemoryTransport()
    endpoint = MessagingEndpoint(node_id="node_a", transport=tx, codec=MessageCodec())

    short_payload = endpoint.send_advertise(
        peer_id="ff:ff:ff:ff:ff:ff",
        profile_hash="5fe921aa",
        service_ids=[100, 205, 900],
    )
    assert len(short_payload) <= 205, len(short_payload)

    _, msg = endpoint.poll()
    assert msg["t"] == "a"

    providers = endpoint.find_providers(205)
    assert providers and providers[0]["node_id"] == "node_a"

    query_payload = endpoint.send_query(peer_id="node_b", service_id=205)
    assert query_payload == '{"v":1,"t":"q","n":"node_a","sid":205}'

    print("demo ok")
    print("short advertise bytes:", len(short_payload))
    print("providers for 205:", providers)


if __name__ == "__main__":
    run_demo()
