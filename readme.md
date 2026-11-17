# 体测评分系统（FitnessScore）

基于 **MediaPipe 姿态识别 + OpenCV 摄像头采集 + Tkinter 图形界面 + SQLite 本地数据库** 的智能体测计数与评分系统。
通过摄像头实时捕捉人体关键点，自动完成引体向上、深蹲、俯卧撑的动作计数与百分制打分，并附带一个基于面部几何比例的"颜值趣味测评"小工具。系统采用 **C/S 分离架构**：推理后端以 Socket 服务运行，GUI 前端通过本机回环地址与之通信。

---

## 一、项目功能一览1

### 1. 双角色用户体系
| 角色 | 权限 |
| --- | --- |
| 学生（student） | 注册账号、进行三项体测、查看自己的历史最优成绩、玩颜值趣味测评 |
| 教师（teacher） | 查看全班所有学生成绩表格、刷新数据、导出 CSV、清零指定学生成绩 |

- 账号密码使用 **SHA-256 哈希**存储，数据库中不落明文。
- 登录成功后发放 `session_id`（UUID），写入 SQLite 会话表，**滑动过期**（每次请求自动续期 1 小时）。
- 预置教师演示账号：`tea01 / 123456`；学生账号需在登录页自行注册。

### 2. 三项正式体测（计入成绩）
所有项目均实时计数、实时折算百分制分数，**只保留历史最高分**。

| 项目 | 满分标准 | 判定依据 |
| --- | --- | --- |
| 💪 引体向上 | 15 次 = 100 分 | 鼻子相对肩线的高低 + 手肘角度 + 手腕是否过肩抓杆；**中途掉落自动结束测试** |
| 🏃 深蹲 | 30 次 = 100 分 | 髋部与膝盖的 y 坐标相对位置 |
| 🤸 俯卧撑 | 25 次 = 100 分 | 手肘角度：小于 90° 记为下压，大于 160° 记为撑起，一次往返计 1 个 |

- **综合总分** = 三项各自百分制分数的平均值（保留 1 位小数）。
- 分数评价：≥90 优秀，≥75 良好，≥60 及格，<60 待加强。
- 引体向上额外做了 **抓杆确认**（连续 20 帧保持"手腕过肩 + 手臂伸直"才算真的跳上去了，避免抬手误判）和 **掉落检测**（抓杆后连续 5 帧失去抓杆姿态即自动停止）。

### 3. 颜值趣味测评（不计入成绩）
调用 MediaPipe FaceLandmarker，基于面部 468 个关键点计算：
- 三庭比例：额头-鼻子-下巴的纵向比例是否接近 1:1；
- 左右对称性：左右眼、左右嘴角的 y 坐标差。
输出 0–100 的趣味分数，仅本地存档，不影响体测成绩。

### 4. 教师端成绩管理
- 表格展示所有注册学生的：姓名、学号、三项次数、三项得分、总分。
- 底部统计：注册人数、已参与测评人数、未参与人数。
- **导出 CSV**：一键另存为 `学生体测成绩表.csv`（UTF-8 BOM 编码，Excel 直接打开不乱码）。
- **删除学生成绩**：把指定学生三项成绩清零（账号保留）。

### 5. 界面与视觉
- 深色科技风（深蓝黑底 `#0B1020` + 青/紫/绿三色点缀）。
- 全窗口 **星空粒子动画背景**，学生端为完整星空，教师端自动切换为四角稀疏星光。
- 摄像头画面等比例缩放显示，不拉伸变形；实时把提示文字用 OpenCV 画在画面上。

---

## 二、项目结构

```
Fitness_Technique_Score1/
├── main.py                    # 程序入口：先后台启动 server.py，再启动 gui.py
├── gui.py                     # Tkinter 主窗口，负责页面切换 + Socket 客户端通信
├── server.py                  # 后端推理服务：Socket 监听 127.0.0.1:8888，多线程处理客户端
├── db.py                      # SQLite 数据层：建表、用户/会话/成绩/颜值记录的全部 SQL
├── login_view.py              # 登录 / 注册页面（深色卡片样式）
├── student_view.py            # 学生端：主页 + 三个测试页 + 颜值页 + 我的成绩页
├── teacher_view.py            # 教师端：成绩表格 + 导出 CSV + 删除学生成绩
├── star_bg.py                 # 星空动画背景 Canvas（full / sparse 两种模式）
├── utils.py                   # 通用三点夹角计算（备用工具）
├── pose_landmarker_full.task  # MediaPipe 姿态关键点模型（约 9 MB）
├── face_landmarker.task       # MediaPipe 面部关键点模型（约 3.7 MB）
├── app.ico                    # 程序图标
├── FitnessScore.spec          # PyInstaller 打包配置
├── record.db                  # 运行后自动生成的 SQLite 数据库
└── readme.md
```

