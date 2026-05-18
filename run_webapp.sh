#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate
echo "Starting GenCon 2026 Preview at http://localhost:8000"
open http://localhost:8000 2>/dev/null || true
uvicorn webapp:app --reload --port 8000
