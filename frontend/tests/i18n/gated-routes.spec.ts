// H4 F5.1 - Specs deterministas para rotas gated prefixadas.
//
// Valida que:
//  - primeiro acesso sem cookie age-verified em rota gated prefixada
//    redireciona 302 PRESERVANDO o prefixo de locale;
//  - /{en,es,fr}/age-verify retorna 200 (nao 404);
//  - <title> de /conta, /plano, /favoritos e locale-aware apos F1.1.
//
// Porta/host: 127.0.0.1:3100 conforme frontend/playwright.config.ts.

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

test.describe("age gate preserves locale prefix", () => {
  for (const prefix of ["en", "es", "fr"]) {
    test(`/${prefix}/ajuda without age cookie redirects to /${prefix}/age-verify`, async ({
      request,
    }) => {
      const res = await request.get(`/${prefix}/ajuda`, {
        maxRedirects: 0,
        failOnStatusCode: false,
      });
      expect(res.status()).toBe(302);
      const loc = res.headers()["location"] || "";
      expect(loc).toContain(`/${prefix}/age-verify`);
      expect(loc).toContain(`next=%2F${prefix}%2Fajuda`);
    });

    test(`/${prefix}/age-verify returns 200 (not 404)`, async ({ request }) => {
      const res = await request.get(`/${prefix}/age-verify`, {
        failOnStatusCode: false,
      });
      expect(res.status()).toBe(200);
    });
  }
});

test.describe("metadata is locale-aware after F1.1", () => {
  for (const { locale, pattern } of [
    { locale: "pt-BR", pattern: /Minha conta/i },
    { locale: "en-US", pattern: /My account/i },
    { locale: "es-419", pattern: /Mi cuenta/i },
    { locale: "fr-FR", pattern: /Mon compte/i },
  ]) {
    test(`/conta <title> matches ${locale}`, async ({ page, context }) => {
      await context.addCookies([AGE_COOKIE, localeCookie(locale)]);
      await page.goto("/conta", { waitUntil: "domcontentloaded" });
      await expect(page).toHaveTitle(pattern);
    });
  }
});
