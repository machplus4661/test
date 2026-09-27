#!/usr/bin/env -S blender -b -P
"""Muhammed'i sıfırdan, prosedürel olarak üretir (Blender 4.2, headless).

Çalıştırma:
    blender -b -P araclar/blender_modelle.py -- --cikti cikti/mm-asistan-muhammed.glb

Adımlar:
 1. Metaball'lardan stilize insan gövdesi → tek birleşik ağ, ~14k üçgen
 2. Smart UV + numpy ile doku (ten, saç, sakal, gözler, kaş, ağız, gömlek, pantolon, ayakkabı)
 3. Yüz shape key'leri: MouthOpen, Smile, MouthPucker, BlinkL, BlinkR, BrowUp
 4. 25 kemikli iskelet, bone-heat otomatik ağırlık
 5. 15 klip (klipler.json'daki glb_adi listesi) NLA track olarak
 6. GLB dışa aktarma (Y-up, JPEG doku)

Koordinatlar Blender'a göre: Z yukarı, karakter -Y yönüne bakar (glTF'te +Z olur).
Karakterin sağı -X, solu +X.
"""
import math
import os
import sys
import time

import bpy
import numpy as np
from mathutils import Quaternion, Vector

# ----------------------------------------------------------------------------
# Parametreler
# ----------------------------------------------------------------------------
BOY = 1.75
FPS = 30
DOKU_BOYUT = 2048
HEDEF_UCGEN = 14000

RENK = {  # sRGB 0-1
    "ten": (0.86, 0.66, 0.52),
    "ten_golge": (0.70, 0.50, 0.38),
    "sac": (0.13, 0.09, 0.06),
    "sakal": (0.30, 0.21, 0.15),
    "goz_beyaz": (0.96, 0.96, 0.94),
    "iris": (0.30, 0.18, 0.10),
    "gobek": (0.02, 0.02, 0.02),
    "kas": (0.12, 0.08, 0.05),
    "dudak": (0.62, 0.38, 0.34),
    "dudak_cizgi": (0.30, 0.15, 0.13),
    "gomlek": (0.11, 0.42, 0.45),
    "gomlek_koyu": (0.07, 0.30, 0.33),
    "pantolon": (0.74, 0.64, 0.47),
    "pantolon_koyu": (0.55, 0.46, 0.32),
    "kemer": (0.25, 0.15, 0.08),
    "ayakkabi": (0.36, 0.20, 0.10),
    "ayakkabi_taban": (0.15, 0.10, 0.07),
}

# Anatomik noktalar (metre)
KAFA = Vector((0, 0, 1.60)); KAFA_R = 0.118
BOYUN_ALT, BOYUN_UST = 1.455, 1.52
OMUZ = (0.205, 1.425)
DIRSEK = (0.245, 1.17)
BILEK = (0.262, 0.93)
EL = (0.265, 0.86)
KALCA = (0.095, 0.90)
DIZ = (0.095, 0.49)
AYAK_BILEK = (0.095, 0.10)
GOZ = (0.037, -0.097, 1.607)   # sol göz (+x); sağ göz x'i negatif
AGIZ = (0.0, -0.104, 1.537)
BURUN = (0.0, -0.112, 1.578)
KAS_Z = 1.632

CIKTI = "cikti/mm-asistan-muhammed.glb"
if "--" in sys.argv:
    a = sys.argv[sys.argv.index("--") + 1:]
    if "--cikti" in a:
        CIKTI = a[a.index("--cikti") + 1]
    if "--ucgen" in a:
        HEDEF_UCGEN = int(a[a.index("--ucgen") + 1])
CIKTI = os.path.abspath(CIKTI)
KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def log(*a):
    print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)


# ----------------------------------------------------------------------------
# 1. Gövde: metaball
# ----------------------------------------------------------------------------
def sahne_temizle():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.fps = FPS
    bpy.context.scene.frame_start = 1


def metaball_govde():
    mb = bpy.data.metaballs.new("MuhammedMB")
    mb.resolution = 0.018
    mb.threshold = 0.3
    K = 1.28  # eşik 0.3 → görünen yarıçap ≈ 0.78 r; telafi

    def top(co, r, st=2.0):
        e = mb.elements.new(); e.type = "BALL"; e.co = Vector(co); e.radius = r * K; e.stiffness = st
        return e

    def elips(co, r, sx, sy, sz, st=2.0):
        e = mb.elements.new(); e.type = "ELLIPSOID"; e.co = Vector(co); e.radius = r * K
        e.size_x, e.size_y, e.size_z = sx, sy, sz; e.stiffness = st
        return e

    def kapsul(a, b, r, st=2.0):
        a, b = Vector(a), Vector(b)
        d = b - a
        e = mb.elements.new(); e.type = "CAPSULE"; e.co = (a + b) / 2; e.radius = r * K
        e.size_x = d.length / 2
        e.rotation = Vector((1, 0, 0)).rotation_difference(d.normalized())
        e.stiffness = st
        return e

    # kafa + saç kabarıklığı + kulak + burun
    elips(KAFA, KAFA_R, 0.95, 1.0, 1.12)
    elips((0, 0.012, 1.645), KAFA_R * 0.98, 1.02, 1.0, 1.0)     # saç hacmi (arka/üst)
    elips((0, -0.02, 1.53), 0.075, 1.05, 0.9, 0.8)               # çene
    for s in (-1, 1):
        elips((s * 0.108, 0.005, 1.60), 0.024, 0.55, 1.0, 1.15, st=3)  # kulak
    elips(BURUN, 0.016, 0.8, 1.0, 0.9, st=2)                     # burun
    # boyun
    kapsul((0, 0.005, BOYUN_ALT - 0.02), (0, 0.005, BOYUN_UST + 0.02), 0.047)
    # gövde
    elips((0, 0.0, 1.33), 0.17, 1.22, 0.82, 0.95)   # göğüs
    elips((0, 0.0, 1.16), 0.155, 1.05, 0.82, 0.85)  # karın
    elips((0, 0.0, 0.97), 0.15, 1.12, 0.85, 0.75)   # kalça
    for s in (-1, 1):
        top((s * 0.185, 0.0, 1.405), 0.048)                           # omuz
        kapsul((s * OMUZ[0], 0, OMUZ[1]), (s * DIRSEK[0], 0.01, DIRSEK[1]), 0.05)     # üst kol
        kapsul((s * DIRSEK[0], 0.01, DIRSEK[1]), (s * BILEK[0], 0.0, BILEK[1]), 0.043)  # ön kol
        elips((s * EL[0], -0.005, EL[1]), 0.045, 0.75, 0.5, 1.1)      # el
        kapsul((s * KALCA[0], 0, KALCA[1]), (s * DIZ[0], 0, DIZ[1]), 0.078)  # üst bacak
        kapsul((s * DIZ[0], 0, DIZ[1]), (s * AYAK_BILEK[0], 0, AYAK_BILEK[1]), 0.058)  # alt bacak
        elips((s * 0.095, -0.04, 0.045), 0.055, 0.85, 1.9, 0.7, st=3)  # ayakkabı
    ob = bpy.data.objects.new("MuhammedMB", mb)
    bpy.context.collection.objects.link(ob)
    return ob


