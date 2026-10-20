"""Validation for the deliberately small remote device command surface."""

import ipaddress
import json
from urllib.parse import urlsplit


def public_url(value):
    if not isinstance(value, str) or not value or len(value) > 2048 or "\\" in value:
        return False
    if any(character.isspace() or ord(character) < 32 for character in value):
        return False
    try:
        url = urlsplit(value)
        host = (url.hostname or "").lower().rstrip(".")
        if url.scheme not in {"http", "https"} or url.username or url.password or "." not in host:
            return False
        if host.endswith((".localhost", ".local", ".internal")):
            return False
        if url.port is not None and not 1 <= url.port <= 65535:
            return False
        if host.replace(".", "").isdigit() or host.startswith("0x"):
            return ipaddress.ip_address(host).is_global
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return not any(not part for part in host.split("."))
    except ValueError:
        return False


def valid_payload(command, payload):
    try:
        if (
            not isinstance(payload, dict)
            or len(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()) > 8192
        ):
            return False
    except (ValueError, TypeError, RecursionError):
        return False
    if command in {"ping", "get_device_status"}:
        return not payload
    if command == "open_url":
        return set(payload) == {"url"} and public_url(payload["url"])
    if command == "show_notification":
        if set(payload) - {"title", "body", "text"} or any(not isinstance(value, str) for value in payload.values()):
            return False
        body = payload.get("body", payload.get("text", ""))
        return bool(body) and len(body) <= 2000 and len(payload.get("title", "")) <= 100
    return False
