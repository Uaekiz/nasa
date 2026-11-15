import { test } from "node:test";
import assert from "node:assert/strict";
import * as THREE from "three";
import { experimentDate } from "../src/services/experimentData.js";
import { experimentViewModel } from "../src/services/experimentViewModel.js";
import { createExperimentScene } from "../src/components/scenes/createExperimentScene.js";

const sourceId = "source";
const field = (name, value, unit, extra = {}) => ({ name, value, unit, rawValue: String(value), sourceId, qualityStatus: "VERIFIED", qualifier: "EXACT", ...extra });
const detail = (investigationId, conditions = [], reportedFindings = []) => ({ investigationId, conditions, reportedFindings, sources: [{ sourceId }] });

test("dates preserve full dates and partial SAME-R dates without generating a year", () => {
  assert.equal(experimentDate({ date: "2009-03-05", dateRaw: "3/5/2009" }), "2009-03-05");
  assert.equal(experimentDate({ date: null, dateRaw: "22-Jul" }), "22-Jul (yıl kaynakta yok)");
  assert.equal(experimentDate({ dateRaw: "21-Jul" }), "21-Jul (yıl kaynakta yok)");
  for (const dateRaw of [null, "", "  ", undefined]) assert.equal(experimentDate({ dateRaw }), "Kaynakta belirtilmemiş");
});

test("FLEX uses only its exact initial diameter and never extinction diameter or simulation values", () => {
  const experiment = detail("PSI-69", [field("Droplet initial diameter", 1.69, "mm")]);
  const model = experimentViewModel(experiment);
  assert.equal(model.diameter, 1.69);
  assert.equal(model.flow, null);
  const scene = new THREE.Scene();
  createExperimentScene(scene, model);
  const mesh = scene.children.find((object) => object.isMesh);
  assert.equal(mesh.geometry.parameters.radius, 1.69 / 2);
  assert.equal(scene.children.some((object) => object.isArrowHelper), false);
  for (const extra of [{ qualifier: "APPROXIMATE" }, { qualityStatus: "MISSING" }, { qualityStatus: "REQUIRES_REVIEW" }, { sourceId: "unlisted" }, { value: null }]) {
    const missing = experimentViewModel(detail("PSI-69", [field("Droplet initial diameter", 1.69, "mm", extra)]));
    assert.equal(missing.diameter, null);
    assert.match(missing.geometryNote, /ölçekli değildir/);
  }
});

test("SAFFIRE preserves dimension ratios and source direction, with no burning result", () => {
  const conditions = [field("Sample length", 940, "mm"), field("Sample width", 406, "mm"), field("Sample thickness", 3.3, "mm"), field("Air flow", 30, "cm/s")];
  for (const [direction, sign] of [["Concurrent", 1], ["Opposed", -1]]) {
    const model = experimentViewModel(detail("PSI-100", conditions, [field("Direction", direction)]));
    assert.deepEqual(model.dimensions, [940, 3.3, 406]);
    assert.equal(model.flow.sign, sign);
    assert.equal(model.flow.speed, 30);
    const scene = new THREE.Scene();
    createExperimentScene(scene, model);
    assert.equal(scene.children.filter((object) => object.type === "ArrowHelper").length, 3);
    assert.equal(scene.children.find((object) => object.isMesh).geometry.parameters.height, 3.3);
    assert.match(model.studyNote, /Yanma ölçümü/);
  }
});

test("BASS only draws labelled dimensions; display settings never become physical airflow", () => {
  const model = experimentViewModel(detail("PSI-25", [field("Fan display", 62, null, { qualityStatus: "REQUIRES_REVIEW" })],
    [field("Fuel Sample Material", "100 micron PMMA film 2 cm wide")]));
  assert.equal(model.kind, "width");
  assert.equal(model.width, 20);
  assert.equal(model.dimensions, null); // No invented length or unlabeled thickness.
  assert.equal(model.flow, null);
  const section = experimentViewModel(detail("PSI-25", [], [field("Fuel Sample Material", "2 cm wide 5 mm thick PMMA")]));
  assert.equal(section.kind, "cross-section");
  assert.deepEqual(section.dimensions, [20, 5]);
  for (const description of ['1/4" clear rod', "1/4 clear rod"]) {
    const rod = experimentViewModel(detail("PSI-25", [], [field("Fuel Sample Material", description)]));
    assert.equal(rod.kind, "rod");
    assert.equal(rod.diameter, null);
    assert.equal(rod.dimensions, null);
  }
  assert.equal(experimentViewModel(detail("PSI-25", [], [field("Fuel Sample Material", "PMMA film about 2 cm wide")])).width, null);
});

test("SAME-R and missing details cannot inherit another experiment's dimensions, flow or flame", () => {
  const model = experimentViewModel(detail("PSI-101", [field("Inlet velocity", 8.1, "cm/s")], [field("Sample Type", "Kapton")]));
  assert.equal(model.kind, "unknown");
  assert.equal(model.flow, null); // Speed alone does not establish direction.
  assert.equal(model.dimensions, null);
  assert.equal(model.parameters.find((p) => p.label === "Inlet velocity").value, 8.1);
  assert.match(model.studyNote, /açık alev deneyi olarak yorumlanmadı/);
  const empty = experimentViewModel(detail("PSI-101"));
  assert.deepEqual(empty.parameters, []);
  assert.equal(empty.diameter, null);
  const scene = new THREE.Scene();
  const state = createExperimentScene(scene, model);
  assert.equal(state.update, undefined); // Source view has no animation or predicted timeline.
  scene.traverse((object) => assert.equal(object.material?.isShaderMaterial, undefined));
});
