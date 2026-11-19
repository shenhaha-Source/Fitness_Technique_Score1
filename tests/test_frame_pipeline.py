"""Regression coverage for the bounded live camera pipeline."""

import threading
import time
import unittest

from frame_pipeline import LatestFramePipeline


class FakeCapture:
    def __init__(self):
        self.sequence = 0
        self.released = threading.Event()

    def read(self):
        if self.released.is_set():
            return False, None
        time.sleep(0.001)
        self.sequence += 1
        return True, self.sequence

    def release(self):
        self.released.set()


class LatestFramePipelineTest(unittest.TestCase):
    def test_slow_inference_skips_stale_frames_and_runs_off_caller_thread(self):
        capture = FakeCapture()
        first_started = threading.Event()
        allow_first_to_finish = threading.Event()
        second_finished = threading.Event()
        processed = []
        opened_on = []
        caller_thread = threading.get_ident()

        def open_capture():
            opened_on.append(threading.get_ident())
            return capture

        def process(frame):
            self.assertNotEqual(threading.get_ident(), caller_thread)
            processed.append(frame)
            if len(processed) == 1:
                first_started.set()
                allow_first_to_finish.wait(timeout=2)
            elif len(processed) == 2:
                second_finished.set()
            return frame

        pipeline = LatestFramePipeline(open_capture, process)
        pipeline.start()
        try:
            self.assertTrue(first_started.wait(timeout=1))
            self.assertNotEqual(opened_on[0], caller_thread)
            deadline = time.monotonic() + 1
            while capture.sequence < 20 and time.monotonic() < deadline:
                time.sleep(0.002)
            self.assertGreaterEqual(capture.sequence, 20)

            allow_first_to_finish.set()
            self.assertTrue(second_finished.wait(timeout=1))
            self.assertGreater(processed[1], processed[0] + 1)

            latest = pipeline.latest_frame()
            self.assertEqual(latest[0], latest[1])
        finally:
            allow_first_to_finish.set()
            pipeline.stop()


if __name__ == "__main__":
    unittest.main(verbosity=2)
