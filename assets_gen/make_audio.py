"""
回声病房 / Echo Ward - 程序化音频生成

不依赖任何外部素材，用 numpy 合成本作所需的全部音频，输出到 assets/sounds/
与 assets/music/。对应音频设计文档（08）的六层音频结构。

生成内容：
  音乐：  menu_theme（主菜单）、chase（追逐，克制）、ending（结局）
  环境：  ambient_ward（住院部底噪）、ambient_basement（地下）
  怪物：  nurse_iv_clink（输液瓶玻璃碰撞·核心识别音）、nurse_drag（拖行输液架）、
          nurse_breath（失真呼吸）
  玩家：  footstep（脚步）、heartbeat（心跳）、door（开关门）、pickup（拾取）、
          flashlight_click（手电开关）
  提示：  stinger（惊吓短音）、save_blip（存档提示）

运行：
    game_env\Scripts\python.exe assets_gen\make_audio.py
可选参数 --force 覆盖已存在文件（默认跳过已存在的，避免重复生成）。
"""

import os
import sys
import math
import wave
import numpy as np

SR = 44100

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOUNDS_DIR = os.path.join(ROOT, "assets", "sounds")
MUSIC_DIR = os.path.join(ROOT, "assets", "music")


# ----------------- 基础工具 -----------------

def _write_wav(path, data, channels):
    """data: float32 in [-1,1]；单声道 shape=(n,)，立体声 shape=(n,2)。"""
    data = np.clip(data, -1.0, 1.0)
    pcm = (data * 32767).astype(np.int16)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "w") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print("WROTE", os.path.relpath(path, ROOT), os.path.getsize(path), "bytes")


def _t(seconds):
    return np.linspace(0, seconds, int(SR * seconds), endpoint=False)


def _fade(sig, fade_sec=0.03):
    n = int(SR * fade_sec)
    if n > 0 and n * 2 < len(sig):
        sig[:n] *= np.linspace(0, 1, n)
        sig[-n:] *= np.linspace(1, 0, n)
    return sig


def _norm(sig, peak=0.9):
    return sig / (np.max(np.abs(sig)) + 1e-9) * peak


def _lowpass(sig, k=200):
    kernel = np.ones(k) / k
    return np.convolve(sig, kernel, mode="same")


def _adsr(n, a=0.01, d=0.1, s=0.7, r=0.2):
    """简单 ADSR 包络，返回长度 n 的增益曲线。"""
    a_n, d_n, r_n = int(SR * a), int(SR * d), int(SR * r)
    a_n = min(a_n, n)
    d_n = min(d_n, max(0, n - a_n))
    r_n = min(r_n, max(0, n - a_n - d_n))
    s_n = max(0, n - a_n - d_n - r_n)
    env = np.concatenate([
        np.linspace(0, 1, a_n) if a_n else np.array([]),
        np.linspace(1, s, d_n) if d_n else np.array([]),
        np.full(s_n, s),
        np.linspace(s, 0, r_n) if r_n else np.array([]),
    ])
    if len(env) < n:
        env = np.concatenate([env, np.full(n - len(env), 0.0)])
    return env[:n]


def _tone(freq, seconds, kind="sine"):
    t = _t(seconds)
    if kind == "saw":
        return 2 * (t * freq - np.floor(0.5 + t * freq))
    if kind == "square":
        return np.sign(np.sin(2 * math.pi * freq * t))
    if kind == "tri":
        return 2 * np.abs(2 * (t * freq - np.floor(0.5 + t * freq))) - 1
    return np.sin(2 * math.pi * freq * t)


NOTE = {  # 频率表（部分）
    "A2": 110.00, "C3": 130.81, "D3": 146.83, "E3": 164.81, "F3": 174.61,
    "G3": 196.00, "A3": 220.00, "Bb3": 233.08, "C4": 261.63, "D4": 293.66,
    "Eb4": 311.13, "E4": 329.63, "F4": 349.23, "G4": 392.00, "Ab4": 415.30,
    "A4": 440.00, "Bb4": 466.16, "C5": 523.25,
}


# ----------------- 音乐 -----------------

