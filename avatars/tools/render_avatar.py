import bpy, sys, os, math
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
glb = argv[0]
out = argv[1]
mode = argv[2] if len(argv) > 2 else "head"

bpy.ops.wm.read_factory_settings(use_empty=True)

bpy.ops.import_scene.gltf(filepath=glb)

meshes = [o for o in bpy.data.objects if o.type == "MESH"]
if not meshes:
    print("NO_MESH"); sys.exit(1)

mn = Vector((1e9, 1e9, 1e9))
mx = Vector((-1e9, -1e9, -1e9))
for o in meshes:
    for c in o.bound_box:
        w = o.matrix_world @ Vector(c)
        for i in range(3):
            mn[i] = min(mn[i], w[i]); mx[i] = max(mx[i], w[i])

height = mx.z - mn.z
center_x = (mn.x + mx.x) / 2
center_y = (mn.y + mx.y) / 2
print(f"BBOX z {mn.z:.3f}..{mx.z:.3f} h={height:.3f}")

if mode == "head":
    target_z = mn.z + height * 0.93
    frame_h = height * 0.22
elif mode == "neck":
    target_z = mn.z + height * 0.845
    frame_h = height * 0.16
elif mode == "bust":
    target_z = mn.z + height * 0.82
    frame_h = height * 0.55
else:
    target_z = mn.z + height * 0.75
    frame_h = height * 0.55

target = Vector((center_x, center_y, target_z))

cam_data = bpy.data.cameras.new("Cam")
cam_data.lens = 60
cam = bpy.data.objects.new("Cam", cam_data)
bpy.context.scene.collection.objects.link(cam)

dist = frame_h / (2 * math.tan(cam_data.angle / 2)) * 1.1
cam.location = Vector((center_x, center_y - dist, target_z))
d = target - cam.location
cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
bpy.context.scene.camera = cam

def add_light(name, ltype, loc, energy, size=2.0):
    ld = bpy.data.lights.new(name, ltype)
    ld.energy = energy
    if ltype == "AREA":
        ld.size = size
    lo = bpy.data.objects.new(name, ld)
    lo.location = loc
    d = target - lo.location
    lo.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.collection.objects.link(lo)

add_light("Key", "AREA", (center_x - 1.5, center_y - 2.0, target_z + 1.5), 400, 2.0)
add_light("Fill", "AREA", (center_x + 1.5, center_y - 1.5, target_z), 150, 2.0)
add_light("Rim", "AREA", (center_x, center_y + 2.0, target_z + 1.0), 200, 2.0)

world = bpy.data.worlds.new("W")
bpy.context.scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.05, 0.05, 0.06, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 1.0

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
try:
    scene.eevee.taa_render_samples = 32
except Exception:
    pass
scene.render.resolution_x = 512
scene.render.resolution_y = 640
scene.render.film_transparent = False
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = out

bpy.ops.render.render(write_still=True)
print("RENDERED", out)
