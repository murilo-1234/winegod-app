// F2.9c1 - Resolver client-side de metadata outbound de locale.
//
// Resolve uiLocale / marketCountry / currencyOverride para anexar em
// requests para api.winegod.ai. Funcao client-only por design (le cookie
// + DOM); SSR retorna defaults seguros sem quebrar.
//
// Ordem de resolucao (1 vez por chamada; sem cache):
//   1. cookie wg_locale_choice (se Tier 1)
//   2. document.documentElement.lang (se Tier 1)
//   3. defaultLocale ("pt-BR")
//
// marketCountry vem de deriveMarketFromLocale(locale) (markets.ts).
// currencyOverride permanece null nesta fase (sem fonte explicita).
//
// NAO le diretamente o LocaleContext para nao acoplar a hierarquia de
// providers a chamadas de fetch fora da arvore React.

import { type AppLocale, defaultLocale, isAppLocale } from "@/i18n/routing";

import { readLocaleCookie } from "./cookie";
import {
  type CurrencyCode,
  type MarketCountry,
  deriveMarketFromLocale,
} from "./markets";

export interface OutboundLocaleMetadata {
  uiLocale: AppLocale;
  marketCountry: MarketCountry;
  currencyOverride: CurrencyCode | null;
}

export interface OutboundLocaleHeaders {
  "X-WG-UI-Locale": string;
  "X-WG-Market-Country": string;
  "X-WG-Currency": string;
}

function resolveUiLocale(): AppLocale {
  if (typeof document === "undefined") return defaultLocale;

  const cookieLocale = readLocaleCookie();
  if (cookieLocale) return cookieLocale;

  const htmlLang = document.documentElement?.lang;
  if (isAppLocale(htmlLang)) return htmlLang;

  return defaultLocale;
}

export function resolveOutboundLocale(): OutboundLocaleMetadata {
  const uiLocale = resolveUiLocale();
  return {
    uiLocale,
    marketCountry: deriveMarketFromLocale(uiLocale),
    currencyOverride: null,
  };
}

/**
 * Headers prontos para anexar em qualquer request para api.winegod.ai.
 * `X-WG-Currency` vai como string vazia quando nao ha override (mantem
 * o header presente para auditoria do backend/Sentry; backend trata
 * vazio como ausente).
 */
export function getOutboundLocaleHeaders(): OutboundLocaleHeaders {
  const meta = resolveOutboundLocale();
  return {
    "X-WG-UI-Locale": meta.uiLocale,
    "X-WG-Market-Country": meta.marketCountry,
    "X-WG-Currency": meta.currencyOverride ?? "",
  };
}

/**
 * Conveniencia: bloco para spread em body JSON quando o endpoint aceita.
 * Mantem o mesmo shape do PATCH /api/auth/me/preferences (snake_case).
 */
export function getOutboundLocaleBodyFields(): {
  ui_locale: string;
  market_country: string;
  currency_override: string | null;
} {
  const meta = resolveOutboundLocale();
  return {
    ui_locale: meta.uiLocale,
    market_country: meta.marketCountry,
    currency_override: meta.currencyOverride,
  };
}
