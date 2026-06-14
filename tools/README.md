# Diagnostic Tools

Python scripts used to probe and verify the Fanimation BTCR9 BLE protocol. These are developer/debugging utilities — they are **not** required to use the Home Assistant integration.

| Script | Purpose |
|--------|---------|
| `probe_fan.py` | Full GATT enumeration and interactive speed/direction/light probing |
| `sniff_light.py` | Remote button sniffer — shows which bytes change when you use the physical remote |
| `test_light.py` | Targeted downlight control verification |
| `test_timer.py` | Timer functionality testing |

## Running the tools

```bash
# Set up a Python virtual environment
python -m venv venv
source venv/bin/activate            # macOS / Linux
# venv\Scripts\Activate.ps1         # Windows (PowerShell)
# venv\Scripts\activate.bat         # Windows (cmd)

# Install dependencies
pip install -r requirements.txt

# Run a script (replace the MAC with your fan's address)
python probe_fan.py 50:8C:B1:4A:16:A0
```

> **Windows PowerShell note:** if `Activate.ps1` is blocked by execution policy, run
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that session first.

Find your fan's MAC address using any BLE scanner app (nRF Connect, LightBlue) — look for a device named `CeilingFan`.

> **Heads-up:** the BTCR9 accepts only **one** Bluetooth connection at a time. Close the FanSync app (and make sure Home Assistant isn't actively polling the fan) before running these scripts, or the connection will fail.

See [../docs/BTCR9-BLE-Protocol-Reference.md](../docs/BTCR9-BLE-Protocol-Reference.md) for the full protocol documentation.
