import { useCallback, useEffect, useRef, useState } from "react";
import ThreeViewport from "./ThreeViewport";
import { createSimulationScene } from "./scenes/createSimulationScene";

export default function FlameSimulationCanvas({ params, riskEvaluation, onApplyAllRecommendations, hasRecommendations }) {
  const [isRunning, setIsRunning] = useState(true);
  const livePropsRef = useRef({ params, riskEvaluation, isRunning });
  useEffect(() => { livePropsRef.current = { params, riskEvaluation, isRunning }; }, [params, riskEvaluation, isRunning]);
  const createScene = useCallback((scene) => createSimulationScene(scene, livePropsRef), []);
  return (
    <div className="panel-card sim-card">
      <div className="panel-card-header">
        <div>
          <span className="section-eyebrow">
            THREE.JS 3B YANMA VE HAVA AKIŞI SİMÜLASYONU
          </span>
          <h3>
            Mikroçekim Alev Morfolojisi ({params.material} //{" "}
            {params.flowDirection === "CONCURRENT"
              ? "Aynı Yönlü Akış"
              : "Ters Yönlü Akış"}
            )
          </h3>
        </div>

        <div className="sim-controls-row">
          <button
            type="button"
            className="nasa-btn nasa-btn-xs"
            onClick={() => setIsRunning((r) => !r)}
          >
            {isRunning ? "⏸ Duraklat" : "▶ Oynat"}
          </button>

          {hasRecommendations && (
            <button
              type="button"
              className="nasa-btn nasa-btn-accent nasa-btn-xs"
              onClick={onApplyAllRecommendations}
            >
              ★ AI Önlemlerini Simüle Et
            </button>
          )}
        </div>
      </div>

      {/* 3D WebGL Viewport with HUD Overlay */}
      <ThreeViewport createScene={createScene} animated label="Ana simülasyon 3B sahnesi">
        {/* Minimalist HUD Overlay inside 3D Viewport */}
        <div className="sim-hud-top-left">
          <span className="hud-tag">
            REJİM: <strong>{riskEvaluation.flameRegime}</strong>
          </span>
          <span className="hud-tag">
            YAYILIM: <strong>{riskEvaluation.metrics.predictedSpreadRateMmS} mm/s</strong>
          </span>
        </div>

        <div className="sim-hud-bottom-right">
          <span>3B Sahne: Döndürmek için sürükleyin</span>
        </div>
      </ThreeViewport>

      <div className="sim-regime-summary">
        <span
          className="regime-indicator-bar"
          style={{ background: riskEvaluation.riskColor }}
        />
        <p>{riskEvaluation.regimeDescription}</p>
      </div>
    </div>
  );
}
