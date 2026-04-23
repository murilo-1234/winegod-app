// F9.4 - Teste visual i18n da rota legal canonica.
// /legal/BR/pt-BR/privacy = celula BR publicada.
// /legal/DEFAULT/en-US/privacy = fallback DEFAULT.
// Rota 100% server-rendered de markdown estatico.

import { test, expect } from "@playwright/test";

test.describe("/legal visual", () => {
  for (const { path, label } of [
    { path: "/legal/BR/pt-BR/privacy", label: "BR-ptBR" },
    { path: "/legal/DEFAULT/en-US/privacy", label: "DEFAULT-enUS" },
  ]) {
    test(`legal ${label}`, async ({ page }) => {
      await page.goto(path, { waitUntil: "domcontentloaded" });
      await expect(page.locator("h1, h2").first()).toBeVisible();
      await expect(page).toHaveScreenshot(`legal-${label}.png`, {
        fullPage: false,
        animations: "disabled",
      });
    });
  }
});
