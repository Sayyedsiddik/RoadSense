
import cv2

print("RoadSense Camera Test Starting...")

camera = cv2.VideoCapture(0)

if not camera.isOpened():
    print("Camera not found.")
    print("Check camera permissions or connect a webcam.")
else:
    print("Camera connected!")
    print("Press Q to close the camera window.")

    while True:
        success, frame = camera.read()

        if not success:
            print("Could not read camera frame.")
            break

        cv2.imshow("RoadSense - Live Camera", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    camera.release()
    cv2.destroyAllWindows()

print("Camera test finished.")
