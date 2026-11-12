import cv2
import socket
import json
import numpy as np
import tkinter as tk
from tkinter import messagebox, ttk
from PIL import Image, ImageTk
import subprocess
import psutil
import sys
import os

HOST = "127.0.0.1"
PORT = 8888

# 测试类型枚举（和后端对应）
TEST_CLAP = 0
TEST_SQUAT = 1
TEST_FACE = 2

# 命令码（和后端对应，从0x80开始，避免和图像模式0/1冲突）
CMD_START_TEST = 0x81
CMD_STOP_TEST = 0x82
CMD_GET_RECORDS = 0x83
CMD_CLEAR_RECORDS = 0x84

# ========== 配色 ==========
COLOR_BG = "#e6f9e9"
COLOR_CARD = "#ffffff"
CARD1_MAIN = "#22c55e"
CARD2_MAIN = "#3b82f6"
CARD3_MAIN = "#ec4899"
CARD4_MAIN = "#f97316"
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
        self.sock = None

        self.start_backend()
        self.after(800, self.connect_server)

        self.container = tk.Frame(self, bg=COLOR_BG)
        self.container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.frames = {}
        for F in (HomePage, ClapTestPage, SquatTestPage, FaceScorePage, RecordPage):
            frame = F(self.container, self)
            self.frames[F] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.show_frame(HomePage)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def start_backend(self):
        server_py = get_resource_path("server.py")
        exe_path = get_resource_path("server.exe")
        if os.path.exists(exe_path):
            self.server_proc = subprocess.Popen([exe_path], creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            self.server_proc = subprocess.Popen([sys.executable, server_py])

    def connect_server(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(2.0)
            self.sock.connect((HOST, PORT))
            self.sock.settimeout(None)
        except Exception:
            self.sock = None
            messagebox.showerror("错误", "后端推理服务启动失败！")

    def show_frame(self, page_class):
        frame = self.frames[page_class]
        frame.tkraise()
        # 记录页显示时自动刷新
        if page_class == RecordPage:
            frame.refresh()

    def get_socket(self):
        return self.sock

    # ========== 统一通信方法 ==========
    def send_command(self, cmd_byte, extra_bytes=None):
        """发送命令帧，返回后端JSON响应"""
        sock = self.sock
        if sock is None:
            return {"success": False, "message": "服务未连接"}
        try:
            sock.sendall(bytes([cmd_byte]))
            if extra_bytes:
                sock.sendall(extra_bytes)
            return self.recv_json()
        except Exception as e:
            print(f"命令发送异常: {e}")
            return {"success": False, "message": str(e)}

    def send_image_frame(self, mode_byte, frame):
        """发送图像帧，返回后端JSON响应"""
        sock = self.sock
        if sock is None:
            return {"success": False, "landmarks": [], "tip": "服务未连接", "count": 0, "score": None}
        try:
            success, buf = cv2.imencode(".jpg", frame)
            if not success:
                return {"success": False, "landmarks": [], "tip": "编码失败", "count": 0, "score": None}
            img_bytes = buf.tobytes()
            sock.sendall(bytes([mode_byte]))
            sock.sendall(len(img_bytes).to_bytes(4, byteorder="big"))
            sock.sendall(img_bytes)
            return self.recv_json()
        except Exception as e:
            print(f"图像发送异常: {e}")
            return None

    def recv_json(self):
        """接收一行JSON响应"""
        sock = self.sock
        raw = b""
        while True:
            c = sock.recv(1)
            if c == b"\n" or not c:
                break
            raw += c
        if raw:
            return json.loads(raw.decode("utf-8"))
        return {"success": False}

    def on_close(self):
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

        button_info = [
            {"icon": "👏", "text": "拍手计数测试", "cmd": lambda: controller.show_frame(ClapTestPage), "color": CARD1_MAIN},
            {"icon": "🏃", "text": "深蹲计数测试", "cmd": lambda: controller.show_frame(SquatTestPage), "color": CARD2_MAIN},
            {"icon": "✨", "text": "颜值比例测评", "cmd": lambda: controller.show_frame(FaceScorePage), "color": CARD3_MAIN},
            {"icon": "📋", "text": "我的记录", "cmd": lambda: controller.show_frame(RecordPage), "color": CARD4_MAIN},
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
        c = hex_color.lstrip("#")
        r = max(0, int(c[0:2], 16) - 30)
        g = max(0, int(c[2:4], 16) - 30)
        b = max(0, int(c[4:6], 16) - 30)
        return f"#{r:02x}{g:02x}{b:02x}"


# ---------------------- 拍手页面 ----------------------
class ClapTestPage(tk.Frame):
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
        # 通知后端开始拍手测试
        self.controller.send_command(CMD_START_TEST, bytes([TEST_CLAP]))
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            messagebox.showerror("错误", "摄像头打开失败")
            return
        self.is_running = True
        self.info_label.config(text="拍手总数：0")
        self.update_frame()

    def stop_capture(self):
        self.is_running = False
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        # 通知后端结束测试（后端自动保存记录）
        if self.controller.get_socket() is not None:
            self.controller.send_command(CMD_STOP_TEST)
        print("===== 拍手测试结束 =====")

    def update_frame(self):
        if not self.is_running:
            return
        ret, frame = self.cap.read()
        if not ret:
            self.stop_capture()
            return

        # 发送图像，后端返回结果
        res = self.controller.send_image_frame(0, frame)
        if res is None:
            self.stop_capture()
            return

        tip_text = res.get("tip", "未检测人体")
        count = res.get("count", 0)
        self.info_label.config(text=f"拍手总数：{count}")

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


# ---------------------- 深蹲页面 ----------------------
class SquatTestPage(tk.Frame):
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
        # 通知后端开始深蹲测试
        self.controller.send_command(CMD_START_TEST, bytes([TEST_SQUAT]))
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            messagebox.showerror("错误", "摄像头打开失败")
            return
        self.is_running = True
        self.info_label.config(text="深蹲总数：0")
        self.update_frame()

    def stop_capture(self):
        self.is_running = False
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        # 通知后端结束测试（后端自动保存记录）
        if self.controller.get_socket() is not None:
            self.controller.send_command(CMD_STOP_TEST)
        print("===== 深蹲测试结束 =====")

    def update_frame(self):
        if not self.is_running:
            return
        ret, frame = self.cap.read()
        if not ret:
            self.stop_capture()
            return

        res = self.controller.send_image_frame(0, frame)
        if res is None:
            self.stop_capture()
            return

        tip_text = res.get("tip", "未检测人体")
        count = res.get("count", 0)
        self.info_label.config(text=f"深蹲总数：{count}")

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
        # 通知后端开始颜值测评
        self.controller.send_command(CMD_START_TEST, bytes([TEST_FACE]))
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
        # 通知后端结束测试（后端自动保存记录）
        if self.controller.get_socket() is not None:
            self.controller.send_command(CMD_STOP_TEST)
        print("===== 面部测评结束 =====")
        self.info_label.config(text="颜值分数：--")

    def update_frame(self):
        if not self.is_running:
            return
        ret, frame = self.cap.read()
        if not ret:
            self.stop_capture()
            return

        res = self.controller.send_image_frame(1, frame)
        if res is None:
            self.stop_capture()
            return

        tip_text = res.get("tip", "未检测人脸")
        score = res.get("score")
        if score is not None:
            self.info_label.config(text=f"颜值分数：{score:.1f}")

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


# ---------------------- 记录页面 ----------------------
class RecordPage(tk.Frame):
    def __init__(self, parent, controller: MainApp):
        super().__init__(parent, bg=COLOR_BG)
        self.controller = controller

        top_frame = tk.Frame(self, bg=COLOR_BG)
        top_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        back_btn = tk.Button(
            top_frame, text="← 返回主页",
            command=lambda: controller.show_frame(HomePage),
            font=("SimHei", 11), bg=COLOR_GRAY, fg="white", relief=tk.FLAT
        )
        back_btn.pack(side=tk.LEFT)

        title_label = tk.Label(
            top_frame, text="我的记录",
            font=("SimHei", 18, "bold"), fg=COLOR_TEXT, bg=COLOR_BG
        )
        title_label.pack(side=tk.LEFT, padx=60)

        clear_btn = tk.Button(
            top_frame, text="清空全部记录", command=self.clear_all,
            font=("SimHei", 11), bg="#dc2626", fg="white", relief=tk.FLAT
        )
        clear_btn.pack(side=tk.RIGHT)

        # 表格
        self.tree = ttk.Treeview(self, columns=("id", "time", "type", "result"), show="headings")
        self.tree.heading("id", text="编号")
        self.tree.heading("time", text="测试时间")
        self.tree.heading("type", text="测试项目")
        self.tree.heading("result", text="结果")
        self.tree.column("id", width=60)
        self.tree.column("time", width=180)
        self.tree.column("type", width=160)
        self.tree.column("result", width=120)
        self.tree.grid(row=1, column=0, sticky="nsew", pady=10)

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

    def refresh(self):
        """从后端拉取记录列表"""
        for item in self.tree.get_children():
            self.tree.delete(item)

        res = self.controller.send_command(CMD_GET_RECORDS)
        if not res.get("success"):
            self.tree.insert("", tk.END, values=("-", "无法连接后端", "", ""))
            return

        records = res.get("records", [])
        if not records:
            self.tree.insert("", tk.END, values=("-", "暂无记录", "", ""))
            return

        for r in records:
            rid, t, typ, cnt, sc = r
            if cnt is not None:
                result = f"{cnt} 次"
            elif sc is not None:
                result = f"{sc:.1f} 分"
            else:
                result = "--"
            self.tree.insert("", tk.END, values=(rid, t, typ, result))

    def clear_all(self):
        if messagebox.askyesno("确认", "确定清空全部记录？"):
            self.controller.send_command(CMD_CLEAR_RECORDS)
            self.refresh()


if __name__ == "__main__":
    app = MainApp()
    app.mainloop()
