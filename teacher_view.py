import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import csv
from PIL import Image, ImageTk

# 配色
BG_COLOR = "#0B1020"
CARD_BG = "#131A33"
PRIMARY = "#22D3EE"
ACCENT = "#A78BFA"
SUCCESS = "#4ADE80"
TEXT_MAIN = "#E5E7EB"
TEXT_SUB = "#9CA3AF"
CMD_GET_ALL_SCORES = 0x86

class TeacherView(tk.Frame):
    def __init__(self, parent, send_command, user_info, on_logout):
        super().__init__(parent, bg=BG_COLOR)
        self.send_command = send_command
        self.user_info = user_info
        self.on_logout = on_logout
        self.all_scores = []

        # 1. 底层背景画布
        self.bg_canvas = tk.Canvas(self, highlightthickness=0, bg=BG_COLOR)
        self.bg_canvas.pack(fill="both", expand=True)
        self.bg_photo = None
        self.original_image = None
        try:
            self.original_image = Image.open("bg_log1.jpg")
        except Exception as e:
            print(f"⚠️ 教师端背景加载失败: {e}")
        
        self.bg_canvas.bind("<Configure>", self._on_resize)

        # 2. 顶部标题栏 (居中，宽度 70%，为了让你看清楚背景)
        header = tk.Frame(self.bg_canvas, bg=CARD_BG, height=60)
        header.place(relx=0.15, rely=0.05, relwidth=0.7, height=60)
        
        tk.Label(header, text=f"👨‍🏫 {user_info['name']} 老师的成绩管理台", font=("微软雅黑", 14, "bold"), fg=TEXT_MAIN, bg=CARD_BG).pack(side=tk.LEFT, padx=10, pady=15)

        btn_frame = tk.Frame(header, bg=CARD_BG)
        btn_frame.pack(side=tk.RIGHT, padx=10)
        tk.Button(btn_frame, text="刷新", command=self.refresh, font=("微软雅黑", 10, "bold"), width=6, bg=PRIMARY, fg="#0B1020", relief=tk.FLAT, cursor="hand2").pack(side=tk.LEFT, padx=3)
        tk.Button(btn_frame, text="导出", command=self.export_csv, font=("微软雅黑", 10, "bold"), width=6, bg=SUCCESS, fg="#0B1020", relief=tk.FLAT, cursor="hand2").pack(side=tk.LEFT, padx=3)
        tk.Button(btn_frame, text="退出", command=on_logout, font=("微软雅黑", 10), width=6, bg="#6B7280", fg="white", relief=tk.FLAT, cursor="hand2").pack(side=tk.LEFT, padx=3)

        # 3. 表格区域 (居中，宽度 70%，高度 70%，上下左右都会露出背景图)
        table_card = tk.Frame(self.bg_canvas, bg=CARD_BG)
        table_card.place(relx=0.15, rely=0.18, relwidth=0.7, relheight=0.65)
        
        self.tree = ttk.Treeview(
            table_card,
            columns=("id", "name", "sid", "pull_up_cnt", "pull_up_score", "squat_cnt", "squat_score", "pushup_cnt", "pushup_score", "total"),
            show="headings"
        )
        cols = [("id", "序号", 40), ("name", "姓名", 70), ("sid", "学号", 80),
                ("pull_up_cnt", "引体(次)", 60), ("pull_up_score", "引体(分)", 60),
                ("squat_cnt", "深蹲(次)", 60), ("squat_score", "深蹲(分)", 60),
                ("pushup_cnt", "俯卧撑(次)", 65), ("pushup_score", "俯卧撑(分)", 65),
                ("total", "总分", 60)]
        for cid, text, w in cols:
            self.tree.heading(cid, text=text)
            self.tree.column(cid, width=w, anchor="center")

        self.tree.pack(fill="both", expand=True, padx=5, pady=5)

        # 滚动条
        scrollbar_y = ttk.Scrollbar(table_card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar_y.set)
        scrollbar_y.place(relx=1.0, rely=0, relheight=1.0, anchor="ne")

        # 4. 样式
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background=CARD_BG, foreground=TEXT_MAIN, fieldbackground=CARD_BG, rowheight=28, font=("微软雅黑", 10))
        style.configure("Treeview.Heading", background=PRIMARY, foreground="#0B1020", font=("微软雅黑", 10, "bold"))
        style.map("Treeview", background=[("selected", PRIMARY)])

        # 5. 底部统计
        self.stats_label = tk.Label(self.bg_canvas, text="加载中...", font=("微软雅黑", 10), fg=TEXT_SUB, bg=BG_COLOR)
        self.stats_label.place(relx=0.15, rely=0.86)

        self.after(100, self.refresh)

    def _on_resize(self, event):
        if not self.original_image:
            return
        new_w, new_h = event.width, event.height
        if new_w < 100 or new_h < 100:
            return
        img_w, img_h = self.original_image.size
        ratio = max(new_w / img_w, new_h / img_h)
        resized_image = self.original_image.resize((int(img_w * ratio), int(img_h * ratio)), Image.Resampling.LANCZOS)
        left = (int(img_w * ratio) - new_w) // 2
        top = (int(img_h * ratio) - new_h) // 2
        cropped_image = resized_image.crop((left, top, left + new_w, top + new_h))
        self.bg_photo = ImageTk.PhotoImage(cropped_image)
        self.bg_canvas.delete("bg")
        self.bg_canvas.create_image(0, 0, image=self.bg_photo, anchor="nw", tags="bg")
        self.bg_canvas.tag_lower("bg")

    def refresh(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        res = self.send_command(CMD_GET_ALL_SCORES)
        if not res.get("ok"):
            self.tree.insert("", tk.END, values=("-", "加载失败", "", "", "", "", "", "", "", ""))
            self.stats_label.config(text="数据加载失败")
            return
        scores = res.get("scores", [])
        self.all_scores = scores  
        if not scores:
            self.tree.insert("", tk.END, values=("-", "暂无注册学生", "", "", "", "", "", "", "", ""))
            self.stats_label.config(text="当前注册学生：0 人")
            return
        for idx, row in enumerate(scores, 1):
            name, sid, squat, squat_score, pull_up, pull_up_score, pushup, pushup_score, total = row
            self.tree.insert("", tk.END, values=(idx, name, sid, pull_up, f"{pull_up_score:.0f}", squat, f"{squat_score:.0f}", pushup, f"{pushup_score:.0f}", f"{total:.1f}"))
        total_students = len(scores)
        tested = sum(1 for r in scores if r[2] + r[4] + r[6] > 0)
        self.stats_label.config(text=f"当前注册学生：{total_students} 人 ｜ 已参与测评：{tested} 人 ｜ 未参与测评：{total_students - tested} 人")

    def export_csv(self):
        if not self.all_scores:
            messagebox.showwarning("提示", "没有数据可导出")
            return
        file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV文件", "*.csv")], initialfile="学生体测成绩表.csv")
        if not file_path: return
        try:
            with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["序号", "姓名", "学号", "引体向上(次)", "引体向上(分)", "深蹲(次)", "深蹲(分)", "俯卧撑(次)", "俯卧撑(分)", "总分(百分制)"])
                for idx, row in enumerate(self.all_scores, 1):
                    name, sid, squat, squat_score, pull_up, pull_up_score, pushup, pushup_score, total = row
                    writer.writerow([idx, name, sid, pull_up, f"{pull_up_score:.0f}", squat, f"{squat_score:.0f}", pushup, f"{pushup_score:.0f}", f"{total:.1f}"])
            messagebox.showinfo("成功", f"成绩表已导出")
        except Exception as e:
            messagebox.showerror("失败", f"导出失败：{e}")