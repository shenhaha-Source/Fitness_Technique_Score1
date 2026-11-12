import sqlite3
import time
import os


def get_db_path():
    """数据库文件放在脚本所在目录，打包后也能正常工作"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "record.db")


DB_PATH = get_db_path()


def init_db():
    """初始化数据库，建表（不存在则创建）"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
    CREATE TABLE IF NOT EXISTS test_record (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        create_time TEXT NOT NULL,
        test_type TEXT NOT NULL,
        count INTEGER,
        score REAL
    )
    ''')
    conn.commit()
    conn.close()


def add_record_db(test_type, count=None, score=None):
    """添加一条测试记录"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        "INSERT INTO test_record(create_time, test_type, count, score) VALUES (?,?,?,?)",
        (now, test_type, count, score)
    )
    conn.commit()
    conn.close()


def load_records_db():
    """查询全部记录，按时间倒序（最新在前）"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM test_record ORDER BY create_time DESC")
    rows = cur.fetchall()
    conn.close()
    return rows


def clear_all_db():
    """清空所有记录"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM test_record")
    conn.commit()
    conn.close()


def del_one_record_db(rec_id):
    """删除单条记录（可选）"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM test_record WHERE id=?", (rec_id,))
    conn.commit()
    conn.close()