def make_menu_theme(path, seconds=24.0):
    """主菜单：缓慢、空洞、带记忆感的钢琴式分解和弦 + 低频铺垫。
    小调 + 偶发不谐和，契合循环与失忆主题。"""
    n = int(SR * seconds)
    out = np.zeros(n)
    # 低频铺垫（A2 持续 + 缓慢起伏）
    t = _t(seconds)
    pad = 0.16 * np.sin(2 * math.pi * NOTE["A2"] * t) * (0.6 + 0.4 * np.sin(2 * math.pi * 0.06 * t))
    out += pad
    # 分解和弦进行（Am - F - C - G 的空洞版），每 3 秒一个音
    prog = ["A3", "C4", "E4", "F3", "A3", "C4", "E3", "G3",
            "C4", "E4", "G4", "D4", "F4", "A4", "E4", "G4"]
    step = seconds / len(prog)
    for i, note in enumerate(prog):
        start = int(i * step * SR)
        dur = step * 1.6  # 音符相互交叠形成延音
        note_n = int(dur * SR)
        note_n = min(note_n, n - start)
        if note_n <= 0:
            continue
        f = NOTE[note]
        seg = (np.sin(2 * math.pi * f * _t(dur)[:note_n])
               + 0.5 * np.sin(2 * math.pi * f * 2 * _t(dur)[:note_n]))
        seg *= _adsr(note_n, a=0.02, d=0.3, s=0.4, r=1.2) * 0.22
        out[start:start + note_n] += seg
    out = _fade(out, 1.0)
    out = _norm(out, 0.72)
    # 立体声轻微加宽
    left = out
    right = np.roll(out, int(SR * 0.011)) * 0.96
    _write_wav(path, np.stack([left, right], axis=1), channels=2)


def make_chase(path, seconds=16.0):
    """追逐音乐：克制但紧迫——快速低频脉动 + 不谐和高频刺 + 心跳式底鼓。
    不做旋律，避免盖过环境威胁音。"""
    n = int(SR * seconds)
    t = _t(seconds)
    # 快速脉动低音（八分音符感，145 BPM）
    bpm = 145.0
    puls = 0.5 * (0.5 + 0.5 * np.sin(2 * math.pi * (bpm / 60) * t)) ** 4
    bass = 0.32 * np.sin(2 * math.pi * 55 * t) * puls
    # 不谐和高频刺（随机颤动）
    stab = 0.10 * np.sin(2 * math.pi * 1200 * t) * (np.random.rand(n) > 0.985)
    stab = _lowpass(stab, 30)
    # 心跳式底鼓
    kick = np.zeros(n)
    beat = 60.0 / bpm
    tk = 0.0
    while tk < seconds:
        idx = int(tk * SR)
        dl = int(0.12 * SR)
        env = np.exp(-np.linspace(0, 8, min(dl, n - idx)))
        kf = 90 * np.exp(-np.linspace(0, 4, min(dl, n - idx)))  # 下扫
        kick[idx:idx + len(env)] += 0.6 * np.sin(2 * math.pi * kf * np.linspace(0, 0.12, len(env))) * env
        tk += beat
    out = _fade(bass + stab + kick, 0.2)
    _write_wav(path, _norm(out, 0.9), channels=1)


def make_ending(path, seconds=20.0):
    """结局音乐：低速、释然中带哀伤的长音铺垫（适配三结局的共用底色）。"""
    t = _t(seconds)
    chord = (0.20 * np.sin(2 * math.pi * NOTE["D3"] * t)
             + 0.16 * np.sin(2 * math.pi * NOTE["F3"] * t)
             + 0.14 * np.sin(2 * math.pi * NOTE["A3"] * t)
             + 0.10 * np.sin(2 * math.pi * NOTE["C4"] * t))
    swell = 0.5 + 0.5 * np.sin(2 * math.pi * 0.05 * t - math.pi / 2)
    out = chord * swell
    # 远处微光高频
    shimmer = 0.05 * np.sin(2 * math.pi * (1400 + 60 * np.sin(2 * math.pi * 0.2 * t)) * t)
    out += shimmer * swell
    out = _fade(out, 2.0)
    out = _norm(out, 0.7)
    right = np.roll(out, int(SR * 0.013)) * 0.95
    _write_wav(path, np.stack([out, right], axis=1), channels=2)


# ----------------- 环境底噪 -----------------

def make_ambient_ward(path, seconds=12.0):
    """住院部底噪：通风低频嗡鸣 + 日光灯电流 60Hz 哼声 + 偶发结构响动。"""
    n = int(SR * seconds)
    t = _t(seconds)
    hum = 0.22 * np.sin(2 * math.pi * 60 * t) * (0.7 + 0.3 * np.sin(2 * math.pi * 0.11 * t))
    vent = _lowpass(np.random.randn(n), 300) * 0.18
    flicker = 0.05 * np.sin(2 * math.pi * 120 * t) * (np.random.rand(n) > 0.7)
    creak = np.zeros(n)
    for c in (3.2, 8.7):
        idx = int(c * SR)
        seg = _metallic(0.5, 240) * 0.12
        creak[idx:idx + len(seg)] += seg[:max(0, n - idx)]
    mono = _fade(hum + vent + flicker + creak, 0.3)
    mono = _norm(mono, 0.6)
    right = np.roll(mono, int(SR * 0.007)) * 0.96
    _write_wav(path, np.stack([mono, right], axis=1), channels=2)


