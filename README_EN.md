# GoldClaw

[中文文档](README.md)

<img width="1496" height="991" alt="Dashboard" src="https://github.com/user-attachments/assets/789dbe20-ffc5-420b-a7d0-d3d84d3e2d76" />

<img width="1491" height="993" alt="Comm" src="https://github.com/user-attachments/assets/d9cb740e-5044-44e8-8a53-64be8237e7c6" />
<img width="1495" height="996" alt="Settings" src="https://github.com/user-attachments/assets/d6c6f8c5-2e03-4495-8bc4-305530eb96f4" />
<img width="1501" height="995" alt="Backup" src="https://github.com/user-attachments/assets/fbe01d0d-2f03-46f2-9baf-500e50a93245" />

> Quantitative Gold Trading Simulation Engine + Dashboard

---

## What is this?

GoldClaw is a native macOS app for simulating gold (XAU) trading. It monitors the market via a live gold price API, receives investment instructions from an external AI system (OpenClaw), and automatically executes simulated trades with P&L calculation, take-profit / stop-loss monitoring, and margin call detection.

It includes a built-in Dashboard with gold price charts, investor position details, communication monitoring, and runtime configuration.

---

## Installation

### Option 1: DMG Install (Recommended)

1. Download the latest `.dmg` from [GitHub Releases](https://github.com/chuhengtantt/GoldClaw/releases)
2. Double-click, drag GoldClaw.app to Applications
3. Launch GoldClaw.app — the Dashboard window opens automatically
4. On first launch, allow it in System Settings > Privacy & Security

### Option 2: Run from Source

```bash
git clone https://github.com/chuhengtantt/GoldClaw.git
cd GoldClaw
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit configuration
python run.py           # start Engine + Dashboard
```

Open http://localhost:8089/dashboard/ in your browser.

---

## Dashboard Features

| Page | Features |
|------|----------|
| **Assets** | Gold price line chart (red=up, green=down), Investor A/B asset curve (with decision labels), positions and trade history |
| **Communication** | GoldClaw ↔ OpenClaw comm log (day/week/month views) |
| **Settings** | Modify scheduling intervals, state machine thresholds at runtime |
| **Backup** | Manual create/restore database backups, auto backup on start/shutdown |

---

## OpenClaw Communication Protocol

GoldClaw and OpenClaw communicate via a **Mailbox + Doorbell** dual-channel system:

```
┌─────────────┐   state_for_openclaw.json   ┌─────────────┐
│             │ ──────────────────────────► │             │
│  GoldClaw   │                             │  OpenClaw   │
│  (Python)   │ ◄── orders_from_openclaw.json │  (AI Agent) │
│             │                             │             │
│             │   POST /emergency (doorbell) │             │
│             │ ──────────────────────────► │             │
└─────────────┘                             └─────────────┘
```

### Data Directory

| Path | Description |
|------|-------------|
| `~/GoldClaw/data/` | Root data directory |
| `~/GoldClaw/data/goldclaw.db` | SQLite database |
| `~/GoldClaw/data/state_for_openclaw.json` | GoldClaw state output (overwritten each tick) |
| `~/GoldClaw/data/orders_from_openclaw.json` | OpenClaw order instructions (archived after reading) |
| `~/GoldClaw/data/bridge_events.jsonl` | Emergency event log |

### GoldClaw → OpenClaw: State File

Overwritten every tick as `state_for_openclaw.json`:

```json
{
  "type": "status_report",
  "timestamp": "2026-04-09T21:21:31Z",
  "system": {
    "state": "IDLE",
    "gold_price": 4767.50,
    "volatility": 0.00349,
    "slope_3min": -0.00022
  },
  "investors": {
    "A": {
      "total_assets": 10381.89,
      "cash": 7115.97,
      "margin_committed": 3019.20,
      "current_action": "cfd_long",
      "entry_price": 4748.10,
      "current_price": 4767.50,
      "tp": 4850.00,
      "sl": 4680.00,
      "nominal_pnl": 246.72,
      "net_pnl": 245.48,
      "margin_call": 0,
      "pnl_pct": 0.0817,
      "nights_held": 0
    },
    "B": {
      "total_assets": 10000.00,
      "cash": 10000.00,
      "margin_committed": 0,
      "current_action": "idle",
      "entry_price": null,
      "current_price": 4767.50,
      "tp": 0,
      "sl": 0,
      "nominal_pnl": 0,
      "net_pnl": 0,
      "margin_call": 0,
      "pnl_pct": 0,
      "nights_held": 0
    }
  },
  "warnings": []
}
```

### OpenClaw → GoldClaw: Order Instructions

OpenClaw writes `orders_from_openclaw.json`, GoldClaw reads and executes on the next tick:

```json
{
  "timestamp": "2026-04-09T12:00:00Z",
  "instructions": [
    {
      "investor": "A",
      "action": "cfd_long",
      "margin_pct": 0.8,
      "tp": 4850.00,
      "sl": 4680.00,
      "signal_strength": 0.85,
      "signal_type": "strong_bullish",
      "reasoning": "Breakout above key resistance, uptrend confirmed"
    },
    {
      "investor": "B",
      "action": "sgln_long",
      "margin_pct": 0.6,
      "tp": 0,
      "sl": 0,
      "reasoning": "Hedge risk with physical gold allocation"
    }
  ]
}
```

**Field Reference:**

| Field | Required | Description |
|-------|----------|-------------|
| `investor` | Yes | Investor ID: `"A"` or `"B"` |
| `action` | Yes | Action: `cfd_long` / `cfd_short` / `sgln_long` / `hold` / `idle` / `close` |
| `margin_pct` | Yes on open | Margin percentage 0.0 - 1.0 |
| `tp` | Yes for CFD | Take-profit price (set 0 for SGLN) |
| `sl` | Yes for CFD | Stop-loss price (set 0 for SGLN) |
| `signal_strength` | No | Signal strength 0.0 - 1.0 |
| `signal_type` | No | Signal type description |
| `reasoning` | No | Investment rationale |

**Investor A:** CFD 1:20 leverage — `cfd_long` / `cfd_short` / `hold` / `idle` / `close`
**Investor B:** SGLN physical gold or CFD short (mutually exclusive) — `sgln_long` / `cfd_short` / `hold` / `idle` / `close`

### Doorbell (Emergency Notification)

When the state machine enters TRIGGER or a margin call / stop-loss / take-profit occurs, GoldClaw POSTs to the Bridge:

**Endpoint:** `POST /emergency`

```json
{
  "type": "emergency",
  "event": "state_trigger",
  "investor": "A",
  "gold_price": 4768.30,
  "priority": "urgent",
  "action_taken": "notifying_openclaw",
  "message": "TRIGGER: slope exceeded threshold, gold price $4768.30",
  "timestamp": "2026-04-09T21:56:58Z"
}
```

**Event Types:**

| Event | Description |
|-------|-------------|
| `state_trigger` | Slope triggered TRIGGER state — OpenClaw needs urgent decision |
| `margin_call` | Margin call (auto-closed) |
| `stop_loss` | Stop-loss hit (auto-closed) |
| `take_profit` | Take-profit hit (auto-closed) |

### OpenClaw Cron Job Configuration

OpenClaw periodically reads state and makes investment decisions. Suggested cron:

```bash
# Check GoldClaw state every 3 hours
0 */3 * * * openclaw agent --read ~/GoldClaw/data/state_for_openclaw.json --write ~/GoldClaw/data/orders_from_openclaw.json
```

**Workflow:**
1. OpenClaw cron fires, reads `~/GoldClaw/data/state_for_openclaw.json`
2. Analyzes market state, investor positions, risk indicators
3. Generates investment decisions, writes `~/GoldClaw/data/orders_from_openclaw.json`
4. GoldClaw reads and executes orders on next tick
5. After execution, file is archived as `orders_processed_[timestamp].json`

**Emergency Workflow:**
1. GoldClaw detects TRIGGER / margin call → POSTs to Bridge URL
2. Bridge triggers `openclaw agent --deliver -m "[urgent message]"`
3. OpenClaw responds immediately, writes `orders_from_openclaw.json`
4. GoldClaw reads and executes within 3 minutes (WATCH mode)

---

## State Machine

```
IDLE ──(slope > THRESHOLD_A × 5 times)──► WATCH ──(slope > THRESHOLD_B)──► TRIGGER
  ▲                                      │                              │
  └──────(cooldown 30 min)───────────────┘                              │
  └──────────────(after TRIGGER execution, return to IDLE)──────────────┘
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `CYCLE_X` | 5 | Consecutive triggers to enter WATCH |
| `THRESHOLD_A` | 0.003 | IDLE slope threshold |
| `THRESHOLD_B` | 0.005 | WATCH slope threshold |
| `WATCH_DURATION` | 5 | WATCH duration in ticks |
| `TRIGGER_SLOPE` | 0.002 | TRIGGER slope threshold |
| `SILENCE_PERIOD` | 30 | Cooldown period (minutes) |

All parameters can be modified at runtime via Dashboard Settings.

---

## Configuration

Edit `.env` file (source mode) or `~/GoldClaw/.env` (App mode):

```bash
# Gold Price API
GOLD_API_URL=https://api.gold-api.com/price/XAU

# OpenClaw Bridge
OPENCLAW_BRIDGE_URL=http://localhost:8089/emergency
OPENCLAW_BRIDGE_TIMEOUT=30

# Database
DB_PATH=data/goldclaw.db

# Scheduling intervals (minutes)
SCHEDULE_INTERVAL_IDLE=15
SCHEDULE_INTERVAL_WATCH=3

# Initial capital
INITIAL_CASH_A=10000
INITIAL_CASH_B=10000
```

---

## Project Structure

```
GoldClaw/
├── app_main.py           # macOS App entry (pywebview native window)
├── run.py                # CLI entry (uvicorn + Engine)
├── dashboard_api.py      # FastAPI Dashboard API
├── openclaw_bridge.py    # OpenClaw Bridge emergency notification service
├── build_dmg.sh          # DMG build script
├── build.sh              # Tarball build script
├── config/               # Configuration (pydantic-settings)
├── profiles/             # Investor profiles (YAML)
├── app/                  # Application layer (engine + scheduler)
├── internal/             # Business logic
│   ├── price/            # Gold price fetching + volatility
│   ├── investor/         # Investor modules + P&L calculation
│   ├── state_machine/    # State machine (IDLE/WATCH/TRIGGER)
│   ├── exchange/         # Communication (mailbox + doorbell + schema)
│   ├── db/               # SQLite database + migrations
│   └── exception/        # Exception handling
├── dashboard/            # Frontend (HTML + CSS + JS)
│   ├── index.html
│   └── static/
│       ├── style.css
│       ├── app.js
│       └── app_icon.icns
├── data/                 # Runtime data (gitignored)
└── tests/                # Tests
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| Database | SQLite (WAL mode) |
| Dashboard | FastAPI + Chart.js |
| Native Window | pywebview (macOS WKWebView) |
| Scheduling | APScheduler |
| HTTP | httpx |
| Validation | Pydantic v2 |
| Configuration | pydantic-settings + .env |
| Packaging | PyInstaller + hdiutil (DMG) |

---

## Documentation

| File | Description |
|------|-------------|
| [PRD.md](PRD.md) | Product Requirements Document |
| [ARCH.md](ARCH.md) | Technical Architecture & Engineering Constraints |
| [RULES.md](RULES.md) | OpenClaw Communication Protocol (JSON format, field constraints) |
| [project_state.md](project_state.md) | Current Project Status |

---

## License

Private project. All rights reserved.