---

## 三、通信协议（前端 ↔ 后端）

前后端通过本机 TCP Socket 通信，端口固定 `8888`，所有响应均为 **一行 JSON（以 `\n` 结尾）**。

**命令码一览：**

| 命令码 | 含义 | 是否需要 session |
| --- | --- | --- |
| `0x88` | 注册 | 否 |
| `0x89` | 登录 | 否 |
| `0x81` | 开始测试（后跟 1 字节测试类型） | 是 |
| `0x82` | 结束测试 | 是 |
| `0x85` | 学生查询自己的最优成绩 | 是 |
| `0x86` | 教师查询全部学生成绩 | 是 |
| `0x87` | 教师删除指定学生成绩（后跟姓名） | 是 |
| `0x84` | 清空记录（占位） | 是 |
| `0x00` / `0x01` | 图像帧：0=姿态识别，1=人脸识别 | 测试进行中 |

**帧格式：**
- 认证帧：命令码(1B) + JSON 长度(4B, 大端) + JSON 数据
- 业务帧：命令码(1B) + session 长度(1B) + session_id(N B) + 附加参数
- 图像帧：模式(1B) + JPG 长度(4B, 大端) + JPG 字节流

**测试类型枚举：**
`0 = 引体向上`，`1 = 深蹲`，`2 = 颜值测评`，`3 = 俯卧撑`

---

## 四、数据库表结构（SQLite，文件 `record.db`）

| 表名 | 作用 |
| --- | --- |
| `users` | 用户表：username（唯一）、password_hash、role（student/teacher）、name、student_id |
| `sessions` | 会话表：session_id、user_id、expire_time（滑动过期 1 小时） |
| `student_best_score` | 学生最优成绩表：每生一行，squat / pull_up / pushup 仅保留历史最大值 + 最后更新时间 |
| `face_fun_record` | 颜值趣味评分流水：user_id、score、create_time |

---

## 五、运行环境与依赖安装

### 环境要求
- **操作系统**：Windows 10 / 11（Tkinter 与 MediaPipe 在 Windows 下测试最稳；理论上 Linux / macOS 也可跑）
- **Python**：建议 **3.10 – 3.12**（MediaPipe 官方 wheel 对 Python 版本敏感，3.13+ 暂未提供预编译包）
- **摄像头**：笔记本内置摄像头或 USB 摄像头（程序默认打开 `cv2.VideoCapture(0)`）

### 安装依赖
建议先建虚拟环境，再一键安装：

```bash
# 1. 进入项目目录
cd C:\Users\shenqifa666\Desktop\daima\Fitness_Technique_Score1

# 2. 创建并激活虚拟环境（可选但推荐）
python -m venv .venv
.venv\Scripts\activate

# 3. 安装第三方库
pip install opencv-python mediapipe numpy Pillow
```

如需打包成 exe，再额外安装：

```bash
pip install pyinstaller
```

### 依赖库说明

| 库名 | 用途 | 是否必需 |
| --- | --- | --- |
| **opencv-python** | 摄像头采集、图像解码（`cv2.imdecode`）、BGR↔RGB 转换、画面上画提示文字 | ✅ 必需 |
| **mediapipe** | Google 出的端侧 AI 推理框架，提供 `PoseLandmarker`（33 个人体关键点）和 `FaceLandmarker`（468 个面部关键点） | ✅ 必需 |
| **numpy** | 关键点坐标数组运算、三点夹角计算（`np.arccos` / 向量点积）、JPG 字节流转图像数组 | ✅ 必需 |
| **Pillow** | 把 OpenCV 读到的帧转成 Tkinter 可显示的 `ImageTk.PhotoImage`，并做等比例缩放 | ✅ 必需 |
| **tkinter** | GUI 框架（窗口、按钮、表格、Canvas 星空背景）。Python 官方自带，无需 pip 安装 | ✅ 内置 |
| **sqlite3** | 本地数据库。Python 官方自带，无需 pip 安装 | ✅ 内置 |
| **socket / threading / json / hashlib / uuid** | Socket 通信、多线程、JSON 序列化、密码哈希、会话 ID 生成。均为标准库 | ✅ 内置 |
| **pyinstaller** | 把 Python 程序打包成独立 exe（对应 `FitnessScore.spec`） | ⬜ 仅打包时需要 |

> 备注：`gui.py` 顶部 `import psutil` 实际未使用，可忽略；`FitnessScore.spec` 中 `collect_all('pandas')` 是历史遗留，当前代码并未真正依赖 pandas，打包时可删掉对应两行。

---

## 六、启动方式

### 方式一：开发模式直接运行
```bash
python main.py
```
`main.py` 会做三件事：
1. 以子进程方式启动 `server.py`（监听 127.0.0.1:8888）；
2. 等待 1.5 秒让推理模型加载完毕；
3. 启动 `gui.py` 弹出登录窗口；
4. 关闭 GUI 后自动 terminate 后端进程。

