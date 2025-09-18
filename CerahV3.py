import cv2
import numpy as np
import pyautogui
import mss
import time
import json
import keyboard
import threading
import tkinter as tk
from PIL import Image
import os
from playsound import playsound

# ====== ปรับค่าพื้นฐาน =======
Speed1 = 0.15
Speed2 = 2.7
MousemovementSpeed = 0.03
WeightTimeset = 3

# ====== โหลดตำแหน่งและเทมเพลต =======
with open("positions.json", "r") as f:
    positions_sets = json.load(f)


monitor = None
weight_monitor = None
plus6_templates = []

for i in range(2):
    path = f"plus6_template_{i}.png"
    if os.path.exists(path):
        template = cv2.imread(path, 0)
        plus6_templates.append(template)
        print(f"✅ โหลด {path}")
    else:
        print(f"❌ ไม่พบ {path}")

current_set_index = 0
running = False
snipping_running = False
last_weight_image = None
weight_stable_since = None
sound_played = False

# ====== ฟังชั่นเล่นเสียงแจ้งเตือน =======
def play_alert():
    try:
        playsound(r"C:\Users\thako\OneDrive\Desktop\chenpy\Hongnoi.wav")
    except Exception as e:
        print(f"❌ เล่นเสียงไม่สำเร็จ: {e}")

# ====== ฟังชั่น Snipping Tool =======
def launch_snipping_tool(target):
    global snipping_running
    if snipping_running:
        return
    snipping_running = True

    class SnippingTool:
        def __init__(self):
            self.start_x = None
            self.start_y = None
            self.rect = None
            self.root = tk.Tk()
            self.root.attributes("-alpha", 0.3)
            self.root.attributes("-fullscreen", True)
            self.root.config(cursor="cross")
            self.root.bind("<ButtonPress-1>", self.on_mouse_down)
            self.root.bind("<B1-Motion>", self.on_mouse_drag)
            self.root.bind("<ButtonRelease-1>", self.on_mouse_up)
            self.canvas = tk.Canvas(self.root, bg="black")
            self.canvas.pack(fill=tk.BOTH, expand=True)
            self.root.mainloop()

        def on_mouse_down(self, event):
            self.start_x = event.x
            self.start_y = event.y
            self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline="red")

        def on_mouse_drag(self, event):
            self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

        def on_mouse_up(self, event):
            global monitor, weight_monitor, snipping_running
            x1 = min(self.start_x, event.x)
            y1 = min(self.start_y, event.y)
            x2 = max(self.start_x, event.x)
            y2 = max(self.start_y, event.y)
            width = x2 - x1
            height = y2 - y1
            box = {"top": y1, "left": x1, "width": width, "height": height}
            if target == "plus6":
                monitor = box
                print(f"\n✅ ตั้งค่าพื้นที่จับภาพ +6 แล้ว: {monitor}")
            else:
                weight_monitor = box
                print(f"\n✅ ตั้งค่าพื้นที่จับภาพน้ำหนักแล้ว: {weight_monitor}")
            snipping_running = False
            self.root.destroy()

    threading.Thread(target=SnippingTool).start()

