
import cv2
import numpy as np
import onnxruntime as ort

MODEL = r"D:\RoadSense\best.onnx"
IMAGE = r"D:\RoadSense\pothole.jpg"
OUTPUT = r"D:\RoadSense\result.jpg"

print("Loading model...", flush=True)

options = ort.SessionOptions()
options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
options.enable_mem_pattern = False
options.intra_op_num_threads = 1
options.inter_op_num_threads = 1

session = ort.InferenceSession(
    MODEL,
    sess_options=options,
    providers=["CPUExecutionProvider"]
)

image = cv2.imread(IMAGE)
if image is None:
    raise FileNotFoundError(f"Cannot open image: {IMAGE}")

height, width = image.shape[:2]

resized = cv2.resize(image, (640, 640))
rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
tensor = rgb.astype(np.float32) / 255.0
tensor = np.transpose(tensor, (2, 0, 1))[None, ...]

input_name = session.get_inputs()[0].name
output = session.run(None, {input_name: tensor})[0]
print("Output shape:", output.shape, flush=True)

predictions = output[0].T
if predictions.shape[1] != 9:
    raise ValueError(f"Unexpected output shape: {predictions.shape}")

scores = predictions[:, 4:]
class_ids = scores.argmax(axis=1)
confidences = scores.max(axis=1)
threshold = 0.35

boxes, kept_scores, kept_classes = [], [], []

for pred, confidence, class_id in zip(
    predictions, confidences, class_ids
):
    if confidence < threshold:
        continue

    cx, cy, bw, bh = pred[:4]
    x = int((cx - bw / 2) * width / 640)
    y = int((cy - bh / 2) * height / 640)
    bw = int(bw * width / 640)
    bh = int(bh * height / 640)

    x = max(0, min(x, width - 1))
    y = max(0, min(y, height - 1))
    bw = max(1, min(bw, width - x))
    bh = max(1, min(bh, height - y))

    boxes.append([x, y, bw, bh])
    kept_scores.append(float(confidence))
    kept_classes.append(int(class_id))

indices = cv2.dnn.NMSBoxes(
    boxes, kept_scores, threshold, 0.45
)

count = 0
if len(indices) > 0:
    for idx in np.array(indices).flatten():
        x, y, bw, bh = boxes[idx]
        confidence = kept_scores[idx]
        class_id = kept_classes[idx]

        cv2.rectangle(
            image, (x, y), (x + bw, y + bh), (0, 0, 255), 2
        )
        cv2.putText(
            image, f"Class {class_id}: {confidence:.2f}",
            (x, max(20, y - 8)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2
        )
        count += 1

if not cv2.imwrite(OUTPUT, image):
    raise RuntimeError("Could not save result image.")

print(f"Potential detections: {count}", flush=True)
print(f"Saved result to: {OUTPUT}", flush=True)
