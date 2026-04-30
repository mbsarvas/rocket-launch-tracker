# 🚀 Rocket Launch Tracker 1.0 (rocket-launch-tracker-1.0)

A Raspberry Pi Zero W project that displays upcoming rocket launches in real time across six I2C LCD displays, powered by the [Launch Library 2 API](https://thespacedevs.com/llapi).

**Created by Matthew Sarvas**

---

## Features

- Displays the next 3 upcoming rocket launches simultaneously
- Three **16x2 LCDs** show the launch site and country for each launch
- Three **20x4 LCDs** show the mission name, rocket, date, and time (Pacific Time) for each launch
- Automatically converts launch times to PST or PDT
- No API is reqired, however acquiring one will allow for a higher data fetch rate, instructions for this below
- Physical button to toggle between all launches and Vandenberg SFB launches only
    - Each time this button is pressed the display must fetch new data
    - Without an API the data will still work but is limited to a certain number times per hour
    - For this reason, I have only added one location (Vandenburg) to filter, I may add more in future verions
- Live countdown timer on displays when the API rate limit is reached
- Auto-refreshes every 60 seconds (with API key) or 5 minutes (anonymous)
- Automatically runs on boot via systemd
- Falls back to anonymous API access if the API key is missing or invalid

---

## Hardware

- Raspberry Pi Zero W
- 3x 16x2 I2C LCD displays (PCF8574 backpack)
- 3x 20x4 I2C LCD displays (PCF8574 backpack)
- 1x momentary push button
- Jumper wires

---

## 3D Printed Frame/Enclosure

- I am working on creating a 3D printable frame for the LCD Displays, but feel free to create your own!

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

### 2. Verify displays are detected

```bash
sudo apt install i2c-tools
i2cdetect -y 1
```

You should see addresses `0x22` through `0x27` appear in the grid.

### 3. Clone the repository

```bash
cd /home/pi
git clone https://github.com/mbsarvas/rocket-launch-tracker.git
cd rocket-launch-tracker
```

### 4. Install dependencies

```bash
pip install -r requirements.txt --break-system-packages
```

### 5. Test the script

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

Paste the following (update the username and path if needed):

```ini
[Unit]
Description=Rocket Launch Tracker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/rocket-launch-tracker
ExecStart=/usr/bin/python3 /home/pi/rocket-launch-tracker/rocket_launch_tracker.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 2. Enable and start the service

```bash
sudo systemctl daemon-reload
sudo systemctl enable rockettracker
sudo systemctl start rockettracker
```

### 3. Check it is running

```bash
sudo systemctl status rockettracker
```

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

By default the script uses anonymous access to the Launch Library 2 API, which allows 15 requests per hour (one refresh every 5 minutes).

To get a higher rate limit (60 requests/hour, one refresh per minute):

1. Support [TheSpaceDevs on Patreon](https://www.patreon.com/TheSpaceDevs) at any paid tier
2. Receive your API key
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

When toggled, all displays briefly show the new filter mode and then immediately fetch and display updated launch data.

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

You can also override the refresh interval at runtime:

```bash
python3 rocket_launch_tracker.py --refresh 120
```

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
- Check RPi.GPIO is installed: `python3 -c "import RPi.GPIO; print('OK')"`
- Check the terminal for `[BUTTON] Filter toggled` messages when pressing

**Script shows past launches**
- This can happen if the system clock is wrong — verify with `date`
- Ensure the Pi has internet access so it can sync time via NTP

---

## License

MIT License — free to use, modify, and distribute.
