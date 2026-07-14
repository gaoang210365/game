"""
回声病房 / Echo Ward - 程序化贴图生成

用 numpy + Pillow 生成灰盒升级用的贴图，输出到 assets/textures/。
风格参考同类医院恐怖游戏：脏旧瓷砖、斑驳墙面、带血渍/污渍的地面。

生成：
  floor_tile.png   —— 破旧地砖（带缝隙、污渍、划痕）
  wall.png         —— 医院墙面（上白下绿护墙，斑驳掉漆）
  ceiling.png      —— 天花板（吸音板 + 污渍）
  door.png         —— 防火门金属质感
  metal.png        —— 通用金属（护士/器械）

运行：
    game_env\Scripts\python.exe assets_gen\make_textures.py [--force]
"""

import os
import sys
import numpy as np

try:
    from PIL import Image
except ImportError:
    print("需要 Pillow：pip install pillow")
    sys.exit(1)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEX_DIR = os.path.join(ROOT, "assets", "textures")
SIZE = 512


def _noise(size, scale, seed):
    """分形噪声（多倍频叠加），返回 [0,1]。"""
    rng = np.random.default_rng(seed)
    out = np.zeros((size, size))
    amp, freq, total = 1.0, scale, 0.0
    for _ in range(4):
        cells = max(2, int(freq))
        grid = rng.random((cells + 1, cells + 1))
        ys = np.linspace(0, cells, size)
        xs = np.linspace(0, cells, size)
        y0 = np.floor(ys).astype(int); x0 = np.floor(xs).astype(int)
        fy = (ys - y0)[:, None]; fx = (xs - x0)[None, :]
        y0 = np.clip(y0, 0, cells - 1); x0 = np.clip(x0, 0, cells - 1)
        g00 = grid[y0][:, x0]; g10 = grid[y0 + 1][:, x0]
        g01 = grid[y0][:, x0 + 1]; g11 = grid[y0 + 1][:, x0 + 1]
        top = g00 * (1 - fx) + g01 * fx
        bot = g10 * (1 - fx) + g11 * fx
        out += amp * (top * (1 - fy) + bot * fy)
        total += amp; amp *= 0.5; freq *= 2
    return out / total


def _stains(img, seed, count, color, strength):
    """叠加不规则污渍/血渍。"""
    rng = np.random.default_rng(seed)
    h, w, _ = img.shape
    yy, xx = np.mgrid[0:h, 0:w]
    for _ in range(count):
        cy, cx = rng.integers(0, h), rng.integers(0, w)
        r = rng.integers(w // 20, w // 6)
        d = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
        mask = np.clip(1 - d / r, 0, 1) ** 2 * strength * rng.uniform(0.4, 1.0)
        for c in range(3):
            img[..., c] = img[..., c] * (1 - mask) + color[c] * mask
    return img


def _save(name, arr):
    os.makedirs(TEX_DIR, exist_ok=True)
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    path = os.path.join(TEX_DIR, name)
    img.save(path)
    print("WROTE", os.path.relpath(path, ROOT))


def make_floor():
    n = _noise(SIZE, 6, 1)[..., None]
    base = np.array([120, 118, 110]) * (0.7 + 0.5 * n)
    img = np.broadcast_to(base, (SIZE, SIZE, 3)).copy()
    # 瓷砖缝
    tiles = 4
    step = SIZE // tiles
    grout = 6
    for i in range(tiles + 1):
        p = min(i * step, SIZE - 1)
        img[max(0, p - grout // 2):p + grout // 2, :] *= 0.45
        img[:, max(0, p - grout // 2):p + grout // 2] *= 0.45
    img = _stains(img, 3, 18, (60, 55, 48), 0.7)      # 污渍
    img = _stains(img, 4, 4, (70, 20, 18), 0.55)      # 暗血渍
    _save("floor_tile.png", img)


def make_wall():
    n = _noise(SIZE, 5, 11)[..., None]
    img = np.zeros((SIZE, SIZE, 3))
    split = int(SIZE * 0.55)
    # 上半：脏白墙
    img[:split] = np.array([175, 172, 160]) * (0.75 + 0.4 * n[:split])
    # 下半：医院护墙绿
    img[split:] = np.array([90, 120, 105]) * (0.7 + 0.5 * n[split:])
    # 分界踢脚线
    img[split - 4:split + 4] *= 0.5
    img = _stains(img, 12, 22, (70, 68, 60), 0.6)     # 掉漆/污渍
    img = _stains(img, 13, 6, (60, 18, 16), 0.4)      # 血迹
    _save("wall.png", img)


def make_ceiling():
    n = _noise(SIZE, 8, 21)[..., None]
    img = np.broadcast_to(np.array([140, 140, 135]) * (0.8 + 0.3 * n),
                          (SIZE, SIZE, 3)).copy()
    grid = SIZE // 4
    for i in range(5):
        p = min(i * grid, SIZE - 1)
        img[max(0, p - 2):p + 2, :] *= 0.6
        img[:, max(0, p - 2):p + 2] *= 0.6
    img = _stains(img, 22, 12, (95, 88, 70), 0.7)     # 水渍
    _save("ceiling.png", img)


def make_door():
    n = _noise(SIZE, 4, 31)[..., None]
    img = np.broadcast_to(np.array([120, 60, 55]) * (0.7 + 0.4 * n),
                          (SIZE, SIZE, 3)).copy()
    # 竖向拉丝
    stripe = (0.9 + 0.1 * np.sin(np.linspace(0, 60, SIZE)))[None, :, None]
    img *= stripe
    img = _stains(img, 32, 10, (40, 30, 28), 0.5)
    _save("door.png", img)


def make_metal():
    n = _noise(SIZE, 10, 41)[..., None]
    img = np.broadcast_to(np.array([150, 152, 160]) * (0.7 + 0.4 * n),
                          (SIZE, SIZE, 3)).copy()
    img = _stains(img, 42, 14, (90, 92, 100), 0.5)
    _save("metal.png", img)


JOBS = [("floor_tile.png", make_floor), ("wall.png", make_wall),
        ("ceiling.png", make_ceiling), ("door.png", make_door),
        ("metal.png", make_metal)]


def main(argv):
    force = "--force" in argv
    made = skipped = 0
    for name, fn in JOBS:
        if os.path.exists(os.path.join(TEX_DIR, name)) and not force:
            print("SKIP (exists)", name); skipped += 1; continue
        fn(); made += 1
    print(f"\nDONE: 生成 {made} 个，跳过 {skipped} 个")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
