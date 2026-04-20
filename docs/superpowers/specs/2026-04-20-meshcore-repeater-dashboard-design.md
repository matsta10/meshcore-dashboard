# MeshCore Repeater Dashboard - Design Spec

## Overview

A lightweight web dashboard for managing a single MeshCore repeater radio connected via USB serial. Provides real-time stats monitoring, configuration management, neighbor discovery, and packet logging through a browser interface.

**Target deployment**: Proxmox LXC container (ID 123, hostname "meshcore") with Blue Orchid repeater connected at `/dev/ttyACM0`. This is the main repeater for the house mesh, so every write path needs a reason to exist, confirmation appropriate to its blast radius, and a way to undo it.

## Deployment Model

**No Docker.** The LXC itself is the isolation boundary. Run FastAPI directly under systemd.

```
/opt/meshcore-dashboard/
  app/              # FastAPI + built frontend
  data/             # SQLite DB
  .venv/            # managed by uv

/etc/systemd/system/meshcore-dashboard.service
```

The service file handles restart-on-failure. Logs via `journalctl -u meshcore-dashboard`. Serial port access via group membership (`dialout` or host-level `chmod 666`).

**Install script** (`scripts/install.sh`): sets up venv with uv, copies files, writes systemd unit, enables service. Not distributing this - the LXC is the reproducibility boundary.

**Resource sizing**: 256-512MB RAM for the LXC. CPU negligible.

## Architecture

```
Browser (React + shadcn/ui)
    |
    WebSocket + REST
    |
FastAPI Backend (systemd)
    |
    +-- Background Poller
    |       60s default / 10s live mode
    |       writes stats/neighbors to SQLite
    |       broadcasts to WebSocket clients
    |       tracks consecutive failures
    |
    +-- Command Executor (on-demand only)
    |       set config, reboot, advert, etc.
    |       serialized via asyncio.Lock
    |       pre-change config snapshots
    |
    +-- RepeaterConnection
    |       owns serial port
    |       reconnect with backoff
    |       command timeout handling
    |       distinct states: connected / unresponsive / disconnected
    |
    +-- Retention Job (daily)
            downsamples stats
            backs up DB
```

### Key Architectural Decisions

**Single background poller, DB-backed reads.** One background task polls the repeater and writes to SQLite. All HTTP and WebSocket clients read from the database, never from serial directly. Only explicit user commands (set config, send advert, reboot) hit serial on demand. Multiple browser clients don't increase device load.

**Single process.** FastAPI serves the built React frontend as static files. No nginx, no split services.

**Adaptive polling.** Default 60s. Frontend can request "live mode" (10s) via WebSocket message. Uses Page Visibility API to auto-downgrade when tab is backgrounded. Only one live mode session needed at a time - the poller runs at the fastest requested rate.

## Serial Protocol Layer

### RepeaterConnection

Owns the serial port exclusively. All access goes through this class.

**Protocol:**
- Send: `command\r`
- Wait: configurable timeout per command tier
- Read: lines prefixed with `  -> ` contain response data
- Stats commands return JSON; config gets return plain text (`  -> > value`)

**Command timeout tiers:**
- Fast commands (stats, get, neighbors): 1s timeout
- Normal commands (set, advert, clock sync): 3s timeout
- Slow commands (reboot, log dump, region ops): 10s timeout

**Three connection states:**
1. **Connected**: serial port open, device responding
2. **Unresponsive**: serial port exists but device not answering (check host USB)
3. **Disconnected**: serial port gone entirely (LXC passthrough broken)

In LXC, we can't auto-recover from USB re-enumeration at the host level. If the port disappears, surface "device unreachable, check host USB passthrough" in the UI rather than spinning on reconnect.

**Reconnect strategy (for transient failures):**
- Detect disconnect via serial read errors or empty reads
- Release asyncio.Lock cleanly on port death (no deadlocks)
- Reconnect with exponential backoff: 1s, 2s, 4s, 8s, max 30s
- After 5 consecutive poll failures, emit `device_unreachable` event
- Emit connection status changes to WebSocket clients

