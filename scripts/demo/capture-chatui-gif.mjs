#!/usr/bin/env node
// capture-chatui-gif.mjs
//
// Captures a 12–15 s demo of the Pellier Boutique (Marco signed in) and
// encodes it into lab-content/builders/static/imgs/chatui.gif.
//
// Run from the repo root:
//   node scripts/demo/capture-chatui-gif.mjs
//
// Prereqs (one-time):
//   npm i -D playwright           # installs Playwright + bundled Chromium
//   # OR: brew install --cask google-chrome   (the script falls back to system Chrome)
//   brew install ffmpeg           # for the encode step
//
// Servers must be running:
//   npm --prefix pellier/frontend run dev          # → http://localhost:5173
//   cd pellier/backend && uvicorn app:app --reload --host 0.0.0.0 --port 8000
//
// Tweakable knobs at the top of main().

import { chromium } from 'playwright';
import { spawnSync } from 'node:child_process';
import { mkdirSync, rmSync, existsSync, statSync, readdirSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, '..', '..');
const FRAMES_DIR = resolve(REPO_ROOT, 'tmp', 'chatui-frames');
const OUT_GIF = resolve(REPO_ROOT, 'lab-content/builders/static/imgs/chatui.gif');
const SYSTEM_CHROME =
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

const URL_BASE = process.env.PELLIER_URL || 'http://localhost:5173';
const VIEWPORT = { width: 1440, height: 900 };
const FPS = 12; // capture + encode rate; 12 is a sweet spot for filesize

async function main() {
  // 1. fresh frames dir
  rmSync(FRAMES_DIR, { recursive: true, force: true });
  mkdirSync(FRAMES_DIR, { recursive: true });
  mkdirSync(dirname(OUT_GIF), { recursive: true });

  // 2. launch browser
  const launchOpts = { headless: true };
  if (existsSync(SYSTEM_CHROME)) {
    // Fallback: bundled Chromium may not be installed; system Chrome is fine.
    try {
      await chromium.launch({ headless: true }).then((b) => b.close());
    } catch {
      console.log('[demo] using system Chrome at', SYSTEM_CHROME);
      launchOpts.executablePath = SYSTEM_CHROME;
    }
  }
  const browser = await chromium.launch(launchOpts);
  const ctx = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 2, // crisp on retina; downscaled in encode
    reducedMotion: 'reduce', // calmer animations for cleaner frames
  });
  const page = await ctx.newPage();

  // Capture loop — start an interval that snapshots a PNG every 1/FPS s.
  // We run scripted UI steps in parallel so the recording is continuous.
  let frameIdx = 0;
  let snapping = true;
  const snap = async () => {
    while (snapping) {
      const idx = String(++frameIdx).padStart(5, '0');
      try {
        await page.screenshot({
          path: resolve(FRAMES_DIR, `f${idx}.png`),
          animations: 'allow',
        });
      } catch {
        // page may be navigating; skip frame
      }
      await sleep(1000 / FPS);
    }
  };

  // 3. navigate, sign in as Marco, run the script
  await page.goto(URL_BASE, { waitUntil: 'networkidle' });

  // start frame capture in background
  const capturePromise = snap();

  // hold on hero so the first 1–2 s show the storefront cleanly
  await sleep(1500);

  // sign in as Marco via the persona dropdown
  await selectPersona(page, 'marco');
  await page.waitForLoadState('networkidle');
  await sleep(1500);

  // gentle scroll down to show editorial sections
  await smoothScroll(page, 0, 1100, 1400);
  await sleep(800);

  // back to hero
  await smoothScroll(page, 1100, 0, 1200);
  await sleep(800);

  // click Marco's first hero pill (linen for 10 days in Goa)
  await clickFirstHeroPill(page);

  // wait for the chat drawer to mount (AnimatePresence + framer-motion);
  // accept either the testid or the class — both are stable in the codebase.
  await page
    .waitForSelector(
      '[data-testid="chat-drawer"], .cd-drawer',
      { timeout: 20000, state: 'visible' },
    )
    .catch(() => {
      console.warn(
        '[demo] drawer never appeared; continuing so the GIF still records something',
      );
    });
  await sleep(8000); // stream + product cards + trace chips

  // stop capture
  snapping = false;
  await capturePromise;
  await browser.close();

  // 4. encode to GIF with palette for clean colors
  encodeGif(FRAMES_DIR, OUT_GIF, FPS);

  // 5. verify metadata
  verify(OUT_GIF);
}

