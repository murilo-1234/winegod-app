// F2.4 - Request config definitivo do next-intl (routing + fallback chain).
//
// Ordem de resolucao do locale (precedencia simplificada desta fase; F2.9
// formalizara sync bidirecional com perfil do usuario autenticado):
//   1. requestLocale do segmento [locale] (caso routing futuro use prefixo).
//   2. Cookie `wg_locale_choice` (escolha manual persistente do usuario).
//   3. Header geo `X-Vercel-IP-Country` mapeado por LOCALE_BY_COUNTRY.
//   4. defaultLocale de ./routing.ts ("pt-BR").
//
// Fallback chain de messages:
//   pt-BR  -> pt-BR
//   en-US  -> en-US  -> pt-BR
//   es-419 -> es-419 -> en-US -> pt-BR
//   fr-FR  -> fr-FR  -> en-US -> pt-BR
//
// Deep merge de plain objects permite que chaves do locale principal
// sobrescrevam fallback, preservando subarvores ausentes.

import { cookies, headers } from "next/headers";
import { getRequestConfig } from "next-intl/server";

import {
  type AppLocale,
  defaultLocale,
  isAppLocale,
  locales,
} from "./routing";

const LOCALE_BY_COUNTRY: Record<string, AppLocale> = {
  BR: "pt-BR",
  US: "en-US",
  MX: "es-419",
  FR: "fr-FR",
};

const MESSAGE_LOADERS: Record<
  AppLocale,
  () => Promise<Record<string, unknown>>
> = {
  "pt-BR": () => import("../messages/pt-BR.json").then((m) => m.default),
  "en-US": () => import("../messages/en-US.json").then((m) => m.default),
  "es-419": () => import("../messages/es-419.json").then((m) => m.default),
  "fr-FR": () => import("../messages/fr-FR.json").then((m) => m.default),
};

// Cadeia de fallback por locale, do mais especifico para o mais generico.
// A ordem do array determina o resultado do merge: indice 0 e o idioma
// principal e sobrescreve os anteriores; ultimos itens sao base.
const FALLBACK_CHAIN: Record<AppLocale, AppLocale[]> = {
  "pt-BR": ["pt-BR"],
  "en-US": ["en-US", "pt-BR"],
  "es-419": ["es-419", "en-US", "pt-BR"],
  "fr-FR": ["fr-FR", "en-US", "pt-BR"],
};

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value) &&
    Object.getPrototypeOf(value) === Object.prototype
  );
}

function deepMerge(
  base: Record<string, unknown>,
  override: Record<string, unknown>,
): Record<string, unknown> {
  const result: Record<string, unknown> = { ...base };
  for (const [key, value] of Object.entries(override)) {
    const existing = result[key];
    if (isPlainObject(existing) && isPlainObject(value)) {
      result[key] = deepMerge(existing, value);
    } else {
      result[key] = value;
    }
  }
  return result;
}

async function loadMessagesWithFallback(
  locale: AppLocale,
): Promise<Record<string, unknown>> {
  const chain = FALLBACK_CHAIN[locale];
  // Carrega do mais generico para o mais especifico, mesclando em cima:
  // o ultimo item (mais generico) vira base; o primeiro (locale pedido)
  // sobrescreve por ultimo.
  let merged: Record<string, unknown> = {};
  for (let i = chain.length - 1; i >= 0; i--) {
    const layer = await MESSAGE_LOADERS[chain[i]]();
    merged = deepMerge(merged, layer);
  }
  return merged;
}

// H4 F4.1 (I5) - Resolucao por Accept-Language como ultimo recurso antes
// de cair em defaultLocale. Evita que 404s e rotas sem contexto de locale
// (ex.: estrangeiro sem cookie, sem geo, sem prefixo) renderizem em pt-BR.
function resolveFromAcceptLanguage(
  headerValue: string | null,
): AppLocale | null {
  if (!headerValue) return null;
  const tags = headerValue
    .split(",")
    .map((entry) => {
      const [rawTag, qstr] = entry.trim().split(";q=");
      const q = qstr ? parseFloat(qstr) : 1.0;
      return { tag: (rawTag || "").trim().toLowerCase(), q };
    })
    .filter((t) => t.tag)
    .sort((a, b) => b.q - a.q);

  for (const { tag } of tags) {
    if (tag.startsWith("pt")) return "pt-BR";
    if (tag.startsWith("en")) return "en-US";
    if (tag.startsWith("es")) return "es-419";
    if (tag.startsWith("fr")) return "fr-FR";
  }
  return null;
}

async function resolveLocale(
  requested: string | undefined,
): Promise<AppLocale> {
  if (isAppLocale(requested)) {
    return requested;
  }

  const cookieStore = await cookies();
  const cookieChoice = cookieStore.get("wg_locale_choice")?.value;
  if (isAppLocale(cookieChoice)) {
    return cookieChoice;
  }

  const headerStore = await headers();
  const geoCountryRaw =
    headerStore.get("x-vercel-ip-country") ??
    headerStore.get("X-Vercel-IP-Country");
  const geoCountry = geoCountryRaw?.toUpperCase();
  if (geoCountry && geoCountry in LOCALE_BY_COUNTRY) {
    return LOCALE_BY_COUNTRY[geoCountry];
  }

  // H4 F4.1 (I5): Accept-Language como ultimo recurso; defaultLocale
  // permanece "pt-BR" mas deixa de ser o catch-all para estrangeiros.
  const acceptLang = headerStore.get("accept-language");
  const alLocale = resolveFromAcceptLanguage(acceptLang);
  if (alLocale) {
    return alLocale;
  }

  return defaultLocale;
}

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const resolved = await resolveLocale(requested);
  // Garante que `locales` seja referenciado no runtime (evita tree-shake
  // do import e deixa explicito que a whitelist vem do routing oficial).
  const locale: AppLocale = locales.includes(resolved) ? resolved : defaultLocale;

  return {
    locale,
    messages: await loadMessagesWithFallback(locale),
  };
});
