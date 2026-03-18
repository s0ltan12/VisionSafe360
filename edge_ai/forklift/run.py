from ultralytics import YOLO

# تحميل موديل جاهز مدرّب مسبقًا
model = YOLO('yolov8n.pt')  # "n" يعني النسخة الصغيرة والخفيفة

# تجربة الموديل على صورة
results = model.predict('download.jpg', save=True)

# عرض النتايج
results[0].show()
