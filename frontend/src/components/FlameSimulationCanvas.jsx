import { useCallback, useEffect, useRef, useState } from "react";
import ThreeViewport from "./ThreeViewport";
import { createSimulationScene } from "./scenes/createSimulationScene";
import { formatNumber } from "../services/format";

export default function FlameSimulationCanvas({
  params,
  riskEvaluation,
  captureRef,
}) {
  const [isRunning, setIsRunning] = useState(true);
  const livePropsRef = useRef({ params, riskEvaluation, isRunning });
  useEffect(() => { livePropsRef.current = { params, riskEvaluation, isRunning }; }, [params, riskEvaluation, isRunning]);
  const createScene = useCallback((scene) => createSimulationScene(scene, livePropsRef), []);
  return (
    <div className="panel-card sim-card">
      <div className="panel-card-header">
        <div>
          <span className="section-eyebrow">
            ILLUSTRATIVE 3D SCENE
          </span>
          <h3>
            Illustrative specimen and flame model ({params.material} //{" "}
            {params.flowDirection === "CONCURRENT"
              ? "Concurrent flow"
              : "Opposed flow"}
            )
          </h3>
        </div>

        <div className="sim-controls-row">
          <button
            type="button"
            className="nasa-btn nasa-btn-xs"
            onClick={() => setIsRunning((r) => !r)}
          >
            {isRunning ? "⏸ Pause" : "▶ Play"}
          </button>

        </div>
      </div>

      {/* 3D WebGL Viewport with HUD Overlay */}
      <ThreeViewport
  createScene={createScene}
  animated
  label="Main illustrative 3D scene"
  captureRef={captureRef}
>
        {/* Minimalist HUD Overlay inside 3D Viewport */}
        <div className="sim-hud-top-left">
          <span className="hud-tag">
            MODEL REGIME: <strong>{riskEvaluation.flameRegime}</strong>
          </span>
          <span className="hud-tag">
            MODEL SPREAD: <strong>{formatNumber(riskEvaluation.metrics.predictedSpreadRateMmS)} mm/s</strong>
          </span>
        </div>

        <div className="sim-hud-bottom-right">
          <span>Drag to rotate the 3D scene</span>
        </div>
      </ThreeViewport>

      <div className="sim-regime-summary">
        <span
          className="regime-indicator-bar"
          style={{ background: riskEvaluation.riskColor }}
        />
        <p>
  Illustrative 3D view. Flame shape and motion come from demo formulas; this is not experiment footage or a validated physical prediction.
</p>
      </div>
    </div>
  );
}
