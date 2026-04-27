"""Serial connection to MeshCore repeater."""

from __future__ import annotations

import asyncio
import logging
from enum import Enum

import serial

from meshcore_dashboard.serial.parser import (
    parse_config_value,
    parse_stats_json,
)

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """Repeater connection states."""

    CONNECTED = "connected"
    UNRESPONSIVE = "unresponsive"
    DISCONNECTED = "disconnected"


class RepeaterConnection:
    """Owns the serial port exclusively. All access goes through this class."""

    def __init__(self, port: str, baud: int = 115200) -> None:
        self._port = port
        self._baud = baud
        self._serial: serial.Serial | None = None
        self._lock = asyncio.Lock()
        self._state = ConnectionState.DISCONNECTED
        self._consecutive_failures = 0
        self._last_uptime: int | None = None

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    async def connect(self) -> None:
        """Open the serial port."""
        try:
            self._serial = serial.Serial(self._port, self._baud, timeout=1)
            self._state = ConnectionState.CONNECTED
            self._consecutive_failures = 0
            logger.info("Connected to %s", self._port)
        except (serial.SerialException, OSError) as e:
            self._state = ConnectionState.DISCONNECTED
            raise ConnectionError(f"Cannot open {self._port}: {e}") from e

    async def disconnect(self) -> None:
        """Close the serial port."""
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._serial = None
        self._state = ConnectionState.DISCONNECTED

    async def send_command(self, cmd: str, timeout: float = 1.0) -> str:
        """Send a command and return the raw response."""
        if self._state == ConnectionState.DISCONNECTED or not self._serial:
            raise ConnectionError("Not connected")

        try:
            async with asyncio.timeout(timeout + 2):
                async with self._lock:
                    return await self._do_send(cmd, timeout)
        except TimeoutError:
            self._consecutive_failures += 1
            if self._consecutive_failures >= 5:
                self._state = ConnectionState.UNRESPONSIVE
            raise
        except (serial.SerialException, OSError) as e:
            self._state = ConnectionState.DISCONNECTED
            self._serial = None
            raise ConnectionError(f"Serial error: {e}") from e

    async def _do_send(self, cmd: str, timeout: float) -> str:
        if cmd.strip() == "log":
            return await self._send_streaming_command(cmd, timeout)
        return await self._send_prefixed_command(cmd, timeout)

    async def _prepare_command(self, cmd: str) -> asyncio.AbstractEventLoop:
        assert self._serial is not None
        loop = asyncio.get_event_loop()
        # The repeater can stream logs continuously, so "read until silence"
        # never reliably creates a clean command window. Flush the unread
        # buffer instead so interactive commands start from a known boundary.
        await loop.run_in_executor(None, self._flush_input_buffer)
        await loop.run_in_executor(None, self._serial.write, f"{cmd}\r".encode())
        return loop

    async def _send_prefixed_command(self, cmd: str, timeout: float) -> str:
        assert self._serial is not None
        loop = await self._prepare_command(cmd)
        lines: list[str] = []
        saw_response = False
        deadline = loop.time() + timeout
        saved_timeout = self._serial.timeout
        self._serial.timeout = min(0.2, timeout)
        try:
            while loop.time() < deadline:
                raw = await loop.run_in_executor(None, self._serial.readline)
                if not raw:
                    if saw_response:
                        break
                    continue
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                if not line:
                    if saw_response:
                        break
                    continue
                lines.append(line)
                if line.startswith("  -> "):
                    saw_response = True
        finally:
            self._serial.timeout = saved_timeout
        self._consecutive_failures = 0
        self._state = ConnectionState.CONNECTED
        return "\r\n".join(lines)

    async def _send_streaming_command(self, cmd: str, timeout: float) -> str:
        assert self._serial is not None
        loop = await self._prepare_command(cmd)
        lines: list[str] = []
        deadline = loop.time() + timeout
        saved_timeout = self._serial.timeout
        self._serial.timeout = min(0.2, timeout)
        try:
            while loop.time() < deadline:
                raw = await loop.run_in_executor(None, self._serial.readline)
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                if not line:
                    continue
                lines.append(line)
                if line.startswith("  ->") and "EOF" in line:
                    break
        finally:
            self._serial.timeout = saved_timeout
        self._consecutive_failures = 0
        self._state = ConnectionState.CONNECTED
        return "\r\n".join(lines)

    def _flush_input_buffer(self) -> None:
        """Drop any unread serial data before sending a new command."""
        assert self._serial is not None
        self._serial.reset_input_buffer()

    async def get_stats_json(self, cmd: str) -> dict:
        """Send a stats command and parse the JSON response."""
        raw = await self.send_command(cmd, timeout=2.0)
        return parse_stats_json(raw)

    async def get_config_value(self, key: str) -> str:
        """Read a single config value from the device."""
        raw = await self.send_command(f"get {key}", timeout=1.0)
        return parse_config_value(raw)

    async def set_config_value(self, key: str, value: str) -> bool:
        """Set a config value on the device."""
        await self.send_command(f"set {key} {value}", timeout=3.0)
        return True

    def check_reboot(self, uptime_secs: int) -> bool:
        """Return True if reboot detected (uptime regression)."""
        if self._last_uptime is not None and uptime_secs < self._last_uptime:
            self._last_uptime = uptime_secs
            return True
        self._last_uptime = uptime_secs
        return False
