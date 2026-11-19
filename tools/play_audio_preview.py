"""
试听音效
========

不启动摄像头、不启动服务端，直接按顺序播放 WAV。

默认播放全部：
    python -X utf8 tools/play_audio_preview.py

只播放某一组：
    python -X utf8 tools/play_audio_preview.py start
    python -X utf8 tools/play_audio_preview.py rep
    python -X utf8 tools/play_audio_preview.py count
    python -X utf8 tools/play_audio_preview.py stop

只列出文件：
    python -X utf8 tools/play_audio_preview.py --list
"""

import os
import sys
import time
import wave

try:
    import winsound
except ImportError:
    winsound = None

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from audio import _prepare_audio_dir, asset_root  # noqa: E402


GROUPS = {
    "start": [
        ("start_tone", "开始提示音（上行三音）"),
        ("start", "语音：开始测试"),
    ],
    "rep": [
        ("beep", "单次动作提示音"),
        ("beep", "单次动作提示音（再听一次）"),
        ("beep", "单次动作提示音（最后一遍）"),
    ],
    "count": [
        ("count_05", "第 5 个：已经做了五个了"),
        ("count_10", "第 10 个：已经做了十个了"),
        ("count_15", "第 15 个：已经做了十五个了"),
        ("count_20", "第 20 个：已经做了二十个了"),
        ("count_25", "第 25 个：已经做了二十五个了"),
        ("count_30", "第 30 个：已经做了三十个了"),
    ],
    "stop": [
        ("stop", "结束提示音（下行两音）"),
    ],
}


def wav_duration(path):
    try:
        with wave.open(path, "rb") as w:
            return w.getnframes() / (w.getframerate() or 1)
    except Exception:
        return 0.0


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    src = os.path.join(asset_root(), "assets", "audio")
    audio_dir = _prepare_audio_dir(src)

    if "--list" in sys.argv:
        for group, items in GROUPS.items():
            print("[%s]" % group)
            for name, label in items:
                path = os.path.join(audio_dir, name + ".wav")
                print("  %-12s %5.2fs  %s" % (name, wav_duration(path), path))
        return

    selected = args or list(GROUPS.keys())
    if winsound is None:
        print("winsound 不可用，无法播放。")
        return

    print("音频目录：", audio_dir)
    print("按 Ctrl+C 可停止。")

    for group in selected:
        if group not in GROUPS:
            print("未知组：", group)
            continue
        print("\n== %s ==" % group)
        for name, label in GROUPS[group]:
            path = os.path.join(audio_dir, name + ".wav")
            if not os.path.exists(path):
                print("  缺失：", path)
                continue
            print("  %s  (%.2fs)" % (label, wav_duration(path)))
            winsound.PlaySound(
                path,
                winsound.SND_FILENAME | winsound.SND_NODEFAULT,
            )
            time.sleep(0.25)

    print("\n试听结束。")


if __name__ == "__main__":
    main()
