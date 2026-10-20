#!/usr/bin/env bash
# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
#
# studio-ctl.sh start|stop|restart|status|logs — run SenseAI Studio in the background.
# Reads STUDIO_ENV (default ~/senseai/studio.env, then ./.env). status also reports the viewer
# (VIEWER_PORT, default 8000) and research (RESEARCH_URL) so one command shows the whole box.
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${STUDIO_ENV:-$HOME/senseai/studio.env}"
[[ -f "$ENV_FILE" ]] || ENV_FILE="$HERE/.env"
if [[ -f "$ENV_FILE" ]]; then set -a; source "$ENV_FILE"; set +a; fi
PORT="${STUDIO_PORT:-8200}"
RUN_DIR="${STUDIO_DATA:-$HERE/data}"
PID_FILE="$RUN_DIR/studio.pid"
LOG_FILE="$RUN_DIR/studio.log"
mkdir -p "$RUN_DIR"

alive() { [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; }
auth() { [[ -n "${VIEWER_PASSWORD:-}" ]] && echo "-u senseai:$VIEWER_PASSWORD" || true; }

probe() { # name url
  if out=$(curl -fsS -m 5 $(auth) "$2" 2>/dev/null); then echo "$1: up ($2)"; echo "$out"; else echo "$1: down ($2)"; return 1; fi
}

case "${1:-status}" in
  start)
    if alive; then echo "studio already running (pid $(cat "$PID_FILE"))"; exit 0; fi
    cd "$HERE"
    nohup uv run senseai-studio serve --host "${STUDIO_HOST:-127.0.0.1}" --port "$PORT" >>"$LOG_FILE" 2>&1 &
    echo $! >"$PID_FILE"
    for _ in $(seq 50); do curl -fsS -m 1 "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1 && break; sleep 0.2; done
    echo "studio started on http://127.0.0.1:$PORT/studio (pid $(cat "$PID_FILE"), log $LOG_FILE)"
    ;;
  stop)
    if alive; then kill "$(cat "$PID_FILE")"; rm -f "$PID_FILE"; echo "studio stopped"; else echo "studio not running"; fi
    ;;
  restart) "$0" stop; "$0" start ;;
  logs) tail -n "${2:-100}" "$LOG_FILE" ;;
  status)
    rc=0
    if h=$(curl -fsS -m 10 $(auth) "http://127.0.0.1:$PORT/api/studio/health" 2>/dev/null); then
      echo "studio: up (http://127.0.0.1:$PORT/studio)"
      STUDIO_HEALTH="$h" python3 - <<'PY'
import json, os
h = json.loads(os.environ["STUDIO_HEALTH"])
print(f"  library: {h.get('clades')} clades, engine {h.get('engine')}")
for name, r in h.get("repos", {}).items():
    print(f"  {name:9} {'found' if r['found'] else 'missing':8} {(r.get('sha') or '')[:12]}")
b = h.get("bench", {})
print(f"  bench: {'found' if b.get('found') else 'not found'}, features {b.get('features')}")
print(f"  circuits: {'installed' if h.get('circuits') else 'not installed'}, research: {h.get('research')}")
PY
    else
      echo "studio: down (port $PORT)"; rc=1
    fi
    probe viewer "http://127.0.0.1:${VIEWER_PORT:-8000}/healthz" >/dev/null && echo "viewer: up" || echo "viewer: down (port ${VIEWER_PORT:-8000})"
    if [[ -n "${RESEARCH_URL:-}" ]]; then probe research "$RESEARCH_URL/api/research/health" >/dev/null && echo "research: up" || echo "research: down ($RESEARCH_URL)"; else echo "research: not configured"; fi
    exit $rc
    ;;
  *) echo "usage: $0 start|stop|restart|status|logs [n]"; exit 2 ;;
esac
