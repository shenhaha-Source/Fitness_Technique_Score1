"""Exercise counting across posture changes and dropped detections."""

import importlib
import io
import json
import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import cv2
import numpy as np

import db
from student_view import BaseTestPage, FaceScorePage, PullUpTestPage, PushupTestPage, SquatTestPage


def setUpModule():
    global server
    with tempfile.TemporaryDirectory() as temp_dir:
        with patch.object(db, "DB_PATH", str(Path(temp_dir) / "record.db")):
            server = importlib.import_module("server")


class ExerciseCountingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ok, image = cv2.imencode(".jpg", np.zeros((8, 8, 3), dtype=np.uint8))
        assert ok
        cls.image = image.tobytes()

    def setUp(self):
        self.session = server.SessionState()

    def frame(self, landmarks=None, image=None):
        if image is None:
            image = self.image
        input_stream = io.BytesIO(len(image).to_bytes(4, "big") + image)
        output_stream = io.BytesIO()
        connection = SimpleNamespace(recv=input_stream.read, sendall=output_stream.write)
        poses = [] if landmarks is None else [landmarks]
        result = SimpleNamespace(pose_landmarks=poses, pose_world_landmarks=poses)
        with patch.object(server, "pose_detector", Mock(**{"detect.return_value": result})):
            server._handle_image_frame(connection, self.session, mode=0)
        return json.loads(output_stream.getvalue())

    @staticmethod
    def pose(**groups):
        points = [SimpleNamespace(x=i / 100, y=0.5, z=0.0) for i in range(33)]
        point_groups = {"nose": (0,), "shoulders": (11, 12), "wrists": (15, 16),
                        "hips": (23, 24), "knees": (25, 26)}
        for group, y in groups.items():
            for index in point_groups[group]:
                points[index].y = y
        return points

    def squat_pose(self, angle, rotation=0, other_angle=None, right_visibility=1):
        points = self.pose()
        rotation = math.radians(rotation)
        for side, bend, visibility in (
            (0, angle, 1),
            (1, angle if other_angle is None else other_angle, right_visibility),
        ):
            knee_x = side * 0.24
            bend = math.radians(bend)
            horizontal = 0.4 * math.sin(bend)
            points[23 + side] = SimpleNamespace(x=knee_x + horizontal * math.sin(rotation),
                                               y=0.4 * math.cos(bend), z=horizontal * math.cos(rotation),
                                               visibility=visibility)
            points[25 + side] = SimpleNamespace(x=knee_x, y=0, z=0, visibility=visibility)
            points[27 + side] = SimpleNamespace(x=knee_x, y=0.4, z=0, visibility=visibility)
        return points

    def squat_frames(self, *angles, rotation=0):
        return [self.frame(self.squat_pose(angle, rotation))["count"] for angle in angles]

    def test_squat_counts_a_complete_cycle_from_front_and_side(self):
        for rotation in (0, 45, 90):
            with self.subTest(rotation=rotation):
                self.session.reset_test(server.TEST_SQUAT)
                # Includes an initial seated pose and only one frame at each exact threshold.
                counts = self.squat_frames(130, 130, 170, 170, 140, 134, 149, 157,
                                           142, 134, 152, 160, 170, rotation=rotation)
                self.assertEqual(counts, [0] * 7 + [1] * 4 + [2, 2])
                self.assertEqual(self.session.stop_test()[1], 2)

    def test_squat_ignores_one_frame_spikes_and_asymmetric_pose(self):
        self.session.reset_test(server.TEST_SQUAT)
        self.assertEqual(self.squat_frames(170, 170, 120, 170, 170), [0] * 5)
        for _ in range(2):
            self.frame(self.squat_pose(130, other_angle=175))
        self.assertEqual(self.squat_frames(170, 170), [0, 0])
        self.assertEqual(self.squat_frames(134, 134, 165, 136, 136, 165, 165),
                         [0, 0, 0, 0, 0, 0, 1])

    def test_squat_handles_occluded_leg_and_tracking_loss(self):
        self.session.reset_test(server.TEST_SQUAT)
        standing = self.squat_pose(170, rotation=90, other_angle=110, right_visibility=0.2)
        shallow = self.squat_pose(133, rotation=90, other_angle=175, right_visibility=0.2)
        clock = SimpleNamespace(monotonic=lambda: 0)
        with patch.object(server, "time", clock):
            for pose in (standing, standing, shallow, shallow):
                self.assertEqual(self.frame(pose)["count"], 0)
            clock.monotonic = lambda: 0.3
            self.assertEqual(self.frame()["count"], 0)
            self.assertEqual(self.frame(standing)["count"], 0)
            self.assertEqual(self.frame(standing)["count"], 1)
            self.frame(shallow)
            self.frame(shallow)
            clock.monotonic = lambda: 1.3
            self.assertEqual(self.frame()["count"], 1)
            self.assertEqual(self.frame(standing)["count"], 1)
            self.assertEqual(self.frame(standing)["count"], 1)
        for response in (self.frame(), self.frame(standing[:20]), self.frame(image=b"")):
            self.assertFalse(response["success"])
            self.assertEqual((response["count"], response["score"]), (1, 3.3))
        self.session.reset_test(server.TEST_SQUAT)
        self.assertEqual(self.frame()["count"], 0)

    def test_pushup_accepts_smaller_range_but_counts_only_once(self):
        self.session.reset_test(server.TEST_PUSHUP)
        with patch.object(server, "calc_angle", side_effect=[150, 115, 105, 140, 150, 150]):
            counts = [self.frame(self.pose())["count"] for _ in range(6)]
        self.assertEqual(counts, [0, 0, 0, 0, 1, 1])
        self.assertEqual(self.frame()["count"], 1)

    def test_pull_up_counts_on_return_to_hang(self):
        self.session.reset_test(server.TEST_PULL_UP)
        hang = self.pose(nose=0.40, shoulders=0.55, wrists=0.20)
        top = self.pose(nose=0.24, shoulders=0.33, wrists=0.20)
        with patch.object(server, "calc_angle", return_value=125):
            for _ in range(server.PU_GRIP_CONFIRM_FRAMES):
                self.assertEqual(self.frame(hang)["count"], 0)
        self.assertTrue(self.session.pu_grip_started)
        with patch.object(server, "calc_angle", return_value=105):
            for _ in range(server.PU_DEBOUNCE_FRAMES):
                self.assertEqual(self.frame(top)["count"], 0)
        with patch.object(server, "calc_angle", return_value=125):
            self.assertEqual(self.frame(hang)["count"], 0)
            self.assertEqual(self.frame(hang)["count"], 1)
            self.assertEqual(self.frame(hang)["count"], 1)
        self.assertEqual(self.frame()["count"], 1)

    def test_preview_keeps_displayed_result_during_missing_pose(self):
        response = {"success": False, "tip": "未检测到", "count": 0, "score": None}
        page = Mock(is_running=True, test_type=server.TEST_SQUAT, auto_stopped=False)
        page.cap.read.return_value = (True, object())
        page.sv.send_image_frame.return_value = response
        page.img_label.winfo_width.return_value = 1
        page.img_label.winfo_height.return_value = 1
        BaseTestPage.update_frame(page)
        page.on_frame_result.assert_not_called()
        page.hint.config.assert_called_once_with(text="未检测到")
        page.after.assert_called_once()

    def preview_page(self, page_class, test_type):
        page = Mock(is_running=True, test_type=test_type, auto_stopped=False,
                    result_label=page_class.result_label, _display_count=0, _display_score=None,
                    _target=30)
        page.cap.read.return_value = (True, object())
        page.img_label.winfo_width.return_value = 1
        page.img_label.winfo_height.return_value = 1
        page.on_frame_result.side_effect = lambda res, frame: page_class.on_frame_result(page, res, frame)
        page.render_result.side_effect = lambda: page_class.render_result(page)
        page.on_start.side_effect = lambda: page_class.on_start(page)
        page.on_stop.side_effect = lambda: page_class.on_stop(page)
        return page

    def test_all_exercise_pages_keep_counts_scores_and_audio_monotonic(self):
        for page_class, test_type in ((PullUpTestPage, server.TEST_PULL_UP),
                                      (SquatTestPage, server.TEST_SQUAT),
                                      (PushupTestPage, server.TEST_PUSHUP)):
            with self.subTest(page=page_class.__name__):
                page = self.preview_page(page_class, test_type)
                expected = [(4, 40), (4, 40), (4, 40), (4, 40), (5, 50)]
                frames = [(True, 4, 40), (False, 0, 0), (True, 0, 0),
                          (True, 4, None), (True, 5, 50)]
                for (success, count, score), (display_count, display_score) in zip(frames, expected):
                    page.sv.send_image_frame.return_value = {"success": success, "count": count, "score": score}
                    BaseTestPage.update_frame(page)
                    page.info.config.assert_called_with(
                        text=f"{page_class.result_label}：{display_count}个 | 得分：{display_score}分")
                self.assertEqual(page.sv.audio.play.call_args_list, [call("beep"), call("count_05")])

    def test_face_page_keeps_best_visible_score_until_the_next_test(self):
        page = self.preview_page(FaceScorePage, server.TEST_FACE)
        for success, score, expected in ((True, 73.5, 73.5), (False, 0, 73.5),
                                         (True, 0, 73.5), (True, 72, 73.5), (True, 77, 77)):
            page.sv.send_image_frame.return_value = {"success": success, "score": score}
            BaseTestPage.update_frame(page)
            page.info.config.assert_called_with(text=f"颜值分数：{expected:.1f}（趣味，不计入成绩）")

        BaseTestPage.stop(page)
        page.info.config.assert_called_with(text="颜值分数：77.0（趣味，不计入成绩）")
        page.after_cancel.assert_called_once_with(page.after.return_value)
        with patch("student_view.cv2.VideoCapture", return_value=Mock(**{"isOpened.return_value": True})):
            BaseTestPage.start(page)
        self.assertIsNone(page._display_score)
        page.info.config.assert_called_with(text="颜值分数：计算中...")
