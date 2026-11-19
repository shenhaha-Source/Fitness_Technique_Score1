"""
生成测试提示音（不依赖第三方库）
================================

输出到 ../assets/audio/：
- beep.wav        每个有效动作一声
- start_tone.wav  开始测试的上行提示音
- stop.wav        结束测试的下行提示音

运行：
    python -X utf8 tools/make_tones.py
"""

import math
import os
import struct
import wave

RATE = 22050
AMP = 0.30


def tone(freq: float, ms: int, amp: float = AMP, fade_ms: int = 6):
    n = int(RATE * ms / 1000)
    fade = max(1, int(RATE * fade_ms / 1000))
    samples = []
    for i in range(n):
        env = min(1.0, i / fade, (n - 1 - i) / fade)
        samples.append(int(32767 * amp * env * math.sin(2 * math.pi * freq * i / RATE)))
    return samples


def silence(ms: int):
    return [0] * int(RATE * ms / 1000)


def write_wav(path: str, samples):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(struct.pack("<%dh" % len(samples), *samples))


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = os.path.join(root, "assets", "audio")
    os.makedirs(out, exist_ok=True)

    beep = tone(880, 65, 0.26)
    write_wav(os.path.join(out, "beep.wav"), beep)

    start = (tone(523.25, 85, 0.26) + silence(18)
             + tone(659.25, 85, 0.28) + silence(18)
             + tone(783.99, 130, 0.30))
    write_wav(os.path.join(out, "start_tone.wav"), start)

    stop = tone(783.99, 110, 0.28) + silence(18) + tone(523.25, 190, 0.26)
    write_wav(os.path.join(out, "stop.wav"), stop)

    for name in ("beep.wav", "start_tone.wav", "stop.wav"):
        path = os.path.join(out, name)
        with wave.open(path, "rb") as w:
            duration = w.getnframes() / w.getframerate()
        print("%-16s %6.2f s  %d bytes" % (name, duration, os.path.getsize(path)))


if __name__ == "__main__":
    main()
