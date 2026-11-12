"""
后端推理服务
============
基于 MediaPipe 的姿态/人脸检测服务，处理 Socket 通信、业务逻辑、成绩管理。

功能：
- 姿态识别：拍手计数、深蹲计数、俯卧撑计数
- 人脸识别：颜值比例趣味评分
- 用户认证：登录、注册、Session 会话管理
- 成绩管理：正式项目最高分保留、教师端成绩查询

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
    add_face_record
)

HOST = "127.0.0.1"
PORT = 8888

# ========== 业务参数阈值 ==========
# 拍手
HAND_CLOSE_THRESH = 0.35   # 双手距离小于此值 = 合拢
HAND_OPEN_THRESH = 0.45    # 双手距离大于此值 = 张开
STATE_APART = "apart"
STATE_CLAP = "clap"

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
TEST_CLAP = 0
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

    Args:
        filename: 模型文件名

    Returns:
        str: 模型文件完整路径
    """
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, filename)


pose_model_path = get_model_path("pose_landmarker_full.task")
face_model_path = get_model_path("face_landmarker.task")

pose_options = PoseLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=pose_model_path),
    running_mode=VisionRunningMode.IMAGE
)
pose_detector = PoseLandmarker.create_from_options(pose_options)

face_options = FaceLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=face_model_path),
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

    Args:
        a: 点A坐标 {"x":.., "y":..}
        b: 顶点B坐标
        c: 点C坐标

    Returns:
        float: 角度值（0-180度）
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

    Args:
        lm: 人脸关键点列表

    Returns:
        float: 0-100分，关键点不足返回 None
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

    # 三庭比例
    h1 = abs(nose["y"] - forehead["y"])
    h2 = abs(chin["y"] - nose["y"])
    ratio_three = h1 / h2 if h2 > 1e-6 else 1
    score_three = max(0, 100 - abs(ratio_three - 1) * 60)

    # 五官对称度
    eye_sym = abs(reye["y"] - leye["y"])
    mouth_sym = abs(rmouth["y"] - lmouth["y"])
    sym_score = max(0, 100 - (eye_sym + mouth_sym) * 250)

    total = 0.5 * score_three + 0.5 * sym_score
    return float(np.clip(total, 0, 100))


