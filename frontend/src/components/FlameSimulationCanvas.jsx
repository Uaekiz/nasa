import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { NASA_PALETTE } from "../theme/nasaPalette";

/**
 * Vertex Shader for 3D Microgravity & Partial-Gravity Flame Morphology
 * Dynamically morphs a high-resolution sphere into:
 * - A spherical diffusion flame in quiescent 0g (low airflow, 0g)
 * - An elongated forced-convection plume along X (airflowCmS)
 * - An upward-curved buoyant plume along Y (gravityG)
 */
const FLAME_VERTEX_SHADER = `
  uniform float uTime;
  uniform float uStretchX;
  uniform float uBuoyancyY;
  uniform float uScale;
  uniform float uTurbulence;
  varying vec3 vNormal;
  varying vec3 vViewPosition;
  varying vec3 vLocalPos;
  varying float vAxialProgress;

  void main() {
    vLocalPos = position;
    vec3 pos = position * uScale;

    // Determine downstream factor (how far towards the flame tail this vertex is)
    float flowDir = sign(uStretchX == 0.0 ? 1.0 : uStretchX);
    float downstream = clamp((position.x * flowDir + 1.0) * 0.5, 0.0, 1.0);
    float topFactor = clamp((position.y + 1.0) * 0.5, 0.0, 1.0);
    float tailWeight = max(downstream * abs(uStretchX) * 0.45, topFactor * uBuoyancyY * 0.55);
    vAxialProgress = clamp(downstream * 0.75 + topFactor * 0.35, 0.0, 1.0);

    // Taper tail into a realistic aerodynamic flame tip
    float taper = 1.0 - 0.52 * pow(downstream, 1.4) * clamp(abs(uStretchX) * 0.4, 0.0, 1.0);
    pos.y *= taper;
    pos.z *= taper;

    // Stretch along airflow vector (X) and buoyancy vector (Y)
    pos.x += pow(downstream, 1.25) * uStretchX;
    pos.y += pow(downstream, 1.35) * uBuoyancyY * 0.65 + pow(topFactor, 1.3) * uBuoyancyY * 0.85;

    // Multi-frequency 3D flame surface instability / flicker
    float wave1 = sin(uTime * 6.5 - position.x * flowDir * 4.0 + position.y * 3.0);
    float wave2 = cos(uTime * 9.2 + position.z * 5.0 - position.x * 3.5);
    float displacement = (wave1 * 0.08 + wave2 * 0.05) * uTurbulence * (0.25 + tailWeight * 0.9);

    pos.y += displacement;
    pos.z += displacement * 0.7;

    vec4 mvPosition = modelViewMatrix * vec4(pos, 1.0);
    vViewPosition = -mvPosition.xyz;
    vNormal = normalize(normalMatrix * normal);
    gl_Position = projectionMatrix * mvPosition;
  }
`;

/**
 * Fragment Shader mapped strictly to the NASA Color Palette:
 * - #0960E1 (Neon Blue) & #2E96F5 (Blue Yonder) for 0g chemiluminescent base/halo
 * - #E43700 (Rocket Red) & #8E1100 (Martian Red) for active reaction front
 * - #EAFE07 (Neon Yellow) & #FFFFFF (White) for high-temp inner core
 */
