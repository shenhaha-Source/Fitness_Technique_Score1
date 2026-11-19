"""
后端推理服务
============
基于 MediaPipe 的姿态/人脸检测服务，处理 Socket 通信、业务逻辑、成绩管理。

功能：
- 姿态识别：引体向上计数（掉落自动停止）、深蹲计数、俯卧撑计数
- 人脸识别：颜值比例趣味评分
- 用户认证：登录、注册、Session 会话管理
- 成绩管理：正式项目最高分保留、百分制打分、教师端成绩查询

打分规则：
- 引体向上：15次 = 100分
- 深蹲：30次 = 100分
- 俯卧撑：25次 = 100分
- 总分 = 三项平均分

通信协议：
- 认证帧：命令码(1) + JSON长度(4) + JSON数据
- 业务帧：命令码(1) + session长度(1) + session_id(N) + 额外参数
- 图像帧：模式(1) + 图片长度(4) + JPG数据
"""

import socket
import json
import cv2
import mediapipe as mp
import numpy as np
import threading
import os
import sys

from db import (
    init_db, add_user, login_user, create_session, check_session,
    update_best_score, get_student_best, get_all_student_score_for_teacher,
    add_face_record, count_to_score, delete_student_score,
    PULL_UP_FULL, SQUAT_FULL, PUSHUP_FULL
)

HOST = "127.0.0.1"
PORT = 8888

# ========== 业务参数阈值 ==========
# 引体向上
PULL_UP_UP_Y_THRESH = 0.03   # 鼻子比肩线高多少算拉起到位
PULL_UP_DOWN_Y_THRESH = 0.02 # 鼻子比肩线低多少算下放到位
PULL_UP_GRIP_RATIO = 0.02    # 手腕比肩膀高多少算抓杆
PULL_UP_STRAIGHT_ANGLE = 130.0 # 手肘角度大于此值 = 手臂伸直（放宽到130°）
PU_DEBOUNCE_FRAMES = 2        # 连续多少帧满足条件才切换状态（放宽到2帧）
PU_FALL_FRAMES = 5            # 连续多少帧检测不到抓杆 = 掉落
PU_GRIP_CONFIRM_FRAMES = 20   # 连续多少帧保持抓杆才算真的跳上去了
STATE_PU_WAIT = "wait"        # 等待抓杆（初始状态，人在地面）
STATE_PU_READY = "ready"      # 抓杆、手臂伸直（基准状态）
STATE_PU_UP = "up"            # 拉起，下巴过杆

# 深蹲
SQUAT_THRESHOLD = 0.08     # 髋膝y坐标差阈值
STATE_STAND = "stand"
STATE_SQUAT = "squat"

# 俯卧撑
PUSHUP_DOWN_ANGLE = 90.0   # 手肘角度小于此值 = 下去了
PUSHUP_UP_ANGLE = 160.0    # 手肘角度大于此值 = 上来了
STATE_UP = "up"
STATE_DOWN = "down"

# 测试类型枚举
TEST_PULL_UP = 0      # 引体向上（替换原来的拍手）
TEST_SQUAT = 1
TEST_FACE = 2
TEST_PUSHUP = 3

# 命令码
CMD_REGISTER = 0x88
CMD_LOGIN = 0x89
CMD_START_TEST = 0x81
CMD_STOP_TEST = 0x82
CMD_GET_MY_SCORE = 0x85      # 学生查我的成绩
CMD_GET_ALL_SCORES = 0x86    # 老师查全部成绩
CMD_CLEAR_RECORDS = 0x84
CMD_DELETE_STUDENT = 0x87    # 老师删除学生成绩

# MediaPipe 组件初始化
BaseOptions = mp.tasks.BaseOptions
PoseLandmarker = mp.tasks.vision.PoseLandmarker
PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
FaceLandmarker = mp.tasks.vision.FaceLandmarker
FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode


def get_model_path(filename: str) -> str:
    """
    获取模型文件路径，兼容开发环境和 PyInstaller 打包环境。
    模型文件放在exe同级目录，不打包进exe内部。
    """
    if hasattr(sys, '_MEIPASS'):
        # 打包后：用exe所在目录
        base_path = os.path.dirname(sys.executable)
    else:
        # 开发环境：用脚本所在目录
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, filename)


