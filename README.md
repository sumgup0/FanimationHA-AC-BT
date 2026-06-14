# Fanimation BLE Ceiling Fan for Home Assistant

<sub>Repository: `FanimationHA-AC-BT`</sub>

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Home Assistant 2024.12+](https://img.shields.io/badge/Home%20Assistant-2024.12%2B-blue.svg)](https://www.home-assistant.io/)
[![HACS Default](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/default)
[![GitHub release](https://img.shields.io/github/v/release/sumgup0/FanimationHA-AC-BT)](https://github.com/sumgup0/FanimationHA-AC-BT/releases)

Control your Fanimation ceiling fan from [Home Assistant](https://www.home-assistant.io/) over **local Bluetooth** — speed, downlight, and sleep timer, with no cloud, no app, and no internet. Works with both AC and DC fans, but only those that use Bluetooth receivers (such as BTCR9) and **not** the WiFi models.

> ### ⚠️ Bluetooth only — not WiFi
> Fanimation uses the "FanSync" name for **both** Bluetooth and WiFi receivers; only Bluetooth works here. **Not sure which you have?** Hold a BLE scanner app (e.g. [nRF Connect](https://www.nordicsemi.com/Products/Development-tools/nRF-Connect-for-mobile), LightBlue) near the fan — if a device named **`CeilingFan`** appears you're good; if nothing shows and you set the fan up over WiFi, it's a WiFi model and won't work.

## What You Get

Three entities per fan, grouped under one device:

| With a sleep timer running | At rest |
|---|---|
| ![Fan entities — timer running](docs/screenshots/fan-entities.png) | ![Fan entities — no timer set](docs/screenshots/fan-entities-no-timer-slider.png) |

| Entity | Type | Controls |
|--------|------|----------|
| Fan | `fan` | Speed slider with N discrete steps (N is your fan's speed count) |
| Downlight | `light` | On/off, brightness (0-100%) |
| Sleep Timer | `number` | 0-360 minutes (turns off fan + light on expiry); the slider is hidden when set to 0 |

### Options

Per-fan options are configurable via **Settings → Devices → Configure** ([screenshot](docs/screenshots/options-flow.png)):

- **Number of fan speeds** — pick a common value (1, 3, 6, 32) or type a custom number. Low/Medium/High and the slider scale automatically. ([dropdown](docs/screenshots/options-flow-speed-count-dropdown.png))
- **Default turn-on speed** — Last used, Low, Medium, or High (Low/Medium/High map proportionally to your fan's speed count). ([dropdown](docs/screenshots/options-flow-default-speed-dropdown.png))
- **Default light brightness** — 0 = last used, 1-100 = fixed level
- **Disconnect notification** — persistent alert on first BLE failure
- **Unavailable threshold** — how many poll failures before entities go grey

## What Works

The BTCR9 BLE protocol has been reverse-engineered and verified on real AC hardware (DC fans community-tested):

| Feature | Range | Status |
|---------|-------|--------|
| Fan speed | Off, then 1 up to your fan's max speed (set speed count in options — default 3, up to 99) | Verified on 3-speed AC and 6- & 32-speed DC fans |
| Fan direction | Forward / Reverse | Not exposed in 1.2.1 — community testing in progress ([#4](https://github.com/sumgup0/FanimationHA-AC-BT/issues/4)) |
| Downlight brightness | 0–100% | Verified |
| Sleep timer | 0–360 minutes | Verified |

## Prerequisites

- **Home Assistant 2024.12 or newer**, with the built-in **Bluetooth** integration enabled.
- **Bluetooth reachability to the fan** — either a Bluetooth adapter on your HA host (built-in or USB), **or** an [ESP32 Bluetooth proxy](https://esphome.io/projects/?type=bluetooth) within range.
- **No cloud account, no internet, no FanSync app** required — control is 100% local.

## Installation

### HACS (Recommended)

This integration is in the **HACS default store**, so no custom repository is needed.

[![Open your Home Assistant instance and open this integration inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=sumgup0&repository=FanimationHA-AC-BT&category=integration)

1. Open **HACS** and search for **Fanimation BLE Ceiling Fan**.
2. Select it and click **Download**.
3. **Restart Home Assistant.**
4. The fan should be auto-discovered over Bluetooth. If not, add it manually: **Settings → Devices & Services → Add Integration → Fanimation BLE Ceiling Fan**, and enter the MAC address (see [Troubleshooting](#troubleshooting)).

### Manual installation

1. Copy the `custom_components/fanimation/` folder into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.
3. Add the integration via **Settings → Devices & Services**.

## Compatibility

This integration talks to the fan's **Bluetooth receiver**, so it should work with any Fanimation ceiling fan that uses a **BTCR9-class FanSync Bluetooth receiver** — regardless of the specific fan model, motor type, or speed count. The hardware listed below is what has been **tested**; treat it as confirmed examples, not an exhaustive list.

**Tested hardware:**

- **BLE receiver**: Fanimation BTCR9 FanSync **Bluetooth** Receiver — the specific module tested. Other Fanimation FanSync *Bluetooth* receivers are expected to use the same protocol.
- **Physical remote**: Fanimation BTT9 (3 speeds, downlight, no reverse button) — the remote on the tested setup. The remote model doesn't affect Bluetooth control; any FanSync BT remote should coexist fine.

**Motor types:**

- Tested on a **3-speed capacitor-switched AC motor**. AC fans with different speed counts should also work — set **Number of fan speeds** in options to match.
- **DC motors** (e.g. 6- and 32-speed) are community-tested and supported.
- **Direction / reverse**: the specific AC fan tested does not change direction electronically (it reverses via a physical switch on the motor housing). Other fans — particularly DC models — may support electronic reverse; that's being investigated in [Issue #4](https://github.com/sumgup0/FanimationHA-AC-BT/issues/4). Direction control is not exposed in 1.2.1.

**Known-working fans:**

- **3-speed AC fans** with BTCR9 + BTT9 remote — maintainer-verified
- **Fanimation Odyn 84"** DC fan with TR305 FanSync remote (32 speeds) — community-tested in 1.2.0 by @JesusSanchezLopez, across 4 AC and DC fans ([Issue #1](https://github.com/sumgup0/FanimationHA-AC-BT/issues/1))

If your Fanimation Bluetooth fan works — or doesn't — [open an issue](https://github.com/sumgup0/FanimationHA-AC-BT/issues) with the model name and speed count.

## Troubleshooting

- **Fan not auto-discovered?** Confirm HA has Bluetooth range to the fan (or an ESP32 proxy nearby), then add it manually: **Settings → Devices & Services → Add Integration → Fanimation BLE Ceiling Fan** and enter the MAC address.
- **Finding your MAC address:** use any BLE scanner app (nRF Connect, LightBlue) and look for a device named `CeilingFan`. Colon, dash, or no-separator formats are all accepted.
- **Entities go grey / "unavailable"?** BLE polling failed repeatedly. Move the fan closer to an adapter/proxy, or raise the **Unavailable threshold** in the integration's options.
- **State seems to lag the physical remote.** The RF remote is independent of Bluetooth; the integration polls and reconciles state, so remote changes appear after the next poll rather than instantly.
- **I have a Fanimation *WiFi* fan.** This integration is Bluetooth-only and cannot control WiFi fans — see the note at the top.

## For Developers

- **Protocol reference:** [docs/BTCR9-BLE-Protocol-Reference.md](docs/BTCR9-BLE-Protocol-Reference.md) — GATT UUIDs, the 10-byte packet format and checksum, command/response details, gotchas, and a Python quick-start.
- **Diagnostic tools:** the [`tools/`](tools/) directory contains scripts to probe and verify the protocol. Setup and run instructions live in [`tools/README.md`](tools/README.md).

## Project History

Originally inspired by [toddhutch/SimpleFanController](https://github.com/toddhutch/SimpleFanController), which targeted DC Bluetooth fans using Java/TinyB. This project is a ground-up rewrite in Python/bleak for the Fanimation BTCR9 FanSync BLE receiver as a Home Assistant integration.

## License

This project is licensed under the MIT License.
