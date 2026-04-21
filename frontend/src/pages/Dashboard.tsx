import { startTransition, useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
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
  const { lastMessage, connected } = useWebSocket()

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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">
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

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">
              Battery
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{stats?.battery_mv ?? "—"} mV</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">
              Uptime
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">
              {formatUptime(stats?.uptime_secs ?? null)}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">RSSI</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">
              {stats?.last_rssi ?? "—"} dBm
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">SNR</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">
              {stats?.last_snr?.toFixed(1) ?? "—"} dB
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">
              Noise Floor
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">
              {stats?.noise_floor ?? "—"} dBm
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">
              Queue
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{stats?.queue_len ?? "—"}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">
              Packets RX
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{stats?.packets_recv ?? "—"}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">
              Packets TX
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{stats?.packets_sent ?? "—"}</p>
          </CardContent>
        </Card>
      </div>

      {/* Sparkline Chart */}
      {history.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Signal (24h)</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={history}>
                <XAxis
                  dataKey="timestamp"
                  tickFormatter={(v) =>
                    new Date(v).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })
                  }
                />
                <YAxis />
                <Tooltip />
                <Line
                  type="monotone"
                  dataKey="last_rssi"
                  stroke="#3b82f6"
                  dot={false}
                  name="RSSI"
                />
                <Line
                  type="monotone"
                  dataKey="noise_floor"
                  stroke="#ef4444"
                  dot={false}
                  name="Noise"
                />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
