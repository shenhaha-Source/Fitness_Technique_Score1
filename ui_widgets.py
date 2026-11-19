"""
登录界面用的轻量 UI 组件
========================

Tkinter 原生控件做不出圆角、悬停和焦点高亮，这里用 Canvas 画。
只服务登录页，不依赖项目其它模块。
"""

import tkinter as tk


# ========== 颜色工具 ==========
def _to_rgb(color: str):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def _to_hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(v))) for v in rgb)


def mix(color_a: str, color_b: str, t: float) -> str:
    """在两个颜色之间线性插值，t=0 返回 a，t=1 返回 b。"""
    a, b = _to_rgb(color_a), _to_rgb(color_b)
    return _to_hex(tuple(a[i] + (b[i] - a[i]) * t for i in range(3)))


def lighten(color: str, t: float) -> str:
    return mix(color, "#FFFFFF", t)


def darken(color: str, t: float) -> str:
    return mix(color, "#000000", t)


# ========== 圆角矩形 ==========
def round_rect(canvas: tk.Canvas, x1, y1, x2, y2, r, **kwargs):
    """在 Canvas 上画一个圆角矩形，返回 item id。"""
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1 + r,
        x2, y2 - r, x2 - r, y2, x1 + r, y2,
        x1, y2 - r, x1, y1 + r,
    ]
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)


# ========== 圆角按钮 ==========
class RoundedButton(tk.Canvas):
    def __init__(
        self,
        master,
        text,
        command=None,
        width=360,
        height=46,
        radius=12,
        bg="#0F1A33",
        fill="#22D3EE",
        fg="#04121F",
        hover_fill=None,
        press_fill=None,
        disabled_fill="#1E2B4D",
        disabled_fg="#6B7A99",
        outline=None,
        font=("Microsoft YaHei UI", 12, "bold"),
    ):
        super().__init__(
            master, width=width, height=height, bg=bg,
            highlightthickness=0, bd=0, cursor="hand2",
        )
        self.w = width
        self.h = height
        self.r = radius
        self.text = text
        self._base_text = text
        self.command = command
        self.fill = fill
        self.fg = fg
        self.hover_fill = hover_fill or lighten(fill, 0.14)
        self.press_fill = press_fill or darken(fill, 0.10)
        self.disabled_fill = disabled_fill
        self.disabled_fg = disabled_fg
        self.outline = outline
        self.font = font
        self.enabled = True
        self.hovered = False
        self.pressed = False

        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self._draw()

    def _current_fill(self):
        if not self.enabled:
            return self.disabled_fill
        if self.pressed:
            return self.press_fill
        if self.hovered:
            return self.hover_fill
        return self.fill

    def _draw(self):
        self.delete("all")
        fill = self._current_fill()
        outline = self.outline if self.enabled and self.outline else fill
        if self.r <= 0:
            # 方角按钮：和方形登录/注册切换框保持一致
            self.create_rectangle(1, 1, self.w - 1, self.h - 1,
                                  fill=fill, outline=outline, width=1)
        else:
            round_rect(self, 1, 1, self.w - 1, self.h - 1, self.r,
                       fill=fill, outline=outline, width=1)
        self.create_text(
            self.w / 2, self.h / 2 + 1, text=self.text,
            fill=self.fg if self.enabled else self.disabled_fg,
            font=self.font,
        )

    def _on_enter(self, _event):
        self.hovered = True
        self._draw()

    def _on_leave(self, _event):
        self.hovered = False
        self.pressed = False
        self._draw()

    def _on_press(self, _event):
        if self.enabled:
            self.pressed = True
            self._draw()

    def _on_release(self, event):
        if not self.enabled:
            return
        inside = 0 <= event.x <= self.w and 0 <= event.y <= self.h
        self.pressed = False
        self.hovered = inside
        self._draw()
        if inside and self.command:
            self.command()

    def set_enabled(self, enabled: bool):
        self.enabled = bool(enabled)
        self.config(cursor="hand2" if enabled else "")
        self._draw()

    def set_text(self, text: str):
        self.text = text
        self._draw()

    def set_loading(self, loading: bool, text: str = "处理中..."):
        self.set_enabled(not loading)
        self.set_text(text if loading else self._base_text)

    def set_base_text(self, text: str):
        self._base_text = text
        self.set_text(text)

    _base_text = ""


