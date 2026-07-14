"""
用 Blender 无界面模式程序化生成《回声病房》住院部走廊场景，导出 GLB。
替换技术验证里难看的方块占位模型。

关键：几何严格按【游戏世界坐标系】生成（与 echo_ward_game.py 的 walls 规格一致），
这样 Panda3D 里直接 loadModel 挂到 render 原点即可，无需缩放/旋转，
且可见墙体与代码里的碰撞盒完全重合。

坐标约定（与游戏一致，均为 Z-up、单位米）：
  - 走廊地面：x∈[-6,6]，y∈[-2,46]，地面顶面在 z=0
  - 天花板底面在 z=3.0
  - 长墙在 x=±5，后墙在 y=-2，中间交错病房隔断
  - 灯管与出口门不在此生成（游戏内代码控制闪烁/开关状态）

运行：
    "D:\\Program Files\\Blender Foundation\\Blender 5.0\\blender.exe" ^
        --background --python tools\\gen_hospital_room.py

输出：assets/models/hospital_room.glb
"""

import bpy
import os
import math


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.images):
        for item in list(block):
            block.remove(item)


def make_material(name, color, rough=0.85, metal=0.0, emit=None):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    # 按节点类型查找 Principled BSDF（避免因名称/本地化取不到）
    bsdf = None
    for node in mat.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            bsdf = node
            break
    if bsdf is None:
        bsdf = mat.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
        out = None
        for node in mat.node_tree.nodes:
            if node.type == "OUTPUT_MATERIAL":
                out = node
                break
        if out is None:
            out = mat.node_tree.nodes.new("ShaderNodeOutputMaterial")
        mat.node_tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if emit is not None:
        # 自发光（灯管等）
        if "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = (*emit, 1.0)
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = 2.0
    return mat


def add_box(name, size, location, material):
    # primitive_cube_add(size=1) 生成边长 1 的立方体（-0.5~0.5）。
    # 要让最终每轴全长 = size[i]，缩放系数应为 size[i]（不是 size[i]/2）。
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (size[0], size[1], size[2])
    bpy.ops.object.transform_apply(scale=True)
    obj.data.materials.append(material)
    return obj


# ---- 与 echo_ward_game.py 完全一致的墙体规格（务必同步）----
# 每项 = (中心x, 中心y, 长度x, 长度y)；墙高统一 WALL_H，底在 z=0。
WALL_H = 3.0
WALL_SPECS = [
    (-5, 22, 1, 48),   # 左长墙
    (5, 22, 1, 48),    # 右长墙
    (0, -2, 12, 1),    # 起点后墙
    (-3, 6, 4, 1),     # 病房隔断（左右交错）
    (3, 12, 4, 1),
    (-3, 18, 4, 1),
    (3, 24, 4, 1),
    (-3, 30, 4, 1),
    (3, 36, 4, 1),
]

# 走廊地面/天花板包围盒（顶面 z=0 / 底面 z=WALL_H）
FLOOR_X0, FLOOR_X1 = -6.0, 6.0
FLOOR_Y0, FLOOR_Y1 = -2.0, 46.0


def build():
    clear_scene()

    # 材质
    mat_floor = make_material("floor", (0.20, 0.21, 0.20), rough=0.9)
    mat_wall = make_material("wall", (0.32, 0.34, 0.33), rough=0.95)
    mat_ceil = make_material("ceil", (0.14, 0.15, 0.17), rough=0.95)
    mat_metal = make_material("metal", (0.55, 0.57, 0.60), rough=0.35, metal=0.9)
    mat_bed = make_material("bed", (0.75, 0.78, 0.80), rough=0.7)
    mat_trim = make_material("trim", (0.42, 0.30, 0.24), rough=0.8)

    t = 0.2  # 板厚
    fw = FLOOR_X1 - FLOOR_X0    # 走廊宽 12
    fl = FLOOR_Y1 - FLOOR_Y0    # 走廊长 48
    cx = (FLOOR_X0 + FLOOR_X1) / 2   # 0
    cy = (FLOOR_Y0 + FLOOR_Y1) / 2   # 22

    # 地面（顶面在 z=0）与天花板（底面在 z=WALL_H）
    add_box("Floor", (fw, fl, t), (cx, cy, -t / 2), mat_floor)
    add_box("Ceiling", (fw, fl, t), (cx, cy, WALL_H + t / 2), mat_ceil)

    # 墙体：严格对齐游戏碰撞规格（中心 z = WALL_H/2）
    for i, (mx, my, lx, ly) in enumerate(WALL_SPECS):
        add_box("Wall_%d" % i, (lx, ly, WALL_H), (mx, my, WALL_H / 2), mat_wall)
        # 踢脚线：沿墙脚一圈深色收边，增强"真实房间"感
        add_box("Base_%d" % i, (lx + 0.02, ly + 0.02, 0.12),
                (mx, my, 0.06), mat_trim)

    # 病床：贴长墙摆放（长轴沿 Y，避免挡住中央通路）
    def make_bed(bx, by):
        frame = add_box("BedFrame", (0.9, 2.0, 0.12), (bx, by, 0.55), mat_metal)
        mattress = add_box("Mattress", (0.8, 1.9, 0.15), (bx, by, 0.66), mat_bed)
        # 枕头
        add_box("Pillow", (0.7, 0.4, 0.12), (bx, by + 0.7, 0.75), mat_bed)
        for dx in (-0.4, 0.4):
            for dy in (-0.9, 0.9):
                add_box("Leg", (0.08, 0.08, 0.5), (bx + dx, by + dy, 0.25), mat_metal)
        return frame, mattress

    # 左墙侧（x≈-4.5，长墙内表面在 x=-4.5）
    for by in (9, 21, 33):
        make_bed(-4.4, by)
    # 右墙侧
    for by in (15, 27):
        make_bed(4.4, by)

    # 输液架（细杆 + 横臂 + 底座）——摆在部分病床旁
    def make_iv(px, py):
        add_box("IVPole", (0.06, 0.06, 1.8), (px, py, 0.9), mat_metal)
        add_box("IVArm", (0.5, 0.06, 0.06), (px + 0.2, py, 1.75), mat_metal)
        add_box("IVBase", (0.4, 0.4, 0.06), (px, py, 0.05), mat_metal)

    make_iv(-3.8, 10.5)
    make_iv(3.8, 16.5)
    make_iv(-3.8, 34.5)

    # 导出 GLB
    out_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "assets", "models",
    )
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "hospital_room.glb")

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(
        filepath=out_path,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
    )
    print("EXPORTED", out_path, os.path.getsize(out_path), "bytes")


if __name__ == "__main__":
    build()