def load_model_bytes(filename: str) -> bytes:
    """
    直接读取模型文件为字节流，绕过中文路径问题（mediapipe C扩展不支持中文路径）。
    """
    path = get_model_path(filename)
    with open(path, "rb") as f:
        return f.read()


# 用字节流加载模型，避免中文路径导致FileNotFoundError
pose_model_bytes = load_model_bytes("pose_landmarker_full.task")
face_model_bytes = load_model_bytes("face_landmarker.task")

pose_options = PoseLandmarkerOptions(
    base_options=BaseOptions(model_asset_buffer=pose_model_bytes),
    running_mode=VisionRunningMode.IMAGE
)
pose_detector = PoseLandmarker.create_from_options(pose_options)

face_options = FaceLandmarkerOptions(
    base_options=BaseOptions(model_asset_buffer=face_model_bytes),
    running_mode=VisionRunningMode.IMAGE,
    num_faces=1
)
face_detector = FaceLandmarker.create_from_options(face_options)

# 初始化数据库
init_db()
print("✅ 数据库初始化完成")
print("✅ Pose + FaceLandmarker 模型加载完成")


# ========== 工具函数 ==========
def calc_angle(a: dict, b: dict, c: dict) -> float:
    """
    计算三点角度：以 b 为顶点，a-b-c 的夹角（度）。
    """
    a = np.array([a["x"], a["y"]])
    b = np.array([b["x"], b["y"]])
    c = np.array([c["x"], c["y"]])
    ba = a - b
    bc = c - b
    cos_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-6)
    angle = np.arccos(np.clip(cos_angle, -1.0, 1.0))
    return np.degrees(angle)


def calc_face_score(lm: list) -> float:
    """
    计算颜值比例趣味评分（基于面部关键点几何比例）。
    """
    if len(lm) < 300:
        return None
    forehead = lm[10]
    nose = lm[1]
    chin = lm[152]
    reye = lm[33]
    leye = lm[263]
    rmouth = lm[61]
    lmouth = lm[291]

    h1 = abs(nose["y"] - forehead["y"])
    h2 = abs(chin["y"] - nose["y"])
    ratio_three = h1 / h2 if h2 > 1e-6 else 1
    score_three = max(0, 100 - abs(ratio_three - 1) * 60)

    eye_sym = abs(reye["y"] - leye["y"])
    mouth_sym = abs(rmouth["y"] - lmouth["y"])
    sym_score = max(0, 100 - (eye_sym + mouth_sym) * 250)

    total = 0.5 * score_three + 0.5 * sym_score
    return float(np.clip(total, 0, 100))


# ========== 会话状态 ==========
class SessionState:
    """
    每个客户端连接独立的会话状态。
    """

    def __init__(self):
        self.user = None            # 登录用户信息
        self.current_test = None    # 当前测试类型

        # 引体向上状态
        self.pu_state = STATE_PU_WAIT   # 初始状态：等待抓杆（人在地面）
        self.pu_count = 0
        self.pu_fall_counter = 0    # 掉落检测计数器
        self.pu_stopped = False     # 是否已因掉落停止
        self.pu_grip_started = False # 是否已成功抓杆（经过确认）
        self.pu_grip_confirm = 0    # 抓杆确认计数器（连续多少帧保持抓杆）
        self.pu_debounce = 0        # 防抖计数器
        self.pu_tip_timer = 0       # 提示显示计时器（持续多少帧）
        self.pu_tip_text = ""       # 要显示的提示文字

        # 深蹲状态
        self.squat_state = STATE_STAND
        self.squat_count = 0

        # 俯卧撑状态
        self.pushup_state = STATE_UP
        self.pushup_count = 0

        # 颜值
        self.last_face_score = None

    def reset_test(self, test_type: int):
        """
        开始新测试，重置所有计数状态。
        """
        self.current_test = test_type
        self.pu_state = STATE_PU_WAIT
        self.pu_count = 0
        self.pu_fall_counter = 0
        self.pu_stopped = False
        self.pu_grip_started = False
        self.pu_grip_confirm = 0
        self.pu_debounce = 0
        self.pu_tip_timer = 0
        self.pu_tip_text = ""
        self.squat_state = STATE_STAND
        self.squat_count = 0
        self.pushup_state = STATE_UP
        self.pushup_count = 0
        self.last_face_score = None

    def stop_test(self):
        """
        结束当前测试，返回 (测试名称, 计数, 分数)。
        """
        result = None
        if self.current_test == TEST_PULL_UP:
            score = count_to_score(self.pu_count, PULL_UP_FULL)
            result = ("引体向上计数测试", self.pu_count, score)
        elif self.current_test == TEST_SQUAT:
            score = count_to_score(self.squat_count, SQUAT_FULL)
            result = ("深蹲计数测试", self.squat_count, score)
        elif self.current_test == TEST_PUSHUP:
            score = count_to_score(self.pushup_count, PUSHUP_FULL)
            result = ("俯卧撑计数测试", self.pushup_count, score)
        elif self.current_test == TEST_FACE:
            if self.last_face_score is not None:
                result = ("颜值比例测评", None, round(self.last_face_score, 1))
        self.current_test = None
        return result


