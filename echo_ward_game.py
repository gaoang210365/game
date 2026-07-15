"""
回声病房 / Echo Ward - 解谜逃脱（非追逐）

废弃住院部整层，黑暗中靠手电探索、解谜逃脱：
  - 第一人称移动 + 碰撞 + 手电筒（黑暗为主，手电是主要光源）
  - 整层大地图（level.glb）：中央走廊 + 8 个房间（病房/护士站/储藏室/
    办公室/检查室/配电房），几何读共享数据 level_data.py，与碰撞严格对齐
  - 解谜链：找两张纸条拼出储物柜密码 -> 键盘输入开柜取钥匙卡 ->
    配电房用钥匙卡恢复供电 -> 北端安全门解锁 -> 离开
  - 幽灵护士：沿走廊游荡的氛围惊吓，靠近增压迫感但【不致死】
  - 3D 定位音频 + 恐怖氛围床（horror_drone，音量偏大）+ 动态混音

依赖资源：assets/music/ 与 assets/sounds/（缺失先跑 assets_gen/make_audio.py）
          assets/models/level.glb（缺失先跑 blender --python tools/gen_level.py）

运行（用游戏专用虚拟环境）：
    game_env\Scripts\python.exe echo_ward_game.py

操作：
    调整好窗口后左键点击进入视角
    WASD/方向键 移动 | 鼠标 视角 | Shift 奔跑 | C 蹲下
    F 手电筒 | E 交互 | 数字键 输入密码 | F5 存档 | F9 读档 | Esc 取消/释放/退出
"""

from panda3d.core import loadPrcFileData

loadPrcFileData("", "window-title Echo Ward - 回声病房")
loadPrcFileData("", "win-size 1280 720")
loadPrcFileData("", "audio-library-name p3openal_audio")
loadPrcFileData("", "show-frame-rate-meter true")
loadPrcFileData("", "framebuffer-multisample 1")
loadPrcFileData("", "multisamples 4")
loadPrcFileData("", "textures-power-2 none")

from direct.showbase.ShowBase import ShowBase
from direct.showbase.Audio3DManager import Audio3DManager
from panda3d.core import (
    AmbientLight, DirectionalLight, Spotlight, PointLight, PerspectiveLens,
    CardMaker, Vec3, Vec4, Point3, NodePath, WindowProperties,
    CollisionTraverser, CollisionHandlerPusher, CollisionNode,
    CollisionSphere, CollisionBox, BitMask32, TextNode,
    ClockObject, KeyboardButton, Filename, Fog, Texture,
    TextureStage, SamplerState,
)
from direct.gui.OnscreenText import OnscreenText
from direct.gui.OnscreenImage import OnscreenImage
import sys
import os
import json
import time
import math

import level_data as L

globalClock = ClockObject.getGlobalClock()


