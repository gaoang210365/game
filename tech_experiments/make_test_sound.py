"""
生成 exp02 用的恐怖音效（无需外部素材）。

输出两个文件到 assets/sounds/：
  1. test_beacon.wav    —— 单声道、可 3D 定位的"移动音源"（值夜护士感）
  2. horror_ambience.wav —— 立体声恐怖背景氛围（不定位，铺底）

设计原则（配合"声音先于视觉"）：
  - 移动音源保留中高频不谐和金属撞击，利于左右/远近定位；
  - 背景氛围集中在低频与缓慢音簇，音量压低，避免掩盖定位线索。

运行：
    game_env\Scripts\python.exe tech_experiments\make_test_sound.py
"""

import os
import wave
import math
import numpy as np

SR = 44100


def _write_wav(path, data, channels):
    """data: float32 in [-1,1]; 单声道 shape=(n,)，立体声 shape=(n,2)。"""
    data = np.clip(data, -1.0, 1.0)
    pcm = (data * 32767).astype(np.int16)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "w") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print("WROTE", path, os.path.getsize(path), "bytes")


def _loop_fade(sig, fade_sec=0.03):
    """首尾淡入淡出，保证循环无缝。"""
    n = int(SR * fade_sec)
    if n * 2 < len(sig):
        sig[:n] *= np.linspace(0, 1, n)
        sig[-n:] *= np.linspace(1, 0, n)
    return sig


def _metallic_hit(length_sec, base_freq):
    """不谐和金属/玻璃撞击（输液架、器械感）。"""
    t = np.linspace(0, length_sec, int(SR * length_sec), endpoint=False)
    partials = [1.0, 2.76, 5.40, 8.93]  # 非整数倍 -> 金属感
    amps = [1.0, 0.6, 0.4, 0.25]
    hit = np.zeros_like(t)
    for p, a in zip(partials, amps):
        hit += a * np.sin(2 * math.pi * base_freq * p * t)
    hit *= np.exp(-t * 9.0)  # 快速衰减
    return hit


def generate_beacon(path, seconds=3.0):
    """移动音源：拍频低音 + 不规则金属撞击 + 游移高频微光。"""
    n = int(SR * seconds)
    t = np.linspace(0, seconds, n, endpoint=False)

    # 拍频低音（110 与 113.5Hz 干涉 -> 不安）
    drone = 0.30 * (np.sin(2 * math.pi * 110 * t) + np.sin(2 * math.pi * 113.5 * t))

    # 游移的高频微光（缓慢频率漂移）
    shimmer_freq = 1600 + 120 * np.sin(2 * math.pi * 0.3 * t)
    shimmer = 0.06 * np.sin(2 * math.pi * shimmer_freq * t)
    shimmer *= (0.5 + 0.5 * np.sin(2 * math.pi * 0.7 * t))  # 强度起伏

    sig = drone + shimmer

    # 不规则金属撞击（间隔不均，增强不安）
    hit_times = [0.15, 0.9, 1.35, 2.1, 2.65]
    for ht in hit_times:
        idx = int(ht * SR)
        hit = _metallic_hit(0.6, base_freq=520) * 0.5
        end = min(idx + len(hit), n)
        sig[idx:end] += hit[:end - idx]

    sig = _loop_fade(sig)
    sig = sig / (np.max(np.abs(sig)) + 1e-9) * 0.85
    _write_wav(path, sig, channels=1)


def generate_ambience(path, seconds=10.0):
    """恐怖背景氛围：深低频 sub + 缓慢不谐和音簇 + 远处金属共鸣 + 气声噪。
    立体声，铺底用，集中低/中低频以免掩盖定位线索。"""
    n = int(SR * seconds)
    t = np.linspace(0, seconds, n, endpoint=False)

    # 深沉 sub 低频（缓慢起伏）
    sub = 0.5 * np.sin(2 * math.pi * 42 * t) * (0.6 + 0.4 * np.sin(2 * math.pi * 0.08 * t))

    # 缓慢不谐和音簇（小二度 -> 压抑）
    cluster = (0.18 * np.sin(2 * math.pi * 130 * t)
               + 0.16 * np.sin(2 * math.pi * 138 * t)   # 接近半音 -> 摩擦感
               + 0.12 * np.sin(2 * math.pi * 196 * t))
    cluster *= (0.4 + 0.3 * np.sin(2 * math.pi * 0.05 * t))

    # 远处金属共鸣（偶发缓慢涌动）
    swell = np.zeros_like(t)
    for center in (2.5, 6.5):
        env = np.exp(-((t - center) ** 2) / (2 * 0.8 ** 2))
        swell += env * np.sin(2 * math.pi * 330 * t)
    swell *= 0.10

    # 极轻气声噪（滤成低频风声）
    noise = np.random.randn(n)
    # 简单低通：滑动平均
    k = 200
    kernel = np.ones(k) / k
    noise = np.convolve(noise, kernel, mode="same")
    noise *= 0.06

    mono = sub + cluster + swell + noise
    mono = _loop_fade(mono, fade_sec=0.2)
    mono = mono / (np.max(np.abs(mono)) + 1e-9) * 0.7

    # 立体声：左右轻微相位/幅度差，营造空间宽度
    left = mono * 1.0
    right = np.roll(mono, int(SR * 0.008)) * 0.95
    stereo = np.stack([left, right], axis=1)
    _write_wav(path, stereo, channels=2)


if __name__ == "__main__":
    base = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "assets", "sounds",
    )
    generate_beacon(os.path.join(base, "test_beacon.wav"))
    generate_ambience(os.path.join(base, "horror_ambience.wav"))
