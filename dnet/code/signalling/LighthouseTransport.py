class LighthouseMeshTransport:
    """
    Adapter between dnet.messaging.MessagingEndpoint and LighthouseMesh.

    Implements the transport contract expected by MessagingEndpoint:
    - send(peer_id, payload)
    - recv() -> (peer_id, payload) or (None, None)
    """

    def __init__(self, mesh, default_peer=None):
        self.mesh = mesh
        self.default_peer = default_peer

    def send(self, peer_id, payload):
        peer = self.default_peer if peer_id is None else peer_id
        self.mesh.send_raw(peer, payload)

    def recv(self):
        mac, payload = self.mesh.recv_raw(timeout_ms=0)
        if payload is None:
            return None, None
        return self.mesh.mac_to_node_id(mac), payload

