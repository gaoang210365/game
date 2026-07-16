"""
《回声病房》关卡布局 —— 单一数据源（Single Source of Truth）。

游戏（echo_ward_game.py）与 Blender 建模脚本（tools/gen_level.py）都 import 本模块，
读同一份坐标，保证"可见几何"与"碰撞盒"永远对齐。只依赖标准库，两边都能用。

坐标系（Z-up，单位米，与游戏一致）：
  - 地面顶面 z=0，天花板底面 z=WALL_H
  - 每段墙 = (中心x, 中心y, 长度x, 长度y)，底在 z=0、高 WALL_H
  - 房间用矩形 + 门洞描述，自动展开成带门洞的墙段

布局：一层废弃住院部。南北主走廊贯穿，两侧分布病房/护士站/储藏室/
配电房/办公室，尽头是安全门（终点）。玩家出生在南端。
"""

WALL_H = 3.2          # 墙高 / 层高
WALL_T = 0.2          # 墙厚
DOOR_W = 1.6          # 门洞宽

# 地面/天花板包围盒（整层外接矩形）—— 扩大：更长更宽
FLOOR_X0, FLOOR_X1 = -16.0, 16.0
FLOOR_Y0, FLOOR_Y1 = -4.0, 80.0

# 玩家出生（南端主走廊）
SPAWN = (0.0, -1.0, 1.6)
SPAWN_H = 0.0

# 出口安全门（北端尽头）
EXIT_POS = (0.0, 78.0, 0.0)


def _wall_with_gaps(x0, y0, x1, y1, gaps):
    """把一条直墙（水平或垂直）按门洞切成多段。
    gaps: [(中心, 洞宽), ...]，中心是沿墙方向坐标。
    返回 [(cx, cy, lx, ly), ...]（中心+长度）。"""
    segs = []
    horizontal = abs(y1 - y0) < 1e-6
    if horizontal:
        a, b = min(x0, x1), max(x0, x1)
        y = y0
        cursor = a
        for gc, gw in sorted(gaps, key=lambda g: g[0]):
            left = gc - gw / 2
            if left > cursor:
                segs.append(((cursor + left) / 2, y, left - cursor, WALL_T))
            cursor = gc + gw / 2
        if b > cursor:
            segs.append(((cursor + b) / 2, y, b - cursor, WALL_T))
    else:
        a, b = min(y0, y1), max(y0, y1)
        x = x0
        cursor = a
        for gc, gw in sorted(gaps, key=lambda g: g[0]):
            low = gc - gw / 2
            if low > cursor:
                segs.append((x, (cursor + low) / 2, WALL_T, low - cursor))
            cursor = gc + gw / 2
        if b > cursor:
            segs.append((x, (cursor + b) / 2, WALL_T, b - cursor))
    return segs


# ---- 房间定义（名称 -> 矩形范围）。中央走廊 x∈[-2,2] 贯穿南北。----
# 西翼隔断 y: 10/22/36/52；东翼隔断 y: 12/28/44/60。房间大小刻意不一。
ROOMS = {
    # 西翼（x 负，x0=-16..x1=-2）
    "ward_a":   {"x0": -16, "y0": -4, "x1": -2, "y1": 10,  "cn": "401 病房"},
    "ward_b":   {"x0": -16, "y0": 10, "x1": -2, "y1": 22,  "cn": "403 病房"},
    "nurse":    {"x0": -16, "y0": 22, "x1": -2, "y1": 36,  "cn": "护士站"},
    "morgue":   {"x0": -16, "y0": 36, "x1": -2, "y1": 52,  "cn": "停尸间"},
    "power":    {"x0": -16, "y0": 52, "x1": -2, "y1": 80,  "cn": "配电房"},
    # 东翼（x 正，x0=2..x1=16）
    "ward_c":   {"x0": 2,   "y0": -4, "x1": 16, "y1": 12,  "cn": "402 病房"},
    "storage":  {"x0": 2,   "y0": 12, "x1": 16, "y1": 28,  "cn": "储藏室"},
    "office":   {"x0": 2,   "y0": 28, "x1": 16, "y1": 44,  "cn": "医生办公室"},
    "exam":     {"x0": 2,   "y0": 44, "x1": 16, "y1": 60,  "cn": "检查室"},
    "surgery":  {"x0": 2,   "y0": 60, "x1": 16, "y1": 80,  "cn": "手术室"},
}

# 每个房间在走廊墙上的门洞中心 y（连通中央走廊）
_WEST_DOORS = [3, 16, 29, 44, 66]     # ward_a/ward_b/nurse/morgue/power
_EAST_DOORS = [4, 20, 36, 52, 70]     # ward_c/storage/office/exam/surgery


