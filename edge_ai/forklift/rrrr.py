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
source = r"D:\Users\one\OneDrive\Desktop\forklift\forklift_test.mp4"  # أو 0 للكاميرا

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

    # ارسم النقاط اللي اخترتيها
    for p in points:
        cv2.circle(frame, tuple(p), 5, (0,255,0), -1)

    cv2.imshow("Select 4 Points", frame)

    key = cv2.waitKey(0) & 0xFF  # 0 = انتظار الضغط على أي زر
    if key == ord('q'):
        break

    if len(points) == 4:
        print("4 points selected!")
        break

cap.release()
cv2.destroyAllWindows()

# استخدم النقاط مباشرة
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
# alarmm
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

    # كشف الأشياء
    results = model(frame, verbose=False)[0]

    forklift_center = None
    persons = []

    for box in results.boxes:
        cls = int(box.cls[0])
        x1,y1,x2,y2 = box.xyxy[0]
        cx = int((x1+x2)/2)
        cy = int((y1+y2)/2)

        if cls == 0:   # forklift
            forklift_center = (cx,cy)
        elif cls == 1: # person
            persons.append((cx,cy))

    danger = False
    if forklift_center:
        fx, fy = pixel_to_meter(forklift_center)

        for p in persons:
            px, py = pixel_to_meter(p)
            dist = math.sqrt((fx-px)**2 + (fy-py)**2)

            # تحديد حالة السلامة
            if dist > 5:
                status = "SAFE"
                color = (0,255,0)
            elif 3 < dist <= 5:
                status = "WARNING"
                color = (0,255,255)
            elif 1 < dist <= 3:
                status = "DANGER"
                color = (0,0,255)
            else:
                status = "CRITICAL"
                color = (0,0,255)
                if not alarm_active:
                    play_alarm()
                    alarm_active = True
                danger = True

            # عرض الحالة على الفيديو
            cv2.putText(frame, f"{status} {dist:.2f}m", (50,50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, color, 3)
            # رسم دائرة على الشخص
            #cv2.circle(frame, p, 5, color, -1)

        # رسم دائرة على الرافعة الشوكية
        #cv2.circle(frame, forklift_center, 8, (255,0,0), -1)

    if not danger:
        alarm_active = False

    cv2.imshow("Safety Monitoring", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()