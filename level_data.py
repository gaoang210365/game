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

# 地面/天花板包围盒（整层外接矩形）
FLOOR_X0, FLOOR_X1 = -14.0, 14.0
FLOOR_Y0, FLOOR_Y1 = -4.0, 56.0

# 玩家出生（南端主走廊）
SPAWN = (0.0, -1.0, 1.6)
SPAWN_H = 0.0

# 出口安全门（北端尽头）
EXIT_POS = (0.0, 54.0, 0.0)


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
ROOMS = {
    # 西翼（x 负）
    "ward_a":  {"x0": -14, "y0": -4, "x1": -2, "y1": 10,  "cn": "401 病房"},
    "ward_b":  {"x0": -14, "y0": 10, "x1": -2, "y1": 24,  "cn": "403 病房"},
    "nurse":   {"x0": -14, "y0": 24, "x1": -2, "y1": 38,  "cn": "护士站"},
    "power":   {"x0": -14, "y0": 38, "x1": -2, "y1": 56,  "cn": "配电房"},
    # 东翼（x 正）
    "ward_c":  {"x0": 2,   "y0": -4, "x1": 14, "y1": 12,  "cn": "402 病房"},
    "storage": {"x0": 2,   "y0": 12, "x1": 14, "y1": 26,  "cn": "储藏室"},
    "office":  {"x0": 2,   "y0": 26, "x1": 14, "y1": 40,  "cn": "医生办公室"},
    "exam":    {"x0": 2,   "y0": 40, "x1": 14, "y1": 56,  "cn": "检查室"},
}

# 每个房间在走廊墙上的门洞中心 y（连通中央走廊）
_WEST_DOORS = [3, 17, 31, 47]        # ward_a / ward_b / nurse / power
_EAST_DOORS = [4, 19, 33, 48]        # ward_c / storage / office / exam


def build_walls():
    """展开成全部墙段 [(cx,cy,lx,ly), ...]。游戏与 Blender 共用。"""
    W = []
    # 外周墙
    W += _wall_with_gaps(FLOOR_X0, FLOOR_Y0, FLOOR_X1, FLOOR_Y0, [])       # 南
    W += _wall_with_gaps(FLOOR_X0, FLOOR_Y1, FLOOR_X1, FLOOR_Y1,
                         [(EXIT_POS[0], DOOR_W)])                          # 北（出口门洞）
    W += _wall_with_gaps(FLOOR_X0, FLOOR_Y0, FLOOR_X0, FLOOR_Y1, [])       # 西
    W += _wall_with_gaps(FLOOR_X1, FLOOR_Y0, FLOOR_X1, FLOOR_Y1, [])       # 东
    # 中央走廊两侧长墙（带各房间门洞）
    W += _wall_with_gaps(-2, FLOOR_Y0, -2, FLOOR_Y1,
                         [(y, DOOR_W) for y in _WEST_DOORS])
    W += _wall_with_gaps(2, FLOOR_Y0, 2, FLOOR_Y1,
                         [(y, DOOR_W) for y in _EAST_DOORS])
    # 西翼房间之间的横向隔断（x: -14..-2）
    for y in (10, 24, 38):
        W += _wall_with_gaps(-14, y, -2, y, [])
    # 东翼房间之间的横向隔断（x: 2..14）
    for y in (12, 26, 40):
        W += _wall_with_gaps(2, y, 14, y, [])
    return W


WALLS = build_walls()


