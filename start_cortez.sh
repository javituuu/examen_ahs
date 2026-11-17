#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

PORT=8000
TUNNEL_LOG=".cortez_tunnel.log"
rm -f "$TUNNEL_LOG"

echo "================================================================"
echo "  HOTEL CORTEZ (CortezOS) — Initializing Server and Tunnel"
echo "================================================================"

# 1. Start Uvicorn in background
./.venv/bin/uvicorn app:app --host 0.0.0.0 --port "$PORT" --log-level warning &
UVICORN_PID=$!

cleanup() {
  echo ""
  echo "[CortezOS] Closing the doors of Hotel Cortez..."
  kill "$UVICORN_PID" 2>/dev/null || true
  if [ -n "${CLOUDFLARED_PID:-}" ]; then
    kill "$CLOUDFLARED_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

sleep 1.2
echo "[OK] FastAPI server active at:"
echo "     • Local Projector: http://localhost:${PORT}/panoptico"
echo "     • Local Check-In:  http://localhost:${PORT}/checkin"

# 2. Verify and start Cloudflare Quick Tunnel (Zero-Config, no account)
if command -v cloudflared >/dev/null 2>&1; then
  echo ""
  echo "[Cloudflare] Opening Quick Tunnel HTTPS/WSS to localhost:${PORT}..."
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
    echo "  🌐 PUBLIC TUNNEL ACTIVE (4G / 5G / Wi-Fi):"
    echo "  • Projector (open this link so the QR points to public URL):"
    echo "    ${PUBLIC_URL}/panoptico"
    echo ""
    echo "  • Direct link for classroom phones:"
    echo "    ${PUBLIC_URL}/checkin"
    echo "================================================================"
  else
    echo "[Notice] cloudflared is still negotiating the URL. Check $TUNNEL_LOG"
  fi
else
  echo ""
  echo "[Notice] 'cloudflared' was not found in PATH."
  echo "         On Arch Linux install it with: sudo pacman -S cloudflared"
fi

echo ""
echo "Press Ctrl+C to stop CortezOS."
wait "$UVICORN_PID"