**asyncio.Lock behavior:**
- All serial commands serialized through a single lock
- Lock acquisition has a timeout (10s) to prevent deadlocks
- If port dies mid-command, the lock holder catches the exception, marks connection as dead, and releases the lock
- Next command attempt triggers reconnect

**Command interface:**
```python
class RepeaterConnection:
    async def connect(port: str, baud: int = 115200) -> None
    async def send_command(cmd: str, timeout: float = 1.0) -> str
    async def get_stats_core() -> StatsCoreModel
    async def get_stats_radio() -> StatsRadioModel
    async def get_stats_packets() -> StatsPacketsModel
    async def get_neighbors() -> list[NeighborModel]
    async def get_config(key: str) -> str
    async def set_config(key: str, value: str) -> bool
    async def get_device_info() -> DeviceInfoModel  # name, ver, board
    async def send_raw(cmd: str) -> str  # for whitelisted commands
    @property
    def state() -> ConnectionState  # connected | unresponsive | disconnected
```

## Data Models (SQLAlchemy)

### stats_snapshots

Stores periodic stats. Retention policy built in from day one.

```
id              INTEGER PRIMARY KEY
timestamp       DATETIME (indexed)
battery_mv      INTEGER
uptime_secs     INTEGER
queue_len       INTEGER
errors          INTEGER
noise_floor     INTEGER
last_rssi       INTEGER
last_snr        REAL
tx_air_secs     INTEGER
rx_air_secs     INTEGER
packets_recv    INTEGER
packets_sent    INTEGER
flood_rx        INTEGER
flood_tx        INTEGER
direct_rx       INTEGER
direct_tx       INTEGER
recv_errors     INTEGER
```

**Retention (downsampling job runs daily):**
- Raw (60s intervals): keep 7 days
- Hourly averages: keep 90 days
- Daily averages: keep forever

Downsampled data stored in `stats_hourly` and `stats_daily` tables with same columns (averaged values).

### config_current

Single-row-per-key table. Stores current config state.

```
key             TEXT PRIMARY KEY
value           TEXT
updated_at      DATETIME
```

### config_changelog

Append-only log of actual config changes. Only written when a value differs from the previous stored value. Includes pre-change snapshot for one-click revert.

```
id              INTEGER PRIMARY KEY
timestamp       DATETIME
key             TEXT
old_value       TEXT
new_value       TEXT
source          TEXT  -- "user" | "detected" (poller noticed drift)
```

### neighbors

```
id              INTEGER PRIMARY KEY
public_key      TEXT (unique, indexed)
name            TEXT
first_seen      DATETIME
last_seen       DATETIME
last_rssi       INTEGER
last_snr        REAL
```

### packet_logs

```
id              INTEGER PRIMARY KEY
timestamp       DATETIME
raw_line        TEXT
```

### device_info

Singleton table for cached device metadata.

```
id              INTEGER PRIMARY KEY (always 1)
name            TEXT
firmware_ver    TEXT
board           TEXT
public_key      TEXT
radio_freq      REAL
radio_bw        REAL
radio_sf        INTEGER
radio_cr        INTEGER
tx_power        INTEGER
updated_at      DATETIME
```

## API Endpoints

### Health

```
GET  /api/health              Returns 200 if last successful poll <5min ago, 503 otherwise.
                              Point Uptime Kuma / monitoring at this.
```

### Status & Stats

```
GET  /api/status              Current connection status + device info (from DB)
GET  /api/stats/current       Latest stats snapshot
GET  /api/stats/history       Stats over time
                              Query params: metric, from, to, resolution (raw|hourly|daily)
```

`resolution` param selects which table to query. Frontend sparklines use `hourly`; detail views use `raw`.

### Configuration

```
GET  /api/config              All config key/values (from config_current table)
GET  /api/config/{key}        Single key read (from DB)
PUT  /api/config/{key}        Set a config value (hits serial, snapshots old value first)
POST /api/config/{key}/revert Revert to previous value (from changelog)
GET  /api/config/changelog    Config change history
```