# ====== ตรวจจับเลข +6 ด้วย Template Matching =======
def check_for_plus6_template(screenshot, return_score=False):
    img = np.array(screenshot)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    max_template_h = max(t.shape[0] for t in plus6_templates)
    max_template_w = max(t.shape[1] for t in plus6_templates)

    h, w = gray.shape
    center_y = h // 2
    center_x = w // 2

    crop_top = max(center_y - max_template_h // 2, 0)
    crop_left = max(center_x - max_template_w // 2, 0)
    crop_bottom = crop_top + max_template_h
    crop_right = crop_left + max_template_w

    cropped = gray[crop_top:crop_bottom, crop_left:crop_right]

    best_score = 0
    for template in plus6_templates:
        if cropped.shape[0] < template.shape[0] or cropped.shape[1] < template.shape[1]:
            continue
        res = cv2.matchTemplate(cropped, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(res)
        best_score = max(best_score, max_val)
        if not return_score and max_val >= 0.85:
            return True
    return best_score if return_score else False

# ====== ตรวจว่าน้ำหนักนิ่งหรือไม่ =======
def check_weight_stable():
    global last_weight_image, weight_stable_since, sound_played
    with mss.mss() as sct:
        while running:
            if not weight_monitor:
                time.sleep(0.5)
                continue

            img = sct.grab(weight_monitor)
            img_np = np.array(img)
            img_gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)

            if last_weight_image is None:
                last_weight_image = img_gray
                weight_stable_since = None
                continue

            if last_weight_image.shape != img_gray.shape:
                last_weight_image = img_gray
                weight_stable_since = None
                sound_played = False
                continue

            diff = cv2.absdiff(last_weight_image, img_gray)
            non_zero_count = np.count_nonzero(diff)
            pixel_change_threshold = 60

            if non_zero_count < pixel_change_threshold:
                if weight_stable_since is None:
                    weight_stable_since = time.time()
                elif time.time() - weight_stable_since >= WeightTimeset:
                    if not sound_played:
                        print("🔔 น้ำหนักนิ่งแล้ว แจ้งเตือน!")
                        threading.Thread(target=play_alert).start()
                        sound_played = True
            else:
                weight_stable_since = None
                sound_played = False

            last_weight_image = img_gray
            time.sleep(Speed2)

# ====== วนลูปเมาส์ + ตรวจจับภาพ =======
def move_mouse_loop():
    global current_set_index, running
    last_detect_time = 0

    with mss.mss() as sct:
        while running:
            if not monitor:
                print("⚠️ ยังไม่ได้ตั้งค่า monitor (กด F4 ก่อน)")
                time.sleep(1)
                continue

            current_set = positions_sets[current_set_index]

            for pos in current_set:
                if not running:
                    break
                pyautogui.moveTo(pos[0], pos[1], duration=0)
                time.sleep(MousemovementSpeed)
                img = sct.grab(monitor)
                now = time.time()
                if now - last_detect_time > Speed1:
                    if check_for_plus6_template(img):
                        last_detect_time = now
                        current_set_index += 1
                        if current_set_index >= len(positions_sets):
                            current_set_index = 0
                        break

# ====== ฟัง Key กดจากผู้ใช้ =======
def key_listener():
    global running, current_set_index, sound_played, last_weight_image, weight_stable_since
    move_thread = None

    while True:
        if keyboard.is_pressed('f2'):
            if running:
                print("⏸ หยุดทำงาน")
                running = False
                if move_thread:
                    move_thread.join()
            else:
                print("▶️ เริ่มทำงานใหม่")
                current_set_index = 0
                running = True
                sound_played = False
                last_weight_image = None
                weight_stable_since = None
                threading.Thread(target=check_weight_stable).start()
                move_thread = threading.Thread(target=move_mouse_loop)
                move_thread.start()
            while keyboard.is_pressed('f2'): pass

        if keyboard.is_pressed('f3'):
            if not monitor:
                print("⚠️ ยังไม่ได้ตั้ง monitor (กด F4 ก่อน)")
            else:
                with mss.mss() as sct:
                    img = sct.grab(monitor)
                    score = check_for_plus6_template(img, return_score=True)
                    print(f"📊 ความแม่นยำของ Template Matching: {score:.4f}")
            while keyboard.is_pressed('f3'): pass

        if keyboard.is_pressed('f4'):
            print("📐 เลือกพื้นที่ตรวจจับ +6")
            launch_snipping_tool("plus6")
            while keyboard.is_pressed('f4'): pass

        if keyboard.is_pressed('f5'):
            print("📐 เลือกพื้นที่ตรวจจับน้ำหนัก")
            launch_snipping_tool("weight")
            while keyboard.is_pressed('f5'): pass

        if keyboard.is_pressed('f6'):
            print("🔊 ทดสอบเสียงแจ้งเตือน...")
            threading.Thread(target=play_alert).start()
            while keyboard.is_pressed('f6'): pass

        time.sleep(0.05)

# ====== เริ่มต้นโปรแกรม =======
if __name__ == "__main__":
    threading.Thread(target=key_listener).start()
