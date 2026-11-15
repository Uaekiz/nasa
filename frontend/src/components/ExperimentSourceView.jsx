import { useCallback, useMemo } from "react";
import { experimentViewModel } from "../services/experimentViewModel";
import { createExperimentScene } from "./scenes/createExperimentScene";
import ThreeViewport from "./ThreeViewport";
import { formatNumber } from "../services/format";

export default function ExperimentSourceView({ experiment }) {
  const model = useMemo(() => experimentViewModel(experiment), [experiment]);
  const createScene = useCallback((scene) => createExperimentScene(scene, model), [model]);
  return <section className="experiment-source-view" aria-label="3D view of experiment source conditions" data-sample-kind={model.kind} data-flow-arrows={!!model.flow}>
    <h4>Specimen and source conditions · 3D</h4>
    <p>{model.geometryNote}</p>
    <ThreeViewport createScene={createScene} label="Source specimen and airflow" />
    <p className="source-view-caption">Illustrative 3D view of source conditions; this is not an experiment video or a validated combustion prediction.</p>
    <p>Drag to rotate. Scroll or pinch to zoom. Colors are for visibility and do not represent measurements.</p>
    {model.flow && <p>Flow: {formatNumber(model.flow.speed)} {model.flow.unit} · {model.flow.direction}. Arrows show the source's relative direction label on a schematic axis, not a camera or flame-spread direction. Arrow length does not encode speed.</p>}
    {model.studyNote && <p>{model.studyNote}</p>}
    <details open><summary>Source parameters used ({model.parameters.length})</summary>
      {model.parameters.length === 0 && <p>No verified parameters are available for this drawing.</p>}
      <dl>{model.parameters.map((param, index) => <div key={index}>
        <dt>{param.label}</dt><dd>{typeof param.value === "number" ? formatNumber(param.value) : param.value} {param.unit}<br /><small>Raw cell: <code>{JSON.stringify(param.rawValue)}</code> · {param.sourceId}</small></dd>
      </div>)}</dl>
    </details>
    <details open><summary>Missing or unsuitable visualization data</summary><ul>{model.missing.map((field) => <li key={field}>{field}</li>)}</ul></details>
  </section>;
}