# ========== 方形分段标签（登录 / 注册，各占一半） ==========
class PillTabs(tk.Canvas):
    def __init__(
        self,
        master,
        tabs,
        command,
        width=360,
        height=40,
        bg="#0F1A33",
        track="#0B1428",
        active="#22D3EE",
        active_fg="#04121F",
        inactive_fg="#8A9AC0",
        font=("Microsoft YaHei UI", 10, "bold"),
    ):
        super().__init__(master, width=width, height=height, bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.w, self.h = width, height
        self.tabs = list(tabs)
        self.command = command
        self.track = track
        self.active = active
        self.active_fg = active_fg
        self.inactive_fg = inactive_fg
        self.font = font
        self.index = 0
        self.bind("<Button-1>", self._on_click)
        self._draw()

    def _draw(self):
        self.delete("all")
        # 方形底框
        self.create_rectangle(1, 1, self.w - 1, self.h - 1,
                              fill=self.track, outline="")
        seg = (self.w - 2) / len(self.tabs)
        x1 = 1 + self.index * seg
        # 当前选中的一半，方形填满
        self.create_rectangle(x1, 1, x1 + seg, self.h - 1,
                              fill=self.active, outline="")
        # 外边框画在填充之上
        self.create_rectangle(1, 1, self.w - 1, self.h - 1,
                              fill="", outline=lighten(self.track, 0.18),
                              width=1)
        for i, tab in enumerate(self.tabs):
            self.create_text(
                1 + seg * (i + 0.5), self.h / 2,
                text=tab,
                fill=self.active_fg if i == self.index else self.inactive_fg,
                font=self.font,
            )

    def _on_click(self, event):
        seg = (self.w - 2) / len(self.tabs)
        index = int(max(0, min(len(self.tabs) - 1, (event.x - 1) // seg)))
        if index != self.index:
            self.index = index
            self._draw()
            if self.command:
                self.command(index)

    def set_active(self, index: int):
        index = max(0, min(len(self.tabs) - 1, index))
        if index != self.index:
            self.index = index
            self._draw()


# ========== 表单图标 ==========
def draw_icon(canvas: tk.Canvas, kind: str, color: str):
    canvas.delete("all")
    cx, cy = 12, 18
    if kind == "user":
        canvas.create_oval(cx - 5, cy - 9, cx + 5, cy + 1, outline=color, width=2)
        canvas.create_arc(cx - 9, cy + 1, cx + 9, cy + 15, start=0, extent=180,
                          style="arc", outline=color, width=2)
    elif kind == "lock":
        canvas.create_rectangle(cx - 6, cy - 1, cx + 6, cy + 9,
                                outline=color, width=2)
        canvas.create_arc(cx - 5, cy - 9, cx + 5, cy + 4, start=0, extent=180,
                          style="arc", outline=color, width=2)
        canvas.create_oval(cx - 1, cy + 3, cx + 1, cy + 5, fill=color, outline=color)
    elif kind == "id":
        canvas.create_rectangle(cx - 8, cy - 6, cx + 8, cy + 6,
                                outline=color, width=2)
        canvas.create_line(cx - 5, cy - 1, cx + 1, cy - 1, fill=color, width=2)
        canvas.create_line(cx - 5, cy + 3, cx + 5, cy + 3, fill=color, width=2)
        canvas.create_oval(cx + 2, cy - 3, cx + 6, cy + 1, outline=color, width=1)
    elif kind == "eye":
        canvas.create_arc(cx - 8, cy - 4, cx + 8, cy + 6, start=0, extent=180,
                          style="arc", outline=color, width=2)
        canvas.create_arc(cx - 8, cy - 6, cx + 8, cy + 4, start=180, extent=180,
                          style="arc", outline=color, width=2)
        canvas.create_oval(cx - 2, cy - 2, cx + 2, cy + 2, outline=color, width=2)


# ========== 带标签的输入框 ==========
class LabeledEntry(tk.Frame):
    def __init__(
        self,
        master,
        label,
        bg="#0F1A33",
        field="#0B1428",
        edge="#1C2A4A",
        text="#F4F7FF",
        muted="#8A9AC0",
        accent="#22D3EE",
        font=("Microsoft YaHei UI", 11),
        show=None,
        icon="user",
    ):
        super().__init__(master, bg=bg)
        self.bg = bg
        self.field = field
        self.edge = edge
        self.accent = accent
        self.muted = muted
        self.icon_kind = icon

        tk.Label(
            self, text=label, font=("Microsoft YaHei UI", 9),
            fg=muted, bg=bg, anchor="w",
        ).pack(fill="x", pady=(0, 3))

        self.box = tk.Frame(self, bg=field, highlightbackground=edge,
                            highlightthickness=1, bd=0)
        self.box.pack(fill="x")

        self.accent_bar = tk.Frame(self.box, bg=field, width=3)
        self.accent_bar.pack(side=tk.LEFT, fill=tk.Y)

        self.icon = tk.Canvas(self.box, width=26, height=36, bg=field,
                              highlightthickness=0, bd=0)
        self.icon.pack(side=tk.LEFT, padx=(6, 0))
        draw_icon(self.icon, icon, muted)

        self.var = tk.StringVar()
        self.entry = tk.Entry(
            self.box, textvariable=self.var, show=show or "",
            font=font, bg=field, fg=text, insertbackground=accent,
            relief=tk.FLAT, bd=0, highlightthickness=0,
        )
        self._is_password = show == "*"
        if self._is_password:
            self.toggle = tk.Button(
                self.box, text="显示", font=("Microsoft YaHei UI", 8),
                fg=muted, bg=field, activeforeground=accent,
                activebackground=field, relief=tk.FLAT, bd=0,
                cursor="hand2", command=self._toggle_password,
            )
            # 先占住右侧空间，避免窄输入框把“显示”挤出去
            self.toggle.pack(side=tk.RIGHT, padx=(0, 6))
            self._password_visible = False

        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True,
                        padx=(2, 8), pady=6)

        self.entry.bind("<FocusIn>", self._focus_in)
        self.entry.bind("<FocusOut>", self._focus_out)

    def _focus_in(self, _event):
        self.box.config(highlightbackground=self.accent)
        self.accent_bar.config(bg=self.accent)
        draw_icon(self.icon, self.icon_kind, self.accent)

    def _focus_out(self, _event):
        self.box.config(highlightbackground=self.edge)
        self.accent_bar.config(bg=self.field)
        draw_icon(self.icon, self.icon_kind, self.muted)

    def _toggle_password(self):
        self._password_visible = not self._password_visible
        self.entry.config(show="" if self._password_visible else "*")
        self.toggle.config(text="隐藏" if self._password_visible else "显示")

    def get(self) -> str:
        return self.var.get().strip()

    def set(self, value: str):
        self.var.set(value)

    def focus(self):
        self.entry.focus_set()

    def bind_return(self, callback):
        self.entry.bind("<Return>", lambda _event: callback())


# ========== 角色选择（学生 / 教师） ==========
class RoleSelector(tk.Frame):
    def __init__(self, master, bg="#0F1A33", field="#0B1428",
                 edge="#1C2A4A", accent="#22D3EE", muted="#8A9AC0",
                 text="#F4F7FF"):
        super().__init__(master, bg=bg)
        self.var = tk.StringVar(value="学生")
        self._buttons = {}
        tk.Label(self, text="角色", font=("Microsoft YaHei UI", 9),
                 fg=muted, bg=bg, anchor="w").pack(fill="x", pady=(0, 3))
        row = tk.Frame(self, bg=bg)
        row.pack(fill="x")
        row.grid_columnconfigure(0, weight=1)
        row.grid_columnconfigure(1, weight=1)
        for i, role in enumerate(("学生", "教师")):
            btn = tk.Button(
                row, text=role, font=("Microsoft YaHei UI", 10, "bold"),
                relief=tk.FLAT, bd=0, cursor="hand2", height=1,
                command=lambda r=role: self._select(r),
            )
            btn.grid(row=0, column=i, sticky="ew",
                     padx=(0, 5) if i == 0 else (5, 0))
            self._buttons[role] = btn
        self._select("学生")

    def _select(self, role: str):
        self.var.set(role)
        for name, btn in self._buttons.items():
            if name == role:
                btn.config(bg="#22D3EE", fg="#04121F",
                           activebackground="#67E8F9", activeforeground="#04121F")
            else:
                btn.config(bg="#0B1428", fg="#8A9AC0",
                           activebackground="#13203C", activeforeground="#F4F7FF")


# ========== 圆角卡片 ==========
class RoundedCard(tk.Canvas):
    def __init__(self, master, width, height, bg, card, edge, radius=20):
        super().__init__(master, width=width, height=height, bg=bg,
                         highlightthickness=0, bd=0)
        self.w, self.h = width, height
        self.card = card
        self.edge = edge
        self.radius = radius
        self.body = tk.Frame(self, bg=card)
        self._win = self.create_window(radius, radius, anchor="nw",
                                       window=self.body)
        self.set_size(width, height)

    def set_size(self, width, height):
        self.w, self.h = width, height
        self.config(width=width, height=height)
        self.delete("deco")
        # 阴影
        round_rect(self, 4, 7, width - 2, height - 1, self.radius,
                   fill=darken(self.card, 0.45), outline="", tags="deco")
        # 卡片
        round_rect(self, 1, 1, width - 1, height - 1, self.radius,
                   fill=self.card, outline=self.edge, width=1, tags="deco")
        self.tag_lower("deco")
        self.itemconfigure(self._win, width=width - 2 * self.radius,
                           height=height - 2 * self.radius)
        self.coords(self._win, self.radius, self.radius)
