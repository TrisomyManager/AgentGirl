"""`python -m shared_runtime` — print runtime configuration snapshot."""

from __future__ import annotations

from shared_runtime import get_settings, is_lite_mode


def main() -> None:
    s = get_settings()
    print("shared_runtime snapshot:")
    print(f"  app_name      = {getattr(s, 'app_name', '<unset>')}")
    print(f"  lite_mode     = {is_lite_mode()}")
    print(f"  llm_provider  = {getattr(s, 'llm_provider', '<unset>')}")
    print(f"  llm_model     = {getattr(s, 'llm_model', '<unset>')}")
    print(f"  postgres_dsn  = {getattr(s, 'postgres_dsn', '<unset>')}")
    print(f"  redis_url     = {getattr(s, 'redis_url', '<unset>')}")


if __name__ == "__main__":
    main()
