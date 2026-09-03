import { spawn } from "node:child_process";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";

const chrome = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const root = path.resolve(import.meta.dirname, "..");
const outDir = path.join(root, "docs", "release_evidence", "2026-09-03", "browser-acceptance");
const profile = path.join(root, "backend", "data", "chrome-acceptance-profile");
const port = 9333;
await mkdir(outDir, { recursive: true });
await rm(profile, { recursive: true, force: true });
await mkdir(profile, { recursive: true });

const child = spawn(chrome, [
  "--headless=new", `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
  "--profile-directory=Default", "--no-first-run", "--no-default-browser-check", "about:blank",
], { stdio: "ignore" });

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
for (let i = 0; i < 100; i += 1) {
  try { if ((await fetch(`http://127.0.0.1:${port}/json/version`)).ok) break; } catch {}
  if (i === 99) throw new Error("Chrome DevTools did not start");
  await sleep(100);
}

const target = await (await fetch(`http://127.0.0.1:${port}/json/new?http://127.0.0.1:5173`, { method: "PUT" })).json();
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
let id = 0;
const pending = new Map();
const consoleErrors = [];
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  if (msg.id && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id); pending.delete(msg.id);
    msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
  }
  if (msg.method === "Runtime.exceptionThrown") consoleErrors.push(msg.params.exceptionDetails.text);
  if (msg.method === "Log.entryAdded" && msg.params.entry.level === "error") consoleErrors.push(msg.params.entry.text);
};
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const callId = ++id; pending.set(callId, { resolve, reject });
  ws.send(JSON.stringify({ id: callId, method, params }));
});
const evaluate = async (expression) => (await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true })).result.value;
const navigate = async (url) => { await send("Page.navigate", { url }); await sleep(2500); };
await send("Page.enable"); await send("Runtime.enable"); await send("Log.enable");

const viewports = [{ name: "desktop", width: 1440, height: 900 }, { name: "tablet", width: 768, height: 1024 }, { name: "mobile", width: 390, height: 844 }];
const pages = ["storyboard", "generate", "review", "timeline"];
const results = [];
for (const viewport of viewports) {
  await send("Emulation.setDeviceMetricsOverride", { width: viewport.width, height: viewport.height, deviceScaleFactor: 1, mobile: viewport.width < 600 });
  for (const theme of ["light", "dark"]) {
    await navigate("http://127.0.0.1:5173/generate");
    await evaluate(`localStorage.setItem('cas.theme','${theme}'); location.reload()`);
    await sleep(2500);
    for (const page of pages) {
      await navigate(`http://127.0.0.1:5173/${page}`);
      const metrics = await evaluate(`(() => ({
        title: document.title,
        text: document.body.innerText.slice(0, 12000),
        theme: document.documentElement.className,
        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        stageNav: !!document.querySelector('[aria-label="Production stages"]'),
        projectSwitch: !!document.querySelector('[aria-label="Switch project"]'),
        brokenImages: [...document.images].filter(i => i.complete && i.naturalWidth === 0).length
      }))()`);
      const expected = { storyboard: "Storyboard", generate: "Generate", review: "Review", timeline: "Timeline" }[page];
      const ok = metrics.text.includes(expected) && metrics.theme.includes(`theme-${theme}`) && metrics.overflow <= 1 && metrics.stageNav && metrics.projectSwitch && metrics.brokenImages === 0;
      const shot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
      await writeFile(path.join(outDir, `${viewport.name}-${theme}-${page}.png`), Buffer.from(shot.data, "base64"));
      results.push({ viewport: viewport.name, theme, page, ok, ...metrics, text: undefined });
    }
  }
}

// Exercise the run filters and verify their accessible labels are present.
await navigate("http://127.0.0.1:5173/generate");
for (let i = 0; i < 20; i += 1) {
  const ready = await evaluate(`document.body.innerText.includes('Run 2 (imported)')`);
  if (ready) break;
  await sleep(500);
}
const generateChecks = await evaluate(`(() => {
  const text = document.body.innerText;
  return {
    tabs: ['Current', 'Failed', 'Completed', 'History'].every(x => text.includes(x)),
    namedShots: text.includes('A Friendly Challenge') && text.includes('Shot 2 -'),
    runCounts: text.includes('11 completed') && text.includes('0 queued'),
    reviewAction: text.includes('Go to Review'),
    noPageError: !text.includes('Something went wrong'),
    excerpt: text.slice(0, 3000)
  };
})()`);
const report = { chrome, profileDirectoryArgument: "--profile-directory=Default", results, generateChecks, consoleErrors };
await writeFile(path.join(outDir, "report.json"), JSON.stringify(report, null, 2));
ws.close(); child.kill();
if (results.some((item) => !item.ok) || consoleErrors.length || Object.values(generateChecks).some((value) => !value)) {
  console.error(JSON.stringify(report, null, 2)); process.exit(1);
}
console.log(JSON.stringify({ checks: results.length, generateChecks, consoleErrors: consoleErrors.length, evidence: outDir }, null, 2));
