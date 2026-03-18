import cv2
import logging
from ultralytics import YOLO
import numpy as np
import math
import winsound
import threading

# ------------------------------
# إعدادات المشروع
# ------------------------------
REAL_WIDTH  = 5.0   # عرض المنطقة بالمتر
REAL_HEIGHT = 10.0  # طول المنطقة بالمتر
model_path = r"D:\Users\one\OneDrive\Desktop\runs\detect\train2\weights\best.pt"
alarm_path = r"D:\Users\one\OneDrive\Desktop\forklift\preview (online-audio-converter.com).wav"
source = r"forklift_test.mp4"
logging.getLogger("ultralytics").setLevel(logging.ERROR)

# ------------------------------
# اختيار أربع نقاط على الفيديو
# ------------------------------
points = []

def click(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        points.append([x, y])
        print(f"Point {len(points)}: {x}, {y}")

cap = cv2.VideoCapture(source)
if not cap.isOpened():
    print("Failed to open video")
    exit()

cv2.namedWindow("Select 4 Points")
cv2.setMouseCallback("Select 4 Points", click)

while True:
    ret, frame = cap.read()
    if not ret:
        print("End of video or cannot read frame")
        break

    for p in points:
        cv2.circle(frame, tuple(p), 5, (0,255,0), -1)

    cv2.imshow("Select 4 Points", frame)
    key = cv2.waitKey(0) & 0xFF
    if key == ord('q'):
        break
    if len(points) == 4:
        print("4 points selected!")
        break

cap.release()
cv2.destroyAllWindows()

image_pts = np.array(points, dtype=np.float32)
print("Image Points =", image_pts)

# ------------------------------
# تحميل الموديل
# ------------------------------
model = YOLO(model_path)

# ------------------------------
# Homography Matrix
# ------------------------------
real_pts = np.array([
    [0,0],
    [REAL_WIDTH,0],
    [REAL_WIDTH,REAL_HEIGHT],
    [0,REAL_HEIGHT]
], dtype=np.float32)

H, _ = cv2.findHomography(image_pts, real_pts)

# ------------------------------
# دالة تحويل Pixel -> Meter
# ------------------------------
def pixel_to_meter(point):
    px = np.array([point[0], point[1], 1])
    world = H @ px
    world /= world[2]
    return world[0], world[1]

# ------------------------------
# دالة لتشغيل الإنذار
# ------------------------------
alarm_active = False
def play_alarm():
    threading.Thread(target=lambda: winsound.PlaySound(alarm_path, winsound.SND_FILENAME), daemon=True).start()

# ------------------------------
# بدء الفيديو / الكاميرا
# ------------------------------
cap = cv2.VideoCapture(source)

while True:
    ret, frame = cap.read()
    if not ret:
        break

    results = model(frame, verbose=False)[0]

    forklift_center = None
    persons = []

    for box in results.boxes:
        cls = int(box.cls[0])
        x1,y1,x2,y2 = box.xyxy[0]
        x1,y1,x2,y2 = int(x1),int(y1),int(x2),int(y2)
        cx = int((x1+x2)/2)
        cy = int((y1+y2)/2)

        if cls == 0:  # رافعة
            label = "Forklift"
            color = (255,0,0)
            forklift_center = (cx,cy)
        elif cls == 1:  # شخص
            label = "Person"
            color = (0,255,0)
            persons.append((cx,cy))
        else:
            continue

        cv2.rectangle(frame, (x1,y1), (x2,y2), color, 2)
        cv2.putText(frame, label, (x1,y1-10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        cv2.circle(frame, (cx,cy), 4, color, -1)

    # ------------------------------
    # حساب المسافات وعرض الحالة لكل شخص
    # ------------------------------
    danger = False
    if forklift_center:
        fx, fy = pixel_to_meter(forklift_center)
        for p_idx, p in enumerate(persons):
            px, py = pixel_to_meter(p)
            dist = math.sqrt((fx-px)**2 + (fy-py)**2)

            # تحديد حالة السلامة لكل شخص
            if dist > 5:
                status = "SAFE"
                color = (0,255,0)
            elif 3 < dist <= 5:
                status = "WARNING"
                color = (0,255,255)
            else:  # dist <= 3
                status = "DANGER"
                color = (0,0,255)
                if not alarm_active:
                    play_alarm()
                    alarm_active = True
                danger = True

            # عرض الحالة والمسافة فوق الـ bounding box الخاصة بالشخص
            x, y = results.boxes.xyxy[p_idx][:2]
            x, y = int(x), int(y)
            cv2.putText(frame, f"{status} {dist:.2f}m", (x, y-10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

    if not danger:
        alarm_active = False

    cv2.imshow("Safety Monitoring", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()