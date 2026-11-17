import asyncio
import json
import random
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Pixels to "Cortez Hotel corridor meters" (immersive mobile scale)
PIXELS_PER_METER = 280.0

ESCAPE_METHOD_LABELS = {
    "button_click": "Physical Evasion (Check-Out Button)",
    "tab_hidden": "Withdrawal Syndrome (Sally / App Switch or Screen Lock)",
    "back_button": "Escape Attempt (Back Button Hijack)",
    "modal_trap": "Psychological Submission (March Clause)",
}

BOT_PROFILES = [
    ("Diego", "Doomscrolling", "Android"),
    ("Valentina", "Vanity", "iOS"),
    ("Matías", "Procrastination", "Android"),
    ("Camila", "Stalking", "iOS"),
    ("Sebastián", "Doomscrolling", "Android"),
    ("Francisca", "Vanity", "iOS"),
    ("Nicolás", "Procrastination", "Android"),
    ("Javiera", "Stalking", "iOS"),
    ("Benjamín", "Doomscrolling", "Android"),
    ("Antonia", "Vanity", "iOS"),
    ("Tomás", "Procrastination", "Android"),
    ("Catalina", "Stalking", "iOS"),
    ("Lucas", "Doomscrolling", "Android"),
    ("Fernanda", "Procrastination", "iOS"),
    ("Ignacio", "Stalking", "Android"),
]


