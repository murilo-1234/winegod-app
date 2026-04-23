// F9.3 - Playwright config para testes visuais i18n + F9.9.
//
// Estrategia:
//   - webServer auto-inicia `next start` na porta 3100 (apos build).
//   - NEXT_PUBLIC_ENABLED_LOCALES forcado a "pt-BR" para F9.9 testar 301
//     em /en|/es|/fr/c/:id quando locale desligado.
//   - 2 projetos: desktop-chromium e mobile-pixel7 para cobertura
//     representativa sem explodir matriz.

import { defineConfig, devices } from "@playwright/test";

const PORT = 3100;
const BASE_URL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: "./tests/i18n",
  timeout: 30_000,
  expect: {
    timeout: 5_000,
    toHaveScreenshot: {
      // Threshold generoso para font rendering cross-OS; suficiente para
      // detectar regressao de layout/locale sem falso-positivo de subpixel.
      maxDiffPixelRatio: 0.02,
    },
  },
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
    {
      name: "mobile-pixel7",
      use: { ...devices["Pixel 7"] },
    },
  ],
  webServer: {
    command: `npm run start -- -p ${PORT}`,
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      NEXT_PUBLIC_ENABLED_LOCALES: "pt-BR",
    },
  },
});
