import json, struct, glob, os, sys

ARKIT = ["eyeBlinkLeft","eyeBlinkRight","eyeLookDownLeft","eyeLookDownRight","eyeLookInLeft","eyeLookInRight","eyeLookOutLeft","eyeLookOutRight","eyeLookUpLeft","eyeLookUpRight","eyeSquintLeft","eyeSquintRight","eyeWideLeft","eyeWideRight","jawForward","jawLeft","jawRight","jawOpen","mouthClose","mouthFunnel","mouthPucker","mouthLeft","mouthRight","mouthSmileLeft","mouthSmileRight","mouthFrownLeft","mouthFrownRight","mouthDimpleLeft","mouthDimpleRight","mouthStretchLeft","mouthStretchRight","mouthRollLower","mouthRollUpper","mouthShrugLower","mouthShrugUpper","mouthPressLeft","mouthPressRight","mouthLowerDownLeft","mouthLowerDownRight","mouthUpperUpLeft","mouthUpperUpRight","browDownLeft","browDownRight","browInnerUp","browOuterUpLeft","browOuterUpRight","cheekPuff","cheekSquintLeft","cheekSquintRight","noseSneerLeft","noseSneerRight","tongueOut"]
VIS = ["viseme_sil","viseme_PP","viseme_FF","viseme_TH","viseme_DD","viseme_kk","viseme_CH","viseme_SS","viseme_nn","viseme_RR","viseme_aa","viseme_E","viseme_I","viseme_O","viseme_U"]
EXTRA = ["mouthOpen","mouthSmile","eyesClosed","eyesLookUp","eyesLookDown"]

def scan(p):
    try:
        f = open(p, "rb")
        f.read(12)
        clen, ct = struct.unpack("<II", f.read(8))
        g = json.loads(f.read(clen).decode())
        blen, bt = struct.unpack("<II", f.read(8))
        buf = f.read(blen)
    except Exception as e:
        return None
    names = set()
    verts = 0
    for m in g.get("meshes", []):
        for pr in m.get("primitives", []):
            acc = pr.get("attributes", {}).get("POSITION")
            if acc is not None:
                verts += g["accessors"][acc]["count"]
            for t in (m.get("extras", {}) or {}).get("targetNames", []) or []:
                names.add(t)
    roots = [g["nodes"][i].get("name") for i in g.get("scenes", [{}])[0].get("nodes", [])]
    joints = [len(s["joints"]) for s in g.get("skins", [])]
    bone_names = []
    if g.get("skins"):
        bone_names = [g["nodes"][n].get("name") or "" for n in g["skins"][0]["joints"]]
    imgs = g.get("images", [])
    img_bytes = 0
    for im in imgs:
        bv = im.get("bufferView")
        if bv is not None:
            img_bytes += g["bufferViews"][bv].get("byteLength", 0)
    mats = [m.get("name") for m in g.get("materials", [])]
    pbr = 0
    for m in g.get("materials", []):
        pm = m.get("pbrMetallicRoughness", {})
        if pm.get("baseColorTexture") or pm.get("metallicRoughnessTexture"):
            pbr += 1
        if m.get("normalTexture"):
            pbr += 1
    return {
        "file": os.path.basename(p), "size_mb": round(os.path.getsize(p)/1e6, 1),
        "roots": roots, "armature": "Armature" in roots,
        "joints": joints, "mixamo": any("mixamorig" in b.lower() for b in bone_names),
        "verts": verts, "arkit": len([n for n in names if n in ARKIT]),
        "vis": len([n for n in names if n in VIS]),
        "extra": len([n for n in names if n in EXTRA]),
        "morphs_total": len(names), "mats": len(mats), "imgs": len(imgs),
        "img_mb": round(img_bytes/1e6, 1), "pbr_slots": pbr,
    }

files = sorted(glob.glob("/opt/talkinghead/avatars/*.glb"))
rows = []
for p in files:
    r = scan(p)
    if r:
        rows.append(r)

hdr = f"{'file':42} {'root':9} {'J':>3} {'mix':>3} {'verts':>7} {'ARK':>3} {'vis':>3} {'ext':>3} {'tot':>4} {'mat':>3} {'imgMB':>6} {'MB':>6}"
print(hdr); print("-"*len(hdr))
for r in sorted(rows, key=lambda x: (-(x["arkit"]+x["vis"]), -x["mats"])):
    print(f"{r['file'][:42]:42} {str(r['roots'])[:9]:9} {r['joints'][0] if r['joints'] else 0:>3} "
          f"{'Y' if r['mixamo'] else '.':>3} {r['verts']:>7} {r['arkit']:>3} {r['vis']:>3} "
          f"{r['extra']:>3} {r['morphs_total']:>4} {r['mats']:>3} {r['img_mb']:>6} {r['size_mb']:>6}")