def make_horror_drone(path, seconds=30.0):
    """恐怖氛围床：深沉不谐和低频嗡鸣 + 缓慢逼近的音团 + 偶发金属尖啸/远处哀鸣。
    设计成常驻循环、音量偏大，替代原本过于安静的探索背景。"""
    n = int(SR * seconds)
    t = _t(seconds)
    rng = np.random.default_rng(66)

    # 1) 双层 sub 低频，微失谐产生缓慢拍频（不安感）
    sub = (0.45 * np.sin(2 * math.pi * 42.0 * t)
           + 0.38 * np.sin(2 * math.pi * 43.7 * t)
           + 0.30 * np.sin(2 * math.pi * 28.0 * t))
    sub *= (0.7 + 0.3 * np.sin(2 * math.pi * 0.04 * t))

    # 2) 中频不谐和音团（小二度堆叠），极慢起伏，像逼近的存在
    cluster = (0.16 * np.sin(2 * math.pi * 196 * t)
               + 0.14 * np.sin(2 * math.pi * 208 * t)
               + 0.12 * np.sin(2 * math.pi * 233 * t))
    swell = 0.5 + 0.5 * np.sin(2 * math.pi * 0.03 * t - math.pi / 2)
    cluster *= swell

    # 3) 通风/风噪铺底
    wind = _lowpass(rng.standard_normal(n), 400) * 0.22

    # 4) 偶发金属尖啸（高频下扫）与远处哀鸣
    stabs = np.zeros(n)
    ts = 2.0
    while ts < seconds - 2:
        idx = int(ts * SR)
        dl = int(rng.uniform(0.6, 1.4) * SR)
        dl = min(dl, n - idx)
        env = np.exp(-np.linspace(0, 5, dl))
        f0 = rng.uniform(900, 1600)
        f = f0 * np.exp(-np.linspace(0, 1.2, dl))  # 下扫尖啸
        stabs[idx:idx + dl] += 0.18 * np.sin(2 * math.pi * f * np.linspace(0, dl / SR, dl)) * env
        ts += rng.uniform(4.0, 8.0)

    # 5) 远处人声哀鸣（带失真的低频共振团）
    moan = np.zeros(n)
    for mt in (7.0, 19.0):
        idx = int(mt * SR)
        dl = min(int(2.5 * SR), n - idx)
        mtt = np.linspace(0, 2.5, dl)
        base = 130 + 12 * np.sin(2 * math.pi * 0.8 * mtt)
        seg = np.sin(2 * math.pi * base * mtt) + 0.5 * np.sin(2 * math.pi * base * 2 * mtt)
        seg = np.tanh(seg * 1.6) * np.exp(-((mtt - 1.25) ** 2) / 0.7) * 0.22
        moan[idx:idx + dl] += seg

    mono = sub + cluster + wind + stabs + moan
    mono = _fade(mono, 1.5)
    mono = _norm(mono, 0.95)   # 偏大音量
    right = np.roll(mono, int(SR * 0.012)) * 0.97
    _write_wav(path, np.stack([mono, right], axis=1), channels=2)


def make_ambient_basement(path, seconds=12.0):
    """地下底噪：更深的 sub 低频 + 滴水 + 管道回声。"""
    n = int(SR * seconds)
    t = _t(seconds)
    sub = 0.4 * np.sin(2 * math.pi * 38 * t) * (0.6 + 0.4 * np.sin(2 * math.pi * 0.05 * t))
    rumble = _lowpass(np.random.randn(n), 500) * 0.16
    drips = np.zeros(n)
    rng = np.random.default_rng(7)
    dt = 0.0
    while dt < seconds:
        idx = int(dt * SR)
        dl = int(0.08 * SR)
        env = np.exp(-np.linspace(0, 30, min(dl, n - idx)))
        f = 900 + rng.uniform(-100, 200)
        drips[idx:idx + len(env)] += 0.25 * np.sin(2 * math.pi * f * np.linspace(0, 0.08, len(env))) * env
        dt += rng.uniform(1.5, 3.5)
    mono = _fade(sub + rumble + drips, 0.3)
    mono = _norm(mono, 0.6)
    right = np.roll(mono, int(SR * 0.009)) * 0.95
    _write_wav(path, np.stack([mono, right], axis=1), channels=2)


