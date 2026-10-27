
import csv
import os
from datetime import datetime

LOG_FILE = r"D:\RoadSense\detections.csv"

def log_detection(confidence, class_id, latitude=None, longitude=None):
    file_exists = os.path.exists(LOG_FILE)

    with open(LOG_FILE, "a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)

        if not file_exists:
            writer.writerow([
                "timestamp",
                "class_id",
                "confidence",
                "latitude",
                "longitude"
            ])

        writer.writerow([
            datetime.now().astimezone().isoformat(timespec="seconds"),
            class_id,
            round(float(confidence), 3),
            latitude,
            longitude
        ])

    print(
        f"Logged potential pothole: class={class_id}, "
        f"confidence={confidence:.2f}"
    )

if __name__ == "__main__":
    log_detection(0.87, 0, None, None)
    print("Test complete. Check detections.csv")
