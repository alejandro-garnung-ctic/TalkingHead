"""
swap_head.py — Pone la cabeza/cara de un avatar donante (p.ej. avaturn_josed) sobre el
cuerpo de un avatar base (p.ej. avaturn_dirkjan, que ya trae traje y cuello coherentes).

Motivación: injertar el traje del donante sobre el cuerpo del base deja un desajuste en el
cuello/collar (el cuello del base es más grueso que la abertura del traje). En su lugar,
se parte del base (cuerpo+cuello+traje ya encajan entre sí) y se le cambia solo la cabeza.

Las cabezas Avaturn comparten forma base, así que se alinean por el centroide de la cabeza.
Los morphs (52 ARKit + 15 visemas) viajan con la malla del donante.

Uso:
  blender -b -P swap_head.py -- base.glb donante.glb salida.glb [opciones]

Opciones:
  --parts a,b,c     piezas de cabeza a sustituir (por defecto cabeza, ojos, dientes,
                    lengua, pelo y gafas del donante)
  --head-scale F    escala la cabeza del donante sobre el punto del cuello  [def 1.0]
  --neck-drop F     baja la cabeza del donante este extra (m)              [def 0.0]
"""

import bpy, sys
import numpy as np
from mathutils import Vector

DEFAULT_PARTS = ["Head_Mesh", "Eye_Mesh", "EyeAO_Mesh", "Eyelash_Mesh",
                 "Teeth_Mesh", "Tongue_Mesh", "avaturn_hair_0", "avaturn_hair_1",
                 "avaturn_glasses_0", "avaturn_glasses_1"]

def parse():
    argv = sys.argv[sys.argv.index("--") + 1:]
    a = {"base": argv[0], "donor": argv[1], "out": argv[2],
         "parts": DEFAULT_PARTS, "head_scale": 1.0, "neck_drop": 0.0}
    i = 3
    while i < len(argv):
        if argv[i] == "--parts":
            a["parts"] = argv[i+1].split(","); i += 2
        elif argv[i] == "--head-scale":
            a["head_scale"] = float(argv[i+1]); i += 2
        elif argv[i] == "--neck-drop":
            a["neck_drop"] = float(argv[i+1]); i += 2
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

def main():
    a = parse()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=a["base"])
    base_objs = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=a["donor"])
    donor_objs = set(bpy.data.objects) - base_objs

    base_arm = [o for o in base_objs if o.type == "ARMATURE"][0]

    def find(objs, name):
        return [o for o in objs if alive(o) and o.type == "MESH" and o.name.startswith(name)]

    bh = find(base_objs, "Head_Mesh")[0]
    dh = find(donor_objs, "Head_Mesh")[0]

    hb = world_verts(bh)
    hd = world_verts(dh)
    vec_world = hb.mean(0) - hd.mean(0)

    def neck_ring_center(vs):
        zmin = vs[:, 2].min()
        return vs[np.abs(vs[:, 2] - zmin) < 0.012].mean(0)

    pivot = neck_ring_center(hb) + vec_world
    drop = np.array([0.0, 0.0, -a["neck_drop"]])
    scale = a["head_scale"]
    print("desplazamiento mundo:", np.round(vec_world, 4),
          "escala:", scale, "bajada extra:", a["neck_drop"])

    def make_fn(vec):
        def fn(w):
            w = np.array([w[0], w[1], w[2]])
            r = pivot + scale * ((w + vec) - pivot) + drop
            return Vector((r[0], r[1], r[2]))
        return fn

    replaced = []
    for part in a["parts"]:
        bm = find(base_objs, part)
        dm = find(donor_objs, part)
        if not dm:
            continue
        d = dm[0]
        xform_all(d, make_fn(vec_world))
        for o in bm:
            bpy.data.objects.remove(o, do_unlink=True)
        d.parent = base_arm
        d.matrix_parent_inverse = base_arm.matrix_world.inverted()
        mods = [m for m in d.modifiers if m.type == "ARMATURE"]
        if mods:
            mods[0].object = base_arm
        else:
            d.modifiers.new("Armature", "ARMATURE").object = base_arm
        d.name = part
        replaced.append(d)
        print("cabeza injertada:", part, "verts", len(d.data.vertices),
              "morphs", len(d.data.shape_keys.key_blocks) - 1 if d.data.shape_keys else 0)

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
