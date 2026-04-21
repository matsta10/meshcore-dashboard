import { startTransition, useEffect, useState } from "react"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
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
import type {
  AdminActionResponse,
  ConfigCategory,
  ConfigChangelogEntry,
  ConfigEntry,
} from "@/lib/types"

const CRITICAL_PARAMS = new Set(["freq", "bw", "sf", "cr", "tx_power", "password"])

const CONFIG_CATEGORIES: ConfigCategory[] = [
  {
    id: "radio",
    label: "Radio",
    keys: ["freq", "bw", "sf", "cr", "tx_power", "radio.rxgain"],
  },
  { id: "network", label: "Network", keys: ["name", "lat", "lon"] },
  {
    id: "security",
    label: "Security",
    keys: ["pub.key", "guest.password"],
  },
  {
    id: "system",
    label: "System",
    keys: ["owner.info", "adc.multiplier", "powersaving", "password", "guest"],
  },
]

const CONFIG_DESCRIPTIONS: Record<string, string> = {
  freq: "Radio frequency (MHz)",
  bw: "Bandwidth (kHz)",
  sf: "Spreading factor",
  cr: "Coding rate",
  tx_power: "Transmit power (dBm)",
  "radio.rxgain": "Boosted receive gain mode on supported SX12xx radios",
  name: "Device name on mesh",
  lat: "Latitude for the node's reported position",
  lon: "Longitude for the node's reported position",
  "pub.key": "Public key (read-only)",
  "guest.password": "Guest access password (masked)",
  "owner.info": "Operator or site information broadcast by the node",
  "adc.multiplier": "Board-specific battery calibration factor",
  powersaving: "Repeater power-saving mode",
  password: "Admin password (masked)",
  guest: "Guest password (masked)",
}

function formatTimestamp(value: string): string {
  const parsed = Date.parse(value)
  if (Number.isNaN(parsed)) return "—"
  return new Date(parsed).toLocaleString()
}

function epochSecondsFromTimestamp(value: string | null): number | null {
  if (!value) return null
  const parsed = Date.parse(value)
  if (Number.isNaN(parsed)) return null
  return Math.floor(parsed / 1000)
}

function buildEditValues(entries: ConfigEntry[]): Record<string, string> {
  return Object.fromEntries(entries.map((entry) => [entry.key, entry.value]))
}

async function loadConfigData(): Promise<{
  config: ConfigEntry[]
  changelog: ConfigChangelogEntry[]
  editValues: Record<string, string>
}> {
  const [config, changelog] = await Promise.all([
    api.getConfig(),
    api.getConfigChangelog(),
  ])
  return {
    config,
    changelog,
    editValues: buildEditValues(config),
  }
}

function getCategoryKeys(
  category: ConfigCategory,
  config: ConfigEntry[],
  configByKey: Record<string, ConfigEntry>,
  assignedKeys: Set<string>
): string[] {
  if (category.id !== "system") {
    return category.keys.filter((key) => key in configByKey)
  }

  const uncategorizedKeys = config
    .map((entry) => entry.key)
    .filter((key) => !assignedKeys.has(key))

  return [...new Set([...category.keys, ...uncategorizedKeys])].filter(
    (key) => key in configByKey
  )
}

type VisibleCategory = ConfigCategory & {
  visibleKeys: string[]
}

