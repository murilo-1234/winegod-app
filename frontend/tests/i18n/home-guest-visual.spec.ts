// F9.4 (corretivo) - Visual i18n da home/chat guest.
//
// A home "/" e rotas prefixadas "/en", "/es", "/fr" sao rotas gated pelo
// middleware F7.6 (age gate) E nao precisam de backend para renderizar a
// shell do chat guest. Para evitar o redirect pra /age-verify nos snapshots,
// setamos o cookie `wg_age_verified` valido antes de navegar.
//
// O cookie nao nos faz logar: fluxo de auth segue intacto. A home guest
// renderiza input, sidebar, menus de idioma e brand. Suficiente para
// detectar regressao visual de locale e layout.
//
// Matriz: 4 locales x 2 projetos (desktop-chromium, mobile-pixel7).
// Idioma por URL: "/" usa fallback do middleware (pt-BR por default); para
// forcar o idioma desejado sem autenticar, tambem setamos
// `wg_locale_choice=<locale>` como cookie.

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

test.describe("/ home/chat guest visual matrix", () => {
  for (const { path, locale, label } of [
    { path: "/", locale: "pt-BR", label: "pt-BR" },
    { path: "/", locale: "en-US", label: "en-US-cookie" },
    { path: "/", locale: "es-419", label: "es-419-cookie" },
    { path: "/", locale: "fr-FR", label: "fr-FR-cookie" },
  ]) {
    test(`home guest ${label}`, async ({ page, context }) => {
      await context.addCookies([AGE_COOKIE, localeCookie(locale)]);
      await page.goto(path, { waitUntil: "domcontentloaded" });
      // Aguarda shell principal; a home espera uma heading/input visiveis
      // sem precisar de chamada a API. networkidle e best-effort.
      await page
        .waitForLoadState("networkidle", { timeout: 10_000 })
        .catch(() => {
          // prossegue mesmo sem idle: API guest pode continuar em flight.
        });
      await expect(page).toHaveScreenshot(`home-guest-${label}.png`, {
        fullPage: false,
        animations: "disabled",
      });
    });
  }
});
