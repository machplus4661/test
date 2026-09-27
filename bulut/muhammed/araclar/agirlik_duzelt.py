#!/usr/bin/env python3
"""Deri ağırlıklarını onarır: kol kemiğinin gövdeyi çekmesini keser,
etki sayısını sınırlar, normalize eder, komşular arasında yumuşatır.

Kullanım:
    python agirlik_duzelt.py girdi/mm-asistan-muhammed.glb cikti/mm-asistan-muhammed.glb \
        --uzak-esik 0.12 --yumusatma 2 --maks-etki 4

Adımlar:
 1. Uzak kesme: bir köşe, kemik doğrusundan (eklem → çocuk eklem) model boyunun
    --uzak-esik katından uzaksa o kemikten aldığı ağırlık sıfırlanır. Yalnızca
    --siniflar ile seçilen kemik sınıflarına uygulanır (varsayılan: kol).
 2. Yumuşatma: ağırlıklar ağ komşuları üzerinden --yumusatma tur ortalanır
    (Laplacian). Kemik geçişlerindeki sert kırılmaları giderir.
 3. Budama: köşe başına en yüksek --maks-etki ağırlık kalır, --min-agirlik
    altındakiler atılır, toplam 1'e normalize edilir.
Geometri, UV, doku, morph ve animasyon verisine dokunulmaz.
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from glb_incele import kemik_sinifi, nokta_dogru_uzaklik  # noqa: E402
from gltf_yardimci import accessor_oku, accessor_yaz, iskelet_bilgisi, kaydet, yukle  # noqa: E402


def yogun_agirlik(J, W, kemik_sayisi):
    D = np.zeros((len(J), kemik_sayisi), dtype=np.float64)
    for c in range(J.shape[1]):
        np.add.at(D, (np.arange(len(J)), J[:, c]), W[:, c])
    return D


def seyrek_agirlik(D, maks_etki, min_agirlik):
    sira = np.argsort(-D, axis=1)[:, :maks_etki]
    Wn = np.take_along_axis(D, sira, axis=1)
    Wn[Wn < min_agirlik] = 0
    toplam = Wn.sum(axis=1, keepdims=True)
    bos = toplam[:, 0] < 1e-8
    if bos.any():
        # tamamen boşalan köşe: en yakın önceki en büyük kemiği geri ver
        Wn[bos, 0] = 1.0
        toplam[bos] = 1.0
    Wn /= toplam
    J = sira.astype(np.uint16)
    eksik = 4 - J.shape[1]
    if eksik > 0:
        J = np.pad(J, ((0, 0), (0, eksik)))
        Wn = np.pad(Wn, ((0, 0), (0, eksik)))
    return J, Wn


def komsuluk(F, n):
    from scipy.sparse import coo_matrix
    i = np.concatenate([F[:, 0], F[:, 1], F[:, 2], F[:, 1], F[:, 2], F[:, 0]])
    j = np.concatenate([F[:, 1], F[:, 2], F[:, 0], F[:, 0], F[:, 1], F[:, 2]])
    A = coo_matrix((np.ones(len(i)), (i, j)), shape=(n, n)).tocsr()
    A.data[:] = 1
    derece = np.asarray(A.sum(axis=1)).ravel()
    derece[derece == 0] = 1
    return A, derece


def duzelt(girdi, cikti, uzak_esik, yumusatma, maks_etki, min_agirlik, siniflar, rapor_yaz=True):
    gltf, blob = yukle(girdi)
    if not gltf.skins:
        raise SystemExit("Skin yok, düzeltilecek ağırlık yok.")
    isk = iskelet_bilgisi(gltf, blob, 0)
    K = len(isk["eklemler"])
    kemik_siniflari = [kemik_sinifi(a) for a in isk["adlar"]]
    ozet = []
    for mesh in gltf.meshes:
        for prim in mesh.primitives:
            if prim.attributes.JOINTS_0 is None:
                continue
            J = accessor_oku(gltf, blob, prim.attributes.JOINTS_0, ham=True).astype(int)
            W = accessor_oku(gltf, blob, prim.attributes.WEIGHTS_0).astype(np.float64)
            P = accessor_oku(gltf, blob, prim.attributes.POSITION).astype(np.float64)
            D = yogun_agirlik(J, W, K)
            boy = float(np.linalg.norm(P.max(axis=0) - P.min(axis=0)))
            # uzak kesme maskeleri (kemik başına)
            maskeler = {}
            for k in range(K):
                if kemik_siniflari[k] not in siniflar:
                    continue
                cocuk = [c for c, e in enumerate(isk["ebeveyn"]) if e == k]
                a = isk["konum"][k]
                b = isk["konum"][cocuk[0]] if cocuk else a
                maskeler[k] = nokta_dogru_uzaklik(P, a, b) > uzak_esik * boy

            def kes(D):
                n = 0
                for k, m in maskeler.items():
                    m2 = m & (D[:, k] > 0)
                    n += int(m2.sum()); D[m2, k] = 0
                t = D.sum(axis=1, keepdims=True); t[t < 1e-8] = 1
                return D / t, n

            D, kesilen = kes(D)
            if yumusatma > 0 and prim.indices is not None:
                F = accessor_oku(gltf, blob, prim.indices).reshape(-1, 3).astype(int)
                A, derece = komsuluk(F, len(P))
                for _ in range(yumusatma):
                    D = 0.5 * D + 0.5 * (A @ D) / derece[:, None]
                D, _ = kes(D)  # yumuşatmanın geri sızdırdığını tekrar kes
            Jn, Wn = seyrek_agirlik(D, maks_etki, min_agirlik)
            accessor_yaz(gltf, blob, prim.attributes.JOINTS_0, Jn[:, : J.shape[1]])
            accessor_yaz(gltf, blob, prim.attributes.WEIGHTS_0, Wn[:, : W.shape[1]])
            ozet.append((mesh.name, len(P), kesilen))
    os.makedirs(os.path.dirname(cikti) or ".", exist_ok=True)
    kaydet(gltf, blob, cikti)
    for ad, n, kesilen in ozet:
        print(f"{ad}: {n} köşe, {kesilen} uzak kol ağırlığı kesildi, {yumusatma} tur yumuşatma, maks {maks_etki} etki")
    print("→", cikti)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("girdi"); ap.add_argument("cikti")
    ap.add_argument("--uzak-esik", type=float, default=0.12, help="model boyuna oranla kesme uzaklığı")
    ap.add_argument("--yumusatma", type=int, default=2)
    ap.add_argument("--maks-etki", type=int, default=4)
    ap.add_argument("--min-agirlik", type=float, default=0.02)
    ap.add_argument("--siniflar", default="kol", help="virgülle: kol,bacak,bas,govde")
    a = ap.parse_args()
    duzelt(a.girdi, a.cikti, a.uzak_esik, a.yumusatma, a.maks_etki, a.min_agirlik, set(a.siniflar.split(",")))


if __name__ == "__main__":
    main()
