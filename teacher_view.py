"""
教师端视图模块（深色科技风）
============================
教师成绩管理页面，展示所有注册学生的正式体测最优成绩。

功能：
- 展示所有学生的三项成绩（次数+分数）和总分
- 删除指定学生成绩
- 一键导出成绩表为CSV文件
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import csv

# 配色
BG_COLOR = "#0B1020"
CARD_BG = "#131A33"
PRIMARY = "#22D3EE"
ACCENT = "#A78BFA"
DANGER = "#F87171"
SUCCESS = "#4ADE80"
TEXT_MAIN = "#E5E7EB"
TEXT_SUB = "#9CA3AF"

CMD_GET_ALL_SCORES = 0x86
CMD_DELETE_STUDENT = 0x87


class TeacherView(tk.Frame):
    """
    教师成绩管理视图。
    """

    def __init__(self, parent, send_command, user_info, on_logout):
        super().__init__(parent, bg=BG_COLOR)
        self.send_command = send_command
        self.user_info = user_info
        self.on_logout = on_logout
        self.all_scores = []  # 保存当前所有成绩数据，用于导出

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
            btn_frame, text="导出表格", command=self.export_csv,
            font=("微软雅黑", 10, "bold"), width=8,
            bg=SUCCESS, fg="#0B1020", relief=tk.FLAT, cursor="hand2",
            activebackground="#86EFAC", bd=0, padx=10, pady=4
        ).pack(side=tk.LEFT, padx=5)

        tk.Button(
            btn_frame, text="退出登录", command=on_logout,
            font=("微软雅黑", 10), width=8,
            bg="#6B7280", fg="white", relief=tk.FLAT, cursor="hand2",
            activebackground="#9CA3AF", bd=0, padx=10, pady=4
        ).pack(side=tk.LEFT, padx=5)

        # 表格卡片
        table_card = tk.Frame(self, bg=CARD_BG)
        table_card.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 10))
        table_card.grid_rowconfigure(0, weight=1)
        table_card.grid_columnconfigure(0, weight=1)

        # 成绩表格
        self.tree = ttk.Treeview(
            table_card,
            columns=("id", "name", "sid",
                     "pull_up_cnt", "pull_up_score",
                     "squat_cnt", "squat_score",
                     "pushup_cnt", "pushup_score",
                     "total"),
            show="headings"
        )

        # 表头
        self.tree.heading("id", text="序号")
        self.tree.heading("name", text="姓名")
        self.tree.heading("sid", text="学号")
        self.tree.heading("pull_up_cnt", text="引体(次)")
        self.tree.heading("pull_up_score", text="引体(分)")
        self.tree.heading("squat_cnt", text="深蹲(次)")
        self.tree.heading("squat_score", text="深蹲(分)")
        self.tree.heading("pushup_cnt", text="俯卧撑(次)")
        self.tree.heading("pushup_score", text="俯卧撑(分)")
        self.tree.heading("total", text="总分")

        # 列宽（紧凑一点，让所有列都能显示）
        self.tree.column("id", width=40, anchor="center")
        self.tree.column("name", width=70, anchor="center")
        self.tree.column("sid", width=80, anchor="center")
        self.tree.column("pull_up_cnt", width=60, anchor="center")
        self.tree.column("pull_up_score", width=60, anchor="center")
        self.tree.column("squat_cnt", width=60, anchor="center")
        self.tree.column("squat_score", width=60, anchor="center")
        self.tree.column("pushup_cnt", width=65, anchor="center")
        self.tree.column("pushup_score", width=65, anchor="center")
        self.tree.column("total", width=60, anchor="center")

        self.tree.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # 滚动条（纵向+横向）
        scrollbar_y = ttk.Scrollbar(table_card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar_y.set)
        scrollbar_y.grid(row=0, column=1, sticky="ns", pady=10)

        scrollbar_x = ttk.Scrollbar(table_card, orient="horizontal", command=self.tree.xview)
        self.tree.configure(xscroll=scrollbar_x.set)
        scrollbar_x.grid(row=1, column=0, sticky="ew", padx=10)

        # 配置 ttk 样式（深色表格）
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Treeview",
            background=CARD_BG,
            foreground=TEXT_MAIN,
            fieldbackground=CARD_BG,
            rowheight=28,
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
            self.tree.insert("", tk.END, values=("-", "加载失败", "", "", "", "", "", "", "", ""))
            self.stats_label.config(text="数据加载失败")
            return

        scores = res.get("scores", [])
        self.all_scores = scores  # 保存数据用于导出
        if not scores:
            self.tree.insert("", tk.END, values=("-", "暂无注册学生", "", "", "", "", "", "", "", ""))
            self.stats_label.config(text="当前注册学生：0 人")
            return

        # 填充数据
        for idx, row in enumerate(scores, 1):
            name, sid, squat, squat_score, pull_up, pull_up_score, pushup, pushup_score, total = row
            self.tree.insert("", tk.END, values=(
                idx, name, sid,
                pull_up, f"{pull_up_score:.0f}",
                squat, f"{squat_score:.0f}",
                pushup, f"{pushup_score:.0f}",
                f"{total:.1f}"
            ))

        # 统计
        total_students = len(scores)
        tested = sum(1 for r in scores if r[2] + r[4] + r[6] > 0)
        self.stats_label.config(
            text=f"当前注册学生：{total_students} 人 ｜ 已参与测评：{tested} 人 ｜ 未参与测评：{total_students - tested} 人"
        )

    def export_csv(self):
        """导出成绩表为CSV文件"""
        if not self.all_scores:
            messagebox.showwarning("提示", "没有数据可导出")
            return

        # 选择保存路径
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV文件", "*.csv"), ("所有文件", "*.*")],
            initialfile="学生体测成绩表.csv"
        )
        if not file_path:
            return

        # 写入CSV
        try:
            with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                # 表头
                writer.writerow([
                    "序号", "姓名", "学号",
                    "引体向上(次)", "引体向上(分)",
                    "深蹲(次)", "深蹲(分)",
                    "俯卧撑(次)", "俯卧撑(分)",
                    "总分(百分制)"
                ])
                # 数据
                for idx, row in enumerate(self.all_scores, 1):
                    name, sid, squat, squat_score, pull_up, pull_up_score, pushup, pushup_score, total = row
                    writer.writerow([
                        idx, name, sid,
                        pull_up, f"{pull_up_score:.0f}",
                        squat, f"{squat_score:.0f}",
                        pushup, f"{pushup_score:.0f}",
                        f"{total:.1f}"
                    ])
            messagebox.showinfo("成功", f"成绩表已导出到：\n{file_path}")
        except Exception as e:
            messagebox.showerror("失败", f"导出失败：{e}")
