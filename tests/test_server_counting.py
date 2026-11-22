"""Regression tests for pose-counter responses and score persistence."""

import importlib
import json
import math
import sys
import types
import unittest
from unittest import mock


class _Vector(list):
    def __sub__(self, other):
        return _Vector(a - b for a, b in zip(self, other))


class _NumpyStub(types.ModuleType):
    uint8 = object()

    @staticmethod
    def array(value):
        return _Vector(value)

    @staticmethod
    def dot(left, right):
        return sum(a * b for a, b in zip(left, right))

    @staticmethod
    def arccos(value):
        return math.acos(value)

    @staticmethod
    def clip(value, low, high):
        return max(low, min(high, value))

    @staticmethod
    def degrees(value):
        return math.degrees(value)

    @staticmethod
    def frombuffer(data, dtype=None):
        return data


_NumpyStub.linalg = types.SimpleNamespace(norm=lambda value: math.sqrt(sum(x * x for x in value)))


class _FakeLandmarker:
    @staticmethod
    def create_from_options(options):
        return types.SimpleNamespace(detect=lambda image: types.SimpleNamespace(pose_landmarks=[]))


def _load_server_without_native_runtime():
    """Load the real handler while replacing only heavyweight runtime modules."""
    import db

    fake_cv2 = types.ModuleType("cv2")
    fake_cv2.IMREAD_COLOR = 1
    fake_cv2.COLOR_BGR2RGB = 2
    fake_cv2.imdecode = lambda data, mode: object()
    fake_cv2.cvtColor = lambda image, mode: image

    fake_vision = types.SimpleNamespace(
        PoseLandmarker=_FakeLandmarker,
        PoseLandmarkerOptions=lambda **kwargs: kwargs,
        FaceLandmarker=_FakeLandmarker,
        FaceLandmarkerOptions=lambda **kwargs: kwargs,
        RunningMode=types.SimpleNamespace(IMAGE="IMAGE"),
    )
    fake_mp = types.ModuleType("mediapipe")
    fake_mp.tasks = types.SimpleNamespace(BaseOptions=lambda **kwargs: kwargs, vision=fake_vision)
    fake_mp.Image = lambda **kwargs: kwargs
    fake_mp.ImageFormat = types.SimpleNamespace(SRGB="SRGB")
    fake_numpy = _NumpyStub("numpy")

    previous = {name: sys.modules.get(name) for name in ("cv2", "mediapipe", "numpy")}
    sys.modules.update(cv2=fake_cv2, mediapipe=fake_mp, numpy=fake_numpy)
    sys.modules.pop("server", None)
    try:
        with mock.patch.object(db, "init_db"):
            return importlib.import_module("server")
    finally:
        for name, module in previous.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


server = _load_server_without_native_runtime()


def _pose(**overrides):
    points = [types.SimpleNamespace(x=0.5, y=0.5, z=0.0, visibility=1.0) for _ in range(33)]
    for index, values in overrides.items():
        x, y = values[:2]
        visibility = values[2] if len(values) > 2 else 1.0
        points[int(index)] = types.SimpleNamespace(x=x, y=y, z=0.0, visibility=visibility)
    return [points]


def _frame(session, pose_landmarks):
    class Connection:
        def __init__(self):
            self.incoming = bytearray((1).to_bytes(4, "big") + b"x")
            self.outgoing = bytearray()

        def recv(self, size):
            chunk = self.incoming[:size]
            del self.incoming[:size]
            return bytes(chunk)

        def sendall(self, data):
            self.outgoing.extend(data)

    conn = Connection()
    with mock.patch.object(server.pose_detector, "detect", return_value=types.SimpleNamespace(pose_landmarks=pose_landmarks)), \
         mock.patch.object(server.cv2, "imdecode", return_value=object()), \
         mock.patch.object(server.cv2, "cvtColor", side_effect=lambda image, mode: image):
        server._handle_image_frame(conn, session, 0)
    return json.loads(conn.outgoing.decode("utf-8"))


