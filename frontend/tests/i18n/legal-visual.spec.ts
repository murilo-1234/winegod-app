// F9.4 - Teste visual i18n da rota legal canonica.
// Cobertura final:
//   - BR/pt-BR
//   - DEFAULT/en-US
//   - DEFAULT/es-419
//   - DEFAULT/fr-FR
// Rota 100% server-rendered de markdown estatico.

import { test, expect } from "@playwright/test";

test.describe("/legal visual", () => {
  for (const { path, label } of [
    { path: "/legal/BR/pt-BR/privacy", label: "BR-ptBR" },
    { path: "/legal/DEFAULT/en-US/privacy", label: "DEFAULT-enUS" },
    { path: "/legal/DEFAULT/es-419/privacy", label: "DEFAULT-es419" },
    { path: "/legal/DEFAULT/fr-FR/privacy", label: "DEFAULT-frFR" },
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
