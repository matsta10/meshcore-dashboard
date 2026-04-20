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
}

export interface StatusResponse {
  connection_state: "connected" | "unresponsive" | "disconnected"
  device_info: DeviceInfoResponse | null
  consecutive_failures: number
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
  timestamp: string
  raw_line: string
}

export interface WsMessage {
  type: string
  data: Record<string, unknown>
}
