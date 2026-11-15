**Kayıt özeti ve eksik alan soruları — 15 Kasım 2026**

Sorun kaynak veya indeks eksikliği değildi. Verilen soru için `plan_query` doğru biçimde `EXACT_ID`, araştırma `PSI-101`, test `51a` ve kaynak `PSI-101:experimental-table:v1` seçiyordu. `assess_coverage`, kaynak başlıkları ve kayıt seçicilerini çıkardıktan sonra kalan sözcükleri dar `GRAMMAR` kümesinde arıyordu. Sorudaki tek tanınmayan sözcük `missing` idi. Bu nedenle `INSUFFICIENT_EVIDENCE` oluşuyor; `answer_service` model çağrısı yapmadan `QUESTION_NOT_COVERED` dönüyordu.

Yalnızca `missing` sözcüğünü eklemek sorunu tamamıyla çözmezdi: varsayılan SAME-R kısa özeti yalnızca Sample Type, Description, Inlet velocity ve Net aging time alanlarını seçiyordu. Date, Rt/R0, Duration, iki boş primary-time hücresi ve kaynak test alanı bu seçimde yoktu. Ayrıca planlayıcıdaki genel `list all` analitik sorgu kuralı, “List all fields for SAME-R test 51a” ifadesini de sayısal analiz gibi engelliyordu.

Yeni `app/record_question.py`, tam kayıt/alan envanteri, mevcut değerler ve eksik hücre incelemesi niyetlerini birleşebilir dil kalıplarıyla tanır. Tam cümle beyaz listesi kullanılmaz. Overview, complete record, all fields, conditions and measurements, present/absent values, blank/unreported fields ve not recorded gibi ifadeler desteklenir. Dil katmanı yalnızca kaynak meta verisini anlatan bölümleri tüketir; bilinmeyen bilimsel alanlar, sayılar ve talimatlar coverage kontrolünde kalır.

Envanter soruları yalnızca ilgili kaynak satırının özgün başlıklarını seçer. CSV ve workbook alanları birleştirilmez; kaynakta bulunmayan sütun üretilmez. Tek alan soruları dar kalır. Yakıt/malzeme filtresi, açık alan isteği sanılıp tüm alanların seçilmesini engellemez. Açık “all fields” veya “overview” isteği, yanında örnek bir alan adı verilse de tam kaydı seçer. Eksik alanların araştırma genelinde aranması/sayılması için nearest-neighbor sonuçlarından çıkarım yapılmaz; eksiklik envanteri belirli test/kaynak kayıt seçimi gerektirir.

`List all` istisnası yalnızca açık kayıt seçicisine bağlı alan/ölçüm envanterine uygulanır. List all tests, count/how many, average, compare, difference ve sayısal eşik sorguları backend analizi sınırında kalır. Sebep, risk, öneri, tanım, değer tahmini veya boşluğu sıfırla doldurma istekleri reddedilmeye devam eder. İngilizce kapsamı korunur.

Model şeması hâlâ her özgün hücreyi tek izin verilen değer olarak taşır. İki primary-time alanının izin verilen tek değeri `""`, Date alanınınki `"22-Jul"` olur. Eksik/ek alan, tekrarlanan JSON anahtarı, değiştirilmiş değer ve sahte atıf kontrolleri korunur. Boş hücre anlatımı artık açıkça “the cell is blank” der. Geçersiz model çıktısının güvenli kaynak aktarımı ve dürüst model bilgisi davranışı değişmez.

SAME-R test 51a için seçilen tüm alanlar aşağıdadır. Kaynak: [SAME-R CSV](<../data/public-docs/PSI-101_Experimental table_SAME-R.csv>), mantıksal CSV satırı **3**, kaynak kimliği `PSI-101:experimental-table:v1`. API cevabında bu kaynak `[S1]` olarak yer alır.

