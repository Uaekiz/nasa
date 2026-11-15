import runScenarios from "./source-view-scenarios.mjs";
// First run: python -m app.multi_checks --reject-model-output (in rag-service).
// Then: node tests/source-view-browser.mjs (in frontend).
// Uses the existing frontend/backend and a separate, hidden Edge test browser.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, readFile, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const base = process.env.FRONTEND_URL || "http://localhost:5173";
const browserPath = process.env.CHROME_BIN || "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const profile = await mkdtemp(join(tmpdir(), "flex-ui-"));
const browser = spawn(browserPath, ["--headless=new", "--no-sandbox", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--disable-extensions", "--no-first-run", "--no-default-browser-check", "--remote-debugging-port=0", `--user-data-dir=${profile}`, "about:blank"], { windowsHide: true, stdio: "ignore" });
const delay = (ms) => new Promise((done) => setTimeout(done, ms));
let socket;
try {
  let port;
  for (let attempt = 0; attempt < 100; attempt++) {
    try { port = (await readFile(join(profile, "DevToolsActivePort"), "utf8")).split("\n")[0]; break; }
    catch { await delay(100); }
  }
  assert.ok(port, "Test browser did not start");
  const target = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: "PUT" })).json();
  socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((done, fail) => { socket.onopen = done; socket.onerror = fail; });
  let nextId = 0;
  const pending = new Map();
  const errors = [];
  const requests = [];
  let failPath = null;
  const responseOverrides = new Map();
  function cdp(method, params = {}) {
    const id = ++nextId;
    return new Promise((done, fail) => {
      const timeout = setTimeout(() => { pending.delete(id); fail(new Error(`CDP timeout: ${method}`)); }, 20000);
      pending.set(id, { done, fail, timeout });
      socket.send(JSON.stringify({ id, method, params }));
    });
  }
  socket.onmessage = async ({ data }) => {
    const event = JSON.parse(data);
    if (event.id) {
      const handler = pending.get(event.id);
      if (!handler) return;
      clearTimeout(handler.timeout);
      pending.delete(event.id);
      if (event.error) handler.fail(new Error(JSON.stringify(event.error)));
      else handler.done(event.result);
    }
    if (event.method === "Runtime.exceptionThrown") errors.push(event.params.exceptionDetails.text);
    if (event.method === "Network.requestWillBeSent") requests.push(event.params.request.url);
    if (event.method === "Fetch.requestPaused") {
      const { requestId, request } = event.params;
      if (responseOverrides.has(request.url)) {
        await cdp("Fetch.fulfillRequest", { requestId, responseCode: 200,
          responseHeaders: [{ name: "Content-Type", value: "application/json" }],
          body: Buffer.from(JSON.stringify(responseOverrides.get(request.url))).toString("base64") });
      } else if (failPath && request.url.includes(failPath)) {
        await cdp("Fetch.fulfillRequest", { requestId, responseCode: 503,
          responseHeaders: [{ name: "Content-Type", value: "application/json" }],
          body: Buffer.from(JSON.stringify({ requestId: "browser-failure-check", error: { code: "TEST_API_UNAVAILABLE", message: "Test API failure" } })).toString("base64") });
      } else await cdp("Fetch.continueRequest", { requestId });
    }
  };
  console.log("Browser connected:", (await cdp("Browser.getVersion")).product);
  await cdp("Runtime.enable");
  await cdp("Network.enable");
  await cdp("Page.enable");
  await cdp("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
  async function evaluate(expression) {
    let result;
    try { result = await cdp("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true }); }
    catch (error) { throw new Error(`Evaluation failed: ${expression.slice(0, 300)}`, { cause: error }); }
    assert.ok(!result.exceptionDetails, JSON.stringify(result.exceptionDetails));
    return result.result.value;
  }
  async function waitFor(expression) {
    for (let attempt = 0; attempt < 150; attempt++) {
      if (await evaluate(expression)) return;
      await delay(100);
    }
    throw new Error(`UI timeout: ${expression}\n${await evaluate("document.body.innerText.slice(-3500)")}`);
  }
  const clickText = (text) => evaluate(`[...document.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(text)})?.click()`);
  await runScenarios({ cdp, evaluate, waitFor, clickText, delay, base, responseOverrides, errors });
} finally {
  socket?.close();
  browser.kill(); // Only the hidden browser spawned by this check.
  await delay(500);
  const expectedPrefix = resolve(tmpdir(), "flex-ui-");
  assert.ok(resolve(profile).startsWith(expectedPrefix), "Temporary browser profile must stay inside the test temp directory");
  await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 300 });
}
