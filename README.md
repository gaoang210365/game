# 回声病房 / Echo Ward

第一人称 3D 心理恐怖游戏（探索解谜 · 环境叙事）。

> 玩家在一所废弃医院中醒来。每次穿过住院部走廊尽头的防火门，时间都会向事故之前倒退一天，而黑暗中的"值夜护士"正在逐渐记住玩家的行为。

## 项目状态

当前处于 **阶段0（设计文档）→ 阶段1（技术实验）** 过渡阶段。

- 设计文档见 `docs/`
- 技术验证代码见 `tech_experiments/`

## 技术栈

- Python 3.11
- Panda3D 1.10.16（主引擎）
- 目标平台：Windows PC 单机

## 目录结构

```text
game/
├── main.py              # 统一启动入口（菜单，选择并运行 demo）
├── docs/                # 设计文档（01～11）
├── tech_experiments/    # 阶段1 技术验证 demo
├── assets/              # 资源（模型/贴图/音频）
└── README.md
```

## 快速开始（统一入口）

用游戏专用虚拟环境运行 `main.py`，会弹出菜单，选择编号即可体验对应 demo。
随着开发推进，新内容会持续加入这个菜单，运行它即可实时体验最新进度。

```powershell
D:\Users\21036\PycharmProjects\PythonProject\game_env\Scripts\python.exe main.py
```

也可直接运行指定 demo，或只列出条目：

```powershell
# 直接运行 exp01
D:\Users\21036\PycharmProjects\PythonProject\game_env\Scripts\python.exe main.py --run exp01
# 只列出可体验条目
D:\Users\21036\PycharmProjects\PythonProject\game_env\Scripts\python.exe main.py --list
```

## 单独运行某个技术验证

也可以绕过入口，直接运行单个实验脚本：

```powershell
D:\Users\21036\PycharmProjects\PythonProject\game_env\Scripts\python.exe tech_experiments\exp01_fps_flashlight.py
```

## 设计文档索引

| 文档 | 内容 |
|---|---|
| 01 | 游戏愿景 |
| 02 | 剧情大纲 |
| 03 | 玩法系统 |
| 04 | 关卡与地图 |
| 05 | 恐怖事件清单 |
| 06 | 怪物与 AI |
| 07 | 美术指导 |
| 08 | 音频设计 |
| 09 | 技术设计 |
| 10 | 制作计划 |
| 11 | 设计决策确认 |

## 说明

本仓库不包含任何 API 密钥、访问令牌或个人凭据。
