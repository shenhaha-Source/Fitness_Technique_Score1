import cv2
import socket
import json
import numpy as np
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import threading
import psutil
import sys
import os

# 导入视图
from login_view import LoginView
from student_view import StudentView
from teacher_view import TeacherView
import server as backend_server

HOST = "127.0.0.1"
PORT = 8888

# 命令码
CMD_REGISTER = 0x88
CMD_LOGIN = 0x89
CMD_START_TEST = 0x81
CMD_STOP_TEST = 0x82
CMD_GET_MY_SCORE = 0x85
CMD_GET_ALL_SCORES = 0x86
CMD_CLEAR_RECORDS = 0x84

BG_COLOR = "#0B1020"


class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("智慧体测 · AI 动作测评")
        self.geometry("720x640")
        self.minsize(720, 640)
        self.resizable(True, True)
        self.configure(bg=BG_COLOR)
        self._set_window_icon()

        self.server_thread = None
        self.sock = None
        self._socket_lock = threading.Lock()
        self.session_id = None
        self.user_info = None
        self.current_view = None

        # 启动后端（后台线程，同进程，不会反复弹窗）
        self.start_backend()
        self.after(800, self.connect_server)

        # 主容器（登录页自带渐变/星光背景，其他页面使用深色底）
        self.container = tk.Frame(self, bg=BG_COLOR)
        self.container.place(x=0, y=0, relwidth=1, relheight=1)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _set_window_icon(self):
        """设置窗口图标；中文路径/打包环境下失败也不影响启动。"""
        if hasattr(sys, "_MEIPASS"):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(base_dir, "app.ico")
        try:
            self.iconbitmap(icon_path)
            return
        except Exception:
            pass
        try:
            img = Image.open(icon_path).convert("RGBA")
            img.thumbnail((64, 64), Image.LANCZOS)
            self._icon_photo = ImageTk.PhotoImage(img)
            self.iconphoto(True, self._icon_photo)
        except Exception:
            pass

    # ========== 后端服务管理（同进程后台线程） ==========
    def start_backend(self):
        # 开一个守护线程跑socket server，不会反复启动gui
        self.server_thread = threading.Thread(
            target=backend_server.start_server,
            daemon=True
        )
        self.server_thread.start()
        print("✅ 后端服务已在后台线程启动")

    def connect_server(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(3.0)
            self.sock.connect((HOST, PORT))
            self.sock.settimeout(None)
            # 连接成功，显示登录页
            self.show_login()
        except Exception:
            self.sock = None
            messagebox.showerror("错误", "后端推理服务启动失败！")

    # ========== 页面切换 ==========
    def show_login(self):
        """显示登录页"""
        self._clear_current_view()
        self.session_id = None
        self.user_info = None

        self.login_view = LoginView(
            self.container,
            on_login=self._handle_login,
            on_register=self._handle_register
        )
        self.login_view.grid(row=0, column=0, sticky="nsew")
        self.current_view = self.login_view

    def show_main_view(self):
        """登录成功，根据角色显示主视图"""
        self._clear_current_view()

        if self.user_info["role"] == "teacher":
            self.current_view = TeacherView(
                self.container,
                send_command=self.send_command,
                user_info=self.user_info,
                on_logout=self.logout
            )
        else:
            self.current_view = StudentView(
                self.container,
                send_command=self.send_command,
                send_image_frame=self.send_image_frame,
                user_info=self.user_info,
                on_logout=self.logout
            )
        self.current_view.grid(row=0, column=0, sticky="nsew")

    def _clear_current_view(self):
        if self.current_view:
            self.current_view.destroy()
            self.current_view = None

    def logout(self):
        """退出登录，回到登录页"""
        self.show_login()

    # ========== 通信：登录/注册 ==========
    def _handle_login(self, username, password):
        """处理登录按钮点击"""
        if self.sock is None:
            self.login_view.show_error("服务未连接")
            return

        try:
            data = json.dumps({"username": username, "password": password}).encode("utf-8")
            self.sock.sendall(bytes([CMD_LOGIN]) + len(data).to_bytes(4, byteorder="big") + data)

            res = self._recv_json()
            if res and res.get("ok"):
                self.session_id = res["session_id"]
                self.user_info = {
                    "uid": None,
                    "username": username,
                    "role": res["role"],
                    "name": res.get("name", ""),
                    "student_id": res.get("student_id", "")
                }
                self.show_main_view()
            else:
                msg = res.get("msg", "登录失败") if res else "登录失败"
                self.login_view.show_error(msg)
        except Exception as e:
            self.login_view.show_error(f"连接异常：{e}")

    def _handle_register(self, form_data):
        """处理注册按钮点击"""
        if self.sock is None:
            self.login_view.show_error("服务未连接")
            return

        try:
            data = json.dumps(form_data).encode("utf-8")
            self.sock.sendall(bytes([CMD_REGISTER]) + len(data).to_bytes(4, byteorder="big") + data)

            res = self._recv_json()
            if res and res.get("ok"):
                self.login_view.show_info("注册成功，请登录")
            else:
                msg = res.get("msg", "注册失败") if res else "注册失败"
                self.login_view.show_error(msg)
        except Exception as e:
            self.login_view.show_error(f"连接异常：{e}")

    # ========== 通信：业务命令（自动带session） ==========
    def send_command(self, cmd_byte, extra=None):
        """发送业务命令，自动带 session_id"""
        with self._socket_lock:
            return self._send_command_locked(cmd_byte, extra)

    def _send_command_locked(self, cmd_byte, extra=None):
        sock = self.sock
        if sock is None or self.session_id is None:
            return {"ok": False, "msg": "未登录"}

        try:
            sid_bytes = self.session_id.encode("utf-8")
            request = bytes([cmd_byte, len(sid_bytes)]) + sid_bytes
            if extra:
                request += extra
            sock.sendall(request)

            res = self._recv_json()
            if res and res.get("need_relogin"):
                msg = res.get("msg", "请重新登录")
                self.after(0, lambda: messagebox.showwarning("登录过期", msg))
                self.after(0, self.show_login)
                return {"ok": False, "msg": "会话失效"}
            return res or {"ok": False}
        except Exception as e:
            print(f"命令发送异常: {e}")
            return {"ok": False, "msg": str(e)}

    def send_command_async(self, cmd_byte, extra=None):
        """Run a command without waiting in Tk's event loop."""
        threading.Thread(
            target=self.send_command,
            args=(cmd_byte, extra),
            name="socket-command",
            daemon=True,
        ).start()

    def send_image_frame(self, mode, frame):
        """发送图像帧（不需要session，开始测试时已校验）"""
        sock = self.sock
        if sock is None:
            return None

        try:
            success, buf = cv2.imencode(".jpg", frame)
            if not success:
                return None
            img_bytes = buf.tobytes()
            with self._socket_lock:
                sock.sendall(bytes([mode]) + len(img_bytes).to_bytes(4, byteorder="big") + img_bytes)
                return self._recv_json()
        except Exception as e:
            print(f"图像发送异常: {e}")
            return None

    def _recv_json(self, timeout=5.0):
        """接收一行JSON，带超时"""
        self.sock.settimeout(timeout)
        raw = bytearray()
        try:
            while True:
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                newline = chunk.find(b"\n")
                if newline >= 0:
                    raw.extend(chunk[:newline])
                    break
                raw.extend(chunk)
        except socket.timeout:
            print("⚠️ 接收响应超时")
            return None
        finally:
            self.sock.settimeout(None)
        if raw:
            return json.loads(raw.decode("utf-8"))
        return None

    # ========== 关闭 ==========
    def on_close(self):
        # 后台线程是daemon=True，主窗口关闭自动结束
        self.destroy()


if __name__ == "__main__":
    app = MainApp()
    app.mainloop()
