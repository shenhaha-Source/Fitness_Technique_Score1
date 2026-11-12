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

# 导入视图
from login_view import LoginView
from student_view import StudentView
from teacher_view import TeacherView
from star_bg import StarBackground

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


def get_resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AI动作测评系统")
        self.geometry("720x600")
        self.resizable(True, True)
        self.configure(bg=BG_COLOR)

        self.server_proc = None
        self.sock = None
        self.session_id = None
        self.user_info = None
        self.current_view = None

        # 启动后端
        self.start_backend()
        self.after(800, self.connect_server)

        # 全局星空背景（常驻底层，不随页面销毁）
        self.star_bg = StarBackground(self, star_count=100, mode="full")
        self.star_bg.place(x=0, y=0, relwidth=1, relheight=1)
        self.star_bg.animate()

        # 主容器（放在星空之上）
        self.container = tk.Frame(self, bg=BG_COLOR)
        self.container.place(x=0, y=0, relwidth=1, relheight=1)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ========== 后端进程管理 ==========
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
        # 切换为完整星空模式
        self.star_bg.set_mode("full")

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
            # 教师页切换为稀疏星光模式
            self.star_bg.set_mode("sparse")
            self.current_view = TeacherView(
                self.container,
                send_command=self.send_command,
                user_info=self.user_info,
                on_logout=self.logout
            )
        else:
            # 学生页保持完整星空
            self.star_bg.set_mode("full")
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
            self.sock.sendall(bytes([CMD_LOGIN]))
            self.sock.sendall(len(data).to_bytes(4, byteorder="big"))
            self.sock.sendall(data)

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
            self.sock.sendall(bytes([CMD_REGISTER]))
            self.sock.sendall(len(data).to_bytes(4, byteorder="big"))
            self.sock.sendall(data)

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
        sock = self.sock
        if sock is None or self.session_id is None:
            return {"ok": False, "msg": "未登录"}

        try:
            sock.sendall(bytes([cmd_byte]))
            sid_bytes = self.session_id.encode("utf-8")
            sock.sendall(bytes([len(sid_bytes)]))
            sock.sendall(sid_bytes)
            if extra:
                sock.sendall(extra)

            res = self._recv_json()
            if res and res.get("need_relogin"):
                messagebox.showwarning("登录过期", res.get("msg", "请重新登录"))
                self.show_login()
                return {"ok": False, "msg": "会话失效"}
            return res or {"ok": False}
        except Exception as e:
            print(f"命令发送异常: {e}")
            return {"ok": False, "msg": str(e)}

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
            sock.sendall(bytes([mode]))
            sock.sendall(len(img_bytes).to_bytes(4, byteorder="big"))
            sock.sendall(img_bytes)
            return self._recv_json()
        except Exception as e:
            print(f"图像发送异常: {e}")
            return None

    def _recv_json(self):
        """接收一行JSON"""
        raw = b""
        while True:
            c = self.sock.recv(1)
            if c == b"\n" or not c:
                break
            raw += c
        if raw:
            return json.loads(raw.decode("utf-8"))
        return None

    # ========== 关闭 ==========
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


if __name__ == "__main__":
    app = MainApp()
    app.mainloop()
