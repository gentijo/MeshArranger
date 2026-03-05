import json

from .schema import Schema


MAX_SHORT_PACKET_BYTES = Schema.SHORT_PACKET_MAX_BYTES


class MessageValidationError(ValueError):
    pass


class MessageCodec:
    def __init__(self, max_short_packet_bytes=MAX_SHORT_PACKET_BYTES):
        self.max_short_packet_bytes = int(max_short_packet_bytes)

    def encode_advertise(self, node_id, profile_hash, service_ids):
        msg = {
            Schema.F_VERSION: Schema.PROTOCOL_VERSION,
            Schema.F_TYPE: Schema.TYPE_ADVERTISE,
            Schema.F_NODE_ID: str(node_id),
            Schema.F_PROFILE_HASH: str(profile_hash),
            Schema.F_SERVICES: list(service_ids),
        }
        self.validate(msg)
        encoded = self.dumps(msg)
        if len(encoded) > self.max_short_packet_bytes:
            raise MessageValidationError(
                "short advertise exceeds {} bytes (got {})".format(
                    self.max_short_packet_bytes, len(encoded)
                )
            )
        return encoded

    def encode_query(self, node_id, service_id):
        msg = {
            Schema.F_VERSION: Schema.PROTOCOL_VERSION,
            Schema.F_TYPE: Schema.TYPE_QUERY,
            Schema.F_NODE_ID: str(node_id),
            Schema.F_SERVICE_ID: int(service_id),
        }
        self.validate(msg)
        return self.dumps(msg)

    def encode_query_result(self, node_id, service_id, providers):
        msg = {
            Schema.F_VERSION: Schema.PROTOCOL_VERSION,
            Schema.F_TYPE: Schema.TYPE_QUERY_RESULT,
            Schema.F_NODE_ID: str(node_id),
            Schema.F_SERVICE_ID: int(service_id),
            Schema.F_PROVIDERS: [str(p) for p in providers],
        }
        self.validate(msg)
        return self.dumps(msg)

    def encode_get_profile(self, node_id, target_node_id):
        msg = {
            Schema.F_VERSION: Schema.PROTOCOL_VERSION,
            Schema.F_TYPE: Schema.TYPE_GET_PROFILE,
            Schema.F_NODE_ID: str(node_id),
            Schema.F_TARGET: str(target_node_id),
        }
        self.validate(msg)
        return self.dumps(msg)

    def encode_profile(
        self,
        node_id,
        profile_hash,
        services,
        name=None,
        role=None,
        firmware=None,
        meta=None,
    ):
        msg = {
            Schema.F_VERSION: Schema.PROTOCOL_VERSION,
            Schema.F_TYPE: Schema.TYPE_PROFILE,
            Schema.F_NODE_ID: str(node_id),
            Schema.F_PROFILE_HASH: str(profile_hash),
            Schema.F_SERVICES: list(services),
        }
        if name is not None:
            msg[Schema.F_NODE_NAME] = str(name)
        if role is not None:
            msg[Schema.F_ROLE] = str(role)
        if firmware is not None:
            msg[Schema.F_FIRMWARE] = str(firmware)
        if meta is not None:
            if not isinstance(meta, dict):
                raise MessageValidationError("meta must be a dict")
            msg[Schema.F_META] = meta
        self.validate(msg)
        return self.dumps(msg)

    def decode(self, raw):
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        msg = json.loads(raw)
        self.validate(msg)
        return msg

    def dumps(self, msg):
        # separators remove all whitespace to minimize packet size.
        return json.dumps(msg, separators=(",", ":"))

    def validate(self, msg):
        if not isinstance(msg, dict):
            raise MessageValidationError("message must be a JSON object")

        self._validate_common(msg)
        mtype = msg[Schema.F_TYPE]
        if mtype == Schema.TYPE_ADVERTISE:
            self._validate_advertise(msg)
        elif mtype == Schema.TYPE_QUERY:
            self._validate_query(msg)
        elif mtype == Schema.TYPE_QUERY_RESULT:
            self._validate_query_result(msg)
        elif mtype == Schema.TYPE_GET_PROFILE:
            self._validate_get_profile(msg)
        elif mtype == Schema.TYPE_PROFILE:
            self._validate_profile(msg)
        else:
            raise MessageValidationError("unsupported message type: {}".format(mtype))

    def _validate_common(self, msg):
        for key in (Schema.F_VERSION, Schema.F_TYPE, Schema.F_NODE_ID):
            if key not in msg:
                raise MessageValidationError("missing field '{}'".format(key))
        if msg[Schema.F_VERSION] != Schema.PROTOCOL_VERSION:
            raise MessageValidationError(
                "unsupported version: {}".format(msg[Schema.F_VERSION])
            )
        if not isinstance(msg[Schema.F_TYPE], str):
            raise MessageValidationError("field '{}' must be a string".format(Schema.F_TYPE))
        if not isinstance(msg[Schema.F_NODE_ID], str) or not msg[Schema.F_NODE_ID]:
            raise MessageValidationError(
                "field '{}' must be a non-empty string".format(Schema.F_NODE_ID)
            )

    def _validate_advertise(self, msg):
        for key in Schema.SHORT_ADVERTISE_SCHEMA["required"]:
            if key not in msg:
                raise MessageValidationError("missing field '{}'".format(key))
        self._validate_service_ids(msg[Schema.F_SERVICES])
        if not isinstance(msg[Schema.F_PROFILE_HASH], str):
            raise MessageValidationError(
                "field '{}' must be a string".format(Schema.F_PROFILE_HASH)
            )

    def _validate_query(self, msg):
        for key in Schema.QUERY_SCHEMA["required"]:
            if key not in msg:
                raise MessageValidationError("missing field '{}'".format(key))
        self._validate_service_id(msg[Schema.F_SERVICE_ID])

    def _validate_query_result(self, msg):
        for key in Schema.QUERY_RESULT_SCHEMA["required"]:
            if key not in msg:
                raise MessageValidationError("missing field '{}'".format(key))
        self._validate_service_id(msg[Schema.F_SERVICE_ID])
        providers = msg[Schema.F_PROVIDERS]
        if not isinstance(providers, list):
            raise MessageValidationError(
                "field '{}' must be an array".format(Schema.F_PROVIDERS)
            )
        for provider in providers:
            if not isinstance(provider, str) or not provider:
                raise MessageValidationError("provider ids must be non-empty strings")

    def _validate_get_profile(self, msg):
        for key in Schema.GET_PROFILE_SCHEMA["required"]:
            if key not in msg:
                raise MessageValidationError("missing field '{}'".format(key))
        if not isinstance(msg[Schema.F_TARGET], str) or not msg[Schema.F_TARGET]:
            raise MessageValidationError("field '{}' must be a non-empty string".format(Schema.F_TARGET))

    def _validate_profile(self, msg):
        for key in Schema.PROFILE_SCHEMA["required"]:
            if key not in msg:
                raise MessageValidationError("missing field '{}'".format(key))
        if not isinstance(msg[Schema.F_PROFILE_HASH], str):
            raise MessageValidationError(
                "field '{}' must be a string".format(Schema.F_PROFILE_HASH)
            )
        services = msg[Schema.F_SERVICES]
        if not isinstance(services, list):
            raise MessageValidationError(
                "field '{}' must be an array".format(Schema.F_SERVICES)
            )
        for entry in services:
            if not isinstance(entry, dict):
                raise MessageValidationError(
                    "profile services must be objects with details"
                )
            if Schema.F_SERVICE_ID not in entry:
                raise MessageValidationError(
                    "profile service entry missing '{}'".format(Schema.F_SERVICE_ID)
                )
            self._validate_service_id(entry[Schema.F_SERVICE_ID])

    def _validate_service_ids(self, service_ids):
        if not isinstance(service_ids, list) or not service_ids:
            raise MessageValidationError("field '{}' must be a non-empty array".format(Schema.F_SERVICES))
        for value in service_ids:
            self._validate_service_id(value)

    def _validate_service_id(self, service_id):
        if not isinstance(service_id, int):
            raise MessageValidationError("service id must be an int")
        if service_id < 0 or service_id > 65535:
            raise MessageValidationError("service id out of uint16 range")
