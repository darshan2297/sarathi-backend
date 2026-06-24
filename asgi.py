"""ASGI entrypoint for the Sarathi backend.

Exposes the FastAPI app as `application` (and `app`) for ASGI servers, and can run uvicorn directly
when executed as a script.

Run (any of these, from backend/ so backend/.env — the OpenRouter key — is loaded):
    poetry run python asgi.py                     # reads SARATHI_HOST / SARATHI_PORT / SARATHI_RELOAD
    poetry run uvicorn asgi:application --reload   # explicit uvicorn invocation

Env knobs (all optional; prefixed SARATHI_ to match app config):
    SARATHI_HOST    bind address   (default 127.0.0.1 — localhost only; set 0.0.0.0 to expose)
    SARATHI_PORT    port           (default 8088 — matches the frontend's .env.local WS target)
    SARATHI_RELOAD  auto-reload    (default true; set false/0 for production)
"""

from __future__ import annotations

import os

from app.main import app

# ASGI servers look for `application` by convention; keep `app` so `uvicorn app.main:app` still works.
application = app


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def main() -> None:
    import uvicorn

    host = os.getenv("SARATHI_HOST", "127.0.0.1")
    port = int(os.getenv("SARATHI_PORT", "8088"))
    reload = _as_bool(os.getenv("SARATHI_RELOAD", "true"))

    # Pass the import string (not the app object) so --reload can re-import the module cleanly.
    uvicorn.run("asgi:application", host=host, port=port, reload=reload)


if __name__ == "__main__":
    main()