def metaball_to_mesh(mb_ob):
    bpy.context.view_layer.objects.active = mb_ob
    mb_ob.select_set(True)
    bpy.ops.object.convert(target="MESH")
    ob = bpy.context.view_layer.objects.active
    ob.name = "Muhammed"
    ob.data.name = "Muhammed"
    # yalnızca en büyük parçayı tut (metaball nadiren ufak adacık bırakır)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=0.0005)
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    # decimate
    n = len(ob.data.polygons) * 2  # metaball çıktısı dörtgen ağırlıklı
    oran = min(1.0, HEDEF_UCGEN / max(n, 1))
    m = ob.modifiers.new("dec", "DECIMATE"); m.ratio = oran; m.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier="dec")
    m = ob.modifiers.new("tri", "TRIANGULATE")
    bpy.ops.object.modifier_apply(modifier="tri")
    bpy.ops.object.shade_smooth()
    # ayakları z=0'a oturt, x'i ortala
    xs = [v.co.x for v in ob.data.vertices]; zs = [v.co.z for v in ob.data.vertices]
    dz = min(zs); dx = (max(xs) + min(xs)) / 2
    for v in ob.data.vertices:
        v.co.x -= dx; v.co.z -= dz
    log(f"ağ: {len(ob.data.vertices)} köşe, {len(ob.data.polygons)} üçgen, boy {max(zs)-min(zs):.3f}")
    return ob


# ----------------------------------------------------------------------------
# 2. UV + doku
# ----------------------------------------------------------------------------
def uv_ac(ob):
    bpy.context.view_layer.objects.active = ob
    if not ob.data.uv_layers:
        ob.data.uv_layers.new(name="UVMap")
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.004, correct_aspect=True, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")


