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
    mock_serial.readline = MagicMock(
        side_effect=[
            b"",  # _drain_buffer reads until silence
            b"  -> MeshCore v1.14.1\r\n",
            b"",
        ]
    )
    with patch(
        "meshcore_dashboard.serial.connection.serial.Serial",
        return_value=mock_serial,
    ):
        await connection.connect()
        result = await connection.send_command("ver")
        assert "MeshCore" in result


@pytest.mark.anyio
async def test_check_reboot_detection(connection):
    assert not connection.check_reboot(100)
    assert not connection.check_reboot(200)
    assert connection.check_reboot(5)  # reboot!
    assert not connection.check_reboot(10)
