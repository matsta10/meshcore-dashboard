"""SQLAlchemy ORM models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# -- Stats columns shared across raw/hourly/daily tables --

_STATS_COLUMNS = {
    "battery_mv": Integer,
    "uptime_secs": Integer,
    "queue_len": Integer,
    "errors": Integer,
    "noise_floor": Integer,
    "last_rssi": Integer,
    "last_snr": Float,
    "tx_air_secs": Integer,
    "rx_air_secs": Integer,
    "packets_recv": Integer,
    "packets_sent": Integer,
    "flood_rx": Integer,
    "flood_tx": Integer,
    "direct_rx": Integer,
    "direct_tx": Integer,
    "recv_errors": Integer,
}


class StatsSnapshot(Base):
    __tablename__ = "stats_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, index=True
    )
    battery_mv: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    uptime_secs: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    queue_len: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    errors: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    noise_floor: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    last_rssi: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    last_snr: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    tx_air_secs: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    rx_air_secs: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    packets_recv: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    packets_sent: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    flood_rx: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    flood_tx: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    direct_rx: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    direct_tx: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    recv_errors: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )


class StatsHourly(Base):
    __tablename__ = "stats_hourly"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, index=True
    )
    battery_mv: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    uptime_secs: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    queue_len: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    errors: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    noise_floor: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    last_rssi: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    last_snr: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    tx_air_secs: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    rx_air_secs: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    packets_recv: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    packets_sent: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    flood_rx: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    flood_tx: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    direct_rx: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    direct_tx: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    recv_errors: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )


class StatsDaily(Base):
    __tablename__ = "stats_daily"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, index=True
    )
    battery_mv: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    uptime_secs: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    queue_len: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    errors: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    noise_floor: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    last_rssi: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    last_snr: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    tx_air_secs: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    rx_air_secs: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    packets_recv: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    packets_sent: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    flood_rx: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    flood_tx: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    direct_rx: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    direct_tx: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    recv_errors: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )


class ConfigCurrent(Base):
    __tablename__ = "config_current"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class ConfigChangelog(Base):
    __tablename__ = "config_changelog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime)
    key: Mapped[str] = mapped_column(Text, index=True)
    old_value: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    new_value: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)  # "user" | "detected"


class Neighbor(Base):
    __tablename__ = "neighbors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_key: Mapped[str] = mapped_column(
        Text, unique=True, index=True
    )
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime)
    last_seen: Mapped[datetime] = mapped_column(DateTime)
    last_rssi: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    last_snr: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )


class PacketLog(Base):
    __tablename__ = "packet_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, index=True
    )
    raw_line: Mapped[str] = mapped_column(Text)


class DeviceInfo(Base):
    __tablename__ = "device_info"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    firmware_ver: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    board: Mapped[str | None] = mapped_column(Text, nullable=True)
    public_key: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    radio_freq: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    radio_bw: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    radio_sf: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    radio_cr: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    tx_power: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