def _disable_ime_process():
    """进程级禁用 IME —— 根治"按 Shift 切中/英文导致 WASD 被输入法吃掉、按键失效"。

    ImmAssociateContext(hwnd,0) 只解除某个窗口的 IME 上下文，挡不住输入法软件的
    全局 Shift 热键；一旦切到中文组字，按键事件被输入法拦截，Panda 收不到，
    is_button_down 恒为 False。ImmDisableIME((DWORD)-1) 禁用当前进程所有线程的
    IME，必须在创建窗口前调用。之后即便系统显示切成中文，游戏也不进入组字，
    硬件按键照常到达。
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        # -1 (0xFFFFFFFF) = 当前进程所有线程
        ctypes.windll.imm32.ImmDisableIME(0xFFFFFFFF)
    except Exception as e:
        print("ImmDisableIME failed (non-fatal):", e)


_disable_ime_process()


_WIN32_READY = False


def _setup_win32_signatures():
    """给 user32 函数声明 64 位指针签名 —— 根治 HWND 被 ctypes 截断成 32 位的问题。

    64 位 Windows 上 HWND 是 64 位指针，ctypes 默认按 32 位 int 处理返回值/参数，
    导致 GetForegroundWindow 截断后与完整 hwnd 永不相等（前台恒判 False）、
    GetAncestor 传入被截断返回垃圾句柄（GetWindowRect 失败、窗口中心=None）。
    显式声明后这些调用才正确，焦点判断与 recenter 才能工作。
    windll.user32 是单例，配置一次全局生效（_force_foreground 也一并受益）。
    """
    global _WIN32_READY
    if _WIN32_READY or sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        u.GetForegroundWindow.restype = wintypes.HWND
        u.GetActiveWindow.restype = wintypes.HWND
        u.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        u.GetAncestor.restype = wintypes.HWND
        u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        u.GetWindowRect.restype = wintypes.BOOL
        u.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        u.GetClientRect.restype = wintypes.BOOL
        u.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        u.ClientToScreen.restype = wintypes.BOOL
        u.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        u.GetCursorPos.restype = wintypes.BOOL
        u.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        u.SetCursorPos.restype = wintypes.BOOL
        u.SetForegroundWindow.argtypes = [wintypes.HWND]
        u.SetForegroundWindow.restype = wintypes.BOOL
        u.BringWindowToTop.argtypes = [wintypes.HWND]
        u.BringWindowToTop.restype = wintypes.BOOL
        u.SetActiveWindow.argtypes = [wintypes.HWND]
        u.SetActiveWindow.restype = wintypes.HWND
        u.SetFocus.argtypes = [wintypes.HWND]
        u.SetFocus.restype = wintypes.HWND
        u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        u.ShowWindow.restype = wintypes.BOOL
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
        u.GetWindowThreadProcessId.restype = wintypes.DWORD
        u.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
        u.AttachThreadInput.restype = wintypes.BOOL
        _WIN32_READY = True
    except Exception as e:
        print("win32 signature setup failed (non-fatal):", e)


_setup_win32_signatures()

ROOT = os.path.dirname(os.path.abspath(__file__))
SOUNDS_DIR = os.path.join(ROOT, "assets", "sounds")
MUSIC_DIR = os.path.join(ROOT, "assets", "music")
TEX_DIR = os.path.join(ROOT, "assets", "textures")
SAVE_DIR = os.path.join(ROOT, "saves")
SAVE_FILE = os.path.join(SAVE_DIR, "autosave.json")
SAVE_VERSION = 2

def _sfx_path(name):
    return Filename.fromOsSpecific(os.path.join(SOUNDS_DIR, name)).getFullpath()


def _music_path(name):
    return Filename.fromOsSpecific(os.path.join(MUSIC_DIR, name)).getFullpath()


def _tex_path(name):
    return Filename.fromOsSpecific(os.path.join(TEX_DIR, name)).getFullpath()


class SaveManager:
    """单槽自动存档：原子写入 + 版本迁移 + 损坏保护。"""

    def __init__(self, save_file=SAVE_FILE):
        self.save_file = save_file

    def save(self, state: dict) -> bool:
        os.makedirs(os.path.dirname(self.save_file), exist_ok=True)
        payload = {"version": SAVE_VERSION,
                   "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "state": state}
        try:
            tmp = self.save_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.save_file)
            return True
        except Exception as e:
            print("SAVE_FAILED:", e)
            return False

    def load(self):
        if not os.path.exists(self.save_file):
            return None
        try:
            with open(self.save_file, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as e:
            print("LOAD_FAILED (corrupt?):", e)
            return None
        return payload.get("state", {})

    def exists(self):
        return os.path.exists(self.save_file)


class EchoWardGame(ShowBase):
    """回声病房可玩原型主程序。"""

    def __init__(self):
        super().__init__()
        self.disableMouse()
        self.setBackgroundColor(0.01, 0.01, 0.02)

        # 参数
        self.walk_speed = 4.0
        self.run_speed = 6.8
        self.crouch_speed = 2.0
        self.mouse_sensitivity = 0.12
        self.heading = 0.0
        self.pitch = 0.0
        self.mouse_captured = False

        # 移动/相机
        self.walk_speed = 4.0
        self.run_speed = 6.8
        self.crouch_speed = 2.0
        self.mouse_sensitivity = 0.12
        self.heading = 0.0
        self.pitch = 0.0
        self.mouse_captured = False
        self.crouching = False
        self.stamina = 1.0

        # 手电
        self.flashlight_on = True

        # ---- 解谜状态（非追逐逃脱）----
        # 密码 4726：note_ward_a 给前两位、note_office 给后两位
        self.secret_code = "4726"
        self.notes_found = set()       # {"note_ward_a","note_office"}
        self.keypad_input = ""          # 键盘输入缓冲
        self.keypad_active = False      # 是否正在输入密码
        self.locker_open = False        # 储物柜是否已开
        self.has_keycard = False        # 是否拿到钥匙卡
        self.power_on = False           # 配电房是否已恢复供电
        self.exit_unlocked = False      # 安全门是否已解锁

        # 结算
        self.stress = 0.0
        self.game_over = False
        # 注意：胜利标志必须叫 victory，绝不能用 self.win —— 那是 ShowBase 的图形窗口对象，
        # 覆盖它会让所有鼠标/窗口操作（句柄、隐藏光标、recenter）全部静默失效。
        self.victory = False
        self.message = ("废弃住院部。找线索拼出储物柜密码，取钥匙卡恢复供电，"
                        "从北端安全门离开。手电筒 F 键。")
        self.msg_timer = 8.0
        self.noise_this_frame = 0.0

        self.save_mgr = SaveManager()

        self._build_scene()
        self._setup_collision()
        self._setup_lighting()
        self._setup_flashlight()
        self._setup_camera()
        self._setup_audio()
        self._setup_input()
        self._setup_hud()
        self.taskMgr.add(self._update, "update")

    # ---------- 场景 ----------

    def _load_tex(self, name, tiling=1.0):
        """加载贴图，设为重复采样；缺失返回 None。"""
        p = os.path.join(TEX_DIR, name)
        if not os.path.exists(p):
            return None
        tex = self.loader.loadTexture(_tex_path(name))
        if tex:
            tex.setWrapU(Texture.WMRepeat)
            tex.setWrapV(Texture.WMRepeat)
            tex.setMinfilter(SamplerState.FTLinearMipmapLinear)
            tex.setAnisotropicDegree(4)
        return tex

    def _build_scene(self):
        self.level = NodePath("level")
        self.level.reparentTo(self.render)

        # 贴图（回退灰盒用）
        self.tex_floor = self._load_tex("floor_tile.png")
        self.tex_wall = self._load_tex("wall.png")
        self.tex_ceiling = self._load_tex("ceiling.png")

        # 墙体碰撞规格：从共享数据 level_data.WALLS 读取（中心x,中心y,长x,长y）。
        # 与 level.glb 的可见墙体是同一份数据，天然对齐。
        self.walls = list(L.WALLS)

        # 加载整层 GLB（地/顶/墙/踢脚 + 病床/桌椅/货架/储物柜等道具）
        level_path = os.path.join(ROOT, "assets", "models", "level.glb")
        self.room_model = None
        if os.path.exists(level_path):
            self.room_model = self.loader.loadModel(
                Filename.fromOsSpecific(level_path).getFullpath())
        if self.room_model:
            self.room_model.reparentTo(self.level)
        else:
            self._build_graybox_fallback()

        self.exit_pos = Point3(*L.EXIT_POS)
        self._build_interactives()
        self._build_knockables()
        self._build_decals()

    def _build_interactives(self):
        """解谜物件：线索纸条、密码键盘、储物柜、配电箱、安全门。
        用带自发光的小模型标记，便于在黑暗中被手电照到时注意。"""
        self.interactive_nodes = {}

        def marker(cid, pos, color, scale=(0.3, 0.3, 0.4)):
            n = self.loader.loadModel("models/box")
            n.setScale(*scale)
            n.setColor(*color, 1)
            n.setColorScale(1.4, 1.4, 1.4, 1)
            n.setPos(Point3(pos[0], pos[1], pos[2]))
            n.reparentTo(self.render)
            self.interactive_nodes[cid] = n
            return n

        I = L.INTERACTIVES
        # 线索纸条（暖白，贴墙）
        marker("note_ward_a", I["note_ward_a"], (0.95, 0.92, 0.7), (0.02, 0.3, 0.4))
        marker("note_office", I["note_office"], (0.95, 0.92, 0.7), (0.02, 0.3, 0.4))
        # 密码键盘（青，贴储物柜）
        marker("keypad_storage", I["keypad_storage"], (0.3, 0.8, 0.85), (0.05, 0.25, 0.35))
        # 钥匙卡（藏在储物柜里，开锁后显示）
        kc = marker("locker_key", I["locker_key"], (0.9, 0.8, 0.2), (0.2, 0.02, 0.14))
        kc.hide()
        # 配电箱总闸（橙）
        marker("fusebox", I["fusebox"], (0.9, 0.55, 0.15), (0.1, 0.5, 0.6))

        # 安全门（终点，通电后变绿可开）
        self.exit_door = self.loader.loadModel("models/box")
        self.exit_door.setScale(1.6, 0.3, 2.4)
        self.exit_door.setPos(self.exit_pos + Point3(0, 0, 1.2))
        self.exit_door.setColorScale(1.2, 0.4, 0.4, 1)
        self.exit_door.reparentTo(self.level)
        self.exit_light = PointLight("exit_light")
        self.exit_light.setColor(Vec4(0.1, 0.55, 0.15, 1))
        self.exit_light_np = self.render.attachNewNode(self.exit_light)
        self.exit_light_np.setPos(self.exit_pos.x, self.exit_pos.y - 1, 2.6)

    def _build_decals(self):
        """血迹/污渍贴花：地面朝上、墙面竖直的半透明卡片，营造恐怖废弃感。
        贴图缺失时静默跳过。"""
        from panda3d.core import TransparencyAttrib

        def load_tex(name):
            p = os.path.join(TEX_DIR, name)
            if not os.path.exists(p):
                return None
            return self.loader.loadTexture(_tex_path(name))

        t_floor = load_tex("blood_splatter_decal.png")
        t_wall = load_tex("blood_wall_decal.png")

        def floor_decal(tex, x, y, size, rotd=0):
            if not tex:
                return
            cm = CardMaker("blood_f")
            cm.setFrame(-size / 2, size / 2, -size / 2, size / 2)
            n = self.render.attachNewNode(cm.generate())
            n.setTexture(tex)
            n.setP(-90)
            n.setH(rotd)
            n.setPos(x, y, 0.02)
            n.setTransparency(TransparencyAttrib.MAlpha)
            n.setDepthOffset(1)
            n.reparentTo(self.level)

        def wall_decal(tex, x, y, z, h, w, ht):
            if not tex:
                return
            cm = CardMaker("blood_w")
            cm.setFrame(-w / 2, w / 2, -ht / 2, ht / 2)
            n = self.render.attachNewNode(cm.generate())
            n.setTexture(tex)
            n.setH(h)
            n.setPos(x, y, z)
            n.setTransparency(TransparencyAttrib.MAlpha)
            n.setDepthOffset(1)
            n.reparentTo(self.level)

        # 地面血迹（走廊/房间散布）
        for (x, y, s, r) in [(0, 10, 2.4, 15), (-3, 22, 2.0, 60), (3, 34, 2.6, -20),
                             (-8, 8, 1.8, 30), (8, 46, 2.2, 45), (0, 44, 2.0, 0),
                             (-4, 40, 1.6, 80)]:
            floor_decal(t_floor, x, y, s)
        # 墙面血手印/拖痕（贴中央走廊两侧内表面 x=±2）
        for (x, y, h) in [(-1.9, 14, 90), (1.9, 26, -90), (-1.9, 38, 90), (1.9, 48, -90)]:
            wall_decal(t_wall, x, y, 1.4, h, 2.0, 2.2)

    def _build_knockables(self):
        """可碰倒的小道具：身体走过去接触即被推倒/推开。
        用简单小圆柱/方块占位，避免与 GLB 里的静态装饰重复太多。
        每个 = {node, home(初始pos), toppled(是否已倒)}。"""
        self.knockables = []
        # (类型, x, y, 颜色) —— 放在房间/走廊里可被撞到的小物件
        specs = [
            ("stool", -6, 4, (0.6, 0.5, 0.35)),
            ("stool", 6, 4, (0.6, 0.5, 0.35)),
            ("bin", -3, 12, (0.3, 0.4, 0.45)),
            ("bin", 3, 20, (0.3, 0.4, 0.45)),
            ("ivstand", -9, 16, (0.7, 0.72, 0.74)),
            ("ivstand", 9, 10, (0.7, 0.72, 0.74)),
            ("bin", -3, 44, (0.3, 0.4, 0.45)),
            ("stool", 4, 50, (0.6, 0.5, 0.35)),
            ("cart", 0, 28, (0.55, 0.57, 0.6)),
        ]
        for kind, x, y, col in specs:
            node = NodePath("knock_%s_%d_%d" % (kind, x, y))
            node.reparentTo(self.render)
            node.setPos(x, y, 0)
            if kind == "ivstand":
                pole = self.loader.loadModel("models/box")
                pole.setScale(0.06, 0.06, 1.6)
                pole.setPos(-0.03, -0.03, 0)
                pole.setColor(*col, 1)
                pole.reparentTo(node)
            elif kind == "cart":
                body = self.loader.loadModel("models/box")
                body.setScale(0.6, 0.4, 0.8)
                body.setPos(-0.3, -0.2, 0)
                body.setColor(*col, 1)
                body.reparentTo(node)
            elif kind == "bin":
                body = self.loader.loadModel("models/box")
                body.setScale(0.35, 0.35, 0.6)
                body.setPos(-0.175, -0.175, 0)
                body.setColor(*col, 1)
                body.reparentTo(node)
            else:  # stool
                body = self.loader.loadModel("models/box")
                body.setScale(0.35, 0.35, 0.45)
                body.setPos(-0.175, -0.175, 0)
                body.setColor(*col, 1)
                body.reparentTo(node)
            self.knockables.append({"node": node, "home": Point3(x, y, 0),
                                    "toppled": False, "vel": Vec3(0, 0, 0)})

    def _update_knockables(self, dt):
        """玩家接触则推倒并给一个远离玩家的速度；已倒的继续滑行减速。"""
        if not hasattr(self, "knockables"):
            return
        ppos = self.player.getPos()
        for k in self.knockables:
            node = k["node"]
            npos = node.getPos()
            flat = Vec3(npos.x - ppos.x, npos.y - ppos.y, 0)
            dist = flat.length()
            if not k["toppled"] and dist < 0.9:
                # 被撞倒：倒向远离玩家方向，并获得初速度
                k["toppled"] = True
                if dist > 1e-3:
                    flat.normalize()
                else:
                    flat = Vec3(0, 1, 0)
                node.setHpr(0, 0, 88)  # 放倒
                node.setZ(0.25)
                k["vel"] = flat * 2.2
            if k["toppled"]:
                v = k["vel"]
                if v.lengthSquared() > 1e-4:
                    node.setPos(npos + v * dt)
                    k["vel"] = v * max(0.0, 1.0 - dt * 3.0)

    def _reset_knockables(self):
        if not hasattr(self, "knockables"):
            return
        for k in self.knockables:
            k["toppled"] = False
            k["vel"] = Vec3(0, 0, 0)
            k["node"].setHpr(0, 0, 0)
            k["node"].setPos(k["home"])

    def _build_graybox_fallback(self):
        """GLB 缺失时的程序化灰盒（地/顶/墙），保证仍可玩。"""
        fw = L.FLOOR_X1 - L.FLOOR_X0
        fl = L.FLOOR_Y1 - L.FLOOR_Y0
        cx = (L.FLOOR_X0 + L.FLOOR_X1) / 2
        cy = (L.FLOOR_Y0 + L.FLOOR_Y1) / 2
        cm = CardMaker("floor")
        cm.setFrame(-fw / 2, fw / 2, -fl / 2, fl / 2)
        floor = self.render.attachNewNode(cm.generate())
        floor.setP(-90)
        floor.setPos(cx, cy, 0)
        floor.setColor(0.16, 0.17, 0.18, 1)
        floor.reparentTo(self.level)
        for mx, my, lx, ly in self.walls:
            w = self.loader.loadModel("models/box")
            w.setScale(max(lx, 0.1), max(ly, 0.1), L.WALL_H)
            w.setPos(mx - max(lx, 0.1) / 2, my - max(ly, 0.1) / 2, 0)
            w.setColor(0.22, 0.2, 0.2, 1)
            w.reparentTo(self.level)

    # ---------- 碰撞 ----------

    def _setup_collision(self):
        self.cTrav = CollisionTraverser("traverser")
        self.pusher = CollisionHandlerPusher()
        self.player = self.render.attachNewNode("player")
        self.player.setPos(*L.SPAWN)

        col = CollisionNode("player_col")
        col.addSolid(CollisionSphere(0, 0, 0, 0.5))
        col.setFromCollideMask(BitMask32.bit(0))
        col.setIntoCollideMask(BitMask32.allOff())
        self.player_col = self.player.attachNewNode(col)
        self.pusher.addCollider(self.player_col, self.player)
        self.cTrav.addCollider(self.player_col, self.pusher)

        # 墙段：level_data (中心x, 中心y, 长x, 长y)，底在 z=0、高 WALL_H
        for mx, my, lx, ly in self.walls:
            cn = CollisionNode("wall_col")
            cn.addSolid(CollisionBox(Point3(0, 0, 0),
                                     max(lx, 0.05) * 0.5, max(ly, 0.05) * 0.5,
                                     L.WALL_H * 0.5))
            cn.setIntoCollideMask(BitMask32.bit(0))
            c = self.render.attachNewNode(cn)
            c.setPos(mx, my, L.WALL_H * 0.5)

    # ---------- 灯光 ----------

    def _setup_lighting(self):
        self.render.setShaderAuto()

        # 环境光压到极低：几乎全黑，手电成为主要光源（修"开关手电没区别"）。
        # 断电时用这个暗环境；恢复供电后 _restore_power 会提亮并点亮日光灯。
        self.amb = AmbientLight("amb")
        self.amb_dark = Vec4(0.04, 0.045, 0.06, 1)   # 断电（极暗）
        self.amb_lit = Vec4(0.16, 0.17, 0.20, 1)     # 通电（仍偏暗但可辨）
        self.amb.setColor(self.amb_dark)
        self.render.setLight(self.render.attachNewNode(self.amb))

        # 微弱冷色方向光，仅给墙面一点轮廓，不足以照亮空间
        dl = DirectionalLight("moon")
        dl.setColor(Vec4(0.06, 0.07, 0.10, 1))
        np_dl = self.render.attachNewNode(dl)
        np_dl.setHpr(30, -60, 0)
        self.render.setLight(np_dl)

        # 日光灯（沿中央走廊 + 各房间），断电时全灭；通电后点亮并闪烁
        self.fluorescents = []
        light_spots = [(0, y, 2.9) for y in range(2, 54, 8)]        # 走廊
        light_spots += [(-8, 8, 2.9), (-8, 30, 2.9), (8, 6, 2.9),
                        (8, 33, 2.9), (8, 46, 2.9)]                  # 房间
        for i, (lx, ly, lz) in enumerate(light_spots):
            pl = PointLight(f"fluoro_{i}")
            pl.setColor(Vec4(0.0, 0.0, 0.0, 1))   # 初始灭（断电）
            pl.setAttenuation(Vec3(1.0, 0.04, 0.015))
            np_pl = self.render.attachNewNode(pl)
            np_pl.setPos(lx, ly, lz)
            self.render.setLight(np_pl)
            tube = self.loader.loadModel("models/box")
            tube.setScale(1.4, 0.22, 0.06)
            tube.setPos(lx - 0.7, ly, lz + 0.15)
            tube.setColor(0.9, 0.95, 1.0, 1)
            tube.setColorScale(0.2, 0.2, 0.25, 1)  # 初始暗
            tube.setLightOff()
            tube.reparentTo(self.level)
            self.fluorescents.append({"light": pl, "tube": tube,
                                      "base": 0.55, "phase": i * 1.3})

        # 体积雾：纵深与压迫感
        fog = Fog("hospital_fog")
        fog.setColor(0.02, 0.025, 0.035)
        fog.setExpDensity(0.05)
        self.render.setFog(fog)
        self.fog = fog

    def _setup_flashlight(self):
        # 更亮更聚焦的手电，断电全黑环境下对比强烈
        spot = Spotlight("flashlight")
        lens = PerspectiveLens()
        lens.setFov(42)
        spot.setLens(lens)
        spot.setColor(Vec4(2.6, 2.5, 2.2, 1))
        spot.setAttenuation(Vec3(1.0, 0.0, 0.0022))
        self.flashlight_np = self.camera.attachNewNode(spot)
        self.flashlight_np.setPos(0.2, 0, -0.1)
        self.render.setLight(self.flashlight_np)

    def _setup_camera(self):
        self.camera.reparentTo(self.player)
        self.camera.setPos(0, 0, 0)
        self.camLens.setFov(75)
        self.camLens.setNear(0.1)
        self._last_mouse = None
        # 是否已"首次点击进入"。启动时不自动捕获鼠标——留时间给玩家最大化/全屏/
        # 拖动窗口；等玩家第一次点击窗口再隐藏光标进入视角，之后焦点检测才接管。
        self._entered = False
        self._disable_ime()
        self._release_mouse()
        # 持续检测前台焦点：仅在已首次点击进入后，才自动捕获/释放（每 0.2s 一次）
        self.taskMgr.doMethodLater(0.2, self._auto_focus_capture, "auto_focus")

    def _grab_focus_and_capture(self, task):
        self._force_foreground()
        self._disable_ime()
        if not self.mouse_captured and not self.game_over:
            self._capture_mouse()
        return task.done

    def _get_root_hwnd(self):
        """Panda 的 getWindowHandle 给的是内层渲染窗口，前台窗口是其顶层父窗口。
        用 GetAncestor(GA_ROOT) 取真正的顶层句柄，否则前台焦点判断恒为误判 False。"""
        hwnd = self._get_hwnd()
        if not hwnd or sys.platform != "win32":
            return hwnd
        try:
            import ctypes
            GA_ROOT = 2
            root = ctypes.windll.user32.GetAncestor(hwnd, GA_ROOT)
            return root or hwnd
        except Exception:
            return hwnd

    def _is_foreground(self):
        """本游戏窗口是否为当前前台窗口（有键鼠焦点）。
        同时比对顶层与内层句柄，规避 Panda 句柄层级导致的误判。"""
        if sys.platform != "win32":
            return True
        hwnd = self._get_hwnd()
        root = self._get_root_hwnd()
        if not hwnd:
            return True
        try:
            import ctypes
            fg = ctypes.windll.user32.GetForegroundWindow()
            return fg == hwnd or fg == root
        except Exception:
            return True

    def _auto_focus_capture(self, task):
        """焦点检测：仅在玩家已"首次点击进入"后才生效。
        窗口在前台且未捕获→隐藏光标进入视角；焦点切走→释放光标。
        启动阶段（未点击进入前）完全不动光标，方便最大化/全屏/拖窗口。"""
        if self.game_over or not self._entered:
            return task.again
        fg = self._is_foreground()
        if fg and not self.mouse_captured:
            self._capture_mouse()
        elif not fg and self.mouse_captured:
            self._release_mouse()
        return task.again

    def _get_hwnd(self):
        try:
            if not hasattr(self.win, "getWindowHandle"):
                return 0
            handle = self.win.getWindowHandle()
            if handle is None:
                return 0
            return handle.getIntHandle() or 0
        except Exception:
            return 0

    def _force_foreground(self):
        """强制把游戏窗口拉到前台并抢占键鼠焦点。

        Windows 有'焦点窃取保护'：非前台进程直接调用 SetForegroundWindow 会被
        静默忽略。可靠解法是先用 AttachThreadInput 把本线程挂到当前前台线程的
        输入队列上（这样调用才被允许），再配合模拟一次 ALT 键清除前台锁定。
        """
        if sys.platform != "win32":
            return
        hwnd = self._get_hwnd()
        if not hwnd:
            return
        try:
            import ctypes
            from ctypes import wintypes
            u = ctypes.windll.user32
            k = ctypes.windll.kernel32

            SW_RESTORE = 9
            KEYEVENTF_KEYUP = 0x0002
            VK_MENU = 0x12  # ALT
            ASFW_ANY = -1

            u.AllowSetForegroundWindow(ASFW_ANY)

            fg = u.GetForegroundWindow()
            fg_thread = u.GetWindowThreadProcessId(fg, None)
            our_thread = k.GetCurrentThreadId()

            # ALT 键脉冲：清除前台锁定计时器，让 SetForegroundWindow 生效
            u.keybd_event(VK_MENU, 0, 0, 0)
            u.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

            attached = False
            if fg_thread and fg_thread != our_thread:
                attached = bool(u.AttachThreadInput(fg_thread, our_thread, True))

            u.ShowWindow(hwnd, SW_RESTORE)
            u.BringWindowToTop(hwnd)
            u.SetForegroundWindow(hwnd)
            u.SetActiveWindow(hwnd)
            u.SetFocus(hwnd)

            if attached:
                u.AttachThreadInput(fg_thread, our_thread, False)
        except Exception as e:
            print("force foreground failed (non-fatal):", e)

    def _disable_ime(self):
        """分离窗口的输入法上下文，避免 Shift 等键被输入法拦截切中英文。"""
        if sys.platform != "win32":
            return
        hwnd = self._get_hwnd()
        if not hwnd:
            return
        try:
            import ctypes
            ctypes.windll.imm32.ImmAssociateContext(hwnd, 0)
        except Exception as e:
            print("disable IME failed (non-fatal):", e)

    # ---------- 音频 ----------

    def _load_sfx(self, name, loop=False, vol=1.0):
        p = os.path.join(SOUNDS_DIR, name)
        if not os.path.exists(p):
            print("WARNING missing sfx:", name)
            return None
        s = self.loader.loadSfx(_sfx_path(name))
        s.setLoop(loop)
        s.setVolume(vol)
        return s

    def _setup_audio(self):
        # 3D 定位：护士标识音绑在护士身上，监听者为相机
        self.audio3d = Audio3DManager(self.sfxManagerList[0], self.camera)
        self.audio3d.setDistanceFactor(1.0)
        self.audio3d.setDropOffFactor(1.2)
        self.audio3d.attachListener(self.camera)

        # 2D 音效
        self.sfx_footstep = self._load_sfx("footstep.wav", vol=0.5)
        self.sfx_heartbeat = self._load_sfx("heartbeat.wav", loop=True, vol=0.0)
        self.sfx_door = self._load_sfx("door.wav", vol=0.7)
        self.sfx_pickup = self._load_sfx("pickup.wav", vol=0.6)
        self.sfx_flash = self._load_sfx("flashlight_click.wav", vol=0.5)
        self.sfx_stinger = self._load_sfx("stinger.wav", vol=0.7)
        self.sfx_save = self._load_sfx("save_blip.wav", vol=0.5)

        # 环境底噪（循环，低音量铺底）
        self.ambience = self._load_sfx("ambient_ward.wav", loop=True, vol=0.35)
        if self.ambience:
            self.ambience.play()
        if self.sfx_heartbeat:
            self.sfx_heartbeat.play()

        # 恐怖氛围床（常驻循环，音量偏大，替代原本过于安静的探索乐）
        self.music_horror = None
        horror_path = os.path.join(MUSIC_DIR, "horror_drone.wav")
        if os.path.exists(horror_path):
            self.music_horror = self.loader.loadSfx(_music_path("horror_drone.wav"))
            self.music_horror.setLoop(True)
            self.music_horror_base_vol = 0.85
            self.music_horror.setVolume(self.music_horror_base_vol)
            self.music_horror.play()

        self._footstep_timer = 0.0

    # ---------- 鼠标 / 输入 ----------

    def _win_center_screen(self):
        """返回游戏窗口客户区中心的【屏幕坐标】(sx, sy)，供 SetCursorPos 用。"""
        if sys.platform != "win32":
            return None
        root = self._get_root_hwnd()
        if not root:
            return None
        try:
            import ctypes
            from ctypes import wintypes
            u = ctypes.windll.user32
            rect = wintypes.RECT()
            # 用窗口整体矩形取中心（够用且稳，不依赖客户区换算）
            if not u.GetWindowRect(root, ctypes.byref(rect)):
                return None
            cx = (rect.left + rect.right) // 2
            cy = (rect.top + rect.bottom) // 2
            return cx, cy
        except Exception:
            return None

    def _win_get_cursor(self):
        if sys.platform != "win32":
            return None
        try:
            import ctypes
            from ctypes import wintypes
            pt = wintypes.POINT()
            if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
                return pt.x, pt.y
        except Exception:
            pass
        return None

    def _win_set_cursor(self, sx, sy):
        if sys.platform != "win32":
            return
        try:
            import ctypes
            ctypes.windll.user32.SetCursorPos(int(sx), int(sy))
        except Exception:
            pass

    def _win_show_cursor(self, show):
        """Win32 ShowCursor 是计数器：反复调直到降到目标可见性。"""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            u = ctypes.windll.user32
            # 返回值是调用后的显示计数；<0 表示已隐藏
            for _ in range(8):
                cnt = u.ShowCursor(bool(show))
                if show and cnt >= 0:
                    break
                if (not show) and cnt < 0:
                    break
        except Exception:
            pass

    def _capture_mouse(self):
        """进入视角控制——纯 Win32 方案（不依赖 Panda 的 requestProperties/movePointer，
        那套在本机不生效：光标不隐藏、也读不到位移）。
        隐藏光标用 ShowCursor(FALSE)；转向在 _update 里用 GetCursorPos 相对屏幕中心
        算位移，再 SetCursorPos 拉回中心。"""
        # Panda 侧也请求隐藏（双保险，无害）
        if hasattr(self.win, "requestProperties"):
            props = WindowProperties()
            props.setCursorHidden(True)
            props.setMouseMode(WindowProperties.M_absolute)
            self.win.requestProperties(props)
        self._win_show_cursor(False)
        self.mouse_captured = True
        self._win_primed = False   # 首帧仅归位、不产生位移，避免开局猛甩
        self._center_mouse()

    def _release_mouse(self):
        if hasattr(self.win, "requestProperties"):
            props = WindowProperties()
            props.setCursorHidden(False)
            props.setMouseMode(WindowProperties.M_absolute)
            self.win.requestProperties(props)
        self._win_show_cursor(True)
        self.mouse_captured = False

    def _center_mouse(self):
        """把光标放到窗口中心（优先 Win32 屏幕坐标，回退 Panda movePointer）。"""
        c = self._win_center_screen()
        if c:
            self._win_set_cursor(*c)
            return
        if (self.win is not None and hasattr(self.win, "movePointer")
                and self.win.hasSize()):
            self.win.movePointer(0, int(self.win.getXSize() / 2),
                                 int(self.win.getYSize() / 2))

    def _setup_input(self):
        self.btn_w = KeyboardButton.ascii_key("w")
        self.btn_a = KeyboardButton.ascii_key("a")
        self.btn_s = KeyboardButton.ascii_key("s")
        self.btn_d = KeyboardButton.ascii_key("d")
        self.btn_shift = KeyboardButton.shift()
        self.btn_up = KeyboardButton.up()
        self.btn_down = KeyboardButton.down()
        self.btn_left = KeyboardButton.left()
        self.btn_right = KeyboardButton.right()
        self.accept("escape", self._on_escape)
        self.accept("mouse1", self._on_click_enter)
        self.accept("f", self._toggle_flashlight)
        self.accept("e", self._interact)
        self.accept("c", self._toggle_crouch)
        self.accept("f5", self._do_save)
        self.accept("f9", self._do_load)
        self.accept("r", self._restart)
        self.accept("f3", self._toggle_debug)
        # 密码键盘输入：主键盘数字 + 小键盘数字
        for d in "0123456789":
            self.accept(d, self._keypad_digit, [d])
            self.accept(d + "-repeat", self._keypad_digit, [d])
        self.accept("backspace", self._keypad_backspace)
        self.accept("enter", self._on_enter)
        # 兜底：任何时候按空格都强制重新抢焦点并捕获鼠标
        self.accept("space", self._grab_focus_and_capture_now)
        self.show_debug = False

    def _on_enter(self):
        if self.keypad_active:
            self._submit_keypad()

    def _toggle_debug(self):
        self.show_debug = not self.show_debug

    def _on_click_enter(self):
        """点击窗口进入视角。首次点击标记 _entered，之后焦点检测才接管自动捕获。"""
        self._entered = True
        if not self.game_over:
            self._capture_mouse()

    def _grab_focus_and_capture_now(self):
        self._entered = True
        self._force_foreground()
        self._disable_ime()
        self._capture_mouse()

    def _on_escape(self):
        if self.keypad_active:
            self.keypad_active = False
            self.keypad_input = ""
            self._set_message("已取消密码输入。")
            return
        if self.mouse_captured:
            self._release_mouse()
        else:
            sys.exit()

    def _is_down(self, button):
        mw = self.mouseWatcherNode
        return mw is not None and hasattr(mw, "is_button_down") and mw.is_button_down(button)

    def _toggle_flashlight(self):
        self.flashlight_on = not self.flashlight_on
        if self.flashlight_on:
            self.render.setLight(self.flashlight_np)
        else:
            self.render.clearLight(self.flashlight_np)
        if self.sfx_flash:
            self.sfx_flash.play()

    def _toggle_crouch(self):
        self.crouching = not self.crouching
        self.player.setZ(1.1 if self.crouching else 1.6)

    def _set_message(self, text, dur=4.0):
        self.message = text
        self.msg_timer = dur

    def _nearest_interactive(self, max_d=2.6):
        ppos = self.player.getPos()
        best, best_d = None, max_d
        for cid, pos in L.INTERACTIVES.items():
            d = (Point3(pos[0], pos[1], pos[2]) - ppos).length()
            if d <= best_d:
                best, best_d = cid, d
        return best

    def _interact(self):
        """E 键交互：解谜链 = 读两张纸条得密码 -> 键盘输入 -> 开储物柜取钥匙卡
        -> 配电房用钥匙卡恢复供电 -> 北端安全门离开。"""
        if self.game_over:
            return
        # 若正在键盘输入界面，E 视作"提交密码"
        if self.keypad_active:
            self._submit_keypad()
            return

        cid = self._nearest_interactive()
        if cid is None:
            self._set_message("附近没有可交互的东西。")
            return

        if cid in ("note_ward_a", "note_office"):
            self.notes_found.add(cid)
            if self.sfx_pickup:
                self.sfx_pickup.play()
            if cid == "note_ward_a":
                self._set_message("病历残页：「储物柜密码前两位 47……后两位问办公室。」", 6)
            else:
                self._set_message("便签：「……密码后两位 26。合起来才开得了柜子。」", 6)
            self.interactive_nodes[cid].setColorScale(0.5, 0.5, 0.5, 1)
            self._do_save()
            return

        # 键盘与储物柜/钥匙卡在同一位置：未开→输密码；已开且卡未取→取卡
        if cid in ("keypad_storage", "locker_key"):
            if not self.locker_open:
                self.keypad_active = True
                self.keypad_input = ""
                self._set_message("密码键盘：输入 4 位数字，Enter/E 确认，退格删除，Esc 取消。", 6)
            elif not self.has_keycard:
                self.has_keycard = True
                self.interactive_nodes["locker_key"].hide()
                if self.sfx_pickup:
                    self.sfx_pickup.play()
                self._set_message("拿到【员工钥匙卡】。去配电房（西北）恢复供电。", 6)
                self._do_save()
            else:
                self._set_message("储物柜已经空了。")
            return

        if cid == "fusebox":
            if self.power_on:
                self._set_message("电力已恢复。前往北端安全门离开。")
            elif self.has_keycard:
                self._restore_power()
            else:
                self._set_message("配电箱需要员工钥匙卡才能打开总闸。")
            return

        if cid == "exit_door":
            if self.exit_unlocked:
                if self.sfx_door:
                    self.sfx_door.play()
                self.victory = True
                self.game_over = True
                self._set_message("你刷卡推开安全门，逃出了回声病房。【逃离结局】按 R 重玩", 999)
            else:
                self._set_message("安全门是电控锁，断电时打不开。先恢复供电。")
            return

    def _submit_keypad(self):
        if self.keypad_input == self.secret_code:
            self.keypad_active = False
            self.locker_open = True
            if self.sfx_door:
                self.sfx_door.play()
            self.interactive_nodes["locker_key"].show()
            self._set_message("咔哒——储物柜开了。里面有一张钥匙卡。", 6)
            self._do_save()
        else:
            hint = ""
            if len(self.notes_found) < 2:
                hint = "（线索不全：病房和办公室各有一张纸条）"
            self._set_message(f"密码错误。{hint}", 5)
            self.keypad_input = ""

    def _keypad_digit(self, d):
        if self.keypad_active and len(self.keypad_input) < 4:
            self.keypad_input += d

    def _keypad_backspace(self):
        if self.keypad_active:
            self.keypad_input = self.keypad_input[:-1]

    def _restore_power(self):
        self.power_on = True
        self.exit_unlocked = True
        self.render.setColor(self.amb_lit) if False else None
        self.amb.setColor(self.amb_lit)
        self.exit_door.setColorScale(0.4, 1.3, 0.5, 1)
        self.render.setLight(self.exit_light_np)
        if self.sfx_door:
            self.sfx_door.play()
        self._set_message("总闸合上，灯光复明。北端安全门已解锁——快离开。", 7)
        self._do_save()

    def _collect_state(self):
        pos = self.player.getPos()
        return {
            "player_pos": [round(pos.x, 3), round(pos.y, 3), round(pos.z, 3)],
            "player_heading": round(self.heading, 3),
            "notes_found": sorted(self.notes_found),
            "locker_open": self.locker_open,
            "has_keycard": self.has_keycard,
            "power_on": self.power_on,
            "exit_unlocked": self.exit_unlocked,
        }

    def _apply_state(self, state):
        px, py, pz = state.get("player_pos", list(L.SPAWN))
        self.player.setPos(px, py, pz)
        self.heading = float(state.get("player_heading", 0.0))
        self.player.setH(self.heading)
        self.notes_found = set(state.get("notes_found", []))
        self.locker_open = bool(state.get("locker_open", False))
        self.has_keycard = bool(state.get("has_keycard", False))
        self.power_on = bool(state.get("power_on", False))
        self.exit_unlocked = bool(state.get("exit_unlocked", False))
        for cid in ("note_ward_a", "note_office"):
            if cid in self.notes_found and cid in self.interactive_nodes:
                self.interactive_nodes[cid].setColorScale(0.5, 0.5, 0.5, 1)
        if self.locker_open and not self.has_keycard:
            self.interactive_nodes["locker_key"].show()
        elif self.has_keycard:
            self.interactive_nodes["locker_key"].hide()
        if self.power_on:
            self.amb.setColor(self.amb_lit)
            self.exit_door.setColorScale(0.4, 1.3, 0.5, 1)
            self.render.setLight(self.exit_light_np)

    def _do_save(self):
        ok = self.save_mgr.save(self._collect_state())
        if ok and self.sfx_save:
            self.sfx_save.play()

    def _do_load(self):
        state = self.save_mgr.load()
        if state is None:
            self._set_message("无存档或存档损坏。")
            return
        self._apply_state(state)
        self._set_message("已读档。")

    def _restart(self):
        if not self.game_over:
            return
        self.notes_found.clear()
        self.keypad_active = False
        self.keypad_input = ""
        self.locker_open = False
        self.has_keycard = False
        self.power_on = False
        self.exit_unlocked = False
        self.amb.setColor(self.amb_dark)
        self.render.clearLight(self.exit_light_np)
        self.exit_door.setColorScale(1.2, 0.4, 0.4, 1)
        for cid in ("note_ward_a", "note_office", "keypad_storage", "fusebox"):
            if cid in self.interactive_nodes:
                self.interactive_nodes[cid].setColorScale(1.4, 1.4, 1.4, 1)
        self.interactive_nodes["locker_key"].hide()
        self.player.setPos(*L.SPAWN)
        self.heading = 0.0
        self._reset_knockables()
        self.game_over = False
        self.victory = False
        self.stress = 0.0
        self._set_message("重新开始。找线索、拼密码、恢复供电、逃离。")

    # ---------- HUD ----------

    def _load_cn_font(self):
        for os_path in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"):
            if os.path.exists(os_path):
                try:
                    font = self.loader.loadFont(Filename.fromOsSpecific(os_path).getFullpath())
                    if font and font.isValid():
                        return font
                except Exception:
                    pass
        return None

    def _setup_vignette(self):
        """暗角遮罩：用程序生成的径向渐变贴图铺满屏幕，压暗四角，增强恐怖聚焦。"""
        path = os.path.join(TEX_DIR, "vignette.png")
        if not os.path.exists(path):
            try:
                from PIL import Image
                import numpy as _np
                s = 512
                yy, xx = _np.mgrid[0:s, 0:s]
                cx = cy = s / 2
                d = _np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / (s / 2)
                alpha = _np.clip((d - 0.55) / 0.5, 0, 1) ** 1.6
                rgba = _np.zeros((s, s, 4), dtype=_np.uint8)
                rgba[..., 3] = (alpha * 235).astype(_np.uint8)
                os.makedirs(TEX_DIR, exist_ok=True)
                Image.fromarray(rgba).save(path)
            except Exception as e:
                print("vignette gen failed (non-fatal):", e)
                return
        try:
            self.vignette = OnscreenImage(image=_tex_path("vignette.png"),
                                          pos=(0, 0, 0), scale=(1.34, 1, 1))
            self.vignette.setTransparency(True)
            self.vignette.setBin("fixed", 10)
        except Exception as e:
            print("vignette load failed (non-fatal):", e)

    def _setup_hud(self):
        self._setup_vignette()
        self.cn_font = self._load_cn_font()
        common = dict(scale=0.05, fg=(0.82, 0.86, 0.9, 1), align=TextNode.ALeft, mayChange=True)
        if self.cn_font:
            common["font"] = self.cn_font
        self.hud = OnscreenText(text="", pos=(-1.28, 0.90), **common)
        self.msg = OnscreenText(text="", pos=(0, -0.82), scale=0.055,
                                fg=(0.95, 0.9, 0.8, 1), align=TextNode.ACenter,
                                mayChange=True, font=self.cn_font if self.cn_font else None)
        self.dbg = OnscreenText(text="", pos=(0.98, 0.90), scale=0.045,
                                fg=(0.5, 1.0, 0.6, 1), align=TextNode.ALeft,
                                mayChange=True, font=self.cn_font if self.cn_font else None)
        self._refresh_hud()

    def _refresh_hud(self):
        if not hasattr(self, "hud"):
            return
        if not self.mouse_captured:
            hint = "先最大化/全屏窗口，再点击画面进入视角" if not self._entered else "点击画面重新进入视角（Esc 释放光标）"
            self.hud.setText(f"回声病房 / Echo Ward\n【{hint}；卡住按空格】\n"
                             "WASD 移动 | 鼠标 视角 | F 手电 | E 交互 | C 蹲下 | F5/F9 存读档")
        else:
            fl = "开" if self.flashlight_on else "关"
            # 解谜进度目标
            if not self.locker_open:
                obj = "目标：找线索拼出储物柜密码"
            elif not self.has_keycard:
                obj = "目标：从储物柜取钥匙卡"
            elif not self.power_on:
                obj = "目标：去配电房（西北）恢复供电"
            elif not self.game_over:
                obj = "目标：从北端安全门离开"
            else:
                obj = ""
            power = "供电" if self.power_on else "断电"
            card = " | 钥匙卡✓" if self.has_keycard else ""
            self.hud.setText(
                f"手电:{fl} | 电力:{power}{card} | 线索 {len(self.notes_found)}/2\n"
                f"{obj}"
            )
        if not self.mouse_captured and not self.game_over:
            tip = "调整好窗口后，点击画面开始" if not self._entered else "点击画面继续"
            self.msg.setText(f"{tip}   (Click to play)")
        elif self.keypad_active:
            shown = self.keypad_input + "_" * (4 - len(self.keypad_input))
            self.msg.setText(f"密码键盘： [ {shown} ]   数字键输入 · Enter/E 确认 · Esc 取消")
        else:
            self.msg.setText(self.message if self.msg_timer > 0 or self.game_over else "")

        # F3 诊断浮层
        if getattr(self, "show_debug", False):
            hwnd = self._get_hwnd()
            focused = False
            ptr = "n/a"
            if sys.platform == "win32":
                try:
                    import ctypes
                    focused = (ctypes.windll.user32.GetForegroundWindow() == hwnd)
                except Exception:
                    pass
            if hasattr(self.win, "getPointer") and self.win.hasSize():
                md = self.win.getPointer(0)
                ptr = f"({md.getX()},{md.getY()}) inWin={md.getInWindow()}"
            root = self._get_root_hwnd()
            center = self._win_center_screen()
            cur = self._win_get_cursor()
            self.dbg.setText(
                f"[F3 诊断] hwnd={hwnd} root={root} 前台焦点={focused}\n"
                f"鼠标捕获={self.mouse_captured} 指针={ptr}\n"
                f"窗口中心={center} 光标={cur}\n"
                f"heading={self.heading:.1f} pitch={self.pitch:.1f}\n"
                f"若焦点=False：按空格抢焦点；方向键可转视角作备选"
            )
        else:
            self.dbg.setText("")

    # ---------- 主循环 ----------

    def _update(self, task):
        dt = globalClock.getDt()
        self.noise_this_frame = 0.0

        # 视角：纯 Win32 recenter —— 读光标屏幕坐标相对窗口中心的偏移，应用后拉回中心
        if self.mouse_captured and sys.platform == "win32":
            center = self._win_center_screen()
            cur = self._win_get_cursor()
            if center and cur:
                cx, cy = center
                dx = cur[0] - cx
                dy = cur[1] - cy
                if not getattr(self, "_win_primed", False):
                    self._win_primed = True  # 首帧仅归位
                elif abs(dx) < 600 and abs(dy) < 600 and (dx or dy):
                    self.heading -= dx * self.mouse_sensitivity
                    self.pitch -= dy * self.mouse_sensitivity
                    self.pitch = max(-89, min(89, self.pitch))
                    self.player.setH(self.heading)
                    self.camera.setP(self.pitch)
                self._win_set_cursor(cx, cy)
        elif (self.mouse_captured and hasattr(self.win, "getPointer")
                and self.win.hasSize()):
            # 非 Windows 回退：Panda movePointer recenter
            md = self.win.getPointer(0)
            cx = self.win.getXSize() // 2
            cy = self.win.getYSize() // 2
            if md.getInWindow():
                dx = md.getX() - cx
                dy = md.getY() - cy
                if abs(dx) < 400 and abs(dy) < 400 and (dx or dy):
                    self.heading -= dx * self.mouse_sensitivity
                    self.pitch -= dy * self.mouse_sensitivity
                    self.pitch = max(-89, min(89, self.pitch))
                    self.player.setH(self.heading)
                    self.camera.setP(self.pitch)
            self._center_mouse()

        # 方向键转视角（鼠标失效时的备选，与 WASD 移动分离）
        if not self.game_over:
            turn = 90.0 * dt
            if self._is_down(self.btn_left):
                self.heading += turn
            if self._is_down(self.btn_right):
                self.heading -= turn
            if self._is_down(self.btn_up):
                self.pitch = min(89, self.pitch + turn)
            if self._is_down(self.btn_down):
                self.pitch = max(-89, self.pitch - turn)
            self.player.setH(self.heading)
            self.camera.setP(self.pitch)

        moving = False
        if self.mouse_captured and not self.game_over:
            move = Vec3(0, 0, 0)
            if self._is_down(self.btn_w):
                move.y += 1
            if self._is_down(self.btn_s):
                move.y -= 1
            if self._is_down(self.btn_a):
                move.x -= 1
            if self._is_down(self.btn_d):
                move.x += 1
            running = self._is_down(self.btn_shift) and not self.crouching and self.stamina > 0.05
            if self.crouching:
                speed = self.crouch_speed
            elif running:
                speed = self.run_speed
            else:
                speed = self.walk_speed
            if move.length() > 0:
                moving = True
                move.normalize()
                rad = math.radians(self.heading)
                wx = move.x * math.cos(rad) - move.y * math.sin(rad)
                wy = move.x * math.sin(rad) + move.y * math.cos(rad)
                self.player.setX(self.player.getX() + wx * speed * dt)
                self.player.setY(self.player.getY() + wy * speed * dt)
                self.player.setZ(1.1 if self.crouching else 1.6)
                # 噪声：奔跑最大，行走中等，蹲行很低
                self.noise_this_frame = 1.0 if running else (0.4 if not self.crouching else 0.1)
                # 脚步声
                self._footstep_timer -= dt
                interval = 0.32 if running else (0.5 if not self.crouching else 0.7)
                if self._footstep_timer <= 0 and self.sfx_footstep:
                    self.sfx_footstep.play()
                    self._footstep_timer = interval
            # 体力
            if running and moving:
                self.stamina = max(0.0, self.stamina - dt * 0.28)
            else:
                self.stamina = min(1.0, self.stamina + dt * 0.16)

        # 压力氛围：断电时持续压抑，通电后缓解（不再依赖护士）
        target_stress = 0.7 if not self.power_on else 0.15
        self.stress += (target_stress - self.stress) * min(1.0, dt * 1.5)

        # 动态混音：断电越久越压抑，恐怖床常驻偏大
        if self.ambience:
            self.ambience.setVolume(0.35 * (1.0 - 0.4 * self.stress))
        if self.sfx_heartbeat:
            self.sfx_heartbeat.setVolume(min(0.7, self.stress * 0.8) if self.stress > 0.3 else 0.0)
        if self.music_horror:
            self.music_horror.setVolume(min(1.0, self.music_horror_base_vol + 0.1 * self.stress))

        # 日光灯：断电全灭；通电后点亮并闪烁
        t_now = globalClock.getFrameTime()
        instability = 0.12 + 0.4 * self.stress
        for fl in self.fluorescents:
            if not self.power_on:
                fl["light"].setColor(Vec4(0, 0, 0, 1))
                fl["tube"].setColorScale(0.15, 0.15, 0.2, 1)
                continue
            flick = 0.5 + 0.5 * math.sin(t_now * 6.0 + fl["phase"])
            spike = 1.0 if (math.sin(t_now * 23.0 + fl["phase"]) > (0.9 - instability)) else 0.0
            level = fl["base"] * (0.75 + 0.25 * flick) * (0.3 if spike else 1.0)
            fl["light"].setColor(Vec4(level, level * 1.03, level * 1.06, 1))
            fl["tube"].setColorScale(level * 3, level * 3.1, level * 3.3, 1)

        # 可碰倒道具：身体接触则推倒
        self._update_knockables(dt)

        if hasattr(self, "audio3d"):
            self.audio3d.update()
        if self.msg_timer > 0:
            self.msg_timer -= dt
        self._refresh_hud()
        return task.cont


if __name__ == "__main__":
    app = EchoWardGame()
    app.run()
