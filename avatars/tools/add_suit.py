"""
add_suit.py — Añade un traje formal neutro (negro/gris) a un avatar TalkingHead
compatible (Avaturn, RPM, ...), reemplazando las texturas de la malla de ropa.

No basta con repintar el color: la chaqueta vieja lleva grabado en el NORMAL MAP y
el ROUGHNESS sus arrugas/cuero. Este script procesa las tres texturas del material
de ropa:
  · base color  -> color del traje (chaqueta/camisa/corbata) modulado por la luz
                   difuminada (conserva pliegues grandes, borra grano/botones).
  · normal      -> casi plano + microtejido sutil (borra el relieve del cuero).
  · roughness   -> tejido (rugosidad uniforme, metallic 0).

Clasificación de regiones por POSICIÓN 3D de los vértices (no por UV), de modo que
funciona con cualquier modelo con malla de ropa y rig Mixamo.

Uso:
  blender -b -P add_suit.py -- entrada.glb salida.glb [opciones]

Opciones:
  --jacket R,G,B     color chaqueta/americana (sRGB 0-1)   [def 0.10,0.10,0.12]
  --shirt  R,G,B     color camisa                            [def 0.94,0.94,0.94]
  --tie    R,G,B     color corbata                            [def 0.13,0.14,0.17]
  --no-tie           sin corbata
  --rough F          rugosidad del tejido 0-1                 [def 0.72]
  --fabric F         amplitud del microtejido en normal 0-1   [def 0.04]
  --blur N           radio de difuminado de la luz             [def 6]
  --mesh NOMBRE      forzar malla de ropa por nombre
  --texture PREFIX   guardar las texturas resultantes (PREFIX_base.png, _normal, _rough)
"""

import bpy, sys, os, math, random
import numpy as np

def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:]
    a = {"input": argv[0], "output": argv[1],
         "jacket": (0.10, 0.10, 0.12), "shirt": (0.94, 0.94, 0.94),
         "tie": (0.13, 0.14, 0.17), "tie_on": True,
         "rough": 0.72, "fabric": 0.04, "blur": 6,
         "mesh": None, "texture": None}
    i = 2
    while i < len(argv):
        k = argv[i]
        if k == "--jacket": a["jacket"] = tuple(float(x) for x in argv[i+1].split(",")); i += 2
        elif k == "--shirt": a["shirt"] = tuple(float(x) for x in argv[i+1].split(",")); i += 2
        elif k == "--tie": a["tie"] = tuple(float(x) for x in argv[i+1].split(",")); i += 2
        elif k == "--no-tie": a["tie_on"] = False; i += 1
        elif k == "--rough": a["rough"] = float(argv[i+1]); i += 2
        elif k == "--fabric": a["fabric"] = float(argv[i+1]); i += 2
        elif k == "--blur": a["blur"] = int(argv[i+1]); i += 2
        elif k == "--mesh": a["mesh"] = argv[i+1]; i += 2
        elif k == "--texture": a["texture"] = argv[i+1]; i += 2
        else: i += 1
    return a

def srgb_to_linear(c):
    return tuple((v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4) for v in c)

def find_clothing(args):
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if args["mesh"]:
        for o in meshes:
            if o.name == args["mesh"]:
                return o
    for o in meshes:
        for m in o.data.materials:
            if m and "look" in m.name.lower():
                return o
    for o in meshes:
        for m in o.data.materials:
            if m and any(t in m.name.lower() for t in ("cloth", "outfit", "garment")):
                return o
    skip = ("head", "eye", "lash", "teeth", "tongue", "hair", "shoe", "glass", "body")
    cands = [o for o in meshes if not any(s in o.name.lower() for s in skip)]
    return max(cands, key=lambda o: len(o.data.vertices)) if cands else None

def trace_image(socket, depth=0):
    if depth > 8 or not socket.is_linked:
        return None
    node = socket.links[0].from_node
    if node.type == "TEX_IMAGE" and node.image:
        return node.image
    for inp in node.inputs:
        img = trace_image(inp, depth + 1)
        if img:
            return img
    return None

