# Muhammed: tam 3D model, animasyon ve ses düzeni

Muhammed'i örnek karakter olarak uçtan uca çalışır hale getirmek için kurulan
iş akışı. Diğer dört karakter aynı düzenden geçirilecek.

**Durum:** Model sıfırdan, prosedürel olarak Blender ile üretildi.
`cikti/mm-asistan-muhammed.glb` (1.67 MB): her açıdan dokulu, 22 deform kemik,
6 yüz morph'u, 15 klip. Sayısal rapor `kontrol/muhammed-rapor.md`, görseller
`kontrol/mm-asistan-muhammed-*.png`. Ayrıntı: `karakter.json`.

## Sıfırdan üretim (Blender)

```
bash araclar/blender_kur.sh            # Linux: Blender 4.2'yi indirir, BLENDER yolunu yazar
$BLENDER -b -P araclar/blender_modelle.py -- --cikti cikti/mm-asistan-muhammed.glb
python araclar/glb_incele.py cikti/mm-asistan-muhammed.glb -o kontrol/muhammed-rapor
npm install && node araclar/ekran_goruntusu.mjs cikti/mm-asistan-muhammed.glb Idle,Wave on,sag,yuz
```

Windows'ta Blender 4.2 LTS kurulu olmalı; `blender.exe -b -P araclar\blender_modelle.py -- --cikti cikti\mm-asistan-muhammed.glb`.
Üretim ~20 sn sürer. Betik `blender_modelle.py` içindeki parametrelerle (ölçüler,
renkler, klip tanımları) tamamen yeniden üretilebilir; elle düzenlenmiş dosya yoktur.

Betik sırasıyla: metaball gövde → tek ağ, ~12k üçgen → smart UV → numpy ile doku
(ten, saç, sakal, gözler, kaş, ağız, gömlek, pantolon, ayakkabı) → shape key'ler →
25 kemik + bone-heat ağırlık → 15 klip (NLA) → GLB (Y-up, JPEG doku).

Ekran görüntüsü betiği: `node araclar/ekran_goruntusu.mjs <glb> <klipler> <açılar> [Morph=değer,...]`.
Klip %45 noktasında dondurulur. Örnek: `... Talk yuz MouthOpen=1`.

## Klasörler

| Klasör | İçerik |
|---|---|
| `girdi/` | Yerelden kopyalanacak GLB'ler. Uygulamanın kullandığı, rig'li ham, rig'siz ham. |
| `cikti/` | Betiklerin ürettiği düzeltilmiş GLB. Uygulamaya bu kopyalanır. |
| `kontrol/` | Teşhis raporları ve ekran görüntüleri. |
| `araclar/` | Python betikleri. |
| `animasyon/` | Klip tanımları. |
| `ses/` | Viseme tablosu, replikler, ses kayıtları, üretilen zaman çizelgeleri. |
| `web/` | Yerelde açılan three.js test görüntüleyicisi. |

Tanım dosyaları: `karakter.json` (dosyalar, hedefler, kabul ölçütleri, aşama durumu),
`animasyon/klipler.json` (15 klip), `ses/visemeler.json` (harf → ağız şekli),
`ses/replikler.json` (konuşma satırları).

## Kurulum (yerelde, bir kez)

```
cd bulut/muhammed
pip install -r requirements.txt
```

Kısayol: `powershell -ExecutionPolicy Bypass -File .\kur.ps1` hem kurulumu hem
sunucuyu hem tarayıcı açılışını tek seferde yapar. Depo yoksa önce klonlayın:

```
cd C:\MakeMaker
git clone -b claude/suan-hediye-limiti-kkrj2d https://github.com/machplus4661/test.git bulut-test
cd bulut-test\bulut\muhammed
powershell -ExecutionPolicy Bypass -File .\kur.ps1
```

## Aşamalar

### 1. Girdi dosyalarını koy

```
C:\MakeMaker\01-proje\public\models\mm-asistan-muhammed.glb  →  girdi/mm-asistan-muhammed.glb
C:\MakeMaker\09-cizim\tamboy\muhammed-2-rigged.glb            →  girdi/muhammed-2-rigged.glb
C:\MakeMaker\09-cizim\tamboy\muhammed-2.glb                   →  girdi/muhammed-2.glb
```

### 2. Teşhis

```
python araclar/glb_incele.py girdi/mm-asistan-muhammed.glb -o kontrol/muhammed-rapor
```

Rapor kopuk parçaları, kemik listesini, kol kemiğinin gövdeye taşan ağırlıklarını,
morph hedeflerini, klipleri ve doku kapsamasını çıkarır. Uyarılar bölümü ilk
bakılacak yerdir. Aynı komutu `-rigged` ve rig'siz ham dosyaya da çalıştırın;
sorunun hangi aşamada girdiği böyle ayrılır.

Rapor geldikten sonra `animasyon/klipler.json` içindeki `glb_adi` alanları GLB'deki
gerçek klip adlarıyla doldurulur.

### 3. Ağırlık onarımı

```
python araclar/agirlik_duzelt.py girdi/mm-asistan-muhammed.glb cikti/mm-asistan-muhammed.glb
python araclar/glb_incele.py cikti/mm-asistan-muhammed.glb -o kontrol/muhammed-duzeltilmis-rapor
```

