import { useCallback, useState } from "react";
import { fetchSource, sourceDocumentUrl } from "../services/apiClient";
import useApiResource from "../hooks/useApiResource";

export default function SourceCard({ source }) {
  const [open, setOpen] = useState(false);
  const [retry, setRetry] = useState(0);
  const load = useCallback(() => fetchSource(source.sourceId), [source.sourceId]);
  const { data, error, loading } = useApiResource(load, open ? `${source.sourceId}:${retry}` : null);
  const documentUrl = data && sourceDocumentUrl(data, source.pdfPage);
  return (
    <div className="citation-card">
      <button type="button" className="nasa-btn nasa-btn-xs" onClick={() => setOpen(!open)}>
        {source.citationId && `[${source.citationId}] `}{source.title || source.sourceId}
        {open ? " ▴" : " ▾"}
      </button>
      <div className="citation-meta">
        <span>{source.sourceId}</span>
        {source.rowNumber != null && <span>Kaynak satırı: {source.rowNumber}</span>}
        {source.sheetName && <span>Çalışma sayfası: {source.sheetName}</span>}
        {source.pdfPage != null && <span>PDF sayfası: {source.pdfPage}</span>}
        {source.chunkId && <span>Chunk: {source.chunkId}</span>}
      </div>
      {open && loading && <p role="status">Kaynak yükleniyor…</p>}
      {open && error && <div role="alert">{error.message} <button type="button" onClick={() => setRetry(retry + 1)}>Yeniden dene</button></div>}
      {open && data && <div className="detail-meta-grid">
        <div>{data.sourceType} · {data.investigationId}</div>
        <div>DOI: {data.doi || "Belirtilmemiş"}</div>
        {documentUrl ? <a href={documentUrl} target="_blank" rel="noreferrer">Kaynak dosyasını aç ↗</a> : <span>Kaynak dosya bağlantısı yok.</span>}
        {data.originalUrl && <a href={data.originalUrl} target="_blank" rel="noreferrer">Orijinal kaynak ↗</a>}
      </div>}
    </div>
  );
}