# ========== 通信工具 ==========
def recv_exact(conn, n: int) -> bytes:
    """
    精确读取 n 个字节，防止粘包。
    """
    data = bytearray()
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            return None
        data.extend(chunk)
    return bytes(data)


def send_json(conn, obj: dict):
    """
    发送 JSON 响应（以换行符结尾）。
    """
    send_buf = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
    conn.sendall(send_buf)


def recv_json(conn) -> dict:
    """
    接收一行 JSON 响应。
    """
    raw = b""
    while True:
        c = conn.recv(1)
        if c == b"\n" or not c:
            break
        raw += c
    if raw:
        return json.loads(raw.decode("utf-8"))
    return {}


def recv_session_id(conn) -> str:
    """
    读取 session_id（1字节长度 + N字节内容）。
    """
    len_data = recv_exact(conn, 1)
    if len_data is None:
        return None
    sid_len = len_data[0]
    sid_data = recv_exact(conn, sid_len)
    if sid_data is None:
        return None
    return sid_data.decode("utf-8")


# ========== 客户端处理主逻辑 ==========
def handle_client(conn, addr):
    """
    处理单个客户端连接的主循环。
    """
    print(f"👉 客户端连接 {addr}")
    session = SessionState()

    while True:
        try:
            first_byte = recv_exact(conn, 1)
            if first_byte is None:
                break
            first = first_byte[0]

            # ========== 认证类命令 ==========
            if first == CMD_REGISTER:
                _handle_register(conn)
                continue

            elif first == CMD_LOGIN:
                _handle_login(conn, session)
                continue

            # ========== 图像帧 ==========
            if first in (0, 1):
                _handle_image_frame(conn, session, first)
                continue

            # ========== 业务类命令 ==========
            sid = recv_session_id(conn)
            if sid is None:
                break

            user = check_session(sid)
            if not user:
                send_json(conn, {"ok": False, "msg": "会话已失效，请重新登录", "need_relogin": True})
                continue

            session.user = user
            try:
                _handle_business_command(conn, session, first)
            except Exception as e:
                print(f"业务命令处理异常: {e}")
                import traceback
                traceback.print_exc()
                send_json(conn, {"ok": False, "msg": f"服务器内部错误: {e}"})

        except Exception as e:
            print(f"处理异常：{e}")
            continue

    conn.close()
    print(f"👋 连接关闭 {addr}")


def _handle_register(conn):
    """处理注册请求"""
    len_buf = recv_exact(conn, 4)
    if len_buf is None:
        return
    json_len = int.from_bytes(len_buf, byteorder="big")
    json_data = recv_exact(conn, json_len)
    if json_data is None:
        return
    info = json.loads(json_data.decode("utf-8"))

    ok = add_user(
        info["username"],
        info["password"],
        info["role"],
        info.get("name", ""),
        info.get("student_id", "")
    )
    if ok:
        send_json(conn, {"ok": True, "msg": "注册成功"})
        print(f"📝 新用户注册: {info['username']} ({info['role']})")
    else:
        send_json(conn, {"ok": False, "msg": "用户名已存在"})


