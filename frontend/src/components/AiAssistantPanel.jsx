import { useCallback, useState } from "react";
import { askAiAssistant, fetchInvestigations, fetchChatCapabilities } from "../services/apiClient";
import useApiResource from "../hooks/useApiResource";
import { loadedChatScopes } from "../services/experimentData";
import SourceCard from "./SourceCard";

export default function AiAssistantPanel() {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedInvFilter, setSelectedInvFilter] = useState("");
  const [responseHistory, setResponseHistory] = useState([]);
  const [retry, setRetry] = useState(0);
  const loadCatalog = useCallback(() => fetchInvestigations(), []);
  const catalog = useApiResource(loadCatalog, `catalog:${retry}`);
  const loadScope = useCallback(() => fetchChatCapabilities(), []);
  const scope = useApiResource(loadScope, `scope:${retry}`);
  const supported = loadedChatScopes(catalog.data, scope.data);
  const suggestions = supported.filter((inv) => !selectedInvFilter || selectedInvFilter === inv.investigationId).flatMap((inv) => inv.examples || []);

  async function handleAsk(text) {
    const query = (text ?? question).trim();
    if (!query || loading) return;
    setQuestion(query);
    setLoading(true);
    setError(null);
    try {
      const response = await askAiAssistant({
        question: query, investigationIds: selectedInvFilter ? [selectedInvFilter] : [],
        experimentIds: [], language: "en",
      });
      setResponseHistory((previous) => [{ question: query, response }, ...previous]);
      setQuestion("");
    } catch (failure) {
      setError(failure);
    } finally {
      setLoading(false);
    }
  }

  return <div className="assistant-layout"><div className="panel-card">
    <div className="panel-card-header"><div><span className="section-eyebrow">KAYNAKLI ASİSTAN</span><h3>NASA PSI kaynakları hakkında soru sorun</h3></div></div>
    <p>Yanıtlar backend üzerinden RAG servisinden alınır. Simülasyon değerleri bu sohbete kaynak ölçümü olarak gönderilmez.</p>
    <p>Kaynak sorularını İngilizce sorun. Seçenekler hazır RAG indeksindeki ve backend'de yüklenmiş araştırmaları gösterir.</p>
    {scope.loading && <p role="status">RAG kaynak kapsamı kontrol ediliyor…</p>}
    {scope.error && <div role="alert">RAG kapsamı doğrulanamadı: {scope.error.message} Servis yeniden başlatmaları bekliyor olabilir. <button onClick={() => setRetry(retry + 1)}>Yeniden dene</button></div>}
    {catalog.error && <div role="alert">Araştırmalar yüklenemedi: {catalog.error.message} <button onClick={() => setRetry(retry + 1)}>Yeniden dene</button></div>}
    <form className="chat-query-form" onSubmit={(event) => { event.preventDefault(); handleAsk(); }}>
      <select className="nasa-select" aria-label="Araştırma kapsamı" value={selectedInvFilter} onChange={(event) => setSelectedInvFilter(event.target.value)}>
        <option value="">Tüm mevcut kaynaklar</option>
        {supported.map((inv) => <option key={inv.investigationId} value={inv.investigationId}>{inv.investigationId} ({inv.name}) · {inv.sourceIds.length} kaynak</option>)}
      </select>
      <input className="nasa-input" aria-label="Asistan sorusu" value={question} onChange={(event) => setQuestion(event.target.value)} maxLength={4000} placeholder="Ask about original source fields in English…" />
      <button type="submit" className="nasa-btn nasa-btn-yellow" disabled={loading || !question.trim()}>{loading ? "Yanıt bekleniyor…" : "Sor / Yeniden dene"}</button>
    </form>
    <div className="suggested-prompts-bar">{suggestions.map((suggestion) => <button key={suggestion} className="nasa-btn nasa-btn-xs" disabled={loading} onClick={() => handleAsk(suggestion)}>{suggestion}</button>)}</div>
    {error && <div role="alert" className="warnings-box"><strong>Yanıt alınamadı.</strong> {error.code && `${error.code}: `}{error.message}{error.requestId && <p>İstek: {error.requestId}</p>}<p>Soru alanından yeniden deneyebilirsiniz. Önceki yanıtlar aşağıda kendi sorularıyla gösterilir.</p></div>}
    {loading && <p role="status">RAG yanıtı bekleniyor…</p>}
    {responseHistory.length === 0 && !loading && <p>Henüz alınmış bir yanıt yok.</p>}
    <div className="chat-answers-feed">{responseHistory.map(({ question: query, response }, index) => <div key={`${response.requestId}:${index}`} className="chat-turn-card">
      <div className="chat-question-header"><strong>{query}</strong></div>
      <div className="chat-answer-body">
        <div className="answer-status-strip"><span>{response.status}</span><span>{response.warnings?.some((warning) => warning.code === "MODEL_OUTPUT_REJECTED")
          ? "Model çıktısı reddedildi · Doğrudan kaynak aktarımı"
          : `Model: ${response.modelUsed || "Çağrılmadı"} (${response.modelTier})`}</span>{response.timings?.ragTotalMs != null && <span>RAG: {response.timings.ragTotalMs} ms</span>}</div>
        <p className="answer-text">{response.answer}</p>
        {(response.warnings || []).map((warning, i) => <p className="warning-line" key={i}>{warning.code}: {warning.message}</p>)}
        <div className="citations-grid">{(response.sources || []).map((source) => <SourceCard key={`${source.citationId}:${source.sourceId}`} source={source} />)}</div>
      </div>
    </div>)}</div>
  </div></div>;
}
