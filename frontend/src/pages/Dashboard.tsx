import { useCallback, useEffect, useRef, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { api } from "@/lib/api"
import type { StatsResponse, StatusResponse } from "@/lib/types"
import { useWebSocket } from "@/hooks/useWebSocket"
import { usePageVisibility } from "@/hooks/usePageVisibility"
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

function ConnectionBadge({ state }: { state: string }) {
  const color =
    state === "connected"
      ? "bg-green-500"
      : state === "unresponsive"
        ? "bg-yellow-500"
        : "bg-red-500"
  return (
    <Badge variant="outline" className="gap-1.5">
      <span className={`h-2 w-2 rounded-full ${color}`} />
      {state}
    </Badge>
  )
}

export default function Dashboard() {
  const [status, setStatus] = useState<StatusResponse | null>(null)
  const [stats, setStats] = useState<StatsResponse | null>(null)
  const [history, setHistory] = useState<StatsResponse[]>([])
  const [liveMode, setLiveMode] = useState(false)
  const { lastMessage, send } = useWebSocket()
  const visible = usePageVisibility()
  const renewalRef = useRef<ReturnType<typeof setInterval>>(null)

  const fetchData = useCallback(async () => {
    const [s, st] = await Promise.all([api.getStatus(), api.getStatsCurrent()])
    setStatus(s)
    setStats(st)
  }, [])

  useEffect(() => {
    fetchData()
    api
      .getStatsHistory({
        metrics: "battery_mv,noise_floor,last_rssi,last_snr",
        resolution: "hourly",
      })
      .then((r) => setHistory(r.data))
  }, [fetchData])

  // Update stats from WS
  useEffect(() => {
    if (lastMessage?.type === "stats_update") {
      setStats(lastMessage.data as unknown as StatsResponse)
    }
  }, [lastMessage])

  // Live mode TTL renewal
  useEffect(() => {
    if (liveMode && visible) {
      send({ type: "set_live_mode", data: { enabled: true } })
      renewalRef.current = setInterval(() => {
        send({ type: "set_live_mode", data: { enabled: true } })
      }, 15000)
    } else {
      if (renewalRef.current) clearInterval(renewalRef.current)
      if (!visible && liveMode) {
        send({ type: "set_live_mode", data: { enabled: false } })
      }
    }
    return () => {
      if (renewalRef.current) clearInterval(renewalRef.current)
    }
  }, [liveMode, visible, send])

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
          <ConnectionBadge state={status?.connection_state ?? "disconnected"} />
          <div className="flex items-center gap-2">
            <span className="text-sm">Live</span>
            <Switch checked={liveMode} onCheckedChange={setLiveMode} />
          </div>
        </div>
      </div>

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