def find_map(mat, names):
    if not mat or not mat.use_nodes:
        return None
    for n in mat.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            for inp in n.inputs:
                if inp.name in names:
                    img = trace_image(inp)
                    if img:
                        return img
    return None

def classify(x, y, z, arm_x=0.185, z_leg=0.96, z_v=1.15, z_top=1.56, v_half=0.115, tie_half=0.026):
    ax = abs(x)
    if ax > arm_x and z > 0.85:
        return 0
    if z < z_leg:
        return 0
    if y < 0.02 and z_v < z < z_top:
        w = v_half * (z - z_v) / (z_top - z_v)
        if ax < w:
            if ax < tie_half and z < 1.40:
                return 2
            return 1
    return 0

def to_np(img):
    w, h = img.size
    return np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4), w, h

def _box1d(a, r, axis):
    n = a.shape[axis]
    k = 2 * r + 1
    pad = [(0, 0)] * a.ndim
    pad[axis] = (r, r)
    ap = np.pad(a, pad, mode="edge")
    c = np.cumsum(ap, axis=axis)
    zshape = list(c.shape); zshape[axis] = 1
    c = np.concatenate([np.zeros(zshape, dtype=c.dtype), c], axis=axis)
    lo = [slice(None)] * a.ndim; hi = [slice(None)] * a.ndim
    lo[axis] = slice(0, n); hi[axis] = slice(k, n + k)
    return (c[tuple(hi)] - c[tuple(lo)]) / k

def blur_rgb(arr, radius, passes=2):
    if radius < 1:
        return arr
    a = arr.astype(np.float32)
    for _ in range(passes):
        a = _box1d(a, radius, 0)
        a = _box1d(a, radius, 1)
    return a

def raster_regions(me, w, h):
    verts = np.array([v.co[:] for v in me.vertices], dtype=np.float32)
    uvdata = np.array([d.uv[:] for d in me.uv_layers.active.data], dtype=np.float32)
    region_map = np.full((h, w), -1, dtype=np.int8)
    counts = {0: 0, 1: 0, 2: 0}
    for poly in me.polygons:
        li = list(poly.loop_indices)
        vi = [me.loops[l].vertex_index for l in li]
        for k in range(1, len(li) - 1):
            i0, i1, i2 = 0, k, k + 1
            a, b, c = li[i0], li[i1], li[i2]
            va, vb, vc = vi[i0], vi[i1], vi[i2]
            p = (verts[va] + verts[vb] + verts[vc]) / 3.0
            region = classify(float(p[0]), float(p[1]), float(p[2]))
            counts[region] += 1
            uv0, uv1, uv2 = uvdata[a], uvdata[b], uvdata[c]
            x0, y0 = uv0[0] * (w - 1), uv0[1] * (h - 1)
            x1, y1 = uv1[0] * (w - 1), uv1[1] * (h - 1)
            x2, y2 = uv2[0] * (w - 1), uv2[1] * (h - 1)
            minx, maxx = int(math.floor(min(x0, x1, x2))), int(math.ceil(max(x0, x1, x2)))
            miny, maxy = int(math.floor(min(y0, y1, y2))), int(math.ceil(max(y0, y1, y2)))
            xs = np.arange(minx, maxx + 1); ys = np.arange(miny, maxy + 1)
            if len(xs) == 0 or len(ys) == 0:
                continue
            gx, gy = np.meshgrid(xs, ys)
            d = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
            if abs(d) < 1e-9:
                continue
            w0 = ((x1 - gx) * (y2 - gy) - (x2 - gx) * (y1 - gy)) / d
            w1 = ((x2 - gx) * (y0 - gy) - (x0 - gx) * (y2 - gy)) / d
            w2 = 1.0 - w0 - w1
            inside = (w0 >= -0.001) & (w1 >= -0.001) & (w2 >= -0.001)
            if not inside.any():
                continue
            px_x = gx[inside].astype(np.int32); px_y = gy[inside].astype(np.int32)
            ok = (px_x >= 0) & (px_x < w) & (px_y >= 0) & (px_y < h)
            if ok.any():
                region_map[px_y[ok], px_x[ok]] = region
    return region_map, counts

