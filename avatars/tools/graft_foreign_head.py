"""
graft_foreign_head.py — Injerta la cabeza de un avatar con rig/topología DISTINTOS
(p.ej. avatarsdk, 73 huesos, cabeza de 7267 verts) sobre el cuerpo+traje de un base
(p.ej. avaturn_dirkjan, 54 huesos).

A diferencia de swap_head.py (que asume mismo rig y misma topología), este script:
  - mapea nombres de malla donante->base por parejas explícitas,
  - remapea/descarta vertex groups que no existen en el esqueleto base,
  - alinea por centroide de la cabeza y (opcional) ajusta el alto.

Uso:
  blender -b -P graft_foreign_head.py -- base.glb donante.glb salida.glb [opciones]

Opciones:
  --replace base=donor,...  pareja de mallas a sustituir (la 1ª es la de referencia
                            para alinear).  [def Head_Mesh=AvatarHead,Eyelash_Mesh=AvatarEyelashes]
  --add donor,...           mallas del donante a añadir tal cual (ojos, dientes...).
                            [def AvatarLeftEyeball,AvatarRightEyeball,AvatarTeethLower,AvatarTeethUpper]
  --drop-base base,...      mallas del base a eliminar sin sustituto.
                            [def Eye_Mesh,EyeAO_Mesh,Teeth_Mesh,Tongue_Mesh]
  --vg-map old=new,...      remapeo de vertex groups huérfanos (se fusionan pesos).
                            [def Neck1=Neck,Neck2=Neck,HeadTop_End=Head]
  --head-scale F            escala extra sobre el pivote del cuello. [def 1.0]
  --neck-drop F             bajada extra en metros.               [def 0.0]
  --fit-height              escala automática = alto(cabeza base)/alto(cabeza donante).
"""

import bpy, sys
import numpy as np
from mathutils import Vector

DEFAULT_REPLACE = [("Head_Mesh", "AvatarHead"), ("Eyelash_Mesh", "AvatarEyelashes")]
DEFAULT_ADD = ["AvatarLeftEyeball", "AvatarRightEyeball",
               "AvatarTeethLower", "AvatarTeethUpper"]
DEFAULT_DROP_BASE = ["Eye_Mesh", "EyeAO_Mesh", "Teeth_Mesh", "Tongue_Mesh"]
DEFAULT_VGMAP = {"Neck1": "Neck", "Neck2": "Neck", "HeadTop_End": "Head"}


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:]
    a = {"base": argv[0], "donor": argv[1], "out": argv[2],
         "replace": DEFAULT_REPLACE, "add": DEFAULT_ADD,
         "drop_base": DEFAULT_DROP_BASE, "vg_map": dict(DEFAULT_VGMAP),
         "head_scale": 1.0, "neck_drop": 0.0, "fit_height": False}
    i = 3
    while i < len(argv):
        k, v = argv[i], argv[i+1] if i + 1 < len(argv) else ""
        if k == "--replace":
            a["replace"] = [tuple(p.split("=")) for p in v.split(",") if "=" in p]; i += 2
        elif k == "--add":
            a["add"] = v.split(",") if v else []; i += 2
        elif k == "--drop-base":
            a["drop_base"] = v.split(",") if v else []; i += 2
        elif k == "--vg-map":
            a["vg_map"] = dict(p.split("=") for p in v.split(",") if "=" in p); i += 2
        elif k == "--head-scale":
            a["head_scale"] = float(v); i += 2
        elif k == "--neck-drop":
            a["neck_drop"] = float(v); i += 2
        elif k == "--fit-height":
            a["fit_height"] = True; i += 1
        else:
            i += 1
    return a


def alive(o):
    try:
        _ = o.name
        return True
    except ReferenceError:
        return False


def world_verts(o):
    mw = o.matrix_world
    return np.array([list(mw @ v.co) for v in o.data.vertices], dtype=np.float64)


def xform_all(obj, fn):
    mw = obj.matrix_world
    mi = mw.inverted()
    me = obj.data
    blocks = me.shape_keys.key_blocks if me.shape_keys else None
    if blocks:
        for kb in blocks:
            for v in kb.data:
                v.co = mi @ fn(mw @ v.co)
    else:
        for v in me.vertices:
            v.co = mi @ fn(mw @ v.co)


def merge_group(obj, src_name, dst_name):
    src = obj.vertex_groups.get(src_name)
    if src is None:
        return
    if dst_name not in obj.vertex_groups:
        src.name = dst_name
        return
    dst = obj.vertex_groups[dst_name]
    pending = []
    for v in obj.data.vertices:
        for g in v.groups:
            if g.group == src.index and g.weight > 0.0:
                pending.append((v.index, g.weight))
    for idx, w in pending:
        dst.add([idx], w, "ADD")
    obj.vertex_groups.remove(src)


