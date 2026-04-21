# Frontend Overhaul — Design Spec

## Goal

Redesign all 4 frontend pages to be a dense, dark-themed radio dashboard using vanilla shadcn components. Remove all manual fallback buttons (the backend auto-collects everything). Kill AI slop.

## Principles

- Vanilla shadcn/ui components only — no custom CSS beyond Tailwind utilities
- Dark theme (shadcn built-in dark mode)
- Dense: monospace for data values, compact padding, no wasted space
- Fully automated: no manual "Fetch", "Discover", or "Start logging" buttons
- All data arrives via WebSocket push or initial API fetch

## Pages

### Dashboard (`/`)

**Layout**: Header bar + two-column stats grid + packets row + signal chart.

**Header bar**:
- Device name (from `/api/status` device_info.name)
- Firmware + board as muted text
- Connection Badge (shadcn `Badge` with green/yellow/red dot)
- No live toggle — always live via WS

**Stats grid** (two columns, each a shadcn `Card` with `Table` inside):

Left — **System**:
| Label | Value |
|-------|-------|
| Battery | `{battery_mv} mV` |
| Uptime | formatted `Xd Xh` / `Xh Xm` / `Xm` |
| Queue | `{queue_len}` |
| Errors | `{errors}` |

Right — **Radio**:
| Label | Value |
|-------|-------|
| RSSI | `{last_rssi} dBm` (blue) |
| SNR | `{last_snr} dB` (blue) |
| Noise Floor | `{noise_floor} dBm` (red) |
| TX Air | `{tx_air_secs}s` |
| RX Air | `{rx_air_secs}s` |

**Packets row** (single `Card`, 4-column grid inside):
- Flood RX, Flood TX, Direct RX, Direct TX — centered, monospace, label above

**Signal chart**: Recharts `LineChart` in a `Card`. RSSI (blue) + Noise Floor (red, dashed). 24h hourly resolution. Compact, no legend — colors are obvious from the stats table above.

**Data flow**: Initial fetch from `/api/stats/current` + `/api/status` + `/api/stats/history`. WS `stats_update` messages update stats in real-time.

### Logs (`/logs`)

**Layout**: Header with entry count + auto-scrolling structured table.

**Remove**: "Fetch from device" button, logging on/off toggle, "Danger Zone" erase card.

**Structured table**: Parse `raw_line` client-side into columns:
- Time (from the log line, e.g. `02:24:24`)
- Dir (`TX` green / `RX` blue)
- Type (number)
- Route (`F` flood / `D` direct)
- Size (payload_len)
- SNR (RX only, else `—`)
- RSSI (RX only, else `—`)

Parsing regex on the raw_line format:
```
HH:MM:SS - DD/M/YYYY U: (TX|RX), len=N (type=N, route=X, payload_len=N) [SNR=N RSSI=N ...]
```

**Data flow**: Initial fetch from `/api/logs`. WS `logs_update` message triggers re-fetch (or push new entries directly). New entries appear at top.

**Backend change needed**: Broadcast `logs_update` from poller after storing new log entries (currently doesn't broadcast log updates).

### Neighbors (`/neighbors`)

**Layout**: Header with count badge + table.

**Remove**: "Discover" button.

**Table columns**: Public Key (monospace), SNR, First Seen (relative, e.g. "3h ago"), Last Seen (relative).

Drop the "Name" column — MeshCore neighbors don't have names in the `neighbors` command output. Drop RSSI column — the value from `neighbors` output isn't dBm (it's some internal metric), only SNR is meaningful.

**Data flow**: Initial fetch from `/api/neighbors`. WS `neighbors_update` triggers re-fetch.

**Frontend bug fix**: Current code listens for `neighbor_update` (singular) but backend broadcasts `neighbors_update` (plural). Fix frontend to match.

### Config (`/config`)

**Layout**: Header + shadcn `Tabs` for categories + settings table + changelog table.

**Tab categories**: Radio, Network, Security, System. Config keys are mapped to categories client-side (since the backend just returns flat key/value pairs).

**Settings display**: Each row shows key name, description (static text mapped client-side), and current value in monospace. Read-only by default.

**Editing**: Click a value to make it editable (inline input). Save button appears. For critical radio params (freq, bw, sf, cr, tx_power), a confirmation input appears requiring the value typed twice. No "critical" badge label — the confirmation step is the safety, not a label.

**Changelog**: Simple shadcn `Table` below the settings. Columns: Time, Key, Old → New. No "Source" column, no "Revert" button.

**Remove**: `alert()` error handling — use shadcn toast or inline error text.

**Data flow**: Initial fetch from `/api/config` + `/api/config/changelog`.

## Sidebar

Narrow the sidebar from `w-56` (224px) to `w-44` (176px). Same structure, just less wasted space.

## Dead Code Removal

- Delete `usePageVisibility.ts` hook (only used for live toggle TTL)
- Remove live mode WS messages from `useWebSocket` usage in Dashboard
- Remove all manual fetch/toggle/discover handlers from pages

## Backend Changes

Two small backend changes needed to support the frontend:

1. **Broadcast `logs_update`**: In `poller.py`, after storing new log entries in `_collect_logs`, broadcast `{"type": "logs_update", "data": {}}` via WS so the frontend knows to refresh.

2. **Fix WS event consistency**: Either rename backend `neighbors_update` → `neighbor_update` or fix frontend to listen for `neighbors_update`. Pick one and be consistent.

## shadcn Components Used

All already installed:
- `Card` — section containers
- `Table` / `TableHeader` / `TableBody` / `TableRow` / `TableCell` / `TableHead` — stats, logs, neighbors, config, changelog
- `Badge` — connection status, entry counts
- `Tabs` / `TabsList` / `TabsTrigger` / `TabsContent` — config categories
- `Switch` — removed (was live toggle)
- `Input` — config editing
- `Button` — save config
- `Separator` — if needed between sections

No new component installs required.