def _handle_login(conn, session: SessionState):
    """处理登录请求"""
    len_buf = recv_exact(conn, 4)
    if len_buf is None:
        return
    json_len = int.from_bytes(len_buf, byteorder="big")
    json_data = recv_exact(conn, json_len)
    if json_data is None:
        return
    info = json.loads(json_data.decode("utf-8"))

    user = login_user(info["username"], info["password"])
    if user:
        sid = create_session(user["uid"])
        session.user = user
        send_json(conn, {
            "ok": True,
            "session_id": sid,
            "role": user["role"],
            "name": user["name"],
            "student_id": user["student_id"]
        })
        print(f"✅ 用户登录: {user['name']} ({user['role']})")
    else:
        send_json(conn, {"ok": False, "msg": "用户名或密码错误"})


def _handle_business_command(conn, session: SessionState, cmd: int):
    """
    处理业务类命令（已通过 session 校验）。
    """
    user = session.user

    if cmd == CMD_START_TEST:
        type_data = recv_exact(conn, 1)
        if type_data is None:
            return
        test_type = type_data[0]
        session.reset_test(test_type)
        send_json(conn, {"ok": True, "msg": "测试已开始"})

    elif cmd == CMD_STOP_TEST:
        result = session.stop_test()
        if result is not None and user:
            test_name, count, score = result
            # 正式项目：写入最高分成绩表
            if test_name == "深蹲计数测试":
                update_best_score(user["uid"], "squat", count)
            elif test_name == "引体向上计数测试":
                update_best_score(user["uid"], "pull_up", count)
            elif test_name == "俯卧撑计数测试":
                update_best_score(user["uid"], "pushup", count)
            # 趣味项目：单独存颜值记录表
            elif test_name == "颜值比例测评" and score is not None:
                add_face_record(user["uid"], score)
            print(f"💾 测试结束: {user['name']} - {test_name}, count={count}, score={score}")
        send_json(conn, {"ok": True, "msg": "测试已结束"})

    elif cmd == CMD_GET_MY_SCORE:
        best = get_student_best(user["uid"])
        send_json(conn, {"ok": True, "score": best})

    elif cmd == CMD_GET_ALL_SCORES:
        if user["role"] != "teacher":
            send_json(conn, {"ok": False, "msg": "无权限"})
            return
        scores = get_all_student_score_for_teacher()
        send_json(conn, {"ok": True, "scores": scores})

    elif cmd == CMD_DELETE_STUDENT:
        # 老师删除指定学生成绩
        if user["role"] != "teacher":
            send_json(conn, {"ok": False, "msg": "无权限"})
            return
        # 读取要删除的学生姓名
        name_len_data = recv_exact(conn, 1)
        if name_len_data is None:
            return
        name_len = name_len_data[0]
        name_data = recv_exact(conn, name_len)
        if name_data is None:
            return
        student_name = name_data.decode("utf-8")
        ok = delete_student_score(student_name)
        if ok:
            send_json(conn, {"ok": True, "msg": f"已删除 {student_name} 的成绩"})
            print(f"🗑️ 老师删除了 {student_name} 的成绩")
        else:
            send_json(conn, {"ok": False, "msg": "未找到该学生"})

    elif cmd == CMD_CLEAR_RECORDS:
        send_json(conn, {"ok": True, "msg": "已清空"})

    else:
        send_json(conn, {"ok": False, "msg": "未知命令"})


