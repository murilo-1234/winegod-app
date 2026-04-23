import { defineConfig, devices } from "@playwright/test";

const PORT = 3111;
const BASE_URL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: "./tests/i18n",
  testMatch: "**/share-301-locale-disabled.spec.ts",
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: BASE_URL,
    actionTimeout: 10_000,
    navigationTimeout: 15_000,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "desktop-chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } },
    },
  ],
  webServer: {
    command:
      `powershell -Command "$env:NEXT_PUBLIC_ENABLED_LOCALES='pt-BR'; ` +
      `npm run build; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; ` +
      `npm run start -- -p ${PORT}"`,
    url: BASE_URL,
    reuseExistingServer: false,
    timeout: 240_000,
  },
});
