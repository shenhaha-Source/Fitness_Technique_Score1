"""
音效层回归测试
==============

覆盖：
- 计数到 cue 的映射（普通提示音 / 每 5 个语音 / 跨多个 5 的处理）
- 预生成 WAV 是否存在、格式是否正确
- AudioPlayer 的串行播放与静音

不依赖真实扬声器：AudioPlayer 测试使用 play_fn 记录播放路径。
运行：
    python -X utf8 -m unittest discover -s tests -v
"""

import os
import sys
import time
import unittest
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import audio


class CountCueTest(unittest.TestCase):
    def test_ordinary_rep_uses_beep(self):
        self.assertEqual(audio.select_count_cue(0, 1, 30), "beep")
        self.assertEqual(audio.select_count_cue(1, 2, 30), "beep")

    def test_fifth_rep_uses_voice_not_beep(self):
        self.assertEqual(audio.select_count_cue(4, 5, 30), "count_05")
        self.assertEqual(audio.select_count_cue(9, 10, 30), "count_10")

    def test_jump_over_five_uses_the_latest_multiple(self):
        self.assertEqual(audio.select_count_cue(4, 6, 30), "count_05")
        self.assertEqual(audio.select_count_cue(14, 16, 30), "count_15")

    def test_target_limits_voice_announcements(self):
        self.assertEqual(audio.select_count_cue(0, 5, 15), "count_05")
        self.assertEqual(audio.select_count_cue(15, 16, 15), "beep")
        self.assertEqual(audio.select_count_cue(30, 31, 30), "beep")

    def test_no_change_and_reset_return_none(self):
        self.assertIsNone(audio.select_count_cue(5, 5, 30))
        self.assertIsNone(audio.select_count_cue(6, 5, 30))
        self.assertIsNone(audio.select_count_cue(0, 0, 30))


class AudioAssetsTest(unittest.TestCase):
    REQUIRED = ["beep", "start_tone", "start", "stop"] + [
        "count_%02d" % n for n in range(5, 31, 5)
    ]

    def test_all_required_wavs_exist_and_are_valid(self):
        audio_dir = os.path.join(audio.asset_root(), "assets", "audio")
        for name in self.REQUIRED:
            path = os.path.join(audio_dir, name + ".wav")
            self.assertTrue(os.path.exists(path), path)
            with wave.open(path, "rb") as w:
                self.assertEqual(w.getnchannels(), 1, path)
                self.assertEqual(w.getsampwidth(), 2, path)
                self.assertGreater(w.getnframes(), 0, path)
                self.assertGreater(w.getnframes() / w.getframerate(), 0.02, path)


class AudioPlayerTest(unittest.TestCase):
    def test_start_sequence_plays_in_order_and_mute_blocks(self):
        played = []
        player = audio.AudioPlayer(play_fn=lambda p: played.append(os.path.basename(p)))
        try:
            player.play_sequence(("start_tone", "start"))
            time.sleep(1.1)
            self.assertEqual(played[:2], ["start_tone.wav", "start.wav"])

            player.set_muted(True)
            player.play("beep")
            time.sleep(0.2)
            self.assertEqual(len(played), 2)

            player.set_muted(False)
            player.play("beep")
            time.sleep(0.2)
            self.assertEqual(played[-1], "beep.wav")
        finally:
            player.stop()


if __name__ == "__main__":
    unittest.main(verbosity=2)