class CortezState:
    """Singleton en RAM que gestiona huéspedes, telemetría y canales WebSocket."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.guests: dict[str, dict[str, Any]] = {}
        self.guest_sockets: dict[str, WebSocket] = {}
        self.panoptico_sockets: set[WebSocket] = set()
        self.next_room: int = 1
        self.events_log: deque[dict[str, Any]] = deque(maxlen=60)
        self.total_escape_attempts: int = 0
        self.bots_active: bool = False
        self._bot_task: asyncio.Task[None] | None = None
        self.created_at: float = time.time()

    def _now_str(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def add_log(
        self,
        message: str,
        severity: str = "info",
        room: int | None = None,
        alias: str | None = None,
        pecado: str | None = None,
    ) -> dict[str, Any]:
        entry = {
            "id": f"{int(time.time() * 1000)}-{random.randint(100, 999)}",
            "time": self._now_str(),
            "room": room,
            "alias": alias,
            "pecado": pecado,
            "message": message,
            "severity": severity,  # "checkin" | "escape" | "offline" | "info"
        }
        self.events_log.appendleft(entry)
        return entry

    async def register_or_reconnect_guest(
        self,
        client_id: str,
        alias: str,
        pecado_digital: str,
        os_name: str,
        is_bot: bool = False,
    ) -> tuple[dict[str, Any], bool]:
        """Registra un nuevo huésped o reconecta uno existente sin colisiones (TC-01)."""
        async with self._lock:
            now = time.time()
            is_new = client_id not in self.guests
            if is_new:
                room_num = self.next_room
                self.next_room += 1
                guest = {
                    "client_id": client_id,
                    "room": room_num,
                    "alias": alias.strip()[:24] or f"Guest #{room_num}",
                    "pecado_digital": pecado_digital or "Doomscrolling",
                    "os": os_name or "Mobile",
                    "status": "IN THE LABYRINTH",
                    "alert_state": "normal",  # "normal" | "escape" | "offline"
                    "escape_until": 0.0,
                    "last_escape_method": "",
                    "pixels": 0,
                    "meters": 0.0,
                    "escape_attempts": 0,
                    "connected_at": now,
                    "last_seen": now,
                    "accumulated_seconds": 0.0,
                    "online": True,
                    "is_bot": is_bot,
                }
                self.guests[client_id] = guest
                self.add_log(
                    f"Check-In signed: Room {room_num} assigned to {guest['alias']} [{guest['os']}] — Sin: {guest['pecado_digital']}",
                    severity="checkin",
                    room=room_num,
                    alias=guest["alias"],
                    pecado=guest["pecado_digital"],
                )
            else:
                guest = self.guests[client_id]
                if alias:
                    guest["alias"] = alias.strip()[:24]
                if pecado_digital:
                    guest["pecado_digital"] = pecado_digital
                if os_name:
                    guest["os"] = os_name
                guest["online"] = True
                guest["last_seen"] = now
                guest["status"] = "RECAPTURED IN THE HOTEL"
                guest["alert_state"] = "normal"
                self.add_log(
                    f"Guest {guest['alias']} (Room {guest['room']}) re-entered the algorithmic trance.",
                    severity="info",
                    room=guest["room"],
                    alias=guest["alias"],
                    pecado=guest["pecado_digital"],
                )
            return guest, is_new

    async def record_scroll(self, client_id: str, delta_pixels: int) -> None:
        if delta_pixels <= 0:
            return
        async with self._lock:
            guest = self.guests.get(client_id)
            if not guest:
                return
            now = time.time()
            guest["pixels"] += int(delta_pixels)
            guest["meters"] = round(guest["pixels"] / PIXELS_PER_METER, 2)
            guest["last_seen"] = now
            guest["online"] = True
            if now >= guest["escape_until"]:
                guest["alert_state"] = "normal"
                guest["status"] = "SCROLLING IN THE LABYRINTH"

    async def record_escape_attempt(self, client_id: str, method: str) -> dict[str, Any] | None:
        async with self._lock:
            guest = self.guests.get(client_id)
            if not guest:
                return None
            now = time.time()
            guest["escape_attempts"] += 1
            self.total_escape_attempts += 1
            guest["last_escape_method"] = method
            guest["last_seen"] = now
            guest["escape_until"] = now + 5.5  # Red blink on projector for 5.5s
            guest["alert_state"] = "escape"

            if method == "tab_hidden":
                guest["status"] = "ESCAPE ATTEMPT (SALLY)"
            elif method == "back_button":
                guest["status"] = "ESCAPE ATTEMPT (BACK BUTTON)"
            else:
                guest["status"] = "ESCAPE ATTEMPT (CHECK-OUT)"

            label = ESCAPE_METHOD_LABELS.get(method, f"Anomaly ({method})")
            log_entry = self.add_log(
                f"SALLY ALERT — Room {guest['room']} ({guest['alias']}): {label} [Attempt #{guest['escape_attempts']}]",
                severity="escape",
                room=guest["room"],
                alias=guest["alias"],
                pecado=guest["pecado_digital"],
            )
            return log_entry

    async def mark_disconnected(self, client_id: str) -> None:
        """Handles abrupt disconnection without breaking broadcast (TC-03)."""
        async with self._lock:
            self.guest_sockets.pop(client_id, None)
            guest = self.guests.get(client_id)
            if not guest:
                return
            guest["online"] = False
            guest["alert_state"] = "offline"
            guest["status"] = "Trapped in the Hotel (Offline)"
            self.add_log(
                f"Signal lost in Room {guest['room']} ({guest['alias']}) → Status: Trapped in the Hotel (Offline)",
                severity="offline",
                room=guest["room"],
                alias=guest["alias"],
                pecado=guest["pecado_digital"],
            )

    def tick_attention(self, dt: float) -> None:
        """Updates stolen attention counters and clears expired alerts."""
        now = time.time()
        for guest in self.guests.values():
            if guest["online"]:
                guest["accumulated_seconds"] += dt
                if guest["alert_state"] == "escape" and now >= guest["escape_until"]:
                    guest["alert_state"] = "normal"
                    guest["status"] = "IN THE LABYRINTH"

    def build_snapshot(self, event_trigger: dict[str, Any] | None = None) -> dict[str, Any]:
        guests_list = sorted(self.guests.values(), key=lambda g: g["room"])
        total_seconds = int(round(sum(g["accumulated_seconds"] for g in guests_list)))
        total_meters = round(sum(g["meters"] for g in guests_list), 2)
        total_pixels = sum(g["pixels"] for g in guests_list)
        online_count = sum(1 for g in guests_list if g["online"])
        escaping_count = sum(1 for g in guests_list if g["alert_state"] == "escape")

        return {
            "type": "snapshot",
            "timestamp": time.time(),
            "metrics": {
                "indice_condesa_seconds": total_seconds,
                "pasillos_march_meters": total_meters,
                "total_pixels": total_pixels,
                "total_guests": len(guests_list),
                "online_guests": online_count,
                "escaping_guests": escaping_count,
                "total_escape_attempts": self.total_escape_attempts,
                "bots_active": self.bots_active,
            },
            "guests": [
                {
                    "client_id": g["client_id"],
                    "room": g["room"],
                    "alias": g["alias"],
                    "pecado_digital": g["pecado_digital"],
                    "os": g["os"],
                    "status": g["status"],
                    "alert_state": g["alert_state"],
                    "last_escape_method": g["last_escape_method"],
                    "pixels": g["pixels"],
                    "meters": g["meters"],
                    "escape_attempts": g["escape_attempts"],
                    "attention_seconds": int(round(g["accumulated_seconds"])),
                    "online": g["online"],
                    "is_bot": g["is_bot"],
                }
                for g in guests_list
            ],
            "logs": list(self.events_log)[:25],
            "trigger": event_trigger,
        }

    async def broadcast_panoptico(self, event_trigger: dict[str, Any] | None = None) -> None:
        if not self.panoptico_sockets:
            return
        payload = json.dumps(self.build_snapshot(event_trigger=event_trigger))
        stale_sockets: list[WebSocket] = []
        for ws in list(self.panoptico_sockets):
            try:
                await ws.send_text(payload)
            except Exception:
                stale_sockets.append(ws)
        for ws in stale_sockets:
            self.panoptico_sockets.discard(ws)

    async def toggle_bots_simulation(self) -> bool:
        """Activa o desactiva la inyección de 15 huéspedes simulados (TC-04 Tecla B / S)."""
        if self.bots_active:
            self.bots_active = False
            if self._bot_task and not self._bot_task.done():
                self._bot_task.cancel()
            async with self._lock:
                bot_ids = [cid for cid, g in self.guests.items() if g.get("is_bot")]
                for cid in bot_ids:
                    self.guests[cid]["online"] = False
                    self.guests[cid]["alert_state"] = "offline"
                    self.guests[cid]["status"] = "Trapped in the Hotel (Offline)"
                self.add_log(
                    "Simulation Mode (Contingency) paused by the operator.",
                    severity="info",
                )
            await self.broadcast_panoptico()
            return False

        self.bots_active = True
        self.add_log(
            "CONTINGENCY PROTOCOL ACTIVATED: Injecting 15 simulated souls into the Hotel Cortez...",
            severity="checkin",
        )
        self._bot_task = asyncio.create_task(self._run_bots_loop())
        return True

    async def _run_bots_loop(self) -> None:
        try:
            # 1. Burst inicial progresivo pero veloz (<1s para los primeros, resto escalonado)
            for idx, (alias, pecado, os_name) in enumerate(BOT_PROFILES, start=1):
                if not self.bots_active:
                    return
                bot_id = f"bot-cortez-{idx:02d}"
                guest, _ = await self.register_or_reconnect_guest(
                    client_id=bot_id,
                    alias=alias,
                    pecado_digital=pecado,
                    os_name=os_name,
                    is_bot=True,
                )
                await self.broadcast_panoptico(
                    event_trigger={
                        "kind": "new_guest",
                        "room": guest["room"],
                        "alias": guest["alias"],
                    }
                )
                await asyncio.sleep(0.08 if idx <= 5 else 0.18)

            # 2. Actividad orgánica continua (scroll + intentos de fuga)
            while self.bots_active:
                await asyncio.sleep(0.6)
                bot_ids = [
                    cid for cid, g in self.guests.items() if g.get("is_bot") and g.get("online")
                ]
                if not bot_ids:
                    continue

                # 4 a 8 bots hacen scroll en cada pulso
                scrollers = random.sample(bot_ids, k=min(len(bot_ids), random.randint(4, 8)))
                for cid in scrollers:
                    await self.record_scroll(cid, random.randint(140, 680))

                # Probabilidad de que un bot intente escapar (dispara alerta roja + log de Sally)
                if random.random() < 0.32:
                    escaper_id = random.choice(bot_ids)
                    method = random.choices(
                        ["tab_hidden", "button_click", "back_button"],
                        weights=[0.45, 0.35, 0.20],
                        k=1,
                    )[0]
                    await self.record_escape_attempt(escaper_id, method)
                    guest = self.guests[escaper_id]
                    await self.broadcast_panoptico(
                        event_trigger={
                            "kind": "escape_attempt",
                            "room": guest["room"],
                            "alias": guest["alias"],
                            "method": method,
                        }
                    )
        except asyncio.CancelledError:
            return


state = CortezState()


async def broadcast_ticker_loop() -> None:
    """Bucle central a 10Hz (cada 100ms) que actualiza tiempo de atención y transmite al proyector."""
    last_tick = time.time()
    while True:
        await asyncio.sleep(0.1)
        now = time.time()
        dt = max(0.0, min(now - last_tick, 1.0))
        last_tick = now
        state.tick_attention(dt)
        await state.broadcast_panoptico()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ticker_task = asyncio.create_task(broadcast_ticker_loop())
    try:
        yield
    finally:
        ticker_task.cancel()


app = FastAPI(
    title="CortezOS — Algorithmic Retention Panopticon",
    description="Reactive In-Memory Monolithic Architecture for AHS: Hotel",
    version="1.0.0",
    lifespan=lifespan,
)


SALA_TEMPLATE_MAP = {
    "doomscrolling": "salas/doomscrolling.html",
    "vanidad": "salas/vanidad.html",
    "vanity": "salas/vanidad.html",
    "stalking": "salas/stalking.html",
    "procrastinacion": "salas/procrastinacion.html",
    "procrastinación": "salas/procrastinacion.html",
    "procrastination": "salas/procrastinacion.html",
}

SALAS_ROUTER_JS = """
(function() {
  function normalizePecado(raw) {
    const v = (raw || "").toLowerCase().normalize("NFD").replace(/[\\u0300-\\u036f]/g, "");
    if (v.includes("vanid") || v.includes("vanit")) return "vanidad";
    if (v.includes("stalk")) return "stalking";
    if (v.includes("procrast")) return "procrastinacion";
    return "doomscrolling";
  }
  const form = document.getElementById("checkin-form");
  if (!form) return;
  form.addEventListener("submit", function(e) {
    e.preventDefault();
    e.stopImmediatePropagation();
    const aliasEl = document.getElementById("alias-input");
    const pecadoEl = document.getElementById("pecado-select");
    const alias = (aliasEl && aliasEl.value.trim()) ? aliasEl.value.trim() : "Guest";
    const pecadoRaw = (pecadoEl && pecadoEl.value) ? pecadoEl.value : "Doomscrolling";
    sessionStorage.setItem("cortez_alias", alias);
    sessionStorage.setItem("cortez_pecado", pecadoRaw);
    const slug = normalizePecado(pecadoRaw);
    window.location.href = "/sala/" + slug;
  }, true);
})();
"""

SALA_CORE_JS = """
(function() {
  function detectMobileOS() {
    const ua = navigator.userAgent || navigator.vendor || window.opera;
    if (/android/i.test(ua)) return "Android";
    if (/iPad|iPhone|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)) return "iOS";
    if (/Linux/i.test(ua)) return "Linux";
    if (/Macintosh|Mac OS X/i.test(ua)) return "macOS";
    if (/Windows/i.test(ua)) return "Windows";
    return "Mobile";
  }

  let clientId = sessionStorage.getItem("cortez_client_id");
  if (!clientId) {
    clientId = "guest-" + Math.random().toString(36).substring(2, 9) + "-" + Date.now().toString(36);
    sessionStorage.setItem("cortez_client_id", clientId);
  }

  let ws = null;
  let pendingPixels = 0;
  let totalPixelsLocal = Number(sessionStorage.getItem("cortez_pixels") || 0);
  let lastScrollY = window.scrollY;

  function updateMetersHUD() {
    const el = document.getElementById("hud-meters");
    if (el) el.textContent = (totalPixelsLocal / 280.0).toFixed(2);
  }

  function sendPayload(payload) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
    }
  }

  window.addCortezSyntheticPixels = function(px) {
    pendingPixels += px;
    totalPixelsLocal += px;
    sessionStorage.setItem("cortez_pixels", String(totalPixelsLocal));
    updateMetersHUD();
  };

  function showEscapeToast(msg) {
    const toast = document.getElementById("escape-toast");
    const text = document.getElementById("escape-toast-msg");
    if (!toast || !text) return;
    text.textContent = msg;
    toast.classList.remove("hidden");
    clearTimeout(window._cortezToastTimer);
    window._cortezToastTimer = setTimeout(() => toast.classList.add("hidden"), 3600);
  }

  window.initCortezSala = function(defaultPecado) {
    const alias = sessionStorage.getItem("cortez_alias") || "Guest";
    const pecado = sessionStorage.getItem("cortez_pecado") || defaultPecado;
    const os = detectMobileOS();
    updateMetersHUD();

    function connectWS() {
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      ws = new WebSocket(proto + "//" + window.location.host + "/ws/huesped/" + encodeURIComponent(clientId));
      ws.onopen = function() {
        ws.send(JSON.stringify({ type: "checkin", alias: alias, pecado_digital: pecado, os: os }));
      };
      ws.onmessage = function(ev) {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === "checkin_ack") {
            const rEl = document.getElementById("hud-room");
            const gEl = document.getElementById("hud-guest");
            if (rEl) rEl.textContent = "ROOM " + msg.room;
            if (gEl) gEl.textContent = msg.alias + " • " + msg.pecado_digital;
          }
        } catch (e) {}
      };
      ws.onclose = function() {
        setTimeout(connectWS, 1500);
      };
    }

    connectWS();

    setInterval(function() {
      if (pendingPixels <= 0) return;
      const toSend = Math.round(pendingPixels);
      pendingPixels = 0;
      sendPayload({ type: "scroll", pixels: toSend });
    }, 1000);

    window.addEventListener("scroll", function() {
      const currentY = window.scrollY;
      const delta = Math.abs(currentY - lastScrollY);
      lastScrollY = currentY;
      if (delta > 0 && delta < 2500) {
        window.addCortezSyntheticPixels(delta);
      }
    }, { passive: true });

    // Dark Pattern 1: Botón Check-Out Evasivo (2 intentos) + Modal (3er intento)
    let attempts = 0;
    let lastEvade = 0;
    const btn = document.getElementById("checkout-btn");
    const modal = document.getElementById("psych-modal");
    const stayBtn = document.getElementById("stay-btn");

    if (btn) {
      function evade(e) {
        const now = Date.now();
        if (now - lastEvade < 280) { e.preventDefault(); return; }
        lastEvade = now;
        e.preventDefault();
        e.stopPropagation();
        attempts++;
        sendPayload({ type: "escape_attempt", method: "button_click" });
        if (attempts <= 2) {
          const rx = (Math.random() > 0.5 ? 1 : -1) * (45 + Math.random() * 95);
          const ry = -(70 + Math.random() * 240);
          const rot = (Math.random() - 0.5) * 14;
          btn.style.transform = "translate(" + rx.toFixed(0) + "px, " + ry.toFixed(0) + "px) rotate(" + rot.toFixed(1) + "deg)";
          showEscapeToast("Physical evasion #" + attempts + ": Check-Out attempt projected to the classroom.");
        } else {
          btn.style.transform = "translate(0px, 0px) rotate(0deg)";
          if (modal) modal.classList.remove("hidden");
          attempts = 0;
        }
      }
      btn.addEventListener("touchstart", evade, { passive: false });
      btn.addEventListener("mouseover", evade);
      btn.addEventListener("click", evade);
    }

    if (stayBtn && modal) {
      stayBtn.addEventListener("click", function() { modal.classList.add("hidden"); });
    }

    // Dark Pattern 2: Back Button Hijack (History API)
    history.pushState({ cortezTrap: true }, "", window.location.href);
    history.pushState({ cortezTrap: true }, "", window.location.href);
    window.addEventListener("popstate", function() {
      history.pushState({ cortezTrap: true }, "", window.location.href);
      sendPayload({ type: "escape_attempt", method: "back_button" });
      showEscapeToast("Escape Attempt! The 'Back' button was intercepted by the Hotel Cortez.");
    });

    // Dark Pattern 3: Page Visibility API (Sally)
    document.addEventListener("visibilitychange", function() {
      if (document.hidden === true) {
        sendPayload({ type: "escape_attempt", method: "tab_hidden" });
      } else {
        showEscapeToast("Sally detected your app switch or screen lock.");
      }
    });
  };
})();
"""


@app.get("/", include_in_schema=False)
async def root_redirect() -> RedirectResponse:
    return RedirectResponse(url="/checkin")


@app.get("/checkin", response_class=HTMLResponse)
async def get_checkin(request: Request) -> HTMLResponse:
    """Sirve checkin.html sin modificar el archivo en disco, inyectando el router de salas."""
    raw_html = (BASE_DIR / "templates" / "checkin.html").read_text(encoding="utf-8")
    injected = raw_html.replace(
        "</body>",
        '<script src="/cortez-salas-router.js"></script></body>',
    )
    return HTMLResponse(content=injected)


@app.get("/sala/{pecado}", response_class=HTMLResponse)
async def get_sala(request: Request, pecado: str) -> HTMLResponse:
    template_name = SALA_TEMPLATE_MAP.get(pecado.lower().strip(), "salas/doomscrolling.html")
    return templates.TemplateResponse(request=request, name=template_name)


@app.get("/api/huespedes-espiados", response_class=JSONResponse)
async def get_spied_guests() -> JSONResponse:
    snap = state.build_snapshot()
    return JSONResponse(content={"guests": snap["guests"]})


@app.get("/cortez-salas-router.js")
async def get_salas_router_js() -> Response:
    return Response(content=SALAS_ROUTER_JS, media_type="application/javascript")


@app.get("/cortez-sala-core.js")
async def get_sala_core_js() -> Response:
    return Response(content=SALA_CORE_JS, media_type="application/javascript")


@app.get("/panoptico", response_class=HTMLResponse)
async def get_panoptico(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="panoptico.html")


@app.websocket("/ws/huesped/{client_id}")
async def ws_huesped(websocket: WebSocket, client_id: str) -> None:
    await websocket.accept()
    state.guest_sockets[client_id] = websocket
    try:
        while True:
            raw_data = await websocket.receive_text()
            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type")

            if msg_type == "checkin":
                guest, is_new = await state.register_or_reconnect_guest(
                    client_id=client_id,
                    alias=str(data.get("alias", "Anonymous Guest")),
                    pecado_digital=str(data.get("pecado_digital", "Doomscrolling")),
                    os_name=str(data.get("os", "Mobile")),
                    is_bot=bool(data.get("is_bot", False)),
                )
                # Confirmar número de habitación al teléfono
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "checkin_ack",
                            "room": guest["room"],
                            "alias": guest["alias"],
                            "pecado_digital": guest["pecado_digital"],
                        }
                    )
                )
                await state.broadcast_panoptico(
                    event_trigger={
                        "kind": "new_guest" if is_new else "reconnect_guest",
                        "room": guest["room"],
                        "alias": guest["alias"],
                    }
                )

            elif msg_type == "scroll":
                pixels = int(data.get("pixels", 0))
                await state.record_scroll(client_id, pixels)

            elif msg_type == "escape_attempt":
                method = str(data.get("method", "button_click"))
                await state.record_escape_attempt(client_id, method)
                guest = state.guests.get(client_id)
                if guest:
                    await state.broadcast_panoptico(
                        event_trigger={
                            "kind": "escape_attempt",
                            "room": guest["room"],
                            "alias": guest["alias"],
                            "method": method,
                        }
                    )

            elif msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        await state.mark_disconnected(client_id)
        await state.broadcast_panoptico()
    except Exception:
        await state.mark_disconnected(client_id)
        await state.broadcast_panoptico()


@app.websocket("/ws/panoptico")
async def ws_panoptico(websocket: WebSocket) -> None:
    await websocket.accept()
    state.panoptico_sockets.add(websocket)
    # Enviar estado inicial inmediatamente al abrir el proyector
    try:
        await websocket.send_text(json.dumps(state.build_snapshot()))
        while True:
            raw_msg = await websocket.receive_text()
            try:
                cmd = json.loads(raw_msg)
            except json.JSONDecodeError:
                continue

            action = cmd.get("action")
            if action == "toggle_bots":
                await state.toggle_bots_simulation()
            elif action == "reset_hotel":
                async with state._lock:
                    state.guests.clear()
                    state.events_log.clear()
                    state.next_room = 1
                    state.total_escape_attempts = 0
                    state.add_log("Hotel Cortez registry reset for new session.", severity="info")
                await state.broadcast_panoptico()
    except WebSocketDisconnect:
        state.panoptico_sockets.discard(websocket)
    except Exception:
        state.panoptico_sockets.discard(websocket)
