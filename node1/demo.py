import json
try:
    import utime as time
except Exception:
    import time
try:
    import urandom as random
except Exception:
    import random

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


PROFILE_PATH = "/lib/profile.json"
ADVERTISE_INTERVAL_S = 2
PROFILE_INTERVAL_S = 15
START_JITTER_MS = 1200
LOOP_JITTER_MS = 400
MESH_CHANNEL = 6


def _init_logger():
    if logging is None:
        return None
    log = logging.getLogger("node1.demo")
    if hasattr(log, "setLevel"):
        log.setLevel(logging.DEBUG)
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

def send_advertise_broadcast(endpoint, profile):
    service_ids = [int(entry.get("sid")) for entry in profile.get("s", []) if "sid" in entry]
    payload = endpoint.send_advertise(
        peer_id="broadcast",
        profile_hash=profile["h"],
        service_ids=service_ids,
    )
    _log_info("broadcasted advertise ({} bytes, services={})".format(len(payload), len(service_ids)))

def _rand_ms(max_ms):
    if max_ms <= 0:
        return 0
    try:
        if hasattr(random, "getrandbits"):
            return random.getrandbits(16) % max_ms
        if hasattr(random, "randrange"):
            return random.randrange(max_ms)
        if hasattr(random, "randint"):
            return random.randint(0, max_ms - 1)
    except Exception:
        pass
    return 0

def _now_ms():
    if hasattr(time, "ticks_ms"):
        return time.ticks_ms()
    return int(time.time() * 1000)

def _elapsed_ms(now, then):
    if hasattr(time, "ticks_diff"):
        return time.ticks_diff(now, then)
    return now - then


async def broadcast_loop(endpoint, profile):
    # Add startup jitter so two identical nodes are less likely to stay in lock-step.
    await asyncio.sleep_ms(_rand_ms(START_JITTER_MS))
    last_adv_ms = 0
    last_profile_ms = 0
    while True:
        now = _now_ms()
        if _elapsed_ms(now, last_adv_ms) >= (ADVERTISE_INTERVAL_S * 1000):
            send_advertise_broadcast(endpoint, profile)
            last_adv_ms = now
        if _elapsed_ms(now, last_profile_ms) >= (PROFILE_INTERVAL_S * 1000):
            send_profile_broadcast(endpoint, profile)
            last_profile_ms = now
        await asyncio.sleep_ms(200 + _rand_ms(LOOP_JITTER_MS))


def on_message(peer_id, message):
    mtype = message.get("t")
    if mtype == "p":
        _log_info("profile from {}: {}".format(peer_id, message))
        return
    _log_info("message from {}: type={} body={}".format(peer_id, mtype, message))


async def run():
    profile = load_profile()
    _log_info(
        "demo config channel={} advertise_s={} profile_s={}".format(
            MESH_CHANNEL, ADVERTISE_INTERVAL_S, PROFILE_INTERVAL_S
        )
    )
    mesh = LighthouseMesh(debug=True, channel=MESH_CHANNEL)
    transport = mesh.create_transport(default_peer="broadcast")
    endpoint = MessagingEndpoint(node_id=mesh.node_id, transport=transport)

    asyncio.create_task(broadcast_loop(endpoint, profile))
    await mesh.run(endpoint=endpoint, on_message=on_message, poll_ms=25)


if __name__ == "__main__":
    asyncio.run(run())
