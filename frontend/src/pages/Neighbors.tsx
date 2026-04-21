import { startTransition, useEffect, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { api } from "@/lib/api"
import type { NeighborResponse } from "@/lib/types"
import { useWebSocket } from "@/hooks/useWebSocket"

function relativeTime(dateStr: string): string {
  const now = Date.now()
  const then = new Date(dateStr).getTime()
  if (Number.isNaN(then)) return "—"
  const diffSecs = Math.floor((now - then) / 1000)
  if (diffSecs < 60) return `${diffSecs}s ago`
  const diffMins = Math.floor(diffSecs / 60)
  if (diffMins < 60) return `${diffMins}m ago`
  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) return `${diffHours}h ago`
  const diffDays = Math.floor(diffHours / 24)
  return `${diffDays}d ago`
}

export default function Neighbors() {
  const [neighbors, setNeighbors] = useState<NeighborResponse[]>([])
  const { lastMessage } = useWebSocket()

  useEffect(() => {
    let cancelled = false
    void api.getNeighbors().then((nextNeighbors) => {
      if (cancelled) return
      startTransition(() => {
        setNeighbors(nextNeighbors)
      })
    })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (lastMessage?.type === "neighbor_update") {
      void api.getNeighbors().then((nextNeighbors) => {
        startTransition(() => {
          setNeighbors(nextNeighbors)
        })
      })
    }
  }, [lastMessage])

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold">Neighbors</h1>
        <Badge variant="secondary">{neighbors.length}</Badge>
      </div>

      <Card>
        <CardContent className="p-0">
          <div className="border-b px-4 py-3">
            <CardDescription>
              Based on recent zero-hop adverts heard by this repeater, not a
              full mesh topology map.
            </CardDescription>
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Public Key</TableHead>
                <TableHead>SNR</TableHead>
                <TableHead>First Seen</TableHead>
                <TableHead>Last Seen</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {neighbors.map((n) => (
                <TableRow key={n.public_key}>
                  <TableCell
                    className="max-w-0 truncate font-mono text-xs"
                    title={n.public_key}
                  >
                    {n.public_key}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {n.last_snr?.toFixed(1) ?? "—"} dB
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {relativeTime(n.first_seen)}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {relativeTime(n.last_seen)}
                  </TableCell>
                </TableRow>
              ))}
              {neighbors.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={4}
                    className="text-center text-muted-foreground"
                  >
                    No neighbors discovered yet
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
