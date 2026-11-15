"""
数据库层模块
============
负责所有 SQLite 数据操作：用户管理、会话管理、正式体测成绩管理、趣味颜值记录。

表结构：
- users: 用户表（学生/教师）
- sessions: 会话表（登录状态保持）
- student_best_score: 学生正式体测最优成绩表（深蹲/引体向上/俯卧撑，每个学生一行，仅存最高分）
- face_fun_record: 趣味颜值评分记录表（仅学生可见，不计入正式成绩）

打分规则（百分制）：
- 引体向上：15次 = 100分
- 深蹲：30次 = 100分
- 俯卧撑：25次 = 100分
- 总分 = 三项平均分（百分制）

作者：AI动作测评系统
"""

import sqlite3
import time
import hashlib
import uuid
import os


# ========== 全局配置 ==========
SESSION_TIMEOUT = 3600  # 会话有效期：1小时（滑动过期）

# 打分标准：多少次满分
PULL_UP_FULL = 15    # 引体向上15次满分
SQUAT_FULL = 30      # 深蹲30次满分
PUSHUP_FULL = 25     # 俯卧撑25次满分


def count_to_score(count: int, full_count: int) -> float:
    """
    把次数转换为百分制分数。

    Args:
        count: 完成次数
        full_count: 多少次满分

    Returns:
        float: 百分制分数（0-100）
    """
    if count <= 0:
        return 0.0
    score = count / full_count * 100
    return round(min(score, 100.0), 1)


def get_db_path():
    """
    获取数据库文件的绝对路径，兼容开发环境和PyInstaller打包环境。
    数据库生成在exe同级目录。
    """
    import sys
    if hasattr(sys, '_MEIPASS'):
        # 打包后：用exe所在目录
        base_dir = os.path.dirname(sys.executable)
    else:
        # 开发环境：用脚本所在目录
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "record.db")


DB_PATH = get_db_path()


# ========== 密码工具 ==========
def get_pwd_hash(raw_pwd: str) -> str:
    """
    对原始密码进行 SHA-256 哈希，不存储明文密码。
    """
    return hashlib.sha256(raw_pwd.encode("utf-8")).hexdigest()


# ========== 初始化 ==========
def init_db():
    """
    初始化数据库，创建所有表（如果不存在）。
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1. 用户表
    cur.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL,
        name TEXT,
        student_id TEXT
    )
    ''')

    # 2. 会话表
    cur.execute('''
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        expire_time REAL NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    ''')

    # 3. 学生正式体测最优成绩表（每个学生一行，仅存最高分）
    cur.execute('''
    CREATE TABLE IF NOT EXISTS student_best_score (
        user_id INTEGER PRIMARY KEY,
        squat INTEGER DEFAULT 0,
        pull_up INTEGER DEFAULT 0,
        pushup INTEGER DEFAULT 0,
        last_update TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    ''')

    # 4. 趣味颜值评分记录表
    cur.execute('''
    CREATE TABLE IF NOT EXISTS face_fun_record (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        score REAL,
        create_time TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    ''')

    conn.commit()
    conn.close()

    # 预置测试账号
    _seed_test_users()


def _seed_test_users():
    """
    预置演示测试账号（仅保留老师账号，学生不预置）。
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users WHERE role='teacher'")
    count = cur.fetchone()[0]
    if count > 0:
        conn.close()
        return

    # 只预置老师账号，不预置学生
    add_user("tea01", "123456", "teacher", "李老师", "T001")
    conn.close()
    print("✅ 已预置老师账号：tea01/123456")


# ========== 用户：注册 / 登录 ==========
def add_user(username: str, raw_pwd: str, role: str, name: str, student_id: str = "") -> bool:
    """
    注册新用户。学生注册时自动初始化一行全0的成绩记录。
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        pwd_hash = get_pwd_hash(raw_pwd)
        cur.execute(
            "INSERT INTO users (username, password_hash, role, name, student_id) VALUES (?,?,?,?,?)",
            (username, pwd_hash, role, name, student_id)
        )
        user_id = cur.lastrowid

        if role == "student":
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(
                "INSERT INTO student_best_score (user_id, squat, pull_up, pushup, last_update) VALUES (?,?,?,?,?)",
                (user_id, 0, 0, 0, now)
            )

        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False


def login_user(username: str, raw_pwd: str):
    """
    校验用户名密码，登录成功返回用户信息。
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    pwd_hash = get_pwd_hash(raw_pwd)
    cur.execute(
        "SELECT id, username, role, name, student_id FROM users WHERE username=? AND password_hash=?",
        (username, pwd_hash)
    )
    row = cur.fetchone()
    conn.close()
    if row:
        return {
            "uid": row[0],
            "username": row[1],
            "role": row[2],
            "name": row[3],
            "student_id": row[4] or ""
        }
    return None


# ========== 会话：创建 / 校验（滑动过期） ==========
def create_session(user_id: int) -> str:
    """
    登录成功后创建会话，返回 session_id。
    """
    session_id = uuid.uuid4().hex
    expire_time = time.time() + SESSION_TIMEOUT
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO sessions (session_id, user_id, expire_time) VALUES (?,?,?)",
        (session_id, user_id, expire_time)
    )
    conn.commit()
    conn.close()
    return session_id


