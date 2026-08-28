import { defineConfig, devices } from "@playwright/test";

const apiUrl = "http://127.0.0.1:5100";

export default defineConfig({
  testDir: "./tests/e2e",
  testIgnore: process.env.CAPTURE_DOCS ? [] : ["**/capturas.spec.ts"],
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:3100",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command:
        `DATABASE_URL=postgresql://argus:argus@127.0.0.1:55432/argus_test ` +
        `CORS_ORIGINS=http://127.0.0.1:3100 PORT=5100 FLASK_DEBUG=0 ` +
        "uv run --quiet python run.py",
      cwd: "../backend",
      url: `${apiUrl}/health/ready`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "python3 -m http.server 3100 --directory out",
      cwd: ".",
      port: 3100,
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
});