# ---- 静态装饰道具（供 Blender 建模；type 决定形状）----
# type: bed / gurney / desk / chair / shelf / locker / sink / fusebox_panel
#       ivpole / monitor / wheelchair / boxes / curtain / bedtable
PROPS = [
    # 401 病房（西南）：两张床+床头桌+隔帘+输液架+监护仪
    {"type": "bed",      "pos": (-11, 1.5), "rot": 90},
    {"type": "bedtable", "pos": (-11, 3.2), "rot": 0},
    {"type": "ivpole",   "pos": (-9.4, 1),  "rot": 0},
    {"type": "curtain",  "pos": (-8.5, 2),  "rot": 0},
    {"type": "bed",      "pos": (-11, 7),   "rot": 90},
    {"type": "bedtable", "pos": (-11, 8.7), "rot": 0},
    {"type": "monitor",  "pos": (-9.4, 7),  "rot": 0},
    {"type": "wheelchair","pos": (-4, 6.5), "rot": 200},
    # 403 病房（西中）
    {"type": "bed",      "pos": (-11, 13),  "rot": 90},
    {"type": "bedtable", "pos": (-11, 14.7),"rot": 0},
    {"type": "ivpole",   "pos": (-9.4, 13), "rot": 0},
    {"type": "curtain",  "pos": (-8.5, 14), "rot": 0},
    {"type": "bed",      "pos": (-11, 20),  "rot": 90},
    {"type": "gurney",   "pos": (-5, 18),   "rot": 20},
    {"type": "monitor",  "pos": (-9.4, 20), "rot": 0},
    # 护士站（西中北）
    {"type": "desk",     "pos": (-8, 30),   "rot": 0},
    {"type": "chair",    "pos": (-8, 28.8), "rot": 180},
    {"type": "monitor",  "pos": (-5.5, 31), "rot": 90},
    {"type": "shelf",    "pos": (-13.3, 26.5),"rot": 90},
    {"type": "shelf",    "pos": (-13.3, 30), "rot": 90},
    {"type": "boxes",    "pos": (-5, 36),   "rot": 0},
    # 配电房（西北）
    {"type": "fusebox_panel", "pos": (-13.4, 47), "rot": 0},
    {"type": "locker",   "pos": (-4, 40),   "rot": 180},
    {"type": "boxes",    "pos": (-11, 52),  "rot": 30},
    {"type": "shelf",    "pos": (-13.3, 42),"rot": 90},
    # 402 病房（东南）
    {"type": "bed",      "pos": (11, 1.5),  "rot": 90},
    {"type": "bedtable", "pos": (11, 3.2),  "rot": 0},
    {"type": "ivpole",   "pos": (9.4, 1),   "rot": 0},
    {"type": "curtain",  "pos": (8.5, 2),   "rot": 0},
    {"type": "bed",      "pos": (11, 8),    "rot": 90},
    {"type": "bedtable", "pos": (11, 9.7),  "rot": 0},
    {"type": "gurney",   "pos": (5, 6),     "rot": 90},
    {"type": "monitor",  "pos": (9.4, 8),   "rot": 0},
    # 储藏室（东中）
    {"type": "shelf",    "pos": (13.3, 14), "rot": 90},
    {"type": "shelf",    "pos": (13.3, 18), "rot": 90},
    {"type": "shelf",    "pos": (13.3, 22), "rot": 90},
    {"type": "locker",   "pos": (4, 24),    "rot": 180},
    {"type": "boxes",    "pos": (10, 20),   "rot": 15},
    {"type": "boxes",    "pos": (7, 14),    "rot": -20},
    {"type": "wheelchair","pos": (6, 24),   "rot": 90},
    # 医生办公室（东中北）
    {"type": "desk",     "pos": (8, 32),    "rot": 0},
    {"type": "chair",    "pos": (8, 30.7),  "rot": 180},
    {"type": "shelf",    "pos": (13.3, 28), "rot": 90},
    {"type": "shelf",    "pos": (13.3, 32), "rot": 90},
    {"type": "boxes",    "pos": (4, 38),    "rot": 0},
    # 检查室（东北）
    {"type": "gurney",   "pos": (8, 46),    "rot": 0},
    {"type": "monitor",  "pos": (10.5, 44), "rot": 0},
    {"type": "ivpole",   "pos": (6, 44),    "rot": 0},
    {"type": "sink",     "pos": (13.3, 42), "rot": 90},
    {"type": "curtain",  "pos": (5, 48),    "rot": 90},
    {"type": "wheelchair","pos": (10, 52),  "rot": 210},
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
    "note_ward_a":  (-6.0, 5.0, 1.2),    # 线索：密码第 1、2 位
    "note_office":  (8.0, 33.0, 1.2),    # 线索：密码第 3、4 位
    "keypad_storage": (4.2, 24.0, 1.3),  # 输入 4 位密码 -> 开储物柜拿钥匙卡
    "locker_key":   (4.0, 24.0, 1.0),    # 储物柜（开锁后给钥匙卡）
    "fusebox":      (-13.6, 47.0, 1.4),  # 钥匙卡开配电房总闸 -> 恢复电力/开安全门
    "exit_door":    EXIT_POS,            # 北端安全门（通电后可开）
}

