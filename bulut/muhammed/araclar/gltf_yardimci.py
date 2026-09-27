"""GLB dosyalarını okuyup yazmak için ortak yardımcılar.

pygltflib üzerine ince bir katman: accessor'ları numpy dizisine çevirir,
aynı yerleşimle geri yazar, iskelet bilgisini çıkarır.
"""
from __future__ import annotations

import numpy as np
from pygltflib import GLTF2

BILESEN_TIPI = {
    5120: np.int8,
    5121: np.uint8,
    5122: np.int16,
    5123: np.uint16,
    5125: np.uint32,
    5126: np.float32,
}
BILESEN_SAYISI = {
    "SCALAR": 1,
    "VEC2": 2,
    "VEC3": 3,
    "VEC4": 4,
    "MAT2": 4,
    "MAT3": 9,
    "MAT4": 16,
}


def yukle(yol: str) -> tuple[GLTF2, bytearray]:
    gltf = GLTF2().load(yol)
    blob = bytearray(gltf.binary_blob() or b"")
    return gltf, blob


def kaydet(gltf: GLTF2, blob: bytearray, yol: str) -> None:
    gltf.set_binary_blob(bytes(blob))
    gltf.save(yol)


def _accessor_konum(gltf: GLTF2, idx: int):
    acc = gltf.accessors[idx]
    bv = gltf.bufferViews[acc.bufferView]
    dtype = np.dtype(BILESEN_TIPI[acc.componentType])
    n = BILESEN_SAYISI[acc.type]
    eleman = dtype.itemsize * n
    stride = bv.byteStride or eleman
    basla = (bv.byteOffset or 0) + (acc.byteOffset or 0)
    return acc, dtype, n, eleman, stride, basla


def accessor_oku(gltf: GLTF2, blob: bytearray, idx: int, ham: bool = False) -> np.ndarray:
    """Accessor'ı (count, n) şeklinde döndürür. Normalize tam sayılar
    ham=False iken [0,1] veya [-1,1] float'a çevrilir."""
    acc, dtype, n, eleman, stride, basla = _accessor_konum(gltf, idx)
    out = np.empty((acc.count, n), dtype=dtype)
    mv = memoryview(blob)
    for i in range(acc.count):
        o = basla + i * stride
        out[i] = np.frombuffer(mv[o : o + eleman], dtype=dtype, count=n)
    if ham or not acc.normalized:
        return out
    if dtype.kind == "u":
        return out.astype(np.float32) / np.iinfo(dtype).max
    if dtype.kind == "i":
        return np.clip(out.astype(np.float32) / np.iinfo(dtype).max, -1.0, 1.0)
    return out


def accessor_yaz(gltf: GLTF2, blob: bytearray, idx: int, veri: np.ndarray) -> None:
    """Aynı accessor'a, aynı tür ve yerleşimle geri yazar."""
    acc, dtype, n, eleman, stride, basla = _accessor_konum(gltf, idx)
    veri = np.asarray(veri)
    assert veri.shape == (acc.count, n), f"beklenen {(acc.count, n)}, gelen {veri.shape}"
    if acc.normalized and dtype.kind in "ui":
        veri = np.round(veri * np.iinfo(dtype).max)
    veri = veri.astype(dtype)
    for i in range(acc.count):
        o = basla + i * stride
        blob[o : o + eleman] = veri[i].tobytes()
    if dtype == np.float32 or True:
        acc.min = [float(x) for x in veri.min(axis=0)] if n <= 4 else None
        acc.max = [float(x) for x in veri.max(axis=0)] if n <= 4 else None


def dugum_dunya_matrisleri(gltf: GLTF2) -> np.ndarray:
    """Her düğüm için 4x4 dünya matrisi (kolon-major glTF → satır-major numpy)."""
    n = len(gltf.nodes)
    yerel = np.zeros((n, 4, 4), dtype=np.float64)
    for i, nd in enumerate(gltf.nodes):
        if nd.matrix:
            yerel[i] = np.array(nd.matrix, dtype=np.float64).reshape(4, 4).T
        else:
            t = np.array(nd.translation or [0, 0, 0], dtype=np.float64)
            q = np.array(nd.rotation or [0, 0, 0, 1], dtype=np.float64)
            s = np.array(nd.scale or [1, 1, 1], dtype=np.float64)
            x, y, z, w = q
            R = np.array(
                [
                    [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                    [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                    [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
                ]
            )
            M = np.eye(4)
            M[:3, :3] = R * s[None, :]
            M[:3, 3] = t
            yerel[i] = M
    ebeveyn = [-1] * n
    for i, nd in enumerate(gltf.nodes):
        for c in nd.children or []:
            ebeveyn[c] = i
    dunya = np.zeros_like(yerel)
    hesaplandi = [False] * n

    def hesapla(i):
        if hesaplandi[i]:
            return dunya[i]
        p = ebeveyn[i]
        dunya[i] = (hesapla(p) @ yerel[i]) if p >= 0 else yerel[i]
        hesaplandi[i] = True
        return dunya[i]

    for i in range(n):
        hesapla(i)
    return dunya


def iskelet_bilgisi(gltf: GLTF2, blob: bytearray, skin_idx: int = 0) -> dict:
    """Eklem adları, ebeveynleri ve bağlama pozundaki dünya konumları."""
    skin = gltf.skins[skin_idx]
    eklemler = list(skin.joints)
    adlar = [gltf.nodes[j].name or f"node{j}" for j in eklemler]
    dunya = dugum_dunya_matrisleri(gltf)
    konum = np.array([dunya[j][:3, 3] for j in eklemler])
    eklem_sira = {j: k for k, j in enumerate(eklemler)}
    ebeveyn = [-1] * len(eklemler)
    for k, j in enumerate(eklemler):
        for c in gltf.nodes[j].children or []:
            if c in eklem_sira:
                ebeveyn[eklem_sira[c]] = k
    return {"eklemler": eklemler, "adlar": adlar, "ebeveyn": ebeveyn, "konum": konum}


def animasyon_suresi(gltf: GLTF2, blob: bytearray, anim) -> float:
    en_uzun = 0.0
    for s in anim.samplers:
        acc = gltf.accessors[s.input]
        if acc.max:
            en_uzun = max(en_uzun, float(acc.max[0]))
        else:
            en_uzun = max(en_uzun, float(accessor_oku(gltf, blob, s.input).max()))
    return en_uzun
