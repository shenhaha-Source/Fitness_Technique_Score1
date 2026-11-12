"""
学生端视图模块（深色星空科技风）
================================
包含学生所有页面：主页、拍手测试、深蹲测试、俯卧撑测试、颜值趣味测评、我的成绩。

布局特点：
- 深色星空背景（由全局 gui.py 提供）
- 纵向通栏长条按钮竖向排列，宽度跟随窗口自适应
- 成绩分行纵向展示
"""

import cv2
import tkinter as tk
from tkinter import messagebox, ttk
from PIL import Image, ImageTk

# 命令码
CMD_START_TEST = 0x81
CMD_STOP_TEST = 0x82
CMD_GET_MY_SCORE = 0x85

# 测试类型
TEST_CLAP = 0
TEST_SQUAT = 1
TEST_FACE = 2
TEST_PUSHUP = 3

# 配色
BG_COLOR = "#0B1020"
CARD_BG = "#131A33"
CARD_HOVER = "#1E293B"
PRIMARY = "#22D3EE"
ACCENT = "#A78BFA"
SUCCESS = "#4ADE80"
TEXT_MAIN = "#E5E7EB"
TEXT_SUB = "#9CA3AF"
DANGER = "#F87171"
BTN_HEIGHT = 46
SIDE_PAD = 30  # 左右边距


class StudentView(tk.Frame):
    """
    学生端主视图容器，管理所有子页面切换。

    Args:
        parent: 父容器
        send_command: 发送业务命令的回调函数
        send_image_frame: 发送图像帧的回调函数
        user_info: 当前登录用户信息
        on_logout: 退出登录回调
    """

    def __init__(self, parent, send_command, send_image_frame, user_info, on_logout):
        super().__init__(parent, bg=BG_COLOR)
        self.send_command = send_command
        self.send_image_frame = send_image_frame
        self.user_info = user_info
        self.on_logout = on_logout

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.container = tk.Frame(self, bg=BG_COLOR)
        self.container.grid(row=0, column=0, sticky="nsew")
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        # 注册所有子页面
        self.pages = {}
        page_classes = [
            HomePage, ClapTestPage, SquatTestPage,
            PushupTestPage, FaceScorePage, MyScorePage
        ]
        for Page in page_classes:
            page = Page(self.container, self)
            self.pages[Page] = page
            page.grid(row=0, column=0, sticky="nsew")

        self.show_page(HomePage)

    def show_page(self, page_class):
        """切换到指定页面"""
        self.pages[page_class].tkraise()
        if page_class == MyScorePage:
            self.pages[page_class].refresh()


# ---------------------- 学生主页 ----------------------
class HomePage(tk.Frame):
    """学生主页，纵向通栏长条按钮布局，宽度自适应"""

    def __init__(self, parent, sv: StudentView):
        super().__init__(parent, bg=BG_COLOR)
        self.sv = sv

        # 头部通栏卡片
        header = tk.Frame(self, bg=CARD_BG, height=50)
        header.pack(fill="x", pady=(20, 10), padx=SIDE_PAD)

        tk.Label(
            header, text=f"👋 {sv.user_info['name']} 同学",
            font=("微软雅黑", 14, "bold"), fg=TEXT_MAIN, bg=CARD_BG
        ).pack(side=tk.LEFT, padx=15)

        tk.Button(
            header, text="退出登录", command=sv.on_logout,
            font=("微软雅黑", 10), bg=DANGER, fg="white", relief=tk.FLAT,
            cursor="hand2", bd=0, padx=12, pady=4
        ).pack(side=tk.RIGHT, padx=10)

        tk.Label(
            header, text=f"学号：{sv.user_info.get('student_id', '-')}",
            font=("微软雅黑", 10), fg=TEXT_SUB, bg=CARD_BG
        ).pack(side=tk.RIGHT, padx=10)

        # 标题
        tk.Label(
            self, text="AI动作测评",
            font=("微软雅黑", 24, "bold"), fg=PRIMARY, bg=BG_COLOR
        ).pack(pady=(10, 15))

        # 测评按钮组（纵向通栏长条，宽度自适应）
        btn_info = [
            ("🏃 深蹲计数", lambda: sv.show_page(SquatTestPage), PRIMARY),
            ("👏 拍手计数", lambda: sv.show_page(ClapTestPage), PRIMARY),
            ("💪 俯卧撑计数", lambda: sv.show_page(PushupTestPage), PRIMARY),
            ("✨ 颜值趣味测评", lambda: sv.show_page(FaceScorePage), ACCENT),
            ("📊 我的成绩", lambda: sv.show_page(MyScorePage), SUCCESS),
        ]

        for text, cmd, color in btn_info:
            btn = tk.Button(
                self, text=text, command=cmd,
                font=("微软雅黑", 13, "bold"),
                height=2, bg=color, fg="#0B1020", relief=tk.FLAT,
                cursor="hand2", activebackground=CARD_HOVER, activeforeground=TEXT_MAIN,
                bd=0, padx=10, pady=6
            )
            btn.pack(fill="x", pady=6, padx=SIDE_PAD)


