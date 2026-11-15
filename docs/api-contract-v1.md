# FlameScope - API ve Kimlik Sözleşmesi v1.0

Tarih: 14 Kasım 2026. Durum: ekibin uygulamaya başlayacağı önerilen ilk sözleşme.

15 Kasım eki: `GET /api/v1/chat/capabilities` backend üzerinden
`GET /rag/v1/capabilities` yanıtını iletir. Yanıt `status: READY`, `language: en`,
`items` içerir. Her öğe `investigationId`, `name`, `sourceIds`, `evidenceRows`,
`examples` alanlarını taşır. Yalnızca orijinal dosyaları ve hazır indeks durumu
doğrulanan kaynaklar listelenir; hata durumunda yerel katalog üretilmez.
CSV ve XLSX kanıtları ayrı kalır; XLSX atıfları gerçek `sheetName` ve `rowNumber`
kullanır. Ayrıntılar: [Çoklu kaynak entegrasyonu](multi-source-integration.md).

Bu belge ekip içi teknik anlaşmadır. Örneklerdeki kimlikler ve yanıt metinleri şemayı göstermek içindir; gerçek NASA kayıtlarının eşleştirilmesi tamamlandığı anlamına gelmez.

## 1. Sahiplik ve servis sınırları

| Bileşen | Sahip | Sorumluluk |
|---|---|---|
| React | Frontend arkadaş | Deney keşfi, filtreler, karşılaştırma, sohbet ve kaynak gösterimi |
| Spring Boot | Backend arkadaş | Deney veritabanı, veri aktarımı, SQL hesaplamaları, dış API ve RAG koordinasyonu |
| FastAPI + Ollama | RAG sahibi | Belge hazırlama, embedding, kaynak arama, yerel model seçimi ve kaynaklı cevap |

React yalnızca Spring Boot ile konuşur. Spring Boot, RAG servisini çağırır. RAG sahibi geliştirme sırasında kendi API'sini doğrudan test edebilir.

Sayısal hesaplamalar Java/SQL'de yapılır. RAG, belgeler ile backend'in doğrulanmış hesaplama sonuçlarını açıklar. Ana deney tablolarını yalnızca backend yönetir. RAG kendi pgvector şemasını/indeksini yönetir; ortak kimlikleri kullanır.

## 2. Yerel adresler ve yapılandırma

| Bileşen | Önerilen geliştirme adresi |
|---|---|
| React | http://localhost:5173 |
| Spring Boot | http://localhost:8080 |
| FastAPI | http://localhost:8000 |
| Ollama | http://localhost:11434 |

Backend kökü: `/api/v1`. RAG kökü: `/rag/v1`. Adresler ortam değişkenleriyle ayarlanır; kaynak koda sabitlenmez.

`localhost`, her kişinin kendi bilgisayarıdır. Servisler farklı bilgisayarlarda çalışacaksa yapılandırmada ilgili ekip bilgisayarının yerel ağ IP'si kullanılır. Docker konteynerleri arasında servis adları kullanılır. Tarayıcıdan erişim için backend CORS ayarı gerçek frontend adresiyle eşleşmelidir.

İlk yerel sürümde uygulama girişi/token akışı kapsam dışıdır. Yerel Ollama için sağlayıcı API key'i gerekmez. Veritabanı parolaları repoya girmez; `.env.example` yalnızca değişken adlarını ve örnek değerleri içerir.

## 3. Ortak kimlikler

| Alan | Biçim / örnek | Kural |
|---|---|---|
| investigationId | `PSI-25` | NASA araştırma kimliği, büyük harf |
| experimentId | `PSI-25:run-0001` | Backend'in bir kez atadığı, kalıcı ve araştırma kapsamında benzersiz uygulama kimliği |
| sourceTestId | `B1` | NASA dosyasındaki orijinal test kimliği; tek başına benzersiz varsayılmaz |
| sourceId | `PSI-25:summary-report:v1` | Manifestte tanımlanmış dosya/sürüm kimliği; buradaki v1 ekip içi kaynak sürümüdür |
| chunkId | `PSI-25:summary-report:v1:p104:c01` | RAG parçası; kaynak sürümüyle bağlantılı |
| requestId | UUID | Backend üretir, RAG'e aktarır ve yanıt/hatalarda geri döner |

