"""
数据库写锁回归测试
==================

背景：
重复用户名注册会触发 sqlite3.IntegrityError。旧版 add_user() 在
except 分支直接 return，没有关闭连接；未回滚的 INSERT 事务继续持有
SQLite 写锁，导致之后所有 create_session() 卡到超时，表现为“登录失败”。

这些测试在临时数据库上运行，不会碰项目里的 record.db。
运行：
    python -X utf8 -m unittest discover -s tests -v
"""

import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

# 让测试可以直接从项目根目录运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db


class DatabaseLockRegressionTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="fitness_db_lock_")
        self.old_db_path = db.DB_PATH
        self.old_db_timeout = getattr(db, "DB_TIMEOUT", 5)
        db.DB_PATH = os.path.join(self.tmp_dir, "test.db")
        # 测试里不要等 5 秒；一旦有锁，1 秒就暴露出来
        db.DB_TIMEOUT = 1
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.old_db_path
        db.DB_TIMEOUT = self.old_db_timeout
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def assert_database_is_writable(self):
        """独立连接能立刻拿到写锁，说明没有残留事务。"""
        conn = sqlite3.connect(db.DB_PATH, timeout=1)
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.rollback()
        finally:
            conn.close()

    def test_duplicate_registration_does_not_hold_write_lock(self):
        self.assertFalse(db.add_user("tea01", "wrong", "teacher", "重复老师", "T999"))
        self.assert_database_is_writable()

    def test_login_after_duplicate_registration(self):
        self.assertFalse(db.add_user("tea01", "wrong", "teacher", "重复老师", "T999"))

        user = db.login_user("tea01", "123456")
        self.assertIsNotNone(user)
        self.assertEqual(user["username"], "tea01")

        sid = db.create_session(user["uid"])
        self.assertTrue(sid)

        current = db.check_session(sid)
        self.assertIsNotNone(current)
        self.assertEqual(current["uid"], user["uid"])

    def test_twenty_duplicate_registrations_then_login(self):
        for _ in range(20):
            self.assertFalse(db.add_user("tea01", "wrong", "teacher", "重复老师", "T999"))

        self.assert_database_is_writable()
        self.assertIsNotNone(db.login_user("tea01", "123456"))

    def test_new_student_registration_and_score_update_still_work(self):
        self.assertTrue(db.add_user("stu_lock", "pw123", "student", "锁测试学生", "2026001"))
        user = db.login_user("stu_lock", "pw123")
        self.assertIsNotNone(user)

        self.assertTrue(db.update_best_score(user["uid"], "squat", 12))
        self.assertFalse(db.update_best_score(user["uid"], "squat", 11))
        best = db.get_student_best(user["uid"])
        self.assertEqual(best["squat"], 12)
        self.assertGreater(best["squat_score"], 0)

    def test_face_record_after_duplicate_registration(self):
        self.assertFalse(db.add_user("tea01", "wrong", "teacher", "重复老师", "T999"))

        user = db.login_user("tea01", "123456")
        self.assertIsNotNone(user)
        db.add_face_record(user["uid"], 88.5)

        conn = sqlite3.connect(db.DB_PATH, timeout=1)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM face_fun_record WHERE user_id=?",
                (user["uid"],),
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(count, 1)

    def test_delete_score_after_duplicate_registration(self):
        self.assertFalse(db.add_user("tea01", "wrong", "teacher", "重复老师", "T999"))
        self.assertTrue(db.add_user("stu_del", "pw123", "student", "待删除学生", "2026002"))
        user = db.login_user("stu_del", "pw123")
        db.update_best_score(user["uid"], "pushup", 20)

        self.assertTrue(db.delete_student_score("待删除学生"))
        self.assertEqual(db.get_student_best(user["uid"])["pushup"], 0)

    def test_teacher_query_after_duplicate_registration(self):
        self.assertFalse(db.add_user("tea01", "wrong", "teacher", "重复老师", "T999"))
        self.assertTrue(db.add_user("stu_q", "pw123", "student", "查询学生", "2026003"))

        rows = db.get_all_student_score_for_teacher()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "查询学生")


if __name__ == "__main__":
    unittest.main(verbosity=2)
