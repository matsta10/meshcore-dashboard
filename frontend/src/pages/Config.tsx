import { startTransition, useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
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

const CONFIG_CATEGORIES: { id: string; label: string; keys: string[] }[] = [
  { id: "radio", label: "Radio", keys: ["freq", "bw", "sf", "cr", "tx_power"] },
  { id: "network", label: "Network", keys: ["name"] },
  { id: "security", label: "Security", keys: ["pub.key"] },
]

const CONFIG_DESCRIPTIONS: Record<string, string> = {
  freq: "Radio frequency (MHz)",
  bw: "Bandwidth (kHz)",
  sf: "Spreading factor",
  cr: "Coding rate",
  tx_power: "Transmit power (dBm)",
  name: "Device name on mesh",
  "pub.key": "Public key (read-only)",
}

export default function Config() {
  const [config, setConfig] = useState<ConfigEntry[]>([])
  const [changelog, setChangelog] = useState<ConfigChangelogEntry[]>([])
  const [editValues, setEditValues] = useState<Record<string, string>>({})
  const [confirmValues, setConfirmValues] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refreshData = async () => {
    try {
      const [nextConfig, nextChangelog] = await Promise.all([
        api.getConfig(),
        api.getConfigChangelog(),
      ])
      const nextValues: Record<string, string> = {}
      for (const entry of nextConfig) {
        nextValues[entry.key] = entry.value
      }
      startTransition(() => {
        setConfig(nextConfig)
        setChangelog(nextChangelog)
        setEditValues(nextValues)
        setError(null)
      })
    } catch (e) {
      setError(`Failed to load config: ${e}`)
    }
  }

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const [nextConfig, nextChangelog] = await Promise.all([
          api.getConfig(),
          api.getConfigChangelog(),
        ])
        if (cancelled) return
        const nextValues: Record<string, string> = {}
        for (const entry of nextConfig) {
          nextValues[entry.key] = entry.value
        }
        startTransition(() => {
          setConfig(nextConfig)
          setChangelog(nextChangelog)
          setEditValues(nextValues)
          setError(null)
        })
      } catch (e) {
        if (!cancelled) setError(`Failed to load config: ${e}`)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const handleSave = async (key: string) => {
    setSaving(key)
    try {
      const value = editValues[key] ?? ""
      const confirm_value = CRITICAL_PARAMS.has(key)
        ? confirmValues[key]
        : undefined
      await api.setConfig(key, value, confirm_value)
      setConfirmValues((v) => ({ ...v, [key]: "" }))
      await refreshData()
    } catch (e) {
      setError(`Error saving ${key}: ${e}`)
    } finally {
      setSaving(null)
    }
  }

  const isDirty = (key: string) => {
    const orig = config.find((c) => c.key === key)
    return orig && editValues[key] !== orig.value
  }

  const configByKey = Object.fromEntries(config.map((c) => [c.key, c]))

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Configuration</h1>

      {error && (
        <div className="rounded-md border border-red-500/50 bg-red-500/10 px-3 py-1.5 text-xs text-red-400">
          {error}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Settings</CardTitle>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue={CONFIG_CATEGORIES[0].id}>
            <TabsList>
              {CONFIG_CATEGORIES.map((cat) => (
                <TabsTrigger key={cat.id} value={cat.id}>
                  {cat.label}
                </TabsTrigger>
              ))}
            </TabsList>

            {CONFIG_CATEGORIES.map((cat) => {
              const categoryKeys = cat.keys.filter((k) => k in configByKey)
              return (
                <TabsContent key={cat.id} value={cat.id}>
                  {categoryKeys.length === 0 ? (
                    <p className="py-4 text-center text-xs text-muted-foreground">
                      No settings in this category
                    </p>
                  ) : (
                    <Table>
                      <TableBody>
                        {categoryKeys.map((key) => {
                          const entry = configByKey[key]
                          return (
                            <TableRow key={key}>
                              <TableCell className="w-44 align-top py-2">
                                <span className="text-xs font-bold">{key}</span>
                                {CONFIG_DESCRIPTIONS[key] && (
                                  <p className="text-xs text-muted-foreground">
                                    {CONFIG_DESCRIPTIONS[key]}
                                  </p>
                                )}
                              </TableCell>
                              <TableCell className="py-2">
                                <div className="flex items-center gap-2">
                                  <Input
                                    value={editValues[key] ?? ""}
                                    onChange={(e) =>
                                      setEditValues((v) => ({
                                        ...v,
                                        [key]: e.target.value,
                                      }))
                                    }
                                    type={
                                      entry.value === "***"
                                        ? "password"
                                        : "text"
                                    }
                                    className="font-mono text-xs h-7 flex-1"
                                  />
                                  {CRITICAL_PARAMS.has(key) &&
                                    isDirty(key) && (
                                      <Input
                                        placeholder="Confirm value"
                                        value={confirmValues[key] ?? ""}
                                        onChange={(e) =>
                                          setConfirmValues((v) => ({
                                            ...v,
                                            [key]: e.target.value,
                                          }))
                                        }
                                        className="font-mono text-xs h-7 w-36"
                                      />
                                    )}
                                  {isDirty(key) && (
                                    <Badge
                                      variant="outline"
                                      className="text-xs shrink-0"
                                    >
                                      modified
                                    </Badge>
                                  )}
                                  <Button
                                    size="sm"
                                    onClick={() => handleSave(key)}
                                    disabled={
                                      !isDirty(key) || saving === key
                                    }
                                    className="shrink-0"
                                  >
                                    {saving === key ? "..." : "Save"}
                                  </Button>
                                </div>
                              </TableCell>
                            </TableRow>
                          )
                        })}
                      </TableBody>
                    </Table>
                  )}
                </TabsContent>
              )
            })}
          </Tabs>
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
                <TableHead>Old → New</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {changelog.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={3}
                    className="text-center text-xs text-muted-foreground py-4"
                  >
                    No changes recorded
                  </TableCell>
                </TableRow>
              ) : (
                changelog.map((entry) => (
                  <TableRow key={entry.id}>
                    <TableCell className="text-xs py-1.5">
                      {new Date(entry.timestamp).toLocaleString()}
                    </TableCell>
                    <TableCell className="font-mono text-xs py-1.5">
                      {entry.key}
                    </TableCell>
                    <TableCell className="text-xs py-1.5">
                      <span className="text-muted-foreground">
                        {entry.old_value ?? "—"}
                      </span>
                      {" → "}
                      <span>{entry.new_value}</span>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
