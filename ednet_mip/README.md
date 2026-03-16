# ednet_mip

Mesh-based extension for the MicroPython `mip` package.

The extension adds an alternate transport path for package file downloads:

- Node side: `ednet_mip.client.install` intercepts `mip` download steps and requests file
  contents from a gateway node via LighthouseMesh.
- Gateway side: `ednet_mip.gateway.GatewayMIPService` listens on LighthouseMesh and fetches
  internet URLs, sending them back in base64-encoded chunks.

## Node usage

Replace direct `import mip` calls with:

```python
from ednet_mip import install

install(
    "github:your_user/your_package",
    gateway_peer="aabbccddeeff",   # target gateway node id or "broadcast"
    gateway_channel=6,
)
```

To keep local HTTP behavior on failure:

```python
install(
    "github:some/pkg",
    gateway_peer="aabbccddeeff",
    fallback_to_http=True,
)
```

## Gateway usage

Run the gateway service on a node with internet access:

```python
from ednet_mip.gateway import GatewayMIPService
GatewayMIPService(channel=6).run()
```

It will answer request messages from `install(..., gateway_peer=...)` and stream
`response.content` back to the requester in chunked frames.