def renk_fonksiyonu(P):
    """P: (N,3) dünya konumu → (N,3) renk. Tamamen konum tabanlı; UV adacığından bağımsız."""
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    N = len(P)
    C = np.tile(np.array(RENK["ten"]), (N, 1))
    rnd = np.random.default_rng(7).random(N)

    def boya(maske, renk):
        C[maske] = np.array(renk)

    def karistir(maske, renk, t):
        if isinstance(t, np.ndarray):
            t = t[maske][:, None]
        C[maske] = C[maske] * (1 - t) + np.array(renk) * t

    kafa_d = np.linalg.norm(P - np.array([KAFA.x, KAFA.y, KAFA.z]), axis=1)
    kafada = (kafa_d < KAFA_R * 1.45) & (z > 1.49)
    on = y < -0.03

    # --- kıyafet ---
    govde = (z < 1.455) & (z > 0.945)
    kol = (np.abs(x) > 0.145) & (z > 0.85) & (z < 1.47)
    gomlek = (govde | kol) & ~(kafada)
    el = (np.abs(x) > 0.2) & (z < 0.885)
    gomlek &= ~el
    boya(gomlek, RENK["gomlek"])
    # yaka: boyun etrafı V
    yaka = gomlek & (z > 1.40) & (np.abs(x) < 0.07) & on & (z > 1.40 + np.abs(x) * 0.6)
    karistir(yaka, RENK["gomlek_koyu"], 0.6)
    # pat (düğme şeridi)
    pat = gomlek & on & (np.abs(x) < 0.008) & (z > 1.20) & (z < 1.42)
    karistir(pat, RENK["gomlek_koyu"], 0.7)
    for zb in (1.24, 1.30, 1.36):
        dugme = gomlek & on & (np.hypot(x, (z - zb) * 1.0) < 0.007)
        boya(dugme, (0.85, 0.85, 0.8))
    # cep
    cep = gomlek & on & (x > 0.06) & (x < 0.14) & (z > 1.27) & (z < 1.36)
    cep_kenar = cep & ((x < 0.066) | (x > 0.134) | (z < 1.276) | (z > 1.354))
    karistir(cep_kenar, RENK["gomlek_koyu"], 0.8)
    # kol manşeti
    manset = gomlek & (np.abs(x) > 0.2) & (z < 0.93)
    karistir(manset, RENK["gomlek_koyu"], 0.5)
    # pantolon
    pantolon = (z <= 0.945) & (z > 0.075) & ~el
    boya(pantolon, RENK["pantolon"])
    dikis = pantolon & (np.abs(np.abs(x) - 0.095) < 0.004) & (y > 0.02)
    karistir(dikis, RENK["pantolon_koyu"], 0.6)
    kemer = (z <= 0.945) & (z > 0.915) & ~el
    boya(kemer, RENK["kemer"])
    toka = kemer & on & (np.abs(x) < 0.02)
    boya(toka, (0.75, 0.70, 0.55))
    # ayakkabı
    ayakkabi = z <= 0.075
    boya(ayakkabi, RENK["ayakkabi"])
    boya(ayakkabi & (z < 0.018), RENK["ayakkabi_taban"])

    # --- saç ---
    on_kafa = y < -0.02
    sac = kafada & (
        (z > 1.672) |                                   # tepe
        ((y > 0.035) & (z > 1.54)) |                    # arka
        ((np.abs(x) > 0.088) & (z > 1.605) & (y > -0.06)) |  # yanlar
        ((z > 1.660 - 0.25 * np.abs(x)) & on_kafa & (np.abs(x) < 0.09))  # ön saç çizgisi hafif M
    )
    # kulakları saçtan çıkar
    kulak = (np.abs(x) > 0.095) & (z > 1.565) & (z < 1.635) & (np.abs(y) < 0.03)
    sac &= ~kulak
    boya(sac, RENK["sac"])
    karistir(sac, (0.22, 0.16, 0.11), (rnd * 0.35))
    # favori
    favori = kafada & (np.abs(x) > 0.09) & (z > 1.54) & (z < 1.61) & (y > -0.045) & (y < 0.0) & ~kulak
    karistir(favori, RENK["sac"], 0.8)

    # --- sakal (hafif) ---
    # sakal: çene çizgisinden yanağa doğru yumuşak geçiş
    sinir = 1.566 - 0.30 * np.abs(x) + 0.35 * np.clip(-y - 0.06, 0, 1)  # yanakta aşağı, ön çenede yukarı
    t_sakal = np.clip((sinir - z) / 0.018, 0, 1) * np.clip((z - 1.478) / 0.015, 0, 1)
    sakal = kafada & (y < 0.005) & (t_sakal > 0) & ~kulak
    agiz_cevre = (np.hypot((x - AGIZ[0]) / 0.045, (z - AGIZ[2]) / 0.02) < 1.0) & (y < -0.06)
    bıyık = (np.hypot((x - AGIZ[0]) / 0.045, (z - AGIZ[2] - 0.018) / 0.009) < 1.0) & (y < -0.06)
    sakal &= ~agiz_cevre
    karistir(sakal, RENK["sakal"], (0.55 + rnd * 0.2) * t_sakal)
    karistir(bıyık, RENK["sakal"], 0.7)

    # --- yüz detayları (ön yarı) ---
    yuz = (y < -0.05) & kafada
    # kaşlar
    for s in (-1, 1):
        kx = s * 0.040
        kas = yuz & (np.abs(x - kx) < 0.022) & (np.abs(z - (KAS_Z + 0.004 - 0.12 * np.abs(x - kx))) < 0.0045)
        boya(kas, RENK["kas"])
    # gözler
    for s in (-1, 1):
        ex, ez = s * GOZ[0], GOZ[2]
        goz = yuz & (np.hypot((x - ex) / 0.017, (z - ez) / 0.0095) < 1.0)
        boya(goz, RENK["goz_beyaz"])
        iris = yuz & (np.hypot((x - ex - s * 0.001) / 0.0085, (z - ez) / 0.0085) < 1.0)
        boya(iris, RENK["iris"])
        gob = yuz & (np.hypot(x - ex - s * 0.001, z - ez) < 0.0038)
        boya(gob, RENK["gobek"])
        parlak = yuz & (np.hypot(x - ex - s * 0.001 - 0.003, z - ez - 0.003) < 0.0016)
        boya(parlak, (1, 1, 1))
        # üst göz kapağı çizgisi
        kapak = yuz & (np.hypot((x - ex) / 0.018, (z - ez - 0.004) / 0.011) < 1.0) & (np.hypot((x - ex) / 0.017, (z - ez) / 0.0095) >= 1.0) & (z > ez)
        karistir(kapak, RENK["ten_golge"], 0.7)
    # ağız
    dudak = yuz & (np.hypot((x - AGIZ[0]) / 0.031, (z - AGIZ[2]) / 0.0075) < 1.0)
    boya(dudak, RENK["dudak"])
    cizgi = yuz & (np.abs(x) < 0.028 - 0.0 * np.abs(z)) & (np.abs(z - AGIZ[2] - 0.0005) < 0.0022 * (1 - (x / 0.03) ** 2) ** 0.5 + 1e-9)
    boya(cizgi, RENK["dudak_cizgi"])
    # burun delikleri gölgesi
    for s in (-1, 1):
        delik = yuz & (np.hypot((x - s * 0.011) / 0.006, (z - (BURUN[2] - 0.016)) / 0.004) < 1.0)
        karistir(delik, RENK["ten_golge"], 0.6)

    # hafif kumaş/ten dokusu
    C *= (0.96 + 0.08 * rnd)[:, None]
    return np.clip(C, 0, 1)


