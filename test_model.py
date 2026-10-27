
import os
import onnxruntime as ort

model_path = r"D:\RoadSense\best.onnx"

print("Loading RoadSense pothole model...")

if not os.path.exists(model_path):
    print("ERROR: Model file not found.")
else:
    try:
        session = ort.InferenceSession(
            model_path,
            providers=["CPUExecutionProvider"]
        )

        print("Model loaded successfully!")

        for inp in session.get_inputs():
            print("Input:", inp.name, inp.shape, inp.type)

        for out in session.get_outputs():
            print("Output:", out.name, out.shape, out.type)

    except Exception as e:
        print("Model loading failed:")
        print(e)

