"""
回声病房 - 阶段1 技术验证 01
第一人称控制 + 碰撞 + 基础灯光 + 手电筒

目标：验证 Panda3D 能否支撑本项目最核心的交互与氛围。
本文件只做技术验证，不是正式游戏内容。

运行：
    game_env\Scripts\python.exe tech_experiments\exp01_fps_flashlight.py

操作：
    W/A/S/D  移动
    鼠标      视角
    Shift    奔跑
    F        手电筒开关
    Esc      退出
"""

from panda3d.core import loadPrcFileData

loadPrcFileData("", "window-title Echo Ward - Tech Exp 01")
loadPrcFileData("", "win-size 1280 720")
loadPrcFileData("", "undecorated false")
loadPrcFileData("", "sync-video true")
loadPrcFileData("", "show-frame-rate-meter true")

from direct.showbase.ShowBase import ShowBase
from panda3d.core import (
    AmbientLight, DirectionalLight, Spotlight, PerspectiveLens,
    CardMaker, Vec3, Vec4, Point3, NodePath, WindowProperties,
    CollisionTraverser, CollisionHandlerPusher, CollisionNode,
    CollisionSphere, CollisionBox, BitMask32, TextNode,
    ClockObject, KeyboardButton, Filename,
)
from direct.gui.OnscreenText import OnscreenText
import sys
import math

globalClock = ClockObject.getGlobalClock()


