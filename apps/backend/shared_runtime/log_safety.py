"""Connection diagnostics without credentials, database names or query values."""

import logging
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def connection_target(value: str) -> str:
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        if not parsed.scheme or not host:
            return "configured"
        if ":" in host:
            host = f"[{host}]"
        port = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.scheme}://{host}{port}"
    except (TypeError, ValueError):
        return "configured"


def redact_http_urls(message: str) -> str:
    """HTTP diagnostics can otherwise expose Bot API path/query credentials."""

    def replace(match):
        try:
            parsed = urlsplit(match.group())
            host = parsed.hostname or "configured"
            if ":" in host:
                host = f"[{host}]"
            target = host + (f":{parsed.port}" if parsed.port else "")
            path = re.sub(r"/bot[^/]+", "/bot[redacted]", parsed.path)
            path = re.sub(r"(/webhooks/[^/]+/)[^/]+", r"\1[redacted]", path)
            secret_keys = {"access_token", "token", "api_key", "key", "corpsecret", "secret", "authorization"}
            query = urlencode(
                [
                    (key, "[redacted]" if key.lower() in secret_keys else value)
                    for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                ]
            )
            return urlunsplit((parsed.scheme, target, path, query, ""))
        except ValueError:
            return "[redacted-url]"

    return re.sub(r"https?://[^\s\"'<>()]+", replace, message)


class _HTTPURLFilter(logging.Filter):
    def filter(self, record):
        record.msg = redact_http_urls(record.getMessage())
        record.args = ()
        return True


def install_http_url_redaction():
    logger = logging.getLogger("httpx")
    if not any(isinstance(item, _HTTPURLFilter) for item in logger.filters):
        logger.addFilter(_HTTPURLFilter())
