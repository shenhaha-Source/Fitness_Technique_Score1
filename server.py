import socket
import json
import cv2
import mediapipe as mp
import numpy as np
import threading

HOST = "127.0.0.1"
PORT = 8888

BaseOptions = mp.tasks.BaseOptions
PoseLandmarker = mp.tasks.vision.PoseLandmarker
PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
FaceLandmarker = mp.tasks.vision.FaceLandmarker
FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

# 模型路径，和你的文件名字保持一致
pose_model_path = "pose_landmarker_full.task"
face_model_path = "face_landmarker.task"

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

print("✅ Pose + FaceLandmarker 模型加载完成")

def handle_client(conn, addr):
    print(f"👉 客户端连接 {addr}")
    while True:
        try:
            # 读取模式标记 1字节：0=pose，1=face
            mode_data = conn.recv(1)
            if not mode_data:
                print(f"客户端 {addr} 断开")
                break
            mode = int.from_bytes(mode_data, byteorder="big")

            # 读取图片长度4字节
            len_buf = conn.recv(4)
            if len(len_buf) != 4:
                print(f"客户端 {addr} 断开")
                break
            img_len = int.from_bytes(len_buf, byteorder="big")

            img_data = b""
            while len(img_data) < img_len:
                chunk = conn.recv(img_len - len(img_data))
                if not chunk:
                    raise Exception("图片接收中断")
                img_data += chunk

            arr = np.frombuffer(img_data, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                ret = {"success": False, "landmarks": []}
                send_buf = (json.dumps(ret, ensure_ascii=False) + "\n").encode("utf-8")
                conn.sendall(send_buf)
                continue

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

            ret = {"success": False, "landmarks": []}
            if mode == 0:
                # 姿态识别（拍手、深蹲）
                res = pose_detector.detect(mp_image)
                if res.pose_landmarks:
                    lm = res.pose_landmarks[0]
                    lm_list = []
                    for p in lm:
                        lm_list.append({"x": p.x, "y": p.y, "z": p.z})
                    ret["success"] = True
                    ret["landmarks"] = lm_list
            else:
                # 人脸 FaceLandmarker（颜值测评）
                res = face_detector.detect(mp_image)
                if res.face_landmarks:
                    lm = res.face_landmarks[0]
                    lm_list = []
                    for p in lm:
                        lm_list.append({"x": p.x, "y": p.y, "z": p.z})
                    ret["success"] = True
                    ret["landmarks"] = lm_list

            send_buf = (json.dumps(ret, ensure_ascii=False) + "\n").encode("utf-8")
            conn.sendall(send_buf)

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
