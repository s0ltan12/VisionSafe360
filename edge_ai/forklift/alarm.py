from ultralytics import YOLO
import cv2
import winsound
import threading

# load your trained model
model = YOLO(r"D:\Users\one\OneDrive\Desktop\runs\detect\train2\weights\best.pt")

# اختاري المصدر: فيديو أو كاميرا
#source = 0  # الكاميرا الافتراضية
source = r"D:\Users\one\OneDrive\Desktop\forklift\forklift_test.mp4"  # لو عايزة فيديو
#source = r"watermarked-ef5d1ccd-4404-453a-bdf0-b46c79c7cc6f.mp4"
cap = cv2.VideoCapture(source)

SAFETY_MARGIN = 80   # مساحة الأمان حوالين الرافعة (px)
alarm_path = (r"D:\Users\one\OneDrive\Desktop\forklift\preview (online-audio-converter.com).wav")  # ضع ملف الصوت هنا في نفس فولدر الكود

# flag لتتبع حالة الإنذار
alarm_active = False

# دالة لتشغيل الإنذار بدون توقف الفيديو
def play_alarm():
    threading.Thread(target=lambda: winsound.PlaySound(alarm_path, winsound.SND_FILENAME), daemon=True).start()

while True:
    ret, frame = cap.read()
    if not ret:
        print("Failed to grab frame")
        break

    results = model(frame, conf=0.5)
    boxes = results[0].boxes

    forklift_box = None
    person_boxes = []

    # --- تحديد الرافعة والأشخاص ---
    for box in boxes:
        cls = int(box.cls[0])
        x1, y1, x2, y2 = box.xyxy[0]

        if cls == 1:  # person
            person_boxes.append((x1, y1, x2, y2))
        elif cls == 0:  # forklift
            forklift_box = (x1, y1, x2, y2)

    danger = False

    if forklift_box is not None:
        fx1, fy1, fx2, fy2 = forklift_box

        # المنطقة الخضراء حول الرافعة
        safe_x1 = int(fx1 - SAFETY_MARGIN)
        safe_y1 = int(fy1 - SAFETY_MARGIN)
        safe_x2 = int(fx2 + SAFETY_MARGIN)
        safe_y2 = int(fy2 + SAFETY_MARGIN)

        zone_color = (0, 255, 0)  # أخضر افتراضي

        # التحقق إذا شخص دخل المنطقة
        for (px1, py1, px2, py2) in person_boxes:
            person_center_x = int((px1 + px2) / 2)
            person_center_y = int((py1 + py2) / 2)

            if safe_x1 < person_center_x < safe_x2 and safe_y1 < person_center_y < safe_y2:
                danger = True
                break

        # إذا في خطر، نغير اللون ونشغل الإنذار مرة واحدة
        if danger:
            zone_color = (0, 0, 255)  # أحمر
            cv2.putText(frame, "DANGER! HUMAN TOO CLOSE", (50, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
            if not alarm_active:
                play_alarm()
                alarm_active = True
        else:
            alarm_active = False  # إعادة السماح بتشغيل الإنذار لو الشخص خرج من المنطقة

        # رسم مربع الأمان
        cv2.rectangle(frame, (safe_x1, safe_y1), (safe_x2, safe_y2), zone_color, 3)

    # دمج الرسم مع YOLO annotations
    annotated_frame = results[0].plot()
    final_output = cv2.addWeighted(annotated_frame, 0.7, frame, 0.3, 0)
    cv2.imshow("Safety Monitoring", final_output)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