def build_walls():
    """展开成全部墙段 [(cx,cy,lx,ly), ...]。游戏与 Blender 共用。"""
    W = []
    W += _wall_with_gaps(FLOOR_X0, FLOOR_Y0, FLOOR_X1, FLOOR_Y0, [])       # 南
    W += _wall_with_gaps(FLOOR_X0, FLOOR_Y1, FLOOR_X1, FLOOR_Y1,
                         [(EXIT_POS[0], DOOR_W)])                          # 北（出口）
    W += _wall_with_gaps(FLOOR_X0, FLOOR_Y0, FLOOR_X0, FLOOR_Y1, [])       # 西
    W += _wall_with_gaps(FLOOR_X1, FLOOR_Y0, FLOOR_X1, FLOOR_Y1, [])       # 东
    W += _wall_with_gaps(-2, FLOOR_Y0, -2, FLOOR_Y1,
                         [(y, DOOR_W) for y in _WEST_DOORS])
    W += _wall_with_gaps(2, FLOOR_Y0, 2, FLOOR_Y1,
                         [(y, DOOR_W) for y in _EAST_DOORS])
    # 西翼横向隔断
    for y in (10, 22, 36, 52):
        W += _wall_with_gaps(-16, y, -2, y, [])
    # 东翼横向隔断
    for y in (12, 28, 44, 60):
        W += _wall_with_gaps(2, y, 16, y, [])
    return W


WALLS = build_walls()


# ---- 静态装饰道具（供 Blender 建模；type 决定形状）----
# type: bed / gurney / desk / chair / shelf / locker / sink / fusebox_panel
#       ivpole / monitor / wheelchair / boxes / curtain / bedtable
PROPS = [
    # 401 病房 ward_a (x-16..-2, y-4..10)，门 y=3
    {"type": "bed",      "pos": (-14, 0),   "rot": 90},
    {"type": "bedtable", "pos": (-14, 2),   "rot": 0},
    {"type": "ivpole",   "pos": (-12, -1),  "rot": 0},
    {"type": "curtain",  "pos": (-11, 0),   "rot": 0},
    {"type": "bed",      "pos": (-14, 7),   "rot": 90},
    {"type": "bedtable", "pos": (-14, 9),   "rot": 0},
    {"type": "monitor",  "pos": (-12, 7),   "rot": 0},
    {"type": "wheelchair","pos": (-5, 7),   "rot": 200},
    # 403 病房 ward_b (x-16..-2, y10..22)，门 y=16
    {"type": "bed",      "pos": (-14, 13),  "rot": 90},
    {"type": "bedtable", "pos": (-14, 15),  "rot": 0},
    {"type": "ivpole",   "pos": (-12, 12),  "rot": 0},
    {"type": "curtain",  "pos": (-11, 13),  "rot": 0},
    {"type": "bed",      "pos": (-14, 20),  "rot": 90},
    {"type": "gurney",   "pos": (-6, 19),   "rot": 20},
    {"type": "monitor",  "pos": (-12, 20),  "rot": 0},
    # 护士站 nurse (x-16..-2, y22..36)，门 y=29
    {"type": "desk",     "pos": (-9, 26),   "rot": 0},
    {"type": "chair",    "pos": (-9, 24.8), "rot": 180},
    {"type": "monitor",  "pos": (-6, 27),   "rot": 90},
    {"type": "shelf",    "pos": (-15.3, 25),"rot": 90},
    {"type": "shelf",    "pos": (-15.3, 29),"rot": 90},
    {"type": "boxes",    "pos": (-6, 34),   "rot": 0},
    # 停尸间 morgue (x-16..-2, y36..52)，门 y=44 —— 尸柜 + 推床
    {"type": "locker",   "pos": (-15, 39),  "rot": 90},
    {"type": "locker",   "pos": (-15, 42),  "rot": 90},
    {"type": "locker",   "pos": (-15, 45),  "rot": 90},
    {"type": "gurney",   "pos": (-9, 40),   "rot": 0},
    {"type": "gurney",   "pos": (-6, 48),   "rot": 15},
    {"type": "sink",     "pos": (-15.3, 49),"rot": 90},
    {"type": "curtain",  "pos": (-4, 46),   "rot": 0},
    # 配电房 power (x-16..-2, y52..80)，门 y=66 —— 配电箱在此
    {"type": "fusebox_panel", "pos": (-15.4, 66), "rot": 0},
    {"type": "locker",   "pos": (-5, 58),   "rot": 180},
    {"type": "shelf",    "pos": (-15.3, 56),"rot": 90},
    {"type": "shelf",    "pos": (-15.3, 60),"rot": 90},
    {"type": "boxes",    "pos": (-12, 74),  "rot": 30},
    {"type": "boxes",    "pos": (-6, 72),   "rot": -15},
    # 402 病房 ward_c (x2..16, y-4..12)，门 y=4
    {"type": "bed",      "pos": (14, 0),    "rot": 90},
    {"type": "bedtable", "pos": (14, 2),    "rot": 0},
    {"type": "ivpole",   "pos": (12, -1),   "rot": 0},
    {"type": "curtain",  "pos": (11, 0),    "rot": 0},
    {"type": "bed",      "pos": (14, 8),    "rot": 90},
    {"type": "bedtable", "pos": (14, 10),   "rot": 0},
    {"type": "gurney",   "pos": (6, 8),     "rot": 90},
    {"type": "monitor",  "pos": (12, 8),    "rot": 0},
    # 储藏室 storage (x2..16, y12..28)，门 y=20 —— 储物柜（藏钥匙卡）
    {"type": "shelf",    "pos": (15.3, 14), "rot": 90},
    {"type": "shelf",    "pos": (15.3, 18), "rot": 90},
    {"type": "shelf",    "pos": (15.3, 24), "rot": 90},
    {"type": "locker",   "pos": (5, 24),    "rot": 180},
    {"type": "boxes",    "pos": (11, 22),   "rot": 15},
    {"type": "boxes",    "pos": (8, 15),    "rot": -20},
    {"type": "wheelchair","pos": (7, 26),   "rot": 90},
    # 医生办公室 office (x2..16, y28..44)，门 y=36 —— 桌上有线索
    {"type": "desk",     "pos": (9, 34),    "rot": 0},
    {"type": "chair",    "pos": (9, 32.7),  "rot": 180},
    {"type": "shelf",    "pos": (15.3, 30), "rot": 90},
    {"type": "shelf",    "pos": (15.3, 40), "rot": 90},
    {"type": "boxes",    "pos": (5, 41),    "rot": 0},
    # 检查室 exam (x2..16, y44..60)，门 y=52
    {"type": "gurney",   "pos": (9, 50),    "rot": 0},
    {"type": "monitor",  "pos": (12, 48),   "rot": 0},
    {"type": "ivpole",   "pos": (6, 48),    "rot": 0},
    {"type": "sink",     "pos": (15.3, 47), "rot": 90},
    {"type": "curtain",  "pos": (5, 54),    "rot": 90},
    {"type": "wheelchair","pos": (12, 56),  "rot": 210},
    # 手术室 surgery (x2..16, y60..80)，门 y=70 —— 手术台居中 + 监护
    {"type": "gurney",   "pos": (9, 68),    "rot": 0},
    {"type": "monitor",  "pos": (12, 66),   "rot": 0},
    {"type": "monitor",  "pos": (6, 66),    "rot": 0},
    {"type": "ivpole",   "pos": (11, 70),   "rot": 0},
    {"type": "ivpole",   "pos": (7, 70),    "rot": 0},
    {"type": "sink",     "pos": (15.3, 74), "rot": 90},
    {"type": "shelf",    "pos": (15.3, 63), "rot": 90},
    {"type": "curtain",  "pos": (5, 74),    "rot": 90},
]