def doku_uret(ob, yol):
    """UV üçgenlerini rasterize eder, her piksel için 3D konumu bulur, renk_fonksiyonu ile boyar."""
    me = ob.data
    uvl = me.uv_layers.active.data
    S = DOKU_BOYUT
    T = len(me.polygons)
    uv = np.empty((T, 3, 2)); pos = np.empty((T, 3, 3))
    vco = np.array([v.co[:] for v in me.vertices])
    for i, p in enumerate(me.polygons):
        for k, li in enumerate(p.loop_indices):
            uv[i, k] = uvl[li].uv[:]
            pos[i, k] = vco[me.loops[li].vertex_index]
    uvp = uv * S  # piksel
    img_pos = np.zeros((S, S, 3)); mask = np.zeros((S, S), bool)
    for i in range(T):
        a, b, c = uvp[i]
        x0, x1 = int(max(0, np.floor(min(a[0], b[0], c[0]) - 1))), int(min(S - 1, np.ceil(max(a[0], b[0], c[0]) + 1)))
        y0, y1 = int(max(0, np.floor(min(a[1], b[1], c[1]) - 1))), int(min(S - 1, np.ceil(max(a[1], b[1], c[1]) + 1)))
        if x1 < x0 or y1 < y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        det = (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])
        if abs(det) < 1e-9:
            continue
        l1 = ((gx - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (gy - a[1])) / det
        l2 = ((b[0] - a[0]) * (gy - a[1]) - (gx - a[0]) * (b[1] - a[1])) / det
        l0 = 1 - l1 - l2
        eps = -0.02  # hafif taşma, dikiş boşluklarını azaltır
        m = (l0 >= eps) & (l1 >= eps) & (l2 >= eps)
        if not m.any():
            continue
        Pp = l0[..., None] * pos[i, 0] + l1[..., None] * pos[i, 1] + l2[..., None] * pos[i, 2]
        sub_pos = img_pos[y0:y1 + 1, x0:x1 + 1]; sub_mask = mask[y0:y1 + 1, x0:x1 + 1]
        yeni = m & ~sub_mask
        sub_pos[yeni] = Pp[yeni]; sub_mask |= m
    log(f"doku: {mask.mean()*100:.1f}% UV kapsama")
    C = np.zeros((S, S, 3))
    C[mask] = renk_fonksiyonu(img_pos[mask])
    # adacık dışına renk taşır (dilate) → dikişlerde siyah çizgi olmaz
    for _ in range(10):
        bos = ~mask
        acc = np.zeros_like(C); cnt = np.zeros((S, S))
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            sm = np.roll(mask, (dy, dx), (0, 1)); sc = np.roll(C, (dy, dx), (0, 1))
            acc += sc * sm[..., None]; cnt += sm
        dolu = bos & (cnt > 0)
        C[dolu] = acc[dolu] / cnt[dolu][:, None]
        mask = mask | dolu
    C[~mask] = np.array(RENK["ten"])
    img = bpy.data.images.new("MuhammedDoku", S, S, alpha=False)
    rgba = np.concatenate([C, np.ones((S, S, 1))], axis=2)
    img.pixels = rgba.ravel().tolist()
    img.filepath_raw = yol; img.file_format = "PNG"; img.save()
    return img


def malzeme(ob, img):
    mat = bpy.data.materials.new("MuhammedMat"); mat.use_nodes = True
    nt = mat.node_tree; bsdf = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexImage"); tex.image = img
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.85
    bsdf.inputs["Specular IOR Level"].default_value = 0.2
    ob.data.materials.append(mat)


# ----------------------------------------------------------------------------
# 3. Shape key'ler
# ----------------------------------------------------------------------------
def shape_keyler(ob):
    me = ob.data
    ob.shape_key_add(name="Basis", from_mix=False)
    co = np.array([v.co[:] for v in me.vertices])
    x, y, z = co[:, 0], co[:, 1], co[:, 2]
    on = y < -0.045

    def gauss(cx, cy, cz, rx, ry, rz):
        d = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 + ((z - cz) / rz) ** 2
        return np.exp(-d * 1.2) * (d < 4)

    def ekle(ad, delta):
        k = ob.shape_key_add(name=ad, from_mix=False)
        for i in range(len(me.vertices)):
            if abs(delta[i]).sum() > 0:
                k.data[i].co = Vector(co[i] + delta[i])
        k.slider_max = 1.0

    d = np.zeros_like(co)
    w = gauss(0, AGIZ[1], AGIZ[2] - 0.012, 0.05, 0.05, 0.035) * on * (z < AGIZ[2] + 0.004)
    d[:, 2] = -0.022 * w; d[:, 1] = 0.006 * w
    ekle("MouthOpen", d)

    d = np.zeros_like(co)
    for s in (-1, 1):
        w = gauss(s * 0.03, AGIZ[1], AGIZ[2], 0.02, 0.05, 0.02) * on
        d[:, 2] += 0.012 * w; d[:, 0] += s * 0.008 * w
    ekle("Smile", d)

    d = np.zeros_like(co)
    w = gauss(0, AGIZ[1], AGIZ[2], 0.04, 0.05, 0.022) * on
    d[:, 0] = -x * 0.4 * w; d[:, 1] = -0.012 * w
    ekle("MouthPucker", d)

    for ad, s in (("BlinkL", 1), ("BlinkR", -1)):
        d = np.zeros_like(co)
        w = gauss(s * GOZ[0], GOZ[1], GOZ[2], 0.024, 0.04, 0.016) * on
        d[:, 2] = -(z - GOZ[2]) * 0.85 * w
        ekle(ad, d)

    d = np.zeros_like(co)
    w = gauss(0, -0.09, KAS_Z, 0.07, 0.05, 0.02) * on
    d[:, 2] = 0.008 * w
    ekle("BrowUp", d)
    log("shape key:", [k.name for k in me.shape_keys.key_blocks][1:])


# ----------------------------------------------------------------------------
# 4. İskelet
# ----------------------------------------------------------------------------
KEMIKLER = [
    # ad, ebeveyn, baş, kuyruk, deform
    ("Hips", None, (0, 0, 0.95), (0, 0, 1.06), True),
    ("Spine", "Hips", (0, 0, 1.06), (0, 0, 1.20), True),
    ("Spine1", "Spine", (0, 0, 1.20), (0, 0, 1.34), True),
    ("Spine2", "Spine1", (0, 0, 1.34), (0, 0, 1.455), True),
    ("Neck", "Spine2", (0, 0.005, 1.455), (0, 0.005, 1.525), True),
    ("Head", "Neck", (0, 0.005, 1.525), (0, 0.005, 1.72), True),
    ("Jaw", "Head", (0, 0.0, 1.55), (0, -0.09, 1.52), False),
    ("EyeL", "Head", (0.037, -0.08, 1.607), (0.037, -0.11, 1.607), False),
    ("EyeR", "Head", (-0.037, -0.08, 1.607), (-0.037, -0.11, 1.607), False),
]
for ad, s in (("L", 1), ("R", -1)):
    KEMIKLER += [
        (f"Shoulder{ad}", "Spine2", (s * 0.03, 0, 1.43), (s * OMUZ[0], 0, OMUZ[1]), True),
        (f"Arm{ad}", f"Shoulder{ad}", (s * OMUZ[0], 0, OMUZ[1]), (s * DIRSEK[0], 0.01, DIRSEK[1]), True),
        (f"ForeArm{ad}", f"Arm{ad}", (s * DIRSEK[0], 0.01, DIRSEK[1]), (s * BILEK[0], 0, BILEK[1]), True),
        (f"Hand{ad}", f"ForeArm{ad}", (s * BILEK[0], 0, BILEK[1]), (s * EL[0], -0.005, EL[1] - 0.06), True),
        (f"UpLeg{ad}", "Hips", (s * KALCA[0], 0, KALCA[1]), (s * DIZ[0], 0, DIZ[1]), True),
        (f"Leg{ad}", f"UpLeg{ad}", (s * DIZ[0], 0, DIZ[1]), (s * AYAK_BILEK[0], 0, AYAK_BILEK[1]), True),
        (f"Foot{ad}", f"Leg{ad}", (s * AYAK_BILEK[0], 0, AYAK_BILEK[1]), (s * 0.095, -0.09, 0.03), True),
        (f"Toe{ad}", f"Foot{ad}", (s * 0.095, -0.09, 0.03), (s * 0.095, -0.15, 0.02), True),
    ]


def iskelet(ob):
    arm = bpy.data.armatures.new("Armature")
    arm_ob = bpy.data.objects.new("Armature", arm)
    bpy.context.collection.objects.link(arm_ob)
    bpy.context.view_layer.objects.active = arm_ob
    bpy.ops.object.mode_set(mode="EDIT")
    eb = {}
    for ad, ebv, bas, kuy, deform in KEMIKLER:
        b = arm.edit_bones.new(ad); b.head = Vector(bas); b.tail = Vector(kuy); b.use_deform = deform
        if ebv:
            b.parent = eb[ebv]; b.use_connect = False
        eb[ad] = b
    bpy.ops.object.mode_set(mode="OBJECT")
    # bone heat ağırlık
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True); arm_ob.select_set(True)
    bpy.context.view_layer.objects.active = arm_ob
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    # deform olmayan kemiklerin grubu varsa sil
    for ad, _, _, _, deform in KEMIKLER:
        if not deform and ad in ob.vertex_groups:
            ob.vertex_groups.remove(ob.vertex_groups[ad])
    log(f"iskelet: {len(arm.bones)} kemik, {sum(1 for k in KEMIKLER if k[4])} deform")
    return arm_ob


