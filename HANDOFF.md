# 交接文档 / HANDOFF —— 新窗口从这里接着做

> 用途：换新对话窗口后，让助手先读本文件即可恢复全部上下文。
> 最近更新：见文件末尾"进度时间线"。

## 一句话现状
恐怖游戏《回声病房》正在开发中。核心可玩原型已存在于 `echo_ward_game.py`，
当前正在执行"全修三件事"：A 音乐、C 建模、B 手电筒。

## 环境与路径（重要，勿改）
- 项目本地路径：`C:\Users\21036\game`
- 游戏运行解释器：`D:\Users\21036\PycharmProjects\PythonProject\game_env\Scripts\python.exe`
  （Python 3.11 + Panda3D 1.10.16 + panda3d-gltf；能读 glb）
- Blender：`D:\Program Files\Blender Foundation\Blender 5.0\blender.exe`（--background 无界面可用，能导出 GLB）
- GitHub 仓库：`https://github.com/gaoang210365/game`
- GitHub token：在 `C:\Users\21036\.mcp.json` 的 mcpServers.github.env.GITHUB_PERSONAL_ACCESS_TOKEN
  推送方式（token 不留在 remote）：
  `git push "https://<token>@github.com/gaoang210365/game.git" main`
- 图像生成（如需概念图）：EasyTokens gpt-image-2，端点 https://image.easytokens.org/v1，
  key 在 .mcp.json mcpServers.'gpt-image-2'.env.OPENAI_API_KEY

## 项目结构
- `echo_ward_game.py` —— 主游戏（约 42KB，可运行）。含第一人称、手电筒(F)、
  3D 护士音源、环境底噪、追逐音乐、存档(F5)/读档(F9)、护士 AI、程序化灰盒场景。
- `main.py` —— 启动器
- `docs/` —— 11 份设计文档（愿景/剧情/玩法/关卡/恐怖事件/怪物AI/美术/音频/技术/制作计划/决策）
- `tech_experiments/` —— exp01 第一人称+手电筒 / exp02 3D音频 / exp03 存档（均已通过离屏自测）
- `assets/` —— sounds/ music/ textures/ models/（含 nurse.glb）
- `assets_gen/` —— make_audio.py / make_textures.py / make_models_blender.py（历史素材生成脚本）
- `tools/` —— gen_hospital_room.py / gen_nurse.py（新的 Blender 模型生成脚本）

## 运行方式
- 玩游戏：`<game_env python> echo_ward_game.py`
- 离屏冒烟测试（不开窗口，验证不报错）：
  用 window-type offscreen 加载模块并 taskMgr.step() 若干帧。
- 生成医院房间模型：
  `"<blender>" --background --python tools\gen_hospital_room.py` -> assets/models/hospital_room.glb
- 生成护士模型：
  `"<blender>" --background --python tools\gen_nurse.py` -> assets/models/nurse.glb

## "全修"任务进度
- A. 音乐丢失：已修。原因是平时只有环境底噪、追逐音乐默认静音、menu_theme.wav 从未被加载。
  已在 echo_ward_game.py 的 _setup_audio 里加入 self.music_explore（menu_theme.wav 低音量 0.30 循环常驻）。
  状态：已改代码并编译通过；已提交。
- C. 建模太丑：已修完。重写 tools/gen_hospital_room.py，让 GLB 几何严格按【游戏世界
  坐标系】生成（地 x∈[-6,6]/y∈[-2,46]，顶 z=3，墙对齐 echo_ward_game.py 的 walls 规格，
  含踢脚线/病床/输液架）。修正了 add_box 缩放 bug（原来乘 size/2 导致尺寸减半、墙盖不住走廊）。
  游戏 _build_scene 改为 loadModel 加载 hospital_room.glb 挂到 render 原点（与碰撞盒重合，
  无需缩放旋转）；灰盒逻辑保留为 _build_graybox_fallback 兜底。离屏测：边界 X[-6,6] Y[-2,46]
  Z[-0.2,3.2] 完全对齐，加载/60帧无异常。灯管与出口门仍由代码控制（闪烁/开关状态）。
- B. 手电筒"丢失"：代码里 F 键切换正常、默认开启、聚光灯已设置。离屏测不出画面问题。
  待用户反馈：按 F 是"完全没反应"还是"有反应但看不到光"。
  可能方向：环境光(0.28)偏亮盖过手电、或聚光灯衰减/朝向、或按键焦点。

## 已知易错点（避免重复踩坑）
1. 音频路径必须用 `Filename.fromOsSpecific(os_path).getFullpath()` 转 Unix 风格，否则 Panda3D 打不开。
2. 中文 HUD 需显式加载系统字体（C:\Windows\Fonts\msyh.ttc 或 simhei.ttf），否则中文不显示。
3. 输入法(IME)会拦截 WASD：已用"每帧轮询硬件按键 + ImmAssociateContext 分离窗口IME + 方向键备选"解决。
4. 鼠标捕获用 recenter 方案（隐藏光标 + 每帧读指针算相对位移再拉回中心）。
5. Blender 材质取 Principled BSDF 要按节点 type=="BSDF_PRINCIPLED" 查找，别按名字。
6. git push 到 stderr 属正常，PowerShell 会显示成红色"错误"，需用 ls-remote 核对 local==remote 才算成功。
7. 重要：动手前先用 git status / 读真实文件核对磁盘状态，不要凭记忆或把工具回显当已完成。

## 下一步建议顺序
1. （已完成）接入 hospital_room.glb 替换灰盒场景（任务 C）。
2. 等用户反馈按 F 现象后修手电筒（任务 B）。
3. 之后回到阶段1 剩余：exp04 AI/整合、exp05 Windows 打包。
4. 可选打磨：给 GLB 加贴图 UV/更多病房细节；证据点与躲藏点也可换成模型。

## 进度时间线
- 设计文档 01~11 完成并入库。
- tech_experiments exp01/exp02/exp03 完成，离屏自测通过。
- 主游戏 echo_ward_game.py + main.py 已存在可运行。
- 音乐(A)已修并提交；hospital_room.glb 与 tools/ 已入库。
- 建模(C)已修完：GLB 按游戏坐标系重生成并接入场景，碰撞对齐，离屏测通过。
- 待办：B 手电筒（等用户反馈按 F 现象）。
