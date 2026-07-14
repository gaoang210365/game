"""
用 Blender 无界面模式生成"值夜护士"低模人形，导出 GLB。
低多边形 + 略微不自然比例（符合美术设定：四肢比例轻微错误、面部遮挡）。

运行：
    "D:\Program Files\Blender Foundation\Blender 5.0\blender.exe" ^
        --background --python tools\gen_nurse.py

输出：assets/models/nurse.glb
"""

import bpy
import os
import math


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.materials):
        for item in list(block):
            block.remove(item)


def mat(name, color, rough=0.8, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = None
    for node in m.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            bsdf = node
            break
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = rough
        bsdf.inputs["Metallic"].default_value = metal
    return m


def box(name, size, loc, material):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.active_object
    o.name = name
    o.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    bpy.ops.object.transform_apply(scale=True)
    o.data.materials.append(material)
    return o


def build():
    clear_scene()
    uniform = mat("nurse_uniform", (0.82, 0.83, 0.85), rough=0.75)
    skin = mat("nurse_skin", (0.70, 0.66, 0.63), rough=0.8)
    dark = mat("nurse_dark", (0.10, 0.10, 0.12), rough=0.9)

    # 躯干（略窄）
    box("Torso", (0.42, 0.24, 0.75), (0, 0, 1.15), uniform)
    # 头（面部用深色遮挡感）
    box("Head", (0.24, 0.24, 0.28), (0, 0, 1.72), skin)
    box("FaceShadow", (0.20, 0.05, 0.20), (0, 0.12, 1.72), dark)
    # 手臂（偏长 -> 不自然）
    box("ArmL", (0.10, 0.10, 0.85), (-0.30, 0, 1.05), uniform)
    box("ArmR", (0.10, 0.10, 0.85), (0.30, 0, 1.05), uniform)
    # 腿
    box("LegL", (0.13, 0.13, 0.85), (-0.11, 0, 0.42), dark)
    box("LegR", (0.13, 0.13, 0.85), (0.11, 0, 0.42), dark)

    out_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "assets", "models",
    )
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "nurse.glb")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(filepath=out_path, export_format="GLB",
                              use_selection=True, export_apply=True)
    print("EXPORTED", out_path, os.path.getsize(out_path), "bytes")


if __name__ == "__main__":
    build()
