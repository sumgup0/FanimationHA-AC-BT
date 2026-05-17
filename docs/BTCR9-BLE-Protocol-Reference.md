# Fanimation BTCR9 FanSync Bluetooth Protocol Reference

> **Status**: Hardware-verified on a BTCR9 AC motor ceiling fan with downlight (2026-03-01)
>
> **Applicability**: Fanimation ceiling fans using the BTCR9 FanSync Bluetooth receiver and BTT9 remote. Other Fanimation FanSync Bluetooth models likely share this protocol but have not been tested.

## Table of Contents

1. [Overview](#1-overview)
2. [Hardware](#2-hardware)
3. [BLE Basics](#3-ble-basics)
4. [GATT Service Table](#4-gatt-service-table)
5. [Packet Format](#5-packet-format)
6. [Commands](#6-commands)
   - [GET_STATUS (0x30)](#get_status-0x30)
   - [SET_STATE (0x31)](#set_state-0x31)
   - [STATUS_RESPONSE (0x32)](#status_response-0x32)
7. [Fan Speed](#7-fan-speed)
8. [Direction](#8-direction)
9. [Downlight](#9-downlight)
10. [Timer](#10-timer)
11. [Gotchas & Edge Cases](#11-gotchas--edge-cases)
12. [Quick Start (Python)](#12-quick-start-python)
13. [Untested / Unknown](#13-untested--unknown)

---

## 1. Overview

The Fanimation BTCR9 is a Bluetooth Low Energy (BLE) receiver module installed inside Fanimation ceiling fans. It allows wireless control of the fan motor (speed, direction) and an integrated downlight (on/off, brightness) from a smartphone app (FanSync) or a physical RF remote (BTT9).

This document describes the BLE protocol used to communicate with the BTCR9 — enough for any developer to build their own controller, Home Assistant integration, or automation script.

**What you can control over BLE:**

- Fan speed (off, low, medium, high)
- Fan direction (forward, reverse)
- Downlight brightness (0-100%)
- Sleep timer (0-360 minutes)

**What you cannot control over BLE:**

- The physical RF remote operates on 303.875 MHz, completely independent of BLE. BLE cannot intercept or replay RF commands, but you can read the resulting fan state via BLE after a remote action.

---

## 2. Hardware

| Detail | Value |
|--------|-------|
| BLE receiver module | Fanimation BTCR9 |
| Physical remote | Fanimation BTT9 (3 speeds, downlight, no reverse button) |
| Smartphone app | FanSync (Android / iOS) |
| Motor type | AC (3-speed capacitor-switched) |
| Light | Downlight only (no uplight on this model) |
| BLE device name | `CeilingFan` |
| BLE advertising | Standard connectable advertising, no pairing or authentication required |
| Concurrent connections | **One connection at a time** — the app and a script cannot connect simultaneously |

The BLE chip appears to be a Texas Instruments CC2640 or CC2650 (based on the presence of a TI OAD firmware update service).

---

## 3. BLE Basics

If you're new to Bluetooth Low Energy, here's a quick primer on the concepts used in this document.

**GATT (Generic Attribute Profile)** is how BLE devices expose their data. Think of it as a structured database on the device.

- **Service**: A group of related features (like "Fan Controller"). Identified by a UUID.
- **Characteristic**: A single data point within a service (like "write commands here" or "read notifications here"). Also identified by a UUID.
- **Descriptor**: Metadata about a characteristic (e.g., its human-readable name).

**How communication works:**

1. Your phone/computer **scans** for BLE devices and finds one advertising as `CeilingFan`.
2. You **connect** to the device (no pairing or PIN required).
3. You **write** a 10-byte command to the Write characteristic.
4. The device sends back a 10-byte response via a **notification** on the Notify characteristic.

**Notifications** are push messages from the device. You must **subscribe** to them before the device will send any. Without subscribing, writes will still work but you won't see responses.

---

## 4. GATT Service Table

The BTCR9 exposes the following GATT services and characteristics:

### Fan Controller Service (Primary — this is what you use)

| UUID | Type | Properties | Description |
|------|------|------------|-------------|
| `0000e000-0000-1000-8000-00805f9b34fb` | Service | — | Fan controller service |
| `0000e001-0000-1000-8000-00805f9b34fb` | Characteristic | Write | **Command input** — send commands here |
| `0000e002-0000-1000-8000-00805f9b34fb` | Characteristic | Notify | **Status output** — receive responses here |

### Generic Access Service (Standard BLE)

| UUID | Type | Description |
|------|------|-------------|
| `00001800-0000-1000-8000-00805f9b34fb` | Service | Standard GAP service |
| `00002a00-...` | Characteristic | Device Name (`CeilingFan`) |
| `00002a01-...` | Characteristic | Appearance |
| `00002a04-...` | Characteristic | Peripheral Preferred Connection Parameters |

### TI OAD Service (Firmware Update — ignore this)

| UUID | Type | Description |
|------|------|-------------|
| `539c6813-0ad0-2137-4f79-bf1a11984790` | Service | TI Over-the-Air Download |
| `539c6813-0ad1-2137-4f79-bf1a11984790` | Characteristic | Image Identify (write, notify) |
| `539c6813-0ad2-2137-4f79-bf1a11984790` | Characteristic | Image Block (write, notify) |

The OAD service is used for firmware updates and should not be used for fan control. Interacting with it incorrectly could brick the device.

---

## 5. Packet Format

All commands and responses are exactly **10 bytes**:

```
Byte:   [0]    [1]    [2]     [3]    [4]      [5]       [6]       [7]       [8]      [9]
Field:  START  CMD    SPEED   DIR    UPLIGHT  DOWNLIGHT TIMER_HI  TIMER_LO  FANTYPE  CHECKSUM
```

| Byte | Field | Description |
|------|-------|-------------|
| 0 | START | Always `0x53` (ASCII `S`) |
| 1 | CMD | Command type (see [Commands](#6-commands)) |
| 2 | SPEED | Fan speed: 0=off, 1=low, 2=med, 3=high |
| 3 | DIR | Fan direction: 0=forward, 1=reverse |
| 4 | UPLIGHT | Uplight brightness (unused on BTCR9, always 0) |
| 5 | DOWNLIGHT | Downlight brightness: 0=off, 1-100=percent |
| 6 | TIMER_HI | Sleep timer high byte (big-endian, in minutes) |
| 7 | TIMER_LO | Sleep timer low byte (big-endian, in minutes) |
| 8 | FANTYPE | Fan type selector (unused on BTCR9, always 0) |
| 9 | CHECKSUM | `sum(bytes[0] through bytes[8]) & 0xFF` |

### Checksum Calculation

The checksum is the lowest 8 bits of the sum of bytes 0 through 8:

```
checksum = (byte[0] + byte[1] + byte[2] + ... + byte[8]) & 0xFF
```

**Example**: For the packet `53 31 01 00 00 64 00 00 00`:
- Sum = 0x53 + 0x31 + 0x01 + 0x00 + 0x00 + 0x64 + 0x00 + 0x00 + 0x00 = 0xE9
- Checksum = 0xE9
- Full packet: `53 31 01 00 00 64 00 00 00 E9`

---

## 6. Commands

### GET_STATUS (0x30)

Requests the current state of the fan. Send this to characteristic `0xE001`:

```
53 30 00 00 00 00 00 00 00 83
```

All bytes except START, CMD, and CHECKSUM are zero. The fan responds with a [STATUS_RESPONSE](#status_response-0x32) notification on `0xE002`.

### SET_STATE (0x31)

Sets the fan state. Send to characteristic `0xE001` with the desired values:

```
53 31 [SPEED] [DIR] [UPLIGHT] [DOWNLIGHT] [TIMER_HI] [TIMER_LO] [FANTYPE] [CHECKSUM]
```

**Every field is sent in every command.** There is no way to change just one field — you must send the complete desired state. To change only the light, for example, you should first GET_STATUS to read the current speed and direction, then send SET_STATE with those values preserved and only the downlight byte changed.

The fan responds with a STATUS_RESPONSE notification confirming the new state.

**Example — turn fan to medium speed, light at 75%, no timer:**
```
53 31 02 00 00 4B 00 00 00 D1
```

**Example — set a 2-hour (120-minute) timer with fan on low:**
```
Timer: 120 = 0x0078 → TIMER_HI=0x00, TIMER_LO=0x78
53 31 01 00 00 00 00 78 00 FD
```

### STATUS_RESPONSE (0x32)

This is what the fan sends back on `0xE002` (via notification) in response to GET_STATUS or SET_STATE:

```
53 32 [SPEED] [DIR] [UPLIGHT] [DOWNLIGHT] [TIMER_HI] [TIMER_LO] [FANTYPE] [CHECKSUM]
```

The byte layout is identical to SET_STATE except byte[1] is `0x32` instead of `0x31`.

> **Important**: After a SET_STATE, the fan sends an immediate echo that may contain the values you sent — even if they are invalid. Always follow up with a GET_STATUS to confirm the actual fan state. See [Gotchas](#11-gotchas--edge-cases) for details.

---

## 7. Fan Speed

| Value | Behavior |
|-------|----------|
| 0 | Off — motor stops |
| 1 | Lowest speed |
| 2 to N-1 | Intermediate speed steps |
| N | Highest speed supported by the connected motor |
| N+1 or higher | **Silently turns the fan off** — see [Gotchas: Out-of-Range Speed](#out-of-range-speed-silently-turns-fan-off) |

The maximum usable speed (N) depends on the specific fan. Reference points from real hardware:

- **3-speed AC fan with BTCR9 + BTT9 remote** (maintainer): N=3
- **Fanimation Odyn 84" DC fan with TR305 remote** (community-tested in v1.2.0): N=32

Other Fanimation BLE fans likely fall somewhere in this range. The Home Assistant integration's per-fan "Number of fan speeds" option lets you tell it which value to use for N.

**Recommendation**: Match the configured speed count to your fan's hardware capability. Setting it higher than the motor supports causes the fan to turn off when the slider crosses the threshold (see the gotcha below).

---

## 8. Direction

| Value | Direction | Description |
|-------|-----------|-------------|
| 0 | Forward | Standard airflow direction (default) |
| 1 | Reverse | Reversed airflow |

**⚠️ NOT SUPPORTED on the AC motor tested for this integration.** Testing on BTCR9 hardware with a capacitor-switched AC motor confirmed that the direction byte is accepted in SET_STATE but has no physical effect — the fan continues spinning in the same direction. The verification GET_STATUS always returns direction=0 (forward) regardless of the value sent. The BTT9 physical remote also has no reverse button.

The direction byte likely works on Fanimation DC motor models that support electronic reverse, but this has not yet been confirmed by community testing. Capacitor-switched AC motors require a physical DPDT switch on the motor housing to change direction.

The Home Assistant integration does not expose direction control. The direction byte is always preserved from the current GET_STATUS response during read-before-write operations.

---

## 9. Downlight

The downlight is controlled via byte[5] with a brightness percentage:

| Value | Result |
|-------|--------|
| 0 | Light off |
| 1 | Minimum brightness |
| 22 | Dim (observed from remote) |
| 65 | Default on brightness (observed from remote) |
| 100 | Maximum brightness |
| 101-255 | **Silently rejected** — see below |

### Out-of-Range Rejection Behavior

Values above 100 are handled in a surprising way:

1. You send SET_STATE with downlight=255
2. The fan echoes back a STATUS_RESPONSE with downlight=255 (looks like it worked)
3. You send GET_STATUS to check the actual state
4. The response shows downlight=0 (the value was rejected and the light is off)

**The SET_STATE echo is not trustworthy for out-of-range values.** Always verify with GET_STATUS.

### Notes

- The light remembers its last brightness when turned on via the physical remote
- Via BLE, you set the exact brightness each time
- Byte[4] (uplight) is accepted by the BLE chip but the BTCR9 has no uplight hardware, so it has no physical effect

---

## 10. Timer

The sleep timer automatically turns off **both the fan and the light** when it expires.

### Encoding

The timer is stored as a **big-endian 16-bit unsigned integer** in minutes:

```
Timer minutes = (byte[6] << 8) | byte[7]
```

| Timer value | byte[6] (high) | byte[7] (low) | Minutes |
|-------------|----------------|----------------|---------|
| No timer | 0x00 | 0x00 | 0 |
| 1 minute | 0x00 | 0x01 | 1 |
| 1 hour | 0x00 | 0x3C | 60 |
| 2 hours | 0x00 | 0x78 | 120 |
| 6 hours (max) | 0x01 | 0x68 | 360 |

### Countdown Behavior

- The timer counts down in real-time, decrementing by 1 each minute
- The remaining time is visible in GET_STATUS responses
- When the timer reaches 0, the fan turns off (speed=0) and the light turns off (downlight=0)
- The timer value itself resets to 0

### Example Countdown (6-hour timer observed)

| Elapsed time | byte[6] | byte[7] | Remaining |
|---|---|---|---|
| 0 min | 0x01 | 0x68 | 360 min |
| 1 min | 0x01 | 0x67 | 359 min |
| 2 min | 0x01 | 0x66 | 358 min |

### Canceling a Timer

Send SET_STATE with byte[6]=0 and byte[7]=0 (timer minutes = 0) while preserving the current speed and light values. The fan and light will continue operating without a shutdown timer.

---

## 11. Gotchas & Edge Cases

### SET_STATE Echo Is Not Ground Truth

When you send a SET_STATE command, the fan immediately responds with a STATUS_RESPONSE that echoes back whatever you sent — **even if the values are invalid**. For example, sending downlight=255 gets echoed as downlight=255, but a subsequent GET_STATUS reveals downlight=0 (rejected).

**Always follow SET_STATE with GET_STATUS to verify the actual fan state.**

### Out-of-Range Speed Silently Turns Fan Off

If you send a SPEED byte higher than the connected motor's physical maximum (for example, SPEED=5 on a 3-speed fan), the BTCR9 acknowledges the BLE write normally, but the verification GET_STATUS returns SPEED=0 — the fan turns off. There is no error code or rejection signal; the misconfigured value just looks like an off command after the fact.

This caused a "stuck-off loop": a fan configured for too many speeds in Home Assistant would resend the over-range value on every "Last Used" turn-on, keeping itself permanently off. The fix (included in v1.2.0) is to make "Number of fan speeds" configurable per fan, and to read `_last_speed` from the verified GET_STATUS response rather than from the requested value.

**Implication for any code talking to the BTCR9**: read your "what speed did the fan actually accept" value from the GET_STATUS-verified response, never from the requested value.

### Single BLE Connection

The BTCR9 only accepts one BLE connection at a time. If the FanSync app is connected, your script cannot connect, and vice versa. Make sure to disconnect one before connecting the other.

### Direction Change Does Not Work on the Tested AC Motor

The direction byte (byte[3]) is accepted in SET_STATE but has no physical effect on the capacitor-switched AC motor tested for this integration. The BLE chip echoes the value in the SET_STATE response, but the verification GET_STATUS always returns 0 (forward). This feature likely works on Fanimation DC motor fans but has not yet been confirmed by community testing. See [Section 8: Direction](#8-direction) for details.

### RF Remote and BLE Are Independent

The BTT9 RF remote communicates on 303.875 MHz, not via BLE. When someone uses the physical remote, the BLE chip does not send a notification — you must poll with GET_STATUS to discover state changes made by the remote.

### Checksum Validation

The fan does not appear to reject commands with incorrect checksums in all cases, but for reliable operation, always calculate and include the correct checksum.

---

## 12. Quick Start (Python)

A minimal example using the [bleak](https://github.com/hbldh/bleak) library (v2.x):

```python
import asyncio
from bleak import BleakClient

DEVICE_MAC  = "50:8C:B1:4A:16:A0"  # Replace with your fan's MAC
CHAR_WRITE  = "0000e001-0000-1000-8000-00805f9b34fb"
CHAR_NOTIFY = "0000e002-0000-1000-8000-00805f9b34fb"

START = 0x53
GET_STATUS = 0x30
SET_STATE  = 0x31


def build_packet(cmd, speed=0, direction=0, downlight=0,
                 timer_hi=0, timer_lo=0):
    """Build a 10-byte command packet."""
    b = bytearray([START, cmd, speed, direction, 0, downlight,
                    timer_hi, timer_lo, 0, 0])
    b[9] = sum(b[:9]) & 0xFF
    return bytes(b)


def on_notify(sender, data: bytearray):
    """Handle status notifications."""
    if len(data) >= 10:
        print(f"Speed={data[2]} Dir={data[3]} Light={data[5]} "
              f"Timer={(data[6]<<8)|data[7]}min")


async def main():
    async with BleakClient(DEVICE_MAC, timeout=20.0) as client:
        # Subscribe to notifications
        await client.start_notify(CHAR_NOTIFY, on_notify)

        # Read current state
        await client.write_gatt_char(CHAR_WRITE,
                                      build_packet(GET_STATUS))
        await asyncio.sleep(1)

        # Set fan to medium speed with light at 75%
        await client.write_gatt_char(CHAR_WRITE,
                                      build_packet(SET_STATE, speed=2,
                                                   downlight=75))
        await asyncio.sleep(1)

        # Verify
        await client.write_gatt_char(CHAR_WRITE,
                                      build_packet(GET_STATUS))
        await asyncio.sleep(1)

asyncio.run(main())
```

**Install dependencies**: `pip install bleak`

**Find your fan's MAC address**: Use any BLE scanner app (nRF Connect, LightBlue) and look for a device named `CeilingFan`.

---

## 13. Untested / Unknown

The following protocol fields exist in the packet format but have not been verified with physical effects on the BTCR9:

| Byte | Field | Notes |
|------|-------|-------|
| 4 | Uplight | The BLE chip accepts values 0-255 and echoes them, but the BTCR9 has no uplight fixture. May work on Fanimation models with an uplight. |
| 8 | Fan Type | Purpose unknown. Always 0 in all observed responses. May select between AC/DC motor behavior on multi-mode receivers. |
| — | Timer range >360 | The FanSync app limits the timer to 360 minutes (6 hours). Values above 360 have not been tested. |
| — | OAD Service | The TI OAD (Over-the-Air Download) firmware update service is present but has not been tested. Do not interact with it unless you know what you are doing. |

---

*This protocol was reverse-engineered from the [SimpleFanController](https://github.com/toddhutch/SimpleFanController) Java/TinyB project (targeting DC fans) and verified against BTCR9 AC motor hardware using Python/bleak diagnostic scripts. All findings are based on empirical testing — no official Fanimation documentation was used.*
