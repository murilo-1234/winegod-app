// F9.4 (corretivo) + H4 F5.2 - Testes visuais i18n em /ajuda.
//
// Matriz: 4 locales (pt-BR default, en via /en, es via /es, fr via /fr).
// H4 F5.2: seta wg_age_verified antes do goto para que os baselines
// capturem o conteudo da ajuda (nao o age gate). Tambem seta locale
// via cookie para reforcar o idioma ativo quando a URL nao e prefixada.

import { test, expect } from "@playwright/test";

const AGE_COOKIE = {
  name: "wg_age_verified",
  value: encodeURIComponent("BR:18:2026-04-22T00:00:00.000Z"),
  path: "/",
  domain: "127.0.0.1",
  sameSite: "Lax" as const,
};

function localeCookie(locale: string) {
  return {
    name: "wg_locale_choice",
    value: locale,
    path: "/",
    domain: "127.0.0.1",
    sameSite: "Lax" as const,
  };
}

test.describe("/ajuda visual matrix", () => {
  for (const { path, label, locale } of [
    { path: "/ajuda", label: "pt-BR", locale: "pt-BR" },
    { path: "/en/ajuda", label: "en-US", locale: "en-US" },
    { path: "/es/ajuda", label: "es-419", locale: "es-419" },
    { path: "/fr/ajuda", label: "fr-FR", locale: "fr-FR" },
  ]) {
    test(`ajuda ${label}`, async ({ page, context }) => {
      await context.addCookies([AGE_COOKIE, localeCookie(locale)]);
      await page.goto(path, { waitUntil: "domcontentloaded" });
      await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {
        // network nao precisa estar 100% idle; seguimos.
      });
      await expect(page).toHaveScreenshot(`ajuda-${label}.png`, {
        fullPage: false,
        animations: "disabled",
      });
    });
  }
});
