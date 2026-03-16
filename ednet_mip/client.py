import mip as _mip

try:
    import utime as time
except Exception:
    import time

from dnet.signalling.LighthouseMesh import LighthouseMesh

from .mesh_protocol import (
    ACTION_CHUNK,
    ACTION_DONE,
    ACTION_ERROR,
    FIELD_DATA,
    FIELD_ERROR,
    FIELD_INDEX,
    FIELD_REQUEST_ID,
    FIELD_STATUS,
    FIELD_TOTAL,
    decode_chunk_data,
    get_action,
    get_request_id,
    make_request,
    parse,
)


_MIP_INSTALL = _mip.install


def _now_ms():
    if hasattr(time, "ticks_ms"):
        return time.ticks_ms()
    return int(time.time() * 1000)


def _ticks_diff(newer, older):
    if hasattr(time, "ticks_diff"):
        return time.ticks_diff(newer, older)
    return newer - older


class _GatewayFetcher:
    def __init__(
        self,
        gateway_peer,
        channel=6,
        timeout_ms=30000,
        poll_ms=25,
        mesh=None,
    ):
        self.gateway_peer = gateway_peer
        self.timeout_ms = int(timeout_ms)
        self.poll_ms = int(poll_ms)
        self.mesh = mesh or LighthouseMesh(channel=channel)

    def fetch_to_file(self, url, target_path):
        request_id = self._next_message_id()
        request = make_request(request_id, url)
        self.mesh.send_raw(self.gateway_peer, request)

        total_chunks = None
        bytes_written = 0
        next_index = 0
        buffered_chunks = {}
        deadline_ms = _now_ms() + self.timeout_ms

        with open(target_path, "wb") as output:
            while True:
                remaining = _ticks_diff(deadline_ms, _now_ms())
                if remaining <= 0:
                    raise TimeoutError("mesh fetch timeout for {}".format(url))
                timeout = self.poll_ms if remaining > self.poll_ms else int(remaining)
                if timeout < 1:
                    timeout = 1

                mac, payload = self.mesh.recv_raw(timeout_ms=timeout)
                if payload is None:
                    continue
                msg = parse(payload)
                if msg is None:
                    continue
                if get_request_id(msg) != request_id:
                    continue

                action = get_action(msg)
                if action == ACTION_CHUNK:
                    chunk_index = int(msg.get(FIELD_INDEX, -1))
                    total_chunks = int(msg.get(FIELD_TOTAL, total_chunks or 0))
                    chunk_data = decode_chunk_data(msg.get(FIELD_DATA))
                    if chunk_index < next_index:
                        continue
                    if chunk_index != next_index:
                        buffered_chunks[chunk_index] = chunk_data
                        continue

                    output.write(chunk_data)
                    bytes_written += len(chunk_data)
                    next_index += 1

                    while next_index in buffered_chunks:
                        buffered_chunk = buffered_chunks.pop(next_index)
                        output.write(buffered_chunk)
                        bytes_written += len(buffered_chunk)
                        next_index += 1

                elif action == ACTION_DONE:
                    status = int(msg.get(FIELD_STATUS, 200))
                    if status != 200:
                        raise RuntimeError("gateway failed with HTTP status {}".format(status))
                    if total_chunks is None:
                        total_chunks = int(msg.get(FIELD_TOTAL, next_index))
                    if total_chunks is not None and next_index >= total_chunks:
                        return True
                    if total_chunks == 0:
                        return True
                    # Keep collecting until all declared chunks arrive, then loop
                    # ends by timeout if chunks are missing.

                elif action == ACTION_ERROR:
                    error_msg = str(msg.get(FIELD_ERROR, "unknown"))
                    raise RuntimeError("gateway error {}".format(error_msg))

                # Keep the receive loop alive while waiting for out-of-order chunks.
                if total_chunks is not None and next_index >= total_chunks:
                    return True

        return bool(bytes_written or total_chunks in (0, None))

    def _next_message_id(self):
        if not hasattr(self, "_message_id"):
            self._message_id = 0
        self._message_id = (self._message_id + 1) & 0xFFFF
        return self._message_id or 1


def install(
    package,
    index=None,
    target=None,
    version=None,
    mpy=True,
    *,
    gateway_peer=None,
    gateway_channel=6,
    timeout_ms=30000,
    poll_ms=25,
    fallback_to_http=False,
):
    if gateway_peer is None:
        return _MIP_INSTALL(package, index, target, version, mpy)

    fetcher = _GatewayFetcher(
        gateway_peer=gateway_peer,
        channel=gateway_channel,
        timeout_ms=timeout_ms,
        poll_ms=poll_ms,
    )

    def _gateway_download_file(url, dest):
        return fetcher.fetch_to_file(url, dest)

    original_download = _mip._download_file
    try:
        _mip._download_file = _gateway_download_file
        return _MIP_INSTALL(package, index, target, version, mpy)
    except Exception:
        if not fallback_to_http:
            raise
        _mip._download_file = original_download
        return _MIP_INSTALL(package, index, target, version, mpy)
    finally:
        _mip._download_file = original_download