# ---------------------- 通用测试页基类 ----------------------
class BaseTestPage(tk.Frame):
    """
    测试页基类，封装通用的摄像头、开始/停止、画面渲染逻辑。
    """

    def __init__(self, parent, sv: StudentView, title: str, color: str, test_type: int, image_mode: int):
        super().__init__(parent, bg=BG_COLOR)
        self.sv = sv
        self.test_type = test_type
        self.image_mode = image_mode
        self.is_running = False
        self.cap = None
        self.imgtk = None

        # 顶部导航
        top = tk.Frame(self, bg=CARD_BG, height=50)
        top.pack(fill="x", pady=(15, 10), padx=SIDE_PAD)

        tk.Button(
            top, text="← 返回", command=self.stop_and_back,
            font=("微软雅黑", 11), bg=TEXT_SUB, fg="white", relief=tk.FLAT,
            cursor="hand2", bd=0, padx=12, pady=4
        ).pack(side=tk.LEFT, padx=10)

        tk.Label(
            top, text=title, font=("微软雅黑", 15, "bold"), fg=TEXT_MAIN, bg=CARD_BG
        ).pack(side=tk.LEFT, padx=30)

        # 摄像头预览卡片（宽度自适应，高度固定）
        cam_card = tk.Frame(self, bg=CARD_BG, height=360)
        cam_card.pack(fill="x", pady=(10, 10), padx=SIDE_PAD)
        cam_card.pack_propagate(False)  # 固定高度，不让内容撑大

        self.img_label = tk.Label(cam_card, bg=CARD_BG, text="摄像头预览", fg=TEXT_SUB)
        self.img_label.pack(fill="both", expand=True, padx=10, pady=10)

        # 状态信息
        self.info = tk.Label(
            self, text="准备就绪", font=("微软雅黑", 14, "bold"),
            fg=color, bg=BG_COLOR
        )
        self.info.pack(pady=(5, 10))

        # 控制按钮区（两个并排，宽度自适应）
        ctrl = tk.Frame(self, bg=BG_COLOR)
        ctrl.pack(fill="x", pady=(5, 15), padx=SIDE_PAD)
        ctrl.grid_columnconfigure(0, weight=1)
        ctrl.grid_columnconfigure(1, weight=1)

        tk.Button(
            ctrl, text="开始测试", command=self.start,
            font=("微软雅黑", 12, "bold"), height=2,
            bg=color, fg="#0B1020", relief=tk.FLAT, cursor="hand2",
            activebackground=CARD_HOVER, activeforeground=TEXT_MAIN, bd=0, padx=10, pady=6
        ).grid(row=0, column=0, sticky="ew", padx=(0, 5))

        tk.Button(
            ctrl, text="停止测试", command=self.stop,
            font=("微软雅黑", 12, "bold"), height=2,
            bg=DANGER, fg="white", relief=tk.FLAT, cursor="hand2",
            activebackground=CARD_HOVER, activeforeground=TEXT_MAIN, bd=0, padx=10, pady=6
        ).grid(row=0, column=1, sticky="ew", padx=(5, 0))

    def stop_and_back(self):
        """停止测试并返回主页"""
        self.stop()
        self.sv.show_page(HomePage)

    def start(self):
        """开始测试"""
        if self.is_running:
            return
        res = self.sv.send_command(CMD_START_TEST, extra=bytes([self.test_type]))
        if not res.get("ok"):
            messagebox.showerror("错误", res.get("msg", "启动失败"))
            return

        # 打开摄像头
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            messagebox.showerror("错误", "摄像头打开失败")
            return

        self.is_running = True
        self.on_start()
        self.update_frame()

    def stop(self):
        """停止测试"""
        self.is_running = False
        if self.cap:
            self.cap.release()
            self.cap = None
        self.sv.send_command(CMD_STOP_TEST)
        self.on_stop()

    def on_start(self):
        """子类可重写：开始测试时的初始化"""
        pass

    def on_stop(self):
        """子类可重写：停止测试后的处理"""
        pass

    def update_frame(self):
        """逐帧更新画面，保持视频原始比例不变形"""
        if not self.is_running:
            return
        ret, frame = self.cap.read()
        if not ret:
            self.stop()
            return
        res = self.sv.send_image_frame(self.image_mode, frame)
        if res is None:
            self.stop()
            return

        self.on_frame_result(res, frame)

        # 等比例缩放显示，不拉伸变形
        w, h = self.img_label.winfo_width(), self.img_label.winfo_height()
        if w > 10 and h > 10:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            # 计算等比例缩放尺寸
            img_ratio = img.width / img.height
            label_ratio = w / h
            if img_ratio > label_ratio:
                # 图片更宽，按宽度适配
                new_w = w
                new_h = int(w / img_ratio)
            else:
                # 图片更高，按高度适配
                new_h = h
                new_w = int(h * img_ratio)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            self.imgtk = ImageTk.PhotoImage(img)
            self.img_label.config(image=self.imgtk, text="")
        self.after(15, self.update_frame)

    def on_frame_result(self, res: dict, frame):
        """子类可重写：处理后端返回的帧结果"""
        pass


