import { useEffect, useRef, useState } from "react";
import { NASA_PALETTE } from "../theme/nasaPalette";

/**
 * Interactive 2D Physics-Based Microgravity Combustion & Airflow Simulator
 * Visualizes flame morphology (spherical 0g diffusion vs fan-driven elongated plume
 * vs partial-gravity buoyant plume vs hypoxic quenching) using the official NASA palette.
 */
export default function FlameSimulationCanvas({
  params,
  riskEvaluation,
  onUpdateParams,
  onApplyAllRecommendations,
  hasRecommendations,
}) {
  const canvasRef = useRef(null);
  const [isRunning, setIsRunning] = useState(true);
  const [showThermalContours, setShowThermalContours] = useState(true);
  const [elapsedSimSec, setElapsedSimSec] = useState(0);

  // Particle systems stored in ref for smooth 60fps animation without React re-render lag
  const simStateRef = useRef({
    airParticles: [],
    sootParticles: [],
    bubbles: [],
    time: 0,
  });

  useEffect(() => {
    // Initialize streamline particles
    const airParticles = Array.from({ length: 48 }, (_, idx) => ({
      x: (idx * 23) % 760,
      y: 34 + ((idx * 37) % 250),
      length: 12 + (idx % 14),
      speedFactor: 0.75 + (idx % 5) * 0.12,
    }));

    const sootParticles = Array.from({ length: 28 }, (_, idx) => ({
      x: 280 + (idx * 13) % 180,
      y: 165 + ((idx * 19) % 40) - 20,
      vx: 1.2,
      vy: 0,
      radius: 1.5 + (idx % 3),
      alpha: 0.2 + (idx % 7) * 0.1,
      life: (idx * 17) % 100,
    }));

    const bubbles = Array.from({ length: 10 }, (_, idx) => ({
      offsetX: -24 + idx * 6,
      r: 1.5 + (idx % 3),
      phase: idx * 0.7,
    }));

    simStateRef.current.airParticles = airParticles;
    simStateRef.current.sootParticles = sootParticles;
    simStateRef.current.bubbles = bubbles;
  }, []);

  useEffect(() => {
    if (!isRunning) return;
    const timer = setInterval(() => {
      setElapsedSimSec((s) => s + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, [isRunning]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    let animationFrameId;

    const render = () => {
      const dpr = window.devicePixelRatio || 1;
      const width = canvas.clientWidth || 720;
      const height = canvas.clientHeight || 330;

      if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
        canvas.width = width * dpr;
        canvas.height = height * dpr;
      }

      ctx.save();
      ctx.scale(dpr, dpr);

      if (isRunning) {
        simStateRef.current.time += 0.045;
      }
      const t = simStateRef.current.time;

      const {
        oxygenPercent,
        airflowCmS,
        gravityG,
        material,
        flowDirection,
      } = params;
      const { probability, flameRegime, metrics } = riskEvaluation;

      const isDroplet = material === "Methanol" || material === "Heptane";
      const isQuenching =
        flameRegime === "QUENCHING_STARVATION" || probability < 16;
      const isBlowoff = flameRegime === "CONVECTIVE_BLOWOFF";
      const flowSign = flowDirection === "CONCURRENT" ? 1 : -1;

      // 1. Deep Blue Chamber Background (#07173F)
      ctx.fillStyle = NASA_PALETTE.deepBlue.hex;
      ctx.fillRect(0, 0, width, height);

      // 2. Technical Telemetry Grid (#0042A6 with subtle opacity)
      ctx.strokeStyle = "rgba(0, 66, 166, 0.35)";
      ctx.lineWidth = 1;
      const gridStep = 32;
      for (let gx = 0; gx < width; gx += gridStep) {
        ctx.beginPath();
        ctx.moveTo(gx, 0);
        ctx.lineTo(gx, height);
        ctx.stroke();
      }
      for (let gy = 0; gy < height; gy += gridStep) {
        ctx.beginPath();
        ctx.moveTo(0, gy);
        ctx.lineTo(width, gy);
        ctx.stroke();
      }

      // 3. Wind Tunnel / MSG Duct Walls (#0042A6 & #2E96F5)
      ctx.strokeStyle = NASA_PALETTE.electricBlue.hex;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(16, 28);
      ctx.lineTo(width - 16, 28);
      ctx.moveTo(16, height - 28);
      ctx.lineTo(width - 16, height - 28);
      ctx.stroke();

      // Duct Inlet Louvers
      ctx.strokeStyle = NASA_PALETTE.blueYonder.hex;
      ctx.lineWidth = 1.5;
      const inletX = flowSign === 1 ? 22 : width - 22;
      for (let ly = 40; ly < height - 36; ly += 18) {
        ctx.beginPath();
        ctx.moveTo(inletX - 4, ly);
        ctx.lineTo(inletX + 4, ly + 6);
        ctx.stroke();
      }

      // 4. Ventilation Airflow Streamlines (#2E96F5 Blue Yonder)
      const visualFlowSpeed = Math.max(0.15, airflowCmS * 0.22);
      ctx.strokeStyle =
        airflowCmS < 1.8
          ? "rgba(46, 150, 245, 0.28)"
          : "rgba(46, 150, 245, 0.65)";
      ctx.lineWidth = 1.5;

      simStateRef.current.airParticles.forEach((p) => {
        if (isRunning) {
          p.x += flowSign * visualFlowSpeed * p.speedFactor;
          if (flowSign === 1 && p.x > width - 24) p.x = 24;
          if (flowSign === -1 && p.x < 24) p.x = width - 24;
        }
        const streakLen = Math.max(4, Math.min(34, airflowCmS * 1.1 + 4));
        ctx.beginPath();
        ctx.moveTo(p.x, p.y);
        ctx.lineTo(p.x - flowSign * streakLen, p.y);
        ctx.stroke();

        // Arrowhead on streamline
        ctx.fillStyle = NASA_PALETTE.blueYonder.hex;
        ctx.beginPath();
        ctx.arc(p.x, p.y, 1.6, 0, Math.PI * 2);
        ctx.fill();
      });

      // Center coordinates of fuel sample
      const centerX = width * 0.44;
      const centerY = height * 0.56;

      // 5. Thermal Radiation & O2 Depletion Contours (Optional Overlay)
      const intensity = Math.max(0.12, probability / 100);
      const flameStretchX =
        flowSign * Math.min(135, airflowCmS * 4.2) * (isQuenching ? 0.3 : 1);
      const buoyancyLiftY =
        -Math.min(95, gravityG * 130) * (isQuenching ? 0.25 : 1);

      if (showThermalContours) {
        ctx.save();
        // Outer thermal hazard contour (#8E1100 Martian Red dashed ring)
        const contourRx = 48 + Math.abs(flameStretchX) * 0.85 + intensity * 45;
        const contourRy = 38 + Math.abs(buoyancyLiftY) * 0.6 + intensity * 30;
        const contourCenterX = centerX + flameStretchX * 0.42;
        const contourCenterY = centerY + buoyancyLiftY * 0.42;

        const radGrad = ctx.createRadialGradient(
          centerX + flameStretchX * 0.25,
          centerY + buoyancyLiftY * 0.25,
          6,
          contourCenterX,
          contourCenterY,
          Math.max(contourRx, contourRy)
        );

        if (isQuenching) {
          radGrad.addColorStop(0, "rgba(9, 96, 225, 0.32)");
          radGrad.addColorStop(0.6, "rgba(0, 66, 166, 0.14)");
          radGrad.addColorStop(1, "rgba(7, 23, 63, 0)");
        } else if (probability >= 60) {
          radGrad.addColorStop(0, "rgba(228, 55, 0, 0.42)");
          radGrad.addColorStop(0.55, "rgba(142, 17, 0, 0.28)");
          radGrad.addColorStop(1, "rgba(7, 23, 63, 0)");
        } else {
          radGrad.addColorStop(0, "rgba(9, 96, 225, 0.38)");
          radGrad.addColorStop(0.55, "rgba(228, 55, 0, 0.18)");
          radGrad.addColorStop(1, "rgba(7, 23, 63, 0)");
        }

        ctx.fillStyle = radGrad;
        ctx.beginPath();
        ctx.ellipse(
          contourCenterX,
          contourCenterY,
          contourRx,
          contourRy,
          0,
          0,
          Math.PI * 2
        );
        ctx.fill();

        // Dashed thermal boundary line
        ctx.setLineDash([5, 5]);
        ctx.strokeStyle = isQuenching
          ? NASA_PALETTE.blueYonder.hex
          : probability >= 60
          ? NASA_PALETTE.rocketRed.hex
          : NASA_PALETTE.neonYellow.hex;
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.ellipse(
          contourCenterX,
          contourCenterY,
          contourRx,
          contourRy,
          0,
          0,
          Math.PI * 2
        );
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.restore();
      }

      // 6. Fuel Sample / Holder Geometry
      ctx.save();
      if (isDroplet) {
        // Silicon carbide fiber tethers for FLEX droplet experiment
        ctx.strokeStyle = "rgba(255, 255, 255, 0.35)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(centerX - 70, centerY - 50);
        ctx.lineTo(centerX + 70, centerY + 50);
        ctx.moveTo(centerX - 70, centerY + 50);
        ctx.lineTo(centerX + 70, centerY - 50);
        ctx.stroke();

        // Liquid fuel droplet core
        ctx.fillStyle = NASA_PALETTE.white.hex;
        ctx.beginPath();
        ctx.arc(centerX, centerY, 9, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = NASA_PALETTE.blueYonder.hex;
        ctx.lineWidth = 2;
        ctx.stroke();
      } else {
        // Solid fuel sample strip (BASS-II / SAFFIRE)
        const sampleW = 130;
        const sampleH = 12;
        // Metallic holder frame
        ctx.fillStyle = NASA_PALETTE.electricBlue.hex;
        ctx.fillRect(
          centerX - sampleW / 2 - 8,
          centerY + 2,
          sampleW + 16,
          sampleH + 6
        );
        // Active fuel strip
        ctx.fillStyle =
          material === "Nomex III"
            ? NASA_PALETTE.neonBlue.hex
            : NASA_PALETTE.white.hex;
        ctx.fillRect(centerX - sampleW / 2, centerY, sampleW, sampleH);

        // Char / pyrolysis blackened zone near ignition point
        const charWidth = Math.min(
          sampleW * 0.85,
          18 + (probability / 100) * 68
        );
        ctx.fillStyle = NASA_PALETTE.martianRed.hex;
        ctx.fillRect(centerX - 24, centerY, charWidth, sampleH);

        // PMMA melting bubbles (observed in NASA BASS-II video transcript)
        if (material === "PMMA Film" && !isQuenching) {
          ctx.fillStyle = NASA_PALETTE.neonYellow.hex;
          simStateRef.current.bubbles.forEach((b) => {
            const by =
              centerY - 1 - Math.abs(Math.sin(t * 2.2 + b.phase)) * 4.5;
            ctx.beginPath();
            ctx.arc(centerX + b.offsetX, by, b.r, 0, Math.PI * 2);
            ctx.fill();
          });
        }
      }
      ctx.restore();

      // 7. Dynamic Physics Flame Plume Rendering
      ctx.save();
      const flickerX = Math.sin(t * 5.2) * (1.8 + airflowCmS * 0.08);
      const flickerY = Math.cos(t * 6.1) * 1.6;

      if (gravityG < 0.05 && airflowCmS < 2.2) {
        // MICROGRAVITY SPHERICAL BLUE DIFFUSION FLAME (FLEX / Quiescent BASS-II)
        const sphereRadius = isQuenching
          ? 18 + Math.sin(t * 3) * 2
          : 34 + (oxygenPercent - 15) * 1.4;

        // Outer Neon Blue / Blue Yonder chemiluminescent reaction zone
        const sphereGrad = ctx.createRadialGradient(
          centerX,
          centerY - 4,
          4,
          centerX,
          centerY - 4,
          sphereRadius
        );
        sphereGrad.addColorStop(0, NASA_PALETTE.white.hex);
        sphereGrad.addColorStop(0.35, NASA_PALETTE.blueYonder.hex);
        sphereGrad.addColorStop(0.78, NASA_PALETTE.neonBlue.hex);
        sphereGrad.addColorStop(1, "rgba(7, 23, 63, 0)");

        ctx.fillStyle = sphereGrad;
        ctx.beginPath();
        ctx.arc(centerX, centerY - 4, sphereRadius, 0, Math.PI * 2);
        ctx.fill();

        // Crisp spherical flame boundary ring
        ctx.strokeStyle = NASA_PALETTE.blueYonder.hex;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(centerX, centerY - 4, sphereRadius * 0.86, 0, Math.PI * 2);
        ctx.stroke();
      } else {
        // FORCED-FLOW OR PARTIAL-GRAVITY ELONGATED PLUME
        const baseScale = isQuenching
          ? 0.38
          : isBlowoff
          ? 0.55
          : Math.max(0.5, Math.min(1.45, probability / 58));

        const tipX =
          centerX +
          flameStretchX * baseScale +
          flickerX +
          (isBlowoff ? flowSign * 22 : 0);
        const tipY =
          centerY - 22 * baseScale + buoyancyLiftY * baseScale + flickerY;

        // Outer Reaction Envelope (#E43700 Rocket Red + #0960E1 leading anchor)
        ctx.beginPath();
        ctx.moveTo(centerX - flowSign * 22 * baseScale, centerY);
        ctx.quadraticCurveTo(
          centerX + flameStretchX * 0.35,
          centerY - 48 * baseScale + buoyancyLiftY * 0.5,
          tipX,
          tipY
        );
        ctx.quadraticCurveTo(
          centerX + flameStretchX * 0.45,
          centerY + 8,
          centerX - flowSign * 22 * baseScale,
          centerY
        );
        ctx.closePath();

        const plumeGrad = ctx.createLinearGradient(
          centerX - flowSign * 22,
          centerY,
          tipX,
          tipY
        );
        // Leading edge in microgravity is always blue (CH*/OH* chemiluminescence)
        plumeGrad.addColorStop(0, NASA_PALETTE.neonBlue.hex);
        plumeGrad.addColorStop(0.24, NASA_PALETTE.blueYonder.hex);
        plumeGrad.addColorStop(
          0.6,
          isQuenching ? NASA_PALETTE.electricBlue.hex : NASA_PALETTE.rocketRed.hex
        );
        plumeGrad.addColorStop(
          1,
          isQuenching ? "rgba(9, 96, 225, 0.1)" : NASA_PALETTE.neonYellow.hex
        );

        ctx.fillStyle = plumeGrad;
        ctx.fill();

        // Inner Incandescent Core (#EAFE07 Neon Yellow & #FFFFFF White)
        if (!isQuenching) {
          ctx.beginPath();
          ctx.moveTo(centerX - flowSign * 10 * baseScale, centerY - 2);
          ctx.quadraticCurveTo(
            centerX + flameStretchX * 0.25,
            centerY - 26 * baseScale + buoyancyLiftY * 0.35,
            centerX + (tipX - centerX) * 0.68,
            centerY + (tipY - centerY) * 0.68
          );
          ctx.quadraticCurveTo(
            centerX + flameStretchX * 0.25,
            centerY,
            centerX - flowSign * 10 * baseScale,
            centerY - 2
          );
          ctx.closePath();
          ctx.fillStyle =
            probability >= 65
              ? NASA_PALETTE.neonYellow.hex
              : NASA_PALETTE.white.hex;
          ctx.fill();
        }
      }
      ctx.restore();

      // 8. Downstream Smoke / Soot Aerosol Plume (SAME-R PSI-101 telemetry)
      ctx.save();
      simStateRef.current.sootParticles.forEach((sp) => {
        if (isRunning) {
          sp.x += flowSign * (1.1 + airflowCmS * 0.12);
          sp.y += -gravityG * 1.4 + Math.sin(t * 2 + sp.life) * 0.35;
          sp.life += 1;
          const maxDist = Math.abs(sp.x - centerX);
          if (maxDist > 230 || sp.y < 34 || sp.y > height - 34) {
            sp.x = centerX + flowSign * 18;
            sp.y = centerY - 12 + ((sp.life * 7) % 16);
          }
        }
        ctx.fillStyle =
          probability >= 60
            ? "rgba(228, 55, 0, 0.55)"
            : "rgba(46, 150, 245, 0.45)";
        ctx.beginPath();
        ctx.arc(
          sp.x,
          sp.y,
          sp.radius * (isQuenching ? 0.6 : 1.15),
          0,
          Math.PI * 2
        );
        ctx.fill();
      });
      ctx.restore();

      // 9. Technical Mission-Control HUD Overlays on Canvas
      ctx.font = "600 11px 'JetBrains Mono', 'Fira Code', monospace";
      ctx.fillStyle = NASA_PALETTE.white.hex;
      ctx.fillText(
        `CHAMBER TELEMETRY // ${material.toUpperCase()} // ${flowDirection} FLOW`,
        26,
        20
      );

      // Right-aligned regime tag
      const regimeBadgeText = `REJİM: ${flameRegime}`;
      const badgeWidth = ctx.measureText(regimeBadgeText).width + 16;
      ctx.fillStyle =
        probability >= 75
          ? NASA_PALETTE.rocketRed.hex
          : probability >= 50
          ? NASA_PALETTE.electricBlue.hex
          : NASA_PALETTE.deepBlue.hex;
      ctx.fillRect(width - badgeWidth - 20, 6, badgeWidth, 18);
      ctx.strokeStyle =
        probability >= 50
          ? NASA_PALETTE.neonYellow.hex
          : NASA_PALETTE.blueYonder.hex;
      ctx.strokeRect(width - badgeWidth - 20, 6, badgeWidth, 18);
      ctx.fillStyle =
        probability >= 50 && probability < 75
          ? NASA_PALETTE.neonYellow.hex
          : NASA_PALETTE.white.hex;
      ctx.fillText(regimeBadgeText, width - badgeWidth - 12, 19);

      // Bottom telemetry strip inside canvas
      ctx.fillStyle = "rgba(7, 23, 63, 0.88)";
      ctx.fillRect(20, height - 56, width - 40, 24);
      ctx.strokeStyle = NASA_PALETTE.electricBlue.hex;
      ctx.strokeRect(20, height - 56, width - 40, 24);

      ctx.font = "500 11px 'JetBrains Mono', monospace";
      ctx.fillStyle = NASA_PALETTE.blueYonder.hex;
      ctx.fillText(
        `V_fan: ${airflowCmS.toFixed(1)} cm/s`,
        30,
        height - 40
      );
      ctx.fillStyle = NASA_PALETTE.white.hex;
      ctx.fillText(
        `ppO₂: ${metrics.partialPressureO2Kpa} kPa (${oxygenPercent.toFixed(1)}%)`,
        165,
        height - 40
      );
      ctx.fillStyle = NASA_PALETTE.neonYellow.hex;
      ctx.fillText(
        `Yayılım Hızı: ${metrics.predictedSpreadRateMmS} mm/s`,
        345,
        height - 40
      );
      ctx.fillStyle =
        probability >= 60 ? NASA_PALETTE.rocketRed.hex : NASA_PALETTE.blueYonder.hex;
      ctx.fillText(
        `G-Kuvveti: ${gravityG.toFixed(2)}g | t+${elapsedSimSec}s`,
        525,
        height - 40
      );

      ctx.restore();
      animationFrameId = requestAnimationFrame(render);
    };

    animationFrameId = requestAnimationFrame(render);
    return () => cancelAnimationFrame(animationFrameId);
  }, [params, riskEvaluation, isRunning, showThermalContours, elapsedSimSec]);

  return (
    <div className="sim-card">
      <div className="sim-card-header">
        <div>
          <span className="section-eyebrow">
            GERÇEK ZAMANLI MİKROÇEKİM YANMA ODASI SİMÜLATÖRÜ
          </span>
          <h3 className="sim-title">
            2B Fizik Tabanlı Alev Morfolojisi & Hava Akışı Telemetri Simülasyonu
          </h3>
        </div>
        <div className="sim-controls-row">
          <button
            type="button"
            className={`nasa-btn nasa-btn-sm ${isRunning ? "active" : ""}`}
            onClick={() => setIsRunning((r) => !r)}
          >
            {isRunning ? "⏸ Simülasyonu Duraklat" : "▶ Simülasyonu Başlat"}
          </button>
          <button
            type="button"
            className={`nasa-btn nasa-btn-sm ${
              showThermalContours ? "active" : ""
            }`}
            onClick={() => setShowThermalContours((c) => !c)}
          >
            {showThermalContours ? "◉ Termal Kontur: AÇIK" : "○ Termal Kontur: KAPALI"}
          </button>
        </div>
      </div>

      <div className="sim-canvas-wrapper">
        <canvas ref={canvasRef} className="sim-canvas" />
      </div>

      {/* Physical explanation banner + Quick Anomaly / Countermeasure Injection */}
      <div className="sim-footer-bar">
        <div className="sim-regime-note">
          <span className="regime-dot" style={{ background: riskEvaluation.riskColor }} />
          <div>
            <strong>Aktif Fiziksel Rejim ({riskEvaluation.flameRegime}):</strong>{" "}
            <span>{riskEvaluation.regimeDescription}</span>
          </div>
        </div>

        <div className="sim-quick-actions">
          <span className="quick-action-label">Hızlı Senaryo Enjeksiyonu:</span>
          <button
            type="button"
            className="nasa-btn nasa-btn-danger-outline nasa-btn-xs"
            onClick={() =>
              onUpdateParams({
                oxygenPercent: Math.min(38, Number((params.oxygenPercent + 5.0).toFixed(1))),
                airflowCmS: Math.max(params.airflowCmS, 14.0),
                flowDirection: "CONCURRENT",
              })
            }
          >
            ▲ O₂ Sızıntısı (+5% O₂)
          </button>
          <button
            type="button"
            className="nasa-btn nasa-btn-xs"
            onClick={() =>
              onUpdateParams({
                airflowCmS: 1.0,
                flowDirection: "OPPOSED",
              })
            }
          >
            ▼ Fan Kesintisi (Quenching &lt;1.2 cm/s)
          </button>
          <button
            type="button"
            className="nasa-btn nasa-btn-xs"
            onClick={() =>
              onUpdateParams({
                gravityG: params.gravityG === 0 ? 0.16 : params.gravityG === 0.16 ? 1.0 : 0.0,
              })
            }
          >
            ⟳ Çekim Değiştir ({params.gravityG === 0 ? "0g→0.16g Ay" : params.gravityG === 0.16 ? "0.16g→1g Dünya" : "1g→0g ISS"})
          </button>
          {hasRecommendations && (
            <button
              type="button"
              className="nasa-btn nasa-btn-yellow nasa-btn-xs"
              onClick={onApplyAllRecommendations}
            >
              ★ AI Önerilerini Simülasyona Uygula
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
