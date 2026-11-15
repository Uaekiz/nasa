# FLEX frontend–backend entegrasyonu

Sonraki genişletme: [Çoklu kaynak entegrasyonu](multi-source-integration.md).
Bu belge ilk FLEX aşamasının kontrol kaydıdır; güncel toplamlar ve restart
komutları sonraki genişletme belgesindedir.

15 Kasım 2026 kontrolü: çalışan backend veritabanına 274 FLEX deneyi aktarıldı.
İkinci aktarım `created=0, updated=274` döndürdü; deney kimlikleri ve
`core.experiment_id_sequence` değişmedi. Commit, push veya merge yapılmadı.

## Aktarım

Repo kökünden PowerShell:

```powershell
# Mevcut RAG sanal ortamındaki psycopg 3 kullanılabilir; RAG servisi çağrılmaz.
.\rag-service\.venv\Scripts\python.exe data/etl/load_experiments.py --investigation PSI-69 --dry-run
.\rag-service\.venv\Scripts\python.exe data/etl/load_experiments.py --investigation PSI-69

# Çalışan API + DB + kaynak hücreleri; isteğe bağlı tekrar aktarım kontrolü:
.\rag-service\.venv\Scripts\python.exe data/etl/verify_flex.py --check-reimport
```

Ayrı ETL ortamı tercih edilirse:

```powershell
python -m venv data/etl/.venv
.\data\etl\.venv\Scripts\python.exe -m pip install -r data/etl/requirements.txt
.\data\etl\.venv\Scripts\python.exe data/etl/load_experiments.py --investigation PSI-69
```

DB ayarları `PYROSPHERE_DB_HOST`, `PYROSPHERE_DB_PORT`, `PYROSPHERE_DB_NAME`,
`PYROSPHERE_DB_USER`, `PYROSPHERE_DB_PASSWORD` ile verilir. Varsayılan geliştirme
bağlantısı backend `application.yaml` / Docker Compose ile aynı olan
`localhost:5433/pyrosphere` bağlantısıdır. API doğrulayıcısının varsayılanı
`http://localhost:8080/api/v1`; `--api-base` ile değiştirilebilir.

Importer kendiliğinden servis başlangıcında çalışmaz. Yalnızca `PSI-69` kabul eder;
diğer araştırmaların katalog, deney veya ölçümlerini oluşturmaz. Mevcut ETL'nin
kimlik/fingerprint ve ölçüm aktarımı tamamlanmıştır. Okuma için RAG'in mevcut
`csv_loader.extract_records` fonksiyonu kullanılır; RAG çıktısına/indeksine yazılmaz.

`rag-service/source_manifest.json` içindeki kaynak kimliği, cp1252 kodlama,
SHA-256, kolonlar ve 274 kayıt koşulu doğrulanır. Backend manifestinin kaynak
yolu aynı dosyaya yönelir. `/files` ile sunulan kopyanın dosya özeti de denetlenir.

Katalog, kalıcı kimlik atama, koşullar, ölçümler, bulgular ve uyarılar tek
transaction içindedir. Kaynak kapsamındaki advisory lock eşzamanlı importer'ları
sıralar. Mevcut fingerprint mevcut deney kimliğini korur; aynı kaynak/satırda
kimlik çelişkisi varsa işlem geri alınır. Yeni kimlikler mevcut monoton
`<investigationId>:run-NNNN` kuralıyla atanır; geride kalmış sıra mevcut en büyük
kimliği yeniden kullanmaz. Ölçüm/bulgu alt satırları transaction içinde yenilenir;
onların BIGSERIAL kimlikleri kalıcı deney kimliği değildir.

Orijinal hücre dizisi `core.experiments.raw_row`, satır numarası
`source_row_number`, orijinal başlık sırası/kodlama/dosya özeti ise
`core.sources.metadata` içinde saklanır. Ölçüm ve bulguların `raw_value` alanları
orijinal metni korur. Basınç dönüşümü `mmHg * 0.133322 = kPa` olarak, orijinal
değer/birim/yöntemle saklanır. Boş ve en dash hücrelerinden sayı üretilmez.
`Burning rate; mm` birimi `mm` olarak korunur, dolu hücreleri
`REQUIRES_REVIEW` olur; `mm/s` dönüşümü veya varsayılan grafik karşılaştırması yoktur.

## Frontend davranışı

- Araştırmalar ve deney özetleri backend'den gelir. Yerel deney/kaynak listeleri
  ve hata durumundaki yerel karşılaştırma/sohbet cevapları kaldırılmıştır.
- Liste özet DTO'sunu, kullanıcı açtığında detay isteği detay DTO'sunu kullanır.
  `FindingView.name/value/rawValue/sourceId` render edilir.
- Araştırma/yakıt filtreleri ve sayfalama çalışır. Seçimler başlangıçta boştur.
  Karşılaştırma için 2–3 deney seçilir; seçimler sayfalar arasında korunur ve
  listedeki seçim düğmelerinden kaldırılabilir.
- Grafikler `series.metric/unit/points` kullanır. Seyrek noktalar ve differences
  deney kimliğine göre hizalanır; eksikler sıfırla doldurulmaz. Uyarılar ve
  `INSUFFICIENT_DATA` durumu görünürdür.