`experimentId` her aktarımda satır sırasına göre yeniden üretilmez. Kaynak dosya, satır, tarih ve orijinal test kimliği eşleştirmesi kalıcı tutulur. Aynı dosyanın tekrar aktarılması yeni testler üretmez. Tek numuneye ait birden çok test ayrı kayıttır.

JSON alanları camelCase, teknik etiketler büyük harfli İngilizce enum olur. Açıklamalar için `language: "tr" | "en"` kullanılır; varsayılan `en`.

## 4. Veri ve eksik değer kuralları

- JSON sayıları sayı olarak gönderilir; `20 cm/s` gibi metinler normalize edilmiş sayısal alana yazılmaz.
- Kaynak hücrenin tam metni `rawValue` olarak korunur. Yaklaşık, eşik ve aralık bilgisi kaybolmaz.
- Ortak sayısal birimler: basınç `kPa`, hava hızı `cm/s`, uzunluk/çap `mm`, süre `s`, gaz bileşimi `mol/mol`, CO derişimi `ppm`. Kaynak hacim yüzdesinden mol kesrine eşleme belge ve gaz varsayımıyla doğrulanmadan yapılmaz; doğrulanmamış dönüşüm normalize edilmez.
- Birim dönüşümü yapılıyorsa orijinal değer/birim ve dönüşüm yöntemi korunur. Oksijen kesri UI'da 100 ile çarpılarak yüzde olarak gösterilebilir.
- Bilinmeyen değer `null` olur. Boş kaynak hücresi, `n/a` ve `none` gibi ifadeler `missingReason` ve `rawValue` ile ayrılır.
- `>500` tam 500 değildir. `11 to 3` tek bir sabit değer değildir. `insignificant`, `complete`, `acceleratory` gibi nitel sonuçlar sayıya çevrilmez.
- Tarih kesin biliniyorsa `YYYY-MM-DD`; yıl yoksa `date: null` ve `dateRaw` gönderilir. Tarih/saat dilimi uydurulmaz.
- Deney koşulu aralıklarından gerçekleşmiş testler türetilmez. Dipnotlar ve görüntü dosyası listeleri test sayılmaz.
- Belirsiz bilimsel alanlar orijinaliyle saklanır ve `REQUIRES_REVIEW` işaretlenir; varsayılan sayısal karşılaştırmaya katılmaz.

Ortak ölçüm nesnesi:

```json
{
  "name": "airflow",
  "value": null,
  "unit": "cm/s",
  "qualifier": "CHANGING",
  "startValue": 11,
  "endValue": 3,
  "rawValue": "11 to 3",
  "missingReason": null,
  "qualityStatus": "VERIFIED",
  "sourceId": "PSI-25:summary-report:v1"
}
```

`qualifier`: EXACT, APPROXIMATE, GREATER_THAN, LESS_THAN, RANGE, CHANGING, UNKNOWN. RANGE için `minValue`/`maxValue`; CHANGING için `startValue`/`endValue` kullanılır. Kullanılmayan alanlar null olabilir veya çıkarılabilir. Dizi biçimindeki akış değişimleri `rawValue` içinde korunur; zaman bilgisi yoksa zaman serisi oluşturulmaz.

`qualityStatus`: VERIFIED, REQUIRES_REVIEW, MISSING. VERIFIED, dosya/birim eşleştirmesinin doğrulandığını belirtir; deneyin güvenlik sertifikası veya bilimsel kesinlik puanı değildir.

## 5. React - Spring Boot endpointleri

| Metot | Endpoint | Görev |
|---|---|---|
| GET | `/api/v1/health` | Backend erişilebilirliği |
| GET | `/api/v1/investigations` | Araştırma kataloğu |
| GET | `/api/v1/experiments` | Filtrelenmiş test listesi |
| GET | `/api/v1/experiments/{experimentId}` | Koşullar, sonuçlar ve kaynaklarla test detayı |
| POST | `/api/v1/comparisons` | 2-3 testi yan yana karşılaştırma |
| POST | `/api/v1/chat` | Kaynaklı asistan cevabı |
| GET | `/api/v1/sources/{sourceId}` | Kaynak metaverisi ve erişim bağlantısı |

