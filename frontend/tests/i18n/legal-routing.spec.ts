import { test, expect } from "@playwright/test";

function localeCookie(locale: string) {
  return {
    name: "wg_locale_choice",
    value: locale,
    path: "/",
    domain: "127.0.0.1",
    sameSite: "Lax" as const,
  };
}

test.describe("legacy legal routes follow locale", () => {
  for (const { locale, entry, expected } of [
    {
      locale: "pt-BR",
      entry: "/privacy",
      expected: "/legal/BR/pt-BR/privacy",
    },
    {
      locale: "en-US",
      entry: "/privacy",
      expected: "/legal/DEFAULT/en-US/privacy",
    },
    {
      locale: "es-419",
      entry: "/privacy",
      expected: "/legal/DEFAULT/es-419/privacy",
    },
    {
      locale: "fr-FR",
      entry: "/privacy",
      expected: "/legal/DEFAULT/fr-FR/privacy",
    },
  ]) {
    test(`${entry} redirects to ${expected} for ${locale}`, async ({
      page,
      context,
    }) => {
      await context.addCookies([localeCookie(locale)]);
      await page.goto(entry, { waitUntil: "domcontentloaded" });
      await expect(page).toHaveURL(expected);
      await expect(page.locator("h1, h2").first()).toBeVisible();
    });
  }
});

test.describe("prefixed legal routes keep locale-specific targets", () => {
  for (const { entry, expected } of [
    { entry: "/en/terms", expected: "/legal/DEFAULT/en-US/terms" },
    { entry: "/es/terms", expected: "/legal/DEFAULT/es-419/terms" },
    { entry: "/fr/terms", expected: "/legal/DEFAULT/fr-FR/terms" },
  ]) {
    test(`${entry} lands on ${expected}`, async ({ page }) => {
      await page.goto(entry, { waitUntil: "domcontentloaded" });
      await expect(page).toHaveURL(expected);
      await expect(page.locator("h1, h2").first()).toBeVisible();
    });
  }
});

test.describe("age gate legal links follow rendered locale", () => {
  for (const { entry, termsHref, privacyHref, cookieLocale } of [
    {
      entry: "/age-verify",
      termsHref: "/legal/BR/pt-BR/terms",
      privacyHref: "/legal/BR/pt-BR/privacy",
      cookieLocale: "pt-BR",
    },
    {
      entry: "/en/age-verify",
      termsHref: "/legal/DEFAULT/en-US/terms",
      privacyHref: "/legal/DEFAULT/en-US/privacy",
    },
    {
      entry: "/es/age-verify",
      termsHref: "/legal/DEFAULT/es-419/terms",
      privacyHref: "/legal/DEFAULT/es-419/privacy",
    },
    {
      entry: "/fr/age-verify",
      termsHref: "/legal/DEFAULT/fr-FR/terms",
      privacyHref: "/legal/DEFAULT/fr-FR/privacy",
    },
  ]) {
    test(`${entry} exposes locale-aware legal links`, async ({
      page,
      context,
    }) => {
      if (cookieLocale) {
        await context.addCookies([localeCookie(cookieLocale)]);
      }
      await page.goto(entry, { waitUntil: "domcontentloaded" });
      await expect(page.locator(`a[href="${termsHref}"]`)).toBeVisible();
      await expect(page.locator(`a[href="${privacyHref}"]`)).toBeVisible();
    });
  }
});
