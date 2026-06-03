#!/usr/bin/env bash
# Container entrypoint. Honours HOST / PORT env vars (defaults set in
# the Dockerfile). Runs the FastAPI app on port 8000 by default.
set -euo pipefail

exec python run.py