Path kimlikleri istemci tarafından URL-encode edilir. Sağlık yanıtı: `{"status":"UP"}`. Health yanıtı bütün bağımlılıkların hazır olduğunu tek başına garanti etmez.

### Listeleme

`GET /api/v1/experiments?investigationId=PSI-69&page=0&size=20`

İlk sürüm filtreleri: `investigationId`, `fuel`, `page`, `size`. Sayfa 0'dan başlar; varsayılan size 20, üst sınır 100. Fuel, veri sözlüğündeki kanonik adla tam eşleşir. Desteklenmeyen filtreler sessizce yok sayılmayıp 400 döndürür. Varsayılan sıralama `experimentId ASC`.

```json
{
  "items": [
    {
      "experimentId": "PSI-69:run-0001",
      "investigationId": "PSI-69",
      "sourceTestId": "1",
      "fuel": "Methanol",
      "date": "2009-03-05",
      "reportedOutcome": "DISRUPTION",
      "dateRaw": "3/5/2009"
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 274,
  "totalPages": 14
}
```

Yukarıdaki response biçim örneğidir. Listeye geriye uyumlu `dateRaw` alanı eklenmiştir; detayda da bulunur. SAME-R test 51a için `date: null, dateRaw: "22-Jul"` döner; yıl tahmin edilmez. Tam tarih yoksa arayüz ham tarihi ve yılın kaynakta olmadığını, iki alan da boşsa “Kaynakta belirtilmemiş” gösterir. Yakıt filtresi için örneğin `&fuel=Heptane` eklenir; filtre sonrası toplamlar yeniden hesaplanır. Test detayı aynı kimlik alanlarına ek olarak `conditions`, `measurements`, `reportedFindings`, `sources`, `warnings` dizilerini içerir. Koşullar ve ölçümler Bölüm 4 nesnesini kullanır; bulgular kaynaklı nitel açıklamalardır.

`GET /investigations`: `{"items":[{"investigationId":"PSI-25","name":"BASS-II","description":"...","availableDataTypes":["CONDITIONS","REPORTED_FINDINGS"]}]}`. Sayısal kapsam mevcut dosyalara göre belirtilir.

### Karşılaştırma

```json
{
  "experimentIds": ["PSI-25:run-0001", "PSI-25:run-0002"]
}
```

Yanıt alanları: `experimentIds`, `status`, `differences`, `series`, `warnings`, `sources`.

- `status`: COMPARABLE, LIMITED, INSUFFICIENT_DATA.
- `differences`: `field`, `values` (experimentId ve value çiftleri), `note` içeren dizi.
- `series`: `metric`, `unit`, `points` (experimentId, value ve sourceId) içeren dizi. Doğrulanmamış ya da eksik noktalar hesaplamaya girmez; ilgili uyarı döner.
- `warnings`: `code` ve `message` nesneleri.
- Farklı yakıt türü/geometri/basınç/oksijen gibi etkenler gösterilir. Yetersiz bilgi varsa güvenli veya güvensiz sonucu üretilmez. LIMITED sonucu yine de tablo karşılaştırmasına izin verir.

### Sohbet isteği

```json
{
  "question": "Seçtiğim araştırmada hava akımı değişiminin etkisi nasıl açıklanıyor?",
  "investigationIds": ["PSI-25"],
  "experimentIds": [],
  "language": "tr"
}
```

Question zorunlu; 1-4000 karakter. Kimlik dizileri isteğe bağlı, boş dizi kısıt yok demektir. İkisi de doluysa deneyler belirtilen araştırmalara ait olmalıdır; aksi hâlde 400. Varsayılan dil en. İlk sürüm tek soruluk; sohbet geçmişi gönderilmez. Kullanıcı model seçmez.

## 6. Spring Boot - RAG sözleşmesi

`GET /rag/v1/health`: `{"status":"UP"}`.

`POST /rag/v1/answer`: Bölüm 5'teki chat isteğine backend aşağıdaki alanları ekler:

```json
{
  "requestId": "00000000-0000-4000-8000-000000000001",
  "question": "Seçilen testlerin sonuçlarını açıkla.",
  "investigationIds": ["PSI-25"],
  "experimentIds": [],
  "language": "tr",
  "analysisContext": null
}
```

`analysisContext`, hesaplama gerekmiyorsa null olur. Varsa `task`, `experimentIds`, `facts`, `warnings`, `sources` alanlarını içerir. `facts`: `name`, `value`, `unit`, `experimentId`, `sourceId` nesneleridir. Backend bu bağlamı kendi verilerinden oluşturur; tarayıcıdan gelen serbest hesaplama metnini aynen iletmez. RAG, null context ile bağımsız belge soru-cevabını çalıştırabilir. Sayısal soru backend hesaplaması gerektiriyorsa ancak context yoksa tahminle sonuç üretmez.

İlk sürüm görev yolları:

| Görev | Yol |
|---|---|
| Listeleme, filtreleme, sayısal hesaplama | Java/SQL; model çağrılmaz |
| Tek kaynağı/deneyi özetleme | SLM + kaynak arama |
| Birden çok kaynağı sentezleme | Daha büyük yerel model + kaynak arama |

Yönlendirme soru uzunluğuna göre yapılmaz. İlk çalışan sürüm tek modelle kurulabilir; model yönlendirmesi 2.5 iş paketinde eklenir. Model adları yapılandırmadan gelir. Her soruda iki modelin de çağrılması zorunlu değildir. Model yükleme gecikmesi gerçek donanımda ölçülür.

## 7. Ortak asistan yanıtı

RAG bu nesneyi döndürür; Spring Boot aynı alanlarla frontend'e iletir:

```json
{
  "requestId": "00000000-0000-4000-8000-000000000001",
  "answer": "Kanıtlarla desteklenen kısa açıklama... [S1]",
  "status": "ANSWERED",
  "modelTier": "SLM",
  "modelUsed": "yapilandirmadaki-model-adi",
  "sources": [
    {
      "citationId": "S1",
      "sourceId": "PSI-25:summary-report:v1",
      "investigationId": "PSI-25",
      "experimentId": null,
      "sourceType": "DOCUMENT",
      "title": "BASS-II Summary Report",
      "pdfPage": 104,
      "printedPage": "96",
      "table": "7.1",
      "chunkId": "PSI-25:summary-report:v1:p104:c01",
      "sheetName": null,
      "rowNumber": null
    }
  ],
  "warnings": [],
  "timings": {
    "retrievalMs": 0,
    "generationMs": 0,
    "ragTotalMs": 0
  }
}
```

Örnekteki süreler yer tutucudur; gerçek servis ölçülen süreleri yazar. `ragTotalMs`, backend ve frontend ağ süresini kapsamaz.

`status`: ANSWERED, PARTIAL, INSUFFICIENT_EVIDENCE. Bunlar HTTP 200 ile döner; teknik hata değildir. `modelTier`: SLM, LLM veya kullanılabilir model çıktısı yoksa NONE. `modelUsed` çağrı yapılmadığında veya çıktısı reddedildiğinde null olur. Doğrulanamayan model çıktısında özgün kaynak hücreleri kısa, atıflı İngilizce cümlelerle aktarılır: `status: PARTIAL`, `modelTier: NONE`, `modelUsed: null` ve `MODEL_OUTPUT_REJECTED` uyarısı döner. Yanıt bu geri dönüşü açıkça belirtir; `generationMs` yapılan denemenin süresini korur. Başarılı çıktıda da modelin serbest metni gösterilmez: tüm alanlar özgün hücrelerle birebir doğrulanır, ardından aynı kontrollü cümle üreticisi kullanılır. Bağlantı/model erişimi/zaman aşımı hataları hata zarfında kalır.

Kaynak türleri: DOCUMENT, CSV, XLSX. PDF sayfaları 1'den başlar; `printedPage` rapordaki basılı etiket, `pdfPage` görüntüleyicideki sıra numarasıdır. CSV satır numarası başlığı da sayarak 1'den başlar; XLSX için sayfa adı ve Excel satırı belirtilir. Kullanılmayan alanlar null olur.

