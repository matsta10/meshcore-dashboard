import { useCallback, useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
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

export default function Neighbors() {
  const [neighbors, setNeighbors] = useState<NeighborResponse[]>([])
  const [discovering, setDiscovering] = useState(false)
  const { lastMessage } = useWebSocket()

  const fetchData = useCallback(async () => {
    setNeighbors(await api.getNeighbors())
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  useEffect(() => {
    if (lastMessage?.type === "neighbor_update") {
      fetchData()
    }
  }, [lastMessage, fetchData])

  const handleDiscover = async () => {
    setDiscovering(true)
    try {
      await api.discoverNeighbors()
    } finally {
      setTimeout(() => {
        setDiscovering(false)
        fetchData()
      }, 5000)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Neighbors</h1>
        <Button onClick={handleDiscover} disabled={discovering}>
          {discovering ? "Discovering..." : "Discover"}
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>
            {neighbors.length} neighbor{neighbors.length !== 1 && "s"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Public Key</TableHead>
                <TableHead>RSSI</TableHead>
                <TableHead>SNR</TableHead>
                <TableHead>First Seen</TableHead>
                <TableHead>Last Seen</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {neighbors.map((n) => (
                <TableRow key={n.public_key}>
                  <TableCell className="font-medium">
                    {n.name ?? "Unknown"}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {n.public_key.slice(0, 12)}...
                  </TableCell>
                  <TableCell>{n.last_rssi ?? "—"} dBm</TableCell>
                  <TableCell>{n.last_snr?.toFixed(1) ?? "—"} dB</TableCell>
                  <TableCell className="text-xs">
                    {new Date(n.first_seen).toLocaleDateString()}
                  </TableCell>
                  <TableCell className="text-xs">
                    {new Date(n.last_seen).toLocaleString()}
                  </TableCell>
                </TableRow>
              ))}
              {neighbors.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-muted-foreground">
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
