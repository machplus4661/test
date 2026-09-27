#!/usr/bin/env python3
"""Betikleri denemek için küçük, rig'li, morph'lu, animasyonlu bir GLB üretir.

Gerçek karakter yerine geçmez; yalnızca araç zincirinin çalıştığını gösterir.
Kasıtlı olarak kol ağırlığını gövdeye taşırır ki agirlik_duzelt.py etkisi görülsün.
"""
import struct
import sys

import numpy as np
from pygltflib import (GLTF2, Accessor, Animation, AnimationChannel, AnimationChannelTarget, AnimationSampler,
                       Asset, Attributes, Buffer, BufferView, Mesh, Node, Primitive, Scene, Skin)

FLOAT, USHORT, UBYTE = 5126, 5123, 5121
ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER = 34962, 34963


def silindir(cx, r, y0, y1, seg=12, halka=8):
    V, F = [], []
    for j in range(halka):
        y = y0 + (y1 - y0) * j / (halka - 1)
        for i in range(seg):
            a = 2 * np.pi * i / seg
            V.append([cx + r * np.cos(a), y, r * np.sin(a)])
    for j in range(halka - 1):
        for i in range(seg):
            a, b = j * seg + i, j * seg + (i + 1) % seg
            c, d = a + seg, b + seg
            F += [[a, b, c], [b, d, c]]
    return np.array(V, np.float32), np.array(F, np.uint16)


def main(yol="girdi/ornek-rigli.glb"):
    gv, gf = silindir(0, 0.25, 0, 1.6, halka=16)         # gövde
    kv, kf = silindir(0.45, 0.08, 0.9, 1.5, halka=8)     # sağ kol (yukarı doğru)
    V = np.vstack([gv, kv]); F = np.vstack([gf, kf + len(gv)])
    n = len(V)
    UV = np.stack([(np.arctan2(V[:, 2], V[:, 0]) / (2 * np.pi) + 0.5), V[:, 1] / 1.6], 1).astype(np.float32)
    # kemikler: 0 kök(kalça) 1 omurga 2 sağ_omuz(kol)
    J = np.zeros((n, 4), np.uint8); W = np.zeros((n, 4), np.float32)
    for i, p in enumerate(V):
        if i >= len(gv):
            J[i, 0] = 2; W[i, 0] = 1.0
        else:
            t = np.clip(p[1] / 1.6, 0, 1)
            J[i, :2] = [0, 1]; W[i, :2] = [1 - t, t]
            if p[0] > 0.1 and 0.8 < p[1] < 1.5:  # kasıtlı hata: gövde köşeleri kol kemiğinden ağırlık alıyor
                J[i, 2] = 2; W[i, 2] = 0.5; W[i, :2] *= 0.5
    # morph: MouthOpen (üst ön köşeleri ileri it), Smile
    m1 = np.zeros_like(V); m2 = np.zeros_like(V)
    ust = (V[:, 1] > 1.4) & (V[:, 2] > 0.1) & (np.arange(n) < len(gv))
    m1[ust] = [0, -0.05, 0.05]; m2[ust] = [0.03, 0.02, 0]
    # animasyon: kol kemiği 1 sn içinde 90° kalkar
    zaman = np.array([0, 0.5, 1.0], np.float32)
    s = np.sin(np.radians([0, 45, 90]) / 2); c = np.cos(np.radians([0, 45, 90]) / 2)
    rot = np.stack([np.zeros(3), np.zeros(3), s, c], 1).astype(np.float32)
    ibm = np.array([np.eye(4).flatten()] * 3, np.float32)
    ibm[1][13] = -0.8; ibm[2][12] = -0.45; ibm[2][13] = -0.9

    parcalar = [V, F, UV, J, W, m1, m2, zaman, rot, ibm]
    blob = b""; bvs = []; accs = []
    for k, p in enumerate(parcalar):
        b = p.tobytes(); off = len(blob); blob += b + b"\0" * ((4 - len(b) % 4) % 4)
        bvs.append(BufferView(buffer=0, byteOffset=off, byteLength=len(b),
                              target=ELEMENT_ARRAY_BUFFER if k == 1 else (ARRAY_BUFFER if k < 7 else None)))
    def acc(k, ct, tp, cnt, mn=None, mx=None, norm=False):
        accs.append(Accessor(bufferView=k, componentType=ct, count=cnt, type=tp, min=mn, max=mx, normalized=norm)); return len(accs) - 1
    aV = acc(0, FLOAT, "VEC3", n, V.min(0).tolist(), V.max(0).tolist())
    aF = acc(1, USHORT, "SCALAR", F.size)
    aUV = acc(2, FLOAT, "VEC2", n); aJ = acc(3, UBYTE, "VEC4", n); aW = acc(4, FLOAT, "VEC4", n)
    aM1 = acc(5, FLOAT, "VEC3", n, m1.min(0).tolist(), m1.max(0).tolist()); aM2 = acc(6, FLOAT, "VEC3", n, m2.min(0).tolist(), m2.max(0).tolist())
    aT = acc(7, FLOAT, "SCALAR", 3, [0.0], [1.0]); aR = acc(8, FLOAT, "VEC4", 3); aI = acc(9, FLOAT, "MAT4", 3)

    g = GLTF2(asset=Asset(version="2.0"), buffers=[Buffer(byteLength=len(blob))], bufferViews=bvs, accessors=accs)
    g.meshes = [Mesh(name="ornek_govde", primitives=[Primitive(attributes=Attributes(POSITION=aV, TEXCOORD_0=aUV, JOINTS_0=aJ, WEIGHTS_0=aW), indices=aF,
                     targets=[{"POSITION": aM1}, {"POSITION": aM2}])], weights=[0, 0], extras={"targetNames": ["MouthOpen", "Smile"]})]
    g.nodes = [Node(name="Armature", children=[1, 4]), Node(name="Hips", translation=[0, 0, 0], children=[2]),
               Node(name="Spine", translation=[0, 0.8, 0], children=[3]), Node(name="RightArm", translation=[0.45, 0.1, 0]),
               Node(name="Karakter", mesh=0, skin=0)]
    g.skins = [Skin(name="Rig", joints=[1, 2, 3], inverseBindMatrices=aI, skeleton=1)]
    g.animations = [Animation(name="selam", samplers=[AnimationSampler(input=aT, output=aR, interpolation="LINEAR")],
                              channels=[AnimationChannel(sampler=0, target=AnimationChannelTarget(node=3, path="rotation"))]),
                    Animation(name="bekleme", samplers=[AnimationSampler(input=aT, output=aR, interpolation="LINEAR")],
                              channels=[AnimationChannel(sampler=0, target=AnimationChannelTarget(node=3, path="rotation"))])]
    g.scenes = [Scene(nodes=[0])]; g.scene = 0
    g.set_binary_blob(blob); g.save(yol)
    print("→", yol)


if __name__ == "__main__":
    main(*sys.argv[1:])