**PUT /api/config/{key} safety:**
- Before any `set` command, snapshot current value to DB as pre-change marker
- Critical params (radio freq, bw, sf, cr, tx power) require `"confirm_value": "<value>"` in body - frontend makes user type the value twice
- All other params use normal save buttons
- Returns the changelog entry so frontend can show "undo" option

### Neighbors

```
GET  /api/neighbors           Current neighbor list (from DB)
POST /api/neighbors/discover  Trigger neighbor discovery (hits serial)
```

### Logs

```
GET  /api/logs                Packet log entries (paginated)
POST /api/logs/start          Start logging on device
POST /api/logs/stop           Stop logging on device
POST /api/logs/fetch          Pull log from device to DB
POST /api/logs/erase          Erase device log (requires confirm: true)
```

### Commands

```
POST /api/command             Execute a whitelisted CLI command
                              Body: { "command": "advert" }
```

**Command whitelist:**
- Safe: `ver`, `board`, `clock`, `stats-core`, `stats-radio`, `stats-packets`, `neighbors`, `advert`, `advert.zerohop`, `discover.neighbors`, `log`, `log start`, `log stop`, `region`, `region list`
- Destructive (require `"confirm": true` in body): `reboot`, `clear stats`, `log erase`
- Blocked: `set prv.key`, `password`, `erase`, any unknown command

**Reboot cooldown:** After a reboot command, the endpoint returns a 60s cooldown. Subsequent reboot requests during cooldown return 429 with remaining seconds. Frontend shows countdown.

### WebSocket

```
WS   /ws                      Live updates
```

**Server -> Client messages:**
```json
{ "type": "stats_update", "data": { ... } }
{ "type": "connection_status", "data": { "state": "connected|unresponsive|disconnected" } }
{ "type": "log_line", "data": { "timestamp": "...", "line": "..." } }
{ "type": "neighbor_update", "data": { ... } }
{ "type": "poll_interval", "data": { "interval_seconds": 60 } }
```

**Client -> Server messages:**
```json
{ "type": "set_live_mode", "data": { "enabled": true } }
```

When live mode enabled, poller drops to 10s. When disabled (or tab backgrounded via Page Visibility API), returns to 60s. The poller runs at the fastest rate any connected client requests.

## Read-Only Mode

Environment variable `READ_ONLY=1`. When set, all mutation endpoints (`PUT`, `POST` except health) return 403. ~20 lines of middleware. For when you want to glance at stats without risk of fat-fingering a config change.

## Frontend (React + Vite + shadcn/ui)

### Stack
- React 19 + TypeScript
- Vite for build
- shadcn/ui + Tailwind CSS
- Recharts for charts
- Single-page app with sidebar nav

### Pages

**1. Dashboard**
- Connection status indicator (green/yellow/red) with state label
- Device info card (name, firmware, board, radio params)
- Stats cards: battery (mV + icon), uptime (human readable), RSSI, SNR, noise floor, queue length
- Packet counters: recv, sent, flood rx/tx, direct rx/tx, errors
- Sparkline charts (last 24h, hourly resolution from `/api/stats/history?resolution=hourly`)
- "Live mode" toggle - bumps polling to 10s, auto-disables on tab background (Page Visibility API)
- "Refresh now" button for on-demand poll

**2. Config**
- Grouped form fields matching repeater config categories:
  - Identity: name, lat, lon, owner info
  - Radio: freq, bw, sf, cr, tx power (these require typed confirmation)
  - Routing: repeat, advert intervals, flood hops, loop detect, duty cycle
  - Access: password fields (write-only)
- Change detection: compare form values to stored values, highlight dirty fields
- Save button per-section
- Critical params (radio, tx power): save requires typing the new value again in a confirmation input
- Config changelog viewer with "revert" buttons

**3. Neighbors**
- Table: name, public key (truncated), RSSI, SNR, first seen, last seen
- Discover button to trigger active discovery
- Auto-refreshes from WebSocket neighbor_update events

**4. Logs**
- Toggle switch: start/stop logging on device
- Fetch button: pull device log to DB
- Scrolling log table with timestamp and raw line
- Erase button (with typed confirmation dialog)

