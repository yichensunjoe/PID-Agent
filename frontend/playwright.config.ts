import { defineConfig } from "@playwright/test";
import path from "node:path";

const databasePath = path.resolve("test-results", `pid-agent-e2e-${process.pid}.db`);
const diagnosticsPath = path.resolve("test-results", `pid-agent-e2e-${process.pid}.diagnostics.jsonl`);

export default defineConfig({
  testDir: "./e2e",
  testIgnore: "security.shared.spec.ts",
  outputDir: "test-results/playwright",
  snapshotPathTemplate: "{testDir}/{testFilePath}-snapshots/{arg}{ext}",
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  timeout: 45_000,
  expect: {
    timeout: 8_000,
    toHaveScreenshot: {
      animations: "disabled",
      caret: "hide",
      maxDiffPixelRatio: 0.015,
    },
  },
  reporter: process.env.CI
    ? [["line"], ["html", { outputFolder: "test-results/playwright-report", open: "never" }]]
    : [["list"], ["html", { outputFolder: "test-results/playwright-report", open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:4173",
    viewport: { width: 1440, height: 960 },
    locale: "zh-CN",
    timezoneId: "Asia/Shanghai",
    colorScheme: "light",
    reducedMotion: "reduce",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: process.env.PID_AGENT_E2E_NO_VIDEO ? "off" : "retain-on-failure",
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH }
      : undefined,
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
  webServer: [
    {
      command: "python -m uvicorn agentcad.main:app --host 127.0.0.1 --port 8000",
      cwd: "..",
      env: {
        ...process.env,
        PYTHONPATH: path.resolve("../backend"),
        PID_AGENT_DATABASE_PATH: databasePath,
        PID_AGENT_DIAGNOSTICS_PATH: diagnosticsPath,
        PID_AGENT_FRONTEND_DIST: path.resolve("dist"),
        PID_AGENT_CORS_ORIGINS: "http://127.0.0.1:4173",
      },
      url: "http://127.0.0.1:8000/health",
      timeout: 30_000,
      reuseExistingServer: false,
    },
    {
      command: "npm run preview -- --host 127.0.0.1 --port 4173",
      cwd: ".",
      url: "http://127.0.0.1:4173",
      timeout: 30_000,
      reuseExistingServer: false,
    },
  ],
});