export default function Config() {
  const [config, setConfig] = useState<ConfigEntry[]>([])
  const [changelog, setChangelog] = useState<ConfigChangelogEntry[]>([])
  const [editValues, setEditValues] = useState<Record<string, string>>({})
  const [confirmValues, setConfirmValues] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [clockOutput, setClockOutput] = useState<string>("Loading…")
  const [clockBusy, setClockBusy] = useState<"read" | "sync" | "set" | null>(null)
  const [clockNotice, setClockNotice] = useState<string | null>(null)
  const [serverNow, setServerNow] = useState<string | null>(null)

  const refreshData = async () => {
    try {
      const nextData = await loadConfigData()
      startTransition(() => {
        setConfig(nextData.config)
        setChangelog(nextData.changelog)
        setEditValues(nextData.editValues)
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
        const nextData = await loadConfigData()
        if (cancelled) return
        startTransition(() => {
          setConfig(nextData.config)
          setChangelog(nextData.changelog)
          setEditValues(nextData.editValues)
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

  useEffect(() => {
    let cancelled = false

    const loadClock = async () => {
      setClockBusy("read")
      try {
        const [clock, stats] = await Promise.all([
          api.readClock(),
          api.getStatsCurrent(),
        ])
        if (cancelled) return
        startTransition(() => {
          setClockOutput(clock.output.trim() || "—")
          setServerNow(stats?.timestamp ?? null)
          setClockNotice(null)
        })
      } catch (e) {
        if (!cancelled) {
          setClockNotice(`Failed to load admin clock state: ${e}`)
        }
      } finally {
        if (!cancelled) setClockBusy(null)
      }
    }

    void loadClock()
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

  const updateEditValue = (key: string, value: string) => {
    setEditValues((current) => ({ ...current, [key]: value }))
  }

  const updateConfirmValue = (key: string, value: string) => {
    setConfirmValues((current) => ({ ...current, [key]: value }))
  }

  const configByKey = Object.fromEntries(config.map((c) => [c.key, c]))
  const assignedKeys = new Set(
    CONFIG_CATEGORIES.flatMap((category) => category.keys)
  )
  const visibleCategories: VisibleCategory[] = CONFIG_CATEGORIES.map(
    (category) => ({
      ...category,
      visibleKeys: getCategoryKeys(category, config, configByKey, assignedKeys),
    })
  ).filter((category) => category.visibleKeys.length > 0)

  const refreshClock = async () => {
    const [clock, stats] = await Promise.all([
      api.readClock(),
      api.getStatsCurrent(),
    ])
    startTransition(() => {
      setClockOutput(clock.output.trim() || "—")
      setServerNow(stats?.timestamp ?? null)
    })
  }

  const performClockAction = async (
    action: "sync" | "set",
    request: Promise<AdminActionResponse>
  ) => {
    setClockBusy(action)
    setClockNotice(null)
    try {
      const response = await request
      setClockNotice(response.detail)
      await refreshClock()
    } catch (e) {
      setClockNotice(`Clock action failed: ${e}`)
    } finally {
      setClockBusy(null)
    }
  }

  const serverEpochSeconds = epochSecondsFromTimestamp(serverNow)

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
          <CardTitle>Admin</CardTitle>
          <CardDescription>
            Low-frequency control actions. Operational status stays on the
            dashboard; one-off admin actions live here.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-start">
            <div className="space-y-2">
              <div>
                <p className="text-xs uppercase tracking-wide text-muted-foreground">
                  Device clock
                </p>
                <p className="font-mono text-xs whitespace-pre-wrap break-words">
                  {clockOutput}
                </p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-wide text-muted-foreground">
                  Server time
                </p>
                <p className="font-mono text-xs">{formatTimestamp(serverNow ?? "")}</p>
              </div>
              {clockNotice && (
                <p className="text-xs text-muted-foreground">{clockNotice}</p>
              )}
            </div>
            <div className="flex flex-wrap gap-2 md:justify-end">
              <Button
                size="sm"
                onClick={() => performClockAction("sync", api.syncClock())}
                disabled={clockBusy !== null}
              >
                {clockBusy === "sync" ? "Syncing..." : "Sync Clock"}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() =>
                  performClockAction(
                    "set",
                    api.setClock(serverEpochSeconds ?? 0)
                  )
                }
                disabled={clockBusy !== null || serverEpochSeconds === null}
              >
                {clockBusy === "set" ? "Setting..." : "Set to Now"}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Settings</CardTitle>
          <CardDescription>
            Radio, network, security, and system settings synced from the
            repeater.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue={visibleCategories[0]?.id}>
            <TabsList variant="line">
              {visibleCategories.map((cat) => (
                <TabsTrigger key={cat.id} value={cat.id}>
                  {cat.label}
                </TabsTrigger>
              ))}
            </TabsList>

            {visibleCategories.length === 0 ? (
              <p className="py-4 text-center text-xs text-muted-foreground">
                No synced configuration values available from this repeater yet.
              </p>
            ) : null}

            {visibleCategories.map((cat) => {
              return (
                <TabsContent key={cat.id} value={cat.id} className="pt-2">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-44">Setting</TableHead>
                        <TableHead>Value</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {cat.visibleKeys.map((key) => {
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
                                    updateEditValue(key, e.target.value)
                                  }
                                  type={
                                    entry.value === "***" ? "password" : "text"
                                  }
                                  className="font-mono text-xs h-7 flex-1"
                                />
                                {CRITICAL_PARAMS.has(key) && isDirty(key) && (
                                  <Input
                                    placeholder="Confirm value"
                                    value={confirmValues[key] ?? ""}
                                    onChange={(e) =>
                                      updateConfirmValue(key, e.target.value)
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
                                  disabled={!isDirty(key) || saving === key}
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
                </TabsContent>
              )
            })}
          </Tabs>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Change History</CardTitle>
          <CardDescription>
            Dashboard-applied config writes, newest first.
          </CardDescription>
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
                      {formatTimestamp(entry.timestamp)}
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
