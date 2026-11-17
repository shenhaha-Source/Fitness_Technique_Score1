"""
登录/注册页面
============
深色科技风格，两个按钮切换登录/注册。
"""
import tkinter as tk
from PIL import Image, ImageTk  # 🌟 导入 PIL 库处理图片
# 配色
BG_COLOR = "#0B1020"
CARD_BG = "#131A33"
CARD_HOVER = "#1E293B"
PRIMARY = "#22D3EE"
ACCENT = "#A78BFA"
TEXT_MAIN = "#E5E7EB"
TEXT_SUB = "#9CA3AF"
DANGER = "#F87171"
SUCCESS = "#4ADE80"
INPUT_BG = "#1E293B"
class LoginView(tk.Frame):
    """
    登录/注册视图。
    """
    def __init__(self, parent, on_login, on_register):
        super().__init__(parent, bg=BG_COLOR)
        self.on_login = on_login
        self.on_register = on_register
        self.current_tab = "login"
        # 关键保险：防止图片被垃圾回收
        self.bg_photo = None 
        self.original_image = None # 保存原图，用于后续缩放
        # 1. 创建一个铺满整个 Frame 的画布 (Canvas)
        self.canvas = tk.Canvas(self, highlightthickness=0, bg=BG_COLOR)
        self.canvas.pack(fill="both", expand=True)
        # 2. 加载原图（此时不缩放，只加载）
        try:
            self.original_image = Image.open("bg_log.jpg")
        except Exception as e:
            print(f"⚠️ 背景图片加载失败，请检查图片路径或名称: {e}")
        # 3. 绑定窗口大小变化事件（核心魔法：只要窗口动了，就触发 self._on_resize）
        self.canvas.bind("<Configure>", self._on_resize)
        # 4. 登录卡片 (父容器是 self.canvas)
        self.card = tk.Frame(self.canvas, bg=CARD_BG, padx=35, pady=30)
        # 5. 使用 place 布局，强制让卡片在画布的绝对正中心
        self.card.place(relx=0.5, rely=0.5, anchor="center")
        # ==================== 以下为原有的界面控件代码 ====================
        # 标题
        tk.Label(
            self.card, text="体测评分系统",
            font=("微软雅黑", 20, "bold"), fg=PRIMARY, bg=CARD_BG
        ).pack(pady=(0, 5))
        tk.Label(
            self.card, text="基于 MediaPipe 的姿态识别测评",
            font=("微软雅黑", 9), fg=TEXT_SUB, bg=CARD_BG
        ).pack(pady=(0, 20))
        # 登录/注册切换按钮
        tab_frame = tk.Frame(self.card, bg=CARD_BG)
        tab_frame.pack(fill="x", pady=(0, 20))
        self.btn_login = tk.Button(
            tab_frame, text="登录", command=self.show_login,
            font=("微软雅黑", 10, "bold"),
            bg=PRIMARY, fg="#0B1020", relief=tk.FLAT, cursor="hand2",
            bd=0, padx=10, pady=6
        )
        self.btn_login.pack(side=tk.LEFT, fill="x", expand=True, padx=(0, 4))
        self.btn_register = tk.Button(
            tab_frame, text="注册", command=self.show_register,
            font=("微软雅黑", 10),
            bg=CARD_HOVER, fg=TEXT_SUB, relief=tk.FLAT, cursor="hand2",
            bd=0, padx=10, pady=6
        )
        self.btn_register.pack(side=tk.LEFT, fill="x", expand=True, padx=(4, 0))
        # 登录表单
        self.login_frame = tk.Frame(self.card, bg=CARD_BG)
        self._build_login_form()
        # 注册表单
        self.register_frame = tk.Frame(self.card, bg=CARD_BG)
        self._build_register_form()
        # 默认显示登录
        self.show_login()
    def _on_resize(self, event):
        """当窗口大小改变时，自动重新绘制背景图"""
        if not self.original_image:
            return
        # 获取当前画布的新宽高
        new_w = event.width
        new_h = event.height
        # 如果窗口太小（比如初始化时），不处理，防止图片缩成 1x1 像素
        if new_w < 100 or new_h < 100:
            return
        # --- 核心算法：等比例缩放并裁剪（Cover 模式） ---
        img_w, img_h = self.original_image.size
        # 计算需要放大的比例（取宽和高比例中较大的一个，保证图片能铺满）
        ratio = max(new_w / img_w, new_h / img_h)
        # 按比例缩放图片
        new_img_w = int(img_w * ratio)
        new_img_h = int(img_h * ratio)
        resized_image = self.original_image.resize((new_img_w, new_img_h), Image.Resampling.LANCZOS)
        # 计算裁剪的左上角坐标（让图片的中心点和画布的中心点对齐）
        # 如果图片比窗口大，多出来的部分就会被裁掉
        left = (new_img_w - new_w) // 2
        top = (new_img_h - new_h) // 2
        right = left + new_w
        bottom = top + new_h
        # 裁剪图片以完全适配窗口
        cropped_image = resized_image.crop((left, top, right, bottom))
        # 转换为 Tkinter 格式并更新画布
        self.bg_photo = ImageTk.PhotoImage(cropped_image)
        # 清除旧的图片，重新画新的（必须清理，否则会重叠）
        self.canvas.delete("bg")
        self.canvas.create_image(0, 0, image=self.bg_photo, anchor="nw", tags="bg")
        # 确保背景图在最底层，不会挡住卡片
        self.canvas.tag_lower("bg")
    # ==================== 以下为原有的方法保持不变 ====================
    def _build_login_form(self):
        """登录表单"""
        tk.Label(self.login_frame, text="用户名", font=("微软雅黑", 10),
                 fg=TEXT_SUB, bg=CARD_BG).pack(anchor="w", pady=(0, 3))
        self.entry_username = tk.Entry(
            self.login_frame, font=("微软雅黑", 11), width=24,
            bg=INPUT_BG, fg=TEXT_MAIN, insertbackground=TEXT_MAIN,
            relief="flat", bd=8
        )
        self.entry_username.pack(pady=(0, 12))

        tk.Label(self.login_frame, text="密码", font=("微软雅黑", 10),
                 fg=TEXT_SUB, bg=CARD_BG).pack(anchor="w", pady=(0, 3))
        self.entry_password = tk.Entry(
            self.login_frame, font=("微软雅黑", 11), width=24, show="*",
            bg=INPUT_BG, fg=TEXT_MAIN, insertbackground=TEXT_MAIN,
            relief="flat", bd=8
        )
        self.entry_password.pack(pady=(0, 18))
        tk.Button(
            self.login_frame, text="登 录", command=self._on_login,
            font=("微软雅黑", 11, "bold"),
            bg=PRIMARY, fg="#0B1020", relief=tk.FLAT, cursor="hand2",
            activebackground="#67E8F9", activeforeground="#0B1020",
            bd=0, padx=10, pady=8
        ).pack(fill="x")
        self.login_error = tk.Label(self.login_frame, text="", font=("微软雅黑", 9),
                                    fg=DANGER, bg=CARD_BG)
        self.login_error.pack(pady=(10, 0))
    def _build_register_form(self):
        """注册表单"""
        tk.Label(self.register_frame, text="用户名", font=("微软雅黑", 10),
                 fg=TEXT_SUB, bg=CARD_BG).pack(anchor="w", pady=(0, 3))
        self.reg_username = tk.Entry(
            self.register_frame, font=("微软雅黑", 11), width=24,
            bg=INPUT_BG, fg=TEXT_MAIN, insertbackground=TEXT_MAIN,
            relief="flat", bd=8
        )
        self.reg_username.pack(pady=(0, 10))
        tk.Label(self.register_frame, text="密码", font=("微软雅黑", 10),
                 fg=TEXT_SUB, bg=CARD_BG).pack(anchor="w", pady=(0, 3))
        self.reg_password = tk.Entry(
            self.register_frame, font=("微软雅黑", 11), width=24, show="*",
            bg=INPUT_BG, fg=TEXT_MAIN, insertbackground=TEXT_MAIN,
            relief="flat", bd=8
        )
        self.reg_password.pack(pady=(0, 10))
        tk.Label(self.register_frame, text="姓名", font=("微软雅黑", 10),
                 fg=TEXT_SUB, bg=CARD_BG).pack(anchor="w", pady=(0, 3))
        self.reg_name = tk.Entry(
            self.register_frame, font=("微软雅黑", 11), width=24,
            bg=INPUT_BG, fg=TEXT_MAIN, insertbackground=TEXT_MAIN,
            relief="flat", bd=8
        )
        self.reg_name.pack(pady=(0, 10))
        tk.Label(self.register_frame, text="学号/工号", font=("微软雅黑", 10),
                 fg=TEXT_SUB, bg=CARD_BG).pack(anchor="w", pady=(0, 3))
        self.reg_sid = tk.Entry(
            self.register_frame, font=("微软雅黑", 11), width=24,
            bg=INPUT_BG, fg=TEXT_MAIN, insertbackground=TEXT_MAIN,
            relief="flat", bd=8
        )
        self.reg_sid.pack(pady=(0, 10))
        # 角色选择
        tk.Label(self.register_frame, text="角色", font=("微软雅黑", 10),
                 fg=TEXT_SUB, bg=CARD_BG).pack(anchor="w", pady=(0, 3))
        role_frame = tk.Frame(self.register_frame, bg=CARD_BG)
        role_frame.pack(pady=(0, 15))
        self.reg_role = tk.StringVar(value="学生")
        tk.Radiobutton(
            role_frame, text="学生", variable=self.reg_role, value="学生",
            font=("微软雅黑", 10), fg=TEXT_MAIN, bg=CARD_BG,
            selectcolor=PRIMARY, activebackground=CARD_BG, activeforeground=PRIMARY
        ).pack(side=tk.LEFT, padx=10)
        tk.Radiobutton(
            role_frame, text="教师", variable=self.reg_role, value="教师",
            font=("微软雅黑", 10), fg=TEXT_MAIN, bg=CARD_BG,
            selectcolor=ACCENT, activebackground=CARD_BG, activeforeground=ACCENT
        ).pack(side=tk.LEFT, padx=10)
        tk.Button(
            self.register_frame, text="注 册", command=self._on_register,
            font=("微软雅黑", 11, "bold"),
            bg=ACCENT, fg="#0B1020", relief=tk.FLAT, cursor="hand2",
            activebackground="#C4B5FD", activeforeground="#0B1020",
            bd=0, padx=10, pady=8
        ).pack(fill="x")

        self.reg_error = tk.Label(self.register_frame, text="", font=("微软雅黑", 9),
                                  fg=DANGER, bg=CARD_BG)
        self.reg_error.pack(pady=(10, 0))
    def show_login(self):
        """切换到登录页"""
        self.current_tab = "login"
        self.register_frame.pack_forget()
        self.login_frame.pack(fill="x")
        self.btn_login.config(bg=PRIMARY, fg="#0B1020", font=("微软雅黑", 10, "bold"))
        self.btn_register.config(bg=CARD_HOVER, fg=TEXT_SUB, font=("微软雅黑", 10))
    def show_register(self):
        """切换到注册页"""
        self.current_tab = "register"
        self.login_frame.pack_forget()
        self.register_frame.pack(fill="x")
        self.btn_register.config(bg=ACCENT, fg="#0B1020", font=("微软雅黑", 10, "bold"))
        self.btn_login.config(bg=CARD_HOVER, fg=TEXT_SUB, font=("微软雅黑", 10))
    def _on_login(self):
        """登录按钮"""
        username = self.entry_username.get().strip()
        password = self.entry_password.get().strip()
        if not username or not password:
            self.login_error.config(text="请输入用户名和密码")
            return
        self.login_error.config(text="")
        self.on_login(username, password)
    def _on_register(self):
        """注册按钮"""
        username = self.reg_username.get().strip()
        password = self.reg_password.get().strip()
        name = self.reg_name.get().strip()
        sid = self.reg_sid.get().strip()
        role_text = self.reg_role.get()

        if not username or not password:
            self.reg_error.config(text="用户名和密码不能为空")
            return
        if not name:
            self.reg_error.config(text="请输入姓名")
            return
        role = "student" if role_text == "学生" else "teacher"
        self.reg_error.config(text="")
        self.on_register({
            "username": username,
            "password": password,
            "name": name,
            "student_id": sid,
            "role": role
        })
    def show_error(self, msg):
        """显示错误"""
        if self.current_tab == "login":
            self.login_error.config(text=msg, fg=DANGER)
        else:
            self.reg_error.config(text=msg, fg=DANGER)              
    def show_info(self, msg):
        """显示成功"""
        self.login_error.config(text="✓ " + msg, fg=SUCCESS)
        self.show_login()