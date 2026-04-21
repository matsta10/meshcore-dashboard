import { startTransition, useEffect, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription } from "@/components/ui/card"
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  EmptyDescription,
} from "@/components/ui/empty"
import { api } from "@/lib/api"
import type { PacketLogEntry } from "@/lib/types"
import { useWebSocket } from "@/hooks/useWebSocket"
import { ScrollTextIcon } from "lucide-react"

const FETCH_LIMIT = 500

/** MeshCore over-the-air payload type names (from Packet.h) */
const PACKET_TYPE_NAMES: Record<number, string> = {
  0: "REQ",
  1: "RESPONSE",
  2: "TXT_MSG",
  3: "ACK",
  4: "ADVERT",
  5: "GRP_TXT",
  6: "GRP_DATA",
  7: "ANON_REQ",
  8: "PATH",
  9: "TRACE",
  10: "MULTIPART",
  11: "CONTROL",
  15: "RAW_CUSTOM",
}

const ROUTE_NAMES: Record<string, string> = {
  F: "FLOOD",
  D: "DIRECT",
}

function formatPacketType(log: PacketLogEntry): string {
  const route = log.route ? (ROUTE_NAMES[log.route] ?? log.route) : ""
  const type =
    log.packet_type != null
      ? (PACKET_TYPE_NAMES[log.packet_type] ?? `TYPE_${log.packet_type}`)
      : "UNKNOWN"
  return route ? `${route} ${type}` : type
}

function formatLogTime(log: PacketLogEntry): string {
  const parsed = Date.parse(log.collected_at)
  if (Number.isNaN(parsed)) return "—"
  return new Date(parsed).toLocaleString()
}

function formatDeviceClock(log: PacketLogEntry): string | null {
  const parts = [log.device_time_text, log.device_date_text].filter(Boolean)
  if (parts.length === 0) return null
  return parts.join(" · ")
}

export default function Logs() {
  const [logs, setLogs] = useState<PacketLogEntry[]>([])
  const { lastMessage } = useWebSocket()

  const refreshLogs = async () => {
    const nextLogs = await api.getLogs(FETCH_LIMIT)
    startTransition(() => {
      setLogs(nextLogs)
    })
  }

  useEffect(() => {
    let cancelled = false
    void api.getLogs(FETCH_LIMIT).then((nextLogs) => {
      if (cancelled) return
      startTransition(() => {
        setLogs(nextLogs)
      })
    })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (lastMessage?.type === "logs_update") {
      void refreshLogs()
    }
  }, [lastMessage])

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Packet Logs</h1>
        <Badge variant="outline">Showing {logs.length} recent</Badge>
      </div>

      <Card>
        <div className="border-b px-4 py-3">
          <CardDescription>
            Route: <span className="font-mono">F</span> flood,{" "}
            <span className="font-mono">D</span> direct. ADVERT, PATH, TRACE,
            and CONTROL entries are routing or control metadata rather than
            user messages.
          </CardDescription>
        </div>
        <CardContent className="p-0">
          <div className="max-h-[calc(100vh-10rem)] overflow-y-auto divide-y divide-border">
            {logs.length === 0 ? (
              <Empty>
                <EmptyHeader>
                  <EmptyMedia variant="icon">
                    <ScrollTextIcon />
                  </EmptyMedia>
                  <EmptyTitle>No packet logs yet</EmptyTitle>
                  <EmptyDescription>
                    Logs will appear once the collector starts polling the
                    device.
                  </EmptyDescription>
                </EmptyHeader>
              </Empty>
            ) : null}
            {logs.map((log) => {
              if (log.parse_status === "raw_only") {
                const deviceClock = formatDeviceClock(log)
                return (
                  <div key={log.id} className="px-3 py-2 flex flex-col gap-1">
                    <div className="font-mono text-[11px] text-muted-foreground flex flex-wrap gap-x-3">
                      <span>{formatLogTime(log)}</span>
                      {deviceClock && (
                        <span className="text-[10px]">
                          device {deviceClock}
                        </span>
                      )}
                    </div>
                    <div className="font-mono text-xs text-muted-foreground break-all">
                      {log.raw_line}
                    </div>
                  </div>
                )
              }

              const isRx = log.direction === "RX"
              const typeName = formatPacketType(log)
              const deviceClock = formatDeviceClock(log)

              return (
                <div key={log.id} className="px-3 py-2 flex gap-3">
                  {/* Left: type badge + details */}
                  <div className="flex-1 min-w-0 flex flex-col gap-0.5">
                    {/* Header line: route badge + type name */}
                    <div className="flex items-center gap-2">
                      <Badge
                        variant="outline"
                        className="size-5 justify-center text-[10px] font-bold shrink-0 p-0"
                      >
                        {log.route ?? "?"}
                      </Badge>
                      <span className="font-mono text-xs font-semibold truncate">
                        {typeName}
                      </span>
                      <Badge variant="secondary" className="text-[10px] font-mono">
                        {log.direction}
                      </Badge>
                    </div>

                    {/* Detail line */}
                    <div className="font-mono text-[11px] text-muted-foreground flex flex-wrap gap-x-3">
                      <span>{formatLogTime(log)}</span>
                      {deviceClock && (
                        <span className="text-[10px]">
                          device {deviceClock}
                        </span>
                      )}
                      <span>
                        {log.total_len ?? log.payload_len ?? "?"} bytes
                      </span>
                      {log.src_addr && log.dst_addr && (
                        <span>
                          &lt;{log.src_addr}&gt; → &lt;{log.dst_addr}&gt;
                        </span>
                      )}
                      {log.score != null && log.score < 1000 && (
                        <Badge variant="outline" className="text-[10px]">
                          score={log.score}
                        </Badge>
                      )}
                    </div>
                  </div>

                  {/* Right: SNR */}
                  {isRx && log.snr != null && (
                    <div className="shrink-0 text-right">
                      <Badge variant="secondary" className="font-mono text-xs font-semibold">
                        {log.snr.toFixed(1)}dB
                      </Badge>
                      {log.rssi != null && (
                        <p className="font-mono text-[10px] text-muted-foreground">
                          {log.rssi}dBm
                        </p>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
