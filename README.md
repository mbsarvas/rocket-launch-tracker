# 🚀 Rocket Launch Tracker

A Raspberry Pi Zero 2 W project that displays upcoming rocket launches in real time across six I2C LCD displays, powered by the [Launch Library 2 API](https://thespacedevs.com/llapi).

**Created by Matthew Sarvas**

---

## Before You Start

If you use **Raspberry Pi Imager** to flash your SD card, it will prompt you to apply OS customisation settings before writing — use this to pre-configure your username, password, Wi-Fi, and SSH. A password is required for the initial setup steps in this guide — once setup is complete the script runs hands-free on every boot.

---

## Features

- Displays the next 3 upcoming rocket launches simultaneously
- Three **16x2 LCDs** show the launch site and country for each launch
- Three **20x4 LCDs** show the mission name, rocket, date, and time (Pacific Time) for each launch
- Automatically converts launch times to PST or PDT
- Physical button to toggle between all launches and Vandenberg SFB launches only
- Live countdown timer on displays when the API rate limit is reached
- Auto-refreshes every 60 seconds (with API key) or 6 minutes (anonymous)
- Automatically runs on boot via systemd
- Falls back to anonymous API access if the API key is missing or invalid

---

## Hardware

- Raspberry Pi Zero 2 W
- 3x 16x2 I2C LCD displays (PCF8574 backpack)
- 3x 20x4 I2C LCD displays (PCF8574 backpack)
- 1x momentary push button
- Jumper wires

---

## Wiring

### I2C LCD Displays (all 6 share the same I2C bus)

| LCD | Size | I2C Address | Slot |
|-----|------|-------------|------|
| 16x2 #1 | 16 cols, 2 rows | 0x24 | Launch #1 |
| 16x2 #2 | 16 cols, 2 rows | 0x23 | Launch #2 |
| 16x2 #3 | 16 cols, 2 rows | 0x22 | Launch #3 |
| 20x4 #1 | 20 cols, 4 rows | 0x27 | Launch #1 |
| 20x4 #2 | 20 cols, 4 rows | 0x26 | Launch #2 |
| 20x4 #3 | 20 cols, 4 rows | 0x25 | Launch #3 |

All LCD displays connect to the same four Pi pins:

| LCD Pin | Pi Pin | Description |
|---------|--------|-------------|
| VCC | Pin 2 | 5V Power |
| GND | Pin 6 | Ground |
| SDA | Pin 3 (GPIO2) | I2C Data |
| SCL | Pin 5 (GPIO3) | I2C Clock |

### Toggle Button

| Button Leg | Pi Pin | Description |
|------------|--------|-------------|
| Leg 1 | Pin 13 (GPIO27) | Signal |
| Leg 2 | Pin 9 (GND) | Ground |

No external resistor is needed — the Pi's internal pull-up resistor is used.

### Display Layout

Each numbered slot pairs one 16x2 with one 20x4 to show the same launch:

```
┌─────────────────┐   ┌──────────────────────┐
│ Vandenberg SFB  │   │ Falcon 9 Block 5     │
│ United States   │   │ Starlink Group 6-10  │
└─────────────────┘   │ Mon Apr 28 2026      │
  16x2 @ 0x24         │ 10:30 AM PDT         │
  (Slot 0)            └──────────────────────┘
                         20x4 @ 0x27
                         (Slot 0)
```

---

## Installation

### 1. Enable I2C on the Pi

```bash
sudo raspi-config
# Interface Options → I2C → Enable
sudo reboot
```
> You may be prompted for your password.

### 2. Verify displays are detected

```bash
sudo apt install i2c-tools
i2cdetect -y 1
```
> You may be prompted for your password.

You should see addresses `0x22` through `0x27` appear in the grid.

### 3. Download the script

```bash
cd /home/YOUR_USERNAME
mkdir rocket-launch-tracker
cd rocket-launch-tracker
wget https://raw.githubusercontent.com/mbsarvas/rocket-launch-tracker/main/rocket_launch_tracker.py
wget https://raw.githubusercontent.com/mbsarvas/rocket-launch-tracker/main/requirements.txt
```
> Replace `YOUR_USERNAME` with your Pi's username. You can check it by running `whoami`.

### 4. Set your username in the script

```bash
nano /home/YOUR_USERNAME/rocket-launch-tracker/rocket_launch_tracker.py
```
> You should still be inside the `rocket-launch-tracker` folder from the previous step. If not, run `cd /home/YOUR_USERNAME/rocket-launch-tracker` first.

Find this line near the top and change `"pi"` to match your Pi username:

```python
PI_USER = "pi"   # change this to your username e.g. "mbsarvas"
```

Save and exit with `Ctrl+X`, then `Y`, then `Enter`. You can find your username by running `whoami`.

### 5. Install dependencies

```bash
cd /home/YOUR_USERNAME/rocket-launch-tracker
pip install -r requirements.txt --break-system-packages
```

### 6. Test the script

```bash
python3 rocket_launch_tracker.py
```

All six displays should initialize and begin showing launch data within a few seconds.

---

## Autostart on Boot (systemd)

### 1. Create the service file

```bash
sudo nano /etc/systemd/system/rockettracker.service
```
> You may be prompted for your password.

Paste the following (update the username and path if needed):

```ini
[Unit]
Description=Rocket Launch Tracker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/home/YOUR_USERNAME/rocket-launch-tracker
ExecStart=/usr/bin/python3 /home/YOUR_USERNAME/rocket-launch-tracker/rocket_launch_tracker.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```
> Replace `YOUR_USERNAME` with your Pi's username (e.g. `pi`, `mbsarvas`). You can check it by running `whoami` in the terminal.

Save and exit with `Ctrl+X`, then `Y`, then `Enter`.

### 2. Enable and start the service

```bash
sudo systemctl daemon-reload
sudo systemctl enable rockettracker
sudo systemctl start rockettracker
```
> You may be prompted for your password.

### 3. Check it is running

```bash
sudo systemctl status rockettracker
```
> You may be prompted for your password.

You should see `Active: active (running)` in the output. If it shows `failed` or `inactive` check the logs with `sudo journalctl -u rockettracker -f` for more details.

### 4. Reboot to confirm autostart

```bash
sudo reboot
```

After rebooting the script will start automatically and the displays should come to life within a minute or so as the Pi boots and connects to the network.

### Useful service commands

```bash
# View live logs
sudo journalctl -u rockettracker -f

# Stop the script
sudo systemctl stop rockettracker

# Restart after making changes
sudo systemctl restart rockettracker

# Disable autostart
sudo systemctl disable rockettracker
```

---

## API Key (Optional)

By default the script uses anonymous access to the Launch Library 2 API, which allows 15 requests per hour. The script refreshes every 6 minutes (10 requests per hour) to stay safely within this limit.

To get a higher rate limit (60 requests/hour, one refresh per minute):

1. Support [TheSpaceDevs on Patreon](https://www.patreon.com/TheSpaceDevs) at any paid tier
2. Receive your API key via Patreon message or their Discord
3. Save the key to a plain text file on the Pi:

```bash
echo "your_api_key_here" > /home/pi/ll2_api_key.txt
```

The script will automatically detect the key file on next start and switch to the faster refresh rate. If the key is ever removed or becomes invalid, it falls back to anonymous access automatically — no changes to the script required.

---

## Button Usage

| Action | Result |
|--------|--------|
| Single press | Toggles between **All Locations** and **Vandenberg SFB only** |

When toggled, all displays briefly show the new filter mode and then display updated launch data.

---

## Configuration

The following constants at the top of `rocket_launch_tracker.py` can be adjusted:

| Constant | Default | Description |
|----------|---------|-------------|
| `REFRESH_INTERVAL_ANON` | 300 | Refresh interval in seconds (anonymous) |
| `REFRESH_INTERVAL_AUTH` | 60 | Refresh interval in seconds (with API key) |
| `TOTAL_SLOTS` | 3 | Number of launch slots to display |
| `BUTTON_PIN` | 27 | GPIO pin number for the toggle button |
| `API_KEY_FILE` | `/home/pi/ll2_api_key.txt` | Path to API key file |
| `PI_USER` | `"pi"` | Your Pi username — update this before running |
| `GITHUB_RAW_URL` | *(set automatically)* | URL to raw script on GitHub for auto-updates |
| `UPDATE_INTERVAL` | 86400 | Seconds between update checks (default: 24 hours) |

You can also override the refresh interval at runtime:

```bash
python3 rocket_launch_tracker.py --refresh 120
```

---

## Auto-Update

The script checks GitHub once every 24 hours for a newer version. If a new version is found it downloads it, replaces the local script, and restarts the systemd service automatically — no manual intervention needed.

### Setup

**1. Set your Pi username in the script**

Open `rocket_launch_tracker.py` and set the `PI_USER` variable to match your Pi's username:

```python
PI_USER = "pi"   # change this to your username
```

The `GITHUB_RAW_URL` is already set to the correct repository and does not need to be changed.

**2. Allow the Pi to restart its own service without a password**

The restart command requires sudo. Add a passwordless sudoers rule so the script can restart itself:

```bash
sudo visudo
```

Add this line at the bottom (replace `pi` with your username):

```
YOUR_USERNAME ALL=(ALL) NOPASSWD: /bin/systemctl restart rockettracker
```
> Replace `YOUR_USERNAME` with your Pi's username.

Save and exit.

**3. Publishing an update**

When you want to push a new version to all Pis:
1. Increment `SCRIPT_VERSION` in the script (e.g. `"1.1.2"` → `"1.1.3"`)
2. Upload the new script to GitHub
3. Within 24 hours the Pi will detect the new version, download it, and restart automatically

The displays will show the update progress:
```
20x4:
Update Found!
v1.1.2 -> v1.1.3
Downloading...
Restarting soon
```

### Notes
- The update check only runs if the Pi has internet access
- If the download fails, the script logs the error and continues running the current version
- The old script is replaced atomically (via a temp file) so a failed download never corrupts the running script

---

## Troubleshooting

**All displays show FAILED on startup**
- Run `i2cdetect -y 1` to confirm displays are visible on the I2C bus
- Check that RPLCD is installed: `python3 -c "from RPLCD.i2c import CharLCD; print('OK')"`
- Verify SDA and SCL wires are connected to the correct Pi pins

**Displays show "API Rate Limited"**
- You have exceeded the anonymous request limit
- The displays will show a live countdown and resume automatically
- Consider adding an API key to increase the limit

**Button press is not responding**
- Confirm the button is wired to Pin 13 (GPIO27) and Pin 9 (GND)
- Check lgpio is installed: `python3 -c "import lgpio; print('OK')"`
- If not installed run: `pip install lgpio --break-system-packages`
- Check the terminal for `[BUTTON] Filter toggled` messages when pressing

**Script shows past launches**
- This can happen if the system clock is wrong — verify with `date`
- Ensure the Pi has internet access so it can sync time via NTP

---

## License

MIT License — free to use, modify, and distribute.
