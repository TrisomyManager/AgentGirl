"""QQ's official Ed25519 callback protocol; no gateway or host identity is implied."""

import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


class QQSignature:
    def __init__(self, secret: str):
        seed = secret.encode("utf-8")
        if not seed:
            raise ValueError("QQ signing secret is missing")
        while len(seed) < 32:
            seed *= 2
        self._key = Ed25519PrivateKey.from_private_bytes(seed[:32])

    def verify(self, body: bytes, signature: str, timestamp: str, *, now=None, max_age=300) -> bool:
        if len(body) > 1024 * 1024 or not isinstance(signature, str) or len(signature) != 128:
            return False
        if not isinstance(timestamp, str) or not timestamp.isascii() or not timestamp.isdecimal():
            return False
        if len(timestamp) not in (10, 13):
            return False
        observed = int(timestamp) / (1000 if len(timestamp) == 13 else 1)
        if abs((time.time() if now is None else now) - observed) > max_age:
            return False
        try:
            raw = bytes.fromhex(signature)
            if len(raw) != 64 or raw[-1] & 224:
                return False
            self._key.public_key().verify(raw, timestamp.encode("ascii") + body)
        except (InvalidSignature, ValueError):
            return False
        return True

    def challenge(self, payload):
        data = payload.get("d") if isinstance(payload, dict) and payload.get("op") == 13 else None
        if not isinstance(data, dict):
            raise ValueError("Invalid QQ callback challenge")
        token, timestamp = data.get("plain_token"), data.get("event_ts")
        if (
            not isinstance(token, str)
            or not isinstance(timestamp, str)
            or not 1 <= len(token) <= 1024
            or not 1 <= len(timestamp) <= 32
        ):
            raise ValueError("Invalid QQ callback challenge")
        return {"plain_token": token, "signature": self._key.sign((timestamp + token).encode("utf-8")).hex()}