# ----------------------------------------------------------------------------
# 5. Animasyon
# ----------------------------------------------------------------------------
def _rest_rot(arm_ob, ad):
    return arm_ob.data.bones[ad].matrix_local.to_quaternion()


def poz(arm_ob, kare, donmeler, hips_konum=None):
    """donmeler: {kemik: [(eksen_dunya, derece), ...]} — rest pozundaki dünya eksenine göre."""
    for ad, liste in donmeler.items():
        pb = arm_ob.pose.bones[ad]; pb.rotation_mode = "QUATERNION"
        q = Quaternion((1, 0, 0, 0))
        for eksen, der in liste:
            q = q @ Quaternion(Vector(eksen), math.radians(der))
        r = _rest_rot(arm_ob, ad)
        pb.rotation_quaternion = r.inverted() @ q @ r
        pb.keyframe_insert("rotation_quaternion", frame=kare)
    if hips_konum is not None:
        pb = arm_ob.pose.bones["Hips"]
        r = _rest_rot(arm_ob, "Hips")
        pb.location = r.inverted() @ Vector(hips_konum)
        pb.keyframe_insert("location", frame=kare)


def sifirla(arm_ob, kare):
    d = {b.name: [] for b in arm_ob.pose.bones}
    poz(arm_ob, kare, d, (0, 0, 0))


X, Y, Z = (1, 0, 0), (0, 1, 0), (0, 0, 1)


