#!/usr/bin/env node
// Resolver: Puppeteer-core drives the Lightpanda engine over CDP, returns
// one page's rendered HTML. Subprocess bridge for scripts/browser_resolver.py.
// Ported from the sibling G2AI_ME repo's pipeline/browser/resolve.mjs.
//
// Usage: node resolve.mjs <url> [waitMs] [frameUrlContains]
// Stdout — ONE line of JSON: {"ok":true,"html":"...","url":"..."} | {"ok":false,"error":"..."}
//
// If frameUrlContains is given, returns the content of the first child
// frame whose URL contains that substring instead of the top-level
// document (added for iCIMS, which only populates a nested iframe — not
// present in the original G2AI_ME script, whose targets never needed it).
//
// Self-contained: starts its own `lightpanda serve` on a free port and
// kills it on exit — the caller (Python) doesn't manage the engine's
// lifecycle. Required page-creation pattern — createBrowserContext()->
// newPage() (NOT browser.pages()[0]/a phantom browser target, or
// navigation hangs — see G2AI_ME's headless-browser-resolver spec §4).
import { spawn } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import net from 'node:net';
import puppeteer from 'puppeteer-core';

const __dirname = dirname(fileURLToPath(import.meta.url));
const LIGHTPANDA_BIN = join(__dirname, 'lightpanda');

function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.listen(0, '127.0.0.1', () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
    srv.on('error', reject);
  });
}

function waitForCdp(port, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    (function tick() {
      fetch(`http://127.0.0.1:${port}/json/version`).then(() => resolve()).catch(() => {
        if (Date.now() > deadline) reject(new Error('lightpanda serve did not come up in time'));
        else setTimeout(tick, 150);
      });
    })();
  });
}

async function main() {
  const url = process.argv[2];
  const waitMs = parseInt(process.argv[3] || '9000', 10);
  const frameUrlContains = process.argv[4] || null;
  if (!url) {
    console.log(JSON.stringify({ ok: false, error: 'no URL given' }));
    return;
  }

  const port = await freePort();
  const lp = spawn(LIGHTPANDA_BIN, ['serve', '--host', '127.0.0.1', '--port', String(port)], { stdio: 'ignore' });
  try {
    await waitForCdp(port, 8000);
    const browser = await puppeteer.connect({
      browserWSEndpoint: `ws://127.0.0.1:${port}/`,
      protocolTimeout: waitMs + 10000,
    });
    try {
      const ctx = await browser.createBrowserContext();
      const page = await ctx.newPage();
      // goto may legitimately not settle a lifecycle event on a heavy SPA —
      // not a failure: content is still read below after the explicit wait.
      await page.goto(url, { timeout: waitMs + 5000 }).catch(() => {});
      await new Promise((r) => setTimeout(r, waitMs));

      let target = page;
      if (frameUrlContains) {
        const match = page.frames().find((f) => f.url().includes(frameUrlContains));
        if (match) target = match;
      }
      const html = await target.content();
      const finalUrl = page.url();
      console.log(JSON.stringify({ ok: true, html, url: finalUrl }));
    } finally {
      await browser.disconnect();
    }
  } catch (e) {
    console.log(JSON.stringify({ ok: false, error: String((e && e.message) || e).slice(0, 300) }));
  } finally {
    lp.kill();
  }
}

main();
