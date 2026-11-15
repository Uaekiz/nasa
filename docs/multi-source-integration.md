# Çoklu NASA kaynak entegrasyonu

15 Kasım 2026. Aktarım ve yeni indeks hazırdır. Çalışan backend/RAG süreçleri
durdurulmadığı için yeni chatbot kapsamının ağ endpointlerinde etkinleşmesi
backend ve RAG'in kullanıcı tarafından yeniden başlatılmasını gerektirir.

## Kaynaklar ve gerçek kapsam

| Araştırma | Backend kaydı | RAG kanıt satırı | Kaynak |
| --- | ---: | ---: | --- |
| FLEX / PSI-69 | 274 | 274 | Korunan CSV |
| BASS-II / PSI-25 | 129 | 258 | 129 CSV satırı + 129 bağımsız Excel satırı |
| SAFFIRE-III / PSI-100 | 2 | 2 | İki numune/koşul satırı; sonuç ölçümü yok |
| SAME-R / PSI-101 | 109 | 109 | CSV; `51` ve `51a` ayrı kayıt |
| Toplam | 514 | 643 | 5 kaynak |

514, uygulamanın deney/numune kaydı sayısıdır. SAFFIRE-III satırları iki
gerçekleşmiş yanma sonucu veya iki ölçüm serisi olarak yorumlanmaz.

Dört aday dosyanın tamamı doğrulandı. NASA PSI'nin halka açık repo API'sinde
araştırma kimliği/dosya adı/sürümü incelendi; resmi indirme endpointinden alınan
baytlar yerel kopyalarla SHA-256 düzeyinde birebir eşleşti. Dosya adlarına veya
Excel yazar alanına dayanarak köken iddiası üretilmedi. Mevcut FLEX dosyası da
aynı yöntemle tekrar doğrulandı.

Birincil kataloglar:

