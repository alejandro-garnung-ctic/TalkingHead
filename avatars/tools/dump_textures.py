import bpy, sys, os
argv = sys.argv[sys.argv.index("--") + 1:]
glb = argv[0]; prefix = argv[1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
for o in bpy.data.objects:
    if o.type != "MESH":
        continue
    for m in o.data.materials:
        if not m or not m.use_nodes:
            continue
        for n in m.node_tree.nodes:
            if n.type == "TEX_IMAGE" and n.image:
                img = n.image
                tag = "base" if "Base Color" in [i.name for i in n.outputs] or True else "x"
                safe = "".join(c for c in (o.name + "_" + m.name) if c.isalnum() or c in "_-")
                path = f"{prefix}_{safe}.png"
                img.filepath_raw = path
                img.file_format = "PNG"
                try:
                    img.save()
                    print("SAVED", path, img.size[0], img.size[1])
                except Exception as e:
                    print("ERR", path, e)
