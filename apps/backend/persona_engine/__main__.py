"""`python -m persona_engine` — start the standalone FastAPI service on port 8001."""

from __future__ import annotations


def main() -> None:
    import uvicorn

    uvicorn.run("persona_engine.main:app", host="0.0.0.0", port=8001, reload=False)


if __name__ == "__main__":
    main()
