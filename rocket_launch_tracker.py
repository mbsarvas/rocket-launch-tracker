"""
Rocket Launch Tracker — Multi-Display Edition
Raspberry Pi Zero W | Python 3.13
Version 1.0
Date: April 30, 2026
Created by Matthew Sarvas

Display layout:
    3x 16x2 LCDs (0x24, 0x23, 0x22) — Launch Site / Country
    3x 20x4 LCDs (0x27, 0x26, 0x25) — Mission / Vehicle / Date / Time (PST)

Each display pair (one 16x2 + one 20x4) shows a different upcoming launch.
Launches are refreshed from Launch Library 2 every REFRESH_INTERVAL seconds.

Wiring (same for all 6 displays — shared I2C bus):
    VCC → Pi Pin 2  (5V)
    GND → Pi Pin 6  (GND)
    SDA → Pi Pin 3  (GPIO2)
    SCL → Pi Pin 5  (GPIO3)

Toggle button wiring:
    One leg → Pi Pin 11 (GPIO17)
    Other leg → Pi Pin 9 (GND)
    (Internal pull-up resistor is used — no external resistor needed)

Install dependencies:
    pip install requests RPLCD smbus2 RPi.GPIO

Run:
    python3 rocket_launch_tracker.py [--refresh 300] [--launches 3]
"""

import argparse
import time
import sys
import threading
from datetime import datetime, timezone, timedelta

import requests

try:
    from RPLCD.i2c import CharLCD
    LCD_AVAILABLE = True
except ImportError:
    LCD_AVAILABLE = False
    print("[WARNING] RPLCD not installed — terminal-only mode.")

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    print("[WARNING] RPi.GPIO not installed — button toggle disabled.")

# ── Configuration ─────────────────────────────────────────────────────────────

# 16x2 displays → one per launch slot
# Line 1: Launch site name   |  Line 2: Country
LCD_16x2_CONFIGS = [
    {"address": 0x24, "slot": 0},
    {"address": 0x23, "slot": 1},
    {"address": 0x22, "slot": 2},
]

# 20x4 displays → one per launch slot
# Line 1: Mission name  |  Line 2: Rocket  |  Line 3: Date (PST)  |  Line 4: Time (PST)
LCD_20x4_CONFIGS = [
    {"address": 0x27, "slot": 0},
    {"address": 0x26, "slot": 1},
    {"address": 0x25, "slot": 2},
]

TOTAL_SLOTS      = 3     # number of launch slots (one per display pair)
API_BASE         = "https://ll.thespacedevs.com/2.0.0"
REFRESH_INTERVAL_ANON = 300  # anonymous: 15 req/hour → 1 per 4 min (300s)
REFRESH_INTERVAL_AUTH = 60   # authenticated: 60 req/hour → 1 per 60s
BUTTON_PIN       = 27    # GPIO pin for the Vandenberg filter toggle button
API_KEY_FILE     = "/home/mbsarvas/ll2_api_key.txt"  # put your API key in this file

# ── API key ──────────────────────────────────────────────────────────────────

def load_api_key() -> str | None:
    """
    Load the Launch Library 2 API key from a plain text file.
    The file should contain just the key on a single line, e.g.:
        abc123yourkeyhere
    Returns the key string, or None if the file doesn't exist or is empty.
    """
    try:
        with open(API_KEY_FILE, "r") as f:
            key = f.read().strip()
            if key:
                return key
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[WARNING] Could not read API key file: {e}")
    return None


# ── Timezone helpers ──────────────────────────────────────────────────────────

