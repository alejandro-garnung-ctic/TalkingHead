"""
graft_suit.py — Injerta piezas de ropa de un avatar donante (p.ej. avaturn_dirkjan,
que trae traje) sobre un avatar base (p.ej. avaturn_josed), conservando la cara y la
complexión del base.

Ambos modelos comparten el mismo esqueleto Mixamo (54 huesos, mismos nombres), así que
la malla donante se re-vincula al armature del base por nombre de hueso.

Uso:
  blender -b -P graft_suit.py -- base.glb donante.glb salida.glb [--parts look_0,shoes_0]
"""

import bpy, sys

def parse():
    argv = sys.argv[sys.argv.index("--") + 1:]
    a = {"base": argv[0], "donor": argv[1], "out": argv[2],
         "parts": ["avaturn_look_0", "avaturn_shoes_0"]}
    i = 3
    while i < len(argv):
        if argv[i] == "--parts":
            a["parts"] = argv[i+1].split(","); i += 2
        else:
            i += 1
    return a

def main():
    a = parse()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=a["base"])
    base_objs = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=a["donor"])
    donor_objs = set(bpy.data.objects) - base_objs

    base_arm = [o for o in base_objs if o.type == "ARMATURE"][0]
    print("base armature:", base_arm.name)

    def alive(o):
        try:
            _ = o.name
            return True
        except ReferenceError:
            return False

    def find(objs, name):
        return [o for o in objs if alive(o) and o.type == "MESH" and o.name.startswith(name)]

    kept = []
    for part in a["parts"]:
        bm = find(base_objs, part)
        dm = find(donor_objs, part)
        if not dm:
            print("SIN donante para", part); continue
        for o in bm:
            print("borrando base", o.name)
            bpy.data.objects.remove(o, do_unlink=True)
        m = dm[0]
        m.parent = base_arm
        m.matrix_parent_inverse = base_arm.matrix_world.inverted()
        mods = [md for md in m.modifiers if md.type == "ARMATURE"]
        if mods:
            mods[0].object = base_arm
        else:
            m.modifiers.new("Armature", "ARMATURE").object = base_arm
        m.name = part
        kept.append(m)
        print("injertado donante", m.name, "verts", len(m.data.vertices),
              "mat", m.data.materials[0].name if m.data.materials else None)

    for o in list(donor_objs):
        if o not in kept and alive(o) and o.name in bpy.data.objects:
            bpy.data.objects.remove(o, do_unlink=True)

    bpy.ops.export_scene.gltf(
        filepath=a["out"], export_format="GLB",
        export_morph=True, export_morph_normal=True,
        export_skins=True, export_apply=False, export_yup=True,
    )
    print("EXPORTADO:", a["out"])

main()
