"""Tests for RepeaterConnection."""

from unittest.mock import MagicMock, patch

import pytest

from meshcore_dashboard.serial.connection import (
    ConnectionState,
    RepeaterConnection,
)


@pytest.fixture
def connection():
    return RepeaterConnection(port="/dev/ttyTEST", baud=115200)


@pytest.mark.anyio
async def test_initial_state(connection):
    assert connection.state == ConnectionState.DISCONNECTED


@pytest.mark.anyio
async def test_send_command_disconnected_raises(connection):
    with pytest.raises(ConnectionError):
        await connection.send_command("ver")


@pytest.mark.anyio
async def test_connect_success(connection):
    mock_serial = MagicMock()
    mock_serial.is_open = True
    with patch(
        "meshcore_dashboard.serial.connection.serial.Serial",
        return_value=mock_serial,
    ):
        await connection.connect()
        assert connection.state == ConnectionState.CONNECTED


@pytest.mark.anyio
async def test_send_command_success(connection):
    mock_serial = MagicMock()
    mock_serial.is_open = True
    mock_serial.write = MagicMock()
    mock_serial.reset_input_buffer = MagicMock()
    responses = iter([b"  -> MeshCore v1.14.1\r\n", b""])
    mock_serial.readline = MagicMock(side_effect=lambda: next(responses, b""))
    with patch(
        "meshcore_dashboard.serial.connection.serial.Serial",
        return_value=mock_serial,
    ):
        await connection.connect()
        result = await connection.send_command("ver")
        assert "MeshCore" in result
        mock_serial.reset_input_buffer.assert_called_once_with()


@pytest.mark.anyio
async def test_send_command_flushes_before_write(connection):
    mock_serial = MagicMock()
    mock_serial.is_open = True
    call_order: list[str] = []

    def record_flush() -> None:
        call_order.append("flush")

    def record_write(_: bytes) -> None:
        call_order.append("write")

    mock_serial.reset_input_buffer = MagicMock(side_effect=record_flush)
    mock_serial.write = MagicMock(side_effect=record_write)
    responses = iter([b"  -> ok\r\n", b""])
    mock_serial.readline = MagicMock(side_effect=lambda: next(responses, b""))

    with patch(
        "meshcore_dashboard.serial.connection.serial.Serial",
        return_value=mock_serial,
    ):
        await connection.connect()
        result = await connection.send_command("clock")
        assert result == "  -> ok"
        assert call_order[:2] == ["flush", "write"]


@pytest.mark.anyio
async def test_send_command_ignores_noise_before_prefixed_response(connection):
    mock_serial = MagicMock()
    mock_serial.is_open = True
    mock_serial.write = MagicMock()
    mock_serial.reset_input_buffer = MagicMock()
    responses = iter([
        b"18:15:39 - 21/4/2026 U: RX, len=66 (type=0, route=F)\r\n",
        b"18:15:40 - 21/4/2026 U: TX, len=63 (type=5, route=F)\r\n",
        b"stats-core\r\n",
        b'  -> {"battery_mv":4170}\r\n',
        b"",
    ])
    mock_serial.readline = MagicMock(side_effect=lambda: next(responses, b""))

    with patch(
        "meshcore_dashboard.serial.connection.serial.Serial",
        return_value=mock_serial,
    ):
        await connection.connect()
        result = await connection.send_command("stats-core", timeout=2.0)
        assert '  -> {"battery_mv":4170}' in result


@pytest.mark.anyio
async def test_log_command_stops_at_eof_marker(connection):
    mock_serial = MagicMock()
    mock_serial.is_open = True
    mock_serial.write = MagicMock()
    mock_serial.reset_input_buffer = MagicMock()
    responses = iter([
        b"log\r\n",
        b"18:15:39 - 21/4/2026 U: RX, len=66 (type=0, route=F)\r\n",
        b"18:15:40 - 21/4/2026 U: TX, len=63 (type=5, route=F)\r\n",
        b"  ->    EOF\r\n",
        b"stats-core\r\n",
        b'  -> {"battery_mv":4170}\r\n',
    ])
    mock_serial.readline = MagicMock(side_effect=lambda: next(responses, b""))

    with patch(
        "meshcore_dashboard.serial.connection.serial.Serial",
        return_value=mock_serial,
    ):
        await connection.connect()
        result = await connection.send_command("log", timeout=10.0)
        assert "U: RX" in result
        assert "U: TX" in result
        assert "  ->    EOF" in result
        assert "stats-core" not in result


@pytest.mark.anyio
async def test_check_reboot_detection(connection):
    assert not connection.check_reboot(100)
    assert not connection.check_reboot(200)
    assert connection.check_reboot(5)  # reboot!
    assert not connection.check_reboot(10)
