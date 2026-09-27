import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DudakSenkronu } from './lipsync.js';

const q = new URLSearchParams(location.search);
const GLB_ADAYLAR = q.get('glb') ? [q.get('glb')] : ['../cikti/mm-asistan-muhammed.glb', '../girdi/mm-asistan-muhammed.glb', '../cikti/ornek-rigli-duzeltilmis.glb'];
const $ = (s) => document.querySelector(s);
const durum = (m) => { $('#durum').textContent = m; };

const canvas = $('#c');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
const scene = new THREE.Scene();
scene.background = new THREE.Color(getComputedStyle(document.documentElement).getPropertyValue('--bg').trim() || '#f4f5f7');
const camera = new THREE.PerspectiveCamera(35, 1, 0.01, 100);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
scene.add(new THREE.HemisphereLight(0xffffff, 0x8899aa, 1.2));
const gunes = new THREE.DirectionalLight(0xffffff, 1.6); gunes.position.set(2, 4, 3); scene.add(gunes);
const dolgu = new THREE.DirectionalLight(0xffffff, 0.5); dolgu.position.set(-3, 2, -2); scene.add(dolgu);
const izgara = new THREE.GridHelper(4, 16, 0x888888, 0xbbbbbb); scene.add(izgara);

let kok = null, mixer = null, klipler = {}, aktifAksiyon = null, iskeletHelper = null, boy = 1.7, merkez = new THREE.Vector3();
let klipTanim = { klipler: [], varsayilan_gecis_sn: 0.35, yuz_katmani: {} };
let morphHedef = {}; // ad -> [{mesh,index}]
let dudak = null;
const saat = new THREE.Clock();

function boyutla() {
  const r = canvas.parentElement.getBoundingClientRect();
  renderer.setSize(r.width, r.height, false);
  camera.aspect = r.width / r.height; camera.updateProjectionMatrix();
}
addEventListener('resize', boyutla); boyutla();

async function jsonGetir(u) { try { return await (await fetch(u)).json(); } catch { return null; } }

async function modelYukle(kaynak) {
  if (kok) { scene.remove(kok); kok = null; }
  const loader = new GLTFLoader();
  let gltf = null, kullanilan = null;
  const adaylar = typeof kaynak === 'string' ? [kaynak] : kaynak;
  for (const a of adaylar) {
    try { gltf = await loader.loadAsync(a); kullanilan = a; break; } catch (e) { /* sıradakine geç */ }
  }
  if (!gltf) { $('#uyari').textContent = 'GLB bulunamadı. Dosya seçin ya da ?glb= ile yol verin.'; durum('model yok'); return; }
  $('#uyari').textContent = '';
  kok = gltf.scene; scene.add(kok);
  const kutu = new THREE.Box3().setFromObject(kok);
  const olcu = kutu.getSize(new THREE.Vector3()); boy = olcu.y || 1; kutu.getCenter(merkez);
  $('#dosya').textContent = `${kullanilan.split('/').pop()} · boy ${boy.toFixed(2)} · alt y ${kutu.min.y.toFixed(3)}`;
  aciAyarla('on');

  // morph hedefleri
  morphHedef = {};
  kok.traverse((o) => {
    if (o.isMesh && o.morphTargetDictionary) {
      for (const [ad, i] of Object.entries(o.morphTargetDictionary)) (morphHedef[ad] ||= []).push({ mesh: o, index: i });
    }
  });
  morphPaneli();
  dudak = new DudakSenkronu(morphHedef);

  // klipler
  mixer = new THREE.AnimationMixer(kok); klipler = {};
  for (const c of gltf.animations) klipler[c.name] = c;
  klipPaneli(gltf.animations.map((c) => c.name));
  if (iskeletHelper) { scene.remove(iskeletHelper); iskeletHelper = null; }
  $('#iskelet').onchange();
  $('#tel').onchange();
  durum(`${gltf.animations.length} klip, ${Object.keys(morphHedef).length} morph, ${sayKemik(gltf)} kemik`);
}

