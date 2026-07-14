"""
回声病房 / Echo Ward - Blender 建模脚本（在 Blender 内运行）

用 Blender 的 bpy 程序化生成低多边形模型并导出 glTF 到 assets/models/：
  nurse.glb   —— 值夜护士（拉长比例、低头、苍白，恐怖轮廓）

用法（由 run_blender.py 或命令行调用，无需手动开 Blender）：
    blender.exe --background --python assets_gen/make_models_blender.py

只用标准 bpy，不依赖第三方插件。
"""

import bpy
import os
import math

# 输出目录：脚本位于 <repo>/assets_gen/，模型放 <repo>/assets/models/
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(SCRIPT_DIR)
OUT_DIR = os.path.join(REPO, "assets", "models")


def _clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.materials):
        for b in list(block):
            if b.users == 0:
                block.remove(b)


def _mat(name, color, rough=0.7, emit=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = rough
        # 自发光（不同 Blender 版本输入名不同，做兼容）
        for key in ("Emission Color", "Emission"):
            if key in bsdf.inputs:
                bsdf.inputs[key].default_value = (*[c * emit for c in color], 1.0)
                break
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emit
    return m


def _add_box(name, size, loc, mat):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    o = bpy.context.active_object
    o.name = name
    o.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    o.data.materials.append(mat)
    return o


def _add_cyl(name, radius, depth, loc, mat, verts=12):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth,
                                         location=loc, vertices=verts)
    o = bpy.context.active_object
    o.name = name
    o.data.materials.append(mat)
    return o


def _add_sphere(name, radius, loc, mat):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=loc, segments=16, ring_count=8)
    o = bpy.context.active_object
    o.name = name
    o.data.materials.append(mat)
    return o


def build_nurse():
    """低多边形值夜护士：拉长躯干、垂落长发遮面、细长四肢，站立中心在原点，
    脚在 z≈0，总高约 1.9m，朝 -Y。"""
    skin = _mat("nurse_skin", (0.86, 0.83, 0.80), rough=0.6)
    gown = _mat("nurse_gown", (0.80, 0.82, 0.85), rough=0.8)
    hair = _mat("nurse_hair", (0.06, 0.06, 0.07), rough=0.9)
    dark = _mat("nurse_dark", (0.10, 0.10, 0.12), rough=0.9)

    parts = []
    # 长袍躯干（上窄下宽，锥形感用两段盒近似）
    parts.append(_add_box("torso", (0.42, 0.28, 0.95), (0, 0, 1.15), gown))
    parts.append(_add_box("skirt", (0.52, 0.34, 0.7), (0, 0, 0.5), gown))
    # 脖子 + 头（略前倾）
    parts.append(_add_cyl("neck", 0.07, 0.18, (0, 0, 1.68), skin))
    head = _add_sphere("head", 0.14, (0, 0.03, 1.82), skin)
    head.scale = (1.0, 1.1, 1.25)  # 拉长脸
    parts.append(head)
    # 垂落长发（遮住面部，恐怖轮廓）
    hairmass = _add_box("hair", (0.30, 0.26, 0.5), (0, 0.02, 1.72), hair)
    parts.append(hairmass)
    # 手臂（细长、自然下垂略前伸）
    for side in (-1, 1):
        parts.append(_add_box(f"arm_{side}", (0.09, 0.09, 0.85),
                              (side * 0.28, 0.04, 1.05), skin))
        parts.append(_add_sphere(f"hand_{side}", 0.07,
                                 (side * 0.28, 0.06, 0.6), skin))
    # 腿（长袍下隐约，暗色）
    for side in (-1, 1):
        parts.append(_add_box(f"leg_{side}", (0.12, 0.12, 0.6),
                              (side * 0.13, 0, 0.15), dark))

    # 合并为单个网格
    bpy.ops.object.select_all(action="DESELECT")
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    nurse = bpy.context.active_object
    nurse.name = "nurse"
    # 平滑着色 + 轻微三角化，保持低多边形
    bpy.ops.object.shade_flat()
    return nurse


def export_glb(name):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, name)
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB",
                              use_selection=False)
    print("EXPORTED", path)


def main():
    _clear_scene()
    build_nurse()
    export_glb("nurse.glb")
    print("BLENDER_MODELS_DONE")


if __name__ == "__main__":
    main()
