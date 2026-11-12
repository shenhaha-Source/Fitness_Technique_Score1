import socket
import json
import cv2
import mediapipe as mp
import numpy as np
import threading
import os
import sys

# 导入数据库层
from db import init_db, add_record_db, load_records_db, clear_all_db

HOST = "127.0.0.1"
PORT = 8888

# ========== 业务参数（原来在gui里的，全部移到后端） ==========
# 拍手
HAND_CLOSE_THRESH = 0.35
HAND_OPEN_THRESH = 0.45
STATE_APART = "apart"
STATE_CLAP = "clap"

# 深蹲
SQUAT_THRESHOLD = 0.08
STATE_STAND = "stand"
STATE_SQUAT = "squat"

# 测试类型枚举
TEST_CLAP = 0
TEST_SQUAT = 1
TEST_FACE = 2

# 命令码（从0x80开始，避免和图像模式0/1冲突）
CMD_START_TEST = 0x81
CMD_STOP_TEST = 0x82
CMD_GET_RECORDS = 0x83
CMD_CLEAR_RECORDS = 0x84

BaseOptions = mp.tasks.BaseOptions
PoseLandmarker = mp.tasks.vision.PoseLandmarker
PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
FaceLandmarker = mp.tasks.vision.FaceLandmarker
FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

# 模型路径
def get_model_path(filename):
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, filename)

pose_model_path = get_model_path("pose_landmarker_full.task")
face_model_path = get_model_path("face_landmarker.task")

# 姿态检测器
pose_options = PoseLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=pose_model_path),
    running_mode=VisionRunningMode.IMAGE
)
pose_detector = PoseLandmarker.create_from_options(pose_options)

# 人脸检测器
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


# ========== 业务逻辑：颜值打分（从gui移过来） ==========
def calc_face_score(lm):
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


# ========== 会话状态管理（每个连接独立） ==========
class SessionState:
    def __init__(self):
        self.current_test = None  # None / TEST_CLAP / TEST_SQUAT / TEST_FACE
        # 拍手状态
        self.clap_state = STATE_APART
        self.clap_count = 0
        # 深蹲状态
        self.squat_state = STATE_STAND
        self.squat_count = 0
        # 颜值
        self.last_face_score = None

    def reset(self, test_type):
        """开始新测试，重置状态"""
        self.current_test = test_type
        self.clap_state = STATE_APART
        self.clap_count = 0
        self.squat_state = STATE_STAND
        self.squat_count = 0
        self.last_face_score = None

    def stop(self):
        """结束当前测试，返回要保存的记录信息"""
        result = None
        if self.current_test == TEST_CLAP:
            result = ("拍手计数测试", self.clap_count, None)
        elif self.current_test == TEST_SQUAT:
            result = ("深蹲计数测试", self.squat_count, None)
        elif self.current_test == TEST_FACE:
            if self.last_face_score is not None:
                result = ("颜值比例测评", None, round(self.last_face_score, 1))
        self.current_test = None
        return result


def recv_exact(conn, n):
    """精确读取n个字节"""
    data = b""
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            return None
        data += chunk
    return data


def send_json(conn, obj):
    """发送JSON + 换行符"""
    send_buf = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
    conn.sendall(send_buf)


def handle_client(conn, addr):
    print(f"👉 客户端连接 {addr}")
    session = SessionState()

    while True:
        try:
            # 读第一个字节：判断是命令帧还是图像帧
            first_byte = recv_exact(conn, 1)
            if first_byte is None:
                break

            first = first_byte[0]

            # ========== 命令帧处理 ==========
            if first in (CMD_START_TEST, CMD_STOP_TEST, CMD_GET_RECORDS, CMD_CLEAR_RECORDS):
                if first == CMD_START_TEST:
                    # 后跟1字节测试类型
                    type_data = recv_exact(conn, 1)
                    if type_data is None:
                        break
                    test_type = type_data[0]
                    session.reset(test_type)
                    print(f"📝 开始测试: {test_type}")
                    send_json(conn, {"success": True, "message": "测试已开始"})

                elif first == CMD_STOP_TEST:
                    result = session.stop()
                    if result is not None:
                        test_name, count, score = result
                        add_record_db(test_name, count=count, score=score)
                        print(f"💾 保存记录: {test_name}, count={count}, score={score}")
                    send_json(conn, {"success": True, "message": "测试已结束，记录已保存"})

                elif first == CMD_GET_RECORDS:
                    rows = load_records_db()
                    records = []
                    for r in rows:
                        rid, t, typ, cnt, sc = r
                        records.append([rid, t, typ, cnt, sc])
                    send_json(conn, {"success": True, "records": records})

                elif first == CMD_CLEAR_RECORDS:
                    clear_all_db()
                    send_json(conn, {"success": True, "message": "记录已清空"})

                continue

            # ========== 图像帧处理 ==========
            # first = 模式 (0=pose, 1=face)
            mode = first

            # 读图片长度
            len_buf = recv_exact(conn, 4)
            if len_buf is None or len(len_buf) != 4:
                break
            img_len = int.from_bytes(len_buf, byteorder="big")

            img_data = recv_exact(conn, img_len)
            if img_data is None:
                break

            arr = np.frombuffer(img_data, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                send_json(conn, {"success": False, "landmarks": [], "tip": "图像解码失败"})
                continue

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

            response = {"success": False, "landmarks": [], "tip": "未检测到", "count": 0, "score": None}

            if mode == 0:
                # ===== 姿态识别 =====
                res = pose_detector.detect(mp_image)
                if res.pose_landmarks:
                    lm = res.pose_landmarks[0]
                    lm_list = [{"x": p.x, "y": p.y, "z": p.z} for p in lm]
                    response["success"] = True
                    response["landmarks"] = lm_list

                    # 根据当前测试类型做业务计算
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

            else:
                # ===== 人脸识别 =====
                res = face_detector.detect(mp_image)
                if res.face_landmarks:
                    lm = res.face_landmarks[0]
                    lm_list = [{"x": p.x, "y": p.y, "z": p.z} for p in lm]
                    response["success"] = True
                    response["landmarks"] = lm_list

                    if session.current_test == TEST_FACE:
                        score = calc_face_score(lm_list)
                        if score is not None:
                            session.last_face_score = score
                            response["score"] = round(score, 1)
                            response["tip"] = f"分数：{score:.1f}"

            send_json(conn, response)

        except Exception as e:
            print(f"单帧异常：{e}")
            continue

    conn.close()
    print(f"👋 连接关闭 {addr}")


def start_server():
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
