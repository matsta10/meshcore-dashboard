const BASE_URL = ""

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`${res.status}: ${body}`)
  }
  return res.json()
}

export const api = {
  getStatus: () => request<import("./types").StatusResponse>("/api/status"),
  getStatsCurrent: () =>
    request<import("./types").StatsResponse | null>("/api/stats/current"),
  getStatsHistory: (params: {
    metrics?: string
    resolution?: string
    start?: string
    end?: string
  }) => {
    const qs = new URLSearchParams()
    if (params.metrics) qs.set("metrics", params.metrics)
    if (params.resolution) qs.set("resolution", params.resolution)
    if (params.start) qs.set("start", params.start)
    if (params.end) qs.set("end", params.end)
    return request<{ data: import("./types").StatsResponse[] }>(
      `/api/stats/history?${qs}`
    )
  },
  getConfig: () => request<import("./types").ConfigEntry[]>("/api/config"),
  getConfigChangelog: () =>
    request<import("./types").ConfigChangelogEntry[]>("/api/config/changelog"),
  setConfig: (key: string, value: string, confirm_value?: string) =>
    request<import("./types").ConfigChangelogEntry>(`/api/config/${key}`, {
      method: "PUT",
      body: JSON.stringify({ value, confirm_value }),
    }),
  readClock: () =>
    request<import("./types").ClockReadResponse>("/api/admin/clock/read", {
      method: "POST",
    }),
  syncClock: () =>
    request<import("./types").AdminActionResponse>("/api/admin/clock/sync", {
      method: "POST",
    }),
  setClock: (epoch_seconds: number) =>
    request<import("./types").AdminActionResponse>("/api/admin/clock/set", {
      method: "POST",
      body: JSON.stringify({ epoch_seconds }),
    }),
  getNeighbors: () =>
    request<import("./types").NeighborResponse[]>("/api/neighbors"),
  getLogs: (limit = 100, offset = 0) =>
    request<import("./types").PacketLogEntry[]>(
      `/api/logs?limit=${limit}&offset=${offset}`
    ),
}
