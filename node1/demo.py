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
from dnet.signalling.LighthouseMesh import LighthouseMesh


PROFILE_PATH = "profile.json"
BROADCAST_INTERVAL_S = 5


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
        profile_hash=profile["h"],
        services=profile["s"],
        name=profile.get("name"),
        role=profile.get("role"),
        firmware=profile.get("fw"),
        meta=profile.get("meta"),
    )
    _log_info("broadcasted profile ({} bytes)".format(len(payload)))


async def broadcast_loop(endpoint, profile):
    while True:
        send_profile_broadcast(endpoint, profile)
        await asyncio.sleep(BROADCAST_INTERVAL_S)


def on_message(peer_id, message):
    if message.get("t") != "p":
        return
    _log_info("profile from {}: {}".format(peer_id, message))


async def run():
    profile = load_profile()
    mesh = LighthouseMesh()
    transport = mesh.create_transport(default_peer="broadcast")
    endpoint = MessagingEndpoint(node_id=mesh.node_id, transport=transport)

    asyncio.create_task(broadcast_loop(endpoint, profile))
    await mesh.run(endpoint=endpoint, on_message=on_message, poll_ms=25)


if __name__ == "__main__":
    asyncio.run(run())
