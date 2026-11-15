import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const fixtureScript = fileURLToPath(new URL("./scenario-fixture.py", import.meta.url));
const python = fileURLToPath(new URL("../../rag-service/.venv/Scripts/python.exe", import.meta.url));
function scenarioFixture(payload) {
  return new Promise((resolve, reject) => {
    const child = spawn(python, [fixtureScript], { windowsHide: true, stdio: ["pipe", "pipe", "pipe"] });
    let stdout = "", stderr = "";
    child.stdout.on("data", (data) => { stdout += data; });
    child.stderr.on("data", (data) => { stderr += data; });
    child.on("error", reject);
    child.on("close", (code) => { if (code) reject(new Error(stderr)); else { try { resolve(JSON.parse(stdout)); } catch { reject(new Error(stdout + stderr)); } } });
    child.stdin.end(JSON.stringify(payload));
  });
}

export default async function scenarios({ cdp, evaluate, waitFor, clickText, delay, base, responseOverrides, errors }) {
  let mode = "normal", delayed = [], requests = [];
  let apiFixtures = {};
  try { apiFixtures = JSON.parse(await readFile(new URL("../../backend/target/flamescope-browser-api.json", import.meta.url), "utf8")); }
  catch { throw new Error("Run backend BrowserApiFixtureTests first to export the real-DB browser responses."); }
  for (const fixture of apiFixtures.responses || []) responseOverrides.set(base + fixture.path, fixture.body);
  const chatFixtures = JSON.parse(await readFile(new URL("../../backend/target/flamescope-chat-browser.json", import.meta.url), "utf8"));
  responseOverrides.set(base + "/api/v1/chat/capabilities", chatFixtures.capabilities);
  responseOverrides.set(base + "/api/v1/chat", chatFixtures.answer);
  responseOverrides.set(base + "/api/v1/health", { status: 503, payload: { error: { code: "UI_TEST_BACKEND_OFFLINE", message: "Isolated UI test; backend health is unavailable." } } });
  responseOverrides.set(base + "/api/v1/scenario-analyses", async (request) => {
    const payload = JSON.parse(request.postData);
    requests.push(payload);
    assert.equal(Object.hasOwn(payload, "imageDataUrl"), false);
    assert.deepEqual(Object.keys(payload).sort(), ["capturedAt", "params"]);
    if (mode === "error") return { status: 503, payload: { requestId: "test-error", error: { code: "RAG_UNAVAILABLE", message: "The RAG service is unavailable. You can retry." } } };
    if (mode === "timeout") return { status: 504, payload: { requestId: "test-timeout", error: { code: "RAG_TIMEOUT", message: "The RAG service timed out." } } };
    const fixture = await scenarioFixture(payload);
    if (mode === "delay") return new Promise((resolve) => delayed.push({ resolve, fixture }));
    return fixture;
  });
  await cdp("Fetch.enable", { patterns: [{ urlPattern: "*/api/v1/*" }] });
  await cdp("Page.addScriptToEvaluateOnNewDocument", { source: `
    const get=HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext=function(type,...args){if(window.__noWebGL && /webgl/.test(type))return null;return get.call(this,type,...args)};
  ` });
  await cdp("Page.navigate", { url: base });
  await waitFor("!!document.querySelector('.sim-card canvas')");
  assert.equal(await evaluate("document.documentElement.lang"), "en");
  assert.equal((await fetch(base + "/flamescope-mark.svg")).status, 200);
  assert.ok(await evaluate("document.querySelector('.flamescope-logo').src.endsWith('/flamescope-mark.svg')"));
  assert.ok(await evaluate("document.body.innerText.includes('Backend API unavailable')"));
  assert.ok(!await evaluate("document.body.innerText.includes('NASA // PSI') || !!document.querySelector('.palette-spec-strip')"));
  assert.ok(!await evaluate("[...document.querySelectorAll('button')].some(b=>/apply.*(?:demo|changes)|undo/i.test(b.textContent))"));
  const select = (selector, value) => evaluate(`(()=>{const s=document.querySelector(${JSON.stringify(selector)});s.value=${JSON.stringify(value)};s.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  await select("#select-material", "PMMA Film");
  await delay(100);
  await clickText("Capture scenario and image");
  await waitFor("!!document.querySelector('.scenario-preview img')");
  assert.ok(await evaluate("document.querySelector('.scenario-preview img').src.startsWith('data:image/png;base64,')"));
  assert.equal(await evaluate("document.querySelectorAll('.scenario-inputs tbody tr').length"), 12);
  assert.ok(await evaluate("document.querySelector('.scenario-preview').innerText.includes('not sent to RAG')"));
  await clickText("Analyze captured scenario");
  await waitFor("document.querySelector('.scenario-assessment')?.innerText.includes('deterministic')");
  assert.equal(await evaluate("document.querySelectorAll('[aria-label=\"Scenario assessment\"]').length"), 1);
  assert.ok(await evaluate("document.querySelector('.scenario-assessment').innerText.includes('could not be used')"));
  assert.ok(await evaluate("document.querySelector('.scenario-coverage').innerText.includes('Measurement phase not specified')"));
  assert.ok(await evaluate("document.querySelectorAll('.scenario-alternates .scenario-source').length>0"));
  await evaluate("document.querySelector('.scenario-assessment').scrollIntoView({block:'start'})");
  const assessmentShot = await cdp("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  await writeFile(new URL("../../backend/target/flamescope-assessment-desktop.png", import.meta.url), Buffer.from(assessmentShot.data, "base64"));
  const citation = await evaluate("document.querySelector('.scenario-citation-link').textContent");
  await evaluate("document.querySelector('.scenario-citation-link').click()");
  assert.ok(await evaluate(`document.querySelector('.scenario-source[open]')?.querySelector('summary').textContent.includes(${JSON.stringify(citation)})`));
  assert.ok(await evaluate("document.querySelectorAll('.scenario-source-differences').length>0"));
  // Any changed capture input or phase makes the pending/result scenario stale.
  await select('[aria-label="CO measurement phase"]', "INITIAL");
  await waitFor("document.querySelector('.scenario-analysis-panel').innerText.includes('Inputs changed')");
  assert.ok(await evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent==='Analyze captured scenario').disabled"));
  await clickText("Capture the current scenario again");
  await waitFor("!document.querySelector('.scenario-assessment') && !!document.querySelector('.scenario-preview img')");
  mode = "delay";
  await clickText("Analyze captured scenario");
  for (let i=0;i<100 && delayed.length===0;i++) await delay(100);
  assert.equal(delayed.length, 1);
  await clickText("Capture the current scenario again");
  await waitFor("!document.body.innerText.includes('Reviewing captured inputs…')");
  mode = "normal";
  await clickText("Analyze captured scenario");
  await waitFor("!!document.querySelector('.scenario-assessment')");
  for (const old of delayed.splice(0)) old.resolve({ ...old.fixture, payload: { ...old.fixture.payload, requestId: "STALE-RESPONSE-MUST-NOT-APPEAR" } });
  await delay(200);
  assert.ok(!await evaluate("document.body.innerText.includes('STALE-RESPONSE-MUST-NOT-APPEAR')"));
  // API errors and timeout stay visible; retry does not lose the capture.
  mode = "error"; await clickText("Analyze captured scenario");
  await waitFor("document.querySelector('.scenario-analysis-panel [role=alert]')?.innerText.includes('unavailable')");
  assert.ok(await evaluate("!!document.querySelector('.scenario-preview img')"));
  mode = "timeout"; await clickText("Analyze captured scenario");
  await waitFor("document.querySelector('.scenario-analysis-panel [role=alert]')?.innerText.includes('timed out')");
  mode = "normal"; await clickText("Analyze captured scenario");
  await waitFor("!!document.querySelector('.scenario-assessment')");
  // A late request cannot update the component after navigation/unmount.
  mode = "delay"; await clickText("Analyze captured scenario");
  for (let i=0;i<100 && delayed.length===0;i++) await delay(100);
  await clickText("NASA PSI Catalog");
  for (const old of delayed.splice(0)) old.resolve(old.fixture);
  await delay(200);
  await waitFor("document.querySelectorAll('.nasa-table tbody tr').length>0");
  assert.equal(await evaluate("document.querySelectorAll('tbody input:checked').length"), 0);
  for (const [investigation, count] of [["PSI-100",2],["PSI-25",129],["PSI-101",109],["PSI-69",274]]) {
    await select('[aria-label="Investigation filter"]', investigation);
    await waitFor(`document.body.innerText.includes('${count} records')`);
    assert.ok(await evaluate(`document.querySelector('tbody .mono-cell').textContent.startsWith('${investigation}:')`));
    if (investigation === "PSI-101") {
      await evaluate("document.querySelectorAll('tbody tr')[1].querySelector('button').click()");
      await waitFor("document.querySelector('.detail-inspector-card').innerText.includes('22-Jul (year not provided in source)')");
    }
  }
  await clickText("Details");
  await waitFor("document.querySelector('.detail-inspector-card').innerText.includes('Disruption')");
  await evaluate("document.querySelector('.detail-inspector-card .citation-card button').click()");
  await waitFor("!!document.querySelector('.detail-inspector-card .citation-card a')");
  assert.ok(await evaluate("document.querySelector('.detail-inspector-card .citation-card a').href.includes('/files/')"));
  await evaluate("document.querySelectorAll('tbody input[type=checkbox]')[0].click();document.querySelectorAll('tbody input[type=checkbox]')[1].click()");
  await waitFor("document.body.innerText.includes('Burn time (s)')");
  await clickText("Next");
  await waitFor("document.body.innerText.includes('Page 2 / 14')");
  await clickText("Source assistant");
  await waitFor("document.querySelectorAll('[aria-label=\"Investigation scope\"] option').length===5");
  await evaluate("(()=>{const i=document.querySelector('[aria-label=\"Assistant question\"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(i,'Summarize FLEX test 70.');i.dispatchEvent(new Event('input',{bubbles:true}));})()");
  await clickText("Ask / Retry");
  await waitFor("document.querySelector('.answer-text')?.innerText.includes('reported burn time was 1.6 s. [S1]')");
  assert.ok(await evaluate("document.querySelector('.answer-status-strip').innerText.includes('Model output rejected')"));
  await clickText("Scenario workspace");
  await waitFor("!!document.querySelector('.sim-card canvas')");
  assert.equal(await evaluate("document.querySelectorAll('.scenario-assessment').length"), 0);
  assert.equal(await evaluate("document.querySelectorAll('.scenario-preview img').length"), 0);
  // Viewport and controls remain within a narrow screen.
  await cdp("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await evaluate("document.querySelector('.scenario-analysis-panel').scrollIntoView({block:'start'})");
  await delay(200);
  assert.ok(await evaluate("document.documentElement.scrollWidth<=390"), "No mobile page overflow");
  const screen = await cdp("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  await writeFile(new URL("../../backend/target/flamescope-scenario-mobile.png", import.meta.url), Buffer.from(screen.data, "base64"));
  // WebGL-unavailable capture is an explicit error, not a blank successful image.
  await clickText("NASA PSI Catalog"); await delay(100);
  await evaluate("window.__noWebGL=true");
  await clickText("Scenario workspace");
  await waitFor("!!document.querySelector('.webgl-fallback')");
  await clickText("Capture scenario and image");
  await waitFor("!!document.querySelector('.scenario-analysis-panel [role=alert]')");
  assert.equal(await evaluate("document.querySelectorAll('.scenario-preview img').length"), 0);
  assert.equal(errors.length, 0, errors.join("\n"));
  assert.ok(requests.length >= 6);
  console.log("PASS: English branding, source-backed scenario capture, all inputs, local-only PNG, single deterministic fallback assessment, gas phase staleness, separate versions/differences, citation navigation, recapture/late response/unmount, API error/timeout, mobile and WebGL failure.");
  console.log("UI uses real reviewed corpus + in-process ASGI with deliberately rejected ordering model; no live model success is claimed.");
  console.log("PASS: actual MockMvc/DB catalogue fixtures, investigation filters, partial SAME-R date, FLEX detail/source endpoint, comparison and paging; real READY scope/source-chat fallback fixture.");
}