# ----------------- 怪物标识音 -----------------

def _metallic(length_sec, base_freq):
    t = _t(length_sec)
    partials = [1.0, 2.76, 5.40, 8.93]
    amps = [1.0, 0.6, 0.4, 0.25]
    hit = sum(a * np.sin(2 * math.pi * base_freq * p * t) for p, a in zip(partials, amps))
    hit *= np.exp(-t * 9.0)
    return hit


def make_nurse_iv_clink(path, seconds=2.6):
    """核心识别音：输液瓶玻璃碰撞。清脆玻璃质感 + 轻微余韵，单声道便于 3D 定位。"""
    n = int(SR * seconds)
    sig = np.zeros(n)
    times = [0.1, 0.55, 0.7, 1.4, 2.0]  # 不规则玻璃相碰
    for ht in times:
        idx = int(ht * SR)
        # 玻璃：高频非谐 + 快衰减
        gl = _metallic(0.5, base_freq=1400 + np.random.uniform(-80, 120)) * 0.6
        end = min(idx + len(gl), n)
        sig[idx:end] += gl[:end - idx]
    sig = _fade(sig, 0.02)
    _write_wav(path, _norm(sig, 0.85), channels=1)


def make_nurse_drag(path, seconds=3.0):
    """拖行输液架金属声：低频摩擦 + 间歇轮子吱声 + 金属轻响。"""
    n = int(SR * seconds)
    t = _t(seconds)
    friction = _lowpass(np.random.randn(n), 120) * 0.3 * (0.5 + 0.5 * np.sin(2 * math.pi * 1.5 * t))
    squeak = 0.12 * np.sin(2 * math.pi * (700 + 200 * np.sin(2 * math.pi * 2.0 * t)) * t)
    squeak *= (np.sin(2 * math.pi * 1.5 * t) > 0.6)
    clink = np.zeros(n)
    for ht in (0.8, 1.9, 2.6):
        idx = int(ht * SR)
        seg = _metallic(0.4, 520) * 0.3
        clink[idx:idx + len(seg)] += seg[:max(0, n - idx)]
    sig = _fade(friction + squeak + clink, 0.1)
    _write_wav(path, _norm(sig, 0.8), channels=1)


def make_nurse_breath(path, seconds=3.2):
    """失真呼吸：带噪的周期性吸呼 + 轻微金属化共振。"""
    n = int(SR * seconds)
    t = _t(seconds)
    cycle = 0.5 + 0.5 * np.sin(2 * math.pi * 0.55 * t - math.pi / 2)  # 呼吸周期
    breath = _lowpass(np.random.randn(n), 260) * cycle * 0.5
    # 失真：轻度削波 + 共振
    breath = np.tanh(breath * 3.0) * 0.4
    reson = 0.06 * np.sin(2 * math.pi * 320 * t) * cycle
    sig = _fade(breath + reson, 0.15)
    _write_wav(path, _norm(sig, 0.75), channels=1)


# ----------------- 玩家反馈 -----------------

def make_footstep(path):
    """单步脚步：短促低频冲击 + 轻噪，硬地面感。"""
    seconds = 0.22
    n = int(SR * seconds)
    t = _t(seconds)
    thud = np.sin(2 * math.pi * 90 * t) * np.exp(-t * 30)
    click = _lowpass(np.random.randn(n), 40) * np.exp(-t * 45) * 0.5
    sig = _fade(thud * 0.7 + click, 0.005)
    _write_wav(path, _norm(sig, 0.7), channels=1)


def make_heartbeat(path, seconds=2.0):
    """心跳：双击（lub-dub），躲藏/高压时循环播放。"""
    n = int(SR * seconds)
    sig = np.zeros(n)
    for ht, amp in [(0.0, 1.0), (0.28, 0.7), (1.0, 1.0), (1.28, 0.7)]:
        idx = int(ht * SR)
        dl = int(0.18 * SR)
        env = np.exp(-np.linspace(0, 12, min(dl, n - idx)))
        f = 60 * np.exp(-np.linspace(0, 3, min(dl, n - idx)))
        beat = amp * np.sin(2 * math.pi * f * np.linspace(0, 0.18, len(env))) * env
        sig[idx:idx + len(beat)] += beat
    sig = _fade(sig, 0.02)
    _write_wav(path, _norm(sig, 0.85), channels=1)