function sayKemik(gltf) { const s = new Set(); gltf.scene.traverse((o) => { if (o.isBone) s.add(o); }); return s.size; }

function klipPaneli(glbAdlari) {
  const kap = $('#klipler'); kap.innerHTML = '';
  const tanimli = klipTanim.klipler || [];
  const eslesme = new Map();
  for (const k of tanimli) { const g = k.glb_adi || k.ad; if (glbAdlari.includes(g)) eslesme.set(g, k); }
  for (const ad of glbAdlari) {
    const k = eslesme.get(ad);
    const b = document.createElement('button');
    b.textContent = k ? `${k.ad}` : ad; b.title = k ? `${ad} · ${k.aciklama}` : `${ad} (klipler.json'da tanımsız)`;
    if (!k) b.style.opacity = 0.7;
    b.onclick = () => klipOynat(ad, k);
    kap.appendChild(b);
  }
  for (const k of tanimli) if (!eslesme.has(k.glb_adi || k.ad)) {
    const b = document.createElement('button'); b.textContent = k.ad; b.disabled = true; b.title = 'GLB içinde bu klip yok'; b.style.opacity = 0.4; kap.appendChild(b);
  }
  const bos = tanimli.find((k) => k.ad === klipTanim.bosta_klip);
  const boslukAd = bos ? (bos.glb_adi || bos.ad) : glbAdlari[0];
  if (boslukAd && klipler[boslukAd]) klipOynat(boslukAd, bos);
}

function klipOynat(ad, tanim) {
  const klip = klipler[ad]; if (!klip || !mixer) return;
  const gecis = parseFloat($('#gecis').value);
  const a = mixer.clipAction(klip);
  a.reset(); a.timeScale = parseFloat($('#hiz').value);
  a.setLoop(tanim && tanim.dongu === false ? THREE.LoopOnce : THREE.LoopRepeat, Infinity);
  a.clampWhenFinished = true; a.enabled = true;
  if (aktifAksiyon && aktifAksiyon !== a) { a.crossFadeFrom(aktifAksiyon, gecis, true); }
  a.play(); aktifAksiyon = a;
  document.querySelectorAll('#klipler button').forEach((b) => b.classList.toggle('aktif', b.textContent === (tanim ? tanim.ad : ad)));
  // yüz katmanı
  const yuz = (klipTanim.yuz_katmani || {});
  const y = yuz[tanim ? tanim.ad : ad] || yuz.varsayilan || {};
  for (const [m, v] of Object.entries(y)) morphAyarla(m, v);
  // tek seferlik klip bitince boşa dön
  if (tanim && tanim.dongu === false) {
    const bosta = klipTanim.klipler.find((k) => k.ad === klipTanim.bosta_klip);
    const dinle = (e) => { if (e.action === a) { mixer.removeEventListener('finished', dinle); if (bosta) klipOynat(bosta.glb_adi || bosta.ad, bosta); } };
    mixer.addEventListener('finished', dinle);
  }
}

function morphAyarla(ad, v) { for (const { mesh, index } of morphHedef[ad] || []) mesh.morphTargetInfluences[index] = v; const s = document.querySelector(`input[data-morph="${ad}"]`); if (s) s.value = v; }

function morphPaneli() {
  const kap = $('#morphlar'); kap.innerHTML = '';
  const adlar = Object.keys(morphHedef);
  if (!adlar.length) { kap.textContent = 'morph yok'; return; }
  for (const ad of adlar) {
    const l = document.createElement('label');
    l.innerHTML = `<span style="width:96px">${ad}</span><input type="range" data-morph="${ad}" min="0" max="1" step="0.01" value="0">`;
    l.querySelector('input').oninput = (e) => morphAyarla(ad, parseFloat(e.target.value));
    kap.appendChild(l);
  }
}

