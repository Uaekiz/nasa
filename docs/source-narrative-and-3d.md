**Kaynaklı anlatım, kısmi tarihler ve deney detayında 3B görünüm — 15 Kasım 2026**

Değişiklikler mevcut çok kaynaklı entegrasyonun üzerine uygulandı. Commit, push, merge, üretim verisine yeniden aktarım veya yeniden indeksleme yapılmadı. Çalışan frontend, backend ve RAG süreçleri durdurulmadı; ikinci uygulama servisi başlatılmadı. Tarayıcı kontrolleri kendi oluşturdukları gizli Edge sürecini kapatır.

Ham alan sıralamasının nedeni iki aşamalıydı: `generation_input` modele serbest metin yerine birebir hücre JSON'u çıkarttırıyor, `render_validated_answer` ise bu alanları başlık/değer ve noktalı virgüllerle birleştiriyordu. JSON sınırı korundu. Yeni `answer_narrative.py`, yalnızca doğrulanmış özgün hücreleri kısa İngilizce cümlelere yerleştirir. Her olgusal cümlenin kendi `[S#]` atfı vardır. İlgili alanlar birlikte anlatılır; neden, tanım, risk, öneri veya hesaplama eklenmez. Sayılar, ham niteleyiciler ve başlıktan gelen birimler korunur. Tanımı kaynakta bulunmayan Rt/R0 gibi terimler açıklanmış gibi gösterilmez.

Eksik hücreler doğal dille açıklanır. `Burning rate; mm` yorumlanmaz ve mm/s yapılmaz. SAFFIRE-III koşulları anlatılır; yanma ölçümü istendiğinde kaynağın bunu içermediği açıkça söylenir. Araştırma filtresi ile soruda adı geçen araştırma çelişirse kaynak veya model cevabı döndürülmez. Sayısal analiz backend sınırında kalır.

Model JSON'u, alanı, atfı veya hücre değerini doğrulatamazsa reddedilir. Yanıt, özgün hücrelerin doğrudan kaynaklı aktarımına döner ve bunu İngilizce olarak açıklar: `PARTIAL`, `modelTier: NONE`, `modelUsed: null`, `MODEL_OUTPUT_REJECTED`. Denemenin gerçek süresi korunur. Frontend bunu “Model çıktısı reddedildi · Doğrudan kaynak aktarımı” diye gösterir; “Çağrılmadı” veya başarılı model metni olarak sunmaz. Bağlantı ve zaman aşımı hataları API hatası olarak kalır.

**Tarih akışı ve korunan kayıtlar**

SAME-R CSV → importer → DB zincirinde veri zaten korunuyordu. `experiment_date` boş, `date_raw` doluydu. Detay DTO'su ham tarihi taşıyordu; liste sorgusu ve özet DTO'su taşımıyordu. Listeye geriye uyumlu `dateRaw` eklendi. Liste ve detay aynı tarih göstericisini kullanır. DB şeması ve kayıtlar değiştirilmedi.

| Kayıt | date | dateRaw | Yeni gösterim |
|---|---|---|---|
| SAME-R 51 | null | 21-Jul | 21-Jul (yıl kaynakta yok) |
| SAME-R 51a | null | 22-Jul | 22-Jul (yıl kaynakta yok) |
| FLEX 1 | 2009-03-05 | 3/5/2009 | 2009-03-05 |
| SAFFIRE-III S1/S2 | null | null | Kaynakta belirtilmemiş |

Araştırma sayıları aynı: FLEX 274, BASS-II 129, SAFFIRE-III 2, SAME-R 109; toplam 514 deney/numune ve 643 bağımsız kaynak satırı. Tüm 514 kimlik ve satır parmak izi başlangıç kaydıyla karşılaştırıldı, aynı kaldı. Eski FLEX indeksinin 274 kaydı, içerik/vektör/zaman damgası ve durum hash'leri aynı kaldı. Çok kaynaklı indeks READY durumunda; kaynak dosyaları ve manifestler değişmedi.

**Kaynak verisinden 3B görünüm**

`ThreeViewport.jsx`, kamera/OrbitControls, yakınlaştırma, sıfırlama, WebGL alternatifi, yeniden boyutlandırma ve kaynak temizliğini ortaklaştırır. Ana simülasyonun mevcut shader ve güncelleme mantığı `scenes/createSimulationScene.js` içine taşındı; simülasyon, duraklatma ve risk açıklaması korundu. Deney görünümü ayrı `createExperimentScene.js` ve `experimentViewModel.js` kullanır. Bu yolun simülasyon telemetrisi, risk motoru veya model cevabına bağımlılığı yoktur.

Detayda başlık/özet altında ve ölçümler üstünde gösterilir. Deney kimliği değişince bileşen yeniden kurulur; önceki sahne taşınmaz. Kesin, VERIFIED, kaynak kimliği bulunan boyutlar kullanılır. Eksik/yaklaşık/incelenmesi gereken ölçüm kesin boyuta dönüştürülmez.