def make_door(path):
    """开关门：铰链吱呀 + 关门闷响。"""
    seconds = 1.4
    n = int(SR * seconds)
    t = _t(seconds)
    creak = 0.3 * np.sin(2 * math.pi * (300 + 250 * t / seconds) * t) * np.exp(-t * 1.2)
    creak *= (0.5 + 0.5 * np.sin(2 * math.pi * 8 * t))
    thud_idx = int(1.05 * SR)
    thud = np.zeros(n)
    dl = n - thud_idx
    tt = np.linspace(0, seconds - 1.05, dl)
    thud[thud_idx:] = 0.6 * np.sin(2 * math.pi * 70 * tt) * np.exp(-tt * 18)
    sig = _fade(creak + thud, 0.02)
    _write_wav(path, _norm(sig, 0.8), channels=1)


def make_pickup(path):
    """拾取物品：轻柔上行两音提示。"""
    seconds = 0.4
    parts = []
    for f, d in [(660, 0.15), (990, 0.25)]:
        seg = np.sin(2 * math.pi * f * _t(d)) * _adsr(int(SR * d), a=0.01, d=0.05, s=0.5, r=0.1)
        parts.append(seg)
    sig = _fade(np.concatenate(parts) * 0.4, 0.005)
    _write_wav(path, _norm(sig, 0.6), channels=1)


def make_flashlight_click(path):
    """手电开关：短促咔哒。"""
    seconds = 0.08
    n = int(SR * seconds)
    t = _t(seconds)
    click = _lowpass(np.random.randn(n), 15) * np.exp(-t * 120)
    click += 0.3 * np.sin(2 * math.pi * 1800 * t) * np.exp(-t * 150)
    _write_wav(path, _norm(_fade(click, 0.002), 0.6), channels=1)


def make_stinger(path):
    """惊吓短音：不谐和刺 + 快速起落（谨慎使用）。"""
    seconds = 0.9
    n = int(SR * seconds)
    t = _t(seconds)
    cluster = (np.sin(2 * math.pi * 800 * t) + np.sin(2 * math.pi * 848 * t)
               + np.sin(2 * math.pi * 1190 * t))
    env = np.exp(-t * 4.0) * (1 - np.exp(-t * 60))
    sig = _fade(cluster * env * 0.3, 0.005)
    _write_wav(path, _norm(sig, 0.85), channels=1)


def make_save_blip(path):
    """存档提示：中性单音。"""
    seconds = 0.25
    sig = np.sin(2 * math.pi * 880 * _t(seconds)) * _adsr(int(SR * seconds), a=0.01, d=0.05, s=0.4, r=0.15)
    _write_wav(path, _norm(_fade(sig * 0.4, 0.005), 0.5), channels=1)


# ----------------- 主流程 -----------------

# (文件名, 目录, 生成函数)
JOBS = [
    ("menu_theme.wav", MUSIC_DIR, make_menu_theme),
    ("chase.wav", MUSIC_DIR, make_chase),
    ("ending.wav", MUSIC_DIR, make_ending),
    ("ambient_ward.wav", SOUNDS_DIR, make_ambient_ward),
    ("ambient_basement.wav", SOUNDS_DIR, make_ambient_basement),
    ("horror_drone.wav", MUSIC_DIR, make_horror_drone),
    ("nurse_iv_clink.wav", SOUNDS_DIR, make_nurse_iv_clink),
    ("nurse_drag.wav", SOUNDS_DIR, make_nurse_drag),
    ("nurse_breath.wav", SOUNDS_DIR, make_nurse_breath),
    ("footstep.wav", SOUNDS_DIR, make_footstep),
    ("heartbeat.wav", SOUNDS_DIR, make_heartbeat),
    ("door.wav", SOUNDS_DIR, make_door),
    ("pickup.wav", SOUNDS_DIR, make_pickup),
    ("flashlight_click.wav", SOUNDS_DIR, make_flashlight_click),
    ("stinger.wav", SOUNDS_DIR, make_stinger),
    ("save_blip.wav", SOUNDS_DIR, make_save_blip),
]


def main(argv):
    force = "--force" in argv
    np.random.seed(1234)  # 结果可复现
    made, skipped = 0, 0
    for name, d, fn in JOBS:
        path = os.path.join(d, name)
        if os.path.exists(path) and not force:
            print("SKIP (exists)", os.path.relpath(path, ROOT))
            skipped += 1
            continue
        fn(path)
        made += 1
    print(f"\nDONE: 生成 {made} 个，跳过 {skipped} 个（--force 可强制覆盖）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
