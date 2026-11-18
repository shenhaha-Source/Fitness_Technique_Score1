"""
登录/注册页面（深色霓虹 · 分栏品牌布局）
========================================

左侧是品牌展示区（渐变、星光、姿态线框），右侧是登录/注册卡片。
参考方向：深色健身 App 的登录页（大面积深色背景 + 霓虹强调色 +
单卡片表单 + 品牌信息区），没有复制任何第三方素材或代码。
"""

import os
import random
import sys
import tkinter as tk

from PIL import Image, ImageColor, ImageDraw, ImageTk

from ui_widgets import (
    LabeledEntry,
    PillTabs,
    RoleSelector,
    RoundedButton,
    RoundedCard,
    round_rect,
)


# ========== 配色 ==========
BG_LEFT_TOP = "#060A15"
BG_LEFT_BOTTOM = "#0B1630"
BG_RIGHT = "#070C18"
CARD_BG = "#0F1A33"
CARD_EDGE = "#1E2D52"
FIELD_BG = "#0B1428"
FIELD_EDGE = "#1C2A4A"
TEXT_MAIN = "#F4F7FF"
TEXT_SUB = "#9FB0D0"
TEXT_MUTED = "#7E90B8"
ACCENT = "#22D3EE"
ACCENT_2 = "#A78BFA"
DANGER = "#FB7185"
SUCCESS = "#4ADE80"
BTN_TEXT = "#04121F"

FONT = "Microsoft YaHei UI"


def asset_path(name: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, name)