# ---- 道具碰撞尺寸（半宽x, 半宽y, 半高z），按 type。旋转 90/270 交换 xy。----
# 小/软/可穿物件（curtain/ivpole/monitor/chair）footprint 很小或不挡路。
_PROP_FOOTPRINT = {
    "bed":      (0.5, 1.0, 0.5),
    "gurney":   (0.4, 1.0, 0.5),
    "desk":     (0.85, 0.45, 0.4),
    "chair":    (0.28, 0.28, 0.4),
    "shelf":    (0.28, 0.72, 1.0),
    "locker":   (0.48, 0.32, 1.0),
    "sink":     (0.32, 0.28, 0.5),
    "fusebox_panel": (0.1, 0.5, 0.6),
    "boxes":    (0.35, 0.3, 0.4),
    "bedtable": (0.22, 0.22, 0.4),
    # ivpole / monitor / curtain 不加碰撞（细杆/软帘，玩家可贴近交互）
}


def build_prop_colliders():
    """返回 [(cx, cy, hx, hy, hz), ...]。供游戏为道具生成碰撞盒。"""
    out = []
    for p in PROPS:
        fp = _PROP_FOOTPRINT.get(p["type"])
        if not fp:
            continue
        hx, hy, hz = fp
        rot = p.get("rot", 0) % 180
        # 接近 90 度时交换 x/y footprint
        if 45 <= rot < 135:
            hx, hy = hy, hx
        out.append((p["pos"][0], p["pos"][1], hx, hy, hz))
    return out


PROP_COLLIDERS = build_prop_colliders()


# ---- 交互/解谜物件的世界坐标（游戏逻辑与可见模型共用）----
# 解谜链见 echo_ward_game。这里只给位置；房间是提示来源。
INTERACTIVES = {
    "note_ward_a":  (-13.0, 4.0, 1.2),   # 401 病房床边：密码前两位 47
    "note_office":  (9.0, 35.0, 1.2),    # 办公室桌上：密码后两位 26
    "keypad_storage": (5.2, 24.0, 1.3),  # 储藏室储物柜旁键盘：输 4 位密码
    "locker_key":   (5.0, 24.0, 1.0),    # 储物柜（开锁后给钥匙卡）
    "fusebox":      (-15.2, 66.0, 1.4),  # 配电房总闸（北端西侧）：钥匙卡恢复供电
    "exit_door":    EXIT_POS,            # 北端安全门（通电后可开）
}

