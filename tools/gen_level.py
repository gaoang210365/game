"""Generate Echo Ward full-floor hospital scene via Blender headless, export GLB.
Geometry strictly reads level_data.py (single source of truth shared with the game),
so visible walls line up with the game collision boxes.
Run: blender --background --python tools/gen_level.py  -> assets/models/level.glb
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


def add_box(name, size, location, material, bevel=0.015):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (size[0], size[1], size[2])
    bpy.ops.object.transform_apply(scale=True)
    if bevel and bevel > 0:
        m = obj.modifiers.new("bev", "BEVEL")
        m.width = bevel
        m.segments = 2
        m.limit_method = "ANGLE"
        bpy.ops.object.modifier_apply(modifier=m.name)
    obj.data.materials.append(material)
    return obj


def add_cyl(name, radius, depth, location, material, axis="Z", verts=20, bevel=0.01):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth,
                                        vertices=verts, location=location)
    obj = bpy.context.active_object
    obj.name = name
    if axis == "X":
        obj.rotation_euler = (0, math.radians(90), 0)
    elif axis == "Y":
        obj.rotation_euler = (math.radians(90), 0, 0)
    bpy.ops.object.transform_apply(rotation=True)
    if bevel and bevel > 0:
        m = obj.modifiers.new("bev", "BEVEL")
        m.width = bevel
        m.segments = 1
        bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.ops.object.shade_smooth()
    obj.data.materials.append(material)
    return obj


def _rot(obj, deg):
    obj.rotation_euler = (0, 0, math.radians(deg))


def prop_bed(px, py, rot, M):
    parts = []
    parts.append(add_box("bed_frame", (0.95, 2.0, 0.1), (px, py, 0.52), M["metal"]))
    parts.append(add_box("bed_mat", (0.84, 1.15, 0.14), (px, py - 0.3, 0.63), M["bed"]))
    parts.append(add_box("bed_mat2", (0.84, 0.6, 0.16), (px, py + 0.55, 0.66), M["bed"]))
    parts.append(add_box("bed_pillow", (0.66, 0.4, 0.12), (px, py + 0.72, 0.75), M["white"]))
    parts.append(add_box("bed_sheet", (0.9, 1.2, 0.03), (px, py - 0.25, 0.71), M["white"]))
    for yy in (py - 0.98, py + 0.98):
        for dx in (-0.4, 0.4):
            parts.append(add_cyl("bed_post", 0.025, 0.5, (px + dx, yy, 0.75), M["metal_l"]))
        parts.append(add_cyl("bed_rail", 0.025, 0.8, (px, yy, 0.98), M["metal_l"], axis="X"))
    for dx in (-0.42, 0.42):
        for dy in (-0.9, 0.9):
            parts.append(add_cyl("bed_leg", 0.03, 0.42, (px + dx, py + dy, 0.24), M["metal"]))
            parts.append(add_cyl("bed_caster", 0.05, 0.06, (px + dx, py + dy, 0.05), M["rubber"], axis="X"))
    grp = _join(parts, "bed", pivot=(px, py), rot=rot)
    return [grp]


def prop_gurney(px, py, rot, M):
    parts = []
    parts.append(add_box("gur_top", (0.72, 1.9, 0.08), (px, py, 0.82), M["metal_l"]))
    parts.append(add_box("gur_pad", (0.66, 1.8, 0.1), (px, py, 0.9), M["bed"]))
    for dx in (-0.36, 0.36):
        parts.append(add_cyl("gur_rail", 0.02, 1.2, (px + dx, py, 0.98), M["metal_l"], axis="Y"))
        for dy in (-0.55, 0.55):
            parts.append(add_cyl("gur_railp", 0.018, 0.18, (px + dx, py + dy, 0.91), M["metal_l"]))
    for dx in (-0.3, 0.3):
        for dy in (-0.8, 0.8):
            parts.append(add_cyl("gur_leg", 0.025, 0.72, (px + dx, py + dy, 0.44), M["metal"]))
            parts.append(add_cyl("gur_caster", 0.055, 0.06, (px + dx, py + dy, 0.06), M["rubber"], axis="X"))
    grp = _join(parts, "gurney", pivot=(px, py), rot=rot)
    return [grp]


def prop_desk(px, py, rot, M):
    parts = []
    parts.append(add_box("desk_top", (1.6, 0.8, 0.06), (px, py, 0.75), M["wood"]))
    parts.append(add_box("desk_apron", (1.5, 0.06, 0.14), (px, py - 0.34, 0.66), M["wood"]))
    parts.append(add_box("desk_cab", (0.55, 0.72, 0.68), (px + 0.48, py, 0.38), M["wood"]))
    for i, zz in enumerate((0.2, 0.42, 0.62)):
        parts.append(add_box("desk_dr", (0.5, 0.02, 0.18), (px + 0.48, py + 0.37, zz), M["wood_d"]))
        parts.append(add_cyl("desk_h", 0.02, 0.14, (px + 0.48, py + 0.4, zz), M["metal_l"], axis="X"))
    parts.append(add_box("desk_side", (0.05, 0.72, 0.68), (px - 0.75, py, 0.38), M["wood"]))
    parts.append(add_box("mon_stand", (0.08, 0.08, 0.16), (px - 0.3, py, 0.87), M["black"]))
    parts.append(add_box("mon_base", (0.24, 0.16, 0.02), (px - 0.3, py, 0.79), M["black"]))
    parts.append(add_box("mon_screen", (0.5, 0.05, 0.34), (px - 0.3, py - 0.02, 1.06), M["black"]))
    parts.append(add_box("kbd", (0.4, 0.16, 0.02), (px - 0.3, py + 0.28, 0.79), M["black"]))
    parts.append(add_box("paper", (0.22, 0.3, 0.03), (px + 0.3, py + 0.05, 0.79), M["white"]))
    grp = _join(parts, "desk", pivot=(px, py), rot=rot)
    return [grp]


def prop_chair(px, py, rot, M):
    parts = []
    parts.append(add_box("ch_seat", (0.46, 0.46, 0.08), (px, py, 0.48), M["black"]))
    parts.append(add_box("ch_back", (0.44, 0.06, 0.44), (px, py - 0.21, 0.74), M["black"]))
    parts.append(add_cyl("ch_post", 0.03, 0.34, (px, py, 0.3), M["metal_l"]))
    for i in range(5):
        a = math.radians(i * 72)
        ex, ey = px + 0.22 * math.cos(a), py + 0.22 * math.sin(a)
        parts.append(add_cyl("ch_arm", 0.02, 0.22, ((px + ex) / 2, (py + ey) / 2, 0.11), M["black"], axis="X"))
        parts.append(add_cyl("ch_wheel", 0.035, 0.04, (ex, ey, 0.05), M["rubber"], axis="X"))
    grp = _join(parts, "chair", pivot=(px, py), rot=rot)
    return [grp]


def prop_shelf(px, py, rot, M):
    import random
    rng = random.Random(int(px * 13 + py * 7))
    parts = []
    for dx in (-0.22, 0.22):
        for dy in (-0.65, 0.65):
            parts.append(add_box("sh_post", (0.04, 0.04, 2.0), (px + dx, py + dy, 1.0), M["metal"]))
    for z in (0.4, 0.9, 1.4, 1.9):
        parts.append(add_box("sh_plate", (0.5, 1.4, 0.03), (px, py, z), M["metal_l"]))
        for _ in range(rng.randint(1, 3)):
            ox = rng.uniform(-0.15, 0.15)
            oy = rng.uniform(-0.55, 0.55)
            h = rng.uniform(0.14, 0.28)
            mat = rng.choice([M["box"], M["porc"], M["wood"]])
            parts.append(add_box("sh_item", (rng.uniform(0.12, 0.2), rng.uniform(0.14, 0.24), h),
                                  (px + ox, py + oy, z + 0.03 + h / 2), mat))
    grp = _join(parts, "shelf", pivot=(px, py), rot=rot)
    return [grp]


def prop_locker(px, py, rot, M):
    parts = []
    parts.append(add_box("lk_body", (0.9, 0.55, 1.9), (px, py, 0.95), M["locker"]))
    parts.append(add_box("lk_top", (0.94, 0.59, 0.04), (px, py, 1.92), M["locker_d"]))
    for dx in (-0.22, 0.22):
        parts.append(add_box("lk_door", (0.42, 0.03, 1.78), (px + dx, py + 0.28, 0.95), M["locker_d"]))
        parts.append(add_cyl("lk_handle", 0.015, 0.16, (px + dx + 0.15, py + 0.31, 1.0), M["metal_l"]))
        for gz in (1.55, 1.62, 1.69):
            parts.append(add_box("lk_vent", (0.28, 0.01, 0.02), (px + dx, py + 0.3, gz), M["black"]))
    grp = _join(parts, "locker", pivot=(px, py), rot=rot)
    return [grp]


def prop_sink(px, py, rot, M):
    parts = []
    parts.append(add_box("sk_basin", (0.6, 0.48, 0.12), (px, py, 0.86), M["porc"]))
    parts.append(add_box("sk_inner", (0.46, 0.34, 0.1), (px, py + 0.02, 0.92), M["porc_d"]))
    parts.append(add_box("sk_col", (0.18, 0.18, 0.8), (px, py - 0.1, 0.45), M["porc"]))
    parts.append(add_cyl("sk_tap", 0.02, 0.18, (px, py - 0.16, 0.95), M["metal_l"]))
    parts.append(add_cyl("sk_spout", 0.018, 0.14, (px, py - 0.08, 1.03), M["metal_l"], axis="Y"))
    parts.append(add_box("sk_mirror", (0.4, 0.02, 0.5), (px, py - 0.22, 1.4), M["glass"]))
    grp = _join(parts, "sink", pivot=(px, py), rot=rot)
    return [grp]


def prop_fusebox_panel(px, py, rot, M):
    parts = []
    parts.append(add_box("fb_box", (0.16, 0.9, 1.1), (px, py, 1.5), M["metal_l"]))
    parts.append(add_box("fb_door", (0.04, 0.85, 1.0), (px + 0.13, py + 0.4, 1.5), M["locker_d"]))
    parts.append(add_box("fb_panel", (0.06, 0.7, 0.85), (px + 0.06, py, 1.5), M["black"]))
    for i in range(6):
        zz = 1.2 + i * 0.11
        parts.append(add_box("fb_sw", (0.05, 0.08, 0.06), (px + 0.11, py - 0.2, zz), M["warn"]))
        parts.append(add_box("fb_sw2", (0.05, 0.08, 0.06), (px + 0.11, py + 0.05, zz), M["metal_l"]))
    parts.append(add_box("fb_label", (0.02, 0.3, 0.2), (px + 0.14, py + 0.25, 1.75), M["warn"]))
    parts.append(add_cyl("fb_conduit", 0.03, 0.6, (px + 0.05, py, 2.3), M["metal"]))
    grp = _join(parts, "fusebox", pivot=(px, py), rot=rot)
    return [grp]


def prop_ivpole(px, py, rot, M):
    parts = []
    parts.append(add_cyl("iv_pole", 0.018, 1.8, (px, py, 0.9), M["metal_l"]))
    parts.append(add_cyl("iv_hook", 0.012, 0.3, (px, py, 1.78), M["metal_l"], axis="X"))
    parts.append(add_box("iv_bag", (0.14, 0.05, 0.26), (px + 0.12, py, 1.55), M["fluid"]))
    for i in range(5):
        a = math.radians(i * 72)
        ex, ey = px + 0.24 * math.cos(a), py + 0.24 * math.sin(a)
        parts.append(add_cyl("iv_foot", 0.015, 0.24, ((px + ex) / 2, (py + ey) / 2, 0.06), M["metal"], axis="X"))
        parts.append(add_cyl("iv_wheel", 0.03, 0.03, (ex, ey, 0.04), M["rubber"], axis="X"))
    grp = _join(parts, "ivpole", pivot=(px, py), rot=rot)
    return [grp]


def prop_monitor(px, py, rot, M):
    parts = []
    parts.append(add_cyl("vm_pole", 0.025, 1.1, (px, py, 0.55), M["metal_l"]))
    parts.append(add_box("vm_body", (0.34, 0.3, 0.3), (px, py, 1.25), M["black"]))
    parts.append(add_box("vm_screen", (0.28, 0.02, 0.22), (px, py - 0.15, 1.28), M["screen"]))
    for i in range(4):
        a = math.radians(i * 90 + 45)
        ex, ey = px + 0.22 * math.cos(a), py + 0.22 * math.sin(a)
        parts.append(add_cyl("vm_foot", 0.014, 0.22, ((px + ex) / 2, (py + ey) / 2, 0.05), M["metal"], axis="X"))
        parts.append(add_cyl("vm_wheel", 0.03, 0.03, (ex, ey, 0.04), M["rubber"], axis="X"))
    grp = _join(parts, "monitor", pivot=(px, py), rot=rot)
    return [grp]


def prop_wheelchair(px, py, rot, M):
    parts = []
    parts.append(add_box("wc_seat", (0.42, 0.42, 0.06), (px, py, 0.5), M["black"]))
    parts.append(add_box("wc_back", (0.42, 0.05, 0.44), (px, py - 0.2, 0.74), M["black"]))
    for dx in (-0.26, 0.26):
        parts.append(add_cyl("wc_wheel", 0.28, 0.04, (px + dx, py - 0.05, 0.28), M["metal_l"], axis="X"))
        parts.append(add_cyl("wc_front", 0.09, 0.03, (px + dx, py + 0.32, 0.09), M["rubber"], axis="X"))
        parts.append(add_box("wc_arm", (0.05, 0.4, 0.05), (px + dx, py, 0.72), M["metal"]))
    grp = _join(parts, "wheelchair", pivot=(px, py), rot=rot)
    return [grp]


def prop_boxes(px, py, rot, M):
    import random
    rng = random.Random(int(px * 5 + py * 11))
    parts = []
    z = 0.0
    for _ in range(rng.randint(2, 4)):
        w = rng.uniform(0.35, 0.55)
        d = rng.uniform(0.35, 0.5)
        h = rng.uniform(0.28, 0.42)
        ox = rng.uniform(-0.1, 0.1)
        oy = rng.uniform(-0.1, 0.1)
        parts.append(add_box("box", (w, d, h), (px + ox, py + oy, z + h / 2), M["box"]))
        z += h
    grp = _join(parts, "boxes", pivot=(px, py), rot=rot)
    return [grp]


def prop_curtain(px, py, rot, M):
    parts = []
    parts.append(add_cyl("cur_track", 0.02, 2.2, (px, py, 2.4), M["metal_l"], axis="Y"))
    for i in range(11):
        oy = -1.0 + i * 0.2
        sway = 0.03 * math.sin(i * 1.3)
        parts.append(add_box("cur_fold", (0.03, 0.22, 1.9), (px + sway, py + oy, 1.45), M["curtain"]))
    grp = _join(parts, "curtain", pivot=(px, py), rot=rot)
    return [grp]


def prop_bedtable(px, py, rot, M):
    parts = []
    parts.append(add_box("bt_top", (0.4, 0.4, 0.04), (px, py, 0.72), M["wood"]))
    parts.append(add_box("bt_cab", (0.34, 0.34, 0.4), (px, py, 0.5), M["wood"]))
    parts.append(add_cyl("bt_cup", 0.04, 0.1, (px + 0.08, py, 0.79), M["porc"]))
    for dx in (-0.16, 0.16):
        for dy in (-0.16, 0.16):
            parts.append(add_box("bt_leg", (0.03, 0.03, 0.7), (px + dx, py + dy, 0.35), M["wood_d"]))
    grp = _join(parts, "bedtable", pivot=(px, py), rot=rot)
    return [grp]


def _join(objs, name, pivot=None, rot=0.0):
    if not objs:
        return None
    for o in bpy.data.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = objs[0]
    for o in objs:
        o.select_set(True)
    if len(objs) > 1:
        bpy.ops.object.join()
    g = bpy.context.active_object
    g.name = name
    if pivot is not None and abs(rot) > 1e-6:
        scene = bpy.context.scene
        prev = tuple(scene.cursor.location)
        scene.cursor.location = (pivot[0], pivot[1], 0.0)
        bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
        g.rotation_euler = (0, 0, math.radians(rot))
        bpy.ops.object.transform_apply(rotation=True)
        scene.cursor.location = prev
    return g


PROP_FUNCS = {
    "bed": prop_bed, "gurney": prop_gurney, "desk": prop_desk,
    "chair": prop_chair, "shelf": prop_shelf, "locker": prop_locker,
    "sink": prop_sink, "fusebox_panel": prop_fusebox_panel,
    "ivpole": prop_ivpole, "monitor": prop_monitor, "wheelchair": prop_wheelchair,
    "boxes": prop_boxes, "curtain": prop_curtain, "bedtable": prop_bedtable,
}


def build():
    clear_scene()
    M = {
        "floor":   make_material("floor", (0.22, 0.23, 0.22), rough=0.7),
        "floor2":  make_material("floor2", (0.16, 0.17, 0.17), rough=0.75),
        "wall":    make_material("wall", (0.40, 0.41, 0.38), rough=0.92),
        "wall_low":make_material("wall_low", (0.28, 0.32, 0.34), rough=0.9),
        "ceil":    make_material("ceil", (0.14, 0.15, 0.17), rough=0.95),
        "trim":    make_material("trim", (0.22, 0.18, 0.15), rough=0.8),
        "metal":   make_material("metal", (0.50, 0.52, 0.55), rough=0.4, metal=0.9),
        "metal_l": make_material("metal_l", (0.72, 0.74, 0.76), rough=0.25, metal=0.95),
        "bed":     make_material("bed", (0.70, 0.73, 0.77), rough=0.7),
        "white":   make_material("white", (0.86, 0.87, 0.88), rough=0.6),
        "wood":    make_material("wood", (0.40, 0.29, 0.19), rough=0.75),
        "wood_d":  make_material("wood_d", (0.28, 0.20, 0.13), rough=0.8),
        "black":   make_material("black", (0.08, 0.08, 0.09), rough=0.5),
        "rubber":  make_material("rubber", (0.05, 0.05, 0.06), rough=0.9),
        "locker":  make_material("locker", (0.30, 0.44, 0.42), rough=0.55, metal=0.4),
        "locker_d":make_material("locker_d", (0.24, 0.36, 0.35), rough=0.55, metal=0.4),
        "porc":    make_material("porc", (0.86, 0.87, 0.89), rough=0.35),
        "porc_d":  make_material("porc_d", (0.70, 0.72, 0.74), rough=0.4),
        "glass":   make_material("glass", (0.6, 0.68, 0.72), rough=0.1, metal=0.3),
        "box":     make_material("box", (0.55, 0.44, 0.30), rough=0.9),
        "curtain": make_material("curtain", (0.45, 0.55, 0.58), rough=0.85),
        "fluid":   make_material("fluid", (0.85, 0.9, 0.8), rough=0.2),
        "warn":    make_material("warn", (0.9, 0.5, 0.1), rough=0.5, emit=(0.9, 0.4, 0.05), emit_str=1.5),
        "screen":  make_material("screen", (0.1, 0.5, 0.35), rough=0.3, emit=(0.1, 0.6, 0.4), emit_str=1.0),
        "lamp":    make_material("lamp", (0.9, 0.95, 1.0), rough=0.5, emit=(0.85, 0.9, 1.0), emit_str=0.6),
    }
    t = 0.2
    fw = L.FLOOR_X1 - L.FLOOR_X0
    fl = L.FLOOR_Y1 - L.FLOOR_Y0
    cx = (L.FLOOR_X0 + L.FLOOR_X1) / 2
    cy = (L.FLOOR_Y0 + L.FLOOR_Y1) / 2
    add_box("Floor", (fw, fl, t), (cx, cy, -t / 2), M["floor"])
    add_box("Ceiling", (fw, fl, t), (cx, cy, L.WALL_H + t / 2), M["ceil"])
    for i, (mx, my, lx, ly) in enumerate(L.WALLS):
        add_box("Wall_%d" % i, (lx, ly, L.WALL_H), (mx, my, L.WALL_H / 2), M["wall"])
        add_box("Dado_%d" % i, (lx + 0.03, ly + 0.03, 1.1), (mx, my, 0.55), M["wall_low"])
        add_box("Base_%d" % i, (lx + 0.05, ly + 0.05, 0.14), (mx, my, 0.07), M["trim"])
    lamp_xy = [(0, y) for y in range(2, 54, 8)]
    lamp_xy += [(-8, 8), (-8, 30), (8, 6), (8, 33), (8, 46)]
    for i, (lx, ly) in enumerate(lamp_xy):
        add_box("LampBox_%d" % i, (1.5, 0.3, 0.12), (lx, ly, L.WALL_H - 0.06), M["metal_l"])
        add_box("LampTube_%d" % i, (1.3, 0.16, 0.05), (lx, ly, L.WALL_H - 0.13), M["lamp"])
    for mx in (-1.4, 1.4):
        add_cyl("Pipe_%d" % int(mx * 10), 0.06, fl - 2, (mx, cy, L.WALL_H - 0.25), M["metal"], axis="Y")
    for yy in range(4, 54, 12):
        add_cyl("PipeX_%d" % yy, 0.045, 3.2, (0, yy, L.WALL_H - 0.4), M["metal"], axis="X")
    for y in L._WEST_DOORS:
        _door_frame(-2, y, "X", M)
    for y in L._EAST_DOORS:
        _door_frame(2, y, "X", M)
    for p in L.PROPS:
        fn = PROP_FUNCS.get(p["type"])
        if fn:
            fn(p["pos"][0], p["pos"][1], p.get("rot", 0), M)
    out_dir = os.path.join(_ROOT, "assets", "models")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "level.glb")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(filepath=out_path, export_format="GLB",
                              use_selection=True, export_apply=True)
    print("EXPORTED", out_path, os.path.getsize(out_path), "bytes")


def _door_frame(mx, my, axis, M):
    dw = L.DOOR_W
    dh = 2.3
    if axis == "X":
        for dy in (-dw / 2 - 0.06, dw / 2 + 0.06):
            add_box("DFpost", (0.26, 0.1, dh), (mx, my + dy, dh / 2), M["trim"])
        add_box("DFhead", (0.26, dw + 0.24, 0.14), (mx, my, dh), M["trim"])


if __name__ == "__main__":
    build()