def utc_to_pacific(dt_utc: datetime) -> tuple[datetime, str]:
    """
    Convert a UTC-aware datetime to Pacific time.
    Returns (local_datetime, label) where label is 'PST' or 'PDT'.
    Uses the standard US DST rule:
        Start: 2nd Sunday in March at 02:00 UTC
        End:   1st Sunday in November at 02:00 UTC
    """
    year = dt_utc.year

    # 2nd Sunday in March
    march_1 = datetime(year, 3, 8, 2, 0, tzinfo=timezone.utc)
    dst_start = march_1 + timedelta(days=(6 - march_1.weekday()) % 7)

    # 1st Sunday in November
    nov_1 = datetime(year, 11, 1, 2, 0, tzinfo=timezone.utc)
    dst_end = nov_1 + timedelta(days=(6 - nov_1.weekday()) % 7)

    if dst_start <= dt_utc < dst_end:
        return dt_utc + timedelta(hours=-7), "PDT"
    return dt_utc + timedelta(hours=-8), "PST"


# ── String helpers ────────────────────────────────────────────────────────────

def pad(text: str, width: int) -> str:
    """Truncate and left-pad a string to exactly `width` characters."""
    return str(text)[:width].ljust(width)


def center(text: str, width: int) -> str:
    """Center-justify a string within `width` characters."""
    return str(text)[:width].center(width)


# ── Site abbreviation map ─────────────────────────────────────────────────────
# Maps the Launch Library 2 location "name" to a 16-char-friendly label.
# Add more entries here if you see a full name appearing on the 16x2 screen.

SITE_ABBREVIATIONS = {
    # USA
    "Kennedy Space Center, FL, USA":                "Kennedy SC",
    "Cape Canaveral, FL, USA":                      "Cape Canaveral",
    "Cape Canaveral Space Force Station, FL, USA":  "Cape Canaveral",
    "Vandenberg Space Force Base, CA, USA":         "Vandenberg SFB",
    "Vandenberg AFB, CA, USA":                      "Vandenberg AFB",
    "Wallops Flight Facility, VA, USA":             "Wallops FF",
    "Mid-Atlantic Regional Spaceport, VA, USA":     "MARS, Wallops",
    "Kodiak Launch Complex, AK, USA":               "Kodiak, AK",
    "Pacific Spaceport Complex, AK, USA":           "Pacific SPC, AK",
    "Starbase, TX, USA":                            "Starbase TX",
    "SpaceX South Texas Launch Site, TX, USA":      "Starbase TX",
    # New Zealand
    "Rocket Lab Launch Complex 1, NZ":              "RL LC-1, NZ",
    "Mahia Peninsula, NZ":                          "Mahia, NZ",
    # Russia / Kazakhstan
    "Baikonur Cosmodrome, Kazakhstan":              "Baikonur",
    "Plesetsk Cosmodrome, Russia":                  "Plesetsk",
    "Vostochny Cosmodrome, Russia":                 "Vostochny",
    # China
    "Jiuquan Satellite Launch Center, China":       "Jiuquan, China",
    "Xichang Satellite Launch Center, China":       "Xichang, China",
    "Wenchang Space Launch Site, China":            "Wenchang, China",
    "Taiyuan Satellite Launch Center, China":       "Taiyuan, China",
    "Haiyang Oriental Spaceport, China":            "Haiyang, China",
    # Europe
    "Guiana Space Centre, French Guiana, France":   "Kourou, FG",
    "Kourou, French Guiana, France":                "Kourou, FG",
    # India
    "Satish Dhawan Space Centre, India":            "Sriharikota",
    # Japan
    "Tanegashima Space Center, Japan":              "Tanegashima",
    "Uchinoura Space Center, Japan":                "Uchinoura",
    # South Korea
    "Naro Space Center, South Korea":               "Naro SC, Korea",
    # Iran
    "Shahroud Missile Test Site, Iran":             "Shahroud, Iran",
    # Israel
    "Palmachim Airbase, Israel":                    "Palmachim, IL",
}

# Location name substrings used to identify Vandenberg launches.
# Any launch whose location name contains one of these strings will be included
# when the Vandenberg filter is active.
VANDENBERG_KEYS = [
    "Vandenberg",
]


# ── Country code map ──────────────────────────────────────────────────────────

