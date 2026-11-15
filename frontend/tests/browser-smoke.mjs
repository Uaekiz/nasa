// Optional live check: node tests/browser-smoke.mjs
// Uses the existing frontend/backend and a separate, hidden Edge test browser.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, readFile, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const base = process.env.FRONTEND_URL || "http://localhost:5173";
const browserPath = process.env.CHROME_BIN || "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const profile = await mkdtemp(join(tmpdir(), "flex-ui-"));
const browser = spawn(browserPath, ["--headless=new", "--no-sandbox", "--disable-gpu", "--disable-extensions", "--no-first-run", "--no-default-browser-check", "--remote-debugging-port=0", `--user-data-dir=${profile}`, "about:blank"], { windowsHide: true, stdio: "ignore" });
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
      if (failPath && request.url.includes(failPath)) {
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
    const result = await cdp("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
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
  await cdp("Page.navigate", { url: base });
  await waitFor("document.body.innerText.includes('NASA PSI Veri Tabanı')");
  await clickText("NASA PSI Veri Tabanı");
  await waitFor("document.querySelectorAll('tbody tr').length > 0");
  assert.equal(await evaluate("document.querySelectorAll('tbody input:checked').length"), 0);
  assert.ok(!requests.some((url) => /\/comparisons$|\/experiments\/PSI/.test(url)), "Initial page must not preselect comparisons or fetch details");
  for (const [inv, count] of [["PSI-25",129],["PSI-100",2],["PSI-101",109],["PSI-69",274]]) {
    await evaluate(`(() => {const select=document.querySelector('[aria-label="Araştırma filtresi"]'); select.value=${JSON.stringify(inv)}; select.dispatchEvent(new Event('change',{bubbles:true}));})()`);
    await waitFor(`document.body.innerText.includes(${JSON.stringify(`${count} kayıt`)})`);
    assert.ok(await evaluate(`document.querySelector('tbody tr .mono-cell').textContent.startsWith(${JSON.stringify(inv)})`));
  }
  await clickText("Detay");
  await waitFor("document.body.innerText.includes('Burning rate')");
  assert.ok(await evaluate("document.body.innerText.includes('Disruption')"), "FindingView must render value");
  assert.ok(await evaluate("document.body.innerText.includes('REQUIRES_REVIEW')"));
  await evaluate("document.querySelector('.detail-inspector-card .citation-card button').click()");
  await waitFor("!!document.querySelector('.detail-inspector-card a')");
  const sourceUrl = await evaluate("document.querySelector('.detail-inspector-card a').href");
  assert.equal((await fetch(sourceUrl)).status, 200);
  await evaluate("document.querySelectorAll('tbody input[type=checkbox]')[0].click(); document.querySelectorAll('tbody input[type=checkbox]')[1].click()");
  await waitFor("document.body.innerText.includes('Burn time (s)')");
  assert.ok(await evaluate("document.body.innerText.includes('DATA_EXCLUDED')"));
  const screenshot = await cdp("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  if (process.env.UI_SCREENSHOT) await writeFile(process.env.UI_SCREENSHOT, Buffer.from(screenshot.data, "base64"));
  await clickText("Sonraki");
  await waitFor("document.body.innerText.includes('Sayfa 2 / 14')");
  await evaluate("(() => { const input = document.querySelector('[aria-label=\"Yakıt filtresi\"]'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, 'not-a-source-fuel'); input.dispatchEvent(new Event('input', {bubbles:true})); })()");
  await clickText("Filtrele");
  await waitFor("document.body.innerText.includes('uygun backend deney kaydı yok')");
  console.log("UI: backend summaries, empty initial selection, lazy detail/FindingView, source download, real comparison metrics, pagination and empty filter passed");

  await cdp("Fetch.enable", { patterns: [{ urlPattern: "*/api/v1/*" }] });
  failPath = "/api/v1/experiments";
  await clickText("Temizle");
  await waitFor("document.body.innerText.includes('Test API failure')");
  failPath = "/api/v1/chat";
  await clickText("AI Bilimsel Asistan");
  await waitFor("document.body.innerText.includes('Henüz alınmış bir yanıt yok')");
  assert.equal(await evaluate("document.querySelectorAll('.chat-turn-card').length"), 0);
  await evaluate("(() => { const input = document.querySelector('[aria-label=\"Asistan sorusu\"]'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, 'Summarize FLEX test 70.'); input.dispatchEvent(new Event('input', {bubbles:true})); })()");
  await clickText("Sor / Yeniden dene");
  await waitFor("document.body.innerText.includes('Yanıt alınamadı')");
  assert.equal(await evaluate("document.querySelectorAll('.chat-turn-card').length"), 0, "Chat errors must not fabricate model answers");
  assert.equal(errors.length, 0, errors.join("\n"));
  console.log("UI: list/API error and chat failure displayed; no fabricated model text; zero uncaught browser exceptions");
} finally {
  socket?.close();
  browser.kill(); // Only the hidden browser spawned by this check.
  await delay(500);
  const expectedPrefix = resolve(tmpdir(), "flex-ui-");
  assert.ok(resolve(profile).startsWith(expectedPrefix), "Temporary browser profile must stay inside the test temp directory");
  await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 300 });
}
