try:
    import urequests as requests
except Exception:
    import requests

from dnet.signalling.LighthouseMesh import LighthouseMesh

from .mesh_protocol import (
    ACTION_REQUEST,
    FIELD_ACTION,
    FIELD_REQUEST_ID,
    FIELD_URL,
    make_chunk,
    make_done,
    make_error,
    parse,
)


class GatewayMIPService:
    """
    Gateway component that answers mesh file-download requests for mip clients.

    It receives JSON request frames over LighthouseMesh, performs HTTP/HTTPS fetches
    using requests, and returns base64-encoded chunks over ESP-NOW.
    """

    def __init__(self, mesh=None, channel=6, chunk_size=1024, peer=None):
        self.mesh = mesh or LighthouseMesh(channel=channel)
        self.chunk_size = int(chunk_size)
        self.peer = peer

    def run(self):
        while True:
            try:
                self._handle_once()
            except Exception as exc:
                print("GatewayMIPService: error {}".format(exc))
                continue

    def _handle_once(self):
        mac, payload = self.mesh.recv_raw(timeout_ms=50)
        if payload is None:
            return

        msg = parse(payload)
        if msg is None:
            return
        if msg.get(FIELD_ACTION) != ACTION_REQUEST:
            return

        request_id = int(msg.get(FIELD_REQUEST_ID, -1))
        source = self.peer or mac
        url = msg.get(FIELD_URL)
        if request_id <= 0 or not isinstance(url, str) or not url:
            self._send(
                source,
                make_error(request_id if request_id > 0 else 0, "invalid request payload"),
            )
            return

        self._process_request(source, request_id, url)

    def _process_request(self, peer, request_id, url):
        try:
            response = requests.get(url)
            try:
                status = int(response.status_code)
                if status != 200:
                    self._send(peer, make_error(request_id, "http_status_{}".format(status)))
                    return
                payload = response.content
            finally:
                try:
                    response.close()
                except Exception:
                    pass

            total_chunks = (len(payload) + self.chunk_size - 1) // self.chunk_size
            for index in range(int(total_chunks)):
                start = index * self.chunk_size
                end = start + self.chunk_size
                chunk = payload[start:end]
                self.mesh.send_raw(
                    peer,
                    make_chunk(request_id, index, total_chunks, chunk),
                )
            self._send(peer, make_done(request_id, status, total_chunks, len(payload)))
        except Exception as exc:
            self._send(peer, make_error(request_id, str(exc)))

    def _send(self, peer, message):
        self.mesh.send_raw(peer, message)


def run(*args, **kwargs):
    GatewayMIPService(*args, **kwargs).run()
