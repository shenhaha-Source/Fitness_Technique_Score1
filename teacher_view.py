"""
教师端视图模块（深色科技风）
============================
教师成绩管理页面，展示所有注册学生的正式体测最优成绩。

功能：
- 展示所有注册学生的三项体测成绩（深蹲/拍手/俯卧撑）和总分
- 未测试项目显示为0
- 刷新数据
- 底部统计信息
"""

import tkinter as tk
from tkinter import ttk

# 配色
BG_COLOR = "#0B1020"
CARD_BG = "#131A33"
PRIMARY = "#22D3EE"
TEXT_MAIN = "#E5E7EB"
TEXT_SUB = "#9CA3AF"
DANGER = "#F87171"

CMD_GET_ALL_SCORES = 0x86


class TeacherView(tk.Frame):
    """
    教师成绩管理视图。

    Args:
        parent: 父容器
        send_command: 发送业务命令的回调函数
        user_info: 当前登录教师信息
        on_logout: 退出登录回调
    """

    def __init__(self, parent, send_command, user_info, on_logout):
        super().__init__(parent, bg=BG_COLOR)
        self.send_command = send_command
        self.user_info = user_info
        self.on_logout = on_logout

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # 顶部标题卡片
        header = tk.Frame(self, bg=CARD_BG, height=60)
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(15, 10))
        header.grid_columnconfigure(0, weight=1)

        tk.Label(
            header, text=f"👨‍🏫 {user_info['name']} 老师的成绩管理台",
            font=("微软雅黑", 16, "bold"), fg=TEXT_MAIN, bg=CARD_BG
        ).grid(row=0, column=0, sticky="w", padx=15, pady=15)

        # 按钮组
        btn_frame = tk.Frame(header, bg=CARD_BG)
        btn_frame.grid(row=0, column=1, sticky="e", padx=15)

        tk.Button(
            btn_frame, text="刷新", command=self.refresh,
            font=("微软雅黑", 10, "bold"), width=8,
            bg=PRIMARY, fg="#0B1020", relief=tk.FLAT, cursor="hand2",
            activebackground="#67E8F9", bd=0, padx=10, pady=4
        ).pack(side=tk.LEFT, padx=5)

        tk.Button(
            btn_frame, text="退出登录", command=on_logout,
            font=("微软雅黑", 10), width=8,
            bg=DANGER, fg="white", relief=tk.FLAT, cursor="hand2",
            activebackground="#FCA5A5", bd=0, padx=10, pady=4
        ).pack(side=tk.LEFT, padx=5)

        # 表格卡片
        table_card = tk.Frame(self, bg=CARD_BG)
        table_card.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 10))
        table_card.grid_rowconfigure(0, weight=1)
        table_card.grid_columnconfigure(0, weight=1)

        # 成绩表格
        self.tree = ttk.Treeview(
            table_card,
            columns=("id", "name", "sid", "squat", "clap", "pushup", "total"),
            show="headings"
        )

        # 表头
        self.tree.heading("id", text="序号")
        self.tree.heading("name", text="学生姓名")
        self.tree.heading("sid", text="学号")
        self.tree.heading("squat", text="深蹲(次)")
        self.tree.heading("clap", text="拍手(次)")
        self.tree.heading("pushup", text="俯卧撑(次)")
        self.tree.heading("total", text="综合总分")

        # 列宽
        self.tree.column("id", width=60, anchor="center")
        self.tree.column("name", width=120, anchor="center")
        self.tree.column("sid", width=120, anchor="center")
        self.tree.column("squat", width=100, anchor="center")
        self.tree.column("clap", width=100, anchor="center")
        self.tree.column("pushup", width=110, anchor="center")
        self.tree.column("total", width=100, anchor="center")

        self.tree.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # 滚动条
        scrollbar = ttk.Scrollbar(table_card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns", pady=10)

        # 配置 ttk 样式（深色表格）
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Treeview",
            background=CARD_BG,
            foreground=TEXT_MAIN,
            fieldbackground=CARD_BG,
            rowheight=30,
            font=("微软雅黑", 10)
        )
        style.configure(
            "Treeview.Heading",
            background=PRIMARY,
            foreground="#0B1020",
            font=("微软雅黑", 10, "bold")
        )
        style.map("Treeview", background=[("selected", PRIMARY)])

        # 底部统计
        self.stats_label = tk.Label(
            self, text="加载中...", font=("微软雅黑", 10),
            fg=TEXT_SUB, bg=BG_COLOR
        )
        self.stats_label.grid(row=2, column=0, sticky="w", padx=25, pady=(0, 10))

        # 初始加载
        self.after(100, self.refresh)

    def refresh(self):
        """从后端拉取所有学生成绩并刷新表格"""
        for item in self.tree.get_children():
            self.tree.delete(item)

        res = self.send_command(CMD_GET_ALL_SCORES)
        if not res.get("ok"):
            self.tree.insert("", tk.END, values=("-", "加载失败", "", "", "", "", ""))
            self.stats_label.config(text="数据加载失败")
            return

        scores = res.get("scores", [])
        if not scores:
            self.tree.insert("", tk.END, values=("-", "暂无注册学生", "", "", "", "", ""))
            self.stats_label.config(text="当前注册学生：0 人")
            return

        # 填充数据
        for idx, row in enumerate(scores, 1):
            name, sid, squat, clap, pushup, total = row
            self.tree.insert("", tk.END, values=(idx, name, sid, squat, clap, pushup, total))

        # 统计
        total_students = len(scores)
        tested = sum(1 for r in scores if r[3] + r[4] + r[5] > 0)
        self.stats_label.config(
            text=f"当前注册学生：{total_students} 人 ｜ 已参与测评：{tested} 人 ｜ 未参与测评：{total_students - tested} 人"
        )
