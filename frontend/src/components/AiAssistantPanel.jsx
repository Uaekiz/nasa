import { useCallback, useState } from "react";
import { askAiAssistant, fetchInvestigations, fetchChatCapabilities } from "../services/apiClient";
import useApiResource from "../hooks/useApiResource";
import { loadedChatScopes } from "../services/experimentData";
import SourceCard from "./SourceCard";
import { formatNumber, warningText } from "../services/format";

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
    <div className="panel-card-header"><div><span className="section-eyebrow">SOURCE ASSISTANT</span><h3>Ask about NASA PSI sources</h3></div></div>
    <p>Answers come from the RAG service through the backend. Simulation values are not submitted to this chat as source measurements.</p>
    <p>Ask source questions in English. The options reflect the ready RAG index and investigations loaded in the backend.</p>
    {scope.loading && <p role="status">Checking RAG source coverage…</p>}
    {scope.error && <div role="alert">RAG coverage could not be verified: {scope.error.message} A service restart may be pending. <button onClick={() => setRetry(retry + 1)}>Retry</button></div>}
    {catalog.error && <div role="alert">Investigations could not be loaded: {catalog.error.message} <button onClick={() => setRetry(retry + 1)}>Retry</button></div>}
    <form className="chat-query-form" onSubmit={(event) => { event.preventDefault(); handleAsk(); }}>
      <select className="nasa-select" aria-label="Investigation scope" value={selectedInvFilter} onChange={(event) => setSelectedInvFilter(event.target.value)}>
        <option value="">All available sources</option>
        {supported.map((inv) => <option key={inv.investigationId} value={inv.investigationId}>{inv.investigationId} ({inv.name}) · {formatNumber(inv.sourceIds.length)} sources</option>)}
      </select>
      <input className="nasa-input" aria-label="Assistant question" value={question} onChange={(event) => setQuestion(event.target.value)} maxLength={4000} placeholder="Ask about original source fields in English…" />
      <button type="submit" className="nasa-btn nasa-btn-yellow" disabled={loading || !question.trim()}>{loading ? "Waiting for an answer…" : "Ask / Retry"}</button>
    </form>
    <div className="suggested-prompts-bar">{suggestions.map((suggestion) => <button key={suggestion} className="nasa-btn nasa-btn-xs" disabled={loading} onClick={() => handleAsk(suggestion)}>{suggestion}</button>)}</div>
    {error && <div role="alert" className="warnings-box"><strong>No answer was received.</strong> {error.code && `${error.code}: `}{error.message}{error.requestId && <p>Request: {error.requestId}</p>}<p>Retry using the question field. Earlier answers remain attached to their original questions below.</p></div>}
    {loading && <p role="status">Waiting for the RAG response…</p>}
    {responseHistory.length === 0 && !loading && <p>No answers yet.</p>}
    <div className="chat-answers-feed">{responseHistory.map(({ question: query, response }, index) => <div key={`${response.requestId}:${index}`} className="chat-turn-card">
      <div className="chat-question-header"><strong>{query}</strong></div>
      <div className="chat-answer-body">
        <div className="answer-status-strip"><span>{response.status}</span><span>{response.warnings?.some((warning) => warning.code === "MODEL_OUTPUT_REJECTED")
          ? "Model output rejected · Direct source rendering"
          : `Model: ${response.modelUsed || "Not called"} (${response.modelTier})`}</span>{response.timings?.ragTotalMs != null && <span>RAG: {formatNumber(response.timings.ragTotalMs)} ms</span>}</div>
        <p className="answer-text">{response.answer}</p>
        {(response.warnings || []).map((warning, i) => <p className="warning-line" key={i}>{warning.code}: {warningText(warning)}</p>)}
        <div className="citations-grid">{(response.sources || []).map((source) => <SourceCard key={`${source.citationId}:${source.sourceId}`} source={source} />)}</div>
      </div>
    </div>)}</div>
  </div></div>;
}
