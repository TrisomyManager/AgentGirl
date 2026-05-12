"""`python -m voice_layer` — start the standalone FastAPI service on port 8003."""

from __future__ import annotations


def main() -> None:
    import uvicorn

    uvicorn.run("voice_layer.main:app", host="0.0.0.0", port=8003, reload=False)


if __name__ == "__main__":
    main()