class ServerCountingRegressionTest(unittest.TestCase):
    def _squat_pose(self, knee_angle):
        phi = math.radians(-90 + knee_angle)
        left_ankle = (0.4 + 0.2 * math.cos(phi), 0.55 + 0.2 * math.sin(phi))
        right_ankle = (0.6 + 0.2 * math.cos(phi), 0.55 + 0.2 * math.sin(phi))
        return _pose(**{
            "23": (0.4, 0.35), "24": (0.6, 0.35),
            "25": (0.4, 0.55), "26": (0.6, 0.55),
            "27": left_ankle, "28": right_ankle,
        })

    def _pushup_pose(self, elbow_angle):
        phi = math.radians(180 - elbow_angle)
        wrist = (1.0 + math.cos(phi), math.sin(phi))
        return _pose(**{
            "11": (0.0, 0.0), "13": (1.0, 0.0), "15": wrist,
            "12": (0.0, 0.0), "14": (1.0, 0.0), "16": wrist,
        })

    def _pullup_pose(self, nose_y):
        return _pose(**{
            "0": (0.5, nose_y),
            "11": (0.4, 0.5), "12": (0.6, 0.5),
            "13": (0.4, 0.4), "14": (0.6, 0.4),
            "15": (0.4, 0.3), "16": (0.6, 0.3),
        })

    def _complete_rep(self, test_type, session):
        if test_type == server.TEST_SQUAT:
            _frame(session, self._squat_pose(175))
            _frame(session, self._squat_pose(95))
            return _frame(session, self._squat_pose(170))
        if test_type == server.TEST_PUSHUP:
            _frame(session, self._pushup_pose(175))
            _frame(session, self._pushup_pose(60))
            return _frame(session, self._pushup_pose(170))
        for _ in range(server.PU_GRIP_CONFIRM_FRAMES):
            _frame(session, self._pullup_pose(0.55))
        _frame(session, self._pullup_pose(0.40))
        _frame(session, self._pullup_pose(0.40))
        _frame(session, self._pullup_pose(0.55))
        return _frame(session, self._pullup_pose(0.55))

    def test_each_exercise_counts_a_complete_rep(self):
        for test_type in (server.TEST_SQUAT, server.TEST_PUSHUP, server.TEST_PULL_UP):
            with self.subTest(test_type=test_type):
                session = server.SessionState()
                session.reset_test(test_type)
                result = self._complete_rep(test_type, session)
                self.assertEqual(result["count"], 1)

    def test_short_pose_drop_mid_rep_preserves_counter_state(self):
        squat = server.SessionState()
        squat.reset_test(server.TEST_SQUAT)
        _frame(squat, self._squat_pose(175))
        _frame(squat, self._squat_pose(95))
        _frame(squat, [])
        self.assertEqual(_frame(squat, self._squat_pose(170))["count"], 1)

        pushup = server.SessionState()
        pushup.reset_test(server.TEST_PUSHUP)
        _frame(pushup, self._pushup_pose(175))
        _frame(pushup, self._pushup_pose(60))
        _frame(pushup, [])
        self.assertEqual(_frame(pushup, self._pushup_pose(170))["count"], 1)

        pullup = server.SessionState()
        pullup.reset_test(server.TEST_PULL_UP)
        for _ in range(server.PU_GRIP_CONFIRM_FRAMES):
            _frame(pullup, self._pullup_pose(0.55))
        _frame(pullup, self._pullup_pose(0.40))
        _frame(pullup, self._pullup_pose(0.40))
        _frame(pullup, [])
        _frame(pullup, self._pullup_pose(0.55))
        self.assertEqual(_frame(pullup, self._pullup_pose(0.55))["count"], 1)

    def test_missing_optional_visibility_does_not_hide_valid_landmarks(self):
        session = server.SessionState()
        session.reset_test(server.TEST_PUSHUP)
        for angle in (175, 60, 170):
            pose = self._pushup_pose(angle)
            for point in pose[0]:
                point.visibility = None
                point.presence = None
            result = _frame(session, pose)
        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 1)

    def test_low_confidence_required_joints_do_not_count_or_clear_score(self):
        cases = (
            (server.TEST_SQUAT, self._squat_pose(175), (23, 25, 27, 24, 26, 28)),
            (server.TEST_PUSHUP, self._pushup_pose(175), (11, 13, 15, 12, 14, 16)),
            (server.TEST_PULL_UP, self._pullup_pose(0.55), (0, 11, 12, 13, 14, 15, 16)),
        )
        for test_type, pose, indices in cases:
            with self.subTest(test_type=test_type):
                session = server.SessionState()
                session.reset_test(test_type)
                for index in indices:
                    pose[0][index].visibility = 0.1
                result = _frame(session, pose)
                self.assertFalse(result["success"])
                self.assertEqual(result["count"], 0)
                self.assertIn("入镜", result["tip"])

    def test_wrong_or_incomplete_motion_does_not_count(self):
        squat = server.SessionState()
        squat.reset_test(server.TEST_SQUAT)
        _frame(squat, self._squat_pose(175))
        result = _frame(squat, self._squat_pose(130))
        self.assertEqual(result["count"], 0)

        pushup = server.SessionState()
        pushup.reset_test(server.TEST_PUSHUP)
        _frame(pushup, self._pushup_pose(175))
        _frame(pushup, self._pushup_pose(130))  # not below the down threshold
        result = _frame(pushup, self._pushup_pose(175))
        self.assertEqual(result["count"], 0)

        pullup = server.SessionState()
        pullup.reset_test(server.TEST_PULL_UP)
        result = _frame(pullup, self._pullup_pose(0.40))  # pulling without confirmed grip
        self.assertEqual(result["count"], 0)

    def test_brief_pose_drop_keeps_the_visible_count_for_every_exercise(self):
        for test_type in (server.TEST_SQUAT, server.TEST_PUSHUP, server.TEST_PULL_UP):
            with self.subTest(test_type=test_type):
                session = server.SessionState()
                session.reset_test(test_type)
                self._complete_rep(test_type, session)
                result = _frame(session, [])
                self.assertFalse(result["success"])
                self.assertEqual(result["count"], 1)
                self.assertGreater(result["score"], 0)

    def test_stop_saves_the_current_count_for_each_exercise(self):
        mappings = (
            (server.TEST_SQUAT, "squat"),
            (server.TEST_PULL_UP, "pull_up"),
            (server.TEST_PUSHUP, "pushup"),
        )
        for test_type, column in mappings:
            with self.subTest(test_type=test_type):
                session = server.SessionState()
                session.user = {"uid": 7, "name": "Test"}
                session.reset_test(test_type)
                self._complete_rep(test_type, session)
                self.assertEqual(session.current_count(), 1)
                with mock.patch.object(server, "update_best_score") as save, mock.patch.object(server, "send_json"):
                    server._handle_business_command(None, session, server.CMD_STOP_TEST)
                save.assert_called_once_with(7, column, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