**5. Console (stretch goal)**
- Direct CLI input with autocomplete (whitelist only)
- Command history
- For power users who want raw access

### Layout

Sidebar navigation with icons. Top bar shows device name + connection status. Responsive but primarily desktop-focused (this is a server dashboard, not mobile). Read-only mode shows a banner.

## Authentication

HTTP Basic Auth via environment variables:

```
BASIC_AUTH_USER=admin
BASIC_AUTH_PASS=changeme
```

FastAPI middleware checks on all routes except `/api/health`. If env vars not set, no auth (local-only use).

If fronted by a reverse proxy (Caddy/Traefik/nginx-proxy-manager) for TLS, can drop basic auth in favor of proxy-level auth.

## Backup

Nightly `sqlite3 .backup` to a location outside the LXC's normal storage. Config history and neighbor discovery data takes weeks to accumulate and shouldn't be lost to an LXC snapshot rollback.

Simple cron job or systemd timer:
```bash
sqlite3 /opt/meshcore-dashboard/data/meshcore.db ".backup /mnt/backup/meshcore-$(date +%Y%m%d).db"
```

## Project Structure

Scaffolded from [cookiecutter-uv](https://github.com/osprey-oss/cookiecutter-uv). Structure below shows the application-specific layout on top of what the template provides.

```
meshcore-dashboard/
  pyproject.toml           # from cookiecutter-uv template
  scripts/
    install.sh           # Sets up venv, systemd unit, enables service
  app/
    __init__.py
    main.py              # FastAPI app, lifespan, static file serving
    config.py            # Settings from env vars (pydantic-settings)
    database.py          # SQLAlchemy engine, session factory
    models.py            # SQLAlchemy ORM models
    schemas.py           # Pydantic request/response schemas
    serial/
      __init__.py
      connection.py      # RepeaterConnection class
      parser.py          # Response parsing utilities
      commands.py        # Command definitions, timeouts, whitelist
    routers/
      __init__.py
      status.py          # /api/status, /api/stats/*, /api/health
      config.py          # /api/config/*
      neighbors.py       # /api/neighbors/*
      logs.py            # /api/logs/*
      commands.py        # /api/command
      websocket.py       # /ws
    services/
      __init__.py
      poller.py          # Background polling task (adaptive rate)
      retention.py       # Stats downsampling + DB backup job
    middleware/
      __init__.py
      auth.py            # Basic auth middleware
      readonly.py        # Read-only mode middleware
  frontend/
    package.json
    vite.config.ts
    src/
      App.tsx
      pages/
        Dashboard.tsx
        Config.tsx
        Neighbors.tsx
        Logs.tsx
      components/
        StatsCard.tsx
        SparklineChart.tsx
        ConfigForm.tsx
        NeighborTable.tsx
        LogViewer.tsx
        ConnectionStatus.tsx
        LiveModeToggle.tsx
        RebootButton.tsx
      hooks/
        useWebSocket.ts
        useApi.ts
        usePageVisibility.ts
      lib/
        api.ts           # API client
        types.ts          # TypeScript types
  data/                  # SQLite DB
```

## Tech Stack

**Backend:**
- Python 3.12+
- FastAPI + uvicorn
- SQLAlchemy 2.0 (async, aiosqlite)
- pyserial (serial communication)
- pydantic / pydantic-settings
- uv for all Python tooling

**Frontend:**
- React 19 + TypeScript
- Vite
- shadcn/ui + Tailwind CSS
- Recharts

**Infrastructure:**
- systemd service in Proxmox LXC
- SQLite
- uv for dependency management

## Testing Strategy

- Serial layer: mock serial port, test command/response parsing
- API: FastAPI test client with test DB
- Frontend: manual testing (homelab tool, not production SaaS)

## Out of Scope (for v1)

- Multi-repeater support (run a second container instead)
- User accounts / role-based auth
- MQTT forwarding
- Mobile-optimized UI
- OTA firmware updates through the dashboard
- Region management UI (complex file upload/download)
- Events timeline table (add later if "why was mesh weird last Tuesday" becomes a need)
