"""Hackathon entry-point.

Boots the FastAPI application on port 8000 (per the non-negotiable
constraint) with a single ``python run.py`` command. No manual setup
required: the bundled mortgage sample dataset is loaded automatically by
``POST /run``.

Environment:
    COMPASS_API_KEY    Compass API (Core42) key. Set via real OS env var,
                       `.env`, or `.env.local` (see `.env.example`).

Usage:
    python run.py                         # serve on 0.0.0.0:8000
    curl -X POST http://localhost:8000/run

Endpoints:
    GET  /                           Health check
    POST /run                        End-to-end run (data + pipeline)
    GET  /docs                       Interactive Swagger UI
    POST /api/v1/pipeline/run        Same as /run with extra options
    GET  /api/v1/dq-scores/results   Latest scores for a (db, snapshot)
    GET  /api/v1/dq-scores/trend     Cross-snapshot trend (GPT-5.1)

This module never imports the FastAPI app at top level so unit tools that
``import run`` don't accidentally bind a port.
"""

from __future__ import annotations

import os


def main() -> None:
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=False,
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    main()
