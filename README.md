# FanimationHA-AC-BT

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Home Assistant 2024.12+](https://img.shields.io/badge/Home%20Assistant-2024.12%2B-blue.svg)](https://www.home-assistant.io/)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)
[![Hardware: Fanimation](https://img.shields.io/badge/Hardware-Fanimation-green.svg)](#compatible-hardware)

[Home Assistant](https://www.home-assistant.io/) HACS custom component for **local Bluetooth control** of Fanimation ceiling fans using the BTCR9 FanSync Bluetooth receiver. No cloud, no app dependency. Includes the fully reverse-engineered BLE protocol and diagnostic tools.

## What Works

The BTCR9 BLE protocol has been fully reverse-engineered and verified against real hardware:

| Feature | Range | Status |
|---------|-------|--------|
| Fan speed | Off + 1-N (N is configurable per fan, default 3, max 99) | Verified on 3-speed AC fans (maintainer + community) and 6- and 32-speed DC fans (community-tested in 1.2.0) |
| Fan direction | Forward / Reverse | Not supported on AC motors |
| Downlight brightness | 0-100% | Verified |
| Sleep timer | 0-360 minutes | Verified |

> **Note on direction:** The BLE protocol includes a direction byte, but the AC motor fans tested for this integration (capacitor-switched, using the BTCR9 + BTT9 remote) do not support electronic direction change — the byte is accepted but has no physical effect. Capacitor-switched AC fans change direction via a physical switch on the motor housing. DC motor Fanimation fans likely support electronic reverse, but this has not yet been confirmed by community testing.

## Installation (Home Assistant)

### HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Click the three dots menu → **Custom repositories**
3. Add `https://github.com/sumgup0/FanimationHA-AC-BT` as an **Integration**
4. Search for "Fanimation" in HACS and install it
5. Restart Home Assistant
6. The fan should be auto-discovered via Bluetooth. If not, go to **Settings → Devices & Services → Add Integration → Fanimation BLE Ceiling Fan** and enter the MAC address manually.

### Manual

1. Copy the `custom_components/fanimation/` folder into your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant
3. Add the integration via **Settings → Devices & Services**

### What You Get

Three entities per fan, grouped under one device:

| With a sleep timer running | At rest |
|---|---|
| ![Fan entities — timer running](docs/screenshots/fan-entities.png) | ![Fan entities — no timer set](docs/screenshots/fan-entities-no-timer-slider.png) |

| Entity | Type | Controls |
|--------|------|----------|
| Fan | `fan` | Speed slider with N discrete steps (N is your fan's speed count) |
| Downlight | `light` | On/off, brightness (0-100%) |
| Sleep Timer | `number` | 0-360 minutes (turns off fan + light on expiry); the slider is hidden when set to 0 |

Per-fan options are configurable via **Settings → Devices → Configure** ([screenshot](docs/screenshots/options-flow.png)):

- **Number of fan speeds** — pick a common value (1, 3, 6, 32) or type a custom number. Low/Medium/High and the slider scale automatically. ([dropdown](docs/screenshots/options-flow-speed-count-dropdown.png))
- **Default turn-on speed** — Last used, Low, Medium, or High (Low/Medium/High map proportionally to your fan's speed count). ([dropdown](docs/screenshots/options-flow-default-speed-dropdown.png))
- **Default light brightness** — 0 = last used, 1-100 = fixed level
- **Disconnect notification** — persistent alert on first BLE failure
- **Unavailable threshold** — how many poll failures before entities go grey

Works with ESP32 Bluetooth proxies — no special configuration needed.

## Removing the integration

1. In Home Assistant, go to **Settings → Devices & Services**.
2. Find the **Fanimation BLE Ceiling Fan** entry, open its three-dot menu, and choose **Delete**. Home Assistant unloads the integration — stopping Bluetooth polling and disconnecting from the fan — and removes its device and entities automatically.
3. *(Optional)* To remove the code as well:
   - **HACS install:** open **HACS → Fanimation BLE Ceiling Fan**, three-dot menu → **Remove**, then restart Home Assistant.
   - **Manual install:** delete the `custom_components/fanimation/` folder and restart Home Assistant.

The integration keeps everything local — no cloud account, no data stored outside Home Assistant — so deleting the entry leaves nothing behind online or on the fan. The fan continues to work with its physical RF remote.

## Protocol Reference

See **[docs/BTCR9-BLE-Protocol-Reference.md](docs/BTCR9-BLE-Protocol-Reference.md)** for the complete protocol documentation, including:

- GATT service and characteristic UUIDs
- 10-byte packet format with checksum
- Command and response details
- Gotchas and edge cases
- A working Python quick-start example

## Diagnostic Tools

The `tools/` directory contains Python scripts used to probe and verify the protocol:

| Script | Purpose |
|--------|---------|
| `probe_fan.py` | Full GATT enumeration and interactive speed/direction/light probing |
| `sniff_light.py` | Remote button sniffer — shows which bytes change when you use the physical remote |
| `test_light.py` | Targeted downlight control verification |
| `test_timer.py` | Timer functionality testing |

### Running the tools

```bash
# Set up a Python virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r tools/requirements.txt

# Run a script (replace MAC with your fan's address)
python tools/probe_fan.py 50:8C:B1:4A:16:A0
```

Find your fan's MAC address using any BLE scanner app (nRF Connect, LightBlue) — look for a device named `CeilingFan`.

## Compatible Hardware

- **BLE receiver**: Fanimation BTCR9 FanSync Bluetooth Receiver
- **Physical remote**: Fanimation BTT9 (3 speeds, downlight, no reverse)
- **Smartphone app**: FanSync (Android / iOS)
- **Motor type**: AC (3-speed capacitor-switched) — fully tested

### Fans with more than 3 speeds (community-tested in 1.2.0)

Fanimation BLE fans with more than 3 discrete speeds — typically DC models — are also supported as of 1.2.0. Set **Number of fan speeds** to match your fan during setup (or change it later in options). Community-tested by @JesusSanchezLopez across 4 AC and DC fans on his setup (Issue #1), including:

- **Fanimation Odyn 84"** DC fan with TR305 FanSync remote — 32 speeds

Other Fanimation FanSync Bluetooth models likely share the same protocol; if yours works (or doesn't), open an issue with the model name and speed count.

## Project History

Originally inspired by [toddhutch/SimpleFanController](https://github.com/toddhutch/SimpleFanController), which targeted DC Bluetooth fans using Java/TinyB. This project is a ground-up rewrite in Python/bleak for the Fanimation BTCR9 FanSync BLE receiver as a Home Assistant integration.

## License

This project is licensed under the MIT License.
