import * as THREE from "three";

// Neutral static geometry. This module has no flame shader, clock, telemetry,
// probability, temperature, spread-rate calculation or simulation dependency.
export function createExperimentScene(scene, model) {
  scene.background = new THREE.Color("#07173f");
  scene.add(new THREE.HemisphereLight(0xddeeff, 0x26304f, 2));
  const light = new THREE.DirectionalLight(0xffffff, 2);
  light.position.set(1, 3, 5);
  scene.add(light);
  const material = new THREE.MeshStandardMaterial({ color: 0xb7c9d9, roughness: 0.75, side: THREE.DoubleSide });
  let geometry, span = 2;
  if (model.kind === "droplet") {
    span = model.diameter || 2;
    geometry = new THREE.SphereGeometry(span / 2, 40, 24);
  } else if (model.kind === "box") {
    span = Math.max(...model.dimensions);
    geometry = new THREE.BoxGeometry(...model.dimensions);
  } else if (model.kind === "cross-section") {
    span = Math.max(...model.dimensions);
    geometry = new THREE.PlaneGeometry(...model.dimensions);
  } else if (model.kind === "width") {
    span = model.width;
    // A measured line only: no guessed length, thickness or rectangular volume.
    geometry = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(-span / 2, 0, 0), new THREE.Vector3(span / 2, 0, 0)]);
  } else if (model.kind === "rod") geometry = new THREE.CylinderGeometry(0.18, 0.18, 2, 24);
  else if (model.kind === "film") geometry = new THREE.PlaneGeometry(2, 1);
  else if (model.kind === "solid") geometry = new THREE.BoxGeometry(1.5, 0.6, 1);
  else geometry = new THREE.OctahedronGeometry(0.45); // Explicitly unscaled unknown-sample marker.
  if (model.kind === "width") {
    material.dispose();
    scene.add(new THREE.Line(geometry, new THREE.LineBasicMaterial({ color: 0xddeeff })));
    for (const x of [-span / 2, span / 2]) {
      const tick = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(x, -span * 0.05, 0), new THREE.Vector3(x, span * 0.05, 0)]);
      scene.add(new THREE.Line(tick, new THREE.LineBasicMaterial({ color: 0xddeeff })));
    }
  } else scene.add(new THREE.Mesh(geometry, material));
  if (model.flow) {
    for (const z of [-0.35, 0, 0.35]) {
      scene.add(new THREE.ArrowHelper(new THREE.Vector3(model.flow.sign, 0, 0),
        new THREE.Vector3(-model.flow.sign * span * 0.6, span * 0.3, z * span), span * 1.2, 0x56b8ed, span * 0.12, span * 0.06));
    }
  }
  // Radius/arrow lengths fit the viewport, never encode speed or a prediction.
  return { radius: span * 2.4 };
}
