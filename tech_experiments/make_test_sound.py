"""
生成 exp02 用的测试音效（无需外部素材）。

生成一个带轻微脉冲的低频循环音，模拟"输液瓶碰撞/设备嗡鸣"类恐怖音源，
输出到 assets/sounds/test_beacon.wav。

运行：
    game_env\Scripts\python.exe tech_experiments\make_test_sound.py
"""

import os
import wave
import struct
import math
import numpy as np


def generate(path, seconds=2.0, sample_rate=44100):
    t = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)

    # 低频基音 + 泛音，营造机械/不安感
    base = 0.35 * np.sin(2 * math.pi * 120 * t)
    overtone = 0.15 * np.sin(2 * math.pi * 240 * t)

    # 每 0.5 秒一次的脉冲（类似玻璃碰撞）
    pulse = np.zeros_like(t)
    for k in range(int(seconds / 0.5)):
        center = k * 0.5
        env = np.exp(-((t - center) ** 2) / (2 * 0.01 ** 2))
        pulse += env * np.sin(2 * math.pi * 900 * t)
    pulse *= 0.25

    signal = base + overtone + pulse

    # 循环无缝：首尾淡入淡出到相同电平
    fade = int(sample_rate * 0.02)
    signal[:fade] *= np.linspace(0, 1, fade)
    signal[-fade:] *= np.linspace(1, 0, fade)

    # 归一化并转 16-bit PCM
    signal = signal / np.max(np.abs(signal)) * 0.8
    pcm = (signal * 32767).astype(np.int16)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "w") as w:
        w.setnchannels(1)       # 单声道，3D 定位需要单声道
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    print("WROTE", path, os.path.getsize(path), "bytes")


if __name__ == "__main__":
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = os.path.join(here, "assets", "sounds", "test_beacon.wav")
    generate(out)