# ---------------------- 拍手测试 ----------------------
class ClapTestPage(BaseTestPage):
    """拍手计数测试页"""

    def __init__(self, parent, sv: StudentView):
        super().__init__(parent, sv, "👏 拍手计数测试", PRIMARY, TEST_CLAP, image_mode=0)

    def on_start(self):
        self.info.config(text="拍手总数：0")

    def on_frame_result(self, res: dict, frame):
        tip = res.get("tip", "")
        count = res.get("count", 0)
        self.info.config(text=f"拍手总数：{count}")
        cv2.putText(frame, tip, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)


# ---------------------- 深蹲测试 ----------------------
class SquatTestPage(BaseTestPage):
    """深蹲计数测试页"""

    def __init__(self, parent, sv: StudentView):
        super().__init__(parent, sv, "🏃 深蹲计数测试", PRIMARY, TEST_SQUAT, image_mode=0)

    def on_start(self):
        self.info.config(text="深蹲总数：0")

    def on_frame_result(self, res: dict, frame):
        tip = res.get("tip", "")
        count = res.get("count", 0)
        self.info.config(text=f"深蹲总数：{count}")
        cv2.putText(frame, tip, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)


# ---------------------- 俯卧撑测试 ----------------------
class PushupTestPage(BaseTestPage):
    """俯卧撑计数测试页"""

    def __init__(self, parent, sv: StudentView):
        super().__init__(parent, sv, "💪 俯卧撑计数测试", PRIMARY, TEST_PUSHUP, image_mode=0)

    def on_start(self):
        self.info.config(text="俯卧撑总数：0")

    def on_frame_result(self, res: dict, frame):
        tip = res.get("tip", "")
        count = res.get("count", 0)
        self.info.config(text=f"俯卧撑总数：{count}")
        cv2.putText(frame, tip, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)


