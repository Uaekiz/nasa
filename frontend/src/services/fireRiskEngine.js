import { MATERIALS_CATALOG } from "../data/nasaPsiData.js";
import { NASA_PALETTE } from "../theme/nasaPalette.js";

const clamp = (val, min, max) => Math.min(max, Math.max(min, val));

/**
 * Heuristic demonstration model for simulation inputs. Its output is not a
 * source measurement or a validated probability derived from imported experiments.
 */
export function evaluateFireRisk(params) {
  const {
    oxygenPercent = 21.0,
    pressureKpa = 101.3,
    airflowCmS = 8.5,
    gravityG = 0.0,
    temperatureC = 23.0,
    ignitionPowerW = 85,
    material = "PMMA Film",
    flowDirection = "CONCURRENT",
    coPpm = 18,
    co2Percent = 0.38,
  } = params;

  const mat = MATERIALS_CATALOG[material] || MATERIALS_CATALOG["PMMA Film"];

  // 1. Oxygen Margin above Material Limiting Oxygen Index (LOI) & Partial Pressure
  const partialPressureO2Kpa = (oxygenPercent / 100) * pressureKpa;
  // In microgravity low-velocity flow, effective LOI drops by ~1.5% compared to 1g
  const microgravityLoiShift = gravityG < 0.05 && airflowCmS >= 2 && airflowCmS <= 22 ? -1.4 : 0;
  const effectiveLoi = mat.loi + microgravityLoiShift;
  const o2Margin = oxygenPercent - effectiveLoi;

  let oxygenScore;
  if (o2Margin <= -2.0) {
    oxygenScore = 4; // Deeply hypoxic quenching region (e.g. BASS-II B14 at 15% O2)
  } else if (o2Margin < 0) {
    oxygenScore = 12 + (o2Margin + 2.0) * 11;
  } else {
    // Non-linear acceleration in hyperoxic exploration atmospheres (23% - 36% O2)
    oxygenScore = 34 + Math.pow(o2Margin, 1.32) * 4.6;
  }
  oxygenScore = clamp(oxygenScore, 2, 98);

  // 2. Convective Flow & Microgravity Oxygen Transport Factor
  // Natural buoyancy equivalent flow velocity: v_b ~ 42 * sqrt(g) cm/s
  const buoyantVelocityCmS = 42.0 * Math.sqrt(Math.max(0, gravityG));
  const effectiveVelocityCmS = Math.sqrt(
    airflowCmS * airflowCmS + buoyantVelocityCmS * buoyantVelocityCmS
  );

  let flowFactor;
  let flameRegime = "FAN_DRIVEN_SUSTAINED";
  let regimeDescription =
      "Illustrative forced-flow display mode. This label is selected by the local model and is not a measured flame regime.";

  if (effectiveVelocityCmS < 1.6) {
    // Quiescent microgravity: combustion products form a stagnant CO2/H2O shell -> self-quenching
    flowFactor = 0.38 + (effectiveVelocityCmS / 1.6) * 0.32;
    flameRegime = "SPHERICAL_DIFFUSION";
    regimeDescription =
      "Illustrative low-flow display mode. The shape and color are model graphics, not measured flame properties.";
  } else if (
    airflowCmS > mat.blowoffFlowCmS &&
    oxygenPercent < effectiveLoi + 3.5
  ) {
    // High airflow at modest O2 causes convective heat loss > chemical generation (Blowoff: BASS-II B18/B19)
    const blowoffExcess = (airflowCmS - mat.blowoffFlowCmS) / 15;
    flowFactor = clamp(0.68 - blowoffExcess * 0.35, 0.25, 0.68);
    flameRegime = "CONVECTIVE_BLOWOFF";
    regimeDescription =
      "Illustrative high-flow display mode. The model does not establish extinction or a safe operating region.";
  } else {
    // Peak microgravity danger zone: 4 - 24 cm/s feeds oxygen steadily without blowing out the flame
    const distFromOptimal = Math.abs(effectiveVelocityCmS - mat.optimalFlowCmS);
    flowFactor = clamp(1.26 - distFromOptimal * 0.014, 0.78, 1.28);
    if (oxygenPercent >= 26.0) {
      flameRegime = "HYPEROXIC_ACCELERATORY";
      regimeDescription =
      "Illustrative higher-oxygen display mode. The source evidence does not validate its predicted flame behavior.";
    } else if (gravityG >= 0.12) {
      flameRegime = "BUOYANT_PLUME";
      regimeDescription =
      "Illustrative partial-gravity display mode. Model-derived motion is not an experiment observation.";
    }
  }

  if (o2Margin < -0.5) {
    flameRegime = "QUENCHING_STARVATION";
    regimeDescription =
      "Illustrative lower-oxygen display mode. This does not establish that ignition or propagation is prevented.";
  }

  // 3. Flow Direction Multiplier (SAFFIRE-I S1 Concurrent vs S2 Opposed)
  const directionMultiplier =
    flowDirection === "CONCURRENT" && effectiveVelocityCmS >= 2.0 ? 1.18 : 0.88;

  // 4. Pressure & Normoxic Exploration Correction
  const pressureFactor = clamp(0.76 + (pressureKpa / 101.3) * 0.24, 0.65, 1.25);

  // 5. Thermal & Ignition Power Factor
  const ignitionRatio = ignitionPowerW / mat.ignitionPowerThresholdW;
  const thermalFactor = clamp(
    0.72 + Math.min(ignitionRatio, 2.2) * 0.18 + Math.max(0, temperatureC - 22) * 0.008,
    0.65,
    1.35
  );

  // 6. Gas Telemetry / Pyrolysis Anomaly Bonus (CO ppm & CO2 % from BASS-II & SAME-R)
  const coAnomalyBoost = clamp((coPpm - 10) * 0.11, 0, 14);
  const co2AnomalyBoost = clamp((co2Percent - 0.35) * 12, 0, 6);

  // Existing unitless demonstration score; the property name is retained for compatibility.
  let rawProbability =
    oxygenScore *
      mat.baseFlammability *
      flowFactor *
      directionMultiplier *
      pressureFactor *
      thermalFactor +
    coAnomalyBoost +
    co2AnomalyBoost;

  const probability = Number(clamp(rawProbability, 1.2, 99.2).toFixed(1));

  // Determine Risk Level & Official NASA Palette Color
  let riskLevel = "LOW";
  let riskLabelTr = "LOWER MODEL SCORE";
  let riskColor = NASA_PALETTE.blueYonder.hex; // #2E96F5

  if (probability >= 75) {
    riskLevel = "CRITICAL";
    riskLabelTr = "UPPER MODEL SCORE";
    riskColor = NASA_PALETTE.rocketRed.hex; // #E43700
  } else if (probability >= 50) {
    riskLevel = "HIGH";
    riskLabelTr = "HIGHER MODEL SCORE";
    riskColor = NASA_PALETTE.neonYellow.hex; // #EAFE07
  } else if (probability >= 26) {
    riskLevel = "MODERATE";
    riskLabelTr = "MID-RANGE MODEL SCORE";
    riskColor = NASA_PALETTE.neonBlue.hex; // #0960E1
  }

  // Predicted physical metrics
  const baseSpreadRate =
    o2Margin <= -0.5
      ? 0
      : Math.max(
          0,
          0.18 *
            Math.pow(Math.max(0.1, o2Margin + 1.5), 1.35) *
            mat.baseFlammability *
            flowFactor *
            (flowDirection === "CONCURRENT" ? 1.35 : 0.72)
        );
  const predictedSpreadRateMmS = Number(clamp(baseSpreadRate, 0, 12.5).toFixed(2));

  const predictedCoEmissionPpm = Math.round(
    clamp(
      coPpm * 0.4 + probability * 1.15 * mat.coYieldFactor,
      1,
      280
    )
  );

  // Factor attribution breakdown (sums to 100% of current risk drivers)
  const fO2 = Math.max(8, Math.round(oxygenScore * 0.55));
  const fFlow = Math.max(8, Math.round(flowFactor * 28 * (flowDirection === "CONCURRENT" ? 1.2 : 0.85)));
  const fMat = Math.max(6, Math.round(mat.baseFlammability * 34));
  const fThermal = Math.max(5, Math.round(thermalFactor * 18));
  const fGas = Math.max(3, Math.round(coAnomalyBoost + co2AnomalyBoost + 4));
  const factorSum = fO2 + fFlow + fMat + fThermal + fGas;

  const factorContributions = [
    {
      id: "oxygen",
      label: "Oxygen input and model partial pressure",
      value: `${oxygenPercent.toFixed(1)}% (${partialPressureO2Kpa.toFixed(1)} kPa)`,
      weightPercent: Math.round((fO2 / factorSum) * 100),
      color: oxygenPercent > 23 ? NASA_PALETTE.rocketRed.hex : NASA_PALETTE.blueYonder.hex,
    },
    {
      id: "airflow",
      label: "Airflow and direction inputs",
      value: `${airflowCmS.toFixed(1)} cm/s (${
        flowDirection === "CONCURRENT" ? "Concurrent" : "Opposed"
      })`,
      weightPercent: Math.round((fFlow / factorSum) * 100),
      color:
        airflowCmS >= 3 && airflowCmS <= 25
          ? NASA_PALETTE.neonYellow.hex
          : NASA_PALETTE.blueYonder.hex,
    },
    {
      id: "material",
      label: `Illustrative material coefficient (${mat.id})`,
      value: `LOI: ${mat.loi}% O₂`,
      weightPercent: Math.round((fMat / factorSum) * 100),
      color: mat.baseFlammability > 0.6 ? NASA_PALETTE.rocketRed.hex : NASA_PALETTE.neonBlue.hex,
    },
    {
      id: "thermal",
      label: "Power and temperature inputs",
      value: `${ignitionPowerW} W / ${temperatureC.toFixed(1)}°C`,
      weightPercent: Math.round((fThermal / factorSum) * 100),
      color: NASA_PALETTE.neonBlue.hex,
    },
    {
      id: "telemetry",
      label: "CO / CO₂ scenario inputs",
      value: `${coPpm} ppm CO / ${co2Percent.toFixed(2)}% CO₂`,
      weightPercent: Math.max(
        3,
        100 -
          Math.round((fO2 / factorSum) * 100) -
          Math.round((fFlow / factorSum) * 100) -
          Math.round((fMat / factorSum) * 100) -
          Math.round((fThermal / factorSum) * 100)
      ),
      color: coPpm > 40 ? NASA_PALETTE.neonYellow.hex : NASA_PALETTE.blueYonder.hex,
    },
  ];

  return {
    probability,
    riskLevel,
    riskLabelTr,
    riskColor,
    flameRegime,
    regimeDescription,
    metrics: {
      partialPressureO2Kpa: Number(partialPressureO2Kpa.toFixed(1)),
      effectiveVelocityCmS: Number(effectiveVelocityCmS.toFixed(1)),
      buoyantVelocityCmS: Number(buoyantVelocityCmS.toFixed(1)),
      effectiveLoi: Number(effectiveLoi.toFixed(1)),
      predictedSpreadRateMmS,
      predictedCoEmissionPpm,
    },
    factorContributions,
  };
}