CitationId, cevapta kullanılan [S1] gibi işaretle eşleşir. Kaynaklar RAG'in gerçekten getirdiği kayıtlarından oluşturulur; modelin ürettiği hayalî kaynaklar kabul edilmez. Bulgu ve yorum ayrılır; benzerlik puanı bilimsel güven veya yangın riski yüzdesi olarak gösterilmez.

`GET /api/v1/sources/{sourceId}`: `sourceId`, `title`, `sourceType`, `investigationId`, `doi`, `originalUrl`, `documentUrl` alanlarını döndürür. Bilinmeyen alanlar null olur. Frontend dosyayı `documentUrl` ile açar; PDF ise `#page={pdfPage}` ekleyebilir. Bu URL backend tarafından erişilebilir biçimde sağlanır; sunucunun yerel disk yolu gönderilmez.

## 8. Hatalar ve ilk sürüm davranışı

```json
{
  "requestId": "00000000-0000-4000-8000-000000000001",
  "error": {
    "code": "EXPERIMENT_NOT_FOUND",
    "message": "İstenen test bulunamadı.",
    "details": []
  }
}
```

| HTTP | Code | Durum |
|---|---|---|
| 400 | VALIDATION_ERROR | Geçersiz alan, filtre, kimlik kapsamı veya 2-3 dışında karşılaştırma sayısı |
| 404 | EXPERIMENT_NOT_FOUND / SOURCE_NOT_FOUND / INVESTIGATION_NOT_FOUND | İstenen kayıt yok |
| 503 | MODEL_UNAVAILABLE / RAG_UNAVAILABLE | Model veya servis hazır değil |
| 504 | RAG_TIMEOUT | RAG yanıt süresi sınırını aştı |
| 500 | INTERNAL_ERROR | Beklenmeyen hata; ayrıntılı trace yalnızca logda |

FastAPI'nin varsayılan doğrulama yanıtı bu hata biçimine uyarlanır. Geçerli filtreyle boş liste normal HTTP 200'dür. Teknik arızada eski cevap yeni cevap gibi gösterilmez. RAG kullanılamasa bile deney listesi ve grafikler çalışabilir.

İlk sürüm normal JSON yanıtıyla çalışır. Başlangıç zaman aşımı: RAG isteği için backend 120 saniye; frontend 130 saniye. Bunlar UX hedefi değildir, geliştirme sınırlarıdır. Backend süresi dolunca mümkünse RAG çağrısı iptal edilir. Otomatik tekrar deneme yoktur; UI yeniden deneme sunar. Streaming/SSE ayrıca tanımlanacak v1.1 geliştirmesidir; v1.0'da event sözleşmesi yoktur.

## 9. GitHub ve ilk entegrasyon kontrolü

Önerilen repo yerleşimi: `backend/`, `rag-service/`, `frontend/`, `data/`, `docs/`. Bu sözleşme `docs/api-contract-v1.md` olarak tutulur. Backend sahibi ortak sözleşme değişikliklerini koordine eder; RAG ve frontend sahipleri etkileniyorsa değişiklik birlikte incelenir.

İlk işler:

1. Backend sahibi araştırma/test/kaynak kimlik manifestini paylaşır.
2. Her servis sahibi health endpointini çalıştırır.
3. Frontend, ortak JSON biçimiyle işaretlenmiş örnek veri üzerinden ilerler.
4. RAG sahibi BASS-II raporunu indeksler; normal cevap, yetersiz kanıt ve servis hatası örneklerini hazırlar.
5. Backend gerçek test listesini ve chat proxy'sini bağlar.
6. Üç kişi kimlik eşleşmesini, null/birim gösterimini ve kaynak sayfasını birlikte doğrular.

Kimlik eşleşmeleri, alan adları veya enum'lar tek taraflı değiştirilmez. Yeni isteğe bağlı alanlar eklenebilir; mevcut alanın anlamını değiştiren sürüm ayrıca kararlaştırılır.

## Scenario analysis

The existing scenario capture workflow uses `POST /api/v1/scenario-analyses`.
The PNG remains local in the browser. Submit only the captured timestamp and
parameters; no image is sent to a text or vision model.

