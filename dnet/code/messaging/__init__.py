"""
DistNet capability messaging package.

Short-form messages are optimized for ESP-NOW packet budgets.
Long-form profile messages are requested directly on demand.
"""

from .codec import (
    MAX_SHORT_PACKET_BYTES,
    MessageCodec,
    MessageValidationError,
)
from .protocol import MessagingEndpoint
from .registry import ServiceRegistry

__all__ = [
    "MAX_SHORT_PACKET_BYTES",
    "MessageCodec",
    "MessageValidationError",
    "MessagingEndpoint",
    "ServiceRegistry",
]