const FLAME_FRAGMENT_SHADER = `
  uniform float uTime;
  uniform float uIntensity;
  uniform float uIsSpherical0g;
  uniform float uIsQuenching;
  uniform float uLayerType; // 0.0 = inner core, 1.0 = outer reaction envelope

  varying vec3 vNormal;
  varying vec3 vViewPosition;
  varying vec3 vLocalPos;
  varying float vAxialProgress;

  void main() {
    vec3 viewDir = normalize(vViewPosition);
    float fresnel = 1.0 - abs(dot(viewDir, normalize(vNormal)));

    // Official NASA Palette RGB values normalized
    vec3 cWhite       = vec3(1.000, 1.000, 1.000); // #FFFFFF
    vec3 cNeonYellow  = vec3(0.918, 0.996, 0.027); // #EAFE07
    vec3 cRocketRed   = vec3(0.894, 0.216, 0.000); // #E43700
    vec3 cMartianRed  = vec3(0.557, 0.067, 0.000); // #8E1100
    vec3 cBlueYonder  = vec3(0.180, 0.588, 0.961); // #2E96F5
    vec3 cNeonBlue    = vec3(0.035, 0.376, 0.882); // #0960E1

    vec3 color;
    float alpha;

    if (uLayerType < 0.5) {
      // Inner Core Layer
      if (uIsSpherical0g > 0.5 || uIsQuenching > 0.5) {
        color = mix(cWhite, cBlueYonder, clamp(fresnel * 1.1, 0.0, 1.0));
        alpha = (0.78 - fresnel * 0.45) * (uIsQuenching > 0.5 ? 0.55 : 0.9);
      } else {
        vec3 hotCore = mix(cWhite, cNeonYellow, clamp(vAxialProgress * 1.1, 0.0, 1.0));
        color = mix(hotCore, cRocketRed, pow(fresnel, 1.5));
        alpha = clamp(0.92 - fresnel * 0.5, 0.15, 0.95);
      }
    } else {
      // Outer Reaction & Chemiluminescence Envelope
      if (uIsSpherical0g > 0.5 || uIsQuenching > 0.5) {
        color = mix(cBlueYonder, cNeonBlue, clamp(fresnel * 1.2, 0.0, 1.0));
        alpha = clamp((1.0 - pow(fresnel, 1.8)) * 0.62, 0.08, 0.72) * (uIsQuenching > 0.5 ? 0.5 : 1.0);
      } else {
        // Leading edge is Neon Blue / Blue Yonder; downstream wake transitions to Rocket Red & Neon Yellow
        vec3 baseToWake = mix(cNeonBlue, cRocketRed, smoothstep(0.12, 0.58, vAxialProgress));
        baseToWake = mix(baseToWake, cMartianRed, smoothstep(0.68, 1.0, vAxialProgress) * 0.5);
        color = mix(baseToWake, cBlueYonder, (1.0 - vAxialProgress) * fresnel * 0.85);
        float flicker = 0.92 + 0.08 * sin(uTime * 11.0 + vLocalPos.x * 4.0);
        alpha = clamp((0.76 - pow(fresnel, 1.6) * 0.58) * flicker * (0.65 + uIntensity * 0.35), 0.05, 0.84);
      }
    }

    gl_FragColor = vec4(color, alpha);
  }
`;