def check_session(session_id: str):
    """
    校验会话是否有效，有效则自动续期（滑动过期）。
    """
    now = time.time()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute('''
        SELECT u.id, u.username, u.role, u.name, u.student_id, s.expire_time
        FROM sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.session_id = ?
    ''', (session_id,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return None

    expire_time = row[5]
    if expire_time < now:
        cur.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
        conn.commit()
        conn.close()
        return None

    new_expire = now + SESSION_TIMEOUT
    cur.execute("UPDATE sessions SET expire_time=? WHERE session_id=?", (new_expire, session_id))
    conn.commit()
    conn.close()

    return {
        "uid": row[0],
        "username": row[1],
        "role": row[2],
        "name": row[3],
        "student_id": row[4] or ""
    }


# ========== 正式体测成绩 ==========
def calc_total(squat: int, pull_up: int, pushup: int) -> float:
    """
    计算综合总分（百分制）：三项平均分。

    Args:
        squat: 深蹲最优次数
        pull_up: 引体向上最优次数
        pushup: 俯卧撑最优次数

    Returns:
        float: 百分制总分（0-100）
    """
    s_score = count_to_score(squat, SQUAT_FULL)
    pu_score = count_to_score(pull_up, PULL_UP_FULL)
    p_score = count_to_score(pushup, PUSHUP_FULL)
    total = (s_score + pu_score + p_score) / 3
    return round(total, 1)


def get_student_best(uid: int) -> dict:
    """
    查询单个学生的三项最优成绩和分数。

    Returns:
        dict: {squat, pull_up, pushup, squat_score, pull_up_score, pushup_score, total, last_update}
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT squat, pull_up, pushup, last_update FROM student_best_score WHERE user_id=?",
        (uid,)
    )
    row = cur.fetchone()
    conn.close()

    if row:
        squat, pull_up, pushup, last_update = row
        squat_score = count_to_score(squat, SQUAT_FULL)
        pull_up_score = count_to_score(pull_up, PULL_UP_FULL)
        pushup_score = count_to_score(pushup, PUSHUP_FULL)
        total = calc_total(squat, pull_up, pushup)
        return {
            "squat": squat,
            "pull_up": pull_up,
            "pushup": pushup,
            "squat_score": squat_score,
            "pull_up_score": pull_up_score,
            "pushup_score": pushup_score,
            "total": total,
            "last_update": last_update or ""
        }
    else:
        return {
            "squat": 0, "pull_up": 0, "pushup": 0,
            "squat_score": 0.0, "pull_up_score": 0.0, "pushup_score": 0.0,
            "total": 0.0, "last_update": ""
        }


def update_best_score(uid: int, mode: str, new_val: int) -> bool:
    """
    更新学生单项最优成绩，仅当新成绩高于历史最高分才覆盖。

    Args:
        uid: 用户ID
        mode: 项目标识，可选 "squat", "pull_up", "pushup"
        new_val: 本次测试得到的计数值

    Returns:
        bool: True=成绩已更新；False=新成绩不高于历史最高分，未改动
    """
    valid_modes = ("squat", "pull_up", "pushup")
    if mode not in valid_modes:
        return False

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(f"SELECT {mode} FROM student_best_score WHERE user_id=?", (uid,))
    row = cur.fetchone()

    if not row:
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            f"INSERT INTO student_best_score (user_id, {mode}, last_update) VALUES (?,?,?)",
            (uid, new_val, now)
        )
        conn.commit()
        conn.close()
        return True

    old_val = row[0]
    if new_val > old_val:
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            f"UPDATE student_best_score SET {mode}=?, last_update=? WHERE user_id=?",
            (new_val, now, uid)
        )
        conn.commit()
        conn.close()
        return True

    conn.close()
    return False


def get_all_student_score_for_teacher() -> list:
    """
    教师端查询所有注册学生的正式体测成绩。

    Returns:
        list: 每行 [name, student_id, squat, squat_score, pull_up, pull_up_score, pushup, pushup_score, total]
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        SELECT u.name, u.student_id, 
               COALESCE(s.squat, 0), 
               COALESCE(s.pull_up, 0), 
               COALESCE(s.pushup, 0),
               s.last_update
        FROM users u
        LEFT JOIN student_best_score s ON u.id = s.user_id
        WHERE u.role = 'student'
        ORDER BY u.id ASC
    ''')
    rows = cur.fetchall()
    conn.close()

    result = []
    for row in rows:
        name, sid, squat, pull_up, pushup, last_update = row
        squat_score = count_to_score(squat, SQUAT_FULL)
        pull_up_score = count_to_score(pull_up, PULL_UP_FULL)
        pushup_score = count_to_score(pushup, PUSHUP_FULL)
        total = calc_total(squat, pull_up, pushup)
        result.append([name, sid, squat, squat_score, pull_up, pull_up_score, pushup, pushup_score, total])
    return result


def delete_student_score(name: str) -> bool:
    """
    老师端删除指定学生的成绩（把三项成绩清零）。

    Args:
        name: 学生姓名

    Returns:
        bool: True=删除成功；False=没找到
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # 先找到用户ID
    cur.execute("SELECT id FROM users WHERE name=? AND role='student'", (name,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return False
    uid = row[0]
    # 把成绩清零
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        "UPDATE student_best_score SET squat=0, pull_up=0, pushup=0, last_update=? WHERE user_id=?",
        (now, uid)
    )
    conn.commit()
    conn.close()
    return True


# ========== 趣味颜值记录 ==========
def add_face_record(uid: int, score: float):
    """
    保存一条趣味颜值评分记录。
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        "INSERT INTO face_fun_record (user_id, score, create_time) VALUES (?,?,?)",
        (uid, score, now)
    )
    conn.commit()
    conn.close()


# ========== 测试入口 ==========
if __name__ == "__main__":
    init_db()
    print("✅ 数据库初始化完成")
    print("打分标准：引体向上15次满分，深蹲30次满分，俯卧撑25次满分")
