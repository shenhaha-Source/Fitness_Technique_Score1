import cv2
import socket
import json
import numpy as np
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import subprocess
import psutil
import sys
import os

HOST = "127.0.0.1"
PORT = 8888

# 拍手
HAND_CLOSE_THRESH = 0.35
HAND_OPEN_THRESH = 0.45
STATE_APART = "apart"
STATE_CLAP = "clap"

# 深蹲
SQUAT_THRESHOLD = 0.08
STATE_STAND = "stand"
STATE_SQUAT = "squat"

# ========== 【新配色，背景绿色 + 多彩卡片】 ==========
COLOR_BG = "#e6f9e9"          # 整体背景：浅薄荷绿
COLOR_CARD = "#ffffff"
# 四个卡片主题色
CARD1_MAIN = "#22c55e"   # 拍手：绿色
CARD2_MAIN = "#3b82f6"   # 深蹲：蓝色
CARD3_MAIN = "#ec4899"   # 颜值：玫红
CARD4_MAIN = "#f97316"   # 记录：橙色
COLOR_TEXT = "#1e293b"
COLOR_GRAY = "#64748b"
COLOR_SHADOW = "#c2e8c7"

def get_resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AI动作识别系统")
        self.geometry("720x600")
        self.resizable(True, True)
        self.configure(bg=COLOR_BG)
        self.server_proc = None
        # 启动后端server
        self.start_backend()
        # 等待后端启动再连接
        self.after(800, self.connect_server)

        self.container = tk.Frame(self, bg=COLOR_BG)
        self.container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.frames = {}
        for F in (HomePage, ClapTestPage, SquatTestPage, FaceScorePage):
            frame = F(self.container, self)
            self.frames[F] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.show_frame(HomePage)
        # 窗口关闭事件：杀掉后端
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def start_backend(self):
        server_py = get_resource_path("server.py")
        # 打包后，在同目录下的server.exe
        exe_path = get_resource_path("server.exe")
        if os.path.exists(exe_path):
            self.server_proc = subprocess.Popen([exe_path], creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            # 开发环境，直接python跑
            self.server_proc = subprocess.Popen([sys.executable, server_py])

    def connect_server(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(2.0)
            self.sock.connect((HOST, PORT))
        except Exception:
            self.sock = None
            messagebox.showerror("错误", "后端推理服务启动失败！")

    def show_frame(self, page_class):
        frame = self.frames[page_class]
        frame.tkraise()

    def get_socket(self):
        return self.sock

    def on_close(self):
        # 关闭GUI，杀掉server进程
        if self.server_proc is not None:
            try:
                proc = psutil.Process(self.server_proc.pid)
                for child in proc.children(recursive=True):
                    child.kill()
                proc.kill()
            except:
                pass
        self.destroy()

# ---------------------- 主页 ----------------------
class HomePage(tk.Frame):
    def __init__(self, parent, controller: MainApp):
        super().__init__(parent, bg=COLOR_BG)
        self.controller = controller

        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=3)
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        title_frame = tk.Frame(self, bg=COLOR_BG)
        title_frame.grid(row=0, column=0, sticky="n")

        title_label = tk.Label(
            title_frame, text="AI动作识别系统",
            font=("SimHei", 30, "bold"), fg="#16a34a", bg=COLOR_BG
        )
        title_label.pack()

        sub_label = tk.Label(
            title_frame, text="实时姿态识别 · 动作计数 · 面部比例测评",
            font=("SimHei", 13), fg=COLOR_GRAY, bg=COLOR_BG
        )
        sub_label.pack(pady=(6, 0))

        line = tk.Frame(self, bg="#94d8a0", height=2)
        line.grid(row=0, column=0, sticky="ew", padx=60, pady=(20, 0))

        card_wrap = tk.Frame(self, bg=COLOR_BG)
        card_wrap.grid(row=1, column=0)
        card_wrap.grid_columnconfigure(0, weight=1)
        card_wrap.grid_columnconfigure(1, weight=1)

        # 【多彩卡片配置】每个卡片独立颜色
        button_info = [
            {"icon": "👏", "text": "拍手计数测试", "cmd": lambda: controller.show_frame(ClapTestPage), "color": CARD1_MAIN},
            {"icon": "🏃", "text": "深蹲计数测试", "cmd": lambda: controller.show_frame(SquatTestPage), "color": CARD2_MAIN},
            {"icon": "✨", "text": "颜值比例测评", "cmd": lambda: controller.show_frame(FaceScorePage), "color": CARD3_MAIN},
            {"icon": "📋", "text": "我的记录", "cmd": lambda: self.show_tip("我的记录，开发中..."), "color": CARD4_MAIN},
        ]

        for idx, item in enumerate(button_info):
            r = idx // 2
            c = idx % 2
            shadow = tk.Frame(card_wrap, bg=COLOR_SHADOW)
            shadow.grid(row=r, column=c, padx=16, pady=16)
            card = tk.Frame(shadow, bg=COLOR_CARD, padx=24, pady=24)
            card.pack(padx=3, pady=3)

            icon_label = tk.Label(card, text=item["icon"], font=("SimHei", 36), bg=COLOR_CARD)
            icon_label.pack()
            text_label = tk.Label(card, text=item["text"], font=("SimHei", 14, "bold"), fg=COLOR_TEXT, bg=COLOR_CARD)
            text_label.pack(pady=(8, 14))

            btn = tk.Button(
                card, text="进入测试", command=item["cmd"],
                font=("SimHei", 11), width=10,
                bg=item["color"], fg="white", relief=tk.FLAT,
                activebackground=self.darken_color(item["color"])
            )
            btn.pack()

        bottom_label = tk.Label(
            self, text="© 2026 AI姿态项目 | 颜值仅几何比例趣味测评",
            font=("SimHei", 10), fg=COLOR_GRAY, bg=COLOR_BG
        )
        bottom_label.grid(row=2, column=0, sticky="s")

    def darken_color(self, hex_color):
        # 简单加深颜色，用于hover
        c = hex_color.lstrip("#")
        r = max(0, int(c[0:2],16)-30)
        g = max(0, int(c[2:4],16)-30)
        b = max(0, int(c[4:6],16)-30)
        return f"#{r:02x}{g:02x}{b:02x}"

    def show_tip(self, msg):
        messagebox.showinfo("提示", msg)

# ---------------------- 拍手页面 ----------------------
class ClapTestPage(tk.Frame):
    def __init__(self, parent, controller: MainApp):
        super().__init__(parent, bg=COLOR_BG)
        self.controller = controller
        self.is_running = False
        self.state = STATE_APART
        self.clap_count = 0
        self.cap = None
        self.imgtk = None

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        top_frame = tk.Frame(self, bg=COLOR_BG)
        top_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        back_btn = tk.Button(
            top_frame, text="← 返回主页",
            command=self.go_back, font=("SimHei", 11),
            bg=COLOR_GRAY, fg="white", relief=tk.FLAT
        )
        back_btn.pack(side=tk.LEFT)

        title_label = tk.Label(
            top_frame, text="拍手计数测试",
            font=("SimHei", 18, "bold"), fg=COLOR_TEXT, bg=COLOR_BG
        )
        title_label.pack(side=tk.LEFT, padx=60)

        ctrl_frame = tk.Frame(self, bg=COLOR_BG)
        ctrl_frame.grid(row=0, column=0, sticky="ew", pady=(60, 0))

        self.btn_start = tk.Button(
            ctrl_frame, text="开始测试", command=self.start_capture,
            font=("SimHei", 12), width=12,
            bg=CARD1_MAIN, fg="white", relief=tk.FLAT, activebackground="#16a34a"
        )
        self.btn_start.grid(row=0, column=0, padx=8)

        self.btn_stop = tk.Button(
            ctrl_frame, text="关闭测试", command=self.stop_capture,
            font=("SimHei", 12), width=12,
            bg="#dc2626", fg="white", relief=tk.FLAT
        )
        self.btn_stop.grid(row=0, column=1, padx=8)

        self.info_label = tk.Label(
            self, text="拍手总数：0", font=("SimHei", 15),
            fg=COLOR_TEXT, bg=COLOR_BG
        )
        self.info_label.grid(row=0, column=0, sticky="s", pady=(100, 0))

        self.img_label = tk.Label(self, bg="#000000")
        self.img_label.grid(row=1, column=0, sticky="nsew")

    def go_back(self):
        self.stop_capture()
        self.controller.show_frame(HomePage)

    def start_capture(self):
        sock = self.controller.get_socket()
        if self.is_running or sock is None:
            messagebox.showwarning("警告", "推理服务未就绪！")
            return
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            messagebox.showerror("错误", "摄像头打开失败")
            return
        self.is_running = True
        self.state = STATE_APART
        self.clap_count = 0
        self.info_label.config(text=f"拍手总数：{self.clap_count}")
        self.update_frame()

    def stop_capture(self):
        self.is_running = False
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        print("\n===== 拍手测试结束 =====")
        print(f"拍手总次数：{self.clap_count}")
        self.info_label.config(text=f"拍手总数：{self.clap_count}")

    def update_frame(self):
        if not self.is_running:
            return
        ret, frame = self.cap.read()
        if not ret:
            self.stop_capture()
            return
        sock = self.controller.get_socket()
        tip_text = "未检测人体"
        dist = 0.0
        try:
            success, buf = cv2.imencode(".jpg", frame)
            img_bytes = buf.tobytes()
            # 模式0 = Pose
            sock.sendall(b"\x00")
            sock.sendall(len(img_bytes).to_bytes(4, byteorder="big"))
            sock.sendall(img_bytes)

            raw = b""
            while True:
                c = sock.recv(1)
                if c == b"\n" or not c:
                    break
                raw += c
            if raw:
                res = json.loads(raw.decode("utf-8"))
                if res["success"]:
                    lm = res["landmarks"]
                    if len(lm) >= 17:
                        rw = lm[15]
                        lw = lm[16]
                        dist = np.sqrt((rw["x"] - lw["x"]) ** 2 + (rw["y"] - lw["y"]) ** 2)
                        tip_text = f"距离:{dist:.3f}"
                        if self.state == STATE_APART:
                            if dist < HAND_CLOSE_THRESH:
                                self.state = STATE_CLAP
                        elif self.state == STATE_CLAP:
                            if dist > HAND_OPEN_THRESH:
                                self.clap_count += 1
                                tip_text = "👏拍手成功！"
                                print(f"👏拍手，当前总数：{self.clap_count}")
                                self.info_label.config(text=f"拍手总数：{self.clap_count}")
                                self.state = STATE_APART
                    else:
                        tip_text = "手部关键点丢失"
        except Exception as e:
            print(f"通信异常：{e}")
            self.stop_capture()
            return

        cv2.putText(frame, tip_text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(frame, f"距离:{dist:.3f}", (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)

        w = self.img_label.winfo_width()
        h = self.img_label.winfo_height()
        if w > 10 and h > 10:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)
            img = img.resize((w, h), Image.Resampling.LANCZOS)
            self.imgtk = ImageTk.PhotoImage(img)
            self.img_label.config(image=self.imgtk)

        self.after(15, self.update_frame)

# ---------------------- 深蹲页面 ----------------------
class SquatTestPage(tk.Frame):
    def __init__(self, parent, controller: MainApp):
        super().__init__(parent, bg=COLOR_BG)
        self.controller = controller
        self.is_running = False
        self.state = STATE_STAND
        self.squat_count = 0
        self.cap = None
        self.imgtk = None

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        top_frame = tk.Frame(self, bg=COLOR_BG)
        top_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        back_btn = tk.Button(
            top_frame, text="← 返回主页",
            command=self.go_back, font=("SimHei", 11),
            bg=COLOR_GRAY, fg="white", relief=tk.FLAT
        )
        back_btn.pack(side=tk.LEFT)

        title_label = tk.Label(
            top_frame, text="深蹲计数测试",
            font=("SimHei", 18, "bold"), fg=COLOR_TEXT, bg=COLOR_BG
        )
        title_label.pack(side=tk.LEFT, padx=60)

        ctrl_frame = tk.Frame(self, bg=COLOR_BG)
        ctrl_frame.grid(row=0, column=0, sticky="ew", pady=(60, 0))

        self.btn_start = tk.Button(
            ctrl_frame, text="开始测试", command=self.start_capture,
            font=("SimHei", 12), width=12,
            bg=CARD2_MAIN, fg="white", relief=tk.FLAT, activebackground="#2563eb"
        )
        self.btn_start.grid(row=0, column=0, padx=8)

        self.btn_stop = tk.Button(
            ctrl_frame, text="关闭测试", command=self.stop_capture,
            font=("SimHei", 12), width=12,
            bg="#dc2626", fg="white", relief=tk.FLAT
        )
        self.btn_stop.grid(row=0, column=1, padx=8)

        self.info_label = tk.Label(
            self, text="深蹲总数：0", font=("SimHei", 15),
            fg=COLOR_TEXT, bg=COLOR_BG
        )
        self.info_label.grid(row=0, column=0, sticky="s", pady=(100, 0))

        self.img_label = tk.Label(self, bg="#000000")
        self.img_label.grid(row=1, column=0, sticky="nsew")

    def go_back(self):
        self.stop_capture()
        self.controller.show_frame(HomePage)

    def start_capture(self):
        sock = self.controller.get_socket()
        if self.is_running or sock is None:
            messagebox.showwarning("警告", "推理服务未就绪！")
            return
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            messagebox.showerror("错误", "摄像头打开失败")
            return
        self.is_running = True
        self.state = STATE_STAND
        self.squat_count = 0
        self.info_label.config(text=f"深蹲总数：{self.squat_count}")
        self.update_frame()

    def stop_capture(self):
        self.is_running = False
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        print("\n===== 深蹲测试结束 =====")
        print(f"深蹲总次数：{self.squat_count}")
        self.info_label.config(text=f"深蹲总数：{self.squat_count}")

    def update_frame(self):
        if not self.is_running:
            return
        ret, frame = self.cap.read()
        if not ret:
            self.stop_capture()
            return
        sock = self.controller.get_socket()
        tip_text = "未检测人体"
        try:
            success, buf = cv2.imencode(".jpg", frame)
            img_bytes = buf.tobytes()
            sock.sendall(b"\x00")
            sock.sendall(len(img_bytes).to_bytes(4, byteorder="big"))
            sock.sendall(img_bytes)

            raw = b""
            while True:
                c = sock.recv(1)
                if c == b"\n" or not c:
                    break
                raw += c
            if raw:
                res = json.loads(raw.decode("utf-8"))
                if res["success"]:
                    lm = res["landmarks"]
                    if len(lm) >= 27:
                        l_hip = lm[23]
                        r_hip = lm[24]
                        l_knee = lm[25]
                        r_knee = lm[26]
                        hip_y = (l_hip["y"] + r_hip["y"]) / 2
                        knee_y = (l_knee["y"] + r_knee["y"]) / 2
                        tip_text = f"髋y:{hip_y:.3f},膝y:{knee_y:.3f}"

                        if self.state == STATE_STAND:
                            if knee_y > hip_y + SQUAT_THRESHOLD:
                                self.state = STATE_SQUAT
                        elif self.state == STATE_SQUAT:
                            if knee_y < hip_y - SQUAT_THRESHOLD:
                                self.squat_count += 1
                                tip_text = "✅深蹲完成！"
                                print(f"✅深蹲，当前总数：{self.squat_count}")
                                self.info_label.config(text=f"深蹲总数：{self.squat_count}")
                                self.state = STATE_STAND
                    else:
                        tip_text = "关键点缺失"
        except Exception as e:
            print(f"通信异常：{e}")
            self.stop_capture()
            return

        cv2.putText(frame, tip_text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        w = self.img_label.winfo_width()
        h = self.img_label.winfo_height()
        if w > 10 and h > 10:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)
            img = img.resize((w, h), Image.Resampling.LANCZOS)
            self.imgtk = ImageTk.PhotoImage(img)
            self.img_label.config(image=self.imgtk)

        self.after(15, self.update_frame)

# ---------------------- 颜值评分页面 ----------------------
class FaceScorePage(tk.Frame):
    def __init__(self, parent, controller: MainApp):
        super().__init__(parent, bg=COLOR_BG)
        self.controller = controller
        self.is_running = False
        self.cap = None
        self.imgtk = None

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        top_frame = tk.Frame(self, bg=COLOR_BG)
        top_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        back_btn = tk.Button(
            top_frame, text="← 返回主页",
            command=self.go_back, font=("SimHei", 11),
            bg=COLOR_GRAY, fg="white", relief=tk.FLAT
        )
        back_btn.pack(side=tk.LEFT)

        title_label = tk.Label(
            top_frame, text="面部比例测评",
            font=("SimHei", 18, "bold"), fg=COLOR_TEXT, bg=COLOR_BG
        )
        title_label.pack(side=tk.LEFT, padx=60)

        ctrl_frame = tk.Frame(self, bg=COLOR_BG)
        ctrl_frame.grid(row=0, column=0, sticky="ew", pady=(60, 0))

        self.btn_start = tk.Button(
            ctrl_frame, text="开始测评", command=self.start_capture,
            font=("SimHei", 12), width=12,
            bg=CARD3_MAIN, fg="white", relief=tk.FLAT, activebackground="#db2777"
        )
        self.btn_start.grid(row=0, column=0, padx=8)

        self.btn_stop = tk.Button(
            ctrl_frame, text="关闭测评", command=self.stop_capture,
            font=("SimHei", 12), width=12,
            bg="#dc2626", fg="white", relief=tk.FLAT
        )
        self.btn_stop.grid(row=0, column=1, padx=8)

        self.info_label = tk.Label(
            self, text="颜值分数：--", font=("SimHei", 15),
            fg=COLOR_TEXT, bg=COLOR_BG
        )
        self.info_label.grid(row=0, column=0, sticky="s", pady=(100, 0))

        self.img_label = tk.Label(self, bg="#000000")
        self.img_label.grid(row=1, column=0, sticky="nsew")

    def go_back(self):
        self.stop_capture()
        self.controller.show_frame(HomePage)

    def start_capture(self):
        sock = self.controller.get_socket()
        if self.is_running or sock is None:
            messagebox.showwarning("警告", "推理服务未就绪！")
            return
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            messagebox.showerror("错误", "摄像头打开失败")
            return
        self.is_running = True
        self.info_label.config(text="颜值分数：计算中...")
        self.update_frame()

    def stop_capture(self):
        self.is_running = False
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        print("\n===== 面部测评结束 =====")
        self.info_label.config(text="颜值分数：--")

    def calc_face_score(self, lm):
        if len(lm) < 300:
            return None
        forehead = lm[10]
        nose = lm[1]
        chin = lm[152]
        reye = lm[33]
        leye = lm[263]
        rmouth = lm[61]
        lmouth = lm[291]

        h1 = abs(nose["y"] - forehead["y"])
        h2 = abs(chin["y"] - nose["y"])
        ratio_three = h1 / h2 if h2 > 1e-6 else 1
        score_three = max(0, 100 - abs(ratio_three - 1) * 60)

        eye_sym = abs(reye["y"] - leye["y"])
        mouth_sym = abs(rmouth["y"] - lmouth["y"])
        sym_score = max(0, 100 - (eye_sym + mouth_sym) * 250)

        total = 0.5 * score_three + 0.5 * sym_score
        return np.clip(total, 0, 100)

    def update_frame(self):
        if not self.is_running:
            return
        ret, frame = self.cap.read()
        if not ret:
            self.stop_capture()
            return
        sock = self.controller.get_socket()
        tip_text = "未检测人脸"
        try:
            success, buf = cv2.imencode(".jpg", frame)
            img_bytes = buf.tobytes()
            # 模式1 = FaceMesh
            sock.sendall(b"\x01")
            sock.sendall(len(img_bytes).to_bytes(4, byteorder="big"))
            sock.sendall(img_bytes)

            raw = b""
            while True:
                c = sock.recv(1)
                if c == b"\n" or not c:
                    break
                raw += c
            if raw:
                res = json.loads(raw.decode("utf-8"))
                if res["success"]:
                    lm = res["landmarks"]
                    score = self.calc_face_score(lm)
                    if score is not None:
                        tip_text = f"分数：{score:.1f}"
                        self.info_label.config(text=f"颜值分数：{score:.1f}")
                    else:
                        tip_text = "人脸关键点不足"
        except Exception as e:
            print(f"通信异常：{e}")
            self.stop_capture()
            return

        cv2.putText(frame, tip_text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        w = self.img_label.winfo_width()
        h = self.img_label.winfo_height()
        if w > 10 and h > 10:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)
            img = img.resize((w, h), Image.Resampling.LANCZOS)
            self.imgtk = ImageTk.PhotoImage(img)
            self.img_label.config(image=self.imgtk)

        self.after(15, self.update_frame)

if __name__ == "__main__":
    app = MainApp()
    app.mainloop()
