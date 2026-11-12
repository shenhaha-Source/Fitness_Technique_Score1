"""
星空背景工具模块
================
提供深色科技风星空背景，青/紫/绿三色星光粒子。

支持：
- 窗口大小自适应（自动重绘星光）
- 星光缓慢漂移动画
- 双模式：完整星空 / 稀疏边角星光（教师页用）
"""

import tkinter as tk
import random


# 配色
BG_COLOR = "#0B1020"
STAR_COLORS = ["#A78BFA", "#22D3EE", "#4ADE80", "#C4B5FD", "#67E8F9"]


class StarBackground(tk.Canvas):
    """
    星空背景 Canvas，自动生成随机星光粒子。

    Args:
        parent: 父容器
        star_count: 星光数量，默认 80
        mode: "full" 完整星空 / "sparse" 稀疏边角星光
    """

    def __init__(self, parent, star_count=80, mode="full"):
        super().__init__(parent, bg=BG_COLOR, highlightthickness=0)
        self.stars = []
        self.star_count = star_count
        self.mode = mode
        self._resize_job = None
        self._draw_pending = True

        # 绑定窗口大小变化事件
        self.bind("<Configure>", self._on_resize)

        # 启动动画
        self.animate()

    def _on_resize(self, event):
        """窗口大小变化时防抖重绘"""
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(150, self._init_stars)

    def _init_stars(self):
        """根据当前画布尺寸初始化星光粒子"""
        self._resize_job = None
        w = self.winfo_width()
        h = self.winfo_height()

        # 尺寸太小，等下次重绘
        if w < 100 or h < 100:
            self._draw_pending = True
            return

        self._draw_pending = False
        self.delete("star")
        self.stars = []

        # 根据面积动态调整星光数量
        area = w * h
        count = int(self.star_count * (area / (800 * 600)))
        count = max(40, min(count, 150))

        if self.mode == "sparse":
            # 稀疏模式：只在四个角落生成星光
            corners = [
                (0, 0, w * 0.25, h * 0.25),
                (w * 0.75, 0, w, h * 0.25),
                (0, h * 0.75, w * 0.25, h),
                (w * 0.75, h * 0.75, w, h),
            ]
            for _ in range(count):
                cx1, cy1, cx2, cy2 = random.choice(corners)
                x = random.randint(int(cx1), int(cx2))
                y = random.randint(int(cy1), int(cy2))
                self._add_star(x, y)
        else:
            # 完整星空：全区域随机
            for _ in range(count):
                x = random.randint(0, w)
                y = random.randint(0, h)
                self._add_star(x, y)

        # 加几个大一点的亮星
        for _ in range(8):
            x = random.randint(0, w)
            y = random.randint(0, h)
            self._add_star(x, y, big=True)

    def _add_star(self, x, y, big=False):
        """添加一颗星光"""
        size = random.randint(3, 5) if big else random.randint(1, 3)
        color = random.choice(STAR_COLORS)
        star_id = self.create_oval(x, y, x + size, y + size, fill=color, outline="", tags="star")
        self.stars.append({
            "id": star_id,
            "x": x,
            "y": y,
            "size": size,
            "vx": random.uniform(-0.3, 0.3),
            "vy": random.uniform(-0.2, 0.2),
        })

    def set_mode(self, mode):
        """切换星光模式：full / sparse"""
        self.mode = mode
        self._init_stars()

    def animate(self):
        """让星光缓慢漂移"""
        # 如果还没绘制，尝试绘制
        if self._draw_pending:
            self._init_stars()

        w = self.winfo_width()
        h = self.winfo_height()
        if w < 100 or h < 100:
            self.after(50, self.animate)
            return

        for star in self.stars:
            star["x"] += star["vx"]
            star["y"] += star["vy"]
            # 出界回绕
            if star["x"] < -5:
                star["x"] = w + 5
            elif star["x"] > w + 5:
                star["x"] = -5
            if star["y"] < -5:
                star["y"] = h + 5
            elif star["y"] > h + 5:
                star["y"] = -5
            self.coords(star["id"], star["x"], star["y"],
                        star["x"] + star["size"], star["y"] + star["size"])
        self.after(50, self.animate)
