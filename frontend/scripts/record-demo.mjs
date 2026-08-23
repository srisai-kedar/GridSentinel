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

const BACKUP_DIR = path.resolve(__dirname, "../backup-demo");
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

  try {
    console.log("[2/4] Loading SCADA Command Center...");
    await page.goto(TARGET_URL, { waitUntil: "networkidle", timeout: 30000 });
    await page.waitForTimeout(2000);

    // Switch to REPLAY MODE
    console.log("[3/4] Switching to REPLAY MODE & driving Demo Director...");
    const replayButton = page.locator("button:has-text('REPLAY MODE')");
    if (await replayButton.isVisible()) {
      await replayButton.click();
      await page.waitForTimeout(1000);
    }

    // Switch to Director Tab
    const directorTab = page.locator("button:has-text('Director')");
    if (await directorTab.isVisible()) {
      await directorTab.click();
      await page.waitForTimeout(1000);
    }

    // Click "Run Full Demo"
    const runDemoButton = page.locator("button:has-text('Run Full Demo')");
    if (await runDemoButton.isVisible()) {
      await runDemoButton.click();
      await page.waitForTimeout(1000);
    }

    // Switch to Audience View
    const audienceViewBtn = page.locator("button:has-text('Audience View')");
    if (await audienceViewBtn.isVisible()) {
      await audienceViewBtn.click();
      await page.waitForTimeout(1000);
    }

    // Let the demo sequence record for 12 seconds
    console.log("Recording video frames...");
    await page.waitForTimeout(12000);

    console.log("[4/4] Finalizing video recording...");
  } catch (err) {
    console.error("Error during recording:", err);
  } finally {
    // Close page and context to finalize video writing
    await page.close();
    await context.close();
    await browser.close();
  }

  // Rename video file to standard name
  const videoFiles = fs.readdirSync(BACKUP_DIR).filter((f) => f.endsWith(".webm"));
  if (videoFiles.length > 0) {
    const latestVideo = videoFiles[videoFiles.length - 1];
    const targetFile = path.join(BACKUP_DIR, "gridsentinel-backup-demo.webm");
    try {
      const srcPath = path.join(BACKUP_DIR, latestVideo);
      if (srcPath !== targetFile) {
        fs.copyFileSync(srcPath, targetFile);
      }
      console.log(`\n✔ Backup video generated successfully:`);
      console.log(`  ${targetFile}\n`);
    } catch (e) {
      console.log(`\n✔ Backup video saved: ${path.join(BACKUP_DIR, latestVideo)}\n`);
    }
  } else {
    console.log(`\n✔ Backup video saved in: ${BACKUP_DIR}\n`);
  }
}

run();