class Experiment01(ShowBase):
    """第一人称 + 手电筒技术验证。"""

    def __init__(self):
        super().__init__()

        self.disableMouse()
        self.setBackgroundColor(0.02, 0.02, 0.03)

        # 移动参数
        self.walk_speed = 4.0
        self.run_speed = 7.0
        self.mouse_sensitivity = 0.12
        self.heading = 0.0
        self.pitch = 0.0

        # 输入状态
        self.keys = {"w": False, "s": False, "a": False, "d": False, "run": False}
        self.flashlight_on = True

        self._build_scene()
        self._setup_collision()
        self._setup_lighting()
        self._setup_flashlight()
        self._setup_camera()
        self._setup_input()
        self._setup_hud()

        self.taskMgr.add(self._update, "update")

    def _build_scene(self):
        """搭建一个简单走廊灰盒。"""
        self.level = NodePath("level")
        self.level.reparentTo(self.render)

        # 地板
        cm = CardMaker("floor")
        cm.setFrame(-20, 20, -20, 20)
        floor = self.render.attachNewNode(cm.generate())
        floor.setP(-90)
        floor.setColor(0.18, 0.19, 0.20, 1)
        floor.reparentTo(self.level)
        self.floor = floor

        # 天花板
        ceil = self.render.attachNewNode(cm.generate())
        ceil.setP(90)
        ceil.setZ(3.0)
        ceil.setColor(0.10, 0.10, 0.12, 1)
        ceil.reparentTo(self.level)

        # 障碍物/墙体（用 box 模型）
        self.obstacles = []
        box_positions = [
            (Point3(-4, 6, 0), Vec3(1, 8, 3)),
            (Point3(4, 6, 0), Vec3(1, 8, 3)),
            (Point3(0, 12, 0), Vec3(3, 1, 3)),
            (Point3(-2, 3, 0), Vec3(1, 1, 1.2)),
            (Point3(3, 9, 0), Vec3(0.8, 0.8, 1.5)),
        ]
        for pos, scale in box_positions:
            box = self.loader.loadModel("models/box")
            box.setScale(scale)
            # box 模型原点在角落，做居中
            box.setPos(pos - Point3(scale.x * 0.5, scale.y * 0.5, 0))
            box.setColor(0.25, 0.22, 0.22, 1)
            box.reparentTo(self.level)
            self.obstacles.append((box, pos, scale))

    def _setup_collision(self):
        """玩家碰撞体，使用 Pusher 防止穿墙。"""
        self.cTrav = CollisionTraverser("traverser")
        self.pusher = CollisionHandlerPusher()

        self.player = self.render.attachNewNode("player")
        self.player.setPos(0, 0, 1.6)

        col_node = CollisionNode("player_col")
        col_node.addSolid(CollisionSphere(0, 0, 0, 0.5))
        col_node.setFromCollideMask(BitMask32.bit(0))
        col_node.setIntoCollideMask(BitMask32.allOff())
        self.player_col = self.player.attachNewNode(col_node)

        self.pusher.addCollider(self.player_col, self.player)
        self.cTrav.addCollider(self.player_col, self.pusher)

        # 障碍物碰撞体
        for box, pos, scale in self.obstacles:
            cn = CollisionNode("obstacle_col")
            cn.addSolid(CollisionBox(Point3(0, 0, 0),
                                     scale.x * 0.5, scale.y * 0.5, scale.z * 0.5))
            cn.setIntoCollideMask(BitMask32.bit(0))
            col = self.render.attachNewNode(cn)
            col.setPos(pos.x, pos.y, scale.z * 0.5)

    def _setup_lighting(self):
        """基础环境光 + 方向光，营造昏暗基调。"""
        self.render.setShaderAuto()

        ambient = AmbientLight("ambient")
        ambient.setColor(Vec4(0.08, 0.09, 0.11, 1))
        self.ambient_np = self.render.attachNewNode(ambient)
        self.render.setLight(self.ambient_np)

        directional = DirectionalLight("moon")
        directional.setColor(Vec4(0.10, 0.11, 0.15, 1))
        self.dir_np = self.render.attachNewNode(directional)
        self.dir_np.setHpr(30, -60, 0)
        self.render.setLight(self.dir_np)

    def _setup_flashlight(self):
        """手电筒：跟随相机的聚光灯。"""
        spot = Spotlight("flashlight")
        lens = PerspectiveLens()
        lens.setFov(45)
        spot.setLens(lens)
        spot.setColor(Vec4(1.1, 1.05, 0.95, 1))
        spot.setAttenuation(Vec3(1.0, 0.0, 0.010))
        self.flashlight_np = self.camera.attachNewNode(spot)
        self.flashlight_np.setPos(0, 0, 0)
        self.render.setLight(self.flashlight_np)

    def _setup_camera(self):
        """相机挂到玩家节点，第一人称视角。"""
        self.camera.reparentTo(self.player)
        self.camera.setPos(0, 0, 0)
        self.camLens.setFov(75)
        self.camLens.setNear(0.1)

        # 让窗口脱离输入法(IME)：即使误按 Shift 切换了中英文，
        # 按键也直接以原始信号进入游戏，不会再被当作文本输入。
        self._disable_ime()

        # 启动时不隐藏/锁定鼠标：先让玩家能点击窗口获取焦点。
        # 点击窗口后进入"捕获"模式（隐藏光标 + 视角控制），Esc 释放。
        self.mouse_captured = False
        self._release_mouse()

    def _disable_ime(self):
        """在 Windows 上分离窗口的 IME 上下文，避免输入法拦截按键。"""
        if sys.platform != "win32":
            return
        try:
            if not hasattr(self.win, "getWindowHandle"):
                return
            handle = self.win.getWindowHandle()
            if handle is None:
                return
            hwnd = handle.getIntHandle()
            if not hwnd:
                return
            import ctypes
            # ImmAssociateContext(hwnd, NULL) 断开该窗口与输入法的关联
            ctypes.windll.imm32.ImmAssociateContext(hwnd, 0)
        except Exception as e:
            print("disable IME failed (non-fatal):", e)

    def _capture_mouse(self):
        """进入视角控制模式：隐藏光标并锁定在窗口内。"""
        if hasattr(self.win, "requestProperties"):
            props = WindowProperties()
            props.setCursorHidden(True)
            props.setMouseMode(WindowProperties.M_confined)
            self.win.requestProperties(props)
        self.mouse_captured = True
        self._center_mouse()
        self._refresh_hud()

    def _release_mouse(self):
        """释放鼠标：显示光标，可自由点击/移出窗口。"""
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
            self.win.movePointer(0,
                                 int(self.win.getXSize() / 2),
                                 int(self.win.getYSize() / 2))

    def _setup_input(self):
        # 移动键改为每帧轮询硬件状态，绕开输入法(IME)对字母键的文本拦截。
        self.btn_w = KeyboardButton.ascii_key("w")
        self.btn_a = KeyboardButton.ascii_key("a")
        self.btn_s = KeyboardButton.ascii_key("s")
        self.btn_d = KeyboardButton.ascii_key("d")
        self.btn_shift = KeyboardButton.shift()
        # 上下方向键作为 WASD 的备选，进一步规避输入法影响
        self.btn_up = KeyboardButton.up()
        self.btn_down = KeyboardButton.down()
        self.btn_left = KeyboardButton.left()
        self.btn_right = KeyboardButton.right()
        # 这些只做单次动作，仍用事件
        self.accept("escape", self._on_escape)
        self.accept("mouse1", self._capture_mouse)  # 左键点击窗口进入视角控制
        self.accept("f", self._toggle_flashlight)

    def _on_escape(self):
        """Esc：若已捕获鼠标则先释放，否则退出。"""
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
        self._refresh_hud()

    def _load_cn_font(self):
        """加载系统中文字体，失败则回退默认字体。"""
        import os
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
        kwargs = dict(
            text="",
            pos=(-1.28, 0.90),
            scale=0.05,
            fg=(0.8, 0.85, 0.9, 1),
            align=TextNode.ALeft,
            mayChange=True,
        )
        if self.cn_font is not None:
            kwargs["font"] = self.cn_font
        self.hud = OnscreenText(**kwargs)
        self._refresh_hud()

    def _refresh_hud(self):
        if not hasattr(self, "hud"):
            return
        fl = "ON" if self.flashlight_on else "OFF"
        if not getattr(self, "mouse_captured", False):
            self.hud.setText(
                "Echo Ward - Tech Exp 01\n"
                "【鼠标左键点击窗口开始】\n"
                "点击后：WASD 移动 | Shift 奔跑 | F 手电筒 | Esc 释放鼠标\n"
                f"Flashlight: {fl}"
            )
        else:
            self.hud.setText(
                "Echo Ward - Tech Exp 01\n"
                "WASD 移动 | Shift 奔跑 | F 手电筒\n"
                "Esc 释放鼠标（再按一次退出）\n"
                f"Flashlight: {fl}"
            )

    def _update(self, task):
        dt = globalClock.getDt()

        # 鼠标视角：仅在捕获模式下生效（离屏模式下 mouseWatcherNode 可能为 None）
        if (self.mouse_captured
                and self.mouseWatcherNode is not None
                and hasattr(self.win, "getPointer")
                and self.mouseWatcherNode.hasMouse()):
            md = self.win.getPointer(0)
            cx = self.win.getXSize() / 2
            cy = self.win.getYSize() / 2
            dx = md.getX() - cx
            dy = md.getY() - cy
            self.heading -= dx * self.mouse_sensitivity
            self.pitch -= dy * self.mouse_sensitivity
            self.pitch = max(-89, min(89, self.pitch))
            self.player.setH(self.heading)
            self.camera.setP(self.pitch)
            self._center_mouse()

        # 移动：仅在捕获模式下响应，每帧轮询硬件按键状态
        move = Vec3(0, 0, 0)
        if self.mouse_captured:
            fwd = self._is_down(self.btn_w) or self._is_down(self.btn_up)
            back = self._is_down(self.btn_s) or self._is_down(self.btn_down)
            left = self._is_down(self.btn_a) or self._is_down(self.btn_left)
            right = self._is_down(self.btn_d) or self._is_down(self.btn_right)
            running = self._is_down(self.btn_shift)
            speed = self.run_speed if running else self.walk_speed
            if fwd:
                move.y += 1
            if back:
                move.y -= 1
            if left:
                move.x -= 1
            if right:
                move.x += 1
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


if __name__ == "__main__":
    app = Experiment01()
    app.run()
