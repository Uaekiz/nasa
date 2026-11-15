// Optional browser integration scenarios using existing services; no server starts.
import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";

export default async function runScenarios({ cdp, evaluate, waitFor, clickText, delay, base, responseOverrides, errors }) {
  await cdp("Page.addScriptToEvaluateOnNewDocument", { source: `
    window.__raf = new Set(); window.__contextsLost = 0;
    const raf=window.requestAnimationFrame.bind(window), cancel=window.cancelAnimationFrame.bind(window);
    window.requestAnimationFrame=(callback)=>{const id=raf(time=>{window.__raf.delete(id);callback(time)});window.__raf.add(id);return id};
    window.cancelAnimationFrame=(id)=>{window.__raf.delete(id);cancel(id)};
    const context=HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext=function(type,...args){
      if (/webgl/.test(type)) {
        if(window.__disableWebGL) return null;
        if(!this.__tracked){this.addEventListener('webglcontextlost',()=>window.__contextsLost++);this.__tracked=true;}
      }
      return context.call(this,type,...args);
    };
  ` });
  await cdp("Page.navigate", { url: base });
  await waitFor("document.querySelector('.sim-card canvas')");
  await delay(300);
  assert.ok(await evaluate("window.__raf.size > 0"), "Main simulation still animates");
  await clickText("⏸ Pause");
  assert.ok(await evaluate("document.body.innerText.includes('▶ Play')"));
  await clickText("▶ Play");
  await clickText("NASA PSI Catalog");
  await waitFor("document.querySelectorAll('tbody tr').length > 0");
  await delay(200);
  assert.equal(await evaluate("window.__raf.size"), 0, "Main simulation RAF is cleaned on unmount");
  const filter = async (inv, count) => {
    await evaluate(`(()=>{const s=document.querySelector('[aria-label="Investigation filter"]');s.value=${JSON.stringify(inv)};s.dispatchEvent(new Event('change',{bubbles:true}));})()`);
    await waitFor(`document.body.innerText.includes('${count} records')`);
  };
  const open = async (index=0) => {
    await evaluate(`document.querySelectorAll('tbody tr')[${index}].querySelector('button').click()`);
    await waitFor("document.querySelector('.experiment-source-view canvas')");
  };
  const assertView = async (kind, flow) => {
    await waitFor(`document.querySelector('.experiment-source-view')?.dataset.sampleKind === ${JSON.stringify(kind)}`);
    assert.equal(await evaluate("document.querySelector('.experiment-source-view').dataset.sampleKind"), kind);
    assert.equal(await evaluate("document.querySelector('.experiment-source-view').dataset.flowArrows"), String(flow));
    await delay(200);
    assert.equal(await evaluate("window.__raf.size"), 0, "Static source view has no animation loop");
    assert.equal(await evaluate("document.querySelectorAll('.experiment-source-view canvas').length"), 1);
  };
  await filter("PSI-100",2); await open(); await assertView("box",true);
  assert.ok(await evaluate("document.querySelector('.experiment-source-view').innerText.includes('30 cm/s')"));
  assert.ok(await evaluate("document.querySelector('.detail-inspector-card').innerText.includes('Not reported in source')"));
  await evaluate("document.querySelector('.experiment-source-view canvas').scrollIntoView({block:'center'})");
  const image = async () => {
    // Capture the fixed viewport first: captureBeyondViewport with a clip can
    // resize Chromium's layout viewport and change the responsive panel width.
    const rect = await evaluate("(()=>{const r=document.querySelector('.experiment-source-view canvas').getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}})()");
    const shot = await cdp("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
    return evaluate(`(async()=>{const img=new Image();img.src='data:image/png;base64,${shot.data}';await img.decode();const r=${JSON.stringify(rect)},c=document.createElement('canvas');c.width=r.width;c.height=r.height;c.getContext('2d').drawImage(img,r.x,r.y,r.width,r.height,0,0,c.width,c.height);return c.toDataURL().split(',')[1]})()`);
  };
  const pixelDistance = (left, right) => evaluate(`(async()=>{
    const pixels=async(data)=>{const img=new Image();img.src='data:image/png;base64,'+data;await img.decode();const c=document.createElement('canvas');c.width=64;c.height=40;const ctx=c.getContext('2d');ctx.drawImage(img,0,0,64,40);return ctx.getImageData(0,0,64,40).data};
    const a=await pixels(${JSON.stringify(left)}),b=await pixels(${JSON.stringify(right)});
    return a.reduce((sum,value,i)=>sum+Math.abs(value-b[i]),0)/a.length;
  })()`);
  const iso = await image();
  await evaluate("document.querySelector('.experiment-source-view [aria-label=Zoom in]').click()");
  await delay(200);
  assert.ok(await pixelDistance(await image(), iso) > 0.2, "Zoom changes rendered projection");
  await evaluate("[...document.querySelectorAll('.experiment-source-view button')].find(b=>b.textContent==='Reset view').click()");
  await delay(200);
  const resetImage = await image();
  if (process.env.UI_SCREENSHOT) {
    await writeFile(process.env.UI_SCREENSHOT.replace('.png','-iso.png'), Buffer.from(iso, 'base64'));
    await writeFile(process.env.UI_SCREENSHOT.replace('.png','-reset.png'), Buffer.from(resetImage, 'base64'));
  }
  const resetDistance = await pixelDistance(resetImage, iso);
  console.log('Reset camera raster distance:', resetDistance);
  assert.ok(resetDistance < 0.5, "Reset restores camera within subpixel rasterization tolerance");
  await evaluate("document.querySelector('.experiment-source-view canvas').scrollIntoView({block:'center'})");
  const rect = await evaluate("(()=>{const r=document.querySelector('.experiment-source-view canvas').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()");
  await cdp("Input.dispatchMouseEvent",{type:"mousePressed",button:"left",clickCount:1,x:rect.x,y:rect.y});
  await cdp("Input.dispatchMouseEvent",{type:"mouseMoved",button:"left",buttons:1,x:rect.x+60,y:rect.y+20});
  await cdp("Input.dispatchMouseEvent",{type:"mouseReleased",button:"left",clickCount:1,x:rect.x+60,y:rect.y+20});
  await delay(200); assert.ok(await pixelDistance(await image(),iso) > 0.2,"Drag rotates scene");
  // Until backend restart, test the additive summary contract using dates
  // fetched from real detail DTOs. No production fallback or invented date.
  const sameUrl = base + "/api/v1/experiments?page=0&size=20&investigationId=PSI-101";
  const summary = await (await fetch(sameUrl)).json();
  for (const row of summary.items) {
    const actual = await (await fetch(base+"/api/v1/experiments/"+encodeURIComponent(row.experimentId))).json();
    row.dateRaw = actual.dateRaw;
  }
  responseOverrides.set(sameUrl,summary);
  await cdp("Fetch.enable",{patterns:[{urlPattern:"*/api/v1/*"}]});
  const lost = await evaluate("window.__contextsLost");
  await filter("PSI-101",109); await open(1); await assertView("unknown",false);
  assert.ok(await evaluate("document.querySelector('tbody tr:nth-child(2)').innerText.includes('22-Jul (year not provided in source)')"));
  assert.ok(await evaluate("document.querySelector('.detail-inspector-card').innerText.includes('22-Jul (year not provided in source)')"));
  assert.ok(!await evaluate("document.querySelector('.experiment-source-view').innerText.includes('30 cm/s')"),"Previous experiment speed cleared");
  assert.ok(await evaluate("window.__contextsLost") > lost,"Previous GPU context released");
  await filter("PSI-69",274); await open(); await assertView("droplet",false);
  assert.ok(await evaluate("document.querySelector('.experiment-source-view').innerText.includes('1.69 mm')"));
  assert.ok(await evaluate("document.querySelector('.detail-inspector-card').innerText.includes('2009-03-05')"));
  // Exercise a real FLEX record with missing diameter.
  let missingDetail;
  for (let page=0;page<14 && !missingDetail;page++) {
    const p=await(await fetch(base+`/api/v1/experiments?investigationId=PSI-69&page=${page}&size=20`)).json();
    for(const row of p.items) {
      const d=await(await fetch(base+"/api/v1/experiments/"+encodeURIComponent(row.experimentId))).json();
      if(d.conditions.some(c=>c.name==="Droplet initial diameter" && c.qualityStatus==="MISSING")) {missingDetail=d;break;}
    }
  }
  assert.ok(missingDetail);
  const currentId=await evaluate("document.querySelector('tbody tr .mono-cell').textContent");
  responseOverrides.set(base+"/api/v1/experiments/"+encodeURIComponent(currentId),missingDetail);
  await filter("PSI-100",2); await filter("PSI-69",274); await open();
  await waitFor("document.querySelector('.experiment-source-view')?.innerText.includes('The droplet symbol is not to scale')");
  assert.ok(await evaluate("document.querySelector('.experiment-source-view').innerText.includes('The droplet symbol is not to scale')"));
  responseOverrides.delete(base+"/api/v1/experiments/"+encodeURIComponent(currentId));
  await filter("PSI-25",129); await open(); await assertView("width",false);
  assert.ok(await evaluate("document.querySelector('.experiment-source-view').innerText.includes('100 micron PMMA film')"));
  const bassRows=[];
  for(let page=0;page<2;page++) bassRows.push(...(await(await fetch(base+`/api/v1/experiments?investigationId=PSI-25&size=100&page=${page}`)).json()).items);
  const rod=bassRows.find(r=>/\brod\b/i.test(r.fuel));
  assert.ok(rod);
  const rodDetail=await(await fetch(base+"/api/v1/experiments/"+encodeURIComponent(rod.experimentId))).json();
  const bassId=await evaluate("document.querySelector('tbody tr .mono-cell').textContent");
  responseOverrides.set(base+"/api/v1/experiments/"+encodeURIComponent(bassId),rodDetail);
  await filter("PSI-100",2); await filter("PSI-25",129); await open(); await assertView("rod",false);
  responseOverrides.delete(base+"/api/v1/experiments/"+encodeURIComponent(bassId));
  await cdp("Emulation.setDeviceMetricsOverride",{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await delay(300);
  assert.ok(await evaluate("(()=>{const v=document.querySelector('.experiment-source-view'),c=v.querySelector('canvas');return c.clientWidth<=v.clientWidth && v.clientWidth<=390})()"));
  const shot=await cdp("Page.captureScreenshot",{format:"png",captureBeyondViewport:true});
  if(process.env.UI_SCREENSHOT) await writeFile(process.env.UI_SCREENSHOT,Buffer.from(shot.data,"base64"));
  await evaluate("window.__disableWebGL=true");
  await filter("PSI-100",2);
  await clickText("Details");
  await waitFor("!!document.querySelector('.webgl-fallback')");
  assert.ok(await evaluate("document.querySelector('.webgl-fallback').innerText.includes('WebGL')"));
  assert.ok(await evaluate("document.querySelector('.experiment-source-view').innerText.includes('940 mm')"));
  assert.equal(await evaluate("document.querySelectorAll('.experiment-source-view canvas').length"),0);
  await evaluate("window.__disableWebGL=false");
  await clickText("Scenario workspace");
  await waitFor("document.querySelector('.sim-card canvas')");
  assert.ok(await evaluate("document.body.innerText.includes('Illustrative specimen and flame model')"));
  assert.ok(await evaluate("window.__raf.size>0"));
  // Use an actual ASGI response produced by the explicit rejected-generation
  // check. This fixture tests honest metadata rendering, not live generation.
  const fallbackReport = JSON.parse(await readFile(new URL("../../rag-service/.local/nasa-provenance/source-fallback-checks.json", import.meta.url), "utf8"));
  responseOverrides.set(base+"/api/v1/chat", fallbackReport.cases[0].response);
  await clickText("Source assistant");
  await waitFor("!!document.querySelector('[aria-label=\"Assistant question\"]')");
  await evaluate("(()=>{const input=document.querySelector('[aria-label=\"Assistant question\"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'Summarize FLEX test 70.');input.dispatchEvent(new Event('input',{bubbles:true}));})()");
  await clickText("Ask / Retry");
  await waitFor("document.body.innerText.includes('Model output rejected')");
  assert.ok(await evaluate("document.querySelector('.answer-text').innerText.includes('reported burn time was 1.6 s. [S1]')"));
  assert.ok(!await evaluate("document.querySelector('.answer-status-strip').innerText.includes('Not called')"));
  assert.equal(errors.length,0,errors.join("\n"));
  console.log("PASS: main simulation/pause, dimensions/flow, SAME-R partial dates, FLEX full dates/missing diameter, BASS width/rod, source switching, rotate/zoom/reset, responsive canvas, WebGL fallback, RAF/context cleanup.");
  console.log("dateRaw summaries were test-only fixtures from actual detail responses; production summary DTO requires backend restart.");
  console.log("PASS: rejected-generation ASGI fixture is labelled as source fallback, never as successful model prose or as an unattempted call.");
}
