import cv2
import numpy as np
import onnxruntime as ort
import os
import csv
import time
import json
import threading
from datetime import datetime
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from esp32_control import send_command

# ---------------- CONFIGURATION ----------------
BASE_DIR = Path(__file__).resolve().parent
MODEL = BASE_DIR / "best.onnx"
LOG_FILE = BASE_DIR / "detections.csv"
GPS_FILE = BASE_DIR / "gps_location.json"

CONFIDENCE_THRESHOLD = 0.45
STOP_CONFIDENCE = 0.70
LOG_COOLDOWN_SECONDS = 5
COMMAND_COOLDOWN_SECONDS = 2

GPS_HOST = "127.0.0.1"
GPS_PORT = 8765
GPS_MAX_AGE_SECONDS = 30
# ------------------------------------------------


def ensure_detection_csv():
    """Create the log only if it does not already exist; never overwrite it."""
    if not LOG_FILE.exists():
        with open(LOG_FILE, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([
                "timestamp", "class_id", "confidence", "latitude", "longitude"
            ])


def read_current_gps():
    """Return recent browser GPS coordinates, or blanks if unavailable/stale."""
    try:
        with open(GPS_FILE, "r", encoding="utf-8") as file:
            location = json.load(file)
        age = time.time() - float(location.get("received_at", 0))
        lat = float(location["latitude"])
        lon = float(location["longitude"])
        if age > GPS_MAX_AGE_SECONDS:
            return "", ""
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return "", ""
        return round(lat, 7), round(lon, 7)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return "", ""


def log_detection(class_id, confidence):
    latitude, longitude = read_current_gps()
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([
            datetime.now().astimezone().isoformat(timespec="seconds"),
            class_id,
            round(float(confidence), 3),
            latitude,
            longitude,
        ])

    gps_label = (
        f"GPS: {latitude}, {longitude}"
        if latitude != "" and longitude != ""
        else "GPS unavailable"
    )
    print(
        f"Logged potential pothole | Class: {class_id} | "
        f"Confidence: {confidence:.2f} | {gps_label}"
    )


GPS_PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RoadSense GPS</title>
<style>
body{font-family:Arial,sans-serif;background:#0b1220;color:#e5e7eb;
max-width:700px;margin:40px auto;padding:24px}
.card{background:#111827;border:1px solid #263244;border-radius:16px;padding:24px}
button{background:#14b8a6;color:#062a2a;border:0;border-radius:10px;
padding:12px 18px;font-weight:bold;cursor:pointer}
small{color:#9ca3af} #status{margin-top:18px;line-height:1.6;white-space:pre-wrap}
</style>
</head>
<body>
<div class="card">
<h1>📍 RoadSense GPS</h1>
<p>Keep this tab open while the RoadSense camera detector is running.</p>
<p>Your browser will request location permission. Coordinates are sent only to
the RoadSense service running on this same laptop.</p>
<button id="start">Enable GPS</button>
<div id="status">GPS is not active yet.</div>
<p><small>Location is refreshed periodically. Indoor accuracy can be poor.
A laptop's location is not the exact position of a pothole seen at a distance.</small></p>
</div>
<script>
const statusBox = document.getElementById('status');
let watchId = null;
async function sendPosition(position) {
  const payload = {
    latitude: position.coords.latitude,
    longitude: position.coords.longitude,
    accuracy_m: position.coords.accuracy,
    received_at: Date.now() / 1000
  };
  try {
    const response = await fetch('/location', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    if (!response.ok) throw new Error('Local GPS service returned ' + response.status);
    statusBox.textContent =
      'GPS active ✓\\nLatitude: ' + payload.latitude.toFixed(6) +
      '\\nLongitude: ' + payload.longitude.toFixed(6) +
      '\\nReported accuracy: ±' + Math.round(payload.accuracy_m) + ' m' +
      '\\nLast update: ' + new Date().toLocaleTimeString();
  } catch (err) {
    statusBox.textContent = 'Could not send GPS to RoadSense: ' + err.message;
  }
}
function gpsError(error) {
  const messages = {
    1: 'Location permission denied. Allow location access in the browser site settings.',
    2: 'Position unavailable. Try moving near a window or checking Windows location settings.',
    3: 'Location request timed out. Press Enable GPS and try again.'
  };
  statusBox.textContent = messages[error.code] || error.message;
}
document.getElementById('start').addEventListener('click', () => {
  if (!navigator.geolocation) {
    statusBox.textContent = 'This browser does not support geolocation.';
    return;
  }
  if (watchId !== null) navigator.geolocation.clearWatch(watchId);
  statusBox.textContent = 'Requesting location permission…';
  watchId = navigator.geolocation.watchPosition(sendPosition, gpsError, {
    enableHighAccuracy: true, maximumAge: 5000, timeout: 20000
  });
});
</script>
</body>
</html>"""


class GPSHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if urlparse(self.path).path != "/":
            self.send_error(404)
            return
        body = GPS_PAGE.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if urlparse(self.path).path != "/location":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            lat = float(payload["latitude"])
            lon = float(payload["longitude"])
            accuracy = float(payload.get("accuracy_m", 0))
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError("Coordinates out of range")
            saved = {
                "latitude": lat,
                "longitude": lon,
                "accuracy_m": accuracy,
                "received_at": time.time(),
            }
            with open(GPS_FILE, "w", encoding="utf-8") as file:
                json.dump(saved, file)
            response = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
            print(
                f"GPS updated: {lat:.6f}, {lon:.6f} "
                f"(browser-reported accuracy +/-{accuracy:.0f} m)"
            )
        except Exception as exc:
            response = json.dumps({"ok": False, "error": str(exc)}).encode("utf-8")
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

    def log_message(self, format, *args):
        # Keep the detector terminal readable.
        return


def start_gps_server():
    try:
        server = ThreadingHTTPServer((GPS_HOST, GPS_PORT), GPSHandler)
    except OSError as exc:
        print(
            f"GPS web service could not start on http://localhost:{GPS_PORT}: {exc}\n"
            "Detection will continue, but GPS will not be available."
        )
        return None
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"GPS page: http://localhost:{GPS_PORT}")
    print("Open that address in your browser and click Enable GPS.")
    return server


def safe_send_command(command):
    """Keep AI detection running if the optional ESP32 connection fails."""
    try:
        send_command(command)
    except Exception as exc:
        print(f"ESP32 command failed ({command}); detection continues: {exc}")


def main():
    ensure_detection_csv()
    gps_server = start_gps_server()

    if not MODEL.exists():
        if gps_server:
            gps_server.shutdown()
        raise FileNotFoundError(
            f"Model not found: {MODEL}\nMake sure best.onnx is in {BASE_DIR}."
        )

    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
    options.enable_mem_pattern = False
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1

    print("Loading RoadSense AI...")
    session = ort.InferenceSession(
        str(MODEL),
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )
    input_name = session.get_inputs()[0].name
    print("AI ready!")

    camera = cv2.VideoCapture(0)
    if not camera.isOpened():
        if gps_server:
            gps_server.shutdown()
        raise RuntimeError("Webcam could not be opened.")

    last_logged = {}
    last_command = None
    last_command_time = 0
    current_command = "STOP"

    print("RoadSense running. Press Q to quit.")
    print("GPS values are blank until browser GPS is enabled and fresh.")
    print("Existing detections.csv and report_status.csv are preserved.")

    try:
        while True:
            ok, frame = camera.read()
            if not ok:
                print("Could not read webcam frame.")
                break

            h, w = frame.shape[:2]
            resized = cv2.resize(frame, (640, 640))
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            tensor = rgb.astype(np.float32) / 255.0
            tensor = np.transpose(tensor, (2, 0, 1))[None, ...]

            output = session.run(None, {input_name: tensor})[0]
            predictions = output[0].T
            scores = predictions[:, 4:]
            class_ids = scores.argmax(axis=1)
            confidences = scores.max(axis=1)

            boxes, kept_scores, kept_classes = [], [], []
            for pred, confidence, class_id in zip(predictions, confidences, class_ids):
                if confidence < CONFIDENCE_THRESHOLD:
                    continue
                cx, cy, bw, bh = pred[:4]
                x = int((cx - bw / 2) * w / 640)
                y = int((cy - bh / 2) * h / 640)
                bw = int(bw * w / 640)
                bh = int(bh * h / 640)
                x = max(0, min(x, w - 1))
                y = max(0, min(y, h - 1))
                bw = max(1, min(bw, w - x))
                bh = max(1, min(bh, h - y))
                boxes.append([x, y, bw, bh])
                kept_scores.append(float(confidence))
                kept_classes.append(int(class_id))

            if boxes:
                raw_indices = cv2.dnn.NMSBoxes(
                    boxes, kept_scores, CONFIDENCE_THRESHOLD, 0.45
                )
                indices = (
                    np.array(raw_indices).flatten()
                    if len(raw_indices) > 0 else np.array([], dtype=int)
                )
            else:
                indices = np.array([], dtype=int)

            if len(indices) > 0:
                best_confidence = max(kept_scores[i] for i in indices)
                proposed_command = (
                    "STOP" if best_confidence >= STOP_CONFIDENCE else "SLOW"
                )
            else:
                proposed_command = "NORMAL"

            now = time.monotonic()
            if (
                proposed_command != last_command
                or now - last_command_time >= COMMAND_COOLDOWN_SECONDS
            ):
                safe_send_command(proposed_command)
                last_command = proposed_command
                last_command_time = now
            current_command = proposed_command

            for idx in indices:
                x, y, bw, bh = boxes[idx]
                confidence = kept_scores[idx]
                class_id = kept_classes[idx]
                cv2.rectangle(frame, (x, y), (x + bw, y + bh), (0, 0, 255), 2)
                cv2.putText(
                    frame, f"Class {class_id}: {confidence:.2f}",
                    (x, max(25, y - 8)), cv2.FONT_HERSHEY_SIMPLEX,
                    0.65, (0, 0, 255), 2,
                )
                if now - last_logged.get(class_id, 0) >= LOG_COOLDOWN_SECONDS:
                    log_detection(class_id, confidence)
                    last_logged[class_id] = now

            gps_lat, gps_lon = read_current_gps()
            gps_status = "GPS ACTIVE" if gps_lat != "" else "GPS NOT READY"
            cv2.putText(
                frame, f"RoadSense AI | Command: {current_command}",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2,
            )
            cv2.putText(
                frame, f"{gps_status} | Press Q to quit",
                (10, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (0, 255, 255) if gps_lat == "" else (0, 255, 0), 2,
            )
            cv2.imshow("RoadSense - Live Detection", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    finally:
        camera.release()
        cv2.destroyAllWindows()
        if gps_server:
            gps_server.shutdown()
            gps_server.server_close()
        print("RoadSense stopped.")


if __name__ == "__main__":
    main()
