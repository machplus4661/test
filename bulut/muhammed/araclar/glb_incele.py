#!/usr/bin/env python3
"""GLB teşhis raporu.

Kullanım:
    python glb_incele.py girdi/mm-asistan-muhammed.glb [-o kontrol/muhammed-rapor]

Üretir:
    <o>.json  : makine okunur tam rapor
    <o>.md    : insan okunur özet

Bakılanlar: ağ parçaları (kopuk parça var mı), iskelet, ağırlık dağılımı
(kol kemiklerinin gövdeye taşması), morph hedefleri, animasyon klipleri,
doku ve UV kapsama.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gltf_yardimci import accessor_oku, animasyon_suresi, iskelet_bilgisi, yukle  # noqa: E402

KOL_ANAHTAR = ("arm", "hand", "elbow", "shoulder", "kol", "el", "dirsek", "omuz", "clavicle", "forearm")
BACAK_ANAHTAR = ("leg", "thigh", "knee", "foot", "bacak", "diz", "ayak", "calf", "shin")


def kemik_sinifi(ad: str) -> str:
    a = ad.lower()
    if any(k in a for k in KOL_ANAHTAR):
        return "kol"
    if any(k in a for k in BACAK_ANAHTAR):
        return "bacak"
    if any(k in a for k in ("head", "neck", "bas", "boyun", "jaw", "cene")):
        return "bas"
    return "govde"


def nokta_dogru_uzaklik(p, a, b):
    ab = b - a
    t = np.clip(np.einsum("ij,j->i", p - a, ab) / max(float(ab @ ab), 1e-9), 0, 1)
    return np.linalg.norm(p - (a + t[:, None] * ab), axis=1)


def incele(yol: str) -> dict:
    gltf, blob = yukle(yol)
    rapor: dict = {"dosya": os.path.basename(yol), "boyut_mb": round(os.path.getsize(yol) / 1e6, 2)}
    uyarilar: list[str] = []

    # --- ağ ---
    agler = []
    for mi, mesh in enumerate(gltf.meshes):
        for pi, prim in enumerate(mesh.primitives):
            pos = accessor_oku(gltf, blob, prim.attributes.POSITION)
            kayit = {
                "mesh": mi, "primitive": pi, "ad": mesh.name,
                "kose": int(len(pos)),
                "bbox_min": pos.min(axis=0).round(4).tolist(),
                "bbox_max": pos.max(axis=0).round(4).tolist(),
                "uv": prim.attributes.TEXCOORD_0 is not None,
                "deri": prim.attributes.JOINTS_0 is not None,
                "morph_sayisi": len(prim.targets or []),
            }
            if prim.indices is not None:
                idx = accessor_oku(gltf, blob, prim.indices).reshape(-1)
                kayit["ucgen"] = int(len(idx) // 3)
                # bağlı bileşen sayısı (kopuk parça tespiti)
                try:
                    import trimesh
                    tm = trimesh.Trimesh(vertices=pos, faces=idx.reshape(-1, 3), process=False)
                    tm.merge_vertices()  # UV dikişlerinde çoğaltılmış köşeleri birleştir; yoksa adacıklar parça sayılır
                    parcalar = tm.split(only_watertight=False)
                    boyutlar = sorted([len(p.vertices) for p in parcalar], reverse=True)
                    kayit["parca_sayisi"] = len(parcalar)
                    kayit["parca_koseleri"] = boyutlar[:10]
                    kucuk = [b for b in boyutlar if b < 0.01 * len(pos)]
                    if len(kucuk) > 20:
                        uyarilar.append(f"{mesh.name}: {len(kucuk)} adet çok küçük kopuk parça var; dağılan parça belirtisi")
                except Exception as e:  # trimesh yoksa sessizce geç
                    kayit["parca_sayisi"] = f"hesaplanamadı: {e}"
            if prim.attributes.TEXCOORD_0 is not None:
                uv = accessor_oku(gltf, blob, prim.attributes.TEXCOORD_0)
                kayit["uv_min"] = uv.min(axis=0).round(3).tolist()
                kayit["uv_max"] = uv.max(axis=0).round(3).tolist()
                # UV kapsama: 64x64 ızgarada dolu hücre oranı
                h = np.zeros((64, 64), dtype=bool)
                g = np.clip((uv * 64).astype(int), 0, 63)
                h[g[:, 1], g[:, 0]] = True
                kayit["uv_kapsama_orani"] = round(float(h.mean()), 3)
            if prim.targets:
                adlar = (mesh.extras or {}).get("targetNames") if isinstance(mesh.extras, dict) else None
                kayit["morph_adlari"] = adlar or [f"target{i}" for i in range(len(prim.targets))]
                # her morph'un kaç köşeyi ne kadar oynattığı
                etkiler = []
                for t in prim.targets:
                    tp = t.get("POSITION") if isinstance(t, dict) else getattr(t, "POSITION", None)
                    if tp is None:
                        etkiler.append(None); continue
                    d = accessor_oku(gltf, blob, tp)
                    n = np.linalg.norm(d, axis=1)
                    etkiler.append({"etkilenen_kose": int((n > 1e-6).sum()), "en_buyuk_kayma": round(float(n.max()), 4),
                                    "merkez": d[n > 1e-6].mean(axis=0).round(3).tolist() if (n > 1e-6).any() else None})
                kayit["morph_etkileri"] = etkiler
            agler.append(kayit)
    rapor["agler"] = agler

    # --- iskelet ve ağırlıklar ---
    if gltf.skins:
        isk = iskelet_bilgisi(gltf, blob, 0)
        rapor["iskelet"] = {
            "kemik_sayisi": len(isk["eklemler"]),
            "kemikler": [{"ad": a, "ebeveyn": isk["adlar"][p] if p >= 0 else None, "sinif": kemik_sinifi(a),
                          "konum": isk["konum"][k].round(3).tolist()} for k, (a, p) in enumerate(zip(isk["adlar"], isk["ebeveyn"]))],
        }
        siniflar = [kemik_sinifi(a) for a in isk["adlar"]]
        agirlik_rapor = []
        for mesh in gltf.meshes:
            for prim in mesh.primitives:
                if prim.attributes.JOINTS_0 is None:
                    continue
                J = accessor_oku(gltf, blob, prim.attributes.JOINTS_0, ham=True).astype(int)
                W = accessor_oku(gltf, blob, prim.attributes.WEIGHTS_0)
                P = accessor_oku(gltf, blob, prim.attributes.POSITION)
                toplam = W.sum(axis=1)
                etkin = (W > 1e-4).sum(axis=1)
                kayit = {
                    "mesh": mesh.name,
                    "normalize_disi_kose": int((np.abs(toplam - 1) > 0.02).sum()),
                    "sifir_agirlikli_kose": int((toplam < 1e-4).sum()),
                    "ort_etki_sayisi": round(float(etkin.mean()), 2),
                    "kemik_basina_kose": {},
                    "kol_kemigi_uzak_kose": 0,
                }
                # kemik başına toplam ağırlık
                kb = np.zeros(len(isk["eklemler"]))
                for c in range(J.shape[1]):
                    np.add.at(kb, J[:, c], W[:, c])
                kayit["kemik_basina_kose"] = {isk["adlar"][k]: round(float(v), 1) for k, v in enumerate(kb) if v > 0}
                # kol kemiği ağırlığı taşıyan ama kemikten uzak köşeler → gövde çekme belirtisi
                boy = float(np.linalg.norm(P.max(axis=0) - P.min(axis=0)))
                esik = 0.12 * boy
                uzak = np.zeros(len(P), dtype=bool)
                for k, s in enumerate(siniflar):
                    if s != "kol":
                        continue
                    a = isk["konum"][k]
                    cocuk = [c for c, e in enumerate(isk["ebeveyn"]) if e == k]
                    b = isk["konum"][cocuk[0]] if cocuk else a
                    d = nokta_dogru_uzaklik(P, a, b)
                    w = np.zeros(len(P))
                    for c in range(J.shape[1]):
                        w += np.where(J[:, c] == k, W[:, c], 0)
                    uzak |= (w > 0.15) & (d > esik)
                kayit["kol_kemigi_uzak_kose"] = int(uzak.sum())
                if uzak.sum() > 0.005 * len(P):
                    uyarilar.append(f"{mesh.name}: {int(uzak.sum())} köşe kol kemiğinden uzak olduğu halde kol ağırlığı taşıyor; kol gövdeyi çeker")
                if kayit["normalize_disi_kose"]:
                    uyarilar.append(f"{mesh.name}: {kayit['normalize_disi_kose']} köşede ağırlık toplamı 1 değil")
                agirlik_rapor.append(kayit)
        rapor["agirliklar"] = agirlik_rapor
    else:
        rapor["iskelet"] = None
        uyarilar.append("Skin yok: model rig'siz")

    # --- animasyonlar ---
    rapor["animasyonlar"] = [
        {"ad": a.name, "sure_sn": round(animasyon_suresi(gltf, blob, a), 3), "kanal": len(a.channels),
         "hedef_dugum": sorted({gltf.nodes[c.target.node].name or str(c.target.node) for c in a.channels if c.target.node is not None}),
         "morph_kanali": any(c.target.path == "weights" for c in a.channels)}
        for a in gltf.animations
    ]

    # --- doku ---
    dokular = []
    for i, img in enumerate(gltf.images):
        kayit = {"indeks": i, "ad": img.name, "mime": img.mimeType}
        if img.bufferView is not None:
            bv = gltf.bufferViews[img.bufferView]
            kayit["boyut_kb"] = round(bv.byteLength / 1024, 1)
            try:
                from PIL import Image
                import io
                im = Image.open(io.BytesIO(bytes(blob[bv.byteOffset or 0: (bv.byteOffset or 0) + bv.byteLength])))
                kayit["cozunurluk"] = list(im.size)
                g = np.asarray(im.convert("L"))
                kayit["gri_alan_orani"] = round(float(((g > 100) & (g < 160)).mean()), 3)
            except Exception as e:
                kayit["cozunurluk"] = f"okunamadı: {e}"
        dokular.append(kayit)
    rapor["dokular"] = dokular
    rapor["malzemeler"] = [{"ad": m.name, "baseColor": m.pbrMetallicRoughness.baseColorTexture is not None if m.pbrMetallicRoughness else False,
                            "normal": m.normalTexture is not None} for m in gltf.materials]
    rapor["uyarilar"] = uyarilar
    return rapor


def md_yaz(r: dict) -> str:
    s = [f"# {r['dosya']} teşhis raporu", "", f"Boyut: {r['boyut_mb']} MB", ""]
    s.append("## Uyarılar")
    s += [f"- {u}" for u in r["uyarilar"]] or ["- Uyarı yok"]
    s += ["", "## Ağlar", "", "| Ad | Köşe | Üçgen | Parça | UV kapsama | Morph |", "|---|---|---|---|---|---|"]
    for a in r["agler"]:
        s.append(f"| {a['ad']} | {a['kose']} | {a.get('ucgen','-')} | {a.get('parca_sayisi','-')} | {a.get('uv_kapsama_orani','-')} | {', '.join(a.get('morph_adlari', [])) or '-'} |")
    if r["iskelet"]:
        s += ["", f"## İskelet ({r['iskelet']['kemik_sayisi']} kemik)", ""]
        s += [f"- {k['ad']} ← {k['ebeveyn'] or 'kök'} [{k['sinif']}]" for k in r["iskelet"]["kemikler"]]
        s += ["", "## Ağırlıklar", ""]
        for w in r.get("agirliklar", []):
            s.append(f"- {w['mesh']}: ortalama {w['ort_etki_sayisi']} kemik/köşe, normalize dışı {w['normalize_disi_kose']}, kol kemiğinden uzak {w['kol_kemigi_uzak_kose']}")
    s += ["", "## Animasyonlar", "", "| Ad | Süre (sn) | Kanal | Morph |", "|---|---|---|---|"]
    s += [f"| {a['ad']} | {a['sure_sn']} | {a['kanal']} | {'evet' if a['morph_kanali'] else '-'} |" for a in r["animasyonlar"]]
    s += ["", "## Dokular", ""]
    s += [f"- {d.get('ad') or d['indeks']}: {d.get('cozunurluk')} {d.get('boyut_kb','?')} KB, gri alan oranı {d.get('gri_alan_orani','?')}" for d in r["dokular"]] or ["- Doku yok"]
    return "\n".join(s) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("glb")
    ap.add_argument("-o", "--cikti", help="rapor yolu (uzantısız)")
    a = ap.parse_args()
    r = incele(a.glb)
    cikti = a.cikti or os.path.splitext(a.glb)[0] + "-rapor"
    os.makedirs(os.path.dirname(cikti) or ".", exist_ok=True)
    with open(cikti + ".json", "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=2)
    with open(cikti + ".md", "w", encoding="utf-8") as f:
        f.write(md_yaz(r))
    print(md_yaz(r))
    print(f"→ {cikti}.json / .md")


if __name__ == "__main__":
    main()