# ========== 左侧品牌面板 ==========
class BrandPanel(tk.Canvas):
    def __init__(self, master):
        super().__init__(master, bg=BG_LEFT_TOP, highlightthickness=0, bd=0)
        self._photo = None
        self._logo_photo = None
        self._stars = []
        self._resize_job = None
        self._anim_job = None
        self.bind("<Configure>", self._on_resize)
        self.after(120, self._redraw)
        self.after(200, self._animate)

    def _on_resize(self, _event):
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(120, self._redraw)

    def _guard(self):
        try:
            return bool(self.winfo_exists())
        except tk.TclError:
            return False

    def _make_background(self, w, h):
        img = Image.new("RGBA", (w, h))
        draw = ImageDraw.Draw(img)
        top = ImageColor.getrgb(BG_LEFT_TOP)
        bottom = ImageColor.getrgb(BG_LEFT_BOTTOM)
        for y in range(h):
            t = y / max(1, h - 1)
            color = tuple(int(top[i] + (bottom[i] - top[i]) * t)
                          for i in range(3))
            draw.line([(0, y), (w, y)], fill=color + (255,))

        # 右上角青色辉光
        glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        cx, cy = int(w * 0.78), int(h * 0.24)
        for r in range(240, 0, -6):
            alpha = int(26 * (1 - r / 240) ** 1.6)
            gd.ellipse([cx - r, cy - r, cx + r, cy + r],
                       fill=(34, 211, 238, alpha))
        img = Image.alpha_composite(img, glow).convert("RGB")
        self._photo = ImageTk.PhotoImage(img)

    def _redraw(self):
        if not self._guard():
            return
        self._resize_job = None
        w, h = self.winfo_width(), self.winfo_height()
        if w < 80 or h < 80:
            return

        self.delete("all")
        self._make_background(w, h)
        self.create_image(0, 0, anchor="nw", image=self._photo, tags="bg")

        # 点阵
        for x in range(18, w, 30):
            for y in range(18, h, 30):
                self.create_oval(x, y, x + 1, y + 1,
                                 fill="#16233D", outline="", tags="deco")

        # 装饰圆环
        cx, cy = int(w * 0.60), int(h * 0.76)
        for r in (70, 100, 130):
            self.create_oval(cx - r, cy - r, cx + r, cy + r,
                             outline="#12233F", width=1, tags="deco")

        self._draw_pose(cx, cy)

        self._init_stars(w, h)
        self._draw_stars()
        self._draw_brand(w, h)

        self.create_text(28, h - 26, anchor="w", text="v0.1  ·  LOCAL ONLY",
                         fill="#3E5175", font=(FONT, 7), tags="ui")

    def _draw_brand(self, w, h):
        logo = self._load_logo(46)
        if logo is not None:
            self._logo_photo = logo
            self.create_image(28, 26, anchor="nw", image=logo, tags="ui")
        else:
            round_rect(self, 28, 26, 74, 72, 12, fill="#0E2B3F",
                       outline=ACCENT, width=1, tags="ui")
            self.create_text(51, 49, text="体", fill=ACCENT,
                             font=(FONT, 16, "bold"), tags="ui")

        self.create_text(28, 92, anchor="nw", text="智慧体测",
                         fill=TEXT_MAIN, font=(FONT, 26, "bold"), tags="ui")
        self.create_text(30, 140, anchor="nw", text="AI FITNESS ASSESSMENT",
                         fill=ACCENT, font=(FONT, 8), tags="ui")

        self.create_line(30, 198, w - 28, 198, fill="#1B2C4C",
                         width=1, tags="ui")

        features = [
            "MediaPipe 33 点姿态识别",
            "深蹲 · 引体 · 俯卧撑",
            "成绩自动归档与导出",
        ]
        y = 216
        for text in features:
            self.create_oval(31, y + 6, 37, y + 12,
                             fill=ACCENT, outline="", tags="ui")
            self.create_text(46, y, anchor="nw", text=text,
                             fill=TEXT_SUB, font=(FONT, 9),
                             width=max(160, w - 66), tags="ui")
            y += 26

        chip_y = 302
        chip_w = (w - 56 - 16) / 3
        labels = ("33 点", "3 动作", "实时")
        for i, label in enumerate(labels):
            x = 28 + i * (chip_w + 8)
            round_rect(self, x, chip_y, x + chip_w, chip_y + 24, 8,
                       fill="#0C1830", outline="#1B2C4C",
                       width=1, tags="ui")
            self.create_text(x + chip_w / 2, chip_y + 12, text=label,
                             fill=TEXT_MUTED, font=(FONT, 7), tags="ui")

    def _load_logo(self, size):
        try:
            img = Image.open(asset_path("app.ico")).convert("RGBA")
            img.thumbnail((size, size), Image.LANCZOS)
            return ImageTk.PhotoImage(img)
        except Exception:
            return None

    def _draw_pose(self, cx, cy):
        head = (cx - 6, cy - 92)
        shoulder = (cx - 6, cy - 77)
        hip = (cx - 18, cy - 25)
        knee = (cx + 28, cy - 5)
        ankle = (cx + 34, cy + 55)
        elbow = (cx + 20, cy - 58)
        wrist = (cx + 44, cy - 66)
        hip2 = (cx - 8, cy - 25)
        knee2 = (cx + 38, cy - 8)
        ankle2 = (cx + 42, cy + 53)

        bones = [
            (shoulder, hip), (hip, knee), (knee, ankle),
            (shoulder, elbow), (elbow, wrist),
            (hip2, knee2), (knee2, ankle2),
        ]
        for a, b in bones:
            self.create_line(a[0], a[1], b[0], b[1],
                             fill="#0B3446", width=8, tags="pose")
        for a, b in bones:
            self.create_line(a[0], a[1], b[0], b[1],
                             fill="#29C7DD", width=3, tags="pose")

        self.create_oval(head[0] - 11, head[1] - 11,
                         head[0] + 11, head[1] + 11,
                         outline=ACCENT, width=2, tags="pose")
        self.create_line(shoulder[0], shoulder[1], head[0], head[1] + 11,
                         fill="#29C7DD", width=3, tags="pose")

        for px, py in (shoulder, hip, knee, ankle, elbow, wrist,
                       hip2, knee2, ankle2):
            self.create_oval(px - 4, py - 4, px + 4, py + 4,
                             fill=ACCENT_2, outline="", tags="pose")

        self.create_arc(knee[0] - 26, knee[1] - 26,
                        knee[0] + 26, knee[1] + 26,
                        start=200, extent=80, style="arc",
                        outline=ACCENT, width=1, dash=(3, 3), tags="pose")
        self.create_text(knee[0] + 18, knee[1] - 24, text="92°",
                         fill=ACCENT, font=(FONT, 8), tags="pose")
        self.create_line(cx - 60, ankle[1] + 14, cx + 80, ankle[1] + 14,
                         fill="#1B3350", width=1, dash=(4, 4), tags="pose")

    def _init_stars(self, w, h):
        self._stars = []
        colors = ["#1D3F5C", "#24516E", "#3A3A6E", "#22D3EE", "#A78BFA"]
        for _ in range(34):
            x = random.randint(8, max(9, w - 8))
            y = random.randint(8, max(9, h - 8))
            size = random.choice((1, 1, 2, 2, 3))
            color = random.choice(colors)
            item = self.create_oval(x, y, x + size, y + size,
                                    fill=color, outline="", tags="star")
            self._stars.append({
                "id": item, "x": x, "y": y, "size": size,
                "vx": random.uniform(-0.15, 0.15),
                "vy": random.uniform(-0.10, 0.10),
            })

    def _draw_stars(self):
        for s in self._stars:
            self.coords(s["id"], s["x"], s["y"],
                        s["x"] + s["size"], s["y"] + s["size"])

    def _animate(self):
        if not self._guard():
            return
        w, h = self.winfo_width(), self.winfo_height()
        if w > 80 and h > 80:
            for s in self._stars:
                s["x"] += s["vx"]
                s["y"] += s["vy"]
                if s["x"] < -4:
                    s["x"] = w + 4
                elif s["x"] > w + 4:
                    s["x"] = -4
                if s["y"] < -4:
                    s["y"] = h + 4
                elif s["y"] > h + 4:
                    s["y"] = -4
            self._draw_stars()
        self._anim_job = self.after(90, self._animate)


