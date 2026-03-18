import cv2
import numpy as np
from ultralytics import YOLO
from collections import defaultdict
import time
import os
from datetime import datetime
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import threading

class AdvancedFallDetection:
    def __init__(self):
        self.model = YOLO('yolov8n-pose.pt')
        self.tracker_states = defaultdict(lambda: {
            'state': 'UPRIGHT', 'fall_start': None, 'photo_taken': False,
            'fall_duration': 0, 'fall_time': None, 'is_falling': False,
            'confirmed_fall': False
        })
        self.fall_count = 0
        self.snapshots_dir = "fall_snapshots"
        os.makedirs(self.snapshots_dir, exist_ok=True)
        
        self.cap = None
        self.running = False
        self.paused = False
        self.frame_count = 0
        self.fps_count = 0
        self.last_fps_time = time.time()
        
        # ✅ حجم فيديو ثابت
        self.VIDEO_WIDTH = 1280
        self.VIDEO_HEIGHT = 720
        
        self.root = tk.Tk()
        self.root.title("🏭 نظام كشف السقوط المتقدم v9.0")
        self.root.geometry("1800x1000")
        self.root.configure(bg='#0a0a0a')
        self.setup_perfect_ui()
    
    def setup_perfect_ui(self):
        # Header
        header = tk.Frame(self.root, bg='#1a1a2e', height=80)
        header.pack(fill='x', padx=10, pady=5)
        header.pack_propagate(False)
        
        tk.Label(header, text="🏭 FACTORY FALL DETECTION v9.0 ✅", 
                font=('Arial', 26, 'bold'), fg='#00ff88', bg='#1a1a2e').pack(side='left', pady=20)
        
        ctrl = tk.Frame(header, bg='#1a1a2e')
        ctrl.pack(side='right', pady=20)
        
        tk.Label(ctrl, text="📹 Source: ", font=('Arial', 14), fg='white', bg='#1a1a2e').pack(side='left')
        self.source_var = tk.StringVar(value="0")
        ttk.Combobox(ctrl, textvariable=self.source_var, width=12,
                    values=["0 (كاميرا)", "1", "2", "vid3.mp4"], state="readonly").pack(side='left', padx=(0,10))
        
        self.start_btn = tk.Button(ctrl, text="▶️ START", command=self.start_detection,
                                  bg='#00ff88', fg='black', font=('Arial', 14, 'bold'), width=12)
        self.start_btn.pack(side='left', padx=5)
        
        self.stop_btn = tk.Button(ctrl, text="⏹️ STOP", command=self.stop_detection,
                                 bg='#ff4444', fg='white', font=('Arial', 14, 'bold'), width=12, state='disabled')
        self.stop_btn.pack(side='left', padx=5)
        
        self.pause_btn = tk.Button(ctrl, text="⏸️ PAUSE", command=self.toggle_pause,
                                  bg='#ffaa00', fg='black', font=('Arial', 14, 'bold'), width=12, state='disabled')
        self.pause_btn.pack(side='left', padx=5)
        
        # ✅ Status مع الوقت جنب الـFalls
        status_frame = tk.Frame(self.root, bg='#16213e', height=80)
        status_frame.pack(fill='x', padx=10, pady=5)
        status_frame.pack_propagate(False)
        
        self.fps_label = tk.Label(status_frame, text="FPS: 0", font=('Arial', 22, 'bold'), 
                                 fg='#00ff88', bg='#16213e')
        self.fps_label.pack(side='left', padx=40, pady=25)
        
        # ✅ Fall count + Time مع بعض
        info_frame = tk.Frame(status_frame, bg='#16213e')
        info_frame.pack(side='left', padx=60, pady=25)
        
        self.fall_label = tk.Label(info_frame, text="🚨 Falls: 0", font=('Arial', 20, 'bold'), 
                                  fg='#ff4444', bg='#16213e')
        self.fall_label.pack(side='left', padx=(0,20))
        
        self.time_label = tk.Label(info_frame, text=datetime.now().strftime("🕐 %H:%M:%S"), 
                                  font=('Arial', 20, 'bold'), fg='#ffffff', bg='#16213e')
        self.time_label.pack(side='left')
        
        self.status_label = tk.Label(status_frame, text="⏹️ STOPPED", font=('Arial', 20, 'bold'), 
                                   fg='#888', bg='#16213e')
        self.status_label.pack(side='right', padx=40, pady=25)
        
        # ✅ Video بحجم ثابت
        video_container = tk.Frame(self.root, bg='#111', relief='ridge', bd=4)
        video_container.pack(fill='both', expand=True, padx=20, pady=15)
        video_container.pack_propagate(False)
        
        # ✅ Frame بحجم ثابت للفيديو
        self.video_frame = tk.Frame(video_container, bg='#000', width=self.VIDEO_WIDTH, 
                                   height=self.VIDEO_HEIGHT)
        self.video_frame.pack(expand=True)
        self.video_frame.pack_propagate(False)  # ✅ ثابت الحجم
        
        self.video_label = tk.Label(self.video_frame, bg='#000', text="اضغط START")
        self.video_label.pack(fill='both', expand=True)
        
        # Snapshots scrollable
        snapshots_frame = tk.Frame(self.root, bg='#1a1a2e', height=250)
        snapshots_frame.pack(fill='x', padx=15, pady=5)
        snapshots_frame.pack_propagate(False)
        
        tk.Label(snapshots_frame, text="📸 SNAPSHOTS - اضغط للتكبير والسكرول", 
                font=('Arial', 18, 'bold'), fg='#00ff88', bg='#1a1a2e').pack(pady=(20,10))
        
        canvas_frame = tk.Frame(snapshots_frame, bg='#2a2a3e')
        canvas_frame.pack(fill='both', expand=True, padx=20, pady=(0,20))
        
        self.thumbs_canvas = tk.Canvas(canvas_frame, bg='#2a2a3e', height=180)
        scrollbar = tk.Scrollbar(canvas_frame, orient="horizontal", command=self.thumbs_canvas.xview)
        self.thumbs_canvas.configure(xscrollcommand=scrollbar.set)
        
        self.thumbs_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="bottom", fill="x")
        
        self.thumbs_inner_frame = tk.Frame(self.thumbs_canvas, bg='#2a2a3e')
        self.thumbs_canvas_window = self.thumbs_canvas.create_window((0, 0), 
                                                                   window=self.thumbs_inner_frame, anchor="nw")
        self.thumbs_inner_frame.bind('<Configure>', self.on_thumbs_configure)
    
    def update_time(self):
        """تحديث الوقت كل ثانية"""
        current_time = datetime.now().strftime("🕐 %H:%M:%S")
        self.time_label.config(text=current_time)
        self.root.after(1000, self.update_time)
    
    def on_thumbs_configure(self, event):
        self.thumbs_canvas.configure(scrollregion=self.thumbs_canvas.bbox("all"))
    
    def load_snapshots(self):
        """تحميل السناب شوتس"""
        for widget in self.thumbs_inner_frame.winfo_children():
            widget.destroy()
        
        if os.path.exists(self.snapshots_dir):
            files = [f for f in os.listdir(self.snapshots_dir) if f.endswith('.jpg')]
            files.sort(reverse=True)
            for i, filename in enumerate(files):
                filepath = os.path.join(self.snapshots_dir, filename)
                self.create_perfect_thumbnail(filepath, i)
    
    def create_perfect_thumbnail(self, filepath, index):
        try:
            img = Image.open(filepath)
            img.thumbnail((110, 85), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            
            thumb_frame = tk.Frame(self.thumbs_inner_frame, bg='#2a2a3e', width=130, height=110)
            thumb_frame.pack(side='left', padx=10, pady=8)
            thumb_frame.pack_propagate(False)
            
            img_label = tk.Label(thumb_frame, image=photo, bg='#333', cursor='hand2', bd=2, relief='ridge')
            img_label.image = photo
            img_label.pack(pady=3)
            img_label.bind('<Button-1>', lambda e, p=filepath: self.show_full_snapshot(p))
            
            tk.Label(thumb_frame, text=os.path.basename(filepath)[-15:], 
                    fg='white', bg='#2a2a3e', font=('Arial', 9)).pack()
        except:
            pass
    
    def show_full_snapshot(self, filepath):
        try:
            win = tk.Toplevel(self.root)
            win.title("سناب شوت كامل")
            win.geometry("1200x800")
            win.configure(bg='black')
            
            img = Image.open(filepath)
            img.thumbnail((1150, 750), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            
            label = tk.Label(win, image=photo, bg='black')
            label.image = photo
            label.pack(expand=True, pady=20)
        except:
            pass
    
    def start_detection(self):
        try:
            self.stop_detection()
            
            source = int(self.source_var.get().split()[0]) if '(' in self.source_var.get() else self.source_var.get()
            
            self.cap = cv2.VideoCapture(source, cv2.CAP_DSHOW)
            if not self.cap.isOpened():
                self.cap = cv2.VideoCapture(source)
            
            if not self.cap.isOpened():
                self.status_label.config(text="❌ الكاميرا غير متاحة!", fg='red')
                return
            
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self.cap.set(cv2.CAP_PROP_FPS, 30)
            
            self.running = True
            self.paused = False
            self.frame_count = 0
            self.fps_count = 0
            self.last_fps_time = time.time()
            
            self.start_btn.config(state='disabled')
            self.stop_btn.config(state='normal')
            self.pause_btn.config(state='normal')
            self.status_label.config(text="🚀 LIVE 75 FPS ✅", fg='#00ff88')
            
            self.load_snapshots()
            self.update_time()  # بدء الـtimer
            
            self.video_thread = threading.Thread(target=self.video_loop, daemon=True)
            self.video_thread.start()
            
        except Exception as e:
            self.status_label.config(text=f"❌ خطأ: {str(e)}", fg='red')
    
    def stop_detection(self):
        self.running = False
        if self.cap:
            self.cap.release()
            self.cap = None
        
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.pause_btn.config(state='disabled', text="⏸️ PAUSE")
        self.status_label.config(text="⏹️ STOPPED", fg='#888')
        self.video_label.config(image='', text="اضغط START")
    
    def toggle_pause(self):
        self.paused = not self.paused
        status_text = "▶️ RESUME" if self.paused else "⏸️ PAUSE"
        status_color = '#ffaa00' if self.paused else '#00ff88'
        status_msg = "⏸️ PAUSED" if self.paused else "🚀 LIVE 75 FPS ✅"
        
        self.pause_btn.config(text=status_text)
        self.status_label.config(text=status_msg, fg=status_color)
    
    def video_loop(self):
        while self.running:
            if self.paused:
                time.sleep(0.1)
                continue
            
            ret, frame = self.cap.read()
            if not ret or frame is None:
                time.sleep(0.05)
                continue
            
            self.frame_count += 1
            
            if self.frame_count % 4 == 0:
                try:
                    small_frame = cv2.resize(frame, (640, 480))
                    results = self.model.track(small_frame, persist=True, verbose=False)
                    
                    for r in results:
                        if r.boxes is not None:
                            for i in range(len(r.boxes)):
                                track_id = int(r.boxes.id[i])
                                state = self.tracker_states[track_id]
                                
                                kpts = r.keypoints.xy[i].cpu().numpy()
                                bbox = r.boxes.xyxy[i].cpu().numpy()
                                
                                aspect_ratio = (bbox[2]-bbox[0]) / max((bbox[3]-bbox[1]), 1)
                                
                                hips = kpts[[11,12]]
                                if not np.isnan(hips[:,1]).all():
                                    hip_y = np.mean(hips[hips[:,1]>0,1])
                                    hip_ratio = (bbox[3] - hip_y) / max((bbox[3]-bbox[1]), 1)
                                    
                                    if state['state'] == 'UPRIGHT' and (aspect_ratio > 0.85 or hip_ratio < 0.2):
                                        state['state'] = 'FALLING'
                                        state['fall_start'] = time.time()
                                    
                                    elif state['state'] == 'FALLING':
                                        fall_duration = time.time() - state['fall_start']
                                        state['fall_duration'] = fall_duration
                                        
                                        if fall_duration > 2.0 and not state.get('confirmed_fall', False):
                                            state['confirmed_fall'] = True
                                            state['is_falling'] = True
                                            state['fall_time'] = time.time()
                                            self.fall_count += 1
                                            self.root.after(0, lambda fc=self.fall_count: 
                                                          self.fall_label.config(text=f"🚨 Falls: {fc}"))
                                            self.save_snapshot_with_timer(frame.copy(), track_id, fall_duration)
                                        
                                        elif hip_ratio > 0.6 and state.get('confirmed_fall', False):
                                            state['state'] = 'UPRIGHT'
                                            state['confirmed_fall'] = False
                                            state['photo_taken'] = False
                                            state['is_falling'] = False
                except:
                    pass
            
            # عرض بحجم ثابت ✅
            display_frame = cv2.resize(frame, (self.VIDEO_WIDTH, self.VIDEO_HEIGHT))
            
            # Red alert overlay
            for track_id, state in list(self.tracker_states.items()):
                if state.get('is_falling', False):
                    fall_duration = time.time() - state['fall_time']
                    cv2.rectangle(display_frame, (10, 50), (350, 90), (0, 0, 200), -1)
                    cv2.putText(display_frame, f"🚨 FALLING ID:{track_id} {fall_duration:.1f}s", 
                              (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            
            self.root.after(0, lambda f=display_frame: self.show_frame(f))
            
            self.fps_count += 1
            if time.time() - self.last_fps_time > 1:
                self.root.after(0, lambda fps=round(self.fps_count, 1): 
                              self.fps_label.config(text=f"FPS: {fps}"))
                self.fps_count = 0
                self.last_fps_time = time.time()
            
            time.sleep(0.013)  # 75 FPS
    
    def show_frame(self, frame):
        try:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            photo = ImageTk.PhotoImage(Image.fromarray(frame_rgb))
            self.video_label.configure(image=photo)
            self.video_label.image = photo
        except:
            pass
    
    def save_snapshot_with_timer(self, frame, track_id, duration):
        state = self.tracker_states[track_id]
        if state['photo_taken']: 
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"fall_{track_id}_{timestamp}.jpg"
        filepath = os.path.join(self.snapshots_dir, filename)
        
        snapshot = cv2.resize(frame, (self.VIDEO_WIDTH, self.VIDEO_HEIGHT))
        cv2.rectangle(snapshot, (50, 50), (snapshot.shape[1]-50, 220), (0, 0, 200), -1)
        cv2.putText(snapshot, f"🚨 EMERGENCY FALL DETECTED!", (80, 110), 
                   cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 4)
        cv2.putText(snapshot, f"ID: {track_id} | Duration: {duration:.1f}s", (80, 155), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 3)
        cv2.putText(snapshot, f"Time: {datetime.now().strftime('%H:%M:%S')}", (80, 190), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        cv2.imwrite(filepath, snapshot)
        state['photo_taken'] = True
        self.root.after(0, self.load_snapshots)
    
    def run(self):
        try:
            self.root.mainloop()
        finally:
            self.running = False
            if self.cap:
                self.cap.release()

if __name__ == "__main__":
    app = AdvancedFallDetection()
    app.run()
