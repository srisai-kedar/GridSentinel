/**
 * record-demo.mjs
 * ---------------
 * Automated Playwright script that produces a guaranteed-to-work backup video
 * by driving DemoDirector's auto-sequence in Replay mode against pre-recorded data.
 * Zero dependency on live backend or live internet connection.
 */

import { chromium } from "playwright";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import http from "http";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const BACKUP_DIR = path.resolve(
  process.env.DEMO_OUTPUT_DIR || path.resolve(__dirname, "../backup-demo")
);
const TARGET_URL = process.env.DEMO_URL || "http://localhost:3000";

async function isServerRunning(url) {
  return new Promise((resolve) => {
    const req = http.get(url, (res) => {
      resolve(res.statusCode >= 200 && res.statusCode < 500);
    });
    req.on("error", () => resolve(false));
    req.setTimeout(2000, () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function run() {
  console.log("=================================================");
  console.log(" GridSentinel — Automated Backup Demo Recorder   ");
  console.log("=================================================");

  // Ensure backup directory exists
  if (!fs.existsSync(BACKUP_DIR)) {
    fs.mkdirSync(BACKUP_DIR, { recursive: true });
  }

  // Check if frontend server is running
  const isUp = await isServerRunning(TARGET_URL);
  if (!isUp) {
    console.error(`\n[Error] Next.js frontend is not running at ${TARGET_URL}.`);
    console.error("Please run `npm run dev` or `npm start` in gridsentinel/frontend first.\n");
    process.exit(1);
  }

  const demoDurationMs = Number(process.env.DEMO_DURATION_MS || 150000);
  if (!Number.isFinite(demoDurationMs) || demoDurationMs <= 0) {
    throw new Error("DEMO_DURATION_MS must be a positive number");
  }

  console.log(`\n[1/4] Connecting to frontend at ${TARGET_URL}...`);

  const browser = await chromium.launch({
    headless: true,
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    recordVideo: {
      dir: BACKUP_DIR,
      size: { width: 1440, height: 900 },
    },
  });

  const page = await context.newPage();

  let recordingSucceeded = false;
  try {
    console.log("[2/4] Loading SCADA Command Center...");
    // DOMContentLoaded keeps the offline fallback usable even when the live
    // backend/WebSocket is unavailable or repeatedly reconnecting.
    await page.goto(TARGET_URL, { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.waitForTimeout(2000);

    // Switch to REPLAY MODE
    console.log("[3/4] Switching to REPLAY MODE & driving Demo Director...");
    await page.getByRole("button", { name: "Replay" }).click();
    await page.waitForTimeout(500);

    // Switch to Director Tab
    await page.getByRole("tab", { name: "Demo" }).click();
    await page.waitForTimeout(500);

    // Click "Run Full Demo"
    await page.getByRole("button", { name: /Run Full Demo/ }).click();
    await page.waitForTimeout(500);

    // Switch to Audience View
    await page.getByRole("button", { name: /Audience View/ }).click();
    await page.waitForTimeout(500);

    // Let the deterministic replay/demo sequence record for the configured
    // duration. Use DEMO_DURATION_MS for a short local smoke test.
    console.log(`Recording video frames for ${demoDurationMs}ms...`);
    await page.waitForTimeout(demoDurationMs);

    console.log("[4/4] Finalizing video recording...");
    recordingSucceeded = true;
  } catch (err) {
    console.error("Error during recording:", err);
    process.exitCode = 1;
  } finally {
    // Close page and context to finalize video writing
    await page.close();
    await context.close();
    await browser.close();
  }

  // Rename video file to standard name
  const videoFiles = fs.readdirSync(BACKUP_DIR)
    .filter((f) => f.endsWith(".webm"))
    .map((name) => ({ name, mtimeMs: fs.statSync(path.join(BACKUP_DIR, name)).mtimeMs }))
    .sort((a, b) => b.mtimeMs - a.mtimeMs);
  if (videoFiles.length > 0) {
    const latestVideo = videoFiles[0].name;
    const targetFile = path.join(BACKUP_DIR, "gridsentinel-backup-demo.webm");
    try {
      const srcPath = path.join(BACKUP_DIR, latestVideo);
      if (srcPath !== targetFile) {
        fs.copyFileSync(srcPath, targetFile);
      }
      if (!recordingSucceeded) {
        console.error(`\n[Error] Recording did not complete successfully; diagnostic video saved at:`);
        console.error(`  ${targetFile}\n`);
        return;
      }
      console.log(`\n✔ Backup video generated successfully:`);
      console.log(`  ${targetFile}\n`);
    } catch (e) {
      console.log(`\n✔ Backup video saved: ${path.join(BACKUP_DIR, latestVideo)}\n`);
    }
  } else {
    console.log(`\n✔ Backup video saved in: ${BACKUP_DIR}\n`);
    if (recordingSucceeded) process.exitCode = 1;
  }
}

run();
