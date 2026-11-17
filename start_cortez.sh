#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PORT="${PORT:-8000}"
TUNNEL_LOG=".cortez_tunnel.log"
rm -f "$TUNNEL_LOG"

if [ -x "./.venv/bin/uvicorn" ]; then
  UVICORN_BIN="./.venv/bin/uvicorn"
elif [ -x "./venv/bin/uvicorn" ]; then
  UVICORN_BIN="./venv/bin/uvicorn"
elif command -v uvicorn >/dev/null 2>&1; then
  UVICORN_BIN="$(command -v uvicorn)"
else
  echo "[Error] 'uvicorn' not found. Create a virtual environment and install requirements:"
  echo "        python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt"
  exit 1
fi

echo "================================================================"
echo "  HOTEL CORTEZ (CortezOS) — Starting Server & Tunnel"
echo "================================================================"

# 1. Start Uvicorn in the background
"$UVICORN_BIN" app:app --host 0.0.0.0 --port "$PORT" --log-level warning &
UVICORN_PID=$!

cleanup() {
  echo ""
  echo "[CortezOS] Closing Hotel Cortez doors..."
  kill "$UVICORN_PID" 2>/dev/null || true
  if [ -n "${CLOUDFLARED_PID:-}" ]; then
    kill "$CLOUDFLARED_PID" 2>/dev/null || true
  fi
  rm -f "$TUNNEL_LOG"
}
trap cleanup EXIT INT TERM

sleep 1.2
echo "[OK] FastAPI server active at:"
echo "     • Projector (Panopticon): http://localhost:${PORT}/panoptico"
echo "     • Guest Check-In:         http://localhost:${PORT}/checkin"
echo "     • Fullscreen QR:          http://localhost:${PORT}/qr"

# 2. Check and start Cloudflare Quick Tunnel (zero-config, no account needed)
if command -v cloudflared >/dev/null 2>&1; then
  echo ""
  echo "[Cloudflare] Opening HTTPS/WSS Quick Tunnel to localhost:${PORT}..."
  cloudflared tunnel --url "http://localhost:${PORT}" --no-autoupdate > "$TUNNEL_LOG" 2>&1 &
  CLOUDFLARED_PID=$!

  PUBLIC_URL=""
  for _ in $(seq 1 30); do
    if grep -qE "https://[a-zA-Z0-9-]+\\.trycloudflare\\.com" "$TUNNEL_LOG" 2>/dev/null; then
      PUBLIC_URL=$(grep -oE "https://[a-zA-Z0-9-]+\\.trycloudflare\\.com" "$TUNNEL_LOG" | head -n 1)
      break
    fi
    sleep 0.5
  done

  if [ -n "$PUBLIC_URL" ]; then
    echo "================================================================"
    echo "  PUBLIC TUNNEL ACTIVE (4G / 5G / Wi-Fi):"
    echo "  • Projector (open this link so the QR code uses the public URL):"
    echo "    ${PUBLIC_URL}/panoptico"
    echo ""
    echo "  • Direct mobile check-in link:"
    echo "    ${PUBLIC_URL}/checkin"
    echo "================================================================"
  else
    echo "[Notice] cloudflared is still negotiating the URL. Check $TUNNEL_LOG"
  fi
else
  echo ""
  echo "[Notice] 'cloudflared' not found in PATH."
  echo "         Install it to expose a public HTTPS/WSS URL for mobile devices:"
  echo "         https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
fi

echo ""
echo "Press Ctrl+C to stop CortezOS."
wait "$UVICORN_PID"
