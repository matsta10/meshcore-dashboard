import { startTransition, useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { Input } from "@/components/ui/input"
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

export default function Logs() {
  const [logs, setLogs] = useState<PacketLogEntry[]>([])
  const [logging, setLogging] = useState(false)
  const [eraseConfirm, setEraseConfirm] = useState("")

  useEffect(() => {
    let cancelled = false
    void api.getLogs().then((nextLogs) => {
      if (cancelled) return
      startTransition(() => {
        setLogs(nextLogs)
      })
    })
    return () => {
      cancelled = true
    }
  }, [])

  const handleToggleLogging = async (enabled: boolean) => {
    if (enabled) {
      await api.startLogging()
    } else {
      await api.stopLogging()
    }
    setLogging(enabled)
  }

  const handleFetch = async () => {
    await api.fetchLogs()
    const nextLogs = await api.getLogs()
    startTransition(() => {
      setLogs(nextLogs)
    })
  }

  const handleErase = async () => {
    if (eraseConfirm !== "erase") return
    await api.eraseLogs()
    setEraseConfirm("")
    const nextLogs = await api.getLogs()
    startTransition(() => {
      setLogs(nextLogs)
    })
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Packet Logs</h1>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="text-sm">Logging</span>
            <Switch checked={logging} onCheckedChange={handleToggleLogging} />
          </div>
          <Button onClick={handleFetch}>Fetch from device</Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{logs.length} entries</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="max-h-[500px] overflow-y-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-40">Time</TableHead>
                  <TableHead>Line</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {logs.map((log) => (
                  <TableRow key={log.id}>
                    <TableCell className="text-xs whitespace-nowrap">
                      {new Date(log.collected_at).toLocaleString()}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {log.raw_line}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-destructive">Danger Zone</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center gap-3">
          <Input
            placeholder='Type "erase" to confirm'
            value={eraseConfirm}
            onChange={(e) => setEraseConfirm(e.target.value)}
            className="w-48"
          />
          <Button
            variant="destructive"
            onClick={handleErase}
            disabled={eraseConfirm !== "erase"}
          >
            Erase Device Logs
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
