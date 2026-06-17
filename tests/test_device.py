"""Tests for the Fanimation BLE device protocol layer.

These tests verify packet construction and response parsing — the core
BLE protocol logic. They are pure unit tests with no BLE hardware
dependency, no mocking of bleak, and no Home Assistant test harness.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.fanimation.const import (
    CMD_GET_STATUS,
    CMD_SET_STATE,
    CMD_STATUS_RESPONSE,
    START_BYTE,
)
from custom_components.fanimation.device import FanimationDevice, FanimationState

from .conftest import TEST_MAC, TEST_NAME, build_response

# ---------------------------------------------------------------------------
# _build_packet tests
# ---------------------------------------------------------------------------


class TestBuildPacket:
    """Tests for FanimationDevice._build_packet."""

    def test_get_status_packet(self) -> None:
        """GET_STATUS packet should be 10 bytes with correct structure."""
        packet = FanimationDevice._build_packet(CMD_GET_STATUS)
        assert len(packet) == 10
        assert packet[0] == START_BYTE
        assert packet[1] == CMD_GET_STATUS
        # All fields should be zero for a status query
        assert packet[2:9] == bytes(7)
        # Checksum = sum of first 9 bytes & 0xFF
        assert packet[9] == (START_BYTE + CMD_GET_STATUS) & 0xFF

    def test_set_state_all_fields(self) -> None:
        """SET_STATE with all fields should encode correctly."""
        packet = FanimationDevice._build_packet(
            CMD_SET_STATE,
            speed=3,
            direction=0,
            uplight=0,
            downlight=75,
            timer_hi=1,
            timer_lo=44,
            fan_type=0,
        )
        assert len(packet) == 10
        assert packet[0] == START_BYTE
        assert packet[1] == CMD_SET_STATE
        assert packet[2] == 3  # speed high
        assert packet[3] == 0  # direction forward
        assert packet[4] == 0  # uplight unused
        assert packet[5] == 75  # downlight 75%
        assert packet[6] == 1  # timer high byte
        assert packet[7] == 44  # timer low byte
        assert packet[8] == 0  # fan type

    def test_checksum_calculation(self) -> None:
        """Checksum should be sum of bytes 0-8 masked to 8 bits."""
        packet = FanimationDevice._build_packet(
            CMD_SET_STATE,
            speed=3,
            downlight=100,
        )
        expected_checksum = sum(packet[:9]) & 0xFF
        assert packet[9] == expected_checksum

    def test_checksum_wraps_at_256(self) -> None:
        """Checksum should wrap correctly on overflow."""
        # Use values that sum well over 255
        packet = FanimationDevice._build_packet(
            CMD_SET_STATE,
            speed=3,
            direction=1,
            uplight=100,
            downlight=100,
            timer_hi=255,
            timer_lo=255,
            fan_type=100,
        )
        raw_sum = sum(packet[:9])
        assert raw_sum > 255, "Test values should overflow a byte"
        assert packet[9] == raw_sum & 0xFF

    def test_timer_encoding_big_endian(self) -> None:
        """Timer should be encoded as big-endian 16-bit value."""
        # 300 minutes = 0x012C → hi=1, lo=44
        timer_minutes = 300
        timer_hi = (timer_minutes >> 8) & 0xFF
        timer_lo = timer_minutes & 0xFF
        packet = FanimationDevice._build_packet(
            CMD_SET_STATE,
            timer_hi=timer_hi,
            timer_lo=timer_lo,
        )
        assert packet[6] == 1  # 300 >> 8 = 1
        assert packet[7] == 44  # 300 & 0xFF = 44

    def test_timer_encoding_max(self) -> None:
        """Maximum timer value (360 min = 0x0168) encodes correctly."""
        timer_minutes = 360
        timer_hi = (timer_minutes >> 8) & 0xFF
        timer_lo = timer_minutes & 0xFF
        packet = FanimationDevice._build_packet(
            CMD_SET_STATE,
            timer_hi=timer_hi,
            timer_lo=timer_lo,
        )
        assert packet[6] == 1  # 360 >> 8 = 1
        assert packet[7] == 104  # 360 & 0xFF = 104

    def test_timer_encoding_zero(self) -> None:
        """Timer of 0 should encode as 0x0000."""
        packet = FanimationDevice._build_packet(CMD_SET_STATE, timer_hi=0, timer_lo=0)
        assert packet[6] == 0
        assert packet[7] == 0

    def test_packet_is_bytes_not_bytearray(self) -> None:
        """Returned packet should be immutable bytes."""
        packet = FanimationDevice._build_packet(CMD_GET_STATUS)
        assert isinstance(packet, bytes)


# ---------------------------------------------------------------------------
# _parse_response tests
# ---------------------------------------------------------------------------


class TestParseResponse:
    """Tests for FanimationDevice._parse_response."""

    def test_valid_response(self) -> None:
        """A well-formed response should parse into FanimationState."""
        data = build_response(speed=2, downlight=80, timer_minutes=120)
        state = FanimationDevice._parse_response(data)

        assert state is not None
        assert state.speed == 2
        assert state.direction == 0
        assert state.uplight == 0
        assert state.downlight == 80
        assert state.timer_minutes == 120
        assert state.fan_type == 0

    def test_all_fields(self) -> None:
        """All fields should be correctly extracted."""
        data = build_response(
            speed=3,
            direction=1,
            uplight=50,
            downlight=100,
            timer_minutes=360,
            fan_type=2,
        )
        state = FanimationDevice._parse_response(data)

        assert state is not None
        assert state.speed == 3
        assert state.direction == 1
        assert state.uplight == 50
        assert state.downlight == 100
        assert state.timer_minutes == 360
        assert state.fan_type == 2

    def test_fan_off_state(self) -> None:
        """All-zero response should parse as fan off."""
        data = build_response()
        state = FanimationDevice._parse_response(data)

        assert state is not None
        assert state.speed == 0
        assert state.downlight == 0
        assert state.timer_minutes == 0

    def test_bad_checksum_rejected(self) -> None:
        """Response with wrong checksum should return None."""
        data = build_response(speed=1)
        data[9] = 0x00  # corrupt the checksum
        state = FanimationDevice._parse_response(data)
        assert state is None

    def test_short_data_rejected(self) -> None:
        """Response shorter than 10 bytes should return None."""
        data = bytearray([START_BYTE, CMD_STATUS_RESPONSE, 0, 0, 0])
        state = FanimationDevice._parse_response(data)
        assert state is None

    def test_wrong_start_byte_rejected(self) -> None:
        """Response with wrong start byte should return None."""
        data = build_response(speed=1)
        data[0] = 0x00  # corrupt the start byte
        state = FanimationDevice._parse_response(data)
        assert state is None

    def test_empty_data_rejected(self) -> None:
        """Empty data should return None."""
        state = FanimationDevice._parse_response(bytearray())
        assert state is None

    def test_timer_decoding_big_endian(self) -> None:
        """Timer should be decoded as big-endian 16-bit value."""
        # 300 minutes = high byte 1, low byte 44
        data = build_response(timer_minutes=300)
        state = FanimationDevice._parse_response(data)

        assert state is not None
        assert state.timer_minutes == 300

    def test_timer_decoding_max(self) -> None:
        """Maximum timer (360 minutes) should decode correctly."""
        data = build_response(timer_minutes=360)
        state = FanimationDevice._parse_response(data)

        assert state is not None
        assert state.timer_minutes == 360

    def test_timer_decoding_zero(self) -> None:
        """Timer of 0 should decode to 0."""
        data = build_response(timer_minutes=0)
        state = FanimationDevice._parse_response(data)

        assert state is not None
        assert state.timer_minutes == 0

    def test_extra_data_still_parses(self) -> None:
        """Response with more than 10 bytes should still parse the first 10."""
        data = build_response(speed=1)
        data.extend(bytearray([0xFF, 0xFF]))  # extra junk
        state = FanimationDevice._parse_response(data)

        assert state is not None
        assert state.speed == 1

    def test_returns_dataclass(self) -> None:
        """Parsed result should be a FanimationState dataclass."""
        data = build_response()
        state = FanimationDevice._parse_response(data)
        assert isinstance(state, FanimationState)


# ---------------------------------------------------------------------------
# FanimationState dataclass tests
# ---------------------------------------------------------------------------


class TestFanimationState:
    """Tests for the FanimationState dataclass."""

    def test_defaults(self) -> None:
        """Default state should be all zeros."""
        state = FanimationState()
        assert state.speed == 0
        assert state.direction == 0
        assert state.uplight == 0
        assert state.downlight == 0
        assert state.timer_minutes == 0
        assert state.fan_type == 0

    def test_equality(self) -> None:
        """Two states with same values should be equal."""
        s1 = FanimationState(speed=1, downlight=50)
        s2 = FanimationState(speed=1, downlight=50)
        assert s1 == s2

    def test_inequality(self) -> None:
        """Two states with different values should not be equal."""
        s1 = FanimationState(speed=1)
        s2 = FanimationState(speed=2)
        assert s1 != s2


# ---------------------------------------------------------------------------
# Stateful BLE client tests
#
# These inject an AsyncMock/MagicMock client and patch the conftest-stubbed
# ``bluetooth`` / ``establish_connection`` in the device namespace — no real
# Bluetooth, no hardware.
# ---------------------------------------------------------------------------


class TestDeviceBasics:
    """Construction, properties, notification handler, disconnect callback."""

    def test_init_and_properties(self) -> None:
        device = FanimationDevice(MagicMock(), TEST_MAC, TEST_NAME)
        assert device.mac == TEST_MAC
        assert device.name == TEST_NAME
        assert device._client is None

    def test_notification_handler_stores_and_signals(self) -> None:
        device = FanimationDevice(MagicMock(), TEST_MAC, TEST_NAME)
        data = build_response(speed=1)
        device._notification_handler(None, data)
        assert device._last_notification == data
        assert device._notify_event.is_set()

    def test_on_disconnect_clears_client(self) -> None:
        device = FanimationDevice(MagicMock(), TEST_MAC, TEST_NAME)
        device._client = MagicMock()
        device._on_disconnect(MagicMock())
        assert device._client is None


_ADDR = "custom_components.fanimation.device.bluetooth.async_ble_device_from_address"
_CONNECT = "custom_components.fanimation.device.establish_connection"


class TestEnsureConnected:
    @pytest.mark.asyncio
    async def test_noop_when_already_connected(self) -> None:
        device = FanimationDevice(MagicMock(), TEST_MAC, TEST_NAME)
        client = MagicMock()
        client.is_connected = True
        device._client = client
        await device._ensure_connected()
        assert device._client is client

    @pytest.mark.asyncio
    async def test_raises_when_no_adapter_finds_device(self) -> None:
        device = FanimationDevice(MagicMock(), TEST_MAC, TEST_NAME)
        with patch(_ADDR, return_value=None), pytest.raises(ConnectionError):
            await device._ensure_connected()

    @pytest.mark.asyncio
    async def test_connects_and_subscribes(self) -> None:
        device = FanimationDevice(MagicMock(), TEST_MAC, TEST_NAME)
        client = AsyncMock()
        with (
            patch(_ADDR, return_value=MagicMock()),
            patch(_CONNECT, AsyncMock(return_value=client)),
        ):
            await device._ensure_connected()
        assert device._client is client
        client.start_notify.assert_awaited_once()


class TestDisconnect:
    @pytest.mark.asyncio
    async def test_closes_and_clears(self) -> None:
        device = FanimationDevice(MagicMock(), TEST_MAC, TEST_NAME)
        client = AsyncMock()
        device._client = client
        await device.disconnect()
        client.disconnect.assert_awaited_once()
        assert device._client is None

    @pytest.mark.asyncio
    async def test_noop_without_client(self) -> None:
        device = FanimationDevice(MagicMock(), TEST_MAC, TEST_NAME)
        await device.disconnect()
        assert device._client is None

    @pytest.mark.asyncio
    async def test_swallows_disconnect_errors(self) -> None:
        device = FanimationDevice(MagicMock(), TEST_MAC, TEST_NAME)
        client = AsyncMock()
        client.disconnect.side_effect = Exception("BLE error")
        device._client = client
        await device.disconnect()
        assert device._client is None


class TestSendAndReceive:
    @pytest.mark.asyncio
    async def test_happy_path_returns_notification(self) -> None:
        device = FanimationDevice(MagicMock(), TEST_MAC, TEST_NAME)
        response = build_response(speed=2)

        async def _write(_char: object, _packet: object) -> None:
            device._notification_handler(None, response)

        client = AsyncMock()
        client.write_gatt_char = AsyncMock(side_effect=_write)
        device._client = client

        result = await device._send_and_receive(FanimationDevice._build_packet(CMD_GET_STATUS))
        assert result == response

    @pytest.mark.asyncio
    async def test_malformed_packet_raises(self) -> None:
        device = FanimationDevice(MagicMock(), TEST_MAC, TEST_NAME)
        device._client = AsyncMock()
        with pytest.raises(ValueError):
            await device._send_and_receive(b"\x00\x01")

    @pytest.mark.asyncio
    async def test_raises_when_not_connected(self) -> None:
        device = FanimationDevice(MagicMock(), TEST_MAC, TEST_NAME)
        device._client = None
        with pytest.raises(ConnectionError):
            await device._send_and_receive(FanimationDevice._build_packet(CMD_GET_STATUS))

    @pytest.mark.asyncio
    async def test_timeout_returns_none(self) -> None:
        device = FanimationDevice(MagicMock(), TEST_MAC, TEST_NAME)
        device._client = AsyncMock()  # write does nothing → no notification
        result = await device._send_and_receive(
            FanimationDevice._build_packet(CMD_GET_STATUS), timeout=0.01
        )
        assert result is None


class TestAsyncGetStatus:
    @pytest.mark.asyncio
    async def test_returns_parsed_state(self) -> None:
        device = FanimationDevice(MagicMock(), TEST_MAC, TEST_NAME)
        device._ensure_connected = AsyncMock()
        device._send_and_receive = AsyncMock(return_value=build_response(speed=2, downlight=40))
        state = await device.async_get_status()
        assert state is not None
        assert state.speed == 2
        assert state.downlight == 40

    @pytest.mark.asyncio
    async def test_returns_none_on_no_response(self) -> None:
        device = FanimationDevice(MagicMock(), TEST_MAC, TEST_NAME)
        device._ensure_connected = AsyncMock()
        device._send_and_receive = AsyncMock(return_value=None)
        assert await device.async_get_status() is None


class TestAsyncSetState:
    @pytest.mark.asyncio
    async def test_merges_unset_fields_and_verifies(self) -> None:
        device = FanimationDevice(MagicMock(), TEST_MAC, TEST_NAME)
        device._ensure_connected = AsyncMock()
        current = build_response(speed=1, downlight=50)
        verify = build_response(speed=3, downlight=50)
        # GET (read-before-write), SET (echo, ignored), GET (verify)
        device._send_and_receive = AsyncMock(side_effect=[current, build_response(speed=3), verify])
        state = await device.async_set_state(speed=3)
        assert state is not None
        assert state.speed == 3
        assert state.downlight == 50  # preserved from current state

    @pytest.mark.asyncio
    async def test_none_when_initial_read_fails(self) -> None:
        device = FanimationDevice(MagicMock(), TEST_MAC, TEST_NAME)
        device._ensure_connected = AsyncMock()
        device._send_and_receive = AsyncMock(return_value=None)
        assert await device.async_set_state(speed=3) is None

    @pytest.mark.asyncio
    async def test_none_when_read_unparseable(self) -> None:
        device = FanimationDevice(MagicMock(), TEST_MAC, TEST_NAME)
        device._ensure_connected = AsyncMock()
        bad = build_response(speed=1)
        bad[9] = 0  # corrupt checksum → parse returns None
        device._send_and_receive = AsyncMock(return_value=bad)
        assert await device.async_set_state(speed=3) is None

    @pytest.mark.asyncio
    async def test_none_when_verify_fails(self) -> None:
        device = FanimationDevice(MagicMock(), TEST_MAC, TEST_NAME)
        device._ensure_connected = AsyncMock()
        current = build_response(speed=1, downlight=50)
        device._send_and_receive = AsyncMock(side_effect=[current, build_response(speed=3), None])
        assert await device.async_set_state(speed=3) is None
