"""
Example: hook MessagingEndpoint to LighthouseMesh via LighthouseMeshTransport.
"""

from dnet.messaging import MessagingEndpoint
from dnet.signalling.LighthouseMesh import LighthouseMesh


def build_endpoint():
    mesh = LighthouseMesh(use_broadcast=True)
    transport = mesh.create_transport(default_peer="broadcast")
    endpoint = MessagingEndpoint(node_id=mesh.node_id, transport=transport)
    return mesh, endpoint


async def run():
    mesh, endpoint = build_endpoint()

    # Broadcast compact capability advertisement.
    endpoint.send_advertise(
        peer_id="broadcast",
        profile_hash="01b3e9a0",
        service_ids=[100, 205, 900],
    )

    def on_message(peer_id, message):
        print("message from {} -> {}".format(peer_id, message))

    await mesh.run(endpoint=endpoint, on_message=on_message, poll_ms=25)

