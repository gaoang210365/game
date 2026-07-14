"""
回声病房 / Echo Ward - 可玩原型（灰盒 + 核心循环）

这是把阶段1 技术验证整合成的第一个"能玩"的版本：
  - 第一人称移动 + 碰撞 + 手电筒
  - 灰盒住院部走廊（401~409 房间概念）
  - 拾取证据、单槽自动存档 / 读档
  - 值夜护士 AI 状态机（巡逻 / 察觉 / 追逐 / 搜索 / 返回）
  - 3D 定位音频 + 环境底噪 + 动态混音（接近减底噪、追逐上音乐）
  - 躲藏点、防火门循环触发、心跳/脚步反馈
  - 胜利（集齐证据从防火门离开）/ 失败（被护士抓到）结算

依赖资源：assets/music/ 与 assets/sounds/（若缺失，先运行 assets_gen/make_audio.py）

运行（用游戏专用虚拟环境）：
    game_env\Scripts\python.exe echo_ward_game.py
或经统一入口：
    game_env\Scripts\python.exe main.py --run game

操作：
    左键点击窗口开始
    WASD/方向键 移动 | 鼠标 视角 | Shift 奔跑
    F 手电筒 | E 交互（拾取/开防火门）| C 蹲下躲藏
    F5 存档 | F9 读档 | Esc 释放鼠标 / 退出
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

globalClock = ClockObject.getGlobalClock()

ROOT = os.path.dirname(os.path.abspath(__file__))
SOUNDS_DIR = os.path.join(ROOT, "assets", "sounds")
MUSIC_DIR = os.path.join(ROOT, "assets", "music")
TEX_DIR = os.path.join(ROOT, "assets", "textures")
SAVE_DIR = os.path.join(ROOT, "saves")
SAVE_FILE = os.path.join(SAVE_DIR, "autosave.json")
SAVE_VERSION = 2

# 需要集齐的证据
EVIDENCE_IDS = ["chart_404", "tape_zhou", "keycard", "photo"]


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


class NurseAI:
    """值夜护士 AI 状态机。

    状态：PATROL 巡逻 / SUSPICIOUS 察觉 / CHASE 追逐 / SEARCH 搜索 / RETURN 返回
    感知：视线（前方锥形 + 距离 + 手电照射加成）与噪声（玩家奔跑/开门产生）。
    公平性：追逐速度略低于玩家奔跑，靠走位可摆脱；玩家蹲下躲藏降低被发现概率。
    """

    PATROL, SUSPICIOUS, CHASE, SEARCH, RETURN = range(5)
    STATE_CN = {0: "巡逻", 1: "察觉", 2: "追逐", 3: "搜索", 4: "返回"}

    def __init__(self, node, waypoints, speed_walk=2.6, speed_chase=6.2):
        self.node = node
        self.waypoints = waypoints
        self.wp_index = 0
        self.speed_walk = speed_walk
        self.speed_chase = speed_chase
        self.state = self.PATROL
        self.awareness = 0.0        # 0~1 察觉度
        self.last_known = None       # 最后已知玩家位置
        self.search_timer = 0.0
        self.memory = 0.0            # 循环记忆（跨循环累积，提升灵敏度，有上限）
        self.caught = False

    def sight_check(self, player_pos, facing_deg, flashlight_on, crouching):
        """返回本帧是否"看见"玩家，以及到玩家的距离。"""
        to_p = player_pos - self.node.getPos()
        dist = to_p.length()
        view_range = 16.0 if flashlight_on else 11.0
        if dist > view_range:
            return False, dist
        # 视线锥：护士朝向与"指向玩家"的夹角
        ang = math.degrees(math.atan2(to_p.x, to_p.y))
        diff = abs((ang - facing_deg + 180) % 360 - 180)
        fov = 55.0
        seen = diff < fov
        if crouching and dist > 4.0:
            seen = seen and (diff < fov * 0.5)  # 蹲下更难被余光发现
        return seen, dist

    def update(self, dt, player_pos, facing_deg, flashlight_on, crouching, noise):
        node_pos = self.node.getPos()
        seen, dist = self.sight_check(player_pos, facing_deg, flashlight_on, crouching)

        # 噪声：玩家奔跑/开门抬高察觉度（距离越近越强）
        if noise > 0 and dist < 14.0:
            self.awareness = min(1.0, self.awareness + noise * (1.0 - dist / 14.0) * dt * 2.0)

        # 记忆加成：多次循环后护士更敏锐（有上限，保证后期可通过）
        mem_bonus = 1.0 + min(self.memory, 0.6)

        if seen:
            self.awareness = min(1.0, self.awareness + dt * 1.6 * mem_bonus)
            self.last_known = Point3(player_pos)
        else:
            self.awareness = max(0.0, self.awareness - dt * 0.35)

        # 状态迁移
        if self.state == self.CHASE:
            if not seen and self.awareness < 0.45:
                self.state = self.SEARCH
                self.search_timer = 6.0
        elif self.awareness >= 0.85:
            self.state = self.CHASE
        elif self.awareness >= 0.4:
            self.state = self.SUSPICIOUS
        elif self.state in (self.SUSPICIOUS,):
            self.state = self.PATROL

        # 行为
        if self.state == self.CHASE and self.last_known is not None:
            self._move_toward(self.last_known, self.speed_chase, dt)
            if dist < 1.3:
                self.caught = True
        elif self.state == self.SUSPICIOUS and self.last_known is not None:
            self._move_toward(self.last_known, self.speed_walk * 1.3, dt)
        elif self.state == self.SEARCH:
            self.search_timer -= dt
            if self.last_known is not None:
                self._move_toward(self.last_known, self.speed_walk, dt)
            if self.search_timer <= 0:
                self.state = self.RETURN
        else:  # PATROL / RETURN
            self._patrol(dt)
        return self.caught

    def _patrol(self, dt):
        if not self.waypoints:
            return
        target = Point3(*self.waypoints[self.wp_index], 0.9)
        if self._move_toward(target, self.speed_walk, dt) < 0.5:
            self.wp_index = (self.wp_index + 1) % len(self.waypoints)
            if self.state == self.RETURN:
                self.state = self.PATROL

    def _move_toward(self, target, speed, dt):
        pos = self.node.getPos()
        to_t = Point3(target.x, target.y, pos.z) - pos
        d = to_t.length()
        if d > 1e-4:
            step = min(speed * dt, d)
            self.node.setPos(pos + to_t / d * step)
            self.node.setH(math.degrees(math.atan2(-to_t.x, to_t.y)))
        return d


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

        # 游戏状态
        self.loop_layer = 0
        self.collected = set()
        self.crouching = False
        self.flashlight_on = True
        self.stamina = 1.0
        self.stress = 0.0
        self.game_over = False
        self.win = False
        self.message = "在废弃住院部醒来。找齐 4 份证据，再从走廊尽头的防火门离开。"
        self.msg_timer = 6.0
        self.noise_this_frame = 0.0

        self.save_mgr = SaveManager()

        self._build_scene()
        self._setup_collision()
        self._setup_lighting()
        self._setup_flashlight()
        self._setup_camera()
        self._setup_nurse()
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

        # 贴图
        self.tex_floor = self._load_tex("floor_tile.png")
        self.tex_wall = self._load_tex("wall.png")
        self.tex_ceiling = self._load_tex("ceiling.png")
        self.tex_door = self._load_tex("door.png")
        self.tex_metal = self._load_tex("metal.png")

        # 地板（贴地砖，按尺寸平铺）
        cm = CardMaker("floor")
        cm.setFrame(-6, 6, -2, 46)
        cm.setUvRange((0, 0), (6, 24))
        floor = self.render.attachNewNode(cm.generate())
        floor.setP(-90)
        if self.tex_floor:
            floor.setTexture(self.tex_floor)
        else:
            floor.setColor(0.16, 0.17, 0.18, 1)
        floor.reparentTo(self.level)
        # 天花板
        cmc = CardMaker("ceil")
        cmc.setFrame(-6, 6, -2, 46)
        cmc.setUvRange((0, 0), (6, 24))
        ceil = self.render.attachNewNode(cmc.generate())
        ceil.setP(90)
        ceil.setZ(3.0)
        if self.tex_ceiling:
            ceil.setTexture(self.tex_ceiling)
        else:
            ceil.setColor(0.08, 0.08, 0.10, 1)
        ceil.reparentTo(self.level)

        # 走廊墙体 + 病房隔断（灰盒）：(中心, 尺寸)
        self.walls = []
        wall_specs = [
            (Point3(-5, 22, 0), Vec3(1, 48, 3)),   # 左长墙
            (Point3(5, 22, 0), Vec3(1, 48, 3)),    # 右长墙
            (Point3(0, -2, 0), Vec3(12, 1, 3)),    # 起点后墙
            # 病房隔断（左右交错，形成 401~409 门洞概念）
            (Point3(-3, 6, 0), Vec3(4, 1, 3)),
            (Point3(3, 12, 0), Vec3(4, 1, 3)),
            (Point3(-3, 18, 0), Vec3(4, 1, 3)),
            (Point3(3, 24, 0), Vec3(4, 1, 3)),
            (Point3(-3, 30, 0), Vec3(4, 1, 3)),
            (Point3(3, 36, 0), Vec3(4, 1, 3)),
        ]
        for pos, scale in wall_specs:
            w = self.loader.loadModel("models/box")
            w.setScale(scale)
            w.setPos(pos - Point3(scale.x * 0.5, scale.y * 0.5, 0))
            if self.tex_wall:
                w.setTexture(self.tex_wall)
                w.setTexScale(TextureStage.getDefault(),
                              max(1, scale.x), max(1, scale.z))
            else:
                w.setColor(0.22, 0.2, 0.2, 1)
            w.reparentTo(self.level)
            self.walls.append((pos, scale))

        # 证据点（黄色方块，可拾取）
        self.collectibles = {}
        ev_specs = {
            "chart_404": Point3(-3, 8, 0.6),
            "tape_zhou": Point3(3, 14, 0.6),
            "keycard": Point3(-3, 28, 0.6),
            "photo": Point3(3, 34, 0.6),
        }
        for cid, pos in ev_specs.items():
            node = self.loader.loadModel("models/box")
            node.setScale(0.35)
            node.setColor(0.95, 0.82, 0.2, 1)
            node.setPos(pos)
            node.reparentTo(self.render)
            self.collectibles[cid] = node

        # 躲藏点（蓝色低矮方块，蹲下靠近可降低被发现）
        self.hiding_spots = [Point3(-3.5, 20, 0.4), Point3(3.5, 26, 0.4)]
        for hp in self.hiding_spots:
            h = self.loader.loadModel("models/box")
            h.setScale(1.0, 1.0, 0.8)
            h.setColor(0.2, 0.35, 0.5, 1)
            h.setPos(hp - Point3(0.5, 0.5, 0))
            h.reparentTo(self.level)

        # 防火门（终点，红绿指示）
        self.exit_pos = Point3(0, 42, 0)
        self.exit_door = self.loader.loadModel("models/box")
        self.exit_door.setScale(3, 0.4, 2.6)
        self.exit_door.setPos(self.exit_pos - Point3(1.5, 0.2, 0))
        if self.tex_door:
            self.exit_door.setTexture(self.tex_door)
        self.exit_door.setColorScale(1.2, 0.5, 0.5, 1)
        self.exit_door.reparentTo(self.level)
        # 门上的绿色出口灯（集齐证据后点亮）
        self.exit_light = PointLight("exit_light")
        self.exit_light.setColor(Vec4(0.1, 0.5, 0.15, 1))
        self.exit_light_np = self.render.attachNewNode(self.exit_light)
        self.exit_light_np.setPos(0, 41, 2.5)

    # ---------- 碰撞 ----------

    def _setup_collision(self):
        self.cTrav = CollisionTraverser("traverser")
        self.pusher = CollisionHandlerPusher()
        self.player = self.render.attachNewNode("player")
        self.player.setPos(0, 1, 1.6)

        col = CollisionNode("player_col")
        col.addSolid(CollisionSphere(0, 0, 0, 0.5))
        col.setFromCollideMask(BitMask32.bit(0))
        col.setIntoCollideMask(BitMask32.allOff())
        self.player_col = self.player.attachNewNode(col)
        self.pusher.addCollider(self.player_col, self.player)
        self.cTrav.addCollider(self.player_col, self.pusher)

        for pos, scale in self.walls:
            cn = CollisionNode("wall_col")
            cn.addSolid(CollisionBox(Point3(0, 0, 0),
                                     scale.x * 0.5, scale.y * 0.5, scale.z * 0.5))
            cn.setIntoCollideMask(BitMask32.bit(0))
            c = self.render.attachNewNode(cn)
            c.setPos(pos.x, pos.y, scale.z * 0.5)

    # ---------- 灯光 ----------

    def _setup_lighting(self):
        self.render.setShaderAuto()

        # 提高环境光：昏暗但可辨认路径（不再纯黑）
        amb = AmbientLight("amb")
        amb.setColor(Vec4(0.28, 0.30, 0.36, 1))
        self.render.setLight(self.render.attachNewNode(amb))

        # 冷月光方向光，给墙面一点立体感
        dl = DirectionalLight("moon")
        dl.setColor(Vec4(0.22, 0.24, 0.32, 1))
        np_dl = self.render.attachNewNode(dl)
        np_dl.setHpr(30, -60, 0)
        self.render.setLight(np_dl)

        # 沿走廊的日光灯（点光源），带闪烁
        self.fluorescents = []
        for y in (6, 14, 22, 30, 38):
            pl = PointLight(f"fluoro_{y}")
            pl.setColor(Vec4(0.55, 0.58, 0.60, 1))
            pl.setAttenuation(Vec3(1.0, 0.02, 0.010))
            np_pl = self.render.attachNewNode(pl)
            np_pl.setPos(0, y, 2.8)
            self.render.setLight(np_pl)
            # 灯管本体（自发光小方块）
            tube = self.loader.loadModel("models/box")
            tube.setScale(1.4, 0.25, 0.08)
            tube.setPos(-0.7, y, 2.92)
            tube.setColor(0.9, 0.95, 1.0, 1)
            tube.setColorScale(1.8, 1.9, 2.0, 1)
            tube.setLightOff()
            tube.reparentTo(self.level)
            self.fluorescents.append({"light": pl, "tube": tube,
                                      "base": 0.58, "phase": y * 1.3})

        # 体积雾：营造纵深与压迫感，同时柔化远处
        fog = Fog("hospital_fog")
        fog.setColor(0.05, 0.06, 0.08)
        fog.setExpDensity(0.035)
        self.render.setFog(fog)
        self.fog = fog

    def _setup_flashlight(self):
        spot = Spotlight("flashlight")
        lens = PerspectiveLens()
        lens.setFov(50)
        spot.setLens(lens)
        spot.setColor(Vec4(1.6, 1.5, 1.35, 1))
        spot.setAttenuation(Vec3(1.0, 0.0, 0.004))
        self.flashlight_np = self.camera.attachNewNode(spot)
        self.flashlight_np.setPos(0.2, 0, -0.1)
        self.render.setLight(self.flashlight_np)

    def _setup_camera(self):
        self.camera.reparentTo(self.player)
        self.camera.setPos(0, 0, 0)
        self.camLens.setFov(75)
        self.camLens.setNear(0.1)
        self._last_mouse = None
        self._disable_ime()
        # 抢占前台焦点，并在启动后自动进入视角控制（不再依赖点击）
        if hasattr(self.win, "requestProperties"):
            fg = WindowProperties()
            fg.setForeground(True)
            self.win.requestProperties(fg)
        self._release_mouse()
        # 延迟一帧再捕获，确保窗口已就绪
        self.taskMgr.doMethodLater(0.3, self._auto_capture, "auto_capture")

    def _auto_capture(self, task):
        if not self.mouse_captured and not self.game_over:
            self._capture_mouse()
        return task.done

    def _disable_ime(self):
        if sys.platform != "win32":
            return
        try:
            if not hasattr(self.win, "getWindowHandle"):
                return
            handle = self.win.getWindowHandle()
            if handle is None:
                return
            hwnd = handle.getIntHandle()
            if hwnd:
                import ctypes
                ctypes.windll.imm32.ImmAssociateContext(hwnd, 0)
        except Exception as e:
            print("disable IME failed (non-fatal):", e)

    # ---------- 护士 ----------

    def _setup_nurse(self):
        # 用一个纵向盒作躯干 + 顶部小盒作头，苍白护士感
        self.nurse_node = NodePath("nurse")
        self.nurse_node.reparentTo(self.render)
        self.nurse_node.setPos(0, 40, 0.9)
        body = self.loader.loadModel("models/box")
        body.setScale(0.5, 0.5, 1.4)
        body.setPos(-0.25, -0.25, -0.9)
        body.setColor(0.82, 0.83, 0.86, 1)
        body.reparentTo(self.nurse_node)
        head = self.loader.loadModel("models/box")
        head.setScale(0.32, 0.32, 0.32)
        head.setPos(-0.16, -0.16, 0.55)
        head.setColor(0.9, 0.88, 0.85, 1)
        head.setColorScale(1.3, 1.3, 1.3, 1)
        head.reparentTo(self.nurse_node)
        waypoints = [(-3, 10), (3, 16), (-3, 26), (3, 32), (0, 38)]
        self.nurse = NurseAI(self.nurse_node, waypoints)

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
        self.nurse_clink = None
        clink_path = os.path.join(SOUNDS_DIR, "nurse_iv_clink.wav")
        if os.path.exists(clink_path):
            self.nurse_clink = self.audio3d.loadSfx(_sfx_path("nurse_iv_clink.wav"))
            self.audio3d.attachSoundToObject(self.nurse_clink, self.nurse_node)
            self.audio3d.attachListener(self.camera)
            self.nurse_clink.setLoop(True)
            self.nurse_clink.setVolume(0.9)
            self.nurse_clink.play()

        # 2D 音效
        self.sfx_footstep = self._load_sfx("footstep.wav", vol=0.5)
        self.sfx_heartbeat = self._load_sfx("heartbeat.wav", loop=True, vol=0.0)
        self.sfx_door = self._load_sfx("door.wav", vol=0.7)
        self.sfx_pickup = self._load_sfx("pickup.wav", vol=0.6)
        self.sfx_flash = self._load_sfx("flashlight_click.wav", vol=0.5)
        self.sfx_stinger = self._load_sfx("stinger.wav", vol=0.7)
        self.sfx_save = self._load_sfx("save_blip.wav", vol=0.5)

        # 环境底噪（循环）
        self.ambience = self._load_sfx("ambient_ward.wav", loop=True, vol=0.55)
        if self.ambience:
            self.ambience.play()
        if self.sfx_heartbeat:
            self.sfx_heartbeat.play()

        # 音乐：追逐（循环，默认静音，进入追逐淡入）
        self.music_chase = None
        chase_path = os.path.join(MUSIC_DIR, "chase.wav")
        if os.path.exists(chase_path):
            self.music_chase = self.loader.loadSfx(_music_path("chase.wav"))
            self.music_chase.setLoop(True)
            self.music_chase.setVolume(0.0)
            self.music_chase.play()

        self._footstep_timer = 0.0

    # ---------- 鼠标 / 输入 ----------

    def _capture_mouse(self):
        """进入视角控制：用 M_relative（相对模式）——系统自动隐藏并锁定光标，
        每帧从 pointer 读到的是相对位移，无需手动回中，兼容性最好。"""
        if hasattr(self.win, "requestProperties"):
            props = WindowProperties()
            props.setCursorHidden(True)
            props.setMouseMode(WindowProperties.M_relative)
            props.setForeground(True)
            self.win.requestProperties(props)
        self.mouse_captured = True
        self._last_mouse = None

    def _release_mouse(self):
        if hasattr(self.win, "requestProperties"):
            props = WindowProperties()
            props.setCursorHidden(False)
            props.setMouseMode(WindowProperties.M_absolute)
            self.win.requestProperties(props)
        self.mouse_captured = False

    def _center_mouse(self):
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
        self.accept("mouse1", self._capture_mouse)
        self.accept("f", self._toggle_flashlight)
        self.accept("e", self._interact)
        self.accept("c", self._toggle_crouch)
        self.accept("f5", self._do_save)
        self.accept("f9", self._do_load)
        self.accept("r", self._restart)

    def _on_escape(self):
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

    def _interact(self):
        if self.game_over:
            return
        ppos = self.player.getPos()
        # 先尝试拾取证据
        best, best_d = None, 2.2
        for cid, node in self.collectibles.items():
            if cid in self.collected:
                continue
            d = (node.getPos() - ppos).length()
            if d <= best_d:
                best, best_d = cid, d
        if best is not None:
            self.collected.add(best)
            self.collectibles[best].hide()
            if self.sfx_pickup:
                self.sfx_pickup.play()
            self._set_message(f"拾取证据：{best}（{len(self.collected)}/{len(EVIDENCE_IDS)}）")
            self._do_save()  # 自动存档
            return
        # 再尝试防火门
        if (self.exit_pos - ppos).length() < 3.0:
            if len(self.collected) >= len(EVIDENCE_IDS):
                if self.sfx_door:
                    self.sfx_door.play()
                self.win = True
                self.game_over = True
                self._set_message("你推开防火门……时间再次倒退。【逃离结局】按 R 重玩", 999)
            else:
                miss = len(EVIDENCE_IDS) - len(self.collected)
                self._set_message(f"防火门锁着。还需 {miss} 份证据。")
            return
        self._set_message("附近没有可交互的东西。")

    def _collect_state(self):
        pos = self.player.getPos()
        return {
            "player_pos": [round(pos.x, 3), round(pos.y, 3), round(pos.z, 3)],
            "player_heading": round(self.heading, 3),
            "loop_layer": self.loop_layer,
            "collected": sorted(self.collected),
            "nurse_memory": round(self.nurse.memory, 3),
        }

    def _apply_state(self, state):
        px, py, pz = state.get("player_pos", [0, 1, 1.6])
        self.player.setPos(px, py, pz)
        self.heading = float(state.get("player_heading", 0.0))
        self.player.setH(self.heading)
        self.loop_layer = int(state.get("loop_layer", 0))
        self.collected = set(state.get("collected", []))
        self.nurse.memory = float(state.get("nurse_memory", 0.0))
        for cid, node in self.collectibles.items():
            node.hide() if cid in self.collected else node.show()

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
        # 循环推进：护士记忆累积（有上限），场景重置
        self.loop_layer += 1
        self.nurse.memory = min(self.nurse.memory + 0.2, 0.6)
        self.collected.clear()
        for node in self.collectibles.values():
            node.show()
        self.player.setPos(0, 1, 1.6)
        self.heading = 0.0
        self.nurse_node.setPos(0, 40, 0.9)
        self.nurse.state = NurseAI.PATROL
        self.nurse.awareness = 0.0
        self.nurse.caught = False
        self.game_over = False
        self.win = False
        self.stress = 0.0
        self._set_message(f"循环层 {self.loop_layer}：护士似乎更警觉了……")

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
        self._refresh_hud()

    def _refresh_hud(self):
        if not hasattr(self, "hud"):
            return
        if not self.mouse_captured:
            self.hud.setText("回声病房 / Echo Ward\n【鼠标已释放 — 点击窗口重新控制视角】\n"
                             "WASD 移动 | 鼠标 视角 | F 手电 | E 交互 | C 蹲下 | F5/F9 存读档")
        else:
            fl = "开" if self.flashlight_on else "关"
            st = NurseAI.STATE_CN[self.nurse.state]
            crouch = " [蹲]" if self.crouching else ""
            self.hud.setText(
                f"循环层 {self.loop_layer} | 证据 {len(self.collected)}/{len(EVIDENCE_IDS)} | 手电:{fl}{crouch}\n"
                f"护士状态：{st} | 察觉度：{self.nurse.awareness:.0%}\n"
                f"体力：{self.stamina:.0%}"
            )
        self.msg.setText(self.message if self.msg_timer > 0 or self.game_over else "")

    # ---------- 主循环 ----------

    def _update(self, task):
        dt = globalClock.getDt()
        self.noise_this_frame = 0.0

        # 视角（M_relative：pointer 的绝对值即为相对累积，用差分得到帧位移）
        if (self.mouse_captured and hasattr(self.win, "getPointer")):
            md = self.win.getPointer(0)
            if md.getInWindow() or self._last_mouse is not None:
                mx, my = md.getX(), md.getY()
                if self._last_mouse is not None:
                    dx = mx - self._last_mouse[0]
                    dy = my - self._last_mouse[1]
                    # 过滤异常大跳变（切窗/重置）
                    if abs(dx) < 200 and abs(dy) < 200:
                        self.heading -= dx * self.mouse_sensitivity
                        self.pitch -= dy * self.mouse_sensitivity
                        self.pitch = max(-89, min(89, self.pitch))
                        self.player.setH(self.heading)
                        self.camera.setP(self.pitch)
                self._last_mouse = (mx, my)

        moving = False
        if self.mouse_captured and not self.game_over:
            move = Vec3(0, 0, 0)
            if self._is_down(self.btn_w) or self._is_down(self.btn_up):
                move.y += 1
            if self._is_down(self.btn_s) or self._is_down(self.btn_down):
                move.y -= 1
            if self._is_down(self.btn_a) or self._is_down(self.btn_left):
                move.x -= 1
            if self._is_down(self.btn_d) or self._is_down(self.btn_right):
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

        # 护士 AI
        if not self.game_over:
            caught = self.nurse.update(dt, self.player.getPos(), self.nurse_node.getH(),
                                       self.flashlight_on, self.crouching,
                                       self.noise_this_frame)
            if caught:
                self.game_over = True
                self.win = False
                if self.sfx_stinger:
                    self.sfx_stinger.play()
                self._set_message("值夜护士抓住了你……【失败】按 R 重新循环", 999)

        # 压力 = 察觉度 + 距离贴近
        dist = (self.nurse_node.getPos() - self.player.getPos()).length()
        target_stress = max(self.nurse.awareness, max(0.0, 1.0 - dist / 12.0))
        self.stress += (target_stress - self.stress) * min(1.0, dt * 3.0)

        # 动态混音：接近/追逐减底噪、上心跳、追逐上音乐
        if self.ambience:
            self.ambience.setVolume(0.55 * (1.0 - 0.6 * self.stress))
        if self.sfx_heartbeat:
            self.sfx_heartbeat.setVolume(min(0.8, self.stress * 0.9) if self.stress > 0.25 else 0.0)
        if self.music_chase:
            target = 0.55 if self.nurse.state == NurseAI.CHASE else 0.0
            cur = self.music_chase.getVolume()
            self.music_chase.setVolume(cur + (target - cur) * min(1.0, dt * 2.0))

        # 日光灯闪烁（护士接近/追逐时更不稳定，恐怖增强）
        t_now = globalClock.getFrameTime()
        instability = 0.15 + 0.5 * self.stress
        for fl in self.fluorescents:
            flick = 0.5 + 0.5 * math.sin(t_now * 6.0 + fl["phase"])
            spike = 1.0 if (math.sin(t_now * 23.0 + fl["phase"]) > (0.9 - instability)) else 0.0
            level = fl["base"] * (0.75 + 0.25 * flick) * (0.35 if spike else 1.0)
            fl["light"].setColor(Vec4(level, level * 1.03, level * 1.06, 1))
            fl["tube"].setColorScale(level * 3, level * 3.1, level * 3.3, 1)

        # 防火门指示：集齐证据变绿
        if len(self.collected) >= len(EVIDENCE_IDS):
            self.exit_door.setColorScale(0.4, 1.3, 0.5, 1)
            if not getattr(self, "_exit_lit", False):
                self.render.setLight(self.exit_light_np)
                self._exit_lit = True

        if hasattr(self, "audio3d"):
            self.audio3d.update()
        if self.msg_timer > 0:
            self.msg_timer -= dt
        self._refresh_hud()
        return task.cont


if __name__ == "__main__":
    app = EchoWardGame()
    app.run()
