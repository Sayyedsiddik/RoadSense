
import json
import time
from pathlib import Path
from datetime import datetime, timezone

import serial
import pynmea2
from serial.tools import list_ports

BASE_DIR = Path(__file__).resolve().parent
GPS_FILE = BASE_DIR / "gps_location.json"

# Change this to the COM port shown in Windows Device Manager.
GPS_PORT = "COM4"
GPS_BAUD = 9600


def main():
    print("Available serial ports:")
    for port in list_ports.comports():
        print(f"  {port.device}: {port.description}")

    print(f"\nConnecting to {GPS_PORT} at {GPS_BAUD} baud...")

    with serial.Serial(GPS_PORT, GPS_BAUD, timeout=1) as gps:
        print("GPS connected. Waiting for a valid satellite fix...")

        while True:
            try:
                line = gps.readline().decode(
                    "ascii", errors="ignore"
                ).strip()

                if not line.startswith("$") or "*" not in line:
                    continue

                try:
                    msg = pynmea2.parse(line)
                except pynmea2.ParseError:
                    continue

                lat = getattr(msg, "latitude", None)
                lon = getattr(msg, "longitude", None)

                # Only accept valid coordinates from a fix-bearing
                # NMEA sentence. Other NMEA sentences have no location.
                if not lat or not lon:
                    continue

                # GGA reports fix quality: 0 means invalid.
                quality = getattr(msg, "gps_qual", None)
                if quality is not None and int(quality or 0) == 0:
                    continue

                data = {
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "received_at": time.time(),
                    "source": "NEO-M8N",
                    "utc_time": datetime.now(
                        timezone.utc
                    ).isoformat(),
                }

                GPS_FILE.write_text(
                    json.dumps(data, indent=2),
                    encoding="utf-8",
                )

                print(
                    f"GPS fix: {lat:.6f}, {lon:.6f}"
                )

            except KeyboardInterrupt:
                print("\nGPS reader stopped.")
                break


if __name__ == "__main__":
    main()