COUNTRY_NAMES = {
    "USA": "United States",
    "RUS": "Russia",
    "CHN": "China",
    "FRA": "France",
    "IND": "India",
    "JPN": "Japan",
    "NZL": "New Zealand",
    "KAZ": "Kazakhstan",
    "IRN": "Iran",
    "KOR": "South Korea",
    "ISR": "Israel",
    "BRA": "Brazil",
    "GBR": "United Kingdom",
    "AUS": "Australia",
    "CAN": "Canada",
    "ITA": "Italy",
    "DEU": "Germany",
    "ARE": "United Arab Emirates",
    "ARG": "Argentina",
    "MEX": "Mexico",
    "UKR": "Ukraine",
    "SWE": "Sweden",
    "NOR": "Norway",
    "FIN": "Finland",
    "ESP": "Spain",
    "PRT": "Portugal",
    "POL": "Poland",
    "PAK": "Pakistan",
    "IDN": "Indonesia",
    "MYS": "Malaysia",
    "SGP": "Singapore",
    "ZAF": "South Africa",
    "EGY": "Egypt",
    "TUR": "Turkey",
}


# ── API ───────────────────────────────────────────────────────────────────────

def _do_fetch(page_limit: int, headers: dict) -> tuple[list | None, int | None]:
    """
    Make a single request to the API.
    Returns (raw_list, None) on success,
            ([], retry_after) on 429 rate limit,
            (None, None) on other errors.
    """
    import re
    try:
        resp = requests.get(
            f"{API_BASE}/launch/upcoming/",
            params={"limit": page_limit, "mode": "normal", "ordering": "net"},
            headers=headers,
            timeout=20,
        )
        if resp.status_code == 429:
            retry_after = None
            try:
                detail = resp.json().get("detail", "")
                match = re.search(r"(\d+)\s+second", detail)
                if match:
                    retry_after = int(match.group(1))
            except Exception:
                pass
            return [], retry_after
        resp.raise_for_status()
        return resp.json().get("results", []), None
    except requests.exceptions.ConnectionError:
        print("[ERROR] No internet connection.")
    except requests.exceptions.Timeout:
        print("[ERROR] Request timed out.")
    except requests.exceptions.HTTPError as e:
        print(f"[ERROR] HTTP {e.response.status_code}")
    except Exception as e:
        print(f"[ERROR] {e}")
    return None, None


def fetch_launches(count: int, vandenberg_only: bool = False) -> tuple[list[dict], int | None]:
    """
    Fetch the next `count` upcoming launches strictly in the future.
    If vandenberg_only is True, only launches from Vandenberg are returned.

    Tries authenticated access first (if an API key file exists), then
    falls back to anonymous access automatically if the key fails.

    Returns (launches, retry_after) where retry_after is seconds to wait
    if the API is rate-limited (429), or None if no throttle.
    """
    now_utc    = datetime.now(timezone.utc)
    page_limit = 50 if vandenberg_only else 20

    # Build list of (label, headers) to try in order
    attempts = []
    api_key  = load_api_key()
    if api_key:
        attempts.append(("authenticated", {"Authorization": f"Token {api_key}"}))
    attempts.append(("anonymous", {}))

    raw_list     = None
    retry_after  = None

    for label, headers in attempts:
        print(f"  Trying {label} API access...")
        raw_list, retry_after = _do_fetch(page_limit, headers)

        if retry_after is not None:
            # Rate limited — no point trying anonymous if authenticated was limited,
            # and vice versa; surface the error immediately
            print(f"[ERROR] Rate limited ({label}). Retry in {retry_after}s.")
            return [], retry_after

        if raw_list is None:
            # Network or HTTP error — try next method if available
            if label == "authenticated":
                print(f"  [WARNING] Authenticated request failed, falling back to anonymous.")
            continue

        # Success
        if label == "authenticated":
            print(f"  ✓ Using authenticated access (higher rate limits).")
        else:
            print(f"  ✓ Using anonymous access.")
        break

    if raw_list is None:
        return [], None

    # Filter to future launches (and optionally Vandenberg only)
    results = []
    for launch in raw_list:
        net_str = launch.get("net", "")
        if not net_str:
            continue
        try:
            net_utc = datetime.fromisoformat(net_str.replace("Z", "+00:00"))
            if net_utc <= now_utc:
                continue

            if vandenberg_only:
                loc_name = (launch.get("pad", {})
                                  .get("location", {})
                                  .get("name", ""))
                if not any(key.lower() in loc_name.lower() for key in VANDENBERG_KEYS):
                    continue

            results.append(launch)
            if len(results) >= count:
                break
        except Exception:
            continue

    return results, None


