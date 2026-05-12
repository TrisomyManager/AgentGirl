"""`python -m action_executor` — start the standalone FastAPI service on port 8007."""

from __future__ import annotations


def main() -> None:
    import uvicorn

    uvicorn.run("action_executor.main:app", host="0.0.0.0", port=8007, reload=False)


if __name__ == "__main__":
    main()