async function replikPaneli() {
  const r = await jsonGetir('../ses/replikler.json'); const kap = $('#replikler');
  if (!r) { kap.innerHTML = '<span class="kucuk">replikler.json bulunamadı</span>'; return; }
  for (const rp of r.replikler) {
    const b = document.createElement('button'); b.textContent = rp.id; b.title = rp.metin;
    b.onclick = async () => {
      if (!dudak) return;
      dudak.durdur();
      const sesUrl = rp.ses ? '../' + rp.ses : null;
      const ok = await dudak.yukle(rp.zaman ? '../' + rp.zaman : null, sesUrl);
      if (!ok.cizelge && !ok.ses) { durum(`${rp.id}: ne zaman çizelgesi ne ses bulundu`); return; }
      if (!ok.ses && !$('#sesTabanli').checked) { durum(`${rp.id}: ses dosyası yok; "metinden zamanla" seçeneğini açın`); return; }
      dudak.kazanc = parseFloat($('#kazanc').value);
      const tanim = klipTanim.klipler.find((k) => k.ad === rp.klip);
      if (tanim) klipOynat(tanim.glb_adi || tanim.ad, tanim);
      dudak.baslat();
      durum(`${rp.id} · ${ok.ses ? 'ses + ' : ''}${ok.cizelge ? 'zaman çizelgesi' : 'genlik'}`);
    };
    kap.appendChild(b);
  }
}

function aciAyarla(a) {
  const u = boy * 2.2, y = merkez.y;
  const konum = { on: [0, y, u], sag: [u, y, 0], arka: [0, y, -u], sol: [-u, y, 0], yuz: [0, merkez.y + boy * 0.38, boy * 0.55] }[a];
  camera.position.set(...konum);
  controls.target.set(0, a === 'yuz' ? merkez.y + boy * 0.38 : y, 0); controls.update();
}
document.querySelectorAll('[data-aci]').forEach((b) => (b.onclick = () => aciAyarla(b.dataset.aci)));
$('#gecis').oninput = (e) => ($('#gecisV').textContent = e.target.value);
$('#hiz').oninput = (e) => { $('#hizV').textContent = parseFloat(e.target.value).toFixed(1); if (aktifAksiyon) aktifAksiyon.timeScale = parseFloat(e.target.value); };
$('#kazanc').oninput = (e) => { $('#kazancV').textContent = parseFloat(e.target.value).toFixed(1); if (dudak) dudak.kazanc = parseFloat(e.target.value); };
$('#iskelet').onchange = () => { if (!kok) return; if ($('#iskelet').checked && !iskeletHelper) { iskeletHelper = new THREE.SkeletonHelper(kok); scene.add(iskeletHelper); } if (iskeletHelper) iskeletHelper.visible = $('#iskelet').checked; };
$('#tel').onchange = () => { if (!kok) return; kok.traverse((o) => { if (o.isMesh) (Array.isArray(o.material) ? o.material : [o.material]).forEach((m) => (m.wireframe = $('#tel').checked)); }); };
$('#zemin').onchange = () => (izgara.visible = $('#zemin').checked);
$('#ekran').onclick = () => { renderer.render(scene, camera); const a = document.createElement('a'); a.download = `muhammed-${Date.now()}.png`; a.href = canvas.toDataURL('image/png'); a.click(); };
$('#glbSec').onchange = (e) => { const f = e.target.files[0]; if (f) modelYukle(URL.createObjectURL(f)); };

(async () => {
  klipTanim = (await jsonGetir('../animasyon/klipler.json')) || klipTanim;
  await replikPaneli();
  await modelYukle(GLB_ADAYLAR);
})();

renderer.setAnimationLoop(() => {
  const dt = saat.getDelta();
  if (mixer) mixer.update(dt);
  if (dudak) dudak.guncelle();
  if ($('#dondur').checked && kok) kok.rotation.y += dt * 0.6;
  controls.update();
  renderer.render(scene, camera);
});
