"""Latest-frame camera and inference pipeline."""

import threading


class LatestFramePipeline:
    """Capture and inference workers with a single replaceable frame slot."""

    def __init__(self, capture, process_frame):
        self.capture = capture if hasattr(capture, "read") else None
        self.capture_factory = None if self.capture is not None else capture
        self.process_frame = process_frame
        self._condition = threading.Condition()
        self._stopping = threading.Event()
        self._frame = None
        self._frame_sequence = 0
        self._result = None
        self._result_sequence = 0
        self.error = None
        self._capture_thread = None
        self._process_thread = None

    def start(self):
        self._capture_thread = threading.Thread(
            target=self._capture_loop, name="camera-capture", daemon=True
        )
        self._process_thread = threading.Thread(
            target=self._process_loop, name="frame-inference", daemon=True
        )
        self._capture_thread.start()
        self._process_thread.start()

    def _capture_loop(self):
        try:
            if self.capture is None:
                self.capture = self.capture_factory()
                if self.capture is None:
                    self.error = "摄像头打开失败"
                    return
            while not self._stopping.is_set():
                ok, frame = self.capture.read()
                if not ok:
                    if not self._stopping.is_set():
                        self.error = "摄像头读取失败"
                    break
                with self._condition:
                    self._frame_sequence += 1
                    self._frame = (self._frame_sequence, frame)
                    self._condition.notify()
        except Exception as exc:
            if not self._stopping.is_set():
                self.error = str(exc)
        finally:
            if self.capture is not None:
                self.capture.release()
            with self._condition:
                self._condition.notify_all()

    def _process_loop(self):
        processed_sequence = 0
        while not self._stopping.is_set():
            with self._condition:
                self._condition.wait_for(
                    lambda: self._stopping.is_set()
                    or (self._frame is not None and self._frame[0] > processed_sequence),
                    timeout=0.25,
                )
                if self._stopping.is_set():
                    return
                sequence, frame = self._frame
            try:
                result = self.process_frame(frame)
            except Exception as exc:
                self.error = str(exc)
                return
            processed_sequence = sequence
            with self._condition:
                self._result_sequence += 1
                self._result = (sequence, frame, result)
                self._condition.notify_all()

    def latest_frame(self):
        with self._condition:
            return self._frame

    def latest_result(self, after_sequence=0):
        with self._condition:
            if self._result is None or self._result_sequence <= after_sequence:
                return None
            return self._result_sequence, self._result

    def stop(self):
        self._stopping.set()
        with self._condition:
            self._condition.notify_all()
        if self.capture is not None:
            self.capture.release()