def parse_launch(raw: dict) -> dict:
    """Extract and format all display-ready fields from a raw API launch object."""

    # ── Mission & rocket name ─────────────────────────────────────────────────
    full_name = raw.get("name", "Unknown")
    parts     = full_name.split("|")
    mission   = parts[-1].strip() if len(parts) > 1 else full_name
    rocket    = parts[0].strip()  if len(parts) > 1 else "Unknown"

    # ── Launch site & country ─────────────────────────────────────────────────
    pad_obj      = raw.get("pad", {})
    location_obj = pad_obj.get("location", {})
    country_code = location_obj.get("country_code", "??")
    country      = COUNTRY_NAMES.get(country_code, country_code)

    # Use the location name (the base/range, not the individual complex)
    # and shorten it to fit 16 chars using a friendly abbreviation map.
    location_full = location_obj.get("name", "Unknown Site")
    site_name = SITE_ABBREVIATIONS.get(location_full, location_full)

    # ── Date & time (Pacific) ─────────────────────────────────────────────────
    net_str = raw.get("net", "")
    if net_str:
        try:
            net_utc      = datetime.fromisoformat(net_str.replace("Z", "+00:00"))
            net_local, tz_label = utc_to_pacific(net_utc)
            # e.g. "Mon Apr 28 2026"
            date_str = net_local.strftime("%a %b %d %Y")
            # e.g. "09:30 AM PDT"
            time_str = net_local.strftime(f"%I:%M %p {tz_label}")
        except Exception:
            date_str = "Date TBD"
            time_str = "Time TBD"
    else:
        date_str = "Date TBD"
        time_str = "Time TBD"

    return {
        "mission": mission,
        "rocket":  rocket,
        "site":    site_name,
        "country": country,
        "date":    date_str,
        "time":    time_str,
        "status":  raw.get("status", {}).get("name", "Unknown"),
    }


# ── LCD initialisation ────────────────────────────────────────────────────────

def init_lcd(address: int, cols: int, rows: int) -> "CharLCD | None":
    if not LCD_AVAILABLE:
        return None
    try:
        lcd = CharLCD(
            i2c_expander="PCF8574",
            address=address,
            port=1,
            cols=cols,
            rows=rows,
            dotsize=8,
            charmap="A02",
            auto_linebreaks=False,
            backlight_enabled=True,
        )
        lcd.clear()
        return lcd
    except Exception as e:
        print(f"  [WARNING] LCD @ {hex(address)} init failed: {e}")
        return None


def write_lines(lcd: "CharLCD | None", lines: list[str], cols: int) -> None:
    """Write a list of pre-padded strings (one per row) to an LCD."""
    if lcd is None:
        return
    try:
        for row, text in enumerate(lines):
            lcd.cursor_pos = (row, 0)
            lcd.write_string(pad(text, cols))
    except Exception as e:
        print(f"  [LCD ERROR] {e}")


# ── Per-display update ────────────────────────────────────────────────────────

def update_16x2(entry: dict, launch: dict | None) -> None:
    """
    16x2 LCD:
        Row 0 — Launch site name
        Row 1 — Country
    """
    cols = 16
    addr = entry["address"]

    if launch:
        lines = [pad(launch["site"], cols), pad(launch["country"], cols)]
    else:
        lines = [pad("No data", cols), pad("", cols)]

    print(f"  [16x2 @ {hex(addr)}]  {lines[0].strip()} / {lines[1].strip()}")
    write_lines(entry["lcd"], lines, cols)