# ---------------------- 颜值趣味测评 ----------------------
class FaceScorePage(BaseTestPage):
    """颜值比例趣味测评页（不计入正式成绩）"""

    def __init__(self, parent, sv: StudentView):
        super().__init__(parent, sv, "✨ 颜值比例趣味测评", ACCENT, TEST_FACE, image_mode=1)

    def on_start(self):
        self.info.config(text="颜值分数：计算中...")

    def on_stop(self):
        self.info.config(text="颜值分数：--")

    def on_frame_result(self, res: dict, frame):
        tip = res.get("tip", "")
        score = res.get("score")
        if score is not None:
            self.info.config(text=f"颜值分数：{score:.1f}（趣味，不计入成绩）")
        cv2.putText(frame, tip, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)


# ---------------------- 我的成绩 ----------------------
class MyScorePage(tk.Frame):
    """学生查看自己的三项最优成绩和总分（纵向分行展示）"""

    def __init__(self, parent, sv: StudentView):
        super().__init__(parent, bg=BG_COLOR)
        self.sv = sv

        # 顶部导航
        top = tk.Frame(self, bg=CARD_BG, height=50)
        top.pack(fill="x", pady=(15, 10), padx=SIDE_PAD)

        tk.Button(
            top, text="← 返回", command=lambda: sv.show_page(HomePage),
            font=("微软雅黑", 11), bg=TEXT_SUB, fg="white", relief=tk.FLAT,
            cursor="hand2", bd=0, padx=12, pady=4
        ).pack(side=tk.LEFT, padx=10)

        tk.Label(
            top, text="📊 我的最优成绩", font=("微软雅黑", 15, "bold"),
            fg=TEXT_MAIN, bg=CARD_BG
        ).pack(side=tk.LEFT, padx=30)

        # 成绩卡片容器
        self.score_frame = tk.Frame(self, bg=CARD_BG)
        self.score_frame.pack(fill="x", pady=(10, 10), padx=SIDE_PAD)

    def refresh(self):
        """从后端拉取我的成绩，纵向分行展示"""
        for w in self.score_frame.winfo_children():
            w.destroy()

        # 加载提示
        loading = tk.Label(self.score_frame, text="正在获取成绩...", font=("微软雅黑", 12),
                           fg=TEXT_SUB, bg=CARD_BG)
        loading.pack(pady=40)
        self.update()

        # 请求后端
        res = self.sv.send_command(CMD_GET_MY_SCORE)

        # 清除加载提示
        loading.destroy()

        if not res.get("ok"):
            tk.Label(self.score_frame, text="加载失败", font=("微软雅黑", 14),
                     fg=DANGER, bg=CARD_BG).pack(pady=30)
            return

        score = res.get("score", {})
        squat = score.get("squat", 0)
        clap = score.get("clap", 0)
        pushup = score.get("pushup", 0)
        total = score.get("total", 0)

        # 评价
        if total >= 15:
            eval_text = "优秀"
            eval_color = SUCCESS
        elif total >= 10:
            eval_text = "良好"
            eval_color = PRIMARY
        elif total >= 6:
            eval_text = "及格"
            eval_color = "#FBBF24"
        else:
            eval_text = "待加强"
            eval_color = DANGER

        # 纵向分行展示
        rows = [
            ("深蹲最优次数", f"{squat} 次", PRIMARY),
            ("拍手最优次数", f"{clap} 次", PRIMARY),
            ("俯卧撑最优次数", f"{pushup} 次", PRIMARY),
            ("综合总分", f"{total}", SUCCESS),
            ("综合评价", eval_text, eval_color),
        ]

        for i, (label, value, color) in enumerate(rows):
            row = tk.Frame(self.score_frame, bg=CARD_BG)
            row.pack(fill="x", padx=25, pady=12)

            tk.Label(row, text=label, font=("微软雅黑", 12),
                     fg=TEXT_SUB, bg=CARD_BG).pack(side=tk.LEFT)

            tk.Label(row, text=value, font=("微软雅黑", 16, "bold"),
                     fg=color, bg=CARD_BG).pack(side=tk.RIGHT)

            # 分隔线
            if i < len(rows) - 1:
                tk.Frame(self.score_frame, bg="#1E293B", height=1).pack(fill="x", padx=25)