def _handle_image_frame(conn, session: SessionState, mode: int):
    """
    处理图像帧：姿态识别/人脸识别 + 计数。
    """
    len_buf = recv_exact(conn, 4)
    if len_buf is None:
        return
    img_len = int.from_bytes(len_buf, byteorder="big")

    img_data = recv_exact(conn, img_len)
    if img_data is None:
        return

    arr = np.frombuffer(img_data, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        send_json(conn, {"success": False, "tip": "图像解码失败"})
        return

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

    response = {"success": False, "tip": "未检测到", "count": 0, "score": None, "auto_stop": False}

    if mode == 0:
        # ===== 姿态识别 =====
        res = pose_detector.detect(mp_image)
        if res.pose_landmarks:
            lm = res.pose_landmarks[0]
            lm_list = [{"x": p.x, "y": p.y, "z": p.z} for p in lm]
            response["success"] = True

            # 引体向上计数
            if session.current_test == TEST_PULL_UP and len(lm_list) >= 17:
                # 如果已经因掉落停止，直接返回
                if session.pu_stopped:
                    current_score = count_to_score(session.pu_count, PULL_UP_FULL)
                    response["count"] = session.pu_count
                    response["score"] = current_score
                    response["tip"] = "⚠️ 已掉落，测试结束"
                    response["auto_stop"] = True
                    send_json(conn, response)
                    return

                nose = lm_list[0]
                l_shoulder = lm_list[11]
                r_shoulder = lm_list[12]
                l_elbow = lm_list[13]
                r_elbow = lm_list[14]
                l_wrist = lm_list[15]
                r_wrist = lm_list[16]

                shoulder_y = (l_shoulder["y"] + r_shoulder["y"]) / 2
                wrist_y = (l_wrist["y"] + r_wrist["y"]) / 2

                # 计算左右手肘角度，判断手臂是否伸直
                l_arm_angle = calc_angle(l_shoulder, l_elbow, l_wrist)
                r_arm_angle = calc_angle(r_shoulder, r_elbow, r_wrist)
                arm_straight = (l_arm_angle > PULL_UP_STRAIGHT_ANGLE and
                                r_arm_angle > PULL_UP_STRAIGHT_ANGLE)

                # 判断是否抓杆：手腕高于肩膀
                is_grip = wrist_y < shoulder_y - PULL_UP_GRIP_RATIO

                # 掉落检测：只有已经开始抓杆之后，才检测掉落
                if session.pu_grip_started:
                    if not is_grip:
                        session.pu_fall_counter += 1
                        if session.pu_fall_counter >= PU_FALL_FRAMES:
                            session.pu_stopped = True
                            current_score = count_to_score(session.pu_count, PULL_UP_FULL)
                            response["count"] = session.pu_count
                            response["score"] = current_score
                            response["tip"] = "⚠️ 已掉落，测试结束！"
                            response["auto_stop"] = True
                            send_json(conn, response)
                            return
                    else:
                        session.pu_fall_counter = 0
                else:
                    # 还没成功抓杆，开始确认过程
                    if is_grip and arm_straight:
                        # 连续保持抓杆+手臂伸直，确认真的抓杆了
                        session.pu_grip_confirm += 1
                        if session.pu_grip_confirm >= PU_GRIP_CONFIRM_FRAMES:  # 连续多帧才算真抓杆
                            session.pu_grip_started = True
                            session.pu_state = STATE_PU_READY
                            session.pu_debounce = 0
                            # 设置提示，持续显示2秒（约60帧）
                            session.pu_tip_timer = 60
                            session.pu_tip_text = "✅ 抓杆成功！开始做引体向上！"
                    else:
                        # 不满足抓杆条件，重置确认计数（随便抬手一下不算数）
                        session.pu_grip_confirm = 0

                # 状态机（只有开始抓杆后才计数）
                if session.pu_grip_started:
                    # 判定是否拉起到位：鼻子比肩线高（上拉时手臂自然弯曲，不做限制）
                    is_up = nose["y"] < shoulder_y - PULL_UP_UP_Y_THRESH
                    # 判定是否下放到位：鼻子比肩线低 且 手臂伸直（回到悬垂起点）
                    is_down = nose["y"] > shoulder_y + PULL_UP_DOWN_Y_THRESH and arm_straight

                    if session.pu_state == STATE_PU_READY:
                        # 基准状态：手臂伸直悬垂，看是否拉起到位
                        if is_up:
                            session.pu_debounce += 1
                            if session.pu_debounce >= PU_DEBOUNCE_FRAMES:
                                session.pu_state = STATE_PU_UP
                                session.pu_debounce = 0
                                response["tip"] = "💪 拉起到位！下放计数"
                        else:
                            session.pu_debounce = 0

                    elif session.pu_state == STATE_PU_UP:
                        # 拉起状态，看是否下放回到基准（必须手臂伸直）
                        if is_down:
                            session.pu_debounce += 1
                            if session.pu_debounce >= PU_DEBOUNCE_FRAMES:
                                session.pu_count += 1
                                response["tip"] = f"✅ 完成第{session.pu_count}个！"
                                session.pu_state = STATE_PU_READY
                                session.pu_debounce = 0
                        else:
                            session.pu_debounce = 0

                # 实时分数
                current_score = count_to_score(session.pu_count, PULL_UP_FULL)
                response["score"] = current_score
                response["count"] = session.pu_count

                # 拼接提示文本
                if not session.pu_grip_started:
                    response["tip"] = "请跳上去抓杆（双手举过肩+手臂伸直保持1秒）..."
                elif session.pu_tip_timer > 0:
                    # 显示抓杆成功提示，持续2秒
                    response["tip"] = session.pu_tip_text
                    session.pu_tip_timer -= 1
                response["tip"] += f" | 分数:{current_score:.0f}"

            # 深蹲计数
            elif session.current_test == TEST_SQUAT and len(lm_list) >= 27:
                l_hip = lm_list[23]
                r_hip = lm_list[24]
                l_knee = lm_list[25]
                r_knee = lm_list[26]
                hip_y = (l_hip["y"] + r_hip["y"]) / 2
                knee_y = (l_knee["y"] + r_knee["y"]) / 2

                if session.squat_state == STATE_STAND:
                    if knee_y > hip_y + SQUAT_THRESHOLD:
                        session.squat_state = STATE_SQUAT
                elif session.squat_state == STATE_SQUAT:
                    if knee_y < hip_y - SQUAT_THRESHOLD:
                        session.squat_count += 1
                        session.squat_state = STATE_STAND

                current_score = count_to_score(session.squat_count, SQUAT_FULL)
                response["score"] = current_score
                response["count"] = session.squat_count
                response["tip"] = f"深蹲:{session.squat_count}个 | 分数:{current_score:.0f}"

            # 俯卧撑计数
            elif session.current_test == TEST_PUSHUP and len(lm_list) >= 16:
                l_shoulder = lm_list[11]
                l_elbow = lm_list[13]
                l_wrist = lm_list[15]
                angle = calc_angle(l_shoulder, l_elbow, l_wrist)

                if session.pushup_state == STATE_UP:
                    if angle < PUSHUP_DOWN_ANGLE:
                        session.pushup_state = STATE_DOWN
                elif session.pushup_state == STATE_DOWN:
                    if angle > PUSHUP_UP_ANGLE:
                        session.pushup_count += 1
                        session.pushup_state = STATE_UP

                current_score = count_to_score(session.pushup_count, PUSHUP_FULL)
                response["score"] = current_score
                response["count"] = session.pushup_count
                response["tip"] = f"俯卧撑:{session.pushup_count}个 | 分数:{current_score:.0f}"

    else:
        # ===== 人脸识别 =====
        res = face_detector.detect(mp_image)
        if res.face_landmarks:
            lm = res.face_landmarks[0]
            lm_list = [{"x": p.x, "y": p.y, "z": p.z} for p in lm]
            response["success"] = True

            if session.current_test == TEST_FACE:
                score = calc_face_score(lm_list)
                if score is not None:
                    session.last_face_score = score
                    response["score"] = round(score, 1)
                    response["tip"] = f"分数：{score:.1f}"

    send_json(conn, response)


def start_server():
    """启动 Socket 服务端，监听客户端连接"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((HOST, PORT))
    sock.listen(5)
    print(f"推理服务监听 {HOST}:{PORT}")
    while True:
        conn, addr = sock.accept()
        t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
        t.start()


if __name__ == "__main__":
    start_server()
