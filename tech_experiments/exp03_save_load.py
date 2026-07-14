"""
回声病房 - 阶段1 技术验证 03
存档读写原型

目标：验证游戏状态的存档/读档机制，对应技术设计文档第 6 节。
验证内容：
  - 游戏状态序列化为 JSON（玩家位置/朝向、已收集证据、循环层、事件标记）
  - 存档版本号与兼容处理
  - 自动存档 + 检查点
  - 读档恢复状态
  - 存档不包含任何密钥/凭据

本实验带一个可移动玩家和若干可拾取标记，便于产生真实状态。

运行：
    game_env\Scripts\python.exe tech_experiments\exp03_save_load.py

操作：
    左键点击窗口开始
    WASD/方向键 移动 | 鼠标 视角
    E 拾取附近证据 | F5 存档 | F9 读档 | N 推进循环层
    Esc 释放/退出
"""

from panda3d.core import loadPrcFileData

loadPrcFileData("", "window-title Echo Ward - Tech Exp 03 (Save/Load)")
loadPrcFileData("", "win-size 1280 720")
loadPrcFileData("", "show-frame-rate-meter true")

from direct.showbase.ShowBase import ShowBase
from panda3d.core import (
    AmbientLight, DirectionalLight, CardMaker, Vec3, Vec4, Point3,
    WindowProperties, TextNode, ClockObject, KeyboardButton, Filename,
)
from direct.gui.OnscreenText import OnscreenText
import sys
import os
import json
import time
import math

globalClock = ClockObject.getGlobalClock()

SAVE_VERSION = 1
SAVE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "saves"
)
SAVE_FILE = os.path.join(SAVE_DIR, "autosave.json")


