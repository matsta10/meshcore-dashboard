import { startTransition, useEffect, useState } from "react"
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

export default function Dashboard() {
  const [status, setStatus] = useState<StatusResponse | null>(null)
  const [stats, setStats] = useState<StatsResponse | null>(null)
  const [history, setHistory] = useState<StatsResponse[]>([])
  const [stale, setStale] = useState(false)
  const { lastMessage, connected, send } = useWebSocket()

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
