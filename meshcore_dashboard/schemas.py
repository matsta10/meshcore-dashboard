"""Pydantic request/response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class StatsResponse(BaseModel):
    timestamp: datetime
    battery_mv: int | None = None
    uptime_secs: int | None = None
    queue_len: int | None = None
    errors: int | None = None
    noise_floor: int | None = None
    last_rssi: int | None = None
    last_snr: float | None = None
    tx_air_secs: int | None = None
    rx_air_secs: int | None = None
    packets_recv: int | None = None
    packets_sent: int | None = None
    flood_rx: int | None = None
    flood_tx: int | None = None
    direct_rx: int | None = None
    direct_tx: int | None = None
    recv_errors: int | None = None
    stale: bool = False


class StatsHistoryResponse(BaseModel):
    data: list[StatsResponse]


class ConfigEntry(BaseModel):
    key: str
    value: str
    updated_at: datetime


class ConfigSetRequest(BaseModel):
    value: str
    confirm_value: str | None = None


class ConfigChangelogEntry(BaseModel):
    id: int
    timestamp: datetime
    key: str
    old_value: str | None
    new_value: str
    source: str


class NeighborResponse(BaseModel):
    public_key: str
    name: str | None
    first_seen: datetime
    last_seen: datetime
    last_rssi: int | None
    last_snr: float | None


class DeviceInfoResponse(BaseModel):
    name: str | None = None
    firmware_ver: str | None = None
    board: str | None = None
    public_key: str | None = None
    radio_freq: float | None = None
    radio_bw: float | None = None
    radio_sf: int | None = None
    radio_cr: int | None = None
    tx_power: int | None = None


class StatusResponse(BaseModel):
    connection_state: str
    device_info: DeviceInfoResponse | None = None
    consecutive_failures: int = 0


class CommandRequest(BaseModel):
    command: str
    confirm: bool = False


class CommandResponse(BaseModel):
    output: str


class ClockSetRequest(BaseModel):
    epoch_seconds: int = Field(strict=True, ge=0, le=4_102_444_800)


class AdminActionResponse(BaseModel):
    detail: str


class PacketLogEntry(BaseModel):
    id: int
    collected_at: datetime
    raw_line: str
    fingerprint: str | None = None
    parse_status: str = "raw_only"
    direction: str | None = None
    packet_type: int | None = None
    route: str | None = None
    payload_len: int | None = None
    total_len: int | None = None
    snr: float | None = None
    rssi: int | None = None
    score: int | None = None
    src_addr: str | None = None
    dst_addr: str | None = None
    device_time_text: str | None = None
    device_date_text: str | None = None


class HealthResponse(BaseModel):
    status: str
    last_poll: datetime | None = None


class WsClientMessage(BaseModel):
    type: str
    data: dict = {}


class WsServerMessage(BaseModel):
    type: str
    data: dict = {}