def update_20x4(entry: dict, launch: dict | None) -> None:
    """
    20x4 LCD:
        Row 0 — Mission name
        Row 1 — Launch vehicle (rocket)
        Row 2 — Date in PST/PDT
        Row 3 — Time in PST/PDT
    """
    cols = 20
    addr = entry["address"]

    if launch:
        lines = [
            pad(launch["mission"], cols),
            pad(launch["rocket"],  cols),
            pad(launch["date"],    cols),
            pad(launch["time"],    cols),
        ]
    else:
        lines = [pad("No data", cols)] * 4

    print(f"  [20x4 @ {hex(addr)}]")
    for i, l in enumerate(lines):
        print(f"          Row {i}: {l.strip()}")

    write_lines(entry["lcd"], lines, cols)


# ── Startup / shutdown screens ────────────────────────────────────────────────

def show_startup(lcds_16: list, lcds_20: list) -> None:
    for e in lcds_16:
        write_lines(e["lcd"],
                    [pad("Rocket Tracker", 16), pad("Starting...", 16)], 16)
    for e in lcds_20:
        write_lines(e["lcd"], [
            center("Rocket Launch", 20),
            center("Tracker v1.0", 20),
            center("By Matthew Sarvas", 20),
            center("Fetching data...", 20),
        ], 20)
    time.sleep(2)