```json
{
  "capturedAt": "2026-11-15T12:00:00.000Z",
  "params": {
    "oxygenPercent": 21,
    "pressureKpa": 101.3,
    "airflowCmS": 8.5,
    "gravityG": 0,
    "temperatureC": 23,
    "ignitionPowerW": 10,
    "material": "PMMA Film",
    "flowDirection": "CONCURRENT",
    "coPpm": 5,
    "co2Percent": 0.1,
    "coMeasurementPhase": "UNSPECIFIED",
    "co2MeasurementPhase": "FINAL"
  }
}
```

All ten original inputs are retained and validated. Numeric inputs must be
finite; oxygen/CO2 range from 0 to 100, pressure is positive, airflow/gravity/
power/CO are nonnegative, and temperature cannot be below −273.15 °C. Material
is a nonblank name up to 120 characters. Direction remains `CONCURRENT|OPPOSED`.
Unknown parameter keys are rejected instead of silently discarded.

The two gas-phase fields are additive and optional, defaulting to `UNSPECIFIED`.
Each accepts `INITIAL|FINAL|UNSPECIFIED`. CO/CO2 are not compared until their own
phase is selected. BASS-II oxygen comparisons explicitly use calibrated initial
O2 % by volume. Percentage differences are **percentage points**, not relative
percent changes. No mole-fraction/species/basis conversion is inferred for the
FLEX composition columns. Fan display and Air display are never cm/s inputs.

Spring Boot forwards `{material, params}` to the existing
`POST /rag/v1/scenarios/evidence` endpoint. RAG validates the full parameter
object and verifies that its material agrees with the outer material. RAG also
retains the existing material-only request mode when `params` is omitted.

The backend response retains `requestId`, `status: EVIDENCE_RETRIEVED`,
`capturedAt`, `params` and `evidence`. It echoes the saved scenario, including
gas-phase defaults. The frontend verifies that echo before attaching a result
to a capture. A changed current scenario is explicitly marked stale.

Additive `evidence` metadata:

- `parameterCoverage`: an entry for every original parameter, including its
  input value, comparison status, reason and source IDs.
- `selectionDetails`: research-specific source class and ordering fields.
- `matchedExperimentCount` and `returnedSourceVersionCount`: distinct grouped
  experiments and independent returned source versions.
- Each source has its own raw `fields`, `comparisons`, verified catalog links,
  `sourceClass`, `alternateRecords` and `recordDifferences`. Alternate versions
  have distinct citations such as `S1A1`. CSV and workbook cells are not merged.
- Numeric comparisons retain original `sourceValue` and add
  `normalizedSourceValue`. `difference` is always **scenario − source**;
  `unit` denotes the difference unit. Direction uses `MATCH|DIFFERENT`.
  Blank, qualified, invalid or unavailable fields remain `NOT_COMPARABLE`.

Coverage statuses include `COMPARED`, `PARTIAL`, `NOT_COMPARABLE`,
`PHASE_UNSPECIFIED` and `NO_SOURCE`. Ordering is within each investigation, then
balanced across applicable investigations; there is no common similarity,
confidence or fire-probability score. Material/test grouping for BASS-II also
retains the original investigator to avoid combining unrelated test IDs.

`evidence.narrative` retains `observations`, `nextChecks`, `message`, `status`
and `modelUsed`, adding `modelRole` and `fallbackReason`. Observations are
deterministic English comparisons with per-source citations. The model may only
return an ordering of the supplied check IDs. Unknown/duplicate/missing IDs,
new prose, model errors or timeout keep the deterministic results and default
check order: `status: DETERMINISTIC`, `modelUsed: null`, `modelRole: NONE` and
an explicit fallback reason. Successful ordering uses `MODEL_ORDERED_CHECKS`
and `ORDERED_CHECK_IDS_ONLY`; it does not claim model-written science.

Validation errors are HTTP 400. Backend/RAG connection errors, malformed
upstream responses and request timeouts remain explicit 503/504 errors; the
saved local capture is kept for retry. No matching source produces
`INSUFFICIENT_EVIDENCE` with empty sources, not manufactured measurements.
Normalized UI values use `en-US`; original source cells/headers stay verbatim.
