"""
裁剪 SAPI 生成的语音首尾静音，并统一响度。

SAPI 的 SetOutputToWaveFile 会在句首/句尾留 0.5–0.8 秒静音。
这会拖长播放时间，影响“每 5 个报数”的实时性。

运行：
    python -X utf8 tools/trim_voice.py
"""

import os
import wave

import numpy as np


def trim(path: str, margin_sec: float = 0.05, target_peak: float = 0.65):
    with wave.open(path, "rb") as w:
        params = w.getparams()
        raw = w.readframes(w.getnframes())

    data = np.frombuffer(raw, dtype="<i2").astype(np.float32)
    if data.size == 0:
        return
    peak = float(np.abs(data).max())
    if peak <= 1:
        return

    threshold = max(400.0, peak * 0.02)
    idx = np.where(np.abs(data) > threshold)[0]
    if idx.size == 0:
        return

    rate = params.framerate
    margin = int(rate * margin_sec)
    start = max(0, int(idx[0]) - margin)
    end = min(len(data), int(idx[-1]) + margin)
    data = data[start:end]

    # 统一响度，让语音比提示音更清楚
    peak = float(np.abs(data).max())
    if peak > 1:
        data = data * (target_peak * 32767.0 / peak)
    data = np.clip(data, -32768, 32767).astype("<i2")

    with wave.open(path, "wb") as w:
        w.setnchannels(params.nchannels)
        w.setsampwidth(params.sampwidth)
        w.setframerate(params.framerate)
        w.writeframes(data.tobytes())


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    audio = os.path.join(root, "assets", "audio")
    names = ["start.wav"] + ["count_%02d.wav" % n for n in range(5, 31, 5)]
    for name in names:
        path = os.path.join(audio, name)
        if not os.path.exists(path):
            print("skip", name)
            continue
        with wave.open(path, "rb") as w:
            before = w.getnframes() / w.getframerate()
        trim(path)
        with wave.open(path, "rb") as w:
            after = w.getnframes() / w.getframerate()
        print("%-14s %.2fs -> %.2fs" % (name, before, after))


if __name__ == "__main__":
    main()
