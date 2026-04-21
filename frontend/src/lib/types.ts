export interface StatsResponse {
  timestamp: string
  battery_mv: number | null
  uptime_secs: number | null
  queue_len: number | null
  errors: number | null
  noise_floor: number | null
  last_rssi: number | null
  last_snr: number | null
  tx_air_secs: number | null
  rx_air_secs: number | null
  packets_recv: number | null
  packets_sent: number | null
  flood_rx: number | null
  flood_tx: number | null
  direct_rx: number | null
  direct_tx: number | null
  recv_errors: number | null
  stale: boolean
  freshness: "fresh" | "partial" | "stale"
  stale_reason: string | null
  stats_health: Record<string, CommandHealthResponse>
}

export interface StatusResponse {
  connection_state: "connected" | "unresponsive" | "disconnected"
  device_info: DeviceInfoResponse | null
  consecutive_failures: number
  telemetry: TelemetryHealthResponse | null
}

export interface CommandHealthResponse {
  ok: boolean
  last_success_at: string | null
  last_error: string | null
}

export interface LogCollectorHealthResponse {
  last_log_poll_at: string | null
  last_log_insert_at: string | null
  unchanged_buffer_count: number
  last_log_buffer_hash: string | null
  last_log_error: string | null
}

export interface TelemetryHealthResponse {
  stats: Record<string, CommandHealthResponse>
  logs: LogCollectorHealthResponse
}

export interface DeviceInfoResponse {
  name: string | null
  firmware_ver: string | null
  board: string | null
  public_key: string | null
  radio_freq: number | null
  radio_bw: number | null
  radio_sf: number | null
  radio_cr: number | null
  tx_power: number | null
}

export interface ConfigEntry {
  key: string
  value: string
  updated_at: string
}

export interface ConfigChangelogEntry {
  id: number
  timestamp: string
  key: string
  old_value: string | null
  new_value: string
  source: string
}

export interface ConfigCategory {
  id: string
  label: string
  keys: string[]
}

export interface ClockReadResponse {
  output: string
}

export interface AdminActionResponse {
  detail: string
}

export interface NeighborResponse {
  public_key: string
  name: string | null
  first_seen: string
  last_seen: string
  last_rssi: number | null
  last_snr: number | null
}

export interface PacketLogEntry {
  id: number
  collected_at: string
  raw_line: string
  fingerprint: string | null
  parse_status: string
  direction: string | null
  packet_type: number | null
  route: string | null
  payload_len: number | null
  total_len: number | null
  snr: number | null
  rssi: number | null
  score: number | null
  src_addr: string | null
  dst_addr: string | null
  device_time_text: string | null
  device_date_text: string | null
}

export interface WsMessage {
  type: string
  data: Record<string, unknown>
}
