"""Background polling service with adaptive rate and reboot detection."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from meshcore_dashboard.models import (
    ConfigChangelog,
    ConfigCurrent,
    DeviceInfo,
    LogCollectionState,
    Neighbor,
    PacketLog,
    StatsSnapshot,
)
from meshcore_dashboard.routers import websocket as ws_router
from meshcore_dashboard.routers.status import update_last_poll
from meshcore_dashboard.serial.connection import RepeaterConnection
from meshcore_dashboard.serial.parser import (
    ParseError,
    parse_response_lines,
)
from meshcore_dashboard.services.log_collector import (
    LogCollectionResult,
    LogCollector,
)

logger = logging.getLogger(__name__)

# Map device JSON field names → DB column names
FIELD_REMAP = {
    "recv": "packets_recv",
    "sent": "packets_sent",
}

# How often to poll neighbors (every N poll cycles)
NEIGHBOR_POLL_INTERVAL = 10

CONFIG_SYNC_KEYS = (
    "name",
    "freq",
    "bw",
    "sf",
    "cr",
    "tx_power",
    "pub.key",
    "radio.rxgain",
    "guest.password",
    "owner.info",
    "lat",
    "lon",
    "adc.multiplier",
    "powersaving",
)


class Poller:
    """Background task that polls the repeater at adaptive intervals."""

    def __init__(
        self,
        connection: RepeaterConnection,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._connection = connection
        self._session_factory = session_factory
        self._task: asyncio.Task | None = None  # type: ignore[type-arg]
        self._poll_count = 0
        self._log_started = False
        self._log_collector = LogCollector()
        self._last_parse_error: str | None = None

    @property
    def is_stale(self) -> bool:
        """True if the most recent poll had a parse failure."""
        return self._last_parse_error is not None

    @property
    def last_parse_error(self) -> str | None:
        return self._last_parse_error

    def record_parse_error(self, command: str, message: str) -> None:
        """Mark poller as stale with a formatted error message."""
        self._last_parse_error = f"{command}: {message}"

    def clear_parse_error(self) -> None:
        """Clear stale state on successful poll."""
        self._last_parse_error = None

    def start(self) -> None:
        """Start the polling loop."""
        self._task = asyncio.create_task(self._poll_loop())

    async def sync_device_state(self, *, detect_drift: bool) -> None:
        """Refresh a bounded set of config and device info from the repeater."""
        config_values: dict[str, str] = {}
        for key in CONFIG_SYNC_KEYS:
            try:
                config_values[key] = await self._connection.get_config_value(key)
            except (ConnectionError, TimeoutError, ParseError):
                logger.debug("Config sync skipped for key %s", key)

        firmware_ver = await self._read_single_line_command("ver")
        board = await self._read_single_line_command("board")
        now = datetime.now(UTC)

        async with self._session_factory() as session:
            existing_result = await session.execute(
                select(ConfigCurrent).where(ConfigCurrent.key.in_(CONFIG_SYNC_KEYS))
            )
            existing_rows = {row.key: row for row in existing_result.scalars().all()}

            for key, new_value in config_values.items():
                existing = existing_rows.get(key)
                if existing:
                    if detect_drift and existing.value != new_value:
                        session.add(
                            ConfigChangelog(
                                timestamp=now,
                                key=key,
                                old_value=existing.value,
                                new_value=new_value,
                                source="detected",
                            )
                        )
                    existing.value = new_value
                    existing.updated_at = now
                else:
                    session.add(
                        ConfigCurrent(
                            key=key,
                            value=new_value,
                            updated_at=now,
                        )
                    )

            device_info = await session.get(DeviceInfo, 1)
            if device_info is None:
                device_info = DeviceInfo(id=1)
                session.add(device_info)

            device_info.name = config_values.get("name")
            device_info.public_key = config_values.get("pub.key")
            device_info.radio_freq = self._parse_optional_float(
                config_values.get("freq")
            )
            device_info.radio_bw = self._parse_optional_float(config_values.get("bw"))
            device_info.radio_sf = self._parse_optional_int(config_values.get("sf"))
            device_info.radio_cr = self._parse_optional_int(config_values.get("cr"))
            device_info.tx_power = self._parse_optional_int(
                config_values.get("tx_power")
            )
            device_info.firmware_ver = firmware_ver
            device_info.board = board
            device_info.updated_at = now

            await session.commit()

    async def _read_single_line_command(self, cmd: str) -> str | None:
        """Read the first response line from a simple serial command."""
        try:
            raw = await self._connection.send_command(cmd, timeout=1.0)
        except (ConnectionError, TimeoutError):
            return None

        lines = parse_response_lines(raw)
        if not lines:
            return None
        return lines[0].strip() or None

    @staticmethod
    def _parse_optional_int(value: str | None) -> int | None:
        if value is None:
            return None
        with suppress(ValueError):
            return int(value)
        return None

    @staticmethod
    def _parse_optional_float(value: str | None) -> float | None:
        if value is None:
            return None
        with suppress(ValueError):
            return float(value)
        return None

    async def stop(self) -> None:
        """Stop the polling loop."""
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def _poll_loop(self) -> None:
        """Main polling loop with adaptive interval."""
        while True:
            try:
                await self._do_poll()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Poll error: %s", e)

            interval = await ws_router.get_active_poll_interval()
            await asyncio.sleep(interval)

    async def _do_poll(self) -> None:
        """Execute one poll cycle."""
        if self._connection.state.value == "disconnected":
            try:
                await self._connection.connect()
            except ConnectionError:
                return

        self._poll_count += 1

        # Sync clock and start logging on first connection
        if not self._log_started:
            await self._sync_device_clock()
            await self._ensure_log_started()

        now = datetime.now(UTC)
        stats_data: dict = {}

        # Collect packet logs BEFORE stats to avoid serial buffer contamination
        # (the log command returns many lines that can bleed into subsequent reads)
        await self._collect_logs()
        # Brief pause to let serial line settle after large log dump
        await asyncio.sleep(0.5)

        # Collect stats from all three commands
        for cmd in ("stats-core", "stats-radio", "stats-packets"):
            try:
                data = await self._connection.get_stats_json(cmd)
                stats_data.update(data)
            except ParseError as e:
                logger.warning(
                    "Parse error for %s: %s (raw: %s)",
                    cmd,
                    e,
                    e.raw,
                )
                self.record_parse_error(cmd, str(e))
                await ws_router.broadcast({
                    "type": "parse_error",
                    "data": {"command": cmd, "message": str(e)},
                })
            except (ConnectionError, TimeoutError) as e:
                logger.warning("Command %s failed: %s", cmd, e)
                return

        if not stats_data:
            return

        # Got valid stats — clear any stale state
        self.clear_parse_error()
        await ws_router.broadcast({"type": "parse_cleared", "data": {}})

        # Remap device field names → DB column names
        for old_key, new_key in FIELD_REMAP.items():
            if old_key in stats_data:
                stats_data[new_key] = stats_data.pop(old_key)

        # Check for reboot
        uptime = stats_data.get("uptime_secs")
        if uptime is not None and self._connection.check_reboot(uptime):
            logger.info("Reboot detected! Re-syncing clock and config.")
            self._log_started = False  # Re-start logging after reboot
            await self._sync_device_clock()
            await self._log_reboot(uptime)
            await self.sync_device_state(detect_drift=True)

        # Write stats to DB
        snapshot = StatsSnapshot(
            timestamp=now,
            battery_mv=stats_data.get("battery_mv"),
            uptime_secs=stats_data.get("uptime_secs"),
            queue_len=stats_data.get("queue_len"),
            errors=stats_data.get("errors"),
            noise_floor=stats_data.get("noise_floor"),
            last_rssi=stats_data.get("last_rssi"),
            last_snr=stats_data.get("last_snr"),
            tx_air_secs=stats_data.get("tx_air_secs"),
            rx_air_secs=stats_data.get("rx_air_secs"),
            packets_recv=stats_data.get("packets_recv"),
            packets_sent=stats_data.get("packets_sent"),
            flood_rx=stats_data.get("flood_rx"),
            flood_tx=stats_data.get("flood_tx"),
            direct_rx=stats_data.get("direct_rx"),
            direct_tx=stats_data.get("direct_tx"),
            recv_errors=stats_data.get("recv_errors"),
        )

        async with self._session_factory() as session:
            session.add(snapshot)
            await session.commit()

        update_last_poll()

        # Broadcast to WebSocket clients
        await ws_router.broadcast({"type": "stats_update", "data": stats_data})

        # Poll neighbors periodically (including first cycle)
        if self._poll_count % NEIGHBOR_POLL_INTERVAL == 1:
            await self._poll_neighbors()

    async def _log_reboot(self, new_uptime: int) -> None:
        """Log reboot event to config_changelog."""
        async with self._session_factory() as session:
            entry = ConfigChangelog(
                timestamp=datetime.now(UTC),
                key="_meta.reboot",
                old_value=str(self._connection._last_uptime or "unknown"),
                new_value=str(new_uptime),
                source="detected",
            )
            session.add(entry)
            await session.commit()

    async def _sync_device_clock(self) -> None:
        """Set the device clock to current UTC epoch seconds."""
        epoch = int(datetime.now(UTC).timestamp())
        try:
            await self._connection.send_command(f"time {epoch}", timeout=3.0)
            logger.info("Synced device clock to epoch %d", epoch)
        except (ConnectionError, TimeoutError) as e:
            logger.warning("Failed to sync device clock: %s", e)

    async def _ensure_log_started(self) -> None:
        """Send 'log start' to enable packet logging on device."""
        try:
            await self._connection.send_command("log start", timeout=3.0)
            self._log_started = True
            logger.info("Packet logging started on device")
        except (ConnectionError, TimeoutError) as e:
            logger.warning("Failed to start logging: %s", e)

    async def _collect_logs(self) -> None:
        """Fetch log buffer from device and store new entries."""
        try:
            raw = await self._connection.send_command("log", timeout=10.0)
        except (ConnectionError, TimeoutError):
            return

        # Load prior fingerprints from persisted snapshot (bounded, not full scan)
        prior_fps: set[str] = set()
        async with self._session_factory() as session:
            state = await session.get(LogCollectionState, 1)
            if state and state.last_snapshot_json:
                prior_fps = set(json.loads(state.last_snapshot_json))

        # Process buffer
        collection = self._log_collector.process_buffer(
            raw, prior_fingerprints=prior_fps
        )

        if not collection.parsed_lines:
            await self._update_collection_state(collection)
            return

        now = datetime.now(UTC)
        entries: list[PacketLog] = []
        for parsed in collection.parsed_lines:
            entries.append(
                PacketLog(
                    collected_at=now,
                    raw_line=parsed.raw_line,
                    fingerprint=parsed.fingerprint,
                    parse_status=parsed.parse_status,
                    direction=parsed.direction,
                    packet_type=parsed.packet_type,
                    route=parsed.route,
                    payload_len=parsed.payload_len,
                    total_len=parsed.total_len,
                    snr=parsed.snr,
                    rssi=parsed.rssi,
                    score=parsed.score,
                    src_addr=parsed.src_addr,
                    dst_addr=parsed.dst_addr,
                    device_time_text=parsed.device_time_text,
                    device_date_text=parsed.device_date_text,
                )
            )

        inserted = 0
        async with self._session_factory() as session:
            session.add_all(entries)
            try:
                await session.commit()
                inserted = len(entries)
            except IntegrityError:
                await session.rollback()
                logger.debug(
                    "Fingerprint collision on batch insert, retrying row-by-row"
                )
                for entry in entries:
                    session.add(entry)
                    try:
                        await session.commit()
                        inserted += 1
                    except IntegrityError:
                        await session.rollback()
            except Exception:
                await session.rollback()
                logger.warning("Unexpected error committing log entries", exc_info=True)

        collection.inserted = inserted
        if inserted:
            logger.debug("Stored %d log entries", inserted)
            await ws_router.broadcast({
                "type": "logs_update",
                "data": {"count": inserted},
            })

        await self._update_collection_state(collection)

    async def _update_collection_state(self, collection: LogCollectionResult) -> None:
        """Persist collection state for restart resilience."""
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            state = await session.get(LogCollectionState, 1)
            if state is None:
                state = LogCollectionState(id=1)
                session.add(state)

            state.last_polled_at = now
            state.last_buffer_hash = collection.buffer_hash
            state.last_buffer_size = collection.lines_seen

            if collection.inserted > 0:
                state.last_new_entry_at = now
                state.unchanged_buffer_count = 0
            else:
                state.unchanged_buffer_count = (state.unchanged_buffer_count or 0) + 1

            # Store full buffer fingerprint list for snapshot diffing
            if collection.all_fingerprints:
                state.last_snapshot_json = json.dumps(collection.all_fingerprints)

            await session.commit()

    async def _poll_neighbors(self) -> None:
        """Fetch neighbors and upsert into DB."""
        try:
            raw = await self._connection.send_command("neighbors", timeout=1.0)
        except (ConnectionError, TimeoutError):
            return

        now = datetime.now(UTC)
        lines = parse_response_lines(raw)

        for line in lines:
            line = line.strip()
            if not line or line == "-none-":
                continue

            # Format: "PUBKEY:RSSI:SNR" e.g. "02ED23CC:9381:54"
            parts = line.split(":")
            if len(parts) < 1:
                continue

            pub_key = parts[0]
            rssi = None
            snr = None
            if len(parts) >= 2:
                with suppress(ValueError):
                    rssi = int(parts[1])
            if len(parts) >= 3:
                with suppress(ValueError):
                    snr = float(parts[2])

            async with self._session_factory() as session:
                result = await session.execute(
                    select(Neighbor).where(Neighbor.public_key == pub_key)
                )
                existing = result.scalar_one_or_none()
                if existing:
                    existing.last_seen = now
                    existing.last_rssi = rssi
                    existing.last_snr = snr
                else:
                    session.add(
                        Neighbor(
                            public_key=pub_key,
                            first_seen=now,
                            last_seen=now,
                            last_rssi=rssi,
                            last_snr=snr,
                        )
                    )
                await session.commit()

        # Broadcast neighbor update
        await ws_router.broadcast({"type": "neighbor_update", "data": {}})
