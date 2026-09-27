#!/usr/bin/env python3
"""Metinden (ve varsa ses dosyasından) dudak senkronu zaman çizelgesi üretir.

Kullanım:
    python lipsync_uret.py --replikler ses/replikler.json            # hepsini üret
    python lipsync_uret.py --metin "Merhaba dünya" --sure 1.4 -o ses/zaman/deneme.json
    python lipsync_uret.py --metin "..." --ses ses/kayit/x.wav -o ses/zaman/x.json

Çıktı JSON:
    {"metin", "sure", "anahtarlar": [{"t", "viseme", "MouthOpen", "Smile", "MouthPucker"}...],
     "egri": {"fps": 30, "MouthOpen": [...], "Smile": [...], "MouthPucker": [...]}}

Ses dosyası (.wav) verilirse süre dosyadan alınır ve MouthOpen genliği ses
zarfıyla çarpılır; böylece sessiz anlarda ağız kapanır.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import wave

import numpy as np

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNLULER = set("aeıioöuüâîû")
NOKTALAMA = set(".,;:!?…")


def visemeleri_yukle(yol=None):
    with open(yol or os.path.join(KOK, "ses", "visemeler.json"), encoding="utf-8") as f:
        return json.load(f)


def ses_zarfi(yol: str, fps: int):
    with wave.open(yol, "rb") as w:
        sr, n, ch, sw = w.getframerate(), w.getnframes(), w.getnchannels(), w.getsampwidth()
        ham = w.readframes(n)
    dt = {1: np.int8, 2: np.int16, 4: np.int32}[sw]
    x = np.frombuffer(ham, dtype=dt).astype(np.float64)
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    x /= max(np.abs(x).max(), 1)
    sure = len(x) / sr
    pencere = int(sr / fps)
    kare = len(x) // pencere
    rms = np.sqrt((x[: kare * pencere].reshape(kare, pencere) ** 2).mean(axis=1))
    rms /= max(rms.max(), 1e-6)
    # hızlı yükselen, yavaş inen zarf
    z = np.zeros_like(rms)
    for i in range(1, len(rms)):
        z[i] = max(rms[i], z[i - 1] * 0.8)
    return sure, z


def uret(metin: str, sure: float | None, ses: str | None, vis: dict, fps: int = 30):
    hv, vm, sa = vis["harf_viseme"], vis["viseme_morph"], vis["sure_agirligi"]
    zarf = None
    if ses and os.path.exists(ses):
        sure, zarf = ses_zarfi(ses, fps)
    if not sure:
        # ortalama Türkçe konuşma hızı ~ 13 harf/sn
        sure = max(0.5, len(metin) / 13.0)
    parcalar = []  # (viseme, ağırlık)
    for h in metin.lower():
        if h in UNLULER:
            parcalar.append((hv.get(h, "aa"), sa["unlu"]))
        elif h.isalpha():
            parcalar.append((hv.get(h, "dd"), sa["unsuz"]))
        elif h in NOKTALAMA:
            parcalar.append(("sil", sa["noktalama"]))
        else:
            parcalar.append(("sil", sa["bosluk"]))
    toplam = sum(w for _, w in parcalar) or 1.0
    olcek = sure / toplam
    anahtarlar, t = [], 0.0
    for v, w in parcalar:
        m = vm[v]
        anahtarlar.append({"t": round(t, 4), "viseme": v, **{k: m.get(k, 0.0) for k in ("MouthOpen", "Smile", "MouthPucker")}})
        t += w * olcek
    anahtarlar.append({"t": round(sure, 4), "viseme": "sil", "MouthOpen": 0.0, "Smile": 0.0, "MouthPucker": 0.0})
    # örneklenmiş eğri
    kare = int(np.ceil(sure * fps)) + 1
    tt = np.arange(kare) / fps
    egri = {}
    ts = np.array([a["t"] for a in anahtarlar])
    for k in ("MouthOpen", "Smile", "MouthPucker"):
        vals = np.array([a[k] for a in anahtarlar])
        y = np.interp(tt, ts, vals)
        # yumuşatma
        yw = max(1, int(vis.get("yumusatma_sn", 0.06) * fps))
        if yw > 1:
            cek = np.ones(yw) / yw
            y = np.convolve(y, cek, mode="same")
        if k == "MouthOpen" and zarf is not None:
            z = np.interp(tt, np.arange(len(zarf)) / fps, zarf)
            y = y * (0.3 + 0.7 * z)
        egri[k] = [round(float(v), 3) for v in y]
    return {"metin": metin, "sure": round(sure, 4), "ses": ses, "anahtarlar": anahtarlar, "egri": {"fps": fps, **egri}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replikler", help="replikler.json; içindeki her replik için üretir")
    ap.add_argument("--metin"); ap.add_argument("--sure", type=float); ap.add_argument("--ses")
    ap.add_argument("-o", "--cikti"); ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--visemeler")
    a = ap.parse_args()
    vis = visemeleri_yukle(a.visemeler)
    if a.replikler:
        with open(a.replikler, encoding="utf-8") as f:
            r = json.load(f)
        kok = os.path.dirname(os.path.abspath(a.replikler))
        kok = os.path.dirname(kok) if os.path.basename(kok) == "ses" else kok
        for rp in r["replikler"]:
            ses = os.path.join(kok, rp["ses"]) if rp.get("ses") else None
            sonuc = uret(rp["metin"], rp.get("sure"), ses, vis, a.fps)
            hedef = os.path.join(kok, rp["zaman"])
            os.makedirs(os.path.dirname(hedef), exist_ok=True)
            with open(hedef, "w", encoding="utf-8") as f:
                json.dump(sonuc, f, ensure_ascii=False)
            print(f"{rp['id']}: {sonuc['sure']} sn, {len(sonuc['anahtarlar'])} anahtar, ses {'var' if ses and os.path.exists(ses) else 'yok → tahmini süre'} → {rp['zaman']}")
        return
    if not a.metin:
        ap.error("--metin veya --replikler gerekli")
    sonuc = uret(a.metin, a.sure, a.ses, vis, a.fps)
    if a.cikti:
        os.makedirs(os.path.dirname(a.cikti) or ".", exist_ok=True)
        with open(a.cikti, "w", encoding="utf-8") as f:
            json.dump(sonuc, f, ensure_ascii=False)
        print("→", a.cikti)
    else:
        print(json.dumps(sonuc, ensure_ascii=False)[:600])


if __name__ == "__main__":
    main()
