import { startTransition, useEffect, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import { api } from "@/lib/api"
import type { PacketLogEntry } from "@/lib/types"
import { useWebSocket } from "@/hooks/useWebSocket"
import { cn } from "@/lib/utils"

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
  if (log.device_time_text) {
    return log.device_time_text
  }
  const parsed = Date.parse(log.collected_at)
  if (Number.isNaN(parsed)) return "—"
  return new Date(parsed).toLocaleString()
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
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Packet Logs</h1>
        <Badge variant="outline">{logs.length} entries</Badge>
      </div>

      <Card>
        <CardContent className="p-0">
          <div className="max-h-[calc(100vh-10rem)] overflow-y-auto divide-y divide-border">
            {logs.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                Waiting for packet logs from the device.
              </p>
            ) : null}
            {logs.map((log) => {
              if (log.parse_status === "raw_only") {
                return (
                  <div
                    key={log.id}
                    className="px-3 py-1.5 font-mono text-xs text-muted-foreground break-all"
                  >
                    {log.raw_line}
                  </div>
                )
              }

              const isRx = log.direction === "RX"
              const typeName = formatPacketType(log)

              return (
                <div key={log.id} className="px-3 py-2 flex gap-3">
                  {/* Left: type badge + details */}
                  <div className="flex-1 min-w-0 space-y-0.5">
                    {/* Header line: route badge + type name */}
                    <div className="flex items-center gap-2">
                      <span
                        className={cn(
                          "inline-flex items-center justify-center w-5 h-5 rounded text-[10px] font-bold shrink-0",
                          log.route === "D"
                            ? "bg-purple-500/20 text-purple-400"
                            : "bg-blue-500/20 text-blue-400"
                        )}
                      >
                        {log.route ?? "?"}
                      </span>
                      <span className="font-mono text-xs font-semibold truncate">
                        {typeName}
                      </span>
                      <span
                        className={cn(
                          "text-[10px] font-mono",
                          log.direction === "TX"
                            ? "text-green-400"
                            : "text-blue-400"
                        )}
                      >
                        {log.direction}
                      </span>
                    </div>

                    {/* Detail line */}
                    <div className="font-mono text-[11px] text-muted-foreground flex flex-wrap gap-x-3">
                      <span>{formatLogTime(log)}</span>
                      <span>
                        {log.total_len ?? log.payload_len ?? "?"} bytes
                      </span>
                      {log.src_addr && log.dst_addr && (
                        <span>
                          &lt;{log.src_addr}&gt; → &lt;{log.dst_addr}&gt;
                        </span>
                      )}
                      {log.score != null && log.score < 1000 && (
                        <span className="text-yellow-400">
                          score={log.score}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Right: SNR */}
                  {isRx && log.snr != null && (
                    <div className="shrink-0 text-right">
                      <span className="font-mono text-xs font-semibold text-green-400">
                        {log.snr.toFixed(1)}dB
                      </span>
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
