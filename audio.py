"""
音效播放层
==========

用 winsound 异步播放预生成 WAV。播放放在独立线程里串行执行，
Tk 主线程只负责 enqueue，不会被音频/文件 IO 阻塞。

设计要点：
- 不依赖网络，不在运行时调用 TTS。
- 第 5/10/... 个动作只播语音，不播提示音，避免单声道互相打断。
- 无人/出画时服务端可能返回 count=0，调用方只在 success=True 时喂数据。
- 路径含中文时，先把 WAV 复制到系统临时目录（ASCII）再播放。
"""

import os
import queue
import shutil
import sys
import tempfile
import threading
import time
import wave

try:
    import winsound
except ImportError:  # 非 Windows 环境下的降级
    winsound = None


AUDIO_SUBDIR = os.path.join("assets", "audio")
MAX_QUEUE = 6


def asset_root() -> str:
    if hasattr(sys, "_MEIPASS"):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _prepare_audio_dir(src: str) -> str:
    """复制到 ASCII 临时目录，规避中文路径下 winsound 的兼容性问题。"""
    try:
        dst = os.path.join(tempfile.gettempdir(), "fitness_audio")
        os.makedirs(dst, exist_ok=True)
        for name in os.listdir(src):
            if not name.lower().endswith(".wav"):
                continue
            s = os.path.join(src, name)
            d = os.path.join(dst, name)
            if (not os.path.exists(d)
                    or os.path.getsize(s) != os.path.getsize(d)
                    or os.path.getmtime(s) > os.path.getmtime(d)):
                shutil.copy2(s, d)
        return dst
    except Exception as exc:
        print("audio copy skipped:", exc)
        return src


def select_count_cue(last_count, count, target):
    """
    根据计数变化选择 cue 名称。

    - 普通动作 -> beep
    - 跨过 5 的倍数（且未超过满分次数）-> count_05 / count_10 / ...
    - 没有新动作或计数回退 -> None

    计数一次跳多个时（例如 4 -> 6），只播最近跨过的那个 5 的倍数。
    """
    try:
        last_count = int(last_count or 0)
        count = int(count or 0)
        target = int(target or 0)
    except (TypeError, ValueError):
        return None

    if count <= last_count:
        return None

    multiple = (count // 5) * 5
    if multiple > last_count and 0 < multiple <= target:
        return "count_%02d" % multiple
    return "beep"


class AudioPlayer:
    def __init__(self, audio_dir=None, play_fn=None, muted=False):
        self.src_dir = audio_dir or os.path.join(asset_root(), AUDIO_SUBDIR)
        if os.path.isdir(self.src_dir):
            self.audio_dir = _prepare_audio_dir(self.src_dir)
        else:
            self.audio_dir = self.src_dir

        self._play_fn = play_fn
        self._muted = bool(muted)
        self._durations = {}
        self._load_durations()

        self._q = queue.Queue(maxsize=MAX_QUEUE)
        self._stop_event = threading.Event()
        self._warned = set()
        self._enabled = play_fn is not None or winsound is not None
        self._thread = None
        if self._enabled:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def _load_durations(self):
        try:
            names = os.listdir(self.audio_dir)
        except OSError:
            return
        for name in names:
            if not name.lower().endswith(".wav"):
                continue
            path = os.path.join(self.audio_dir, name)
            try:
                with wave.open(path, "rb") as w:
                    frames = w.getnframes()
                    rate = w.getframerate() or 1
                    self._durations[name[:-4]] = frames / rate
            except Exception:
                self._durations[name[:-4]] = 0.25

    @property
    def muted(self) -> bool:
        return self._muted

    def set_muted(self, muted: bool):
        self._muted = bool(muted)
        if self._muted:
            self.clear()
            if winsound is not None:
                try:
                    winsound.PlaySound(None, winsound.SND_PURGE)
                except Exception:
                    pass

    def toggle_muted(self) -> bool:
        self.set_muted(not self._muted)
        return self._muted

    def clear(self):
        try:
            while True:
                self._q.get_nowait()
        except queue.Empty:
            pass

    def play(self, name: str):
        if not self._enabled or self._muted:
            return
        try:
            self._q.put_nowait(name)
        except queue.Full:
            # 丢掉最旧的一条，保证最新反馈能进来
            try:
                self._q.get_nowait()
                self._q.put_nowait(name)
            except Exception:
                pass

    def play_sequence(self, names):
        for name in names:
            self.play(name)

    def _run(self):
        while not self._stop_event.is_set():
            try:
                name = self._q.get(timeout=0.2)
            except queue.Empty:
                continue
            if name is None:
                break
            if self._muted or self._stop_event.is_set():
                continue

            path = os.path.join(self.audio_dir, name + ".wav")
            if not os.path.exists(path):
                if name not in self._warned:
                    print("audio missing:", path)
                    self._warned.add(name)
                continue

            try:
                if self._play_fn is not None:
                    self._play_fn(path)
                else:
                    winsound.PlaySound(
                        path,
                        winsound.SND_FILENAME
                        | winsound.SND_ASYNC
                        | winsound.SND_NODEFAULT,
                    )

                # 串行等待本段播完，避免下一条提示音打断语音。
                # 语音额外留 0.2s 尾巴，抵消系统音频缓冲/蓝牙延迟，
                # 否则下一条 beep 可能在“开始/报数”最后一个字之前响起。
                duration = float(self._durations.get(name, 0.25))
                if name == "start" or name.startswith("count_"):
                    duration += 0.20
                end = time.monotonic() + duration
                while (not self._stop_event.is_set()
                       and time.monotonic() < end):
                    time.sleep(min(0.03, max(0.0, end - time.monotonic())))
            except Exception as exc:
                print("audio play error:", name, exc)
                time.sleep(0.05)

    def stop(self):
        self._stop_event.set()
        self.clear()
        try:
            self._q.put_nowait(None)
        except Exception:
            pass
        if winsound is not None:
            try:
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