async function selectPersona(page, id) {
  // Open dropdown then click the option.
  const pill = page.locator('[data-testid="persona-pill"]');
  if (await pill.isVisible().catch(() => false)) {
    await pill.click();
    const opt = page.locator(`[data-testid="persona-option-${id}"]`);
    await opt.click({ timeout: 4000 }).catch(() => {});
  }
}

async function clickFirstHeroPill(page) {
  // Marco's first pill is the "linen for 10 days in Goa" turn. Most pills
  // don't have individual testids — match by visible text first, then fall
  // back to the first pill inside the rail.
  const byText = page
    .locator('[data-testid="boutique-hero-pills"] button', {
      hasText: /linen.*goa/i,
    })
    .first();
  if (await byText.isVisible().catch(() => false)) {
    await byText.scrollIntoViewIfNeeded().catch(() => {});
    await byText.click();
    return;
  }
  const fallback = page
    .locator('[data-testid="boutique-hero-pills"] button')
    .first();
  if (await fallback.isVisible().catch(() => false)) {
    await fallback.scrollIntoViewIfNeeded().catch(() => {});
    await fallback.click();
    return;
  }
  throw new Error('hero pill not found — frontend may have changed');
}

async function smoothScroll(page, from, to, durationMs) {
  await page.evaluate(
    async ([from, to, duration]) => {
      const start = performance.now();
      return new Promise((resolve) => {
        const tick = (now) => {
          const t = Math.min(1, (now - start) / duration);
          const eased = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
          window.scrollTo(0, from + (to - from) * eased);
          if (t < 1) requestAnimationFrame(tick);
          else resolve();
        };
        requestAnimationFrame(tick);
      });
    },
    [from, to, durationMs],
  );
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function encodeGif(framesDir, outPath, fps) {
  // Two-pass: build a global palette, then encode using it.
  const palette = resolve(framesDir, 'palette.png');
  const filter =
    `fps=${fps},scale=1280:-1:flags=lanczos`;
  run('ffmpeg', [
    '-y',
    '-framerate', String(fps),
    '-i', resolve(framesDir, 'f%05d.png'),
    '-vf', `${filter},palettegen=stats_mode=diff`,
    palette,
  ]);
  run('ffmpeg', [
    '-y',
    '-framerate', String(fps),
    '-i', resolve(framesDir, 'f%05d.png'),
    '-i', palette,
    '-lavfi', `${filter} [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=4`,
    outPath,
  ]);
}

function run(cmd, args) {
  const r = spawnSync(cmd, args, { stdio: 'inherit' });
  if (r.status !== 0) throw new Error(`${cmd} failed (${r.status})`);
}

function verify(path) {
  if (!existsSync(path)) throw new Error('no output gif at ' + path);
  const size = statSync(path).size;
  const probe = spawnSync(
    'ffprobe',
    [
      '-v', 'error',
      '-select_streams', 'v:0',
      '-show_entries', 'stream=width,height,nb_read_frames,r_frame_rate,duration',
      '-count_frames',
      '-of', 'default=nw=1',
      path,
    ],
    { encoding: 'utf8' },
  );
  console.log('--- chatui.gif ---');
  console.log('path:', path);
  console.log('size:', (size / 1024 / 1024).toFixed(2), 'MB');
  console.log(probe.stdout || probe.stderr);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
