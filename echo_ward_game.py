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

from direct.showbase.ShowBase import ShowBase
from direct.showbase.Audio3DManager import Audio3DManager
from panda3d.core import (
    AmbientLight, DirectionalLight, Spotlight, PerspectiveLens,
    CardMaker, Vec3, Vec4, Point3, NodePath, WindowProperties,
    CollisionTraverser, CollisionHandlerPusher, CollisionNode,
    CollisionSphere, CollisionBox, BitMask32, TextNode,
    ClockObject, KeyboardButton, Filename,
)
from direct.gui.OnscreenText import OnscreenText
import sys
import os
import json
import time
import math

globalClock = ClockObject.getGlobalClock()

ROOT = os.path.dirname(os.path.abspath(__file__))
SOUNDS_DIR = os.path.join(ROOT, "assets", "sounds")
MUSIC_DIR = os.path.join(ROOT, "assets", "music")
SAVE_DIR = os.path.join(ROOT, "saves")
SAVE_FILE = os.path.join(SAVE_DIR, "autosave.json")
SAVE_VERSION = 2

# 需要集齐的证据
EVIDENCE_IDS = ["chart_404", "tape_zhou", "keycard", "photo"]


def _sfx_path(name):
    return Filename.fromOsSpecific(os.path.join(SOUNDS_DIR, name)).getFullpath()


def _music_path(name):
    return Filename.fromOsSpecific(os.path.join(MUSIC_DIR, name)).getFullpath()


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

    def _build_scene(self):
        self.level = NodePath("level")
        self.level.reparentTo(self.render)

        # 地板 + 天花板
        cm = CardMaker("floor")
        cm.setFrame(-6, 6, -2, 46)
        floor = self.render.attachNewNode(cm.generate())
        floor.setP(-90)
        floor.setColor(0.16, 0.17, 0.18, 1)
        floor.reparentTo(self.level)
        ceil = self.render.attachNewNode(cm.generate())
        ceil.setP(90)
        ceil.setZ(3.0)
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
        self.exit_door.setColor(0.5, 0.15, 0.15, 1)
        self.exit_door.reparentTo(self.level)

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
        amb = AmbientLight("amb")
        amb.setColor(Vec4(0.06, 0.07, 0.09, 1))
        self.render.setLight(self.render.attachNewNode(amb))
        dl = DirectionalLight("moon")
        dl.setColor(Vec4(0.08, 0.09, 0.13, 1))
        np_dl = self.render.attachNewNode(dl)
        np_dl.setHpr(30, -60, 0)
        self.render.setLight(np_dl)

    def _setup_flashlight(self):
        spot = Spotlight("flashlight")
        lens = PerspectiveLens()
        lens.setFov(42)
        spot.setLens(lens)
        spot.setColor(Vec4(1.1, 1.05, 0.95, 1))
        spot.setAttenuation(Vec3(1.0, 0.0, 0.008))
        self.flashlight_np = self.camera.attachNewNode(spot)
        self.render.setLight(self.flashlight_np)

    def _setup_camera(self):
        self.camera.reparentTo(self.player)
        self.camera.setPos(0, 0, 0)
        self.camLens.setFov(75)
        self.camLens.setNear(0.1)
        self._disable_ime()
        self._release_mouse()

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
        self.nurse_node = self.loader.loadModel("models/box")
        self.nurse_node.setScale(0.5, 0.5, 1.7)
        self.nurse_node.setColor(0.75, 0.75, 0.8, 1)
        self.nurse_node.setPos(0, 40, 0.9)
        self.nurse_node.reparentTo(self.render)
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
        if hasattr(self.win, "requestProperties"):
            props = WindowProperties()
            props.setCursorHidden(True)
            props.setMouseMode(WindowProperties.M_confined)
            self.win.requestProperties(props)
        self.mouse_captured = True
        self._center_mouse()

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

    def _setup_hud(self):
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
            self.hud.setText("回声病房 / Echo Ward\n【鼠标左键点击窗口开始】\n"
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

        # 视角
        if (self.mouse_captured and self.mouseWatcherNode is not None
                and hasattr(self.win, "getPointer") and self.mouseWatcherNode.hasMouse()):
            md = self.win.getPointer(0)
            cx, cy = self.win.getXSize() / 2, self.win.getYSize() / 2
            self.heading -= (md.getX() - cx) * self.mouse_sensitivity
            self.pitch -= (md.getY() - cy) * self.mouse_sensitivity
            self.pitch = max(-89, min(89, self.pitch))
            self.player.setH(self.heading)
            self.camera.setP(self.pitch)
            self._center_mouse()

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

        # 防火门指示：集齐证据变绿
        if len(self.collected) >= len(EVIDENCE_IDS):
            self.exit_door.setColor(0.15, 0.5, 0.2, 1)

        if hasattr(self, "audio3d"):
            self.audio3d.update()
        if self.msg_timer > 0:
            self.msg_timer -= dt
        self._refresh_hud()
        return task.cont


if __name__ == "__main__":
    app = EchoWardGame()
    app.run()
