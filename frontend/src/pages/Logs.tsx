import { startTransition, useEffect, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { api } from "@/lib/api"
import type { PacketLogEntry } from "@/lib/types"
import { useWebSocket } from "@/hooks/useWebSocket"
import { cn } from "@/lib/utils"

const FETCH_LIMIT = 500

/**
 * Format collected_at timestamp, returning "—" for invalid dates.
 */
function formatCollectedAt(value: string): string {
  const parsed = Date.parse(value)
  if (Number.isNaN(parsed)) return "—"
  return new Date(parsed).toLocaleString()
}

/**
 * Return the best available time label for a log entry.
 * Prefers device_time_text, falls back to collected_at, never shows "Invalid Date".
 */
function formatLogTime(log: PacketLogEntry): string {
  if (log.device_time_text) {
    return log.device_date_text
      ? `${log.device_time_text} · ${log.device_date_text}`
      : log.device_time_text
  }
  return formatCollectedAt(log.collected_at)
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
          <div className="max-h-[calc(100vh-10rem)] overflow-y-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-44">Time</TableHead>
                  <TableHead className="w-12">Dir</TableHead>
                  <TableHead className="w-14">Type</TableHead>
                  <TableHead className="w-14">Route</TableHead>
                  <TableHead className="w-14">Size</TableHead>
                  <TableHead className="w-16">SNR</TableHead>
                  <TableHead className="w-16">RSSI</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {logs.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={7}
                      className="py-8 text-center text-sm text-muted-foreground"
                    >
                      Waiting for packet logs from the device.
                    </TableCell>
                  </TableRow>
                ) : null}
                {logs.map((log) => {
                  if (log.parse_status === "raw_only") {
                    return (
                      <TableRow key={log.id}>
                        <TableCell
                          colSpan={7}
                          className="py-1 font-mono text-xs text-muted-foreground break-all"
                        >
                          {log.raw_line}
                        </TableCell>
                      </TableRow>
                    )
                  }

                  const isRx = log.direction === "RX"

                  return (
                    <TableRow key={log.id}>
                      <TableCell className="py-1 font-mono text-xs">
                        {formatLogTime(log)}
                      </TableCell>
                      <TableCell className="py-1 font-mono text-xs">
                        <span
                          className={cn(
                            log.direction === "TX" && "text-green-400",
                            log.direction === "RX" && "text-blue-400"
                          )}
                        >
                          {log.direction ?? "—"}
                        </span>
                      </TableCell>
                      <TableCell className="py-1 font-mono text-xs">
                        {log.packet_type ?? "—"}
                      </TableCell>
                      <TableCell className="py-1 font-mono text-xs">
                        {log.route ?? "—"}
                      </TableCell>
                      <TableCell className="py-1 font-mono text-xs">
                        {log.payload_len ?? "—"}
                      </TableCell>
                      <TableCell className="py-1 font-mono text-xs">
                        {isRx ? (log.snr ?? "—") : "—"}
                      </TableCell>
                      <TableCell className="py-1 font-mono text-xs">
                        {isRx ? (log.rssi ?? "—") : "—"}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
