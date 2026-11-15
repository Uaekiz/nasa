import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

// Shared by the live simulation and the static, source-only experiment view.
// Scene factories own content; this component owns camera, WebGL and cleanup.
export default function ThreeViewport({
  createScene,
  animated = false,
  label,
  children,
  captureRef,
}) {
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

      if (captureRef) {
  captureRef.current = null;
}
    };
    const contextLost = (event) => {
      event.preventDefault();
      release();
      setFailure("The WebGL context was lost. Text and parameters remain available; reopen the view to try again.");
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
      if (captureRef) {
  captureRef.current = () => {
    if (disposed || renderer.getContext().isContextLost()) {
      throw new Error("The 3D view is not ready for image capture.");
    }

    // Güncel sahneyi çizip görüntüyü hemen al.
    sceneState.update?.();
    renderer.render(scene, camera);

    const image = renderer.domElement.toDataURL("image/png");

    if (!image.startsWith("data:image/png;base64,")) {
      throw new Error("The 3D image could not be created.");
    }

    return image;
  };
}
    } catch {
      release();

      // Keep source text visible even when a browser cannot create a GPU context.
      queueMicrotask(() => setFailure("The 3D view could not open. WebGL or GPU access is unavailable. Text and parameters remain available."));
    }
    return release;
  }, [createScene, animated, label, captureRef]);

  return <div className="three-viewport">
    <div className="camera-view-group" role="group" aria-label={`${label} controls`}>
      <button className="nasa-btn nasa-btn-xs" disabled={!!failure} onClick={() => actionsRef.current?.reset()}>Reset view</button>
      <button className="nasa-btn nasa-btn-xs" disabled={!!failure} onClick={() => actionsRef.current?.side()}>Side view</button>
      <button className="nasa-btn nasa-btn-xs" disabled={!!failure} onClick={() => actionsRef.current?.top()}>Top view</button>
      <button className="nasa-btn nasa-btn-xs" disabled={!!failure} aria-label="Zoom in" onClick={() => actionsRef.current?.zoom(0.8)}>+</button>
      <button className="nasa-btn nasa-btn-xs" disabled={!!failure} aria-label="Zoom out" onClick={() => actionsRef.current?.zoom(1.25)}>−</button>
    </div>
    <div className="sim-canvas-wrapper">
      <div ref={mountRef} className="three-mount-box" title="Drag to rotate; scroll or pinch to zoom." />
      {failure ? <p className="webgl-fallback" role="status">{failure}</p> : children}
    </div>
  </div>;
}