- Kaynak kartı açıldığında `/sources/{sourceId}` çağrılır; gerçek `documentUrl`
  kullanılır. DOI, URL veya satır numarası uydurulmaz. Vite `/files` proxy'si
  kaynak indirmesini backend'e iletir; ayrı API origin'i de desteklenir.
- API hataları/boş sonuçlar/yükleme ayrı görünür. Chat hatası yeni bir model
  cevabı oluşturmaz; geçmiş yalnızca başarıyla alınmış yanıtları içerir.
- Simülasyon girdileri ve grafikler ayrı ekranda örnek model çıktıları olarak
  belirtilir. Simülasyon senaryoları deney ekranına veya RAG isteğine aktarılmaz.

## Kontroller ve sonuçlar

| Kontrol | Sonuç |
| --- | --- |
| İlk aktarım | 274 yeni deney; yalnızca 1 araştırma ve 1 kaynak |
| İkinci aktarım | 0 yeni, 274 güncellenen; kimlikler/sayı/sıra değişmedi |
| Kaynak satırları | 274 satırın tüm orijinal hücreleri DB ile eşleşti |
| Detay örnekleri | 7 kayıt: ilk/son test, boş saat, en dash ve yaklaşık süreler |
| Liste | 14 sayfa, 274 benzersiz özet; sıralama ve son sayfa kontrol edildi |
| Yakıt filtreleri | Methanol 157, Heptane 117; boş ve geçersiz filtreler kontrol edildi |
| Karşılaştırma | Gerçek SQL değerleriyle eşleşti; Burning rate hariç, eksikler uyarılı |
| Kaynak indirme | API üzerinden indirilen CSV SHA-256 manifestle aynı |
| RAG | Salt okunur kontrolde 274 kaynak/satır/test eşlemesi aynı |
| Importer testleri | 7 geçti; transaction rollback, tekrar aktarım, sıra ve kaynak hücreleri |
| Backend testleri | 5 geçti; context + 4 karşılaştırma testi |
| RAG CSV loader testleri | 12 geçti |
| Frontend | Build, lint ve 6 Node testi geçti |
| Canlı tarayıcı | Liste, boş başlangıç seçimi, detay/bulgular, kaynak dosyası, karşılaştırma, sayfalama, boş filtre, API ve chat hata akışları geçti; yakalanmamış JS hatası yok |

DB ölçüm durumu: 1.632 VERIFIED koşul, 12 MISSING koşul;
465 VERIFIED ölçüm, 258 REQUIRES_REVIEW ölçüm, 99 MISSING ölçüm.
Toplam 2.466 koşul/ölçüm satırı ve 274 nitel bulgu vardır.

Tekrar kontrol komutları:

```powershell
$env:PYROSPHERE_IMPORT_TEST_DB = '1'
.\rag-service\.venv\Scripts\python.exe -m unittest discover -s data/etl -v
# DB testleri yalnızca UUID ile adlandırılan geçici test şemalarını oluşturur/siler.
# Test bağlantısı için CREATE SCHEMA yetkisi gerekir; core ve RAG tablolarına yazılmaz.

npm.cmd --prefix frontend run build
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend test

Push-Location rag-service
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_csv_loader.py -v
Pop-Location

Push-Location backend
.\mvnw.cmd test
Pop-Location

# Mevcut servisleri kullanan Windows Edge kontrolü; başka uygulama servisi başlatmaz:
Push-Location frontend
node tests/browser-smoke.mjs
Pop-Location
```

Bu makinede Maven wrapper `.Target[0]` için PowerShell null hatası verdi.
Backend testleri kurulu Maven 3.10.0 ile aşağıdaki alternatifle çalıştırıldı:

```powershell
$mavenBin = Get-ChildItem 'C:/Users/hüseyin/.m2/wrapper/dists/apache-maven-3.10.0' -Recurse -Filter mvn.cmd | Select-Object -First 1 -ExpandProperty FullName
& $mavenBin -f backend/pom.xml '-Dmaven.repo.local=C:/Users/hüseyin/.m2/repository' '-Daether.syncContext.named.factory=rwlock-local' -o test
```

## Yeniden başlatma ve kalan sınırlamalar

Çalışan frontend/backend/RAG süreçleri durdurulmadı; aynı portta ikinci servis
başlatılmadı. Backend üretim kodu ve şeması değişmedi; backend/RAG restart veya
yeniden indeksleme gerekmez. Canlı Vite sunucusu değişiklikleri aldı ve yeni
`/files` proxy'si tarayıcı kontrolünde çalıştı. Frontend'i elle yeniden başlatmak
gerekirse mevcut frontend sürecini kendiniz kapattıktan sonra repo kökünde
`npm.cmd --prefix frontend run dev` çalıştırın.

Burning rate birimi kaynakta belirsiz kalıyor; bilimsel doğrulama olmadan sayısal
karşılaştırmaya açılmamalıdır. Diğer araştırmalar bu aktarımın dışında kalır.
Vite build mevcut büyük bundle uyarısını veriyor; build başarılıdır. Backend
context testi mevcut JDK 25 / Mockito agent uyarılarını veriyor; 5 testin tamamı
başarılıdır. Bu çalışmada yeni bir Ollama üretimi tetiklenmedi; RAG indeksi ve
kaynak eşleşmeleri salt okunur doğrulandı, frontend chat hata yolu test edildi.

Önceden değiştirilmiş `rag-service/app/retrieval.py` ve mevcut `databases/`
dosyaları değiştirilmedi.