export default function FlameSimulationCanvas({
  params,
  riskEvaluation,
  onApplyAllRecommendations,
  hasRecommendations,
}) {
  const mountRef = useRef(null);
  const [isRunning, setIsRunning] = useState(true);
  const [cameraPreset, setCameraPreset] = useState("iso");

  // Keep latest props in a ref so the 60fps Three.js loop always reads fresh telemetry without re-creating the WebGL context
  const livePropsRef = useRef({ params, riskEvaluation, isRunning });
  useEffect(() => {
    livePropsRef.current = { params, riskEvaluation, isRunning };
  }, [params, riskEvaluation, isRunning]);

  // Camera spherical coordinates for smooth mouse drag orbit + preset switching
  const cameraOrbitRef = useRef({
    theta: 0.38,
    phi: 1.22,
    radius: 6.2,
    targetTheta: 0.38,
    targetPhi: 1.22,
    targetRadius: 6.2,
    isDragging: false,
    lastX: 0,
    lastY: 0,
  });

  const handleSetCameraView = (view) => {
    setCameraPreset(view);
    const orbit = cameraOrbitRef.current;
    if (view === "iso") {
      orbit.targetTheta = 0.42;
      orbit.targetPhi = 1.18;
      orbit.targetRadius = 6.2;
    } else if (view === "side") {
      orbit.targetTheta = 0.0;
      orbit.targetPhi = Math.PI / 2;
      orbit.targetRadius = 5.8;
    } else if (view === "top") {
      orbit.targetTheta = 0.0;
      orbit.targetPhi = 0.22;
      orbit.targetRadius = 6.6;
    }
  };

  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    const width = container.clientWidth || 720;
    const height = container.clientHeight || 340;

    // 1. Scene & Deep Blue Space Chamber Backdrop (#07173F)
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(NASA_PALETTE.deepBlue.hex);
    scene.fog = new THREE.FogExp2(NASA_PALETTE.deepBlue.hex, 0.045);

    const camera = new THREE.PerspectiveCamera(42, width / height, 0.1, 100);

    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      powerPreference: "high-performance",
    });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    container.innerHTML = "";
    container.appendChild(renderer.domElement);

    // 2. Lighting
    const ambientLight = new THREE.AmbientLight(NASA_PALETTE.blueYonder.hex, 0.9);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(NASA_PALETTE.white.hex, 1.1);
    dirLight.position.set(4, 6, 5);
    scene.add(dirLight);

    const flameLight = new THREE.PointLight(NASA_PALETTE.rocketRed.hex, 2.8, 9);
    flameLight.position.set(0, 0.2, 0);
    scene.add(flameLight);

    // 3. Technical Wind-Tunnel / MSG Chamber Grid & Rings
    const gridHelper = new THREE.GridHelper(
      10,
      20,
      NASA_PALETTE.blueYonder.hex,
      NASA_PALETTE.electricBlue.hex
    );
    gridHelper.position.y = -1.35;
    gridHelper.material.opacity = 0.45;
    gridHelper.material.transparent = true;
    scene.add(gridHelper);

    // Cylindrical tunnel rings (#0042A6 Electric Blue)
    const ringGroup = new THREE.Group();
    const ringGeo = new THREE.RingGeometry(1.75, 1.78, 48);
    const ringMat = new THREE.MeshBasicMaterial({
      color: NASA_PALETTE.electricBlue.hex,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.45,
    });
    [-3.2, -1.6, 0, 1.6, 3.2].forEach((xPos) => {
      const rMesh = new THREE.Mesh(ringGeo, ringMat);
      rMesh.rotation.y = Math.PI / 2;
      rMesh.position.set(xPos, 0.1, 0);
      ringGroup.add(rMesh);
    });
    scene.add(ringGroup);

    // 4. Fuel Sample Holder & Pyrolysis Zone
    const sampleGroup = new THREE.Group();
    const holderGeo = new THREE.BoxGeometry(2.6, 0.14, 0.9);
    const holderMat = new THREE.MeshStandardMaterial({
      color: NASA_PALETTE.electricBlue.hex,
      roughness: 0.35,
      metalness: 0.65,
    });
    const holderMesh = new THREE.Mesh(holderGeo, holderMat);
    holderMesh.position.set(0, -0.42, 0);
    sampleGroup.add(holderMesh);

    const fuelStripGeo = new THREE.BoxGeometry(2.2, 0.08, 0.68);
    const fuelStripMat = new THREE.MeshStandardMaterial({
      color: NASA_PALETTE.white.hex,
      roughness: 0.4,
    });
    const fuelStripMesh = new THREE.Mesh(fuelStripGeo, fuelStripMat);
    fuelStripMesh.position.set(0, -0.32, 0);
    sampleGroup.add(fuelStripMesh);

    // Pyrolysis / char glow patch on sample surface
    const charGeo = new THREE.BoxGeometry(1.1, 0.09, 0.56);
    const charMat = new THREE.MeshStandardMaterial({
      color: NASA_PALETTE.martianRed.hex,
      emissive: NASA_PALETTE.rocketRed.hex,
      emissiveIntensity: 0.45,
    });
    const charMesh = new THREE.Mesh(charGeo, charMat);
    charMesh.position.set(0, -0.315, 0);
    sampleGroup.add(charMesh);

    // Droplet sphere for FLEX liquid fuel mode (Methanol / Heptane)
    const dropletGeo = new THREE.SphereGeometry(0.22, 32, 32);
    const dropletMat = new THREE.MeshStandardMaterial({
      color: NASA_PALETTE.white.hex,
      emissive: NASA_PALETTE.blueYonder.hex,
      emissiveIntensity: 0.3,
      roughness: 0.15,
    });
    const dropletMesh = new THREE.Mesh(dropletGeo, dropletMat);
    dropletMesh.position.set(-0.35, -0.05, 0);
    sampleGroup.add(dropletMesh);

    scene.add(sampleGroup);

    // 5. 3D Volumetric Multi-Layer Flame Meshes (Outer Reaction + Inner Core)
    const flameBaseGeo = new THREE.SphereGeometry(0.55, 64, 48);

    const outerUniforms = {
      uTime: { value: 0 },
      uStretchX: { value: 1.2 },
      uBuoyancyY: { value: 0.0 },
      uScale: { value: 1.0 },
      uTurbulence: { value: 1.0 },
      uIntensity: { value: 0.7 },
      uIsSpherical0g: { value: 0.0 },
      uIsQuenching: { value: 0.0 },
      uLayerType: { value: 1.0 },
    };

    const innerUniforms = {
      uTime: { value: 0 },
      uStretchX: { value: 0.85 },
      uBuoyancyY: { value: 0.0 },
      uScale: { value: 0.62 },
      uTurbulence: { value: 0.7 },
      uIntensity: { value: 0.7 },
      uIsSpherical0g: { value: 0.0 },
      uIsQuenching: { value: 0.0 },
      uLayerType: { value: 0.0 },
    };

    const outerFlameMat = new THREE.ShaderMaterial({
      vertexShader: FLAME_VERTEX_SHADER,
      fragmentShader: FLAME_FRAGMENT_SHADER,
      uniforms: outerUniforms,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      side: THREE.DoubleSide,
    });

    const innerFlameMat = new THREE.ShaderMaterial({
      vertexShader: FLAME_VERTEX_SHADER,
      fragmentShader: FLAME_FRAGMENT_SHADER,
      uniforms: innerUniforms,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });

    const outerFlameMesh = new THREE.Mesh(flameBaseGeo, outerFlameMat);
    const innerFlameMesh = new THREE.Mesh(flameBaseGeo, innerFlameMat);
    outerFlameMesh.position.set(-0.35, -0.05, 0);
    innerFlameMesh.position.set(-0.35, -0.05, 0);
    scene.add(outerFlameMesh);
    scene.add(innerFlameMesh);

    // 6. 3D Ventilation Airflow Streamlines (#2E96F5 Blue Yonder)
    const airCount = 90;
    const airPositions = new Float32Array(airCount * 6); // 2 vertices per line segment
    const airSeeds = Array.from({ length: airCount }, (_, i) => ({
      x: -3.5 + ((i * 0.43) % 7.0),
      y: -1.0 + ((i * 0.29) % 2.3),
      z: -1.1 + ((i * 0.37) % 2.2),
      speedMul: 0.75 + (i % 5) * 0.12,
    }));

    const airLineGeo = new THREE.BufferGeometry();
    airLineGeo.setAttribute(
      "position",
      new THREE.BufferAttribute(airPositions, 3)
    );
    const airLineMat = new THREE.LineBasicMaterial({
      color: NASA_PALETTE.blueYonder.hex,
      transparent: true,
      opacity: 0.62,
    });
    const airLines = new THREE.LineSegments(airLineGeo, airLineMat);
    scene.add(airLines);

    // 7. 3D Flame Embers / Pyrolysis Soot Particles (#EAFE07 Neon Yellow & #E43700 Rocket Red)
    const emberCount = 75;
    const emberPositions = new Float32Array(emberCount * 3);
    const emberColors = new Float32Array(emberCount * 3);
    const cYellow = new THREE.Color(NASA_PALETTE.neonYellow.hex);
    const cRed = new THREE.Color(NASA_PALETTE.rocketRed.hex);

    const emberData = Array.from({ length: emberCount }, (_, i) => {
      const c = i % 2 === 0 ? cYellow : cRed;
      emberColors[i * 3] = c.r;
      emberColors[i * 3 + 1] = c.g;
      emberColors[i * 3 + 2] = c.b;
      return {
        x: -0.35,
        y: -0.05,
        z: 0,
        age: (i * 0.07) % 1.0,
        spreadY: ((i % 7) - 3) * 0.06,
        spreadZ: ((i % 5) - 2) * 0.06,
      };
    });

    const emberGeo = new THREE.BufferGeometry();
    emberGeo.setAttribute(
      "position",
      new THREE.BufferAttribute(emberPositions, 3)
    );
    emberGeo.setAttribute("color", new THREE.BufferAttribute(emberColors, 3));
    const emberMat = new THREE.PointsMaterial({
      size: 0.085,
      vertexColors: true,
      transparent: true,
      opacity: 0.85,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const emberPoints = new THREE.Points(emberGeo, emberMat);
    scene.add(emberPoints);

    // Mouse Orbit Interaction Handlers
    const domElem = renderer.domElement;
    const onPointerDown = (e) => {
      cameraOrbitRef.current.isDragging = true;
      cameraOrbitRef.current.lastX = e.clientX;
      cameraOrbitRef.current.lastY = e.clientY;
    };
    const onPointerMove = (e) => {
      if (!cameraOrbitRef.current.isDragging) return;
      const dx = e.clientX - cameraOrbitRef.current.lastX;
      const dy = e.clientY - cameraOrbitRef.current.lastY;
      cameraOrbitRef.current.lastX = e.clientX;
      cameraOrbitRef.current.lastY = e.clientY;
      cameraOrbitRef.current.targetTheta -= dx * 0.007;
      cameraOrbitRef.current.targetPhi = Math.max(
        0.2,
        Math.min(Math.PI * 0.48, cameraOrbitRef.current.targetPhi - dy * 0.006)
      );
      setCameraPreset("custom");
    };
    const onPointerUp = () => {
      cameraOrbitRef.current.isDragging = false;
    };

    domElem.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);

    // ResizeObserver for seamless responsive layout
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const w = entry.contentRect.width;
        const h = entry.contentRect.height;
        if (w > 0 && h > 0) {
          camera.aspect = w / h;
          camera.updateProjectionMatrix();
          renderer.setSize(w, h);
        }
      }
    });
    resizeObserver.observe(container);

    // 8. 60fps Animation Loop
    let animId;
    let simClock = 0;

    const animate = () => {
      animId = requestAnimationFrame(animate);

      const {
        params: curParams,
        riskEvaluation: curEval,
        isRunning: running,
      } = livePropsRef.current;

      if (running) {
        simClock += 0.016;
      }

      const {
        airflowCmS = 8.5,
        gravityG = 0.0,
        material = "PMMA Film",
        flowDirection = "CONCURRENT",
      } = curParams;
      const { probability = 50, flameRegime = "" } = curEval;

      const flowSign = flowDirection === "CONCURRENT" ? 1 : -1;
      const isDroplet = material === "Methanol" || material === "Heptane";
      const isQuenching =
        flameRegime === "QUENCHING_STARVATION" || probability < 16 ? 1.0 : 0.0;
      const isSpherical0g =
        gravityG < 0.05 && airflowCmS < 2.2 ? 1.0 : 0.0;

      // Toggle sample geometry visibility (Droplet vs Solid Strip)
      dropletMesh.visible = isDroplet;
      holderMesh.visible = !isDroplet;
      fuelStripMesh.visible = !isDroplet;
      charMesh.visible = !isDroplet;

      const intensity = Math.max(0.18, probability / 100);
      const stretchX =
        isSpherical0g > 0.5
          ? flowSign * airflowCmS * 0.08
          : flowSign *
            Math.min(2.35, 0.25 + airflowCmS * 0.072) *
            (isQuenching > 0.5 ? 0.35 : 1.0);
      const buoyancyY =
        Math.min(1.85, gravityG * 2.1) * (isQuenching > 0.5 ? 0.3 : 1.0);
      const baseScale =
        isQuenching > 0.5
          ? 0.42
          : Math.max(0.55, Math.min(1.28, 0.52 + intensity * 0.68));

      // Update Shader Uniforms
      outerUniforms.uTime.value = simClock;
      outerUniforms.uStretchX.value = stretchX;
      outerUniforms.uBuoyancyY.value = buoyancyY;
      outerUniforms.uScale.value = baseScale;
      outerUniforms.uTurbulence.value = 0.6 + airflowCmS * 0.04;
      outerUniforms.uIntensity.value = intensity;
      outerUniforms.uIsSpherical0g.value = isSpherical0g;
      outerUniforms.uIsQuenching.value = isQuenching;

      innerUniforms.uTime.value = simClock * 1.15;
      innerUniforms.uStretchX.value = stretchX * 0.68;
      innerUniforms.uBuoyancyY.value = buoyancyY * 0.68;
      innerUniforms.uScale.value = baseScale * 0.62;
      innerUniforms.uTurbulence.value = 0.45 + airflowCmS * 0.03;
      innerUniforms.uIntensity.value = intensity;
      innerUniforms.uIsSpherical0g.value = isSpherical0g;
      innerUniforms.uIsQuenching.value = isQuenching;

      // Update dynamic point light color & intensity
      flameLight.color.set(
        isSpherical0g > 0.5 || isQuenching > 0.5
          ? NASA_PALETTE.blueYonder.hex
          : probability >= 65
          ? NASA_PALETTE.rocketRed.hex
          : NASA_PALETTE.neonBlue.hex
      );
      flameLight.intensity =
        (isQuenching > 0.5 ? 1.1 : 2.2 + intensity * 1.8) +
        Math.sin(simClock * 9) * 0.25;

      // Update 3D Airflow Streamlines
      const posAttr = airLineGeo.getAttribute("position");
      const streakLen = Math.max(0.12, Math.min(0.75, airflowCmS * 0.025));
      const stepSpeed = Math.max(0.008, airflowCmS * 0.0038);

      for (let i = 0; i < airCount; i++) {
        const s = airSeeds[i];
        if (running) {
          s.x += flowSign * stepSpeed * s.speedMul;
          if (flowSign === 1 && s.x > 3.5) s.x = -3.5;
          if (flowSign === -1 && s.x < -3.5) s.x = 3.5;
        }
        const i6 = i * 6;
        posAttr.array[i6] = s.x;
        posAttr.array[i6 + 1] = s.y;
        posAttr.array[i6 + 2] = s.z;
        posAttr.array[i6 + 3] = s.x - flowSign * streakLen;
        posAttr.array[i6 + 4] = s.y;
        posAttr.array[i6 + 5] = s.z;
      }
      posAttr.needsUpdate = true;

      // Update 3D Ember / Pyrolysis Particles
      const emberAttr = emberGeo.getAttribute("position");
      for (let i = 0; i < emberCount; i++) {
        const em = emberData[i];
        if (running) {
          em.age += 0.012 + airflowCmS * 0.0005;
          if (em.age > 1.0) em.age = 0.0;
        }
        const p = em.age;
        const ex = -0.35 + stretchX * p * 1.35;
        const ey =
          -0.05 +
          buoyancyY * p * 1.15 +
          em.spreadY * p * 3.0 +
          Math.sin(simClock * 5 + i) * 0.05;
        const ez = em.spreadZ * p * 3.0 + Math.cos(simClock * 4 + i) * 0.05;

        emberAttr.array[i * 3] = ex;
        emberAttr.array[i * 3 + 1] = ey;
        emberAttr.array[i * 3 + 2] = ez;
      }
      emberAttr.needsUpdate = true;
      emberMat.opacity = isQuenching > 0.5 ? 0.25 : 0.85;

      // Smooth Camera Orbit Interpolation
      const orbit = cameraOrbitRef.current;
      orbit.theta += (orbit.targetTheta - orbit.theta) * 0.1;
      orbit.phi += (orbit.targetPhi - orbit.phi) * 0.1;
      orbit.radius += (orbit.targetRadius - orbit.radius) * 0.1;

      camera.position.x =
        orbit.radius * Math.sin(orbit.phi) * Math.sin(orbit.theta);
      camera.position.y = orbit.radius * Math.cos(orbit.phi);
      camera.position.z =
        orbit.radius * Math.sin(orbit.phi) * Math.cos(orbit.theta);
      camera.lookAt(0.15, 0.0, 0);

      renderer.render(scene, camera);
    };

    animId = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(animId);
      resizeObserver.disconnect();
      domElem.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      renderer.dispose();
    };
  }, []);

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
          <div className="camera-view-group" role="group" aria-label="Kamera Açısı">
            <button
              type="button"
              className={`nasa-btn nasa-btn-xs ${
                cameraPreset === "iso" ? "active" : ""
              }`}
              onClick={() => handleSetCameraView("iso")}
            >
              3B İzometrik
            </button>
            <button
              type="button"
              className={`nasa-btn nasa-btn-xs ${
                cameraPreset === "side" ? "active" : ""
              }`}
              onClick={() => handleSetCameraView("side")}
            >
              Yan Kesit
            </button>
            <button
              type="button"
              className={`nasa-btn nasa-btn-xs ${
                cameraPreset === "top" ? "active" : ""
              }`}
              onClick={() => handleSetCameraView("top")}
            >
              Üst Bakış
            </button>
          </div>

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
      <div className="sim-canvas-wrapper">
        <div
          ref={mountRef}
          className="three-mount-box"
          title="3B sahneyi döndürmek için fareyle sürükleyin"
        />

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
      </div>

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