| Özgün alan | Özgün hücre |
|---|---|
| Sample Type | Kapton |
| SAME Test # | 51a |
| Description | B.L. new formula |
| Date | 22-Jul — yıl yok |
| Inlet velocity (cm/s) | 8.1 |
| Rt/R0 | 1.38 |
| Duration (sec) | 60 |
| Primary aging time (sec) | boş dize; sıfır değildir |
| Primary mixing time (sec) | boş dize; sıfır değildir |
| Net aging time (sec) | 261 |

Örnek doğrulanmış kaynak anlatımı:

> SAME-R test 51a lists the sample type as “Kapton”. [S1] The recorded inlet velocity was 8.1 cm/s, with a net aging time of 261 sec. [S1] The source records “SAME Test #” as “51a”. [S1] The source description reads “B.L. new formula”. [S1] The date is recorded as 22-Jul; no year is given in the source. [S1] The Rt/R0 value was recorded as 1.38. [S1] The duration was recorded as 60 sec. [S1] The source does not give a primary aging time value for this entry; the cell is blank. [S1] The source does not give a primary mixing time value for this entry; the cell is blank. [S1]

Durum `PARTIAL` olur; bu ret değildir. `SOURCE_MISSING_VALUE` boş kaynak hücrelerini açıklar. Başarılı doğrulanmış model çıktısı testinde model çağrısı yapılır; `QUESTION_NOT_COVERED` uyarısı oluşmaz.

Kontrol: 130 RAG testi; 125 geçti, 5 ayrıcalıklı ortam testi atlandı. Yeni `test_record_question_scope.py` içindeki 11 test, farklı doğal soru kalıplarını, kaynak bazında alan seçimini, dar alan sorularını, model çağrısına geçişi, boş/tarih şemasını, sahte değerleri, desteklenmeyen çıkarımları ve araştırma filtresi çelişkisini kapsar. Unit/API model çıktıları açık test düzeneğidir; canlı model başarısı olarak sunulmaz. Gerçek DB ile 17 güvenli geri dönüş senaryosu `app.multi_checks --reject-model-output` üzerinden geçti; burada model çıktısı bilerek reddedilir. Eski 274 kayıtlık FLEX indeksinin hash'leri aynı kaldı.

Aynı kullanıcı sorusu, port açılmadan yeni kodla in-process ASGI üzerinden gerçek PostgreSQL ve yapılandırılmış Ollama'ya da gönderildi. Soru coverage'dan geçip model çağrısına ulaştı; Ollama chat isteği zaman aşımına uğradı: HTTP 504 `RAG_TIMEOUT`, ayrıntı `GENERATION_TIMEOUT`. Bu, `QUESTION_NOT_COVERED` reddi değildir; canlı üretim başarısı iddia edilmez. Zaman aşımını kaynak cevabı gibi göstermeyen mevcut hata davranışı korundu. Çıktılar `rag-service/.local/nasa-provenance/record-question-tests.log`, `record-question-fallback.log`, `record-question-live.json` altındadır.

Yeniden aktarım, şema değişikliği veya indeksleme gerekmez. Çalışan servislere müdahale edilmedi. Yeni kodu yüklemesi için yalnızca RAG sürecini kendi terminalinizden yeniden başlatın; mevcut portta ikinci servis açmayın. Backend/frontend değişmedi. Commit, push veya merge yapılmadı.

`rag-service` klasöründe test ve kontrol komutları:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m app.multi_checks --reject-model-output
# Mevcut RAG yeniden başlatıldıktan ve Ollama erişilebilir olduktan sonra:
.\.venv\Scripts\python.exe -m app.multi_checks --base-url http://127.0.0.1:8000
```

RAG'i mevcut başlatma ayarınızla yeniden başlatabilirsiniz. Yerel çok kaynaklı ayarlarla ayrı terminalde, önce mevcut RAG sürecini kendiniz kapattıktan sonra:

```powershell
$env:RAG_DB_SCHEMA='rag'
$env:RAG_INDEX_NAME='nasa_multi_v1'
$env:RAG_CORPUS_MODE='multi'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