/**
 * Retains the existing illustrative model variants for charts.
 * These patches are not operating advice or source-backed interventions.
 */
export function generateMitigationRecommendations(params) {
  const baseline = evaluateFireRisk(params);
  const candidates = [];

  // 1. Ventilation Airflow Starvation (Quenching Protocol - PSI-25 BASS-II B13/B14)
  if (params.airflowCmS > 2.0) {
    const targetAirflow = params.gravityG < 0.05 ? 1.2 : 2.0;
    const patch = { airflowCmS: targetAirflow };
    const after = evaluateFireRisk({ ...params, ...patch });
    const delta = Number((baseline.probability - after.probability).toFixed(1));
    if (delta > 1.5) {
      candidates.push({
        id: "rec-airflow-quench",
        priority: delta >= 15 ? "MODEL VARIANT" : "MODEL VARIANT",
        category: "Airflow variant",
        title: "Illustrative airflow variant",
        rationale: "Illustrative model variant only; no real-world recommendation or source-supported effect is established.",
        psiReference: null,
        riskReductionDelta: delta,
        postActionProbability: after.probability,
        patch,
      });
    }
  }

  // 2. Oxygen Partial Pressure / Hypoxic Buffer Regulation (PSI-25 & Exploration Atm)
  if (params.oxygenPercent > 19.2) {
    const targetO2 = params.oxygenPercent > 24 ? 20.5 : 17.5;
    const targetPressure =
      params.pressureKpa < 75 && targetO2 <= 21 ? 92.0 : params.pressureKpa;
    const patch = { oxygenPercent: targetO2, pressureKpa: targetPressure };
    const after = evaluateFireRisk({ ...params, ...patch });
    const delta = Number((baseline.probability - after.probability).toFixed(1));
    if (delta > 2.0) {
      candidates.push({
        id: "rec-o2-normoxic",
        priority: params.oxygenPercent >= 24 ? "MODEL VARIANT" : "MODEL VARIANT",
        category: "Oxygen / pressure variant",
        title: "Illustrative oxygen / pressure variant",
        rationale: "Illustrative model variant only; no real-world recommendation or source-supported effect is established.",
        psiReference: null,
        riskReductionDelta: delta,
        postActionProbability: after.probability,
        patch,
      });
    }
  }

  // 3. Flow Direction Reversal: Concurrent -> Opposed (PSI-98 SAFFIRE-I S1 vs S2)
  if (params.flowDirection === "CONCURRENT" && params.airflowCmS >= 2.0) {
    const patch = { flowDirection: "OPPOSED" };
    const after = evaluateFireRisk({ ...params, ...patch });
    const delta = Number((baseline.probability - after.probability).toFixed(1));
    if (delta > 1.0) {
      candidates.push({
        id: "rec-flow-direction",
        priority: "MODEL VARIANT",
        category: "Direction variant",
        title: "Illustrative direction variant",
        rationale: "Illustrative model variant only; no real-world recommendation or source-supported effect is established.",
        psiReference: null,
        riskReductionDelta: delta,
        postActionProbability: after.probability,
        patch,
      });
    }
  }

  // 4. Material Barrier / Flame-Retardant Substitution (PSI-25 F1 & PSI-99 Test 2-7 Nomex III)
  if (params.material !== "Nomex III" && params.material !== "Teflon") {
    const patch = { material: "Nomex III" };
    const after = evaluateFireRisk({ ...params, ...patch });
    const delta = Number((baseline.probability - after.probability).toFixed(1));
    if (delta > 2.0) {
      candidates.push({
        id: "rec-material-nomex",
        priority: "MODEL VARIANT",
        category: "Material variant",
        title: "Illustrative material variant",
        rationale: "Illustrative model variant only; no real-world recommendation or source-supported effect is established.",
        psiReference: null,
        riskReductionDelta: delta,
        postActionProbability: after.probability,
        patch,
      });
    }
  }

  // 5. Thermal Power & Pyrolysis Cut-off (PSI-101 SAME-R Early Smoke Detection)
  if (params.ignitionPowerW > 55 || params.coPpm > 25) {
    const patch = {
      ignitionPowerW: 40,
      temperatureC: Math.min(params.temperatureC, 21.5),
      coPpm: Math.min(params.coPpm, 8),
    };
    const after = evaluateFireRisk({ ...params, ...patch });
    const delta = Number((baseline.probability - after.probability).toFixed(1));
    if (delta > 1.0) {
      candidates.push({
        id: "rec-thermal-cutoff",
        priority: params.coPpm > 50 ? "MODEL VARIANT" : "MODEL VARIANT",
        category: "Power / gas variant",
        title: "Illustrative power / gas variant",
        rationale: "Illustrative model variant only; no real-world recommendation or source-supported effect is established.",
        psiReference: null,
        riskReductionDelta: delta,
        postActionProbability: after.probability,
        patch,
      });
    }
  }

  candidates.sort((a, b) => b.riskReductionDelta - a.riskReductionDelta);

  // Combined optimization state
  const combinedPatch = candidates.reduce((acc, item) => ({ ...acc, ...item.patch }), {});
  const optimizedEval = evaluateFireRisk({ ...params, ...combinedPatch });

  return {
    baseline,
    recommendations: candidates,
    combinedPatch,
    optimizedProbability: optimizedEval.probability,
    totalReductionDelta: Number(
      Math.max(0, baseline.probability - optimizedEval.probability).toFixed(1)
    ),
  };
}

