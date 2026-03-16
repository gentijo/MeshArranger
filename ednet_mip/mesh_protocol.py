import json

try:
    import ubinascii
except Exception:
    import binascii as ubinascii


FIELD_ACTION = "a"
FIELD_REQUEST_ID = "i"
FIELD_URL = "u"
FIELD_INDEX = "x"
FIELD_TOTAL = "t"
FIELD_DATA = "b"
FIELD_STATUS = "s"
FIELD_SIZE = "n"
FIELD_ERROR = "e"

ACTION_REQUEST = "r"
ACTION_CHUNK = "c"
ACTION_DONE = "d"
ACTION_ERROR = "e"


def dumps(payload):
    return json.dumps(payload, separators=(",", ":"))


def parse(raw):
    if raw is None:
        return None
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = bytes(raw).decode("utf-8")
        except Exception:
            return None
    if not isinstance(raw, str):
        return None

    raw = raw.strip()
    if not raw or raw[0] != "{":
        return None
    try:
        msg = json.loads(raw)
    except Exception:
        return None
    if not isinstance(msg, dict):
        return None
    return msg


def _ensure_int(value, default=None):
    try:
        return int(value)
    except Exception:
        return default


def make_request(message_id, url):
    return dumps(
        {
            FIELD_ACTION: ACTION_REQUEST,
            FIELD_REQUEST_ID: int(message_id),
            FIELD_URL: str(url),
        }
    )


def make_chunk(message_id, index, total, chunk_bytes):
    if isinstance(chunk_bytes, str):
        chunk_bytes = chunk_bytes.encode("utf-8")
    encoded_chunk = ubinascii.b2a_base64(bytes(chunk_bytes)).decode("utf-8").strip()
    return dumps(
        {
            FIELD_ACTION: ACTION_CHUNK,
            FIELD_REQUEST_ID: int(message_id),
            FIELD_INDEX: int(index),
            FIELD_TOTAL: int(total),
            FIELD_DATA: encoded_chunk,
        }
    )


def make_done(message_id, status_code, total_chunks, total_size):
    return dumps(
        {
            FIELD_ACTION: ACTION_DONE,
            FIELD_REQUEST_ID: int(message_id),
            FIELD_STATUS: int(status_code),
            FIELD_TOTAL: int(total_chunks),
            FIELD_SIZE: int(total_size),
        }
    )


def make_error(message_id, error):
    return dumps(
        {
            FIELD_ACTION: ACTION_ERROR,
            FIELD_REQUEST_ID: int(message_id),
            FIELD_ERROR: str(error),
        }
    )


def decode_chunk_data(raw_chunk):
    if raw_chunk is None:
        return b""
    if isinstance(raw_chunk, str):
        raw_chunk = raw_chunk.encode("utf-8")
    return ubinascii.a2b_base64(raw_chunk)


def get_action(msg):
    if not isinstance(msg, dict):
        return None
    return msg.get(FIELD_ACTION)


def get_request_id(msg):
    return _ensure_int(msg.get(FIELD_REQUEST_ID), None) if isinstance(msg, dict) else None
