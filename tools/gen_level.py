"""
用 Blender 无界面模式生成《回声病房》整层住院部场景，导出 GLB。

几何严格读 level_data.py（游戏与建模共用的单一数据源），保证可见墙体与游戏
碰撞盒完全对齐。含：地/顶/墙 + 病床/推床/办公桌/椅/货架/储物柜/水槽/配电箱等道具。

运行：
    "D:\\Program Files\\Blender Foundation\\Blender 5.0\\blender.exe" ^
        --background --python tools\\gen_level.py

输出：assets/models/level.glb
"""

import bpy
import os
import sys
import math

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import level_data as L


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.images):
        for item in list(block):
            block.remove(item)


def make_material(name, color, rough=0.85, metal=0.0, emit=None, emit_str=2.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = None
    for node in mat.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            bsdf = node
            break
    if bsdf is None:
        bsdf = mat.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if emit is not None:
        if "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = (*emit, 1.0)
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emit_str
    return mat


def add_box(name, size, location, material):
    """size = 每轴全长；primitive_cube_add(size=1) 边长 1，故缩放系数=size。"""
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (size[0], size[1], size[2])
    bpy.ops.object.transform_apply(scale=True)
    obj.data.materials.append(material)
    return obj


# ---------- 道具建模 ----------

def _rot(obj, deg):
    obj.rotation_euler = (0, 0, math.radians(deg))


def prop_bed(px, py, rot, M):
    parts = []
    parts.append(add_box("bed_frame", (0.95, 2.0, 0.12), (px, py, 0.55), M["metal"]))
    parts.append(add_box("bed_mat", (0.85, 1.9, 0.16), (px, py, 0.66), M["bed"]))
    parts.append(add_box("bed_pillow", (0.7, 0.42, 0.13), (px, py + 0.7, 0.76), M["bed"]))
    for dx in (-0.42, 0.42):
        for dy in (-0.9, 0.9):
            parts.append(add_box("bed_leg", (0.08, 0.08, 0.5), (px + dx, py + dy, 0.25), M["metal"]))
    return parts


def prop_gurney(px, py, rot, M):
    parts = []
    parts.append(add_box("gur_top", (0.75, 1.9, 0.1), (px, py, 0.85), M["metal"]))
    parts.append(add_box("gur_pad", (0.68, 1.8, 0.12), (px, py, 0.95), M["bed"]))
    for dx in (-0.32, 0.32):
        for dy in (-0.85, 0.85):
            parts.append(add_box("gur_leg", (0.05, 0.05, 0.8), (px + dx, py + dy, 0.42), M["metal"]))
    return parts


def prop_desk(px, py, rot, M):
    parts = []
    parts.append(add_box("desk_top", (1.6, 0.8, 0.08), (px, py, 0.74), M["wood"]))
    for dx in (-0.72, 0.72):
        for dy in (-0.34, 0.34):
            parts.append(add_box("desk_leg", (0.08, 0.08, 0.72), (px + dx, py + dy, 0.36), M["wood"]))
    parts.append(add_box("desk_draw", (0.7, 0.72, 0.5), (px + 0.4, py, 0.42), M["wood"]))
    return parts


def prop_chair(px, py, rot, M):
    parts = []
    parts.append(add_box("ch_seat", (0.45, 0.45, 0.06), (px, py, 0.46), M["wood"]))
    parts.append(add_box("ch_back", (0.45, 0.06, 0.5), (px, py - 0.2, 0.72), M["wood"]))
    for dx in (-0.18, 0.18):
        for dy in (-0.18, 0.18):
            parts.append(add_box("ch_leg", (0.05, 0.05, 0.46), (px + dx, py + dy, 0.23), M["metal"]))
    return parts


def prop_shelf(px, py, rot, M):
    parts = []
    parts.append(add_box("sh_body", (0.5, 1.4, 2.0), (px, py, 1.0), M["metal"]))
    for z in (0.4, 0.9, 1.4, 1.9):
        parts.append(add_box("sh_plate", (0.5, 1.4, 0.04), (px, py, z), M["metal_l"]))
    grp = _join(parts, "shelf")
    _rot(grp, rot)
    return [grp]


def prop_locker(px, py, rot, M):
    parts = []
    parts.append(add_box("lk_body", (0.9, 0.6, 1.9), (px, py, 0.95), M["locker"]))
    parts.append(add_box("lk_door", (0.02, 0.55, 1.8), (px + 0.46, py, 0.95), M["locker_d"]))
    parts.append(add_box("lk_handle", (0.06, 0.06, 0.2), (px + 0.5, py + 0.18, 1.0), M["metal_l"]))
    grp = _join(parts, "locker")
    _rot(grp, rot)
    return [grp]


def prop_sink(px, py, rot, M):
    parts = []
    parts.append(add_box("sk_basin", (0.6, 0.5, 0.25), (px, py, 0.85), M["porc"]))
    parts.append(add_box("sk_pillar", (0.2, 0.2, 0.85), (px, py, 0.42), M["porc"]))
    parts.append(add_box("sk_tap", (0.05, 0.2, 0.05), (px, py - 0.15, 1.02), M["metal_l"]))
    grp = _join(parts, "sink")
    _rot(grp, rot)
    return [grp]


def prop_fusebox_panel(px, py, rot, M):
    parts = []
    parts.append(add_box("fb_box", (0.15, 1.0, 1.2), (px, py, 1.5), M["metal_l"]))
    parts.append(add_box("fb_door", (0.05, 0.9, 1.1), (px + 0.1, py, 1.5), M["locker_d"]))
    for i in range(3):
        parts.append(add_box("fb_sw", (0.05, 0.12, 0.12), (px + 0.14, py - 0.25 + i * 0.25, 1.6), M["warn"]))
    grp = _join(parts, "fusebox")
    _rot(grp, rot)
    return [grp]


def _join(objs, name):
    if not objs:
        return None
    for o in objs:
        o.select_set(False)
    bpy.context.view_layer.objects.active = objs[0]
    for o in objs:
        o.select_set(True)
    if len(objs) > 1:
        bpy.ops.object.join()
    g = bpy.context.active_object
    g.name = name
    return g


PROP_FUNCS = {
    "bed": prop_bed, "gurney": prop_gurney, "desk": prop_desk,
    "chair": prop_chair, "shelf": prop_shelf, "locker": prop_locker,
    "sink": prop_sink, "fusebox_panel": prop_fusebox_panel,
}


def build():
    clear_scene()

    M = {
        "floor":   make_material("floor", (0.19, 0.20, 0.20), rough=0.9),
        "wall":    make_material("wall", (0.34, 0.35, 0.33), rough=0.95),
        "ceil":    make_material("ceil", (0.13, 0.14, 0.16), rough=0.95),
        "trim":    make_material("trim", (0.24, 0.20, 0.17), rough=0.8),
        "metal":   make_material("metal", (0.55, 0.57, 0.60), rough=0.35, metal=0.9),
        "metal_l": make_material("metal_l", (0.70, 0.72, 0.74), rough=0.3, metal=0.9),
        "bed":     make_material("bed", (0.72, 0.75, 0.78), rough=0.7),
        "wood":    make_material("wood", (0.35, 0.26, 0.18), rough=0.8),
        "locker":  make_material("locker", (0.30, 0.42, 0.40), rough=0.6, metal=0.5),
        "locker_d":make_material("locker_d", (0.26, 0.36, 0.35), rough=0.6, metal=0.5),
        "porc":    make_material("porc", (0.85, 0.86, 0.88), rough=0.4),
        "warn":    make_material("warn", (0.9, 0.5, 0.1), rough=0.5, emit=(0.9, 0.4, 0.05), emit_str=1.2),
    }

    t = 0.2
    fw = L.FLOOR_X1 - L.FLOOR_X0
    fl = L.FLOOR_Y1 - L.FLOOR_Y0
    cx = (L.FLOOR_X0 + L.FLOOR_X1) / 2
    cy = (L.FLOOR_Y0 + L.FLOOR_Y1) / 2

    # 地面 / 天花板
    add_box("Floor", (fw, fl, t), (cx, cy, -t / 2), M["floor"])
    add_box("Ceiling", (fw, fl, t), (cx, cy, L.WALL_H + t / 2), M["ceil"])

    # 墙体（读共享数据；含踢脚线）
    for i, (mx, my, lx, ly) in enumerate(L.WALLS):
        add_box("Wall_%d" % i, (lx, ly, L.WALL_H), (mx, my, L.WALL_H / 2), M["wall"])
        add_box("Base_%d" % i, (lx + 0.02, ly + 0.02, 0.12), (mx, my, 0.06), M["trim"])

    # 道具
    for p in L.PROPS:
        fn = PROP_FUNCS.get(p["type"])
        if fn:
            fn(p["pos"][0], p["pos"][1], p.get("rot", 0), M)

    # 导出
    out_dir = os.path.join(_ROOT, "assets", "models")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "level.glb")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(filepath=out_path, export_format="GLB",
                              use_selection=True, export_apply=True)
    print("EXPORTED", out_path, os.path.getsize(out_path), "bytes")


if __name__ == "__main__":
    build()

