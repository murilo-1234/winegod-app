// F9.4 - Teste visual i18n do AgeGate em /age-verify.
// Rota publica estatica, nao depende de API.

import { test, expect } from "@playwright/test";

test.describe("/age-verify visual matrix", () => {
  for (const { path, label } of [
    { path: "/age-verify", label: "pt-BR" },
    { path: "/en/age-verify", label: "en-US" },
    { path: "/es/age-verify", label: "es-419" },
    { path: "/fr/age-verify", label: "fr-FR" },
  ]) {
    test(`age-verify ${label}`, async ({ page }) => {
      await page.goto(path, { waitUntil: "domcontentloaded" });
      await expect(page.getByRole("heading")).toBeVisible();
      await expect(page).toHaveScreenshot(`age-verify-${label}.png`, {
        fullPage: false,
        animations: "disabled",
      });
    });
  }
});
