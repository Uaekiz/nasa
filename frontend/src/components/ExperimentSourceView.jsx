import { useCallback, useMemo } from "react";
import { experimentViewModel } from "../services/experimentViewModel";
import { createExperimentScene } from "./scenes/createExperimentScene";
import ThreeViewport from "./ThreeViewport";

export default function ExperimentSourceView({ experiment }) {
  const model = useMemo(() => experimentViewModel(experiment), [experiment]);
  const createScene = useCallback((scene) => createExperimentScene(scene, model), [model]);
  return <section className="experiment-source-view" aria-label="Deney kaynak koşulları 3B görünümü" data-sample-kind={model.kind} data-flow-arrows={!!model.flow}>
    <h4>Numune ve kaynak koşulları · 3B</h4>
    <p>{model.geometryNote}</p>
    <ThreeViewport createScene={createScene} label="Deney numunesi ve kaynak akışı" />
    <p className="source-view-caption">Kaynak koşullarını gösteren temsili 3B görünüm; deney videosu veya doğrulanmış yanma tahmini değildir.</p>
    <p>Döndürmek için sürükleyin. Kaydırarak veya iki parmakla yakınlaştırın. Renkler yalnızca görünürlük içindir; ölçüm göstermez.</p>
    {model.flow && <p>Akış: {model.flow.speed} {model.flow.unit} · {model.flow.direction}. Oklar, kaynaktaki göreli yön etiketini şematik bir eksende gösterir; kamera yönü veya alev yayılım yönü değildir. Ok uzunluğu hız ölçeği değildir.</p>}
    {model.studyNote && <p>{model.studyNote}</p>}
    <details open><summary>Kullanılan kaynak parametreleri ({model.parameters.length})</summary>
      {model.parameters.length === 0 && <p>Çizim için kullanılabilecek doğrulanmış parametre yok.</p>}
      <dl>{model.parameters.map((param, index) => <div key={index}>
        <dt>{param.label}</dt><dd>{param.value} {param.unit}<br /><small>Ham hücre: <code>{JSON.stringify(param.rawValue)}</code> · {param.sourceId}</small></dd>
      </div>)}</dl>
    </details>
    <details open><summary>Eksik veya görselleştirmeye uygun olmayan bilgiler</summary><ul>{model.missing.map((field) => <li key={field}>{field}</li>)}</ul></details>
  </section>;
}