def clear_all(lcds_16: list, lcds_20: list) -> None:
    for entry in lcds_16 + lcds_20:
        lcd = entry.get("lcd")
        if lcd:
            try:
                lcd.clear()
                lcd.backlight_enabled = False
            except Exception:
                pass


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Rocket Launch Tracker — Multi-Display")
    parser.add_argument("--refresh",  type=int, default=None,
                        help="Override API refresh interval in seconds")
    parser.add_argument("--launches", type=int, default=TOTAL_SLOTS,
                        help=f"Number of launches to display (default: {TOTAL_SLOTS})")
    args = parser.parse_args()

    num_slots = max(args.launches, TOTAL_SLOTS)

    # Auto-select refresh rate based on whether an API key is present
    if args.refresh is not None:
        refresh_interval = args.refresh
        refresh_source   = "manual override"
    elif load_api_key():
        refresh_interval = REFRESH_INTERVAL_AUTH
        refresh_source   = "authenticated (60 req/hr)"
    else:
        refresh_interval = REFRESH_INTERVAL_ANON
        refresh_source   = "anonymous (15 req/hr)"

    print("=" * 52)
    print("  🚀  Rocket Launch Tracker — Multi-Display")
    print(f"  Slots: {TOTAL_SLOTS} | Refresh: {refresh_interval}s ({refresh_source})")
    print("=" * 52)

    # ── Init all LCDs ─────────────────────────────────────────────────────────
    lcds_16 = []
    for cfg in LCD_16x2_CONFIGS:
        lcd = init_lcd(cfg["address"], cols=16, rows=2)
        lcds_16.append({**cfg, "lcd": lcd})
        print(f"  16x2 @ {hex(cfg['address'])} (slot {cfg['slot']}) "
              f"→ {'OK' if lcd else 'FAILED (terminal only)'}")

    lcds_20 = []
    for cfg in LCD_20x4_CONFIGS:
        lcd = init_lcd(cfg["address"], cols=20, rows=4)
        lcds_20.append({**cfg, "lcd": lcd})
        print(f"  20x4 @ {hex(cfg['address'])} (slot {cfg['slot']}) "
              f"→ {'OK' if lcd else 'FAILED (terminal only)'}")

    show_startup(lcds_16, lcds_20)

    # ── Button setup ──────────────────────────────────────────────────────────
    vandenberg_only = False
    filter_lock     = threading.Lock()
    last_fetch      = 0
    launches        = []

    def on_button_press(channel):
        nonlocal vandenberg_only, last_fetch
        with filter_lock:
            vandenberg_only = not vandenberg_only
            mode = "Vandenberg only" if vandenberg_only else "All locations"
            print(f"\n[BUTTON] Filter toggled -> {mode}")
            for entry in lcds_16:
                write_lines(entry["lcd"],
                            [pad("Filter:", 16), pad(mode, 16)], 16)
            for entry in lcds_20:
                write_lines(entry["lcd"], [
                    pad("Filter changed:", 20),
                    pad(mode,             20),
                    pad("Fetching...",    20),
                    pad("",              20),
                ], 20)
            last_fetch = 0   # force immediate re-fetch with new filter

    if GPIO_AVAILABLE:
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(BUTTON_PIN, GPIO.FALLING,
                              callback=on_button_press, bouncetime=300)
        print(f"  Button on GPIO{BUTTON_PIN} ready — press to toggle Vandenberg filter.")
    else:
        print("  [WARNING] GPIO not available — button toggle disabled.")

    # ── Main loop ─────────────────────────────────────────────────────────────
    try:
        while True:
            now = time.time()

            with filter_lock:
                current_filter = vandenberg_only

            # Refresh data if interval elapsed, first run, or filter just changed
            if now - last_fetch >= refresh_interval or not launches:
                ts = datetime.now().strftime("%H:%M:%S")
                mode_str = "Vandenberg only" if current_filter else "all locations"
                print(f"\n[{ts}] Fetching {num_slots} launches ({mode_str})...")
                raw_list, retry_after = fetch_launches(num_slots, vandenberg_only=current_filter)

                if retry_after is not None:
                    print(f"  WARNING: Rate limited. Counting down {retry_after}s on displays.")
                    deadline = time.time() + retry_after
                    while True:
                        remaining = int(deadline - time.time())
                        if remaining <= 0:
                            break
                        mins     = remaining // 60
                        secs     = remaining % 60
                        wait_str = f"{mins}m {secs:02d}s" if mins else f"{remaining}s"
                        for entry in lcds_16:
                            write_lines(entry["lcd"], [
                                pad("API Rate Limited", 16),
                                pad(f"Retry in {wait_str}", 16),
                            ], 16)
                        for entry in lcds_20:
                            write_lines(entry["lcd"], [
                                pad("API Rate Limited",       20),
                                pad("Too many requests",      20),
                                pad(f"Retry in: {wait_str}", 20),
                                pad("",                       20),
                            ], 20)
                        print(f"  Rate limit countdown: {wait_str}    ", end="\r")
                        time.sleep(1)
                    print()   # newline after countdown
                    last_fetch = 0
                    continue

                launches   = [parse_launch(r) for r in raw_list]
                last_fetch = time.time()
                print(f"  OK {len(launches)} launches loaded.\n")

            # Write each slot to its paired displays
            mode_label = " [VAFB]" if current_filter else ""
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Updating displays{mode_label}:")

            for entry in lcds_16:
                slot   = entry["slot"]
                launch = launches[slot] if slot < len(launches) else None
                update_16x2(entry, launch)

            for entry in lcds_20:
                slot   = entry["slot"]
                launch = launches[slot] if slot < len(launches) else None
                update_20x4(entry, launch)

            elapsed   = time.time() - last_fetch
            sleep_for = max(0, refresh_interval - elapsed)
            print(f"\n  Next refresh in {int(sleep_for)}s  (Ctrl+C to quit)\n")
            # Sleep in 0.2s increments so a button press wakes the loop immediately
            sleep_end = time.time() + sleep_for
            while time.time() < sleep_end:
                with filter_lock:
                    filter_changed = (vandenberg_only != current_filter)
                if filter_changed:
                    last_fetch = 0   # trigger immediate re-fetch
                    break
                time.sleep(0.2)

    except KeyboardInterrupt:
        print("\n\n[INFO] Shutting down — clearing all displays...")
        if GPIO_AVAILABLE:
            GPIO.cleanup()
        clear_all(lcds_16, lcds_20)
        print("[INFO] Done. Goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