Kol kemiğinden uzak köşelerin kol ağırlığı kesilir, ağırlıklar komşular arasında
yumuşatılır, köşe başına en çok 4 etki bırakılır. Geometri, doku, morph ve
animasyon verisine dokunulmaz. İkinci raporda "kol kemiğinden uzak" sayısı 0 olmalı.

Kesme çok sert gelirse `--uzak-esik 0.16`, yetersizse `0.09` deneyin. Etek ya da
elbise gibi bacak taşması varsa `--siniflar kol,bacak`.

### 4. Klip doğrulama

```
python -m http.server 8000
```

Tarayıcıda `http://localhost:8000/web/` açın. Görüntüleyici sırayla `cikti/`, sonra
`girdi/` klasöründeki GLB'yi yükler. Başka dosya için `?glb=../girdi/muhammed-2-rigged.glb`.

- Her klibi ön, sağ, arka, sol açıdan izleyin. Sorunlu kareyi "Ekran görüntüsü kaydet"
  ile alıp `kontrol/` klasörüne koyun.
- "Kendi etrafında döndür" ile dokunun yan ve arkada nasıl göründüğüne bakın.
- "İskeleti göster" ile kemiklerin ağın içinde oturup oturmadığını görün.
- Tek seferlik klipler bitince `bosta_klip` (bekleme) klibine döner. Geçiş süresi kaydırıcıdan.

### 5. Dudak senkronu

Ses kayıtlarını `ses/kayit/<id>.wav` olarak koyun (16 bit PCM). Sonra:

```
python araclar/lipsync_uret.py --replikler ses/replikler.json
```

Her replik için `ses/zaman/<id>.json` üretilir. Görüntüleyicide "Konuşma" bölümünden
replik tıklanınca ses çalar, ağız zaman çizelgesine göre hareket eder, üstüne
`klip` alanındaki vücut klibi biner.

Ses yoksa "Ses dosyası yoksa metinden zamanla" seçeneğiyle tahmini süreyle izlenir.
Zaman çizelgesi de yoksa ses genliğinden ağız açılır (eski davranış).

`ses/kayit/selam-01.wav` şu an yapay bir test sinyalidir, gerçek kayıtla değiştirin.

### 6. Doku tamamlama

Bu adım betikle çözülmüyor. Yan ve arka referans görsel gerekiyor; üretim betiği
gelince buraya eklenecek. Mevcut aynalama sınırı `glb_incele.py` çıktısındaki
`uv_kapsama_orani` ve `gri_alan_orani` ile ölçülür.

### 7. Uygulamaya alma

`cikti/mm-asistan-muhammed.glb` dosyasını `C:\MakeMaker\01-proje\public\models\`
altına kopyalayın. `karakter.json` içindeki aşama durumlarını `tamam` yapın.

## Kabul ölçütleri

`karakter.json` → `kabul_olcutleri`. Özetle: kol kemiğinden uzak köşe 0, normalize
dışı köşe 0, kopuk küçük parça en çok 5, UV kapsama en az 0.35, her klip her
açıdan gözle onaylı.

## Uygulama tarafına aktarılacaklar

Uygulama (three.js) tarafında yapılacak değişiklikler `web/goruntuleyici.js` ve
`web/lipsync.js` içinde çalışır halde duruyor:

- Klip geçişi `crossFadeFrom`, tek seferlik kliplerin bitince boşa dönmesi.
- Klip başına yüz katmanı (`yuz_katmani`), Smile ve MouthOpen taban değerleri.
- `DudakSenkronu` sınıfı: zaman çizelgesi varsa onu, yoksa ses genliğini kullanır.
  Uygulamadaki mevcut genlik tabanlı kodun yerine doğrudan bu sınıf konabilir.

## Bilinen sınırlar

- Stilize karakter; fotoğraf benzeri değil. Eller parmaksız.
- Göz kırpma boyalı gözün dikey sıkışmasıyla yapılır; ayrı göz kapağı yok.
- Blender'ın seyrek (sparse) morph kaydı three.js'te deriyi bozuyor;
  `blender_modelle.py` bu yüzden `export_try_sparse_sk=False` kullanır.
- Eski Hunyuan/UniRig modeli için teşhis ve ağırlık onarım betikleri duruyor
  (`glb_incele.py`, `agirlik_duzelt.py`); diğer karakterlerde gerekirse kullanılır.

## Örnek deneme

Gerçek dosya olmadan zincirin çalıştığını görmek için:

```
python araclar/ornek_glb_uret.py girdi/ornek-rigli.glb
python araclar/glb_incele.py girdi/ornek-rigli.glb -o kontrol/ornek-rapor
python araclar/agirlik_duzelt.py girdi/ornek-rigli.glb cikti/ornek-rigli-duzeltilmis.glb
python araclar/glb_incele.py cikti/ornek-rigli-duzeltilmis.glb -o kontrol/ornek-duzeltilmis-rapor
```

İlk raporda 93 köşe kol taşması uyarısı çıkar, ikincisinde uyarı kalmaz.
`kontrol/ornek-goruntuleyici.png` bu örneğin görüntüleyicideki hali.
