import csv
import os
import time
from datetime import datetime

LOG_FILE = r"D:\RoadSense\detections.csv"

print("=" * 45)
print("       ROADSENSE - DEMO MODE")
print("=" * 45)
print("This demo does not control any physical vehicle.")
print("Commands are simulated until the ESP32 is connected.")
print("Press Ctrl+C to stop.\n")

last_count = -1

try:
    while True:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", newline="", encoding="utf-8") as file:
                rows = list(csv.DictReader(file))

            if len(rows) != last_count:
                last_count = len(rows)
                print(f"\nTotal logged detections: {last_count}")

                if rows:
                    latest = rows[-1]
                    confidence = float(latest.get("confidence") or 0)

                    if confidence >= 0.70:
                        command = "STOP"
                    else:
                        command = "SLOW"

                    print("Latest detection time:", latest.get("timestamp"))
                    print("Class ID:", latest.get("class_id"))
                    print(f"Confidence: {confidence:.2f}")
                    print("Simulated car command:", command)
                    print("GPS: Not available yet")

        time.sleep(2)

except KeyboardInterrupt:
    print("\nRoadSense demo stopped.")