def fix_groups(obj, bones, vg_map):
    for vg in list(obj.vertex_groups):
        if vg.name in bones:
            continue
        tgt = vg_map.get(vg.name)
        if tgt and tgt in bones:
            merge_group(obj, vg.name, tgt)
            print("      vg remap:", vg.name, "->", tgt)
        else:
            print("      vg drop :", vg.name)
            obj.vertex_groups.remove(vg)


def main():
    a = parse()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=a["base"])
    base_objs = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=a["donor"])
    donor_objs = set(bpy.data.objects) - base_objs

    base_arm = [o for o in base_objs if o.type == "ARMATURE"][0]
    bones = {b.name for b in base_arm.data.bones}
    print("huesos base:", len(bones))

    def find(objs, name):
        c = [o for o in objs if alive(o) and o.type == "MESH"
             and (o.name == name or o.name.startswith(name + "."))]
        c.sort(key=lambda o: (o.name != name, o.name))
        return c

    def find_empty(objs, name):
        return [o for o in objs if alive(o) and o.type == "EMPTY"
                and (o.name == name or o.name.startswith(name + "."))]

    ref_base, ref_donor = a["replace"][0]
    bh = find(base_objs, ref_base)[0]
    dh = find(donor_objs, ref_donor)[0]

    hb, hd = world_verts(bh), world_verts(dh)
    vec = hb.mean(0) - hd.mean(0)
    scale = a["head_scale"]
    if a["fit_height"]:
        scale *= (hb[:, 2].max() - hb[:, 2].min()) / (hd[:, 2].max() - hd[:, 2].min())

    zmin = hb[:, 2].min()
    pivot = hb[np.abs(hb[:, 2] - zmin) < 0.012].mean(0) + vec
    drop = np.array([0.0, 0.0, -a["neck_drop"]])
    print("desplazamiento:", np.round(vec, 4), "escala total:", round(scale, 4),
          "bajada:", a["neck_drop"])

    def make_fn():
        def fn(w):
            w = np.array([w[0], w[1], w[2]])
            r = pivot + scale * ((w + vec) - pivot) + drop
            return Vector((r[0], r[1], r[2]))
        return fn

    replaced = []
    for base_name, donor_name in a["replace"]:
        dm = find(donor_objs, donor_name)
        if not dm:
            print("AVISO: donante sin", donor_name); continue
        d = dm[0]
        xform_all(d, make_fn())
        fix_groups(d, bones, a["vg_map"])
        for o in find(base_objs, base_name) + find_empty(base_objs, base_name):
            bpy.data.objects.remove(o, do_unlink=True)
        d.parent = base_arm
        d.matrix_parent_inverse = base_arm.matrix_world.inverted()
        mods = [m for m in d.modifiers if m.type == "ARMATURE"]
        if mods:
            mods[0].object = base_arm
        else:
            d.modifiers.new("Armature", "ARMATURE").object = base_arm
        d.name = base_name
        replaced.append(d)
        print("  injertado:", donor_name, "->", base_name,
              "verts", len(d.data.vertices),
              "morphs", len(d.data.shape_keys.key_blocks) - 1 if d.data.shape_keys else 0)

    for name in a["add"]:
        dm = find(donor_objs, name)
        if not dm:
            print("AVISO: donante sin", name); continue
        d = dm[0]
        xform_all(d, make_fn())
        fix_groups(d, bones, a["vg_map"])
        d.parent = base_arm
        d.matrix_parent_inverse = base_arm.matrix_world.inverted()
        mods = [m for m in d.modifiers if m.type == "ARMATURE"]
        if mods:
            mods[0].object = base_arm
        else:
            d.modifiers.new("Armature", "ARMATURE").object = base_arm
        replaced.append(d)
        print("  añadido:", name, "verts", len(d.data.vertices))

    for name in a["drop_base"]:
        for o in find(base_objs, name) + find_empty(base_objs, name):
            bpy.data.objects.remove(o, do_unlink=True)

    for o in list(donor_objs):
        if o not in replaced and alive(o) and o.name in bpy.data.objects:
            bpy.data.objects.remove(o, do_unlink=True)

    bpy.ops.export_scene.gltf(
        filepath=a["out"], export_format="GLB",
        export_morph=True, export_morph_normal=True,
        export_skins=True, export_apply=False, export_yup=True,
    )
    print("EXPORTADO:", a["out"])


main()