def klip_tanimlari():
    """Her klip: (ad, süre_sn, [(t_oran, donmeler, hips), ...]). t_oran 0..1."""
    K = {}
    # Idle: nefes + hafif sallanma (4 sn döngü)
    K["Idle"] = (4.0, [
        (0.0, {"Spine1": [(X, 0)], "Spine2": [(X, 0)], "Head": [(X, 0)], "ArmL": [(Y, -14)], "ArmR": [(Y, 14)]}, (0, 0, 0)),
        (0.5, {"Spine1": [(X, 1.5)], "Spine2": [(X, -2.5)], "Head": [(X, 1.5)], "ArmL": [(Y, -15.5)], "ArmR": [(Y, 15.5)]}, (0, 0, -0.004)),
        (1.0, {"Spine1": [(X, 0)], "Spine2": [(X, 0)], "Head": [(X, 0)], "ArmL": [(Y, -14)], "ArmR": [(Y, 14)]}, (0, 0, 0)),
    ])
    # IdleBakin: etrafa bakınma
    K["IdleBakin"] = (3.5, [
        (0.0, {"Head": [(Z, 0)], "Neck": [(Z, 0)], "ArmL": [(Y, -14)], "ArmR": [(Y, 14)]}, None),
        (0.25, {"Head": [(Z, 28), (X, -3)], "Neck": [(Z, 8)]}, None),
        (0.45, {"Head": [(Z, 28), (X, -3)], "Neck": [(Z, 8)]}, None),
        (0.7, {"Head": [(Z, -30), (X, 2)], "Neck": [(Z, -8)]}, None),
        (0.85, {"Head": [(Z, -30), (X, 2)], "Neck": [(Z, -8)]}, None),
        (1.0, {"Head": [(Z, 0)], "Neck": [(Z, 0)]}, None),
    ])
    # IdleCeket: iki el yakayı düzeltir
    K["IdleCeket"] = (3.0, [
        (0.0, {"ArmL": [(Y, -14)], "ArmR": [(Y, 14)], "ForeArmL": [], "ForeArmR": [], "Head": []}, None),
        (0.3, {"ArmL": [(Y, -20), (X, -25)], "ArmR": [(Y, 20), (X, -25)], "ForeArmL": [(X, -120), (Z, 35)], "ForeArmR": [(X, -120), (Z, -35)], "Head": [(X, 8)]}, None),
        (0.5, {"ArmL": [(Y, -22), (X, -20)], "ArmR": [(Y, 22), (X, -20)], "ForeArmL": [(X, -125), (Z, 30)], "ForeArmR": [(X, -125), (Z, -30)], "Head": [(X, 10)]}, None),
        (0.7, {"ArmL": [(Y, -20), (X, -25)], "ArmR": [(Y, 20), (X, -25)], "ForeArmL": [(X, -120), (Z, 35)], "ForeArmR": [(X, -120), (Z, -35)], "Head": [(X, 8)]}, None),
        (1.0, {"ArmL": [(Y, -14)], "ArmR": [(Y, 14)], "ForeArmL": [], "ForeArmR": [], "Head": []}, None),
    ])
    # IdleSaat: sol bileğe bakar
    K["IdleSaat"] = (3.0, [
        (0.0, {"ArmL": [(Y, -14)], "ArmR": [(Y, 14)], "ForeArmL": [], "HandL": [], "Head": []}, None),
        (0.3, {"ArmL": [(Y, -10), (X, -30)], "ForeArmL": [(X, -95), (Z, 40)], "HandL": [(Y, -40)], "Head": [(X, 22), (Z, 12)]}, None),
        (0.7, {"ArmL": [(Y, -10), (X, -30)], "ForeArmL": [(X, -95), (Z, 40)], "HandL": [(Y, -40)], "Head": [(X, 22), (Z, 12)]}, None),
        (1.0, {"ArmL": [(Y, -14)], "ForeArmL": [], "HandL": [], "Head": []}, None),
    ])
    # Gulumse: baş hafif yana, omuzlar yukarı (yüz morph'u uygulama tarafında)
    K["Gulumse"] = (2.0, [
        (0.0, {"Head": [], "ShoulderL": [], "ShoulderR": [], "ArmL": [(Y, -14)], "ArmR": [(Y, 14)]}, None),
        (0.4, {"Head": [(Y, -7), (X, -3)], "ShoulderL": [(Y, -6)], "ShoulderR": [(Y, 6)]}, None),
        (0.7, {"Head": [(Y, -7), (X, -3)], "ShoulderL": [(Y, -6)], "ShoulderR": [(Y, 6)]}, None),
        (1.0, {"Head": [], "ShoulderL": [], "ShoulderR": []}, None),
    ])
    # Jump
    K["Jump"] = (1.3, [
        (0.0, {"UpLegL": [], "UpLegR": [], "LegL": [], "LegR": [], "Spine1": [], "ArmL": [(Y, -14)], "ArmR": [(Y, 14)]}, (0, 0, 0)),
        (0.25, {"UpLegL": [(X, -45)], "UpLegR": [(X, -45)], "LegL": [(X, 70)], "LegR": [(X, 70)], "Spine1": [(X, 15)], "ArmL": [(Y, -14), (X, 30)], "ArmR": [(Y, 14), (X, 30)]}, (0, 0, -0.22)),
        (0.5, {"UpLegL": [(X, -5)], "UpLegR": [(X, -5)], "LegL": [(X, 8)], "LegR": [(X, 8)], "Spine1": [(X, -5)], "ArmL": [(Y, -60), (X, -40)], "ArmR": [(Y, 60), (X, -40)]}, (0, 0, 0.30)),
        (0.75, {"UpLegL": [(X, -35)], "UpLegR": [(X, -35)], "LegL": [(X, 55)], "LegR": [(X, 55)], "Spine1": [(X, 10)], "ArmL": [(Y, -20), (X, 10)], "ArmR": [(Y, 20), (X, 10)]}, (0, 0, -0.16)),
        (1.0, {"UpLegL": [], "UpLegR": [], "LegL": [], "LegR": [], "Spine1": [], "ArmL": [(Y, -14)], "ArmR": [(Y, 14)]}, (0, 0, 0)),
    ])
    # KafaVurma: hayır (baş iki yana)
    K["KafaVurma"] = (1.2, [
        (0.0, {"Head": [], "ArmL": [(Y, -14)], "ArmR": [(Y, 14)]}, None),
        (0.2, {"Head": [(Z, 22)]}, None), (0.45, {"Head": [(Z, -22)]}, None),
        (0.7, {"Head": [(Z, 18)]}, None), (0.9, {"Head": [(Z, -12)]}, None), (1.0, {"Head": []}, None),
    ])
    # Sasir: geri çekilme, eller açık
    K["Sasir"] = (1.6, [
        (0.0, {"Head": [], "Spine1": [], "ArmL": [(Y, -14)], "ArmR": [(Y, 14)], "ForeArmL": [], "ForeArmR": []}, (0, 0, 0)),
        (0.25, {"Head": [(X, -14)], "Spine1": [(X, -10)], "ArmL": [(Y, -50), (X, -20)], "ArmR": [(Y, 50), (X, -20)], "ForeArmL": [(X, -70)], "ForeArmR": [(X, -70)]}, (0, 0.03, -0.01)),
        (0.6, {"Head": [(X, -12)], "Spine1": [(X, -8)], "ArmL": [(Y, -48), (X, -18)], "ArmR": [(Y, 48), (X, -18)], "ForeArmL": [(X, -65)], "ForeArmR": [(X, -65)]}, (0, 0.03, -0.01)),
        (1.0, {"Head": [], "Spine1": [], "ArmL": [(Y, -14)], "ArmR": [(Y, 14)], "ForeArmL": [], "ForeArmR": []}, (0, 0, 0)),
    ])
    # Talk: baş küçük hareketler, sağ el jest
    K["Talk"] = (3.0, [
        (0.0, {"Head": [], "ArmL": [(Y, -14)], "ArmR": [(Y, 14)], "ForeArmR": [(X, -50)], "HandR": []}, None),
        (0.2, {"Head": [(X, 4), (Z, 5)], "ArmR": [(Y, 22), (X, -10)], "ForeArmR": [(X, -80), (Z, -20)], "HandR": [(Z, 15)]}, None),
        (0.45, {"Head": [(X, -2), (Z, -4)], "ArmR": [(Y, 16)], "ForeArmR": [(X, -60), (Z, 10)], "HandR": [(Z, -10)]}, None),
        (0.7, {"Head": [(X, 3), (Z, 3)], "ArmR": [(Y, 24), (X, -14)], "ForeArmR": [(X, -85), (Z, -25)], "HandR": [(Z, 20)]}, None),
        (1.0, {"Head": [], "ArmR": [(Y, 14)], "ForeArmR": [(X, -50)], "HandR": []}, None),
    ])
    # Tikla: öne uzanıp dokunma
    K["Tikla"] = (1.5, [
        (0.0, {"ArmR": [(Y, 14)], "ForeArmR": [], "HandR": [], "ArmL": [(Y, -14)], "Spine1": []}, None),
        (0.35, {"ArmR": [(Y, 12), (X, -75)], "ForeArmR": [(X, -10)], "HandR": [(X, -10)], "Spine1": [(X, 4)]}, None),
        (0.5, {"ArmR": [(Y, 12), (X, -80)], "ForeArmR": [(X, -5)], "HandR": [(X, 12)], "Spine1": [(X, 6)]}, None),
        (0.65, {"ArmR": [(Y, 12), (X, -75)], "ForeArmR": [(X, -10)], "HandR": [(X, -10)], "Spine1": [(X, 4)]}, None),
        (1.0, {"ArmR": [(Y, 14)], "ForeArmR": [], "HandR": [], "Spine1": []}, None),
    ])
    # Uyari: sağ el yukarı, işaret
    K["Uyari"] = (1.6, [
        (0.0, {"ArmR": [(Y, 14)], "ForeArmR": [], "HandR": [], "Head": [], "ArmL": [(Y, -14)]}, None),
        (0.3, {"ArmR": [(Y, 30), (X, -30)], "ForeArmR": [(X, -120)], "HandR": [(X, -15)], "Head": [(X, 6)]}, None),
        (0.45, {"ArmR": [(Y, 30), (X, -30)], "ForeArmR": [(X, -110)], "HandR": [(X, -25)], "Head": [(X, 2)]}, None),
        (0.6, {"ArmR": [(Y, 30), (X, -30)], "ForeArmR": [(X, -120)], "HandR": [(X, -15)], "Head": [(X, 6)]}, None),
        (1.0, {"ArmR": [(Y, 14)], "ForeArmR": [], "HandR": [], "Head": []}, None),
    ])
    # Walking: yerinde yürüme döngüsü (1.1 sn)
    def adim(f):
        a = 32 * math.sin(2 * math.pi * f); k = max(0, 60 * math.sin(2 * math.pi * f + 0.6))
        k2 = max(0, 60 * math.sin(2 * math.pi * f + math.pi + 0.6))
        return {"UpLegL": [(X, -a)], "UpLegR": [(X, a)], "LegL": [(X, k)], "LegR": [(X, k2)],
                "ArmL": [(Y, -14), (X, a * 0.8)], "ArmR": [(Y, 14), (X, -a * 0.8)],
                "ForeArmL": [(X, -20)], "ForeArmR": [(X, -20)], "Spine1": [(Z, 3 * math.sin(2 * math.pi * f))],
                "Head": [(Z, -3 * math.sin(2 * math.pi * f))]}
    K["Walking"] = (1.1, [(f, adim(f), (0, 0, -0.012 * abs(math.sin(2 * math.pi * f)))) for f in (0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0)])
    # Wave: sağ kol yukarı, el sallama
    K["Wave"] = (2.2, [
        (0.0, {"ArmR": [(Y, 14)], "ForeArmR": [], "HandR": [], "ArmL": [(Y, -14)], "Head": []}, None),
        (0.2, {"ArmR": [(Y, 150), (X, -10)], "ForeArmR": [(Y, 30)], "HandR": [], "Head": [(Y, 4)]}, None),
        (0.35, {"ArmR": [(Y, 150), (X, -10)], "ForeArmR": [(Y, -25)], "HandR": [(Y, -10)]}, None),
        (0.5, {"ArmR": [(Y, 150), (X, -10)], "ForeArmR": [(Y, 30)], "HandR": [(Y, 10)]}, None),
        (0.65, {"ArmR": [(Y, 150), (X, -10)], "ForeArmR": [(Y, -25)], "HandR": [(Y, -10)]}, None),
        (0.8, {"ArmR": [(Y, 150), (X, -10)], "ForeArmR": [(Y, 30)], "HandR": [(Y, 10)], "Head": [(Y, 4)]}, None),
        (1.0, {"ArmR": [(Y, 14)], "ForeArmR": [], "HandR": [], "Head": []}, None),
    ])
    # Yaslan: ağırlık bir bacağa, gövde eğik, kollar bağlı
    K["Yaslan"] = (3.0, [
        (0.0, {"Spine": [], "Spine1": [], "Hips": [], "Head": [], "ArmL": [(Y, -14)], "ArmR": [(Y, 14)], "ForeArmL": [], "ForeArmR": []}, (0, 0, 0)),
        (0.3, {"Spine": [(Y, 6)], "Spine1": [(Y, 4)], "Hips": [(Y, -6)], "Head": [(Y, -8)], "ArmL": [(Y, -12), (X, -20)], "ArmR": [(Y, 12), (X, -20)], "ForeArmL": [(X, -110), (Z, 55)], "ForeArmR": [(X, -110), (Z, -55)]}, (0.03, 0, -0.01)),
        (0.7, {"Spine": [(Y, 6)], "Spine1": [(Y, 4)], "Hips": [(Y, -6)], "Head": [(Y, -8)], "ArmL": [(Y, -12), (X, -20)], "ArmR": [(Y, 12), (X, -20)], "ForeArmL": [(X, -110), (Z, 55)], "ForeArmR": [(X, -110), (Z, -55)]}, (0.03, 0, -0.01)),
        (1.0, {"Spine": [], "Spine1": [], "Hips": [], "Head": [], "ArmL": [(Y, -14)], "ArmR": [(Y, 14)], "ForeArmL": [], "ForeArmR": []}, (0, 0, 0)),
    ])
    # Yes: baş sallama
    K["Yes"] = (1.2, [
        (0.0, {"Head": [], "ArmL": [(Y, -14)], "ArmR": [(Y, 14)]}, None),
        (0.2, {"Head": [(X, 16)]}, None), (0.4, {"Head": [(X, -4)]}, None),
        (0.6, {"Head": [(X, 14)]}, None), (0.8, {"Head": [(X, -2)]}, None), (1.0, {"Head": []}, None),
    ])
    return K