- [BASS-II / PSI-25](https://psi.nasa.gov/physci/repo/data/investigations/PSI-25), DOI `10.60555/4qc4-de67`.
- [SAFFIRE-III / PSI-100](https://psi.nasa.gov/physci/repo/data/investigations/PSI-100), DOI `10.60555/040q-4h36`.
- [SAME-R / PSI-101](https://psi.nasa.gov/physci/repo/data/investigations/PSI-101), DOI `10.60555/2np7-jv14`.

İncelenen bayt özetleri, kalıcı indirme/metaveri adresleri, başlıklar ve kodlama
`rag-service/source_catalog.json` içinde sabittir. BASS-II CSV UTF-8 BOM içerir;
`utf-8-sig` ile okunur. Diğer iki yeni CSV UTF-8, FLEX cp1252, Excel ise OOXML'dir.

SAFFIRE-III CSV'si **239 bayt ve iki satır** olarak NASA indirmesiyle aynıdır;
yerel kopya kesilmemiştir. Ancak yayımlanan bu küçük tablo yalnızca malzeme,
boyutlar, akış, yön ve kamera etiketlerini içerir. Tam deney sonuçları dosyası
değildir; yanma süresi, yanma hızı, tarih veya sonuç üretilmedi.

BASS-II Excel'i NASA'daki `PSI-25_Science Documents_BASS-II_Test.Matrices.xlsx`
dosyasıyla aynıdır. Altı sayfadaki kayıtlar: Bhattacharjee 22, Ferkul 4, Miller 20,
Olson 27, Fernandez-Pello 27, T'ien 29. CSV ve Excel arasında 129 test kimliği +
araştırmacı eşleşmesi vardır. Ham metin farkları malzemede 53, fan gösteriminde
89, hava gösteriminde 85 hücredir; bazı gaz hücrelerinde de Excel'in uzun ondalık
gösterimleri farklıdır. Bunlar eşitlenmedi veya birbirinin yerine yazılmadı.
Excel tarih seri değerleri, hücre tipleri, stilleri, adresleri ve varsa formüller
ayrı saklanır. [Kaynak denetimi](local-source-audit.json) örnek farkları içerir.

## Backend

Mevcut importer genişletildi. `--investigation PSI-69` komutu çalışmaya devam eder;
`--all-verified` dört araştırmayı ve beş kaynağı açıkça seçer. Tek transaction,
kaynak kilidi, mevcut fingerprint ve kalıcı araştırma sırası korunur. İkinci
aktarım hiçbir yeni deney üretmedi; bütün deney kimlikleri, sayılar ve sıra
değerleri değişmedi. 274 FLEX kimliği önceden alınan temel listeyle aynıdır.

`V3__source_rows.sql` eklemeli migration'ı `core.experiment_source_rows` tablosunu
oluşturur. CSV başlıkları/hücreleri ve Excel sayfa/satır/hücre metaverisi burada
ayrı kaynak satırları olarak saklanır. Ana CSV deneylerinin `raw_row` alanları
korunur. Workbook satırları yalnızca doğrulanan test kimliği + PI eşleşmesiyle
mevcut BASS-II deneylerine bağlanır; **ikinci 129 deney oluşturulmaz**. Workbook
malzeme bulguları ayrı `sourceId` ile görünür; sayısal workbook okumaları CSV
ölçümlerinin üzerine yazılmaz veya onlarla ortalanmaz. Toplam 643 kaynak satırı
ve beş erişilebilir kaynak dosyası vardır.

Importer migration'ı kendi transaction'ında idempotent uygular; Flyway aynı
eklemeli migration'ı backend context testinde kaydetti. Var olan V1/V2 değiştirilmedi.

Koşullar/birimler araştırmaya göre eşlenir. BASS fan/air/gain göstergeleri fiziksel
hız veya süre sayılmaz, `REQUIRES_REVIEW` kalır. Negatif gaz okumaları ham olarak
saklanır ve doğrulanmış karşılaştırmalara alınmaz. `% by vol` değerlerinden mol
kesri üretilmez. SAME-R'nin yılı olmayan tarihleri `date: null` ve `dateRaw` ile
korunur. SAFFIRE boyutlarının kaynak hücrelerindeki açık `cm` birimi `mm`'ye
belgeli çevrilir; kaynak değer/birim/yöntem korunur. FLEX Burning rate belirsizliği
aynen korunur. Karşılaştırma ve chat sayısal bağlamı, `>500` gibi sınırları tam 500
olarak hesaplamaz; yalnızca VERIFIED + EXACT/APPROXIMATE tek değerler kullanılır.

## RAG

Eski `rag.index_state` ve `rag.evidence_records` tabloları değiştirilmedi. Eski
274 kaydın içerik, vektör ve zaman damgası özetleri işlem öncesi/sonrası aynıdır.

Uygulama rolünün yeni şema oluşturma yetkisi bulunmadığından, yetki artırmadan
mevcut sahipli `rag` şemasında **ayrı indeks tabloları** oluşturuldu:

```text
rag.index_state_nasa_multi_v1
rag.evidence_records_nasa_multi_v1
```

Yeni indeks 643 kayıtla READY'dir. Mevcut yerel `qwen3-embedding:0.6b` modeliyle
1024 boyutlu vektörler oluşturuldu; ikinci indeksleme 0 yeni embedding üretti ve
643 vektörü yeniden kullandı. Yeni model indirilmedi. Legacy ve yeni indekslerin
model/format metaverileri ayrıdır; uyumsuz indeks sessizce yeniden yazılmaz.

Kaynak satırı kimliği CSV'de `(sourceId, rowNumber)`, Excel'de
`(sourceId, sheetName, rowNumber)` içerir. Sayfaların aynı satır numaraları
birbirini ezmez. Katalog her yüklemede dosya özeti ve orijinal hücrelerle
doğrulanır. Farklı eski snapshot'ın üzerine yazılmaz. Küçülen/eksik kapsamlı
snapshot indeksleme başlamadan reddedilir; indeks sonlandırmada otomatik
kaynak/satır silme yoktur.

Yakıt/malzeme alanları, başlık takma adları, özet alanları ve araştırma adları
araştırmaya göre tanımlıdır. Varsayılan BASS-II cevabı CSV'den gelir; `workbook`
isteği Excel'i, `CSV and workbook` isteği iki kaynağı ayrı atıflarla getirir.
Çoklu araştırma isteği de her kaynağın kendi başlıklarıyla cevaplanabilir.
SAFFIRE-I/II, FLEX-2 ve elde olmayan araştırmalar açılmadı.

Üretim mevcut `qwen2.5:3b` modelini gerçekten çağırır. Şema, her atfın alanını ve
izin verilen orijinal hücre metnini sınırlar; çıktı yeniden hücre hücre doğrulanır.
Farklı kaynak şemaları ayrı çıkarım çağrılarıyla doğrulanır ve atıfları sonra
birleştirilir. Serbest model açıklaması, neden, risk veya öneri sunulmaz. Sayım,
ortalama, karşılaştırma ve uç değer soruları backend SQL gerektiren yol olarak
ayrılır; en yakın beş satırdan hesaplanmaz. Başarısız üretim hazır cevaba düşmez.

## Frontend ve etkinleştirme

Katalog mevcut backend kayıtlarından gelir. Chat seçenekleri backend kataloğu ile
`GET /api/v1/chat/capabilities` üzerinden iletilen hazır RAG kapsamının kesişimidir.
RAG'nin `/rag/v1/capabilities` endpointi orijinal dosyaları ve indeks durumunu
doğrulamadan kapsam döndürmez. İngilizce örnek sorular bu kapsamdan gelir;
tamamı gerçek yerel model çağrısıyla doğrulandı. Request dili `en` olur. API
hataları ve restart bekleyen kapsam açıkça görünür; eski yerel örnek cevap/katalog
geri dönüşü yoktur. Kaynak kartları Excel sayfa/satırını ve gerçek dosya linkini gösterir.

Yerel `.env` şu doğrulanmış indekse geçirildi; çalışan süreçler durdurulmadı:

```dotenv
RAG_DB_SCHEMA=rag
RAG_INDEX_NAME=nasa_multi_v1
RAG_CORPUS_MODE=multi
```

## Tekrar çalıştırma

Repo kökünde, servisleri durdurmadan çalıştırılabilen işlemler:

```powershell
.\rag-service\.venv\Scripts\python.exe data/etl/audit_sources.py
.\rag-service\.venv\Scripts\python.exe data/etl/load_experiments.py --all-verified --dry-run
.\rag-service\.venv\Scripts\python.exe data/etl/load_experiments.py --all-verified
.\rag-service\.venv\Scripts\python.exe data/etl/verify_sources.py --check-reimport

Push-Location rag-service
.\.venv\Scripts\python.exe -m app.stage_sources
.\.venv\Scripts\python.exe -m app.multi_index
.\.venv\Scripts\python.exe -m app.multi_checks
Pop-Location
```

`multi_checks` başka port/sunucu açmadan ASGI yolunu, gerçek PostgreSQL indeksini
ve gerçek yerel Ollama modellerini kullanır. Böylece çalışan eski RAG süreci
kapatılmadan yeni cevap yolu doğrulanabilir.

**Yeni HTTP kapsamı için önce mevcut RAG ve backend süreçlerini kendiniz yeniden
başlatın. Aşağıdaki başlatma komutlarını mevcut süreçler aynı portlarda çalışırken
ikinci kez çalıştırmayın.**

RAG için `rag-service` klasöründe:

```powershell
$env:RAG_DB_SCHEMA='rag'
$env:RAG_INDEX_NAME='nasa_multi_v1'
$env:RAG_CORPUS_MODE='multi'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Backend'i IDE'nizde mevcut başlatma ayarıyla yeniden başlatabilirsiniz. Bu
makinedeki wrapper null `.Target[0]` hatası nedeniyle kullanılan Maven alternatifi:

```powershell
$mavenBin = Get-ChildItem 'C:/Users/hüseyin/.m2/wrapper/dists/apache-maven-3.10.0' -Recurse -Filter mvn.cmd | Select-Object -First 1 -ExpandProperty FullName
Push-Location backend
& $mavenBin '-Dmaven.repo.local=C:/Users/hüseyin/.m2/repository' '-Daether.syncContext.named.factory=rwlock-local' spring-boot:run
Pop-Location
```

Frontend Vite değişiklikleri aldı. HMR açıkken restart gerekmez; elle yeniden
başlatılacaksa önce mevcut frontend sürecini kendiniz kapatıp repo kökünde
`npm.cmd --prefix frontend run dev` çalıştırın. Ollama/DB restart gerekmez.

İki servis yeniden başladıktan sonra:

```powershell
Invoke-RestMethod http://localhost:8080/api/v1/chat/capabilities
Push-Location rag-service
.\.venv\Scripts\python.exe -m app.multi_checks --base-url http://127.0.0.1:8000
Pop-Location
```

Kapsam yanıtı READY ve dört araştırma olmalıdır. Bu çalışmada eski çalışan RAG
yeni capabilities endpointini henüz tanımıyor (404); eski backend de proxy
endpointini henüz tanımıyor. Frontend bu durumu API hatası olarak gösteriyor.

## Doğrulama sonuçları

- Backend: 514 kayıt; ikinci aktarımda dört araştırmada da 0 yeni kayıt. Bütün
  kimlikler, sayılar ve sıralar sabit. 274 FLEX kimliği başlangıç listesiyle aynı.
- 643 kaynak satırının tüm başlıkları, hücreleri ve Excel hücre metaverileri
  orijinalleriyle eşleşti. Tüm beş kaynak endpointi ve indirilen dosya SHA'ları aynı.
- Her araştırmada sayfalama, yakıt filtresi, başka araştırma getirmeme, ilk/son
  detay ve karşılaştırma gerçek çalışan backend üzerinden kontrol edildi.
  [Backend kontrol sonuçları](multi-backend-checks.json).
- Importer: 9 test geçti; izole şema, ilk/tekrar aktarım, FLEX korunumu, ham
  kaynak hücreleri, geride kalmış sıra ve transaction rollback kapsamı.
- Backend: 8 test geçti; context/Flyway, karşılaştırma dışlamaları ve capabilities
  proxy'si. Bu testler ikinci bir HTTP servisi başlatmaz.
- RAG: 112 testin 107'si geçti; admin/provisioning gerektiren 5 isteğe bağlı test
  atlandı. Ek olarak 18 gerçek Ollama senaryosu yeni ASGI yolunda geçti: dört
  araştırma, iki BASS kaynağı, iki araştırmalı istek, anlamsal filtreler, kaynak
  hücreleri ve desteklenmeyen istekler. Yeni indeksin ikinci çalışması embedding üretmedi.
- Eski çalışan HTTP RAG endpointinde 9 FLEX regresyon senaryosu ayrıca geçti;
  çalışan sorular, yinelenen FLEX Identifier ve anlamsal Extinction filtresi korundu.
- Frontend: build/lint ve 7 test geçti. Canlı Edge kontrolünde dört araştırmanın
  kayıt filtreleri, boş başlangıç seçimleri, detay/bulgular, dosya açma,
  karşılaştırma, sayfalama, boş sonuç ve chat/API hata yolları geçti.

Yeni RAG HTTP servisine ve yeni backend proxy endpointine ağ üzerinden son smoke
kontrolü, kullanıcının yapacağı restart sonrasında yukarıdaki komutla yapılır.
Yeni RAG cevapları bu çalışmada gerçek DB/Ollama ile **in-process ASGI** üzerinden,
yeni backend proxy yolu ise MockMvc/RestClient sözleşme testleriyle doğrulandı;
çalışan servislerin yeni sürüme geçtiği iddia edilmez.

## Açık sınırlar

Aday dosyalardan kökeni doğrulanamadığı için dışarıda bırakılan yoktur. Ancak
SAFFIRE-III'ün yerelde olmayan ölçülmüş sonuçları, başka araştırmalar, kayıp PDF
raporu, fan kalibrasyonu, güvenlik/risk önerileri ve simülasyon çıktıları bu
kapsama eklenmedi. RAG'de doğrudan backend `experimentId` eşleme ve serbest
`analysisContext` yorumlama hâlâ kapalıdır; filtreler sessizce yok sayılmaz.
Kaynak test kimlikleri, araştırma ve kaynak kapsamı çalışır.

Mevcut büyük frontend bundle ve JDK/Mockito uyarıları sürüyor; testler/build geçti.
Commit, push veya merge yapılmadı. Ham CSV/Excel dosyaları ve FLEX
`source_manifest.json` içeriği değiştirilmedi.
