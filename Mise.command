#!/bin/bash
# Double-click to start Mise. Opens your browser; leave this window open while cooking.
cd "$(dirname "$0")"
if lsof -i :8137 -sTCP:LISTEN >/dev/null 2>&1; then
  open "http://localhost:8137"
  exit 0
fi
exec python3 server.py --lan --open
