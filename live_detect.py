
import cv2
import numpy as np
import onnxruntime as ort
import threading
import time
import os

# ============== SETTINGS ==============
MODEL_PATH = r"D:\RoadSense\best.onnx"
CAMERA_INDEX = 0
INPUT_SIZE = 640
CONFIDENCE_THRESHOLD = 0.35
IOU_THRESHOLD = 0.45
INFERENCE_INTERVAL = 0.15

# ============== LOAD MODEL ==============
print("Loading RoadSense model...", flush=True)

if not os.path.exists(MODEL_PATH):
    raise FileNotFoundError(f"Model not found: {MODEL_PATH}")

options = ort.SessionOptions()
options.graph_optimization_level = (
    ort.GraphOptimizationLevel.ORT_DISABLE_ALL
)
options.enable_mem_pattern = False
options.intra_op_num_threads = 1
options.inter_op_num_threads = 1

session = ort.InferenceSession(
    MODEL_PATH,
    sess_options=options,
    providers=["CPUExecutionProvider"]
)

input_name = session.get_inputs()[0].name
print("Model loaded:", session.get_outputs()[0].shape, flush=True)

# ============== OPEN LAPTOP CAMERA ==============
camera = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)

if not camera.isOpened():
    camera.release()
    camera = cv2.VideoCapture(CAMERA_INDEX)

if not camera.isOpened():
    raise RuntimeError(
        "Laptop webcam not found. Close other camera apps and try again."
    )

camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)

# ============== SHARED DATA ==============
lock = threading.Lock()
latest_frame = None
latest_detections = []
running = True
last_inference = 0.0
inference_fps = 0.0

# ============== DETECTION WORKER ==============
def detection_worker():
    global latest_frame, latest_detections
    global running, last_inference, inference_fps

    while running:
        with lock:
            frame = (
                latest_frame.copy()
                if latest_frame is not None else None
            )

        if frame is None:
            time.sleep(0.01)
            continue

        now = time.time()
        if now - last_inference < INFERENCE_INTERVAL:
            time.sleep(0.005)
            continue

        last_inference = now
        start = time.time()

        try:
            height, width = frame.shape[:2]

            resized = cv2.resize(
                frame, (INPUT_SIZE, INPUT_SIZE)
            )
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            tensor = rgb.astype(np.float32) / 255.0
            tensor = np.transpose(tensor, (2, 0, 1))[None, ...]

            output = session.run(
                None, {input_name: tensor}
            )[0]

            # Match detect_image.py's output decoding.
            predictions = output[0].T

            if predictions.ndim != 2 or predictions.shape[1] != 9:
                print(
                    "Unexpected output shape:",
                    output.shape,
                    flush=True
                )
                continue

            scores = predictions[:, 4:]
            class_ids = scores.argmax(axis=1)
            confidences = scores.max(axis=1)

            boxes = []
            kept_scores = []
            kept_classes = []

            for pred, confidence, class_id in zip(
                predictions, confidences, class_ids
            ):
                confidence = float(confidence)

                if confidence < CONFIDENCE_THRESHOLD:
                    continue

                cx, cy, bw, bh = pred[:4]

                x = int(
                    (cx - bw / 2) * width / INPUT_SIZE
                )
                y = int(
                    (cy - bh / 2) * height / INPUT_SIZE
                )
                bw = int(bw * width / INPUT_SIZE)
                bh = int(bh * height / INPUT_SIZE)

                x = max(0, min(x, width - 1))
                y = max(0, min(y, height - 1))
                bw = max(1, min(bw, width - x))
                bh = max(1, min(bh, height - y))

                boxes.append([x, y, bw, bh])
                kept_scores.append(confidence)
                kept_classes.append(int(class_id))

            indices = cv2.dnn.NMSBoxes(
                boxes,
                kept_scores,
                CONFIDENCE_THRESHOLD,
                IOU_THRESHOLD
            )

            detections = []

            if len(indices) > 0:
                for idx in np.array(indices).flatten():
                    x, y, bw, bh = boxes[int(idx)]

                    detections.append((
                        x, y, x + bw, y + bh,
                        kept_scores[int(idx)],
                        kept_classes[int(idx)]
                    ))

            with lock:
                latest_detections = detections

            duration = time.time() - start
            inference_fps = 1.0 / max(duration, 0.001)

        except Exception as error:
            print("Detection error:", error, flush=True)
            time.sleep(0.1)

# ============== START AI THREAD ==============
worker = threading.Thread(
    target=detection_worker,
    daemon=True
)
worker.start()

print("RoadSense live detection started. Press Q to quit.", flush=True)

# ============== LIVE CAMERA LOOP ==============
camera_fps = 0.0
frame_count = 0
fps_start = time.time()

try:
    while True:
        success, frame = camera.read()

        if not success:
            print("Could not read camera frame.", flush=True)
            time.sleep(0.05)
            continue

        with lock:
            latest_frame = frame.copy()
            detections = list(latest_detections)

        for x1, y1, x2, y2, confidence, class_id in detections:
            cv2.rectangle(
                frame, (x1, y1), (x2, y2),
                (0, 0, 255), 2
            )

            cv2.putText(
                frame,
                f"Class {class_id}: {confidence:.2f}",
                (x1, max(20, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6, (0, 0, 255), 2
            )

        frame_count += 1
        elapsed = time.time() - fps_start

        if elapsed >= 1.0:
            camera_fps = frame_count / elapsed
            frame_count = 0
            fps_start = time.time()

        cv2.putText(
            frame,
            f"Camera FPS: {camera_fps:.1f}",
            (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65, (0, 255, 0), 2
        )

        cv2.putText(
            frame,
            f"Detections: {len(detections)}",
            (10, 52),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65, (0, 255, 0), 2
        )

        cv2.imshow("RoadSense - Live Pothole Detection", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

finally:
    running = False
    worker.join(timeout=2)
    camera.release()
    cv2.destroyAllWindows()
    print("RoadSense stopped.", flush=True)