/**
 * Generates 16 example model points on an arbitrary time axis.
 * No points are sensor history or validated future forecasts.
 */
export function generateTelemetryTimeline(params) {
  const { baseline, optimizedProbability, combinedPatch } =
    generateMitigationRecommendations(params);

  const points = [];
  for (let i = 0; i < 16; i++) {
    const tSec = (i - 10) * 10; // -100s to +50s
    const wave = Math.sin(i * 0.65) * 1.8;

    if (tSec <= 0) {
      // Historical leading up to t=0 (now)
      const progress = (i + 1) / 11;
      const risk = clamp(
        baseline.probability * (0.72 + 0.28 * progress) + wave,
        2,
        99
      );
      const o2 = clamp(
        params.oxygenPercent - (1 - progress) * 0.4 + Math.cos(i) * 0.08,
        12,
        40
      );
      const flow = clamp(
        params.airflowCmS * (0.85 + 0.15 * progress) + Math.sin(i) * 0.4,
        0,
        50
      );
      const co = Math.round(
        clamp(params.coPpm * (0.5 + 0.5 * progress) + Math.abs(wave) * 2, 0, 250)
      );
      points.push({
        label: `${tSec === 0 ? "REFERENCE" : `${tSec}s`}`,
        tSec,
        isForecast: false,
        riskUnmitigated: Number(risk.toFixed(1)),
        riskMitigated: Number(risk.toFixed(1)),
        oxygenPercent: Number(o2.toFixed(2)),
        airflowCmS: Number(flow.toFixed(1)),
        coPpm: co,
      });
    } else {
      // Forecast (t > 0): Unmitigated vs AI Countermeasure Applied
      const step = i - 10; // 1..5
      const factor = step / 5;
      const unmitigatedRisk = clamp(
        baseline.probability +
          (baseline.probability >= 45 ? step * 3.1 : step * 0.6) +
          wave * 0.5,
        2,
        99.4
      );
      const mitigatedRisk = clamp(
        baseline.probability -
          (baseline.probability - optimizedProbability) * (1 - Math.exp(-step * 0.75)),
        1.5,
        99
      );
      const targetFlow = combinedPatch.airflowCmS ?? params.airflowCmS;
      const targetO2 = combinedPatch.oxygenPercent ?? params.oxygenPercent;

      points.push({
        label: `+${tSec}s`,
        tSec,
        isForecast: true,
        riskUnmitigated: Number(unmitigatedRisk.toFixed(1)),
        riskMitigated: Number(mitigatedRisk.toFixed(1)),
        oxygenPercent: Number(
          (params.oxygenPercent + (targetO2 - params.oxygenPercent) * factor).toFixed(2)
        ),
        airflowCmS: Number(
          (params.airflowCmS + (targetFlow - params.airflowCmS) * factor).toFixed(1)
        ),
        coPpm: Math.round(
          clamp(
            params.coPpm * (1 - 0.65 * factor) + 2,
            1,
            250
          )
        ),
      });
    }
  }
  return points;
}