| Araştırma | Görünüm ve sınır |
|---|---|
| FLEX | Başlangıç çapı bilinen küre biçiminde damlacık temsili. Çap eksikse açıkça ölçekli olmayan simge. Sönme çapı başlangıç çapı yerine kullanılmaz. |
| BASS-II | Açıkça “wide/thick” diye etiketlenmiş kesin ölçülerden yalnızca genişlik çizgisi veya kesit. Tam boyut yoksa film/rod/katı için ölçekli olmayan farklı simgeler. Etiketsiz inch kesirlerinden çap çıkarılmaz. CSV ve workbook ölçümleri birleştirilmez. Fan/Air display fiziksel hız sayılmaz. |
| SAFFIRE-III | Kaynaktaki uzunluk/kalınlık/genişlik oranları. Doğrulanmış 30 cm/s ve Concurrent/Opposed etiketlerinden şematik göreli akış okları. Kamera veya alev yayılım yönü çıkarılmaz; ok uzunluğu hız ölçeği değildir. Yanma sonucu üretilmez. |
| SAME-R | Geometri eksikse nötr numune işareti. Giriş hızı metin olarak korunur; yön bilinmeden ok çizilmez. Kayıt açık alev deneyi sayılmaz. |

Alev animasyonu eklenmedi. Kaynaklar 3B alev şekli, rengi, sıcaklığı ve zamana bağlı davranışı belirlemiyor. Kullanılan parametreler, birimler, ham hücreler, kaynak kimlikleri ve eksik bilgiler görünüm altında listelenir. Gerekli açıklama aynen yer alır: “Kaynak koşullarını gösteren temsili 3B görünüm; deney videosu veya doğrulanmış yanma tahmini değildir.” Statik görünüm yalnızca etkileşim/resize sırasında çizilir. Kapanışta RAF, OrbitControls olayları, ResizeObserver, geometri, materyaller, dokular, render listeleri, WebGL bağlamı ve canvas temizlenir.

**Kontrol sonuçları**

| Kontrol | Sonuç |
|---|---|
| Frontend `npm run lint` | Geçti |
| Frontend `npm test` | 12/12 geçti |
| Frontend `npm run build` | Geçti; mevcut büyük bundle uyarısı sürüyor (~1.98 MB sıkıştırılmamış) |
| Backend Maven test | 10/10 geçti; gerçek DB'den liste/detay ve MockMvc JSON tarih kontrolü dahil, yeni HTTP sunucusu açılmadı |
| Importer test | 10/10 geçti; geçici şemalarda transaction/tekrar aktarım, kimlikler ve kısmi tarih kontrolü dahil |
| RAG unittest | 119 test: 114 geçti, 5 ayrıcalıklı/izole ortam testi atlandı |
| Tüm kaynak anlatımları | 643 özgün satırın özet hücreleri ve atıfları karşılaştırıldı |
| Gerçek DB + ASGI kaynak aktarımı | 14 senaryo geçti; açıkça reddedilen model çıktısı test düzeneği kullanıldı. Bu sonuç canlı model başarısı değildir. |
| Mevcut tarayıcı smoke | Liste, dört araştırma filtresi, sayfalama, detay, FindingView, kaynak indirme, karşılaştırma, boş veri ve API/chat hata durumları geçti |
| Yeni tarayıcı senaryoları | Döndürme, yakınlaştırma, sıfırlama, deney geçişi, FLEX eksik çap, BASS genişlik/rod, SAFFIRE akış/boyut, SAME-R kısmi tarih, 390 px görünüm, WebGL alternatifi, RAF/bağlam temizliği, ana simülasyon ve dürüst geri dönüş etiketi geçti |

Çalışan backend henüz eski liste DTO'sunu sunuyor. Tarayıcıda yeni `dateRaw` sözleşmesi, gerçek detay yanıtlarındaki ham tarihler kullanılarak yalnızca test trafiğine eklenen özet yanıtlarla kontrol edildi. Üretim frontend'ine yerel tarih düzeltmesi veya sahte veri eklenmedi. Yeni backend SQL/DTO'su gerçek DB ve MockMvc ile ayrıca doğrulandı. Eksik çap/rod görselleri de gerçek detay yanıtlarıyla test edildi.

Canlı Ollama kontrolü ilk soruda HTTP 503 `MODEL_UNAVAILABLE` verdi: `localhost:11434` erişilemiyordu; son bağlantı kontrolü de başarısızdı. Bu çalışmada yeni anlatım için canlı model/semantik sorgu başarısı iddia edilmiyor. Model cevabı bozulduğunda kullanılacak güvenli yol gerçek DB ile test edildi. Ollama başlatılmadı, model indirilmedi; çalışan süreçlere müdahale edilmedi.

Yerel ayrıntılı çıktılar: `backend/target/ux-test-run.log`, `backend/target/import-date-tests.log`, `backend/target/browser-smoke.log`, `backend/target/source-view-browser.log`, `backend/target/source-view-mobile.png`, `rag-service/.local/nasa-provenance/narrative-unit-tests.log`, `source-fallback-checks.json`, `ux-preservation-checks.json`, `narrative-live-checks.log`.

