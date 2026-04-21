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
        except serial.SerialException as e:
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
        except serial.SerialException as e:
            self._state = ConnectionState.DISCONNECTED
            self._serial = None
            raise ConnectionError(f"Serial error: {e}") from e

    async def _do_send(self, cmd: str, timeout: float) -> str:
        assert self._serial is not None
        loop = asyncio.get_event_loop()
        # Flush any stale data from the input buffer
        await loop.run_in_executor(None, self._serial.reset_input_buffer)
        await loop.run_in_executor(None, self._serial.write, f"{cmd}\r".encode())
        lines: list[str] = []
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            raw = await loop.run_in_executor(None, self._serial.readline)
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            if line:
                lines.append(line)
            elif lines:
                break
        self._consecutive_failures = 0
        self._state = ConnectionState.CONNECTED
        return "\r\n".join(lines)

    async def get_stats_json(self, cmd: str) -> dict:
        """Send a stats command and parse the JSON response."""
        raw = await self.send_command(cmd, timeout=1.0)
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
