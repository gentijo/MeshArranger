import mip as _mip

from .client import install
from .gateway import GatewayMIPService


def enable_gateway_transport():
    """
    Make `mip.install(...)` use the mesh gateway when `gateway_peer` is provided.
    """
    _mip.install = install


__all__ = ["install", "enable_gateway_transport", "GatewayMIPService"]
