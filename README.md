# Fanimation BLE Ceiling Fan for Home Assistant

<sub>Repository: `FanimationHA-AC-BT`</sub>

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Home Assistant 2024.12+](https://img.shields.io/badge/Home%20Assistant-2024.12%2B-blue.svg)](https://www.home-assistant.io/)
[![HACS Default](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/default)
[![GitHub release](https://img.shields.io/github/v/release/sumgup0/FanimationHA-AC-BT)](https://github.com/sumgup0/FanimationHA-AC-BT/releases)

Control your Fanimation ceiling fan from [Home Assistant](https://www.home-assistant.io/) over **fully local Bluetooth** - speed, downlight, and sleep timer - no cloud, FanSync app, or internet access required. Works with both AC and DC fans, but only those that use Bluetooth receivers (such as BTCR9) and **not** the WiFi models.

> ### ⚠️ Bluetooth only - not WiFi
> Fanimation uses the "FanSync" name for **both** Bluetooth and WiFi receivers; only Bluetooth works here. **Not sure which you have?** Hold a BLE scanner app (e.g. [nRF Connect](https://www.nordicsemi.com/Products/Development-tools/nRF-Connect-for-mobile), LightBlue) near the fan - if a device named **`CeilingFan`** appears you're good; if nothing shows and you set the fan up over WiFi, it's a WiFi model and won't work.

## What You Get

Three entities per fan, grouped under one device:

| With a sleep timer running | At rest |
|---|---|
| ![Fan entities - timer running](docs/screenshots/fan-entities.png) | ![Fan entities - no timer set](docs/screenshots/fan-entities-no-timer-slider.png) |

| Entity | Type | Controls |
|--------|------|----------|
| Fan | `fan` | Speed slider with N discrete steps (N is your fan's speed count) |
| Downlight | `light` | On/off, brightness (0-100%) |
| Sleep Timer | `number` | 0-360 minutes (turns off fan + light on expiry); the slider is hidden when set to 0 |

### Options

Per-fan options are configurable via **Settings -> Devices -> Configure** ([screenshot](docs/screenshots/options-flow.png)):

- **Number of fan speeds** - pick a common value (1, 3, 6, 32) or type a custom number. Low/Medium/High and the slider scale automatically. ([dropdown](docs/screenshots/options-flow-speed-count-dropdown.png))
- **Default turn-on speed** - Last used, Low, Medium, or High (Low/Medium/High map proportionally to your fan's speed count). ([dropdown](docs/screenshots/options-flow-default-speed-dropdown.png))
- **Default light brightness** - 0 = last used, 1-100 = fixed level
- **Change direction** - adds a forward/reverse control; auto-on for DC fans, off for AC. Turn on manually if your fan supports electronic direction control which wasn't detected by the integration.
- **Disconnect notification** - persistent alert on first BLE failure
- **Unavailable threshold** - how many poll failures before entities go grey

## Use cases

A Fanimation Bluetooth fan normally answers only to its RF remote. In Home Assistant it can respond to the rest of the house instead.

Temperature is the obvious one: pair the fan with a thermostat or temperature sensor so it speeds up as a room warms and idles as it cools. Presence works the same way, turning the fan off when everyone leaves, or leaving it on low while you are away to keep air moving.

Schedules cover the rest. Drop to low at bedtime and arm the built-in sleep timer so the fan and light switch themselves off. Because this is a standard `fan` entity, voice control needs no extra setup: "turn off the bedroom fan" or "set the bedroom fan to 50%" works through Home Assistant Assist, or a linked Alexa, Google, or Siri assistant. Several fans can also share a single dashboard view.

Ready-to-adapt YAML for several of these is in [Example automations](#example-automations).

## What Works

The BTCR9 BLE protocol has been reverse-engineered and verified on real AC hardware (and DC fans have been community-tested):

| Feature | Range | Status |
|---------|-------|--------|
| **Fan speed** | Off, then 1 up to your fan's max speed (set speed count in options - default 3, up to 99) | Verified on 3-speed AC as well as 6- and 32-speed DC fans |
| **Fan direction** | Forward / Reverse | Shown by default for DC fans (which are auto-detected) ([#4](https://github.com/sumgup0/FanimationHA-AC-BT/issues/4)), but can toggle on/off for any fan type in per-fan settings |
| **Downlight brightness** | 0-100% | Verified |
| **Sleep timer** | 0-360 minutes | Verified |

## Installation

### Prerequisites

- **Home Assistant 2024.12 or newer**, with the built-in **Bluetooth** integration enabled.
- **Bluetooth reachability to the fan** - either a Bluetooth adapter on your HA host (built-in or USB), **or** an [ESP32 Bluetooth proxy](https://esphome.io/projects/?type=bluetooth) within range.

### HACS (Recommended)

This integration is in the **HACS default store**, so no custom repository is needed.

[![Open your Home Assistant instance and open this integration inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=sumgup0&repository=FanimationHA-AC-BT&category=integration)

1. Open **HACS** and search for **Fanimation BLE Ceiling Fan**.
2. Select it and click **Download**.
3. **Restart Home Assistant.**
4. The fan should be auto-discovered over Bluetooth. If not, add it manually: **Settings -> Devices & Services -> Add Integration -> Fanimation BLE Ceiling Fan**, and enter the MAC address (see [Troubleshooting](#troubleshooting)).

### Manual installation

1. Copy the `custom_components/fanimation/` folder into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.
3. Add the integration via **Settings -> Devices & Services**.

## Removing the integration

1. In Home Assistant, go to **Settings -> Devices & Services**.
2. Find the **Fanimation BLE Ceiling Fan** entry, open its three-dot menu, and choose **Delete**. Home Assistant unloads the integration - stopping Bluetooth polling and disconnecting from the fan - and removes its device and entities automatically.
3. *(Optional)* To remove the code as well:
   - **HACS:** open **HACS -> Fanimation BLE Ceiling Fan**, three-dot menu -> **Remove**, then restart Home Assistant.
   - **Manual install:** delete the `custom_components/fanimation/` folder and restart Home Assistant.

Everything stays local - no cloud account, no data stored outside Home Assistant - so deleting the entry leaves nothing behind online or on the fan. The fan continues to work with its physical RF remote.

## Compatibility

This integration talks to the fan's **Bluetooth receiver**, so it should work with any Fanimation ceiling fan that uses a **BTCR9-class FanSync Bluetooth receiver** - regardless of the specific fan model, motor type, or speed count. The hardware listed below is what has been **tested**. Other Fanimation Bluetooth fans may well work; they just have not been reported yet.

**Maintainer-tested hardware:**

- **BLE receiver**: Fanimation BTCR9 FanSync **Bluetooth** Receiver - the specific module tested. Other Fanimation FanSync Bluetooth receivers are expected to use the same protocol.
- **Physical remote**: Fanimation BTT9 (3 speeds, downlight, no reverse button) - the remote on the tested setup. The remote model doesn't affect Bluetooth control; any FanSync RF/BT remote should coexist fine.

**Motor types:**

- Tested on a **3-speed capacitor-switched AC motor**. AC fans with different speed counts should also work - set **Number of fan speeds** in options to match.
- **DC motors** (e.g. 6- and 32-speed) are community-tested and supported.
- **Direction / reverse**: DC motors reverse electronically, and the integration **auto-detects** them (via the `fan_type` byte) to show a forward/reverse control - with a **Change direction** toggle in options to override. The tested AC fan does not reverse electronically (it uses a physical switch on the motor housing), so the control stays hidden for AC but can be overridden in options. Confirmed on real DC hardware in [Issue #4](https://github.com/sumgup0/FanimationHA-AC-BT/issues/4).

**Known-working fans:**

- **3-speed AC fans** with BTCR9 + BTT9 remote - maintainer-verified
- **Fanimation Odyn 84"** DC fan with TR305 FanSync remote (32 speeds) - community-tested in 1.2.0 by @JesusSanchezLopez, across 4 AC and DC fans ([Issue #1](https://github.com/sumgup0/FanimationHA-AC-BT/issues/1))

If your Fanimation Bluetooth fan works - or doesn't - [open an issue](https://github.com/sumgup0/FanimationHA-AC-BT/issues) with the model name and speed count.

## Example automations

These examples use a fan named **Living Room Fan**; change the entity IDs to match yours. The three entities all live under the one fan device: the fan (`fan.living_room_fan`), its downlight (`light.living_room_fan_downlight`), and the sleep timer (`number.living_room_fan_sleep_timer`).

**Speed up when the room gets warm** - pair with any temperature sensor:

```yaml
automation:
  - alias: "Living room fan follows temperature"
    trigger:
      - platform: numeric_state
        entity_id: sensor.living_room_temperature
        above: 25          # degrees C
    action:
      - service: fan.set_percentage
        target:
          entity_id: fan.living_room_fan
        data:
          percentage: 100
```

**Turn the fan off when everyone leaves:**

```yaml
automation:
  - alias: "Fan off when away"
    trigger:
      - platform: state
        entity_id: group.family
        to: "not_home"
    action:
      - service: fan.turn_off
        target:
          entity_id: fan.living_room_fan
```

**Wind down at bedtime with the sleep timer** - it turns the fan *and* light off when it expires:

```yaml
automation:
  - alias: "Bedroom fan sleep timer at 11 PM"
    trigger:
      - platform: time
        at: "23:00:00"
    action:
      - service: fan.set_percentage      # the timer is ignored unless the fan is running
        target:
          entity_id: fan.bedroom_fan
        data:
          percentage: 33
      - service: number.set_value
        target:
          entity_id: number.bedroom_fan_sleep_timer
        data:
          value: 60                      # minutes
```

The bedtime example sets a low speed *before* arming the timer on purpose: the BTCR9 silently ignores a timer set while the fan is off (see [Troubleshooting](#troubleshooting)).

## How Home Assistant stays in sync

This is a local-polling integration (`iot_class: local_polling`). There is no cloud and no push: Home Assistant keeps a Bluetooth connection open and reads the fan's state with a `GET_STATUS` poll.

Between commands it polls every 5 minutes, which keeps Bluetooth traffic low. After you change speed, brightness, direction, or the timer it drops to a 1-second poll for three cycles, so the dashboard confirms the new state almost immediately, then returns to the slower cadence.

The BTCR9 does not push state changes on its own, and the RF remote is independent of Bluetooth, so a change made with the physical remote only shows up on the next poll, up to 5 minutes later. Every command Home Assistant sends reads the live state first (read-before-write), so remote changes are never overwritten.

The poll interval is not configurable. The **Unavailable threshold** option does control how many consecutive failed polls (each about 5 minutes apart) are tolerated before a fan's entities go grey.

## Troubleshooting

- **Fan not auto-discovered?** Confirm HA has Bluetooth range to the fan (or an ESP32 proxy nearby), then add it manually: **Settings -> Devices & Services -> Add Integration -> Fanimation BLE Ceiling Fan** and enter the MAC address.
- **Finding your MAC address:** use any BLE scanner app (nRF Connect, LightBlue) and look for a device named `CeilingFan`. Colon, dash, or no-separator formats are all accepted.
- **Entities go grey / "unavailable"?** BLE polling failed repeatedly. Move the fan closer to an adapter/proxy, or raise the **Unavailable threshold** in the integration's options.
- **State seems to lag the physical remote.** The RF remote is independent of Bluetooth; the integration polls and reconciles state, so remote changes appear after the next poll rather than instantly.
- **Sleep timer won't set / immediately reads 0?** The fan must be *running* before you set a timer - the BTCR9 controller silently ignores a timer set while the fan is off. Turn the fan on first, then set the minutes.
- **Replaced your receiver or fan?** Use **Reconfigure** (Settings -> Devices & Services -> the entry's three-dot menu -> Reconfigure) to change the MAC address in place - entity history and automations survive, no delete-and-re-add needed.
- **Reporting a bug?** Attach a diagnostics download (the fan's device page -> **Download diagnostics**) to your issue - it captures the integration's state with identifiers redacted.
- **I have a Fanimation *WiFi* fan.** This integration is Bluetooth-only and cannot control WiFi fans - see the note at the top.

## For Developers

- **Protocol reference:** [docs/BTCR9-BLE-Protocol-Reference.md](docs/BTCR9-BLE-Protocol-Reference.md) - GATT UUIDs, the 10-byte packet format and checksum, command/response details, gotchas, and a Python quick-start.
- **Diagnostic tools:** the [`tools/`](tools/) directory contains scripts to probe and verify the protocol. Setup and run instructions live in [`tools/README.md`](tools/README.md).

## Project History

Originally inspired by [toddhutch/SimpleFanController](https://github.com/toddhutch/SimpleFanController), which targeted DC Bluetooth fans using Java/TinyB. This project is a ground-up rewrite in Python/bleak for the Fanimation BTCR9 FanSync BLE receiver as a Home Assistant integration.

## Acknowledgments

This integration was developed with the assistance of Claude (Anthropic).

## License

This project is licensed under the MIT License.
