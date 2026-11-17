# CortezOS — The Panopticon of Algorithmic Retention

An interactive, real-time live classroom/audience experience inspired by ***American Horror Story: Hotel***, exploring **surveillance capitalism**, **attention extraction**, and **deceptive UI dark patterns**.

Participants scan a QR code on their phones to "check in" to the **Hotel Cortez**, choose a *Digital Deadly Sin*, and enter an endless algorithmic hallway while a live **Panopticon dashboard** on the projector tracks every pixel scrolled, every second of attention captured, and every attempt to leave.

---

## How It Works

### 1. Mobile Guest Check-In (`/checkin`)
- **Art Deco Guest Registry**: Participants enter an alias, select one of four *Digital Deadly Sins*, and see their detected OS (`Android`, `iOS`, `macOS`, `Windows`, `Linux`).
- **Room Assignment**: Each participant is assigned a sequential room (`Room 1 / Suite 64`, `Room 2`, etc.) and connected over WebSockets (`/ws/huesped/{client_id}`) with automatic reconnection and iOS Safari keep-alive pings.

### 2. Four Interactive "Hotel Wings" (`/sala/{pecado}`)
After signing the registry, guests are routed to a tailored mobile experience:
- **Doomscrolling** (`doomscrolling.html` — *March's Labyrinth*): Endless algorithmic corridor scroll feed.
- **Pride / Vanidad** (`vanidad.html` — *The Countess' Mirror*): Interactive vanity engagement loop with synthetic scroll telemetry.
- **Stalking** (`stalking.html` — *March's Peepholes*): Interactive surveillance peephole cards.
- **Procrastination** (`procrastinacion.html` — *Sally's Needle*): Endless distraction feed.

### 3. Built-In Dark Patterns & Escape Telemetry
Every wing runs `SALA_CORE_JS` (served from `/cortez-sala-core.js`), which instruments user behavior and sends real-time events to the projector:
- **Evasive Check-Out Button (`button_click`)**: The exit button physically dodges the user's first two taps/hovers before revealing a guilt-trip modal (*Clause No. 64*).
- **Bait Exit Modal (`modal_trap`)**: Selecting the secondary "check out and exit anyway" link triggers a rejected-exit trap.
- **Back Button Hijacking (`back_button`)**: Intercepts History API `popstate` events and re-arms the trap on user interaction.
- **App-Switch & Screen-Lock Detection (`tab_hidden`)**: Monitors `visibilitychange` and `pagehide` events (including iOS Safari `pageshow` recovery) to alert the room when a guest tries to leave.

### 4. Projector Panopticon (`/panoptico`)
A live **10 Hz** WebSocket command center (`/ws/panoptico`) designed for a classroom or presentation projector:
- **Global Telemetry Counters**:
  - *Índice La Condesa*: Total accumulated attention seconds across connected guests.
  - *Pasillos de March*: Total distance scrolled in meters (`280 px = 1 m`) and raw pixels.
  - *Sally's Alerts*: Total intercepted escape attempts.
- **Live Room Matrix**: Per-guest cards showing room number, OS badge, chosen sin, distance scrolled, escape count, and state (gold when active, flashing crimson on escape alert, dimmed when offline).
- **Dopamine Extraction Curve**: Real-time dual-axis `Chart.js` graph comparing scrolled meters vs. escape anomalies.
- **Surveillance Terminal (Sally Log)**: Live color-coded event stream.
- **Synthesized Audio (Web Audio API)**: Reception desk bell on check-in and alarm buzzer on escape attempts (toggleable via UI).
- **Keyboard Shortcuts**:
  - `Q`: Toggle the Check-In QR modal (or open `/qr` for a dedicated fullscreen QR view).
  - `B` or `S`: Toggle **Contingency Mode** (injects 15 simulated bot guests with organic scroll and escape behavior; includes a client-side fallback if the backend WebSocket is unreachable).
  - `Esc`: Close the QR modal.

---

## Tech Stack

- **Backend**: [FastAPI](https://fastapi.tiangolo.com/), [Uvicorn](https://www.uvicorn.org/), WebSockets, Jinja2
- **Frontend**: Vanilla JavaScript, Tailwind CSS (CDN), [Chart.js](https://www.chartjs.org/) (CDN), [QRCode.js](https://davidshimjs.github.io/qrcodejs/) (CDN), Web Audio API
- **State**: In-memory singleton (`CortezState` in `app.py`) — zero database setup required; state resets on server restart or via the `reset_hotel` WebSocket command
- **Tunneling (Optional)**: [Cloudflare Quick Tunnel (`cloudflared`)](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) for instant public `https://` / `wss://` mobile access over 4G/5G without port forwarding

---

## Project Structure

```text
.
├── app.py                              # FastAPI app, in-memory state, WebSockets, bot engine & wing JS
├── requirements.txt                    # Python dependencies
├── start_cortez.sh                     # Launcher script (Uvicorn + optional Cloudflare Quick Tunnel)
├── templates/
│   ├── checkin.html                    # Mobile guest check-in registry & labyrinth view
│   ├── panoptico.html                  # Live 10 Hz projector dashboard
│   ├── qr.html                         # Dedicated fullscreen QR code page
│   └── salas/
│       ├── doomscrolling.html          # Doomscrolling wing
│       ├── procrastinacion.html        # Procrastination wing
│       ├── stalking.html               # Stalking wing
│       └── vanidad.html                # Pride / Vanity wing
├── LICENSE                             # MIT License
└── README.md
```

---

## Quick Start

### Prerequisites
- **Python 3.10+**
- *(Optional)* `cloudflared` if you want smartphones on cellular networks (4G/5G) to reach your local server over HTTPS/WSS.

### 1. Install Dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Run the Server

#### Option A: Launcher script (with optional Cloudflare Quick Tunnel)
```bash
chmod +x start_cortez.sh
./start_cortez.sh
```
If `cloudflared` is installed, the script prints a public `https://*.trycloudflare.com/panoptico` URL. Open the Panopticon from that public URL so the generated QR code automatically points phones to the public HTTPS endpoint.

#### Option B: Local Uvicorn only
```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```
Then open:
- **Projector dashboard**: `http://localhost:8000/panoptico`
- **Mobile check-in**: `http://localhost:8000/checkin`
- **Fullscreen QR**: `http://localhost:8000/qr`

---

## Endpoints Reference

| Route | Type | Purpose |
| --- | --- | --- |
| `/` | HTTP (`GET`) | Redirects to `/checkin` |
| `/checkin` | HTTP (`GET`) | Mobile check-in registry (injects `/cortez-salas-router.js`) |
| `/qr` | HTTP (`GET`) | Fullscreen responsive QR code pointing to `/checkin` |
| `/sala/{pecado}` | HTTP (`GET`) | Renders the wing for `doomscrolling`, `vanidad`/`vanity`, `stalking`, or `procrastinacion`/`procrastination` |
| `/panoptico` | HTTP (`GET`) | Live projector surveillance dashboard |
| `/api/huespedes-espiados` | HTTP (`GET`) | JSON snapshot of currently registered guests |
| `/cortez-salas-router.js` | HTTP (`GET`) | Client-side check-in form router |
| `/cortez-sala-core.js` | HTTP (`GET`) | Shared dark-pattern & WebSocket telemetry script |
| `/ws/huesped/{client_id}` | WebSocket | Mobile guest telemetry (`checkin`, `scroll`, `escape_attempt`, `ping`) |
| `/ws/panoptico` | WebSocket | 10 Hz projector broadcast & commands (`toggle_bots`, `reset_hotel`) |

---

## License

This project is licensed under the [MIT License](LICENSE).
