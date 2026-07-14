"""
回声病房 - 阶段1 技术验证 02
3D 音源与距离衰减

目标：验证 Panda3D 的 3D 定位音频能否支撑"声音先于视觉"的恐怖设计。
一个发声物体（红色方块，代表怪物音源）在场景中来回移动，
玩家移动/转向时应能通过音量与左右声道判断它的方位和远近。

依赖：assets/sounds/test_beacon.wav
    若不存在，先运行 make_test_sound.py 生成。

运行：
    game_env\Scripts\python.exe tech_experiments\exp02_audio_3d.py

操作：
    左键点击窗口开始
    W/A/S/D 或方向键 移动 | 鼠标 视角 | Esc 释放/退出
"""

from panda3d.core import loadPrcFileData

loadPrcFileData("", "window-title Echo Ward - Tech Exp 02 (3D Audio)")
loadPrcFileData("", "win-size 1280 720")
loadPrcFileData("", "audio-library-name p3openal_audio")
loadPrcFileData("", "show-frame-rate-meter true")

from direct.showbase.ShowBase import ShowBase
from direct.showbase.Audio3DManager import Audio3DManager
from panda3d.core import (
    AmbientLight, DirectionalLight, Spotlight, PerspectiveLens,
    CardMaker, Vec3, Vec4, Point3, NodePath, WindowProperties,
    TextNode, ClockObject, KeyboardButton,
)
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import Filename
import sys
import os
import math

globalClock = ClockObject.getGlobalClock()

_SOUNDS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "sounds",
)
_BEACON_OS_PATH = os.path.join(_SOUNDS_DIR, "test_beacon.wav")
_AMBIENCE_OS_PATH = os.path.join(_SOUNDS_DIR, "horror_ambience.wav")
# Panda3D 需要 Unix 风格路径（面板内部路径），用 Filename 转换
SOUND_PATH = Filename.fromOsSpecific(_BEACON_OS_PATH).getFullpath()
AMBIENCE_PATH = Filename.fromOsSpecific(_AMBIENCE_OS_PATH).getFullpath()

# 混音比例（配合"声音先于视觉"：定位音源保持清晰，背景压低铺底）
BEACON_VOLUME = 1.0     # 3D 定位音源（会再随距离衰减）
AMBIENCE_VOLUME = 0.65  # 2D 背景氛围（调大：更有压迫感，但仍低于定位音源）


class Experiment02(ShowBase):
    """3D 音源技术验证。"""

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

        self.source_pos = Point3(8, 8, 1.2)
        self.source_dir = 1
        self.distance = 0.0

        self._build_scene()
        self._setup_lighting()
        self._setup_camera()
        self._setup_audio()
        self._setup_input()
        self._setup_hud()
        self.taskMgr.add(self._update, "update")

    def _build_scene(self):
        cm = CardMaker("floor")
        cm.setFrame(-25, 25, -25, 25)
        floor = self.render.attachNewNode(cm.generate())
        floor.setP(-90)
        floor.setColor(0.18, 0.19, 0.20, 1)
        self.floor = floor

        # 发声物体（红色方块）
        self.source = self.loader.loadModel("models/box")
        self.source.setScale(0.8)
        self.source.setColor(0.8, 0.15, 0.15, 1)
        self.source.reparentTo(self.render)
        self.source.setPos(self.source_pos)

    def _setup_lighting(self):
        self.render.setShaderAuto()
        amb = AmbientLight("amb")
        amb.setColor(Vec4(0.12, 0.13, 0.16, 1))
        self.render.setLight(self.render.attachNewNode(amb))
        dl = DirectionalLight("moon")
        dl.setColor(Vec4(0.15, 0.16, 0.2, 1))
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

    def _setup_audio(self):
        """3D 定位音源（怪物）+ 2D 背景恐怖氛围，按比例混音。"""
        self.beacon = None
        self.ambience = None

        # 3D 定位音源：监听者绑相机，音源绑发声物体
        self.audio3d = Audio3DManager(self.sfxManagerList[0], self.camera)
        self.audio3d.setDistanceFactor(1.0)
        self.audio3d.setDropOffFactor(1.0)
        if os.path.exists(_BEACON_OS_PATH):
            self.beacon = self.audio3d.loadSfx(SOUND_PATH)
            self.audio3d.attachSoundToObject(self.beacon, self.source)
            self.audio3d.attachListener(self.camera)
            self.beacon.setLoop(True)
            self.beacon.setVolume(BEACON_VOLUME)
            self.beacon.play()
        else:
            print("WARNING: beacon missing:", _BEACON_OS_PATH)

        # 2D 背景氛围：不定位，直接用 sfx 管理器播放，音量压低铺底
        if os.path.exists(_AMBIENCE_OS_PATH):
            self.ambience = self.loader.loadSfx(AMBIENCE_PATH)
            self.ambience.setLoop(True)
            self.ambience.setVolume(AMBIENCE_VOLUME)
            self.ambience.play()
        else:
            print("WARNING: ambience missing:", _AMBIENCE_OS_PATH)

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

    def _on_escape(self):
        if self.mouse_captured:
            self._release_mouse()
        else:
            sys.exit()

    def _is_down(self, button):
        mw = self.mouseWatcherNode
        return mw is not None and hasattr(mw, "is_button_down") and mw.is_button_down(button)

    def _load_cn_font(self):
        """加载系统中文字体，失败则返回 None（回退默认字体）。"""
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
        if not self.mouse_captured:
            self.hud.setText("Echo Ward - Tech Exp 02 (3D Audio)\n"
                             "【鼠标左键点击窗口开始】\n"
                             "红色方块是移动音源，靠听觉判断其方位")
        else:
            self.hud.setText("Echo Ward - Tech Exp 02 (3D Audio)\n"
                             "WASD/方向键 移动 | 鼠标 视角 | Esc 释放\n"
                             f"音源距离: {self.distance:.1f} m")

    def _update(self, task):
        dt = globalClock.getDt()

        # 音源来回移动
        self.source_pos.x += self.source_dir * 2.5 * dt
        if self.source_pos.x > 12:
            self.source_dir = -1
        elif self.source_pos.x < -12:
            self.source_dir = 1
        self.source.setPos(self.source_pos)

        # 视角
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

        # 移动
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

        # 更新 3D 音频与距离显示
        if hasattr(self, "audio3d"):
            self.audio3d.update()
        self.distance = (self.source_pos - self.player.getPos()).length()
        self._refresh_hud()
        return task.cont


if __name__ == "__main__":
    app = Experiment02()
    app.run()
