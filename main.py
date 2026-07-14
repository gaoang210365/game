"""
回声病房 / Echo Ward - 统一启动入口

这是项目的总入口。当前处于阶段1（技术验证），此菜单列出所有已完成、
可直接体验的技术验证 demo。随着开发推进（灰盒关卡、核心系统……），
新条目会持续加入这里，你运行本文件即可实时体验最新进度。

运行（务必用游戏专用虚拟环境）：
    D:\\Users\\21036\\PycharmProjects\\PythonProject\\game_env\\Scripts\\python.exe main.py

也可用 --list 只列出条目，或 --run <编号> 直接运行某个 demo：
    python main.py --list
    python main.py --run exp01
"""

import os
import sys
import subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
EXPERIMENTS_DIR = os.path.join(ROOT, "tech_experiments")

# 菜单条目：(编号, 标题, 相对脚本路径, 状态说明)
# 新的可体验内容在这里登记即可出现在入口菜单中。
ENTRIES = [
    ("game", "▶ 开始游戏：回声病房（可玩原型 · 灰盒 + 护士 AI + 音频）",
     "echo_ward_game.py", "可体验（建议戴耳机）"),
    ("exp01", "第一人称控制 + 手电筒 + 碰撞",
     "tech_experiments/exp01_fps_flashlight.py", "技术验证"),
    ("exp02", "3D 定位音频（声音先于视觉）",
     "tech_experiments/exp02_audio_3d.py", "技术验证（建议戴耳机）"),
    ("exp03", "存档 / 读档原型",
     "tech_experiments/exp03_save_load.py", "技术验证"),
    ("audio", "重新生成全部音频资源（音乐/环境/音效）",
     "assets_gen/make_audio.py", "工具"),
    ("textures", "重新生成全部贴图资源（地砖/墙面/门/金属）",
     "assets_gen/make_textures.py", "工具"),
]

# Blender 模型生成需在 Blender 内运行，不走本菜单：
#   blender.exe --background --python assets_gen/make_models_blender.py


def _print_header():
    print("=" * 56)
    print("  回声病房 / Echo Ward  —  统一启动入口")
    print("  阶段1：技术验证  (Phase 1: Tech Experiments)")
    print("=" * 56)


def list_entries():
    _print_header()
    print(" 可运行的技术验证：\n")
    for i, (eid, title, _path, status) in enumerate(ENTRIES, 1):
        print(f"  [{i}] {eid}  {title}")
        print(f"      状态：{status}")
    print("\n  [q] 退出")
    print("-" * 56)


def _find_entry(token):
    """按序号(1..N)或编号(exp01)查找条目。"""
    token = token.strip().lower()
    for idx, entry in enumerate(ENTRIES, 1):
        if token == str(idx) or token == entry[0].lower():
            return entry
    return None


def run_entry(entry):
    eid, title, rel_path, _status = entry
    script = os.path.join(ROOT, rel_path.replace("/", os.sep))
    if not os.path.exists(script):
        print(f"[错误] 找不到脚本：{script}")
        return 1
    print(f"\n>> 启动 {eid}：{title}")
    print(f">> {script}")
    print(">> 关闭该 demo 窗口后会回到本菜单。\n")
    # 用当前解释器（应为 game_env）以子进程方式运行，
    # 避免多个 Panda3D ShowBase 实例在同一进程内冲突。
    result = subprocess.run([sys.executable, script], cwd=ROOT)
    return result.returncode


def interactive_menu():
    while True:
        list_entries()
        choice = input(" 请选择要体验的编号（或 q 退出）：").strip()
        if choice.lower() in ("q", "quit", "exit"):
            print("再见。")
            return 0
        entry = _find_entry(choice)
        if entry is None:
            print(f"\n[提示] 无效选择：{choice!r}\n")
            continue
        run_entry(entry)
        print()


def main(argv):
    if "--list" in argv:
        list_entries()
        return 0
    if "--run" in argv:
        i = argv.index("--run")
        if i + 1 >= len(argv):
            print("用法：main.py --run <编号，如 exp01 或 1>")
            return 2
        entry = _find_entry(argv[i + 1])
        if entry is None:
            print(f"[错误] 未知条目：{argv[i + 1]}")
            return 2
        return run_entry(entry)
    return interactive_menu()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