class SaveManager:
    """负责存档的序列化、写入、读取与版本兼容。"""

    def __init__(self, save_file=SAVE_FILE):
        self.save_file = save_file

    def save(self, state: dict) -> bool:
        """写入存档。state 为纯数据字典，禁止包含任何密钥/凭据。"""
        os.makedirs(os.path.dirname(self.save_file), exist_ok=True)
        payload = {
            "version": SAVE_VERSION,
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "state": state,
        }
        try:
            # 先写临时文件再替换，避免写入中断损坏存档
            tmp = self.save_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.save_file)
            return True
        except Exception as e:
            print("SAVE_FAILED:", e)
            return False

    def load(self):
        """读取存档，返回 state 字典；无存档或损坏返回 None。"""
        if not os.path.exists(self.save_file):
            return None
        try:
            with open(self.save_file, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as e:
            print("LOAD_FAILED (corrupt?):", e)
            return None
        version = payload.get("version", 0)
        state = payload.get("state", {})
        if version != SAVE_VERSION:
            state = self._migrate(version, state)
        return state

    def _migrate(self, from_version, state):
        """存档版本迁移占位：未来结构变更时在此兼容旧档。"""
        print(f"migrating save from v{from_version} to v{SAVE_VERSION}")
        return state

    def exists(self):
        return os.path.exists(self.save_file)


class Experiment03(ShowBase):
    """存档读写技术验证。"""

    def __init__(self):
        super().__init__()
        self.disableMouse()
        self.setBackgroundColor(0.02, 0.02, 0.03)

        self.walk_speed = 4.0
        self.run_speed = 7.0
        self.mouse_sensitivity = 0.12
        self.heading = 0.0
        self.pitch = 0.0
        self.mouse_captured = False

        # 游戏状态（会被存档）
        self.loop_layer = 0
        self.collected = set()          # 已拾取证据 id
        self.event_flags = {}           # 事件标记
        self.last_status = "就绪"

        self.save_mgr = SaveManager()

        self._build_scene()
        self._setup_lighting()
        self._setup_camera()
        self._setup_input()
        self._setup_hud()
        self.taskMgr.add(self._update, "update")

    def _build_scene(self):
        cm = CardMaker("floor")
        cm.setFrame(-25, 25, -25, 25)
        floor = self.render.attachNewNode(cm.generate())
        floor.setP(-90)
        floor.setColor(0.18, 0.19, 0.20, 1)

        # 可拾取证据标记（id -> 世界坐标节点）
        self.collectibles = {}
        specs = {
            "evidence_chart": Point3(5, 6, 0.5),
            "evidence_key": Point3(-6, 8, 0.5),
            "evidence_tape": Point3(3, -7, 0.5),
        }
        for cid, pos in specs.items():
            node = self.loader.loadModel("models/box")
            node.setScale(0.4)
            node.setColor(0.9, 0.8, 0.2, 1)
            node.setPos(pos)
            node.reparentTo(self.render)
            self.collectibles[cid] = node

    def _setup_lighting(self):
        self.render.setShaderAuto()
        amb = AmbientLight("amb")
        amb.setColor(Vec4(0.18, 0.19, 0.22, 1))
        self.render.setLight(self.render.attachNewNode(amb))
        dl = DirectionalLight("moon")
        dl.setColor(Vec4(0.2, 0.21, 0.26, 1))
        np_dl = self.render.attachNewNode(dl)
        np_dl.setHpr(30, -60, 0)
        self.render.setLight(np_dl)

    def _setup_camera(self):
        self.player = self.render.attachNewNode("player")
        self.player.setPos(0, 0, 1.6)
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

    def _capture_mouse(self):
        if hasattr(self.win, "requestProperties"):
            props = WindowProperties()
            props.setCursorHidden(True)
            props.setMouseMode(WindowProperties.M_confined)
            self.win.requestProperties(props)
        self.mouse_captured = True
        self._center_mouse()
        self._refresh_hud()

    def _release_mouse(self):
        if hasattr(self.win, "requestProperties"):
            props = WindowProperties()
            props.setCursorHidden(False)
            props.setMouseMode(WindowProperties.M_absolute)
            self.win.requestProperties(props)
        self.mouse_captured = False
        self._refresh_hud()

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
        self.accept("e", self._try_pickup)      # 拾取附近证据
        self.accept("f5", self._do_save)        # 手动存档
        self.accept("f9", self._do_load)        # 读档
        self.accept("n", self._advance_loop)    # 推进循环层

    # ---- 存档状态的收集与恢复 ----

    def _collect_state(self) -> dict:
        """把当前游戏状态收集成纯数据字典（可 JSON 序列化）。
        注意：只放游戏数据，绝不放任何密钥/凭据/绝对路径。"""
        pos = self.player.getPos()
        return {
            "player_pos": [round(pos.x, 3), round(pos.y, 3), round(pos.z, 3)],
            "player_heading": round(self.heading, 3),
            "player_pitch": round(self.pitch, 3),
            "loop_layer": self.loop_layer,
            "collected": sorted(self.collected),
            "event_flags": dict(self.event_flags),
        }

    def _apply_state(self, state: dict):
        """把读到的状态应用回场景。对缺字段做安全默认，兼容旧档。"""
        px, py, pz = state.get("player_pos", [0, 0, 1.6])
        self.player.setPos(px, py, pz)
        self.heading = float(state.get("player_heading", 0.0))
        self.pitch = float(state.get("player_pitch", 0.0))
        self.player.setH(self.heading)
        self.camera.setP(self.pitch)
        self.loop_layer = int(state.get("loop_layer", 0))
        self.collected = set(state.get("collected", []))
        self.event_flags = dict(state.get("event_flags", {}))
        # 已拾取的证据在场景中隐藏
        for cid, node in self.collectibles.items():
            if cid in self.collected:
                node.hide()
            else:
                node.show()

    # ---- 动作 ----

    def _try_pickup(self):
        """拾取距玩家 2m 内、尚未拾取的最近证据。"""
        ppos = self.player.getPos()
        best, best_d = None, 2.0
        for cid, node in self.collectibles.items():
            if cid in self.collected:
                continue
            d = (node.getPos() - ppos).length()
            if d <= best_d:
                best, best_d = cid, d
        if best is not None:
            self.collected.add(best)
            self.collectibles[best].hide()
            self.event_flags[f"picked_{best}"] = True
            self.last_status = f"拾取: {best}"
        else:
            self.last_status = "附近没有可拾取的证据"
        self._refresh_hud()

    def _advance_loop(self):
        self.loop_layer += 1
        self.last_status = f"进入循环层 {self.loop_layer}"
        self._refresh_hud()

    def _do_save(self):
        ok = self.save_mgr.save(self._collect_state())
        self.last_status = "已存档 (F5)" if ok else "存档失败"
        self._refresh_hud()

    def _do_load(self):
        state = self.save_mgr.load()
        if state is None:
            self.last_status = "无存档或存档损坏"
        else:
            self._apply_state(state)
            self.last_status = "已读档 (F9)"
        self._refresh_hud()

    # ---- 中文字体 / HUD ----

    def _load_cn_font(self):
        for os_path in (r"C:\Windows\Fonts\msyh.ttc",
                        r"C:\Windows\Fonts\simhei.ttf"):
            if os.path.exists(os_path):
                try:
                    panda_path = Filename.fromOsSpecific(os_path).getFullpath()
                    font = self.loader.loadFont(panda_path)
                    if font is not None and font.isValid():
                        return font
                except Exception:
                    pass
        return None

    def _setup_hud(self):
        self.cn_font = self._load_cn_font()
        kwargs = dict(text="", pos=(-1.28, 0.90), scale=0.05,
                      fg=(0.8, 0.85, 0.9, 1), align=TextNode.ALeft,
                      mayChange=True)
        if self.cn_font is not None:
            kwargs["font"] = self.cn_font
        self.hud = OnscreenText(**kwargs)
        self._refresh_hud()

    def _refresh_hud(self):
        if not hasattr(self, "hud"):
            return
        remaining = len(self.collectibles) - len(self.collected)
        if not self.mouse_captured:
            self.hud.setText(
                "Echo Ward - Tech Exp 03 (Save/Load)\n"
                "【鼠标左键点击窗口开始】\n"
                "点击后：WASD 移动 | E 拾取 | F5 存档 | F9 读档 | N 循环层\n"
                f"循环层 {self.loop_layer} | 剩余证据 {remaining} | {self.last_status}"
            )
        else:
            self.hud.setText(
                "Echo Ward - Tech Exp 03 (Save/Load)\n"
                "WASD/方向键 移动 | 鼠标 视角 | E 拾取 | F5 存 | F9 读 | N 循环层\n"
                "Esc 释放鼠标（再按一次退出）\n"
                f"循环层 {self.loop_layer} | 剩余证据 {remaining} | {self.last_status}"
            )

    # ---- 主循环 ----

    def _update(self, task):
        dt = globalClock.getDt()

        if (self.mouse_captured and self.mouseWatcherNode is not None
                and hasattr(self.win, "getPointer")
                and self.mouseWatcherNode.hasMouse()):
            md = self.win.getPointer(0)
            cx = self.win.getXSize() / 2
            cy = self.win.getYSize() / 2
            self.heading -= (md.getX() - cx) * self.mouse_sensitivity
            self.pitch -= (md.getY() - cy) * self.mouse_sensitivity
            self.pitch = max(-89, min(89, self.pitch))
            self.player.setH(self.heading)
            self.camera.setP(self.pitch)
            self._center_mouse()

        move = Vec3(0, 0, 0)
        if self.mouse_captured:
            if self._is_down(self.btn_w) or self._is_down(self.btn_up):
                move.y += 1
            if self._is_down(self.btn_s) or self._is_down(self.btn_down):
                move.y -= 1
            if self._is_down(self.btn_a) or self._is_down(self.btn_left):
                move.x -= 1
            if self._is_down(self.btn_d) or self._is_down(self.btn_right):
                move.x += 1
            speed = self.run_speed if self._is_down(self.btn_shift) else self.walk_speed
        else:
            speed = self.walk_speed
        if move.length() > 0:
            move.normalize()
            rad = math.radians(self.heading)
            wx = move.x * math.cos(rad) - move.y * math.sin(rad)
            wy = move.x * math.sin(rad) + move.y * math.cos(rad)
            self.player.setX(self.player.getX() + wx * speed * dt)
            self.player.setY(self.player.getY() + wy * speed * dt)
            self.player.setZ(1.6)
        return task.cont


def _run_selftest():
    """离屏自测：不开窗口，验证存档核心逻辑（存/读/迁移/损坏/无凭据）。
    退出码 0 表示全部通过。"""
    import tempfile

    failures = []

    def check(cond, msg):
        if not cond:
            failures.append(msg)
        print(("PASS " if cond else "FAIL ") + msg)

    tmpdir = tempfile.mkdtemp(prefix="echoward_save_")
    save_file = os.path.join(tmpdir, "autosave.json")
    mgr = SaveManager(save_file=save_file)

    # 1) 无存档时 load 返回 None
    check(mgr.load() is None, "无存档时 load() 返回 None")
    check(not mgr.exists(), "无存档时 exists() 为 False")

    # 2) 存档写入 + 原子替换（无残留 .tmp）
    state = {
        "player_pos": [1.5, -2.0, 1.6],
        "player_heading": 42.0,
        "player_pitch": -5.0,
        "loop_layer": 2,
        "collected": ["evidence_chart", "evidence_tape"],
        "event_flags": {"picked_evidence_chart": True},
    }
    check(mgr.save(state) is True, "save() 返回 True")
    check(os.path.exists(save_file), "存档文件已生成")
    check(not os.path.exists(save_file + ".tmp"), "原子写入无残留 .tmp")

    # 3) 读回一致
    loaded = mgr.load()
    check(loaded == state, "读回的 state 与写入一致")

    # 4) 存档内容含版本号与时间戳，且不含任何疑似凭据
    with open(save_file, "r", encoding="utf-8") as f:
        raw = f.read()
    payload = json.loads(raw)
    check(payload.get("version") == SAVE_VERSION, "存档含正确 version")
    check("saved_at" in payload, "存档含 saved_at 时间戳")
    low = raw.lower()
    check(not any(k in low for k in ("token", "ghp_", "api_key", "apikey",
                                     "secret", "password")),
          "存档不含任何疑似密钥/凭据字段")

    # 5) 版本迁移：伪造旧版本号，load 时触发 _migrate 且不报错
    payload_old = {"version": 0, "saved_at": "old", "state": state}
    with open(save_file, "w", encoding="utf-8") as f:
        json.dump(payload_old, f, ensure_ascii=False)
    migrated = mgr.load()
    check(migrated == state, "旧版本存档经迁移后仍可读")

    # 6) 损坏存档：写入非法 JSON，load 返回 None 而不抛异常
    with open(save_file, "w", encoding="utf-8") as f:
        f.write("{ this is not valid json ")
    check(mgr.load() is None, "损坏存档 load() 安全返回 None")

    # 清理
    try:
        for name in os.listdir(tmpdir):
            os.remove(os.path.join(tmpdir, name))
        os.rmdir(tmpdir)
    except OSError:
        pass

    if failures:
        print(f"\nSELFTEST FAILED: {len(failures)} 项未通过")
        for m in failures:
            print("  -", m)
        return 1
    print("\nSELFTEST PASSED: 存档核心逻辑全部通过")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_run_selftest())
    app = Experiment03()
    app.run()

    def _on_escape(self):
        if self.mouse_captured:
            self._release_mouse()
        else:
            sys.exit()

    def _is_down(self, button):
        mw = self.mouseWatcherNode
        return mw is not None and hasattr(mw, "is_button_down") and mw.is_button_down(button)