def main():
    args = parse_args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=args["input"])

    obj = find_clothing(args)
    if obj is None:
        print("ERROR: no se encontró malla de ropa"); sys.exit(1)
    mat = obj.data.materials[0] if obj.data.materials else None
    print(f"ROPA: {obj.name} verts={len(obj.data.vertices)} polys={len(obj.data.polygons)} mat={mat.name if mat else None}")

    img_base = find_map(mat, {"Base Color"})
    img_rough = find_map(mat, {"Roughness"})
    img_normal = find_map(mat, {"Normal"})
    print(f"TEXTURAS: base={img_base.name if img_base else None} "
          f"rough={img_rough.name if img_rough else None} normal={img_normal.name if img_normal else None}")

    if img_base is None:
        print("ERROR: la ropa no tiene textura base color"); sys.exit(1)

    base_px, w, h = to_np(img_base)
    region_map, counts = raster_regions(obj.data, w, h)
    print(f"regiones: chaqueta={counts[0]} camisa={counts[1]} corbata={counts[2]} "
          f"px={int((region_map>=0).sum())}")

    jacket = np.array(srgb_to_linear(args["jacket"]), dtype=np.float32)
    shirt = np.array(srgb_to_linear(args["shirt"]), dtype=np.float32)
    tie = np.array(srgb_to_linear(args["tie"]), dtype=np.float32)
    targets = {0: jacket, 1: shirt, 2: tie}
    if not args["tie_on"]:
        targets[2] = jacket

    # --- base color: color objetivo modulado por luz difuminada (conserva pliegues) ---
    lum = 0.299 * base_px[:, :, 0] + 0.587 * base_px[:, :, 1] + 0.114 * base_px[:, :, 2]
    lum_blur = blur_rgb(lum[:, :, None].repeat(3, axis=2), args["blur"])[:, :, 0]
    out_base = base_px.copy()
    for reg in (0, 1, 2):
        mask = region_map == reg
        if not mask.any():
            continue
        ref = max(float(np.mean(lum_blur[mask])), 1e-4)
        scale = (lum_blur / ref)[:, :, None]
        col = np.clip(targets[reg][None, None, :] * scale, 0.0, 1.0)
        out_base[:, :, :3] = np.where(mask[:, :, None], col, out_base[:, :, :3])
    img_base.pixels[:] = out_base.reshape(-1).tolist()
    img_base.update(); img_base.pack()
    if args["texture"]:
        img_base.filepath_raw = args["texture"] + "_base.png"
        img_base.file_format = "PNG"; img_base.save()

    # --- normal: casi plano + microtejido (borra el relieve del cuero) ---
    if img_normal:
        n_px, nw, nh = to_np(img_normal)
        img_normal.colorspace_settings.name = "Non-Color"
        rng = np.random.default_rng(7)
        noise = rng.normal(0.0, args["fabric"], (nh, nw, 1)).astype(np.float32)
        n_px[:, :, 0] = np.clip(0.5 + noise[:, :, 0], 0, 1)
        n_px[:, :, 1] = 0.5
        n_px[:, :, 2] = 1.0
        img_normal.pixels[:] = n_px.reshape(-1).tolist()
        img_normal.update(); img_normal.pack()
        if args["texture"]:
            img_normal.filepath_raw = args["texture"] + "_normal.png"
            img_normal.file_format = "PNG"; img_normal.save()

    # --- roughness: tejido uniforme (G), metallic 0 (B) ---
    if img_rough:
        r_px, rw, rh = to_np(img_rough)
        img_rough.colorspace_settings.name = "Non-Color"
        r_px[:, :, 0] = 1.0
        r_px[:, :, 1] = args["rough"]
        r_px[:, :, 2] = 0.0
        img_rough.pixels[:] = r_px.reshape(-1).tolist()
        img_rough.update(); img_rough.pack()
        if args["texture"]:
            img_rough.filepath_raw = args["texture"] + "_rough.png"
            img_rough.file_format = "PNG"; img_rough.save()

    bpy.ops.export_scene.gltf(
        filepath=args["output"], export_format="GLB",
        export_morph=True, export_morph_normal=True,
        export_skins=True, export_apply=False, export_yup=True,
    )
    print(f"EXPORTADO: {args['output']}")

main()
