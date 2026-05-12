"""`python -m memory_system` — start the standalone FastAPI service on port 8002."""

from __future__ import annotations


def main() -> None:
    import uvicorn

    uvicorn.run("memory_system.main:app", host="0.0.0.0", port=8002, reload=False)


if __name__ == "__main__":
    main()
