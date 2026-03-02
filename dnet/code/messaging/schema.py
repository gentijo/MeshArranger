"""
Tight JSON schemas for DistNet capability messaging.

Short form message keys are intentionally minimal to stay inside
small wireless packet budgets.
"""

PROTOCOL_VERSION = 1

# Message type codes (1 byte when serialized).
TYPE_ADVERTISE = "a"      # Short capability advertisement (broadcast).
TYPE_QUERY = "q"          # Query for providers of a capability.
TYPE_QUERY_RESULT = "i"   # Response with candidate providers.
TYPE_GET_PROFILE = "g"    # Request full profile from a node.
TYPE_PROFILE = "p"        # Full profile response.

# Hard packet limit for compact advertisements.
SHORT_PACKET_MAX_BYTES = 205

# Field names (short keys to save bytes).
F_VERSION = "v"
F_TYPE = "t"
F_NODE_ID = "n"
F_PROFILE_HASH = "h"
F_SERVICES = "s"
F_SERVICE_ID = "sid"
F_PROVIDERS = "p"
F_TARGET = "to"

# Long profile fields.
F_NODE_NAME = "name"
F_ROLE = "role"
F_FIRMWARE = "fw"
F_META = "meta"


SHORT_ADVERTISE_SCHEMA = {
    "required": (F_VERSION, F_TYPE, F_NODE_ID, F_PROFILE_HASH, F_SERVICES),
    "type": TYPE_ADVERTISE,
}

QUERY_SCHEMA = {
    "required": (F_VERSION, F_TYPE, F_NODE_ID, F_SERVICE_ID),
    "type": TYPE_QUERY,
}

QUERY_RESULT_SCHEMA = {
    "required": (F_VERSION, F_TYPE, F_NODE_ID, F_SERVICE_ID, F_PROVIDERS),
    "type": TYPE_QUERY_RESULT,
}

GET_PROFILE_SCHEMA = {
    "required": (F_VERSION, F_TYPE, F_NODE_ID, F_TARGET),
    "type": TYPE_GET_PROFILE,
}

PROFILE_SCHEMA = {
    "required": (F_VERSION, F_TYPE, F_NODE_ID, F_PROFILE_HASH, F_SERVICES),
    "type": TYPE_PROFILE,
}

