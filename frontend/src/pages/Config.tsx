import { useCallback, useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { api } from "@/lib/api"
import type { ConfigChangelogEntry, ConfigEntry } from "@/lib/types"

const CRITICAL_PARAMS = new Set(["freq", "bw", "sf", "cr", "tx_power"])

export default function Config() {
  const [config, setConfig] = useState<ConfigEntry[]>([])
  const [changelog, setChangelog] = useState<ConfigChangelogEntry[]>([])
  const [editValues, setEditValues] = useState<Record<string, string>>({})
  const [confirmValues, setConfirmValues] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    const [c, cl] = await Promise.all([
      api.getConfig(),
      api.getConfigChangelog(),
    ])
    setConfig(c)
    setChangelog(cl)
    const vals: Record<string, string> = {}
    for (const entry of c) {
      vals[entry.key] = entry.value
    }
    setEditValues(vals)
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const handleSave = async (key: string) => {
    setSaving(key)
    try {
      const value = editValues[key] ?? ""
      const confirm_value = CRITICAL_PARAMS.has(key)
        ? confirmValues[key]
        : undefined
      await api.setConfig(key, value, confirm_value)
      await fetchData()
    } catch (e) {
      alert(`Error: ${e}`)
    } finally {
      setSaving(null)
    }
  }

  const handleRevert = async (key: string) => {
    try {
      await api.revertConfig(key)
      await fetchData()
    } catch (e) {
      alert(`Error: ${e}`)
    }
  }

  const isDirty = (key: string) => {
    const orig = config.find((c) => c.key === key)
    return orig && editValues[key] !== orig.value
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Configuration</h1>

      <Card>
        <CardHeader>
          <CardTitle>Settings</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {config.map((entry) => (
            <div
              key={entry.key}
              className="flex items-center gap-3 border-b pb-3"
            >
              <div className="w-40 shrink-0">
                <span className="text-sm font-medium">{entry.key}</span>
                {isDirty(entry.key) && (
                  <Badge variant="outline" className="ml-2 text-xs">
                    modified
                  </Badge>
                )}
              </div>
              <Input
                value={editValues[entry.key] ?? ""}
                onChange={(e) =>
                  setEditValues((v) => ({ ...v, [entry.key]: e.target.value }))
                }
                type={entry.value === "***" ? "password" : "text"}
                className="flex-1"
              />
              {CRITICAL_PARAMS.has(entry.key) && isDirty(entry.key) && (
                <Input
                  placeholder="Confirm value"
                  value={confirmValues[entry.key] ?? ""}
                  onChange={(e) =>
                    setConfirmValues((v) => ({
                      ...v,
                      [entry.key]: e.target.value,
                    }))
                  }
                  className="w-40"
                />
              )}
              <Button
                size="sm"
                onClick={() => handleSave(entry.key)}
                disabled={!isDirty(entry.key) || saving === entry.key}
              >
                {saving === entry.key ? "..." : "Save"}
              </Button>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Change History</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Time</TableHead>
                <TableHead>Key</TableHead>
                <TableHead>Old</TableHead>
                <TableHead>New</TableHead>
                <TableHead>Source</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {changelog.map((entry) => (
                <TableRow key={entry.id}>
                  <TableCell className="text-xs">
                    {new Date(entry.timestamp).toLocaleString()}
                  </TableCell>
                  <TableCell className="font-mono text-sm">
                    {entry.key}
                  </TableCell>
                  <TableCell className="text-sm">
                    {entry.old_value ?? "—"}
                  </TableCell>
                  <TableCell className="text-sm">{entry.new_value}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{entry.source}</Badge>
                  </TableCell>
                  <TableCell>
                    {entry.old_value && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => handleRevert(entry.key)}
                      >
                        Revert
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
