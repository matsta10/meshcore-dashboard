import { startTransition, useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableRow,
} from "@/components/ui/table"
import { api } from "@/lib/api"
import type { StatsResponse, StatusResponse } from "@/lib/types"
import { useWebSocket } from "@/hooks/useWebSocket"
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Tooltip,
} from "recharts"

function formatUptime(secs: number | null): string {
  if (secs === null) return "—"
  const d = Math.floor(secs / 86400)
  const h = Math.floor((secs % 86400) / 3600)
  const m = Math.floor((secs % 3600) / 60)
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

function formatDateTime(value: string | null): string {
  if (!value) return "—"
  const parsed = Date.parse(value)
  if (Number.isNaN(parsed)) return "—"
  return new Date(parsed).toLocaleString()
}

function epochSecondsFromTimestamp(value: string | null): number | null {
  if (!value) return null
  const parsed = Date.parse(value)
  if (Number.isNaN(parsed)) return null
  return Math.floor(parsed / 1000)
}

function ConnectionBadge({ state, wsConnected }: { state: string; wsConnected: boolean }) {
  const label = !wsConnected ? "reconnecting" : state
  const color = !wsConnected
    ? "bg-yellow-500 animate-pulse"
    : state === "connected"
      ? "bg-green-500"
      : state === "unresponsive"
        ? "bg-yellow-500"
        : "bg-red-500"
  return (
    <Badge variant="outline" className="gap-1.5">
      <span className={`h-2 w-2 rounded-full ${color}`} />
      {label}
    </Badge>
  )
}

type ClockNotice = {
  tone: "success" | "error"
  text: string
} | null

export default function Dashboard() {
  const [status, setStatus] = useState<StatusResponse | null>(null)
  const [stats, setStats] = useState<StatsResponse | null>(null)
  const [history, setHistory] = useState<StatsResponse[]>([])
  const [stale, setStale] = useState(false)
  const [localNow, setLocalNow] = useState(() => Date.now())
  const [clockOutput, setClockOutput] = useState<string | null>(null)
  const [clockNotice, setClockNotice] = useState<ClockNotice>(null)
  const [clockBusy, setClockBusy] = useState<"read" | "sync" | "set" | null>(
    null
  )
  const { lastMessage, connected, send } = useWebSocket()
  const serverEpochSeconds = epochSecondsFromTimestamp(stats?.timestamp ?? null)

  useEffect(() => {
    let cancelled = false

    void Promise.all([api.getStatus(), api.getStatsCurrent()]).then(
      ([nextStatus, nextStats]) => {
        if (cancelled) return
        startTransition(() => {
          setStatus(nextStatus)
          setStats(nextStats)
          setStale(nextStats?.stale ?? false)
        })
      }
    )

    void api
      .getStatsHistory({
        metrics: "battery_mv,noise_floor,last_rssi,last_snr",
        resolution: "hourly",
      })
      .then((r) => {
        if (cancelled) return
        startTransition(() => {
          setHistory(r.data)
        })
      })

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    const id = window.setInterval(() => {
      setLocalNow(Date.now())
    }, 1000)
    return () => {
      window.clearInterval(id)
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    const loadClock = async () => {
      setClockBusy("read")
      try {
        const response = await api.readClock()
        if (cancelled) return
        startTransition(() => {
          setClockOutput(response.output.trim() || "—")
          setClockNotice(null)
        })
      } catch (e) {
        if (!cancelled) {
          setClockNotice({
            tone: "error",
            text: `Failed to read device clock: ${e}`,
          })
        }
      } finally {
        if (!cancelled) setClockBusy(null)
      }
    }

    void loadClock()

    return () => {
      cancelled = true
    }
  }, [])

  // Update from WS messages
  useEffect(() => {
    if (lastMessage?.type === "stats_update") {
      startTransition(() => {
        setStats(lastMessage.data as unknown as StatsResponse)
      })
    } else if (lastMessage?.type === "parse_error") {
      startTransition(() => {
        setStale(true)
      })
    } else if (lastMessage?.type === "parse_cleared") {
      startTransition(() => {
        setStale(false)
      })
    } else if (lastMessage?.type === "connection_status") {
      startTransition(() => {
        setStatus((prev) =>
          prev
            ? {
                ...prev,
                connection_state: (lastMessage.data as { state: string }).state as
                  StatusResponse["connection_state"],
              }
            : prev
        )
      })
    }
  }, [lastMessage])

  // Auto-renew live mode while dashboard is visible
  useEffect(() => {
    const renew = () => send({ type: "set_live_mode", data: { enabled: true } })
    renew()
    const id = setInterval(renew, 20_000)
    return () => {
      clearInterval(id)
      send({ type: "set_live_mode", data: { enabled: false } })
    }
  }, [send])

  const refreshClock = async (options?: { silentFailure?: boolean }) => {
    setClockBusy("read")
    try {
      const response = await api.readClock()
      startTransition(() => {
        setClockOutput(response.output.trim() || "—")
      })
    } catch (e) {
      if (!options?.silentFailure) {
        setClockNotice({
          tone: "error",
          text: `Failed to read device clock: ${e}`,
        })
      }
    } finally {
      setClockBusy(null)
    }
  }

  const handleSyncClock = async () => {
    setClockBusy("sync")
    setClockNotice(null)
    try {
      const response = await api.syncClock()
      setClockNotice({ tone: "success", text: response.detail })
      await refreshClock({ silentFailure: true })
    } catch (e) {
      setClockNotice({
        tone: "error",
        text: `Failed to sync clock: ${e}`,
      })
    } finally {
      setClockBusy(null)
    }
  }

  const handleSetClockToNow = async () => {
    if (serverEpochSeconds === null) {
      setClockNotice({
        tone: "error",
        text: "Server time is unavailable, so Set to Now is disabled.",
      })
      return
    }

    setClockBusy("set")
    setClockNotice(null)
    try {
      const response = await api.setClock(serverEpochSeconds)
      setClockNotice({ tone: "success", text: response.detail })
      await refreshClock({ silentFailure: true })
    } catch (e) {
      setClockNotice({
        tone: "error",
        text: `Failed to set clock: ${e}`,
      })
    } finally {
      setClockBusy(null)
    }
  }

  return (
    <div className="space-y-4">
      {/* Header bar */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold font-mono">
            {status?.device_info?.name ?? "MeshCore Dashboard"}
          </h1>
          <p className="text-sm text-muted-foreground">
            {status?.device_info?.firmware_ver ?? ""}{" "}
            {status?.device_info?.board ?? ""}
          </p>
        </div>
        <div className="flex items-center gap-4">
          <ConnectionBadge state={status?.connection_state ?? "disconnected"} wsConnected={connected} />
        </div>
      </div>

      {stale && (
        <div className="rounded-md border border-yellow-500/50 bg-yellow-500/10 px-4 py-2 text-sm text-yellow-200">
          Device response could not be parsed — stats may be outdated
        </div>
      )}

      <Card>
        <CardHeader className="pb-2 pt-3 px-4">
          <CardTitle className="text-sm text-muted-foreground">
            Clock / Admin
          </CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-3">
          <div className="grid gap-4 md:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)] md:items-start">
            <div className="space-y-2">
              <div>
                <p className="text-xs uppercase tracking-wide text-muted-foreground">
                  Local time
                </p>
                <p className="font-mono text-sm">{new Date(localNow).toLocaleString()}</p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-wide text-muted-foreground">
                  Device clock
                </p>
                <p className="font-mono text-xs whitespace-pre-wrap break-words text-foreground/90">
                  {clockOutput ?? "Reading clock..."}
                </p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-wide text-muted-foreground">
                  Server time
                </p>
                <p className="font-mono text-sm">
                  {formatDateTime(stats?.timestamp ?? null)}
                </p>
                {serverEpochSeconds === null && (
                  <p className="text-xs text-muted-foreground">
                    Server time unavailable; Set to Now is disabled.
                  </p>
                )}
              </div>
              {clockNotice && (
                <p
                  className={`text-xs ${clockNotice.tone === "success" ? "text-emerald-400" : "text-red-400"}`}
                >
                  {clockNotice.text}
                </p>
              )}
            </div>
            <div className="flex flex-wrap gap-2 md:justify-end">
              <Button
                size="sm"
                onClick={handleSyncClock}
                disabled={clockBusy !== null}
              >
                {clockBusy === "sync" ? "Syncing..." : "Sync Clock"}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={handleSetClockToNow}
                disabled={clockBusy !== null || serverEpochSeconds === null}
              >
                {clockBusy === "set" ? "Setting..." : "Set to Now"}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Stats grid — two columns */}
      <div className="grid grid-cols-2 gap-4">
        {/* Left: System */}
        <Card>
          <CardHeader className="pb-1 pt-3 px-4">
            <CardTitle className="text-sm text-muted-foreground">System</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-3">
            <Table>
              <TableBody>
                <TableRow>
                  <TableCell className="text-xs py-1.5 text-muted-foreground">Battery</TableCell>
                  <TableCell className="text-xs py-1.5 font-mono text-right">
                    {stats?.battery_mv != null ? `${stats.battery_mv} mV` : "—"}
                  </TableCell>
                </TableRow>
                <TableRow>
                  <TableCell className="text-xs py-1.5 text-muted-foreground">Uptime</TableCell>
                  <TableCell className="text-xs py-1.5 font-mono text-right">
                    {formatUptime(stats?.uptime_secs ?? null)}
                  </TableCell>
                </TableRow>
                <TableRow>
                  <TableCell className="text-xs py-1.5 text-muted-foreground">Queue</TableCell>
                  <TableCell className="text-xs py-1.5 font-mono text-right">
                    {stats?.queue_len ?? "—"}
                  </TableCell>
                </TableRow>
                <TableRow>
                  <TableCell className="text-xs py-1.5 text-muted-foreground">Errors</TableCell>
                  <TableCell className="text-xs py-1.5 font-mono text-right">
                    {stats?.errors ?? "—"}
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        {/* Right: Radio */}
        <Card>
          <CardHeader className="pb-1 pt-3 px-4">
            <CardTitle className="text-sm text-muted-foreground">Radio</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-3">
            <Table>
              <TableBody>
                <TableRow>
                  <TableCell className="text-xs py-1.5 text-muted-foreground">RSSI</TableCell>
                  <TableCell className="text-xs py-1.5 font-mono text-right text-blue-400">
                    {stats?.last_rssi != null ? `${stats.last_rssi} dBm` : "—"}
                  </TableCell>
                </TableRow>
                <TableRow>
                  <TableCell className="text-xs py-1.5 text-muted-foreground">SNR</TableCell>
                  <TableCell className="text-xs py-1.5 font-mono text-right text-blue-400">
                    {stats?.last_snr != null ? `${stats.last_snr.toFixed(1)} dB` : "—"}
                  </TableCell>
                </TableRow>
                <TableRow>
                  <TableCell className="text-xs py-1.5 text-muted-foreground">Noise Floor</TableCell>
                  <TableCell className="text-xs py-1.5 font-mono text-right text-red-400">
                    {stats?.noise_floor != null ? `${stats.noise_floor} dBm` : "—"}
                  </TableCell>
                </TableRow>
                <TableRow>
                  <TableCell className="text-xs py-1.5 text-muted-foreground">TX Air</TableCell>
                  <TableCell className="text-xs py-1.5 font-mono text-right">
                    {stats?.tx_air_secs != null ? `${stats.tx_air_secs}s` : "—"}
                  </TableCell>
                </TableRow>
                <TableRow>
                  <TableCell className="text-xs py-1.5 text-muted-foreground">RX Air</TableCell>
                  <TableCell className="text-xs py-1.5 font-mono text-right">
                    {stats?.rx_air_secs != null ? `${stats.rx_air_secs}s` : "—"}
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>

      {/* Packets row */}
      <Card>
        <CardContent className="px-4 py-3">
          <div className="grid grid-cols-4 gap-4">
            <div className="flex flex-col items-center gap-1">
              <span className="text-xs text-muted-foreground">Flood RX</span>
              <span className="font-mono text-sm">{stats?.flood_rx ?? "—"}</span>
            </div>
            <div className="flex flex-col items-center gap-1">
              <span className="text-xs text-muted-foreground">Flood TX</span>
              <span className="font-mono text-sm">{stats?.flood_tx ?? "—"}</span>
            </div>
            <div className="flex flex-col items-center gap-1">
              <span className="text-xs text-muted-foreground">Direct RX</span>
              <span className="font-mono text-sm">{stats?.direct_rx ?? "—"}</span>
            </div>
            <div className="flex flex-col items-center gap-1">
              <span className="text-xs text-muted-foreground">Direct TX</span>
              <span className="font-mono text-sm">{stats?.direct_tx ?? "—"}</span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Signal chart */}
      {history.length > 0 && (
        <Card>
          <CardHeader className="pb-1 pt-3 px-4">
            <CardTitle className="text-sm text-muted-foreground">Signal (24h)</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-3">
            <ResponsiveContainer width="100%" height={160}>
              <LineChart data={history}>
                <XAxis
                  dataKey="timestamp"
                  tickFormatter={(v) =>
                    new Date(v as string).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })
                  }
                  tick={{ fontSize: 10 }}
                />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip />
                <Line
                  type="monotone"
                  dataKey="last_rssi"
                  stroke="#60a5fa"
                  dot={false}
                  name="RSSI"
                />
                <Line
                  type="monotone"
                  dataKey="noise_floor"
                  stroke="#f87171"
                  dot={false}
                  strokeDasharray="4 2"
                  name="Noise Floor"
                />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
