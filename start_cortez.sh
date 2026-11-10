#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

PORT=8000
TUNNEL_LOG=".cortez_tunnel.log"
rm -f "$TUNNEL_LOG"

echo "================================================================"
echo "  HOTEL CORTEZ (CortezOS) — Inicializando Servidor y Túnel"
echo "================================================================"

# 1. Levantar Uvicorn en segundo plano
./.venv/bin/uvicorn app:app --host 0.0.0.0 --port "$PORT" --log-level warning &
UVICORN_PID=$!

cleanup() {
  echo ""
  echo "[CortezOS] Cerrando puertas del Hotel Cortez..."
  kill "$UVICORN_PID" 2>/dev/null || true
  if [ -n "${CLOUDFLARED_PID:-}" ]; then
    kill "$CLOUDFLARED_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

sleep 1.2
echo "[OK] Servidor FastAPI activo en:"
echo "     • Proyector Local: http://localhost:${PORT}/panoptico"
echo "     • Check-In Local:  http://localhost:${PORT}/checkin"

# 2. Verificar e iniciar Cloudflare Quick Tunnel (Zero-Config, sin cuenta)
if command -v cloudflared >/dev/null 2>&1; then
  echo ""
  echo "[Cloudflare] Abriendo Quick Tunnel HTTPS/WSS hacia localhost:${PORT}..."
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
    echo "  🌐 TÚNEL PÚBLICO ACTIVO (4G / 5G / Wi-Fi):"
    echo "  • Proyector (abre este link para que el QR sea público):"
    echo "    ${PUBLIC_URL}/panoptico"
    echo ""
    echo "  • Link directo para celulares de la clase:"
    echo "    ${PUBLIC_URL}/checkin"
    echo "================================================================"
  else
    echo "[Aviso] cloudflared sigue negociando la URL. Revisa $TUNNEL_LOG"
  fi
else
  echo ""
  echo "[Aviso] No se encontró 'cloudflared' en el PATH."
  echo "        En Arch Linux instálalo con: sudo pacman -S cloudflared"
fi

echo ""
echo "Presiona Ctrl+C para detener CortezOS."
wait "$UVICORN_PID"
