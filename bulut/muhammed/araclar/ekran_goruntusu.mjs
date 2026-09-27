// Görüntüleyiciyi headless Chromium'da açar, istenen klip ve açılardan PNG alır.
// Kullanım: node araclar/ekran_goruntusu.mjs [glb_yolu] [klip1,klip2] [on,sag,arka,sol,yuz] [MouthOpen=1,Smile=0.5]
// Klip görüntüsü klibin %45'inde alınır. Dördüncü argüman morph değerlerini sabitler.
// Çıktı: kontrol/<glb-adi>-<klip>-<aci>.png   (playwright gerekir: npm i playwright)
import { chromium } from 'playwright';
import { createServer } from 'http';
import { readFile } from 'fs/promises';
import { extname, join, resolve, basename } from 'path';

const KOK = resolve(new URL('..', import.meta.url).pathname);
const glb = process.argv[2] || 'cikti/mm-asistan-muhammed.glb';
const klipler = (process.argv[3] || 'Idle').split(',');
const acilar = (process.argv[4] || 'on,sag,arka,sol,yuz').split(',');
const morphlar = Object.fromEntries((process.argv[5] || '').split(',').filter(Boolean).map((m) => { const [k, v] = m.split('='); return [k, parseFloat(v)]; }));
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.glb': 'model/gltf-binary', '.wav': 'audio/wav', '.png': 'image/png' };
const srv = createServer(async (req, res) => {
  try { const p = join(KOK, decodeURIComponent(req.url.split('?')[0])); const d = await readFile(p); res.writeHead(200, { 'content-type': MIME[extname(p)] || 'application/octet-stream' }); res.end(d); }
  catch { res.writeHead(404); res.end(); }
});
await new Promise((r) => srv.listen(0, '127.0.0.1', r));
const port = srv.address().port;
const b = await chromium.launch({ executablePath: process.env.CHROMIUM || '/opt/pw-browsers/chromium', args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--ignore-certificate-errors'] });
const p = await b.newPage({ viewport: { width: 1200, height: 900 }, ignoreHTTPSErrors: true });
const hatalar = [];
p.on('pageerror', (e) => hatalar.push(e.message));
await p.goto(`http://127.0.0.1:${port}/web/index.html?glb=../${glb}`, { waitUntil: 'networkidle' });
await p.waitForFunction(() => !document.querySelector('#durum').textContent.startsWith('hazır') && !document.querySelector('#durum').textContent.startsWith('model yok'), null, { timeout: 60000 });
await p.evaluate(() => { document.querySelector('#durum').style.display = 'none'; });
console.log('durum:', await p.evaluate(() => document.querySelector('#durum').textContent));
const ad = basename(glb, '.glb');
for (const k of klipler) {
  const var_mi = await p.evaluate((k) => { const b = [...document.querySelectorAll('#klipler button')].find((x) => x.title.startsWith(k + ' ') || x.textContent === k || x.title.includes(k)); if (b && !b.disabled) { b.click(); return true; } return false; }, k);
  if (!var_mi) console.log('klip yok:', k);
  // geçiş bitsin, sonra klibi %45 noktasında dondur (yazılım çiziminde gerçek zaman güvenilmez)
  await p.waitForTimeout(450);
  await p.evaluate((m) => { const d = window.__dbg; const a = d.aktif(); if (a) { a.time = a.getClip().duration * 0.45; } d.mixer.timeScale = 0; d.mixer.update(0);
    for (const [k, v] of Object.entries(m)) d.morphAyarla(k, v); }, morphlar);
  for (const a of acilar) {
    await p.evaluate((a) => document.querySelector(`[data-aci="${a}"]`).click(), a);
    await p.waitForTimeout(150);
    const ek = Object.keys(morphlar).length ? '-' + Object.keys(morphlar).join('+') : '';
    const yol = join(KOK, 'kontrol', `${ad}-${k}-${a}${ek}.png`);
    await p.locator('main').screenshot({ path: yol });
    console.log('→', yol.replace(KOK + '/', ''));
  }
  await p.evaluate(() => { window.__dbg.mixer.timeScale = 1; });
}
if (hatalar.length) console.log('sayfa hataları:', hatalar.slice(0, 5));
await b.close(); srv.close();
