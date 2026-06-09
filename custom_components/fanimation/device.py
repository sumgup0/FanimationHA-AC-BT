"""BLE device layer for Fanimation BTCR9 ceiling fans."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from bleak import BleakClient
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant

from .const import (
    CHAR_NOTIFY,
    CHAR_WRITE,
    CMD_GET_STATUS,
    CMD_SET_STATE,
    LOGGER,
    START_BYTE,
)


@dataclass
class FanimationState:
    """Parsed fan state from a GET_STATUS response."""

    speed: int = 0
    direction: int = 0
    uplight: int = 0
    downlight: int = 0
    timer_minutes: int = 0
    fan_type: int = 0


class FanimationDevice:
    """BLE communication layer for a Fanimation BTCR9 fan."""

    def __init__(self, hass: HomeAssistant, mac: str, name: str) -> None:
        """Initialize the device."""
        self._hass = hass
        self._mac = mac
        self._name = name
        self._client: BleakClient | None = None
        self._lock = asyncio.Lock()
        self._notify_event = asyncio.Event()
        self._last_notification: bytearray | None = None

    @property
    def mac(self) -> str:
        """Return the MAC address."""
        return self._mac

    @property
    def name(self) -> str:
        """Return the friendly name."""
        return self._name

    @staticmethod
    def _build_packet(
        cmd: int,
        speed: int = 0,
        direction: int = 0,
        uplight: int = 0,
        downlight: int = 0,
        timer_hi: int = 0,
        timer_lo: int = 0,
        fan_type: int = 0,
    ) -> bytes:
        """Build a 10-byte command packet with checksum."""
        packet = bytearray([START_BYTE, cmd, speed, direction, uplight, downlight, timer_hi, timer_lo, fan_type, 0])
        packet[9] = sum(packet[:9]) & 0xFF
        return bytes(packet)

    @staticmethod
    def _parse_response(data: bytearray) -> FanimationState | None:
        """Parse a 10-byte status response into FanimationState."""
        if len(data) < 10 or data[0] != START_BYTE:
            return None

        # Verify checksum
        expected = sum(data[:9]) & 0xFF
        if data[9] != expected:
            LOGGER.warning("Checksum mismatch: got 0x%02X, expected 0x%02X", data[9], expected)
            return None

        return FanimationState(
            speed=data[2],
            direction=data[3],
            uplight=data[4],
            downlight=data[5],
            timer_minutes=(data[6] << 8) | data[7],
            fan_type=data[8],
        )

    def _notification_handler(self, _sender: Any, data: bytearray) -> None:
        """Handle BLE notifications from the fan."""
        self._last_notification = data
        self._notify_event.set()

    async def _ensure_connected(self) -> None:
        """Connect to the fan if not already connected."""
        if self._client and self._client.is_connected:
            return

        ble_device = bluetooth.async_ble_device_from_address(self._hass, self._mac.upper(), connectable=True)
        if not ble_device:
            raise ConnectionError(f"Fan {self._name} ({self._mac}) not found by any Bluetooth adapter")

        self._client = await establish_connection(
            BleakClientWithServiceCache,
            ble_device,
            name=self._name,
            disconnected_callback=self._on_disconnect,
            max_attempts=3,
        )
        await self._client.start_notify(
            CHAR_NOTIFY,
            self._notification_handler,
            bluez={"use_start_notify": True},
        )
        LOGGER.debug("Connected to %s (%s)", self._name, self._mac)

    def _on_disconnect(self, _client: BleakClient) -> None:
        """Handle unexpected disconnection."""
        LOGGER.debug("Disconnected from %s (%s)", self._name, self._mac)
        self._client = None

    async def disconnect(self) -> None:
        """Disconnect from the fan."""
        if self._client:
            try:
                await self._client.disconnect()
            except Exception:  # noqa: S110
                pass
            finally:
                self._client = None

    async def _send_and_receive(self, packet: bytes, timeout: float = 5.0) -> bytearray | None:
        """Send a packet to CHAR_WRITE and wait for the notification response.

        All writes go to CHAR_WRITE (0xE001) only. The OAD firmware
        service (0xAD0/AD1/AD2) is never referenced anywhere in this
        integration — writing to it could brick the fan.
        """
        # Sanity check: packet must be our protocol format
        if len(packet) != 10 or packet[0] != START_BYTE:
            raise ValueError(
                f"Refusing to send malformed packet (len={len(packet)}, "
                f"start=0x{packet[0]:02X}). Expected 10 bytes starting with 0x53."
            )

        self._notify_event.clear()
        self._last_notification = None

        await self._client.write_gatt_char(CHAR_WRITE, packet)

        try:
            await asyncio.wait_for(self._notify_event.wait(), timeout=timeout)
        except TimeoutError:
            LOGGER.warning("Timeout waiting for response from %s", self._name)
            return None

        return self._last_notification

    async def async_get_status(self) -> FanimationState | None:
        """Send GET_STATUS and return parsed state."""
        async with self._lock:
            await self._ensure_connected()
            packet = self._build_packet(CMD_GET_STATUS)
            response = await self._send_and_receive(packet)
            if response is None:
                return None
            return self._parse_response(response)

    async def async_set_state(
        self,
        speed: int | None = None,
        direction: int | None = None,
        downlight: int | None = None,
        timer_minutes: int | None = None,
    ) -> FanimationState | None:
        """Set fan state using read-before-write pattern.

        Only the provided fields are changed; all others are preserved
        from the current fan state (read via GET_STATUS first).

        ``direction`` is only ever passed by the fan entity when the user has a
        reverse-capable fan (DC). AC callers omit it, so the current direction
        byte is preserved untouched — AC behaviour is identical to having no
        direction control at all.
        """
        async with self._lock:
            await self._ensure_connected()

            # Read current state first (read-before-write)
            get_packet = self._build_packet(CMD_GET_STATUS)
            get_response = await self._send_and_receive(get_packet)
            if get_response is None:
                LOGGER.error("Failed to read state before writing to %s", self._name)
                return None

            current = self._parse_response(get_response)
            if current is None:
                LOGGER.error("Failed to parse state from %s", self._name)
                return None

            # Merge: use provided values, fall back to current state
            new_speed = speed if speed is not None else current.speed
            new_direction = direction if direction is not None else current.direction
            new_downlight = downlight if downlight is not None else current.downlight
            new_timer = timer_minutes if timer_minutes is not None else current.timer_minutes
            timer_hi = (new_timer >> 8) & 0xFF
            timer_lo = new_timer & 0xFF

            # Send SET_STATE (direction preserved unless a reverse-capable caller set it)
            set_packet = self._build_packet(
                CMD_SET_STATE,
                speed=new_speed,
                direction=new_direction,
                uplight=0,
                downlight=new_downlight,
                timer_hi=timer_hi,
                timer_lo=timer_lo,
            )
            await self._send_and_receive(set_packet)

            # Don't trust the echo — do a verification GET_STATUS
            verify_packet = self._build_packet(CMD_GET_STATUS)
            verify_response = await self._send_and_receive(verify_packet)
            if verify_response is None:
                return None
            return self._parse_response(verify_response)
