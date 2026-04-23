// F9.9 - DECISIONS #19: link /c/:id indexado com prefixo de locale desligado
// deve redirecionar 301 permanente para rota sem prefixo, preservando o slug
// do share (SEO). NUNCA retornar 404 ou fallback silencioso.
//
// Controle de teste: o webServer do Playwright roda com
// NEXT_PUBLIC_ENABLED_LOCALES=pt-BR, portanto /en, /es e /fr estao desligados.

import { test, expect } from "@playwright/test";

test.describe("F9.9 - 301 para locale desligado em share link", () => {
  const slug = "rally4-fixture-slug";

  for (const prefix of ["en", "es", "fr"]) {
    test(`GET /${prefix}/c/${slug} -> 301 -> /c/${slug}`, async ({ request }) => {
      const res = await request.get(`/${prefix}/c/${slug}`, {
        maxRedirects: 0,
        failOnStatusCode: false,
      });
      expect(res.status()).toBe(301);
      const location = res.headers()["location"] ?? "";
      // Location pode ser absoluto ou relativo; normalizar para pathname.
      const pathname = location.startsWith("http")
        ? new URL(location).pathname
        : location;
      expect(pathname).toBe(`/c/${slug}`);
    });
  }

  // Sanity: rota sem prefixo nao pode ser tratada como locale desligado.
  // Slug inexistente -> backend pode devolver 404 ou 200 com fallback;
  // qualquer status e aceito EXCETO 301 (que indicaria que pt-BR foi
  // incorretamente considerado "desligado" pelo middleware).
  test(`GET /c/${slug} NAO dispara 301 de locale desligado`, async ({ request }) => {
    const res = await request.get(`/c/${slug}`, {
      maxRedirects: 0,
      failOnStatusCode: false,
    });
    expect(res.status()).not.toBe(301);
  });
});