def animasyonlar(arm_ob):
    if not arm_ob.animation_data:
        arm_ob.animation_data_create()
    ad_data = arm_ob.animation_data
    for ad, (sure, anahtarlar) in klip_tanimlari().items():
        act = bpy.data.actions.new(ad)
        ad_data.action = act
        son_kare = max(2, int(round(sure * FPS)))
        # rest'ten başlayıp tüm kemikleri ilk karede sıfırla ki klipler birbirine sızmasın
        sifirla(arm_ob, 1)
        for t, donmeler, hips in anahtarlar:
            kare = 1 + int(round(t * (son_kare - 1)))
            poz(arm_ob, kare, donmeler, hips)
        for fc in act.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "BEZIER"
        ad_data.action = None
        tr = ad_data.nla_tracks.new(); tr.name = ad
        st = tr.strips.new(ad, 1, act); st.name = ad
    log(f"animasyon: {len(ad_data.nla_tracks)} klip")


# ----------------------------------------------------------------------------
# 6. Dışa aktarma
# ----------------------------------------------------------------------------
def disa_aktar(ob, arm_ob, yol):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True); arm_ob.select_set(True)
    bpy.ops.export_scene.gltf(
        filepath=yol, export_format="GLB", use_selection=True,
        export_apply=False, export_yup=True, export_texcoords=True, export_normals=True,
        export_materials="EXPORT", export_image_format="JPEG", export_jpeg_quality=88,
        export_skins=True, export_def_bones=True, export_all_influences=False,
        export_morph=True, export_morph_normal=False, export_try_sparse_sk=False,
        export_animations=True, export_animation_mode="NLA_TRACKS", export_frame_range=False,
        export_force_sampling=True, export_optimize_animation_size=True,
        export_rest_position_armature=True,
    )
    log(f"→ {yol} ({os.path.getsize(yol)/1e6:.2f} MB)")


def main():
    t0 = time.time()
    sahne_temizle()
    mb = metaball_govde()
    ob = metaball_to_mesh(mb)
    uv_ac(ob)
    doku_yol = os.path.join(os.path.dirname(CIKTI), "mm-asistan-muhammed-doku.png")
    img = doku_uret(ob, doku_yol)
    malzeme(ob, img)
    shape_keyler(ob)
    arm_ob = iskelet(ob)
    animasyonlar(arm_ob)
    disa_aktar(ob, arm_ob, CIKTI)
    log(f"bitti, {time.time()-t0:.0f} sn")


if __name__ == "__main__":
    main()