也可以分两个终端手动跑，便于调试：
```bash
python server.py     # 终端 1：后端
python gui.py        # 终端 2：前端
```

### 方式二：打包成 exe
```bash
pyinstaller FitnessScore.spec
```
打包产物在 `dist/FitnessScore/` 目录下。
> 注意：打包时 `pose_landmarker_full.task`、`face_landmarker.task`、`app.ico` **不会被塞进 exe**，必须和 `FitnessScore.exe` 放在同一目录（代码里通过 `sys.executable` 同级目录读取）。

---

## 七、使用说明

1. **首次启动**会自动在项目目录生成 `record.db` 数据库，并预置教师账号 `tea01 / 123456`。
2. **学生注册**：登录页点"注册"，填写用户名、密码、姓名、学号，选择"学生"角色即可。
3. **开始测试**：
   - 点对应项目进入测试页；
   - 人站在摄像头前，全身（或至少半身 + 动作所需部位）入镜；
   - 点"开始测试"，画面上会实时显示计数与分数；
   - 做完点"停止测试"，系统自动把本次成绩与历史最高分比较，取大存入数据库。
4. **引体向上特殊提示**：需要先跳上单杠、双手举过肩并保持手臂伸直约 1 秒，系统提示"✅ 抓杆成功"后才开始计数；中途掉杠会自动弹窗结束。
5. **查成绩**：学生点"📊 我的成绩"查看自己的三项最优与总分。
6. **教师登录后**：自动展示全班成绩，可点"导出表格"保存 CSV，或清空某学生成绩。

---

## 八、关键参数调优位置（`server.py` 顶部）

如果动作识别不准，可以直接改这些阈值，无需动业务逻辑：

```python
# 引体向上
PULL_UP_UP_Y_THRESH    = 0.03    # 鼻子比肩线高多少算拉起到位
PULL_UP_DOWN_Y_THRESH  = 0.02    # 鼻子比肩线低多少算下放到位
PULL_UP_GRIP_RATIO     = 0.02    # 手腕比肩线高多少算抓杆
PULL_UP_STRAIGHT_ANGLE = 130.0   # 手肘角度大于此值 = 手臂伸直
PU_DEBOUNCE_FRAMES     = 2       # 防抖：连续多少帧满足条件才切换状态
PU_FALL_FRAMES         = 5       # 连续多少帧检测不到抓杆 = 掉落
PU_GRIP_CONFIRM_FRAMES = 20      # 连续多少帧保持抓杆才算真的跳上去了

# 深蹲
SQUAT_THRESHOLD = 0.08           # 髋膝 y 坐标差阈值

# 俯卧撑
PUSHUP_DOWN_ANGLE = 90.0         # 手肘角度小于此值 = 下去了
PUSHUP_UP_ANGLE   = 160.0        # 手肘角度大于此值 = 上来了
```

打分标准在 `db.py` 顶部：
```python
PULL_UP_FULL = 15   # 引体向上 15 次满分
SQUAT_FULL   = 30   # 深蹲 30 次满分
PUSHUP_FULL  = 25   # 俯卧撑 25 次满分
```

---

## 九、常见问题

**Q：启动报 `FileNotFoundError: pose_landmarker_full.task`？**
A：确认两个 `.task` 模型文件和脚本在同一目录；打包后要和 exe 放一起。代码里已经用"读取字节流再喂给 MediaPipe"的方式绕过了中文路径问题，但文件本身必须存在。

**Q：摄像头打不开 / 黑屏？**
A：检查是否有其他程序占用摄像头；`cv2.VideoCapture(0)` 的 `0` 是默认设备号，多摄像头时可改成 `1`、`2` 试一下。Windows 设置里要允许本应用访问摄像头。

**Q：MediaPipe 装不上？**
A：先确认 Python 版本在 3.10–3.12 之间、64 位系统；然后 `pip install mediapipe`。不要用 3.13+，官方还没出对应 wheel。

**Q：引体向上一直不计数？**
A：确认摄像头能拍到完整手臂（手腕要在肩膀上方），并保持约 1 秒等系统提示"抓杆成功"；拉起来时鼻子要明显高于肩膀连线。

---

## 十、技术栈速览

```
GUI 层      : Tkinter + ttk + Pillow
业务通信    : socket (TCP, 127.0.0.1:8888) + JSON 换行协议 + threading
AI 推理     : MediaPipe Tasks API (PoseLandmarker / FaceLandmarker, IMAGE 模式)
图像处理    : OpenCV (VideoCapture / imencode / imdecode / putText)
数据存储    : SQLite3 (标准库)
密码加密    : hashlib.sha256
打包        : PyInstaller (onedir 模式, 无控制台窗口)
```
