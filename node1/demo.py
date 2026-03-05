import json

try:
    import uasyncio as asyncio
except Exception:
    import asyncio

try:
    import logging
except Exception:
    logging = None

from dnet.messaging import MessagingEndpoint
from dnet.messaging import Schema
from dnet.signalling.LighthouseMesh import LighthouseMesh


PROFILE_PATH = "/lib/profile.json"
BROADCAST_INTERVAL_S = 5
MESH_CHANNEL = 6


def _init_logger():
    if logging is None:
        return None
    log = logging.getLogger("node1.demo")
    if hasattr(log, "setLevel"):
        log.setLevel(logging.INFO)
    return log


LOGGER = _init_logger()


def _log_info(message):
    if LOGGER is not None and hasattr(LOGGER, "info"):
        LOGGER.info(message)
        return
    print("INFO node1.demo: {}".format(message))


def load_profile(path=PROFILE_PATH):
    with open(path, "r") as f:
        return json.load(f)


def send_profile_broadcast(endpoint, profile):
    payload = endpoint.send_profile(
        peer_id="broadcast",
        profile_hash=profile[Schema.F_PROFILE_HASH],
        services=profile[Schema.F_SERVICES],
        name=profile.get(Schema.F_NODE_NAME),
        role=profile.get(Schema.F_ROLE),
        firmware=profile.get(Schema.F_FIRMWARE),
        meta=profile.get(Schema.F_META),
    )
    _log_info("broadcasted profile ({} bytes)".format(len(payload)))


async def broadcast_loop(endpoint, profile):
    while True:
        send_profile_broadcast(endpoint, profile)
        await asyncio.sleep(BROADCAST_INTERVAL_S)


def on_message(peer_id, message):
    if message.get(Schema.F_TYPE) != Schema.TYPE_PROFILE:
        return
    _log_info("profile from {}: {}".format(peer_id, message))


async def run():
    profile = load_profile()
    _log_info(
        "demo config channel={} interval_s={}".format(
            MESH_CHANNEL, BROADCAST_INTERVAL_S
        )
    )
    mesh = LighthouseMesh(channel=MESH_CHANNEL)
    transport = mesh.create_transport(default_peer="broadcast")
    endpoint = MessagingEndpoint(node_id=mesh.node_id, transport=transport)

    asyncio.create_task(broadcast_loop(endpoint, profile))
    await mesh.run(endpoint=endpoint, on_message=on_message, poll_ms=25)


if __name__ == "__main__":
    asyncio.run(run())
