import pytest

from shared_runtime.log_safety import connection_target, redact_http_urls


@pytest.mark.parametrize(
    "value,expected",
    [
        (
            "postgresql+asyncpg://operator:secret@localhost:5432/private_db?token=hidden",
            "postgresql+asyncpg://localhost:5432",
        ),
        ("redis://:secret@[::1]:6379/2", "redis://[::1]:6379"),
        ("bolt://operator:secret@localhost:7687", "bolt://localhost:7687"),
        ("sqlite+aiosqlite:///private/files.db", "configured"),
        ("postgresql://operator:secret@localhost:invalid/db", "configured"),
        ("broken-secret", "configured"),
    ],
)
def test_connection_diagnostics_exclude_credentials_paths_and_query(value, expected):
    assert connection_target(value) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://api.telegram.org/bot123:private-credential/sendMessage",
        "https://discord.com/api/webhooks/123/private-credential?wait=true",
        "https://user:private-credential@host/path?access_token=private-credential&corpsecret=private-credential",
    ],
)
def test_http_url_diagnostics_redact_path_query_and_userinfo(url):
    assert "private-credential" not in redact_http_urls("HTTP Request: POST " + url)
