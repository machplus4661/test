// Zaman çizelgesi (lipsync_uret.py çıktısı) veya ses genliğiyle morph sürücüsü.
export class DudakSenkronu {
  constructor(morphHedefleri) {
    this.hedefler = morphHedefleri; // { MouthOpen: {mesh, index}, Smile: {...}, ... }
    this.cizelge = null;
    this.ses = null;
    this.analiz = null;
    this.baslangic = 0;
    this.kazanc = 1;
    this.aktif = false;
    this.suzgec = 0;
  }

  async yukle(cizelgeUrl, sesUrl) {
    this.cizelge = null; this.ses = null;
    if (cizelgeUrl) {
      try { this.cizelge = await (await fetch(cizelgeUrl)).json(); } catch { this.cizelge = null; }
    }
    if (sesUrl) {
      const a = new Audio(sesUrl);
      a.crossOrigin = 'anonymous';
      await new Promise((res) => { a.oncanplaythrough = res; a.onerror = res; a.load(); });
      if (!isNaN(a.duration) && a.duration > 0) this.ses = a;
    }
    return { cizelge: !!this.cizelge, ses: !!this.ses };
  }

  baslat() {
    this.aktif = true;
    this.baslangic = performance.now() / 1000;
    if (this.ses) {
      if (!this.analiz) {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const kaynak = ctx.createMediaElementSource(this.ses);
        this.analiz = ctx.createAnalyser(); this.analiz.fftSize = 512;
        kaynak.connect(this.analiz); this.analiz.connect(ctx.destination);
        this.veri = new Uint8Array(this.analiz.fftSize);
      }
      this.ses.currentTime = 0; this.ses.play();
      this.ses.onended = () => { this.aktif = false; this.sifirla(); };
    }
  }

  durdur() { this.aktif = false; if (this.ses) this.ses.pause(); this.sifirla(); }

  sifirla() { for (const k in this.hedefler) this.uygula(k, 0); }

  uygula(ad, deger) {
    const h = this.hedefler[ad];
    if (!h) return;
    for (const { mesh, index } of h) mesh.morphTargetInfluences[index] = deger;
  }

  guncelle() {
    if (!this.aktif) return;
    const t = this.ses ? this.ses.currentTime : performance.now() / 1000 - this.baslangic;
    if (this.cizelge) {
      const e = this.cizelge.egri;
      const i = Math.min(Math.floor(t * e.fps), e.MouthOpen.length - 1);
      for (const k of ['MouthOpen', 'Smile', 'MouthPucker']) {
        if (!e[k]) continue;
        const v = k === 'MouthOpen' ? e[k][i] * this.kazanc : e[k][i];
        this.uygula(k, Math.min(1, v));
      }
      if (!this.ses && t > this.cizelge.sure) { this.aktif = false; this.sifirla(); }
    } else if (this.analiz) {
      this.analiz.getByteTimeDomainData(this.veri);
      let s = 0; for (const v of this.veri) { const x = (v - 128) / 128; s += x * x; }
      const rms = Math.sqrt(s / this.veri.length);
      this.suzgec = Math.max(rms * 4 * this.kazanc, this.suzgec * 0.75);
      this.uygula('MouthOpen', Math.min(1, this.suzgec));
    }
  }
}