# ========== 会话状态 ==========
class SessionState:
    """
    每个客户端连接独立的会话状态。
    记录当前登录用户、当前测试类型、各测试的计数状态。
    """

    def __init__(self):
        self.user = None            # 登录用户信息
        self.current_test = None    # 当前测试类型

        # 拍手状态
        self.clap_state = STATE_APART
        self.clap_count = 0

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

        Args:
            test_type: 测试类型枚举
        """
        self.current_test = test_type
        self.clap_state = STATE_APART
        self.clap_count = 0
        self.squat_state = STATE_STAND
        self.squat_count = 0
        self.pushup_state = STATE_UP
        self.pushup_count = 0
        self.last_face_score = None

    def stop_test(self):
        """
        结束当前测试，返回 (测试名称, 计数, 分数)。

        Returns:
            tuple 或 None: (test_name, count, score)
        """
        result = None
        if self.current_test == TEST_CLAP:
            result = ("拍手计数测试", self.clap_count, None)
        elif self.current_test == TEST_SQUAT:
            result = ("深蹲计数测试", self.squat_count, None)
        elif self.current_test == TEST_PUSHUP:
            result = ("俯卧撑计数测试", self.pushup_count, None)
        elif self.current_test == TEST_FACE:
            if self.last_face_score is not None:
                result = ("颜值比例测评", None, round(self.last_face_score, 1))
        self.current_test = None
        return result


# ========== 通信工具 ==========
def recv_exact(conn, n: int) -> bytes:
    """
    精确读取 n 个字节，防止粘包。

    Args:
        conn: socket 连接
        n: 要读取的字节数

    Returns:
        bytes 或 None: 读取到的数据，连接断开返回 None
    """
    data = b""
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            return None
        data += chunk
    return data


def send_json(conn, obj: dict):
    """
    发送 JSON 响应（以换行符结尾）。

    Args:
        conn: socket 连接
        obj: 要发送的字典对象
    """
    send_buf = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
    conn.sendall(send_buf)


def recv_json(conn) -> dict:
    """
    接收一行 JSON 响应。

    Args:
        conn: socket 连接

    Returns:
        dict: 解析后的 JSON 对象，失败返回空字典
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

    Args:
        conn: socket 连接

    Returns:
        str 或 None: session 字符串
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

    Args:
        conn: socket 连接对象
        addr: 客户端地址
    """
    print(f"👉 客户端连接 {addr}")
    session = SessionState()

    while True:
        try:
            first_byte = recv_exact(conn, 1)
            if first_byte is None:
                break
            first = first_byte[0]

            # ========== 认证类命令（不需要 session） ==========
            if first == CMD_REGISTER:
                _handle_register(conn)
                continue

            elif first == CMD_LOGIN:
                _handle_login(conn, session)
                continue

            # ========== 图像帧（模式 0=pose, 1=face，不需要 session） ==========
            if first in (0, 1):
                _handle_image_frame(conn, session, first)
                continue

            # ========== 业务类命令（需要 session 校验） ==========
            sid = recv_session_id(conn)
            if sid is None:
                break

            user = check_session(sid)
            if not user:
                send_json(conn, {"ok": False, "msg": "会话已失效，请重新登录", "need_relogin": True})
                continue

            session.user = user
            _handle_business_command(conn, session, first)

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

    Args:
        conn: socket 连接
        session: 会话状态
        cmd: 命令码
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
            elif test_name == "拍手计数测试":
                update_best_score(user["uid"], "clap", count)
            elif test_name == "俯卧撑计数测试":
                update_best_score(user["uid"], "pushup", count)
            # 趣味项目：单独存颜值记录表
            elif test_name == "颜值比例测评" and score is not None:
                add_face_record(user["uid"], score)
            print(f"💾 测试结束: {user['name']} - {test_name}, count={count}, score={score}")
        send_json(conn, {"ok": True, "msg": "测试已结束"})

    elif cmd == CMD_GET_MY_SCORE:
        # 学生查自己的成绩
        best = get_student_best(user["uid"])
        send_json(conn, {"ok": True, "score": best})

    elif cmd == CMD_GET_ALL_SCORES:
        # 老师查全部学生成绩
        if user["role"] != "teacher":
            send_json(conn, {"ok": False, "msg": "无权限"})
            return
        scores = get_all_student_score_for_teacher()
        send_json(conn, {"ok": True, "scores": scores})

    elif cmd == CMD_CLEAR_RECORDS:
        send_json(conn, {"ok": True, "msg": "已清空"})

    else:
        send_json(conn, {"ok": False, "msg": "未知命令"})


def _handle_image_frame(conn, session: SessionState, mode: int):
    """
    处理图像帧：姿态识别/人脸识别 + 计数。

    Args:
        conn: socket 连接
        session: 会话状态
        mode: 0=pose姿态, 1=face人脸
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

    response = {"success": False, "tip": "未检测到", "count": 0, "score": None}

    if mode == 0:
        # ===== 姿态识别 =====
        res = pose_detector.detect(mp_image)
        if res.pose_landmarks:
            lm = res.pose_landmarks[0]
            lm_list = [{"x": p.x, "y": p.y, "z": p.z} for p in lm]
            response["success"] = True

            # 拍手计数
            if session.current_test == TEST_CLAP and len(lm_list) >= 17:
                rw = lm_list[15]
                lw = lm_list[16]
                dist = np.sqrt((rw["x"] - lw["x"]) ** 2 + (rw["y"] - lw["y"]) ** 2)
                response["tip"] = f"距离:{dist:.3f}"

                if session.clap_state == STATE_APART:
                    if dist < HAND_CLOSE_THRESH:
                        session.clap_state = STATE_CLAP
                elif session.clap_state == STATE_CLAP:
                    if dist > HAND_OPEN_THRESH:
                        session.clap_count += 1
                        response["tip"] = "👏拍手成功！"
                        session.clap_state = STATE_APART
                response["count"] = session.clap_count

            # 深蹲计数
            elif session.current_test == TEST_SQUAT and len(lm_list) >= 27:
                l_hip = lm_list[23]
                r_hip = lm_list[24]
                l_knee = lm_list[25]
                r_knee = lm_list[26]
                hip_y = (l_hip["y"] + r_hip["y"]) / 2
                knee_y = (l_knee["y"] + r_knee["y"]) / 2
                response["tip"] = f"髋y:{hip_y:.3f},膝y:{knee_y:.3f}"

                if session.squat_state == STATE_STAND:
                    if knee_y > hip_y + SQUAT_THRESHOLD:
                        session.squat_state = STATE_SQUAT
                elif session.squat_state == STATE_SQUAT:
                    if knee_y < hip_y - SQUAT_THRESHOLD:
                        session.squat_count += 1
                        response["tip"] = "✅深蹲完成！"
                        session.squat_state = STATE_STAND
                response["count"] = session.squat_count

            # 俯卧撑计数
            elif session.current_test == TEST_PUSHUP and len(lm_list) >= 16:
                l_shoulder = lm_list[11]
                l_elbow = lm_list[13]
                l_wrist = lm_list[15]
                angle = calc_angle(l_shoulder, l_elbow, l_wrist)
                response["tip"] = f"手肘角度:{angle:.1f}°"

                if session.pushup_state == STATE_UP:
                    if angle < PUSHUP_DOWN_ANGLE:
                        session.pushup_state = STATE_DOWN
                elif session.pushup_state == STATE_DOWN:
                    if angle > PUSHUP_UP_ANGLE:
                        session.pushup_count += 1
                        response["tip"] = "💪俯卧撑完成！"
                        session.pushup_state = STATE_UP
                response["count"] = session.pushup_count

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
