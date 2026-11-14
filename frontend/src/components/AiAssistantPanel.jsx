import { useState } from "react";
import { askAiAssistant } from "../services/apiClient";
import { SOURCES_BY_ID } from "../data/nasaPsiData";

const SUGGESTED_QUESTIONS = [
  "Seçtiğim araştırmada hava akımı değişiminin yangın ihtimaline etkisi nasıl açıklanıyor?",
  "Ay (Lunar) habitatlarında yüksek oksijen (%34 O₂) riskini düşürmek için hangi NASA PSI önlemleri uygulanmalı?",
  "Mevcut simülasyon telemetri parametrelerime göre yangın çıkma ihtimalini en hızlı nasıl düşürebilirim?",
];

export default function AiAssistantPanel({ params, mitigationPlan }) {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [selectedInvFilter, setSelectedInvFilter] = useState("PSI-25");
  const [inspectedSource, setInspectedSource] = useState(null);
  const [responseHistory, setResponseHistory] = useState([
    {
      question:
        "Sistem Başlangıç Analizi: Mevcut çevre koşullarında mikroçekim yangın davranışı ve risk düşürme stratejisi nedir?",
      response: {
        requestId: "00000000-0000-4000-8000-000000000001",
        answer:
          "NASA Physical Sciences Informatics (PSI) BASS-II [S1] ve SAFFIRE [S2] telemetri kayıtlarına göre, mikroçekimde doğal kaldırma kuvveti (buoyancy) olmadığından sıcak gazlar yükselmez. Ancak kabin havalandırması (3–20 cm/s) aleve sürekli oksijen taşıyarak Dünya'dakinden daha düşük O₂ eşiklerinde bile kararlı yanmaya yol açar [S1]. Yangın çıkma ihtimalini düşürmek için: (1) Havalandırma akışı sönme sınırı olan <1.5 cm/s seviyesine çekilmeli veya ters yönlü (Opposed) akışa alınmalı [S1, S2], (2) Kabin O₂ kısmi basıncı malzemenin LOI sınırına yaklaştırılmalı ve Nomex III bariyer katmanları kullanılmalıdır [S2].",
        status: "ANSWERED",
        modelTier: "SLM",
        modelUsed: "flamescope-psi-rag-v1",
        sources: [
          {
            citationId: "S1",
            sourceId: "PSI-25:csv-table:v1",
            investigationId: "PSI-25",
            experimentId: "PSI-25:run-0014",
            sourceType: "CSV",
            title: "PSI-25 Experimental Table — BASS-II (Tests B8, B13, B14)",
            table: "BASS-II Matrix",
            chunkId: "PSI-25:csv-table:v1:r15",
            sheetName: "PSI-25_Experimental table_BASS-II",
            rowNumber: 15,
          },
          {
            citationId: "S2",
            sourceId: "PSI-98:csv-table:v1",
            investigationId: "PSI-98",
            experimentId: "PSI-98:run-0002",
            sourceType: "CSV",
            title: "PSI-98 Experimental Table — SAFFIRE-I (Concurrent vs Opposed)",
            table: "SAFFIRE-I",
            chunkId: "PSI-98:csv-table:v1:r3",
            sheetName: "PSI-98_Experimental table_SAFFIRE-1",
            rowNumber: 3,
          },
        ],
        timings: {
          retrievalMs: 14,
          generationMs: 38,
          ragTotalMs: 52,
        },
      },
    },
  ]);

  const handleAsk = async (qText) => {
    const query = (qText ?? question).trim();
    if (!query || loading) return;
    setLoading(true);
    try {
      const res = await askAiAssistant({
        question: query,
        investigationIds: selectedInvFilter ? [selectedInvFilter] : [],
        experimentIds: [],
        language: "tr",
        activeTelemetryParams: params,
      });
      setResponseHistory((prev) => [{ question: query, response: res }, ...prev]);
      setQuestion("");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="assistant-layout">
      <div className="panel-card">
        <div className="panel-card-header">
          <div>
            <span className="section-eyebrow">
              KAYNAK DOĞRULAMALI AI BİLİMSEL ASİSTAN (POST /api/v1/chat)
            </span>
            <h3>
              NASA PSI Telemetri & Yangın Önleme Karar Destek Asistanı (RAG v1.0)
            </h3>
          </div>
          <div className="rag-meta-badges">
            <span className="tech-pill">Aktif Risk: %{mitigationPlan.baseline.probability}</span>
            <span className="tech-pill">Hedef Risk: %{mitigationPlan.optimizedProbability}</span>
          </div>
        </div>

        {/* Prompt Input Form */}
        <form
          className="chat-query-form"
          onSubmit={(e) => {
            e.preventDefault();
            handleAsk();
          }}
        >
          <select
            className="nasa-select"
            value={selectedInvFilter}
            onChange={(e) => setSelectedInvFilter(e.target.value)}
            aria-label="Araştırma kapsamı seç"
          >
            <option value="">Tüm PSI Araştırmaları</option>
            <option value="PSI-25">PSI-25 (BASS-II)</option>
            <option value="PSI-98">PSI-98 (SAFFIRE-I)</option>
            <option value="PSI-99">PSI-99 (SAFFIRE-II)</option>
            <option value="PSI-69">PSI-69 (FLEX)</option>
            <option value="PSI-101">PSI-101 (SAME-R)</option>
          </select>

          <input
            type="text"
            className="nasa-input"
            placeholder="NASA PSI telemetrisi, O₂/akış sınırları veya yangın riskini düşürme protokolleri hakkında sorun..."
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            maxLength={4000}
          />

          <button
            type="submit"
            className="nasa-btn nasa-btn-yellow"
            disabled={loading || !question.trim()}
          >
            {loading ? "Analiz Ediliyor..." : "Kanıtlı Yanıt Üret →"}
          </button>
        </form>

        {/* Quick Scientific Prompts */}
        <div className="suggested-prompts-bar">
          <span className="quick-action-label">Örnek Bilimsel Sorular:</span>
          {SUGGESTED_QUESTIONS.map((sq) => (
            <button
              key={sq}
              type="button"
              className="nasa-btn nasa-btn-xs"
              onClick={() => handleAsk(sq)}
            >
              {sq}
            </button>
          ))}
        </div>

        {/* Answers & Citations Feed */}
        <div className="chat-answers-feed">
          {responseHistory.map((item, idx) => {
            const { response } = item;
            return (
              <div key={`${response.requestId}-${idx}`} className="chat-turn-card">
                <div className="chat-question-header">
                  <span className="q-badge">SORU</span>
                  <strong>{item.question}</strong>
                </div>

                <div className="chat-answer-body">
                  <div className="answer-status-strip">
                    <span className="status-pill-up">STATUS: {response.status}</span>
                    <span className="tech-pill">
                      MODEL TIER: {response.modelTier} ({response.modelUsed})
                    </span>
                    <span className="tech-pill">
                      RAG SÜRESİ: {response.timings?.ragTotalMs} ms (Arama:{" "}
                      {response.timings?.retrievalMs} ms)
                    </span>
                  </div>

                  <p className="answer-text">{response.answer}</p>

                  {/* Verified Citations Array */}
                  {response.sources?.length > 0 && (
                    <div className="citations-block">
                      <div className="subpanel-title">
                        Doğrulanmış NASA PSI Kaynak Atıfları (Bölüm 7 Sözleşmesi)
                      </div>
                      <div className="citations-grid">
                        {response.sources.map((src) => (
                          <div
                            key={src.citationId}
                            className="citation-card"
                            onClick={() =>
                              setInspectedSource({
                                ...src,
                                ...(SOURCES_BY_ID[src.sourceId] || {}),
                              })
                            }
                          >
                            <div className="citation-top">
                              <span className="citation-id-badge">
                                [{src.citationId}]
                              </span>
                              <span className="citation-type-tag">
                                {src.sourceType}
                              </span>
                              <span className="mono-cell">{src.investigationId}</span>
                            </div>
                            <div className="citation-title">{src.title}</div>
                            <div className="citation-meta">
                              <span>Chunk: {src.chunkId}</span>
                              {src.rowNumber && <span>Satır: #{src.rowNumber}</span>}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Source Metadata Inspector Drawer / Card */}
      {inspectedSource && (
        <div className="panel-card source-inspector-card">
          <div className="panel-card-header">
            <div>
              <span className="section-eyebrow">
                KAYNAK METAVERİSİ (GET /api/v1/sources/{inspectedSource.sourceId})
              </span>
              <h4>
                [{inspectedSource.citationId}] {inspectedSource.title}
              </h4>
            </div>
            <button
              type="button"
              className="nasa-btn nasa-btn-xs"
              onClick={() => setInspectedSource(null)}
            >
              ✕ Kapat
            </button>
          </div>
          <div className="detail-meta-grid">
            <div>
              <span className="meta-label">sourceId:</span>
              <strong className="mono-cell">{inspectedSource.sourceId}</strong>
            </div>
            <div>
              <span className="meta-label">investigationId:</span>
              <strong className="mono-cell">
                {inspectedSource.investigationId}
              </strong>
            </div>
            <div>
              <span className="meta-label">sourceType:</span>
              <strong>{inspectedSource.sourceType}</strong>
            </div>
            <div>
              <span className="meta-label">DOI:</span>
              <strong>{inspectedSource.doi || "10.26030/nasa-psi"}</strong>
            </div>
            <div>
              <span className="meta-label">Tablo / Sayfa:</span>
              <strong>
                {inspectedSource.sheetName || inspectedSource.table} (Satır #
                {inspectedSource.rowNumber || 1})
              </strong>
            </div>
            <div>
              <span className="meta-label">NASA PSI Bağlantısı:</span>
              <a
                href={inspectedSource.originalUrl || "https://psi.nasa.gov"}
                target="_blank"
                rel="noreferrer"
                className="nasa-link"
              >
                {inspectedSource.originalUrl || "https://psi.nasa.gov"} ↗
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
