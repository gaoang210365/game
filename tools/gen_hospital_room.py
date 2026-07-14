"""
用 Blender 无界面模式程序化生成一个医院房间/走廊场景，导出 GLB。
替换技术验证里难看的方块占位模型。

运行：
    "D:\Program Files\Blender Foundation\Blender 5.0\blender.exe" ^
        --background --python tools\gen_hospital_room.py

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
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    bpy.ops.object.transform_apply(scale=True)
    obj.data.materials.append(material)
    return obj


def build():
    clear_scene()

    # 材质
    mat_floor = make_material("floor", (0.20, 0.21, 0.20), rough=0.9)
    mat_wall = make_material("wall", (0.32, 0.34, 0.33), rough=0.95)
    mat_ceil = make_material("ceil", (0.14, 0.15, 0.17), rough=0.95)
    mat_metal = make_material("metal", (0.55, 0.57, 0.60), rough=0.35, metal=0.9)
    mat_bed = make_material("bed", (0.75, 0.78, 0.80), rough=0.7)
    mat_door = make_material("door", (0.28, 0.22, 0.18), rough=0.8)
    mat_lamp = make_material("lamp", (0.9, 0.95, 1.0), emit=(0.9, 0.95, 1.0))

    # 房间尺寸：24 x 10 x 3.2（走廊式）
    W, L, H = 24.0, 10.0, 3.2
    t = 0.2  # 墙厚

    add_box("Floor", (W, L, t), (0, 0, -t / 2), mat_floor)
    add_box("Ceiling", (W, L, t), (0, 0, H + t / 2), mat_ceil)
    # 四面墙
    add_box("Wall_N", (W, t, H), (0, L / 2, H / 2), mat_wall)
    add_box("Wall_S", (W, t, H), (0, -L / 2, H / 2), mat_wall)
    add_box("Wall_E", (t, L, H), (W / 2, 0, H / 2), mat_wall)
    add_box("Wall_W", (t, L, H), (-W / 2, 0, H / 2), mat_wall)

    # 天花板灯管（自发光）
    for x in (-7, 0, 7):
        add_box("Lamp_%d" % x, (1.6, 0.25, 0.08), (x, 0, H - 0.1), mat_lamp)

    # 病床（床架 + 床垫 + 四条腿）
    def make_bed(bx, by, rot=0.0):
        frame = add_box("BedFrame", (2.0, 0.9, 0.12), (bx, by, 0.55), mat_metal)
        mattress = add_box("Mattress", (1.9, 0.8, 0.15), (bx, by, 0.66), mat_bed)
        for dx in (-0.9, 0.9):
            for dy in (-0.4, 0.4):
                add_box("Leg", (0.08, 0.08, 0.5), (bx + dx, by + dy, 0.25), mat_metal)
        for obj in (frame, mattress):
            obj.rotation_euler = (0, 0, math.radians(rot))

    make_bed(-7, -3)
    make_bed(-2, -3)
    make_bed(3, -3)

    # 输液架（细杆 + 横臂 + 底座）
    def make_iv(px, py):
        add_box("IVPole", (0.06, 0.06, 1.8), (px, py, 0.9), mat_metal)
        add_box("IVArm", (0.5, 0.06, 0.06), (px + 0.2, py, 1.75), mat_metal)
        add_box("IVBase", (0.5, 0.5, 0.06), (px, py, 0.05), mat_metal)

    make_iv(-6, -1.5)
    make_iv(2, -1.5)

    # 门（东墙开口处的门板）
    add_box("Door", (0.15, 1.4, 2.4), (W / 2 - 0.1, 3, 1.2), mat_door)

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