# ========== 登录页 ==========
class LoginView(tk.Frame):
    def __init__(self, parent, on_login, on_register):
        super().__init__(parent, bg=BG_RIGHT)
        self.on_login = on_login
        self.on_register = on_register
        self.current_tab = "login"
        self._last_username = ""
        self._last_registered_username = ""
        self._pending_error = None
        self._busy = False
        self.submit_btn = None
        self.error_label = None
        self.username_field = None
        self.password_field = None

        # 用 place 固定 40% / 60% 分栏，避免 Canvas 的默认请求宽度把右栏挤窄
        self.brand = BrandPanel(self)
        self.brand.place(x=0, y=0, relwidth=0.40, relheight=1.0)

        self.right = tk.Frame(self, bg=BG_RIGHT)
        self.right.place(relx=0.40, y=0, relwidth=0.60, relheight=1.0)

        tk.Frame(self.right, bg="#15213C", width=1).place(
            x=0, y=0, relheight=1.0)

        self.card = RoundedCard(
            self.right, 380, 470,
            bg=BG_RIGHT, card=CARD_BG, edge=CARD_EDGE, radius=20,
        )
        self.card.place(relx=0.5, rely=0.5, anchor="center")

        self._render()

    # ---- 公共接口 ----
    def show_error(self, msg: str):
        self._pending_error = msg
        self._set_busy(False)
        if self.error_label is not None:
            try:
                if self.error_label.winfo_exists():
                    self.error_label.config(text=msg, fg=DANGER)
            except tk.TclError:
                pass

    def show_info(self, msg: str):
        self._pending_error = None
        if self._last_registered_username:
            self._last_username = self._last_registered_username
        self.current_tab = "login"
        self._render()
        if self.error_label is not None:
            try:
                self.error_label.config(text="✓ " + msg, fg=SUCCESS)
            except tk.TclError:
                pass

    def show_login(self):
        self._switch_tab(0)

    def show_register(self):
        self._switch_tab(1)

    # ---- 渲染 ----
    def _clear_body(self):
        for child in self.card.body.winfo_children():
            child.destroy()

    def _render(self):
        self._clear_body()
        self.card.set_size(380, 500 if self.current_tab == "login" else 610)
        content = tk.Frame(self.card.body, bg=CARD_BG)
        content.pack(fill="both", expand=True, padx=24, pady=20)

        tk.Label(content, text="SECURE ACCESS",
                 font=(FONT, 7), fg=ACCENT, bg=CARD_BG,
                 anchor="w").pack(fill="x", pady=(0, 4))

        title = "欢迎回来" if self.current_tab == "login" else "创建账号"
        subtitle = ("登录后开始今天的体测" if self.current_tab == "login"
                    else "填写信息，加入体测系统")
        tk.Label(content, text=title, font=(FONT, 20, "bold"),
                 fg=TEXT_MAIN, bg=CARD_BG, anchor="w").pack(fill="x")
        tk.Label(content, text=subtitle, font=(FONT, 9),
                 fg=TEXT_SUB, bg=CARD_BG, anchor="w").pack(
            fill="x", pady=(2, 8))

        tabs = PillTabs(
            content, ("登录", "注册"), self._switch_tab,
            width=292, height=36, bg=CARD_BG, track=FIELD_BG,
            active=ACCENT, active_fg=BTN_TEXT, inactive_fg=TEXT_MUTED,
            font=(FONT, 9, "bold"),
        )
        tabs.pack(fill="x", pady=(0, 10))
        tabs.set_active(0 if self.current_tab == "login" else 1)

        if self.current_tab == "login":
            self._build_login(content)
        else:
            self._build_register(content)

        if self._pending_error:
            self.error_label.config(text=self._pending_error, fg=DANGER)

        self.after(120, self._focus_current)

    def _build_login(self, parent):
        self.username_field = LabeledEntry(
            parent, "用户名", bg=CARD_BG, field=FIELD_BG, edge=FIELD_EDGE,
            text=TEXT_MAIN, muted=TEXT_MUTED, accent=ACCENT,
            font=(FONT, 10), icon="user",
        )
        self.username_field.pack(fill="x", pady=(0, 8))
        if self._last_username:
            self.username_field.set(self._last_username)

        self.password_field = LabeledEntry(
            parent, "密码", bg=CARD_BG, field=FIELD_BG, edge=FIELD_EDGE,
            text=TEXT_MAIN, muted=TEXT_MUTED, accent=ACCENT,
            font=(FONT, 10), icon="lock", show="*",
        )
        self.password_field.pack(fill="x", pady=(0, 2))

        self.error_label = tk.Label(
            parent, text="", font=(FONT, 8), fg=DANGER, bg=CARD_BG,
            anchor="w", height=2,
        )
        self.error_label.pack(fill="x", pady=(4, 2))

        self.submit_btn = RoundedButton(
            parent, "登 录", self._on_login, width=292, height=42,
            radius=0, bg=CARD_BG, fill=ACCENT, fg=BTN_TEXT,
            font=(FONT, 11, "bold"),
        )
        self.submit_btn.pack(fill="x")

        footer = tk.Frame(parent, bg=CARD_BG)
        footer.pack(fill="x", pady=(12, 0))
        tk.Label(footer, text="还没有账号？", font=(FONT, 8),
                 fg=TEXT_MUTED, bg=CARD_BG).pack(side=tk.LEFT)
        link = tk.Label(footer, text="立即注册", font=(FONT, 8, "bold"),
                        fg=ACCENT, bg=CARD_BG, cursor="hand2")
        link.pack(side=tk.LEFT, padx=(4, 0))
        link.bind("<Button-1>", lambda _e: self._switch_tab(1))

        self.username_field.bind_return(self._on_login)
        self.password_field.bind_return(self._on_login)

    def _build_register(self, parent):
        self.reg_username_field = LabeledEntry(
            parent, "用户名", bg=CARD_BG, field=FIELD_BG, edge=FIELD_EDGE,
            text=TEXT_MAIN, muted=TEXT_MUTED, accent=ACCENT,
            font=(FONT, 10), icon="user",
        )
        self.reg_username_field.pack(fill="x", pady=(0, 6))

        row1 = tk.Frame(parent, bg=CARD_BG)
        row1.pack(fill="x", pady=(0, 6))
        row1.grid_columnconfigure(0, weight=1)
        row1.grid_columnconfigure(1, weight=1)
        self.reg_password_field = LabeledEntry(
            row1, "密码", bg=CARD_BG, field=FIELD_BG, edge=FIELD_EDGE,
            text=TEXT_MAIN, muted=TEXT_MUTED, accent=ACCENT,
            font=(FONT, 10), icon="lock", show="*",
        )
        self.reg_password_field.grid(row=0, column=0, sticky="ew",
                                     padx=(0, 4))
        self.reg_confirm_field = LabeledEntry(
            row1, "确认密码", bg=CARD_BG, field=FIELD_BG, edge=FIELD_EDGE,
            text=TEXT_MAIN, muted=TEXT_MUTED, accent=ACCENT,
            font=(FONT, 10), icon="lock", show="*",
        )
        self.reg_confirm_field.grid(row=0, column=1, sticky="ew",
                                    padx=(4, 0))

        row2 = tk.Frame(parent, bg=CARD_BG)
        row2.pack(fill="x", pady=(0, 6))
        row2.grid_columnconfigure(0, weight=1)
        row2.grid_columnconfigure(1, weight=1)
        self.reg_name_field = LabeledEntry(
            row2, "姓名", bg=CARD_BG, field=FIELD_BG, edge=FIELD_EDGE,
            text=TEXT_MAIN, muted=TEXT_MUTED, accent=ACCENT,
            font=(FONT, 10), icon="user",
        )
        self.reg_name_field.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.reg_sid_field = LabeledEntry(
            row2, "学号 / 工号", bg=CARD_BG, field=FIELD_BG,
            edge=FIELD_EDGE, text=TEXT_MAIN, muted=TEXT_MUTED,
            accent=ACCENT, font=(FONT, 10), icon="id",
        )
        self.reg_sid_field.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        self.role_selector = RoleSelector(
            parent, bg=CARD_BG, field=FIELD_BG, edge=FIELD_EDGE,
            accent=ACCENT, muted=TEXT_MUTED, text=TEXT_MAIN,
        )
        self.role_selector.pack(fill="x", pady=(0, 4))

        self.error_label = tk.Label(
            parent, text="", font=(FONT, 8), fg=DANGER, bg=CARD_BG,
            anchor="w", height=1,
        )
        self.error_label.pack(fill="x", pady=(2, 0))

        self.submit_btn = RoundedButton(
            parent, "注 册", self._on_register, width=292, height=42,
            radius=0, bg=CARD_BG, fill=ACCENT_2, fg=BTN_TEXT,
            font=(FONT, 11, "bold"),
        )
        self.submit_btn.pack(fill="x")

        footer = tk.Frame(parent, bg=CARD_BG)
        footer.pack(fill="x", pady=(8, 0))
        tk.Label(footer, text="已有账号？", font=(FONT, 8),
                 fg=TEXT_MUTED, bg=CARD_BG).pack(side=tk.LEFT)
        link = tk.Label(footer, text="返回登录", font=(FONT, 8, "bold"),
                        fg=ACCENT, bg=CARD_BG, cursor="hand2")
        link.pack(side=tk.LEFT, padx=(4, 0))
        link.bind("<Button-1>", lambda _e: self._switch_tab(0))

        for field in (self.reg_username_field, self.reg_password_field,
                      self.reg_confirm_field, self.reg_name_field,
                      self.reg_sid_field):
            field.bind_return(self._on_register)

    def _focus_current(self):
        field = (self.username_field if self.current_tab == "login"
                 else getattr(self, "reg_username_field", None))
        if field is not None:
            try:
                field.focus()
            except tk.TclError:
                pass

    # ---- 切页 ----
    def _switch_tab(self, index: int):
        if self.current_tab == "login" and self.username_field is not None:
            self._last_username = self.username_field.get()
        elif self.current_tab == "register":
            self._last_username = self.reg_username_field.get()
        self._pending_error = None
        self.current_tab = "login" if index == 0 else "register"
        self._render()

    # ---- 提交 ----
    def _set_busy(self, busy: bool, action: str = ""):
        self._busy = busy
        if self.submit_btn is None:
            return
        try:
            if busy:
                self.submit_btn.set_loading(
                    True, "登录中..." if action == "login" else "注册中...")
            else:
                self.submit_btn.set_loading(False)
            self.update_idletasks()
        except tk.TclError:
            pass

    def _on_login(self):
        if self._busy:
            return
        username = self.username_field.get()
        password = self.password_field.get()
        if not username or not password:
            self.show_error("请输入用户名和密码")
            return
        self._last_username = username
        self._set_busy(True, "login")
        try:
            self.on_login(username, password)
        finally:
            try:
                if self.winfo_exists():
                    self._set_busy(False)
            except tk.TclError:
                pass

    def _on_register(self):
        if self._busy:
            return
        username = self.reg_username_field.get()
        password = self.reg_password_field.get()
        confirm = self.reg_confirm_field.get()
        name = self.reg_name_field.get()
        sid = self.reg_sid_field.get()
        role_text = self.role_selector.var.get()

        if not username or not password:
            self.show_error("用户名和密码不能为空")
            return
        if password != confirm:
            self.show_error("两次输入的密码不一致")
            return
        if not name:
            self.show_error("请输入姓名")
            return

        self._last_registered_username = username
        role = "student" if role_text == "学生" else "teacher"
        self._set_busy(True, "register")
        try:
            self.on_register({
                "username": username,
                "password": password,
                "name": name,
                "student_id": sid,
                "role": role,
            })
        finally:
            try:
                if self.winfo_exists():
                    self._set_busy(False)
            except tk.TclError:
                pass