**Önce/sonra örnekleri**

Bunlar özgün hücrelerden doğrulanmış renderer çıktılarıdır; bu oturumda başarılı canlı model üretimi olarak sunulmaz. Atıfların kaynak kimliği/satırı aşağıdadır.

Önceki biçim örneği:

> FLEX test 70 (FLEX Identifier 193F001): Fuel: Heptane; Test end: Extinction; Burn time; s: 1.6; Burning rate; mm: 0.41. [S1]

Yeni çıktı:

> FLEX test 70 (FLEX Identifier 193F001) used Heptane. [S1] The recorded outcome was Extinction, and the reported burn time was 1.6 s. [S1] The “Burning rate; mm” column records 0.41; its rate unit is ambiguous, so the value is left uninterpreted. [S1]

Burada S1, `PSI-69:experimental-table:v1`, CSV satırı 71'dir.

Önce: SAME-R 51a listede “Belirtilmemiş”, detayda yalnızca `22-Jul` gösteriyordu. Yeni liste/detay: `22-Jul (yıl kaynakta yok)`. İngilizce tarih cevabı:

> The source entry is SAME-R test 51a. [S1] The date is recorded as 22-Jul; no year is given in the source. [S1]

Burada S1, `PSI-101:experimental-table:v1`, CSV satırı 3'tür.

SAFFIRE-III koşul cevabı:

> SAFFIRE-III sample S1 lists the material as “SIBAL Fabric”. [S1] The sample is listed as .33 cm thick, 94 cm long and 40.6 cm wide. [S1] The table records an air flow of 30 cm/s and labels the direction “Concurrent ”. [S1] This source lists sample conditions, but does not provide burn time, burning rate or a measured outcome. [S1]

Burada S1, `PSI-100:experimental-table:v1`, CSV satırı 2'dir. `Concurrent ` hücresinin sondaki boşluğu dahil ham değer korunur. Yanma ölçümü sorusuna `INSUFFICIENT_EVIDENCE` döner.

**Çalıştırma ve kalan iş**

Yeni tarih DTO'su için backend, yeni anlatım için RAG yeniden başlatılmalı. Bunu mevcut servisleri kendi terminal/IDE'nizden kapattıktan sonra yapın; aşağıdaki komutları mevcut portlar doluyken ikinci servis açmak için kullanmayın. Vite HMR frontend değişikliklerini aldı; frontend restart gerekmiyor. DB restart, migration, yeniden aktarım veya yeniden indeksleme gerekmiyor.

Backend, repo kökünden ayrı terminalde (mevcut wrapper yerine testte kullanılan kurulu Maven):

```powershell
$mavenBin = Get-ChildItem "$env:USERPROFILE/.m2/wrapper/dists/apache-maven-3.10.0" -Recurse -Filter mvn.cmd | Select-Object -First 1 -ExpandProperty FullName
Push-Location backend
& $mavenBin "-Dmaven.repo.local=$env:USERPROFILE/.m2/repository" '-Daether.syncContext.named.factory=rwlock-local' spring-boot:run
Pop-Location
```

RAG, repo kökünden diğer terminalde:

```powershell
Push-Location rag-service
$env:RAG_DB_SCHEMA='rag'
$env:RAG_INDEX_NAME='nasa_multi_v1'
$env:RAG_CORPUS_MODE='multi'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Pop-Location
```

Ollama'yı mevcut kurulumunuzdan erişilebilir hale getirdikten sonra, model indirmeden yeni modüllerin gerçek DB/Ollama kontrolü (`rag-service` klasöründe):

```powershell
.\.venv\Scripts\python.exe -m app.multi_checks
# Backend ve RAG restart sonrasında mevcut HTTP servisini de kontrol eder:
.\.venv\Scripts\python.exe -m app.multi_checks --base-url http://127.0.0.1:8000
```

Yerel regresyon komutları:

```powershell
# Repo kökünde
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
$env:PYROSPHERE_IMPORT_TEST_DB='1'
.\rag-service\.venv\Scripts\python.exe -m unittest discover -s data/etl -v
Push-Location backend
& $mavenBin "-Dmaven.repo.local=$env:USERPROFILE/.m2/repository" '-Daether.syncContext.named.factory=rwlock-local' '-Ddebug=false' '-Dlogging.level.root=WARN' -o -e test
Pop-Location
Push-Location rag-service
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m app.multi_checks --reject-model-output
Pop-Location
Push-Location frontend
node tests/browser-smoke.mjs
node tests/source-view-browser.mjs
Pop-Location
```

Reddetme düzeneği Ollama çıktısını bilerek geçersiz sayar; kaynak aktarımını test eder ve model başarısı olarak raporlamaz. İkinci tarayıcı senaryosu bu ASGI kontrolünün yerel raporunu test yanıtı olarak kullanır. Gerçek model/semantik kontrolü, Ollama erişimi sağlandıktan sonra yukarıdaki normal komutla tamamlanmalıdır.
