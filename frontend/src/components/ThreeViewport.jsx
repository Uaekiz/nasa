import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

// Shared by the live simulation and the static, source-only experiment view.
// Scene factories own content; this component owns camera, WebGL and cleanup.
export default function ThreeViewport({ createScene, animated = false, label, children }) {
  const mountRef = useRef(null);
  const actionsRef = useRef(null);
  const [failure, setFailure] = useState("");

  useEffect(() => {
    const container = mountRef.current;
    const scene = new THREE.Scene();
    let renderer, controls, observer, sceneState;
    let frame = null;
    let disposed = false;
    const geometries = new Set(), materials = new Set(), textures = new Set();
    const release = () => {
      if (disposed) return;
      disposed = true;
      cancelAnimationFrame(frame);
      observer?.disconnect();
      controls?.dispose();
      sceneState?.dispose?.();
      scene.traverse((object) => {
        if (object.geometry) geometries.add(object.geometry);
        for (const material of [object.material].flat().filter(Boolean)) {
          materials.add(material);
          for (const value of Object.values(material)) if (value?.isTexture) textures.add(value);
          for (const uniform of Object.values(material.uniforms || {})) if (uniform.value?.isTexture) textures.add(uniform.value);
        }
      });
      textures.forEach((texture) => texture.dispose());
      materials.forEach((material) => material.dispose());
      geometries.forEach((geometry) => geometry.dispose());
      scene.clear();
      if (renderer) {
        renderer.domElement.removeEventListener("webglcontextlost", contextLost);
        renderer.renderLists.dispose();
        renderer.dispose();
        renderer.forceContextLoss();
        renderer.domElement.remove();
      }
      actionsRef.current = null;
    };
    const contextLost = (event) => {
      event.preventDefault();
      release();
      setFailure("WebGL bağlamı kayboldu. Kaynak parametreleri aşağıda gösteriliyor; görünümü yeniden açabilirsiniz.");
    };
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: animated ? "high-performance" : "low-power" });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.domElement.setAttribute("aria-label", label);
      renderer.domElement.setAttribute("role", "img");
      renderer.domElement.addEventListener("webglcontextlost", contextLost);
      container.appendChild(renderer.domElement);
      sceneState = createScene(scene);
      const radius = sceneState.radius || 6;
      const target = new THREE.Vector3(...(sceneState.target || [0, 0, 0]));
      const camera = new THREE.PerspectiveCamera(42, 1, radius / 1000, radius * 100);
      controls = new OrbitControls(camera, renderer.domElement);
      controls.target.copy(target);
      controls.enablePan = false;
      controls.minDistance = radius * 0.25;
      controls.maxDistance = radius * 5;
      const render = () => {
        frame = null;
        if (disposed) return;
        sceneState.update?.();
        renderer.render(scene, camera);
        if (animated) frame = requestAnimationFrame(render);
      };
      const invalidate = () => { if (!disposed && frame === null) frame = requestAnimationFrame(render); };
      controls.addEventListener("change", invalidate);
      const view = (theta, phi) => {
        camera.position.copy(target).add(new THREE.Vector3().setFromSphericalCoords(radius, phi, theta));
        controls.update();
        invalidate();
      };
      actionsRef.current = {
        reset: () => view(0.42, 1.18),
        side: () => view(0, Math.PI / 2),
        top: () => view(0, 0.05),
        zoom: (factor) => {
          const offset = camera.position.clone().sub(target);
          offset.setLength(THREE.MathUtils.clamp(offset.length() * factor, controls.minDistance, controls.maxDistance));
          camera.position.copy(target).add(offset);
          controls.update();
          invalidate();
        },
      };
      observer = new ResizeObserver(() => {
        const width = Math.max(container.clientWidth, 1), height = Math.max(container.clientHeight, 1);
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
        renderer.setSize(width, height);
        invalidate();
      });
      observer.observe(container);
      actionsRef.current.reset();
    } catch {
      release();
      // Keep source text visible even when a browser cannot create a GPU context.
      queueMicrotask(() => setFailure("3B görünüm açılamadı. WebGL desteklenmiyor veya GPU kullanılamıyor. Kaynak parametreleri metin olarak gösteriliyor."));
    }
    return release;
  }, [createScene, animated, label]);

  return <div className="three-viewport">
    <div className="camera-view-group" role="group" aria-label={`${label} kontrolleri`}>
      <button className="nasa-btn nasa-btn-xs" disabled={!!failure} onClick={() => actionsRef.current?.reset()}>Görünümü sıfırla</button>
      <button className="nasa-btn nasa-btn-xs" disabled={!!failure} onClick={() => actionsRef.current?.side()}>Yan görünüm</button>
      <button className="nasa-btn nasa-btn-xs" disabled={!!failure} onClick={() => actionsRef.current?.top()}>Üst görünüm</button>
      <button className="nasa-btn nasa-btn-xs" disabled={!!failure} aria-label="Yakınlaştır" onClick={() => actionsRef.current?.zoom(0.8)}>+</button>
      <button className="nasa-btn nasa-btn-xs" disabled={!!failure} aria-label="Uzaklaştır" onClick={() => actionsRef.current?.zoom(1.25)}>−</button>
    </div>
    <div className="sim-canvas-wrapper">
      <div ref={mountRef} className="three-mount-box" title="Döndürmek için sürükleyin; yakınlaştırmak için kaydırın veya iki parmak kullanın." />
      {failure ? <p className="webgl-fallback" role="status">{failure}</p> : children}
    </div>
  </div>;
}
