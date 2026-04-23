// F2.9a - Espelho minimo do shared/i18n/markets.json relevante para o
// client (apenas locale + currency default por country).
//
// O JSON canonico vive em shared/i18n/markets.json e e a fonte de verdade
// para o backend. Aqui temos somente o subset que o client precisa para
// derivar defaults quando o usuario nao tem preferencia salva. Se um pais
// novo entrar em markets.json (ex: it-IT), atualizar tambem este mapa.

import {
  type AppLocale,
  defaultLocale,
  isAppLocale,
} from "@/i18n/routing";

export type MarketCountry = string;
export type CurrencyCode = string;

export interface MarketDefaults {
  defaultLocale: AppLocale;
  currencyDefault: CurrencyCode;
  ageGateRequired: boolean;
  ageGateMinimum: number;
}

// F7.6 - retorno minimalista do age gate por market. Facilita o middleware
// e a page /age-verify decidirem bloqueio sem recarregar MARKETS inteiro.
export interface AgeGatePolicy {
  required: boolean;
  minimumAge: number;
}

export const DEFAULT_MARKET_COUNTRY: MarketCountry = "BR";
export const FALLBACK_MARKET_DEFAULTS: MarketDefaults = {
  defaultLocale,
  currencyDefault: "BRL",
  ageGateRequired: true,
  ageGateMinimum: 18,
};

// Valores espelham shared/i18n/markets.json (source of truth do backend).
// Se um mercado novo entrar la, atualizar tambem este mapa.
const MARKETS: Record<string, MarketDefaults> = {
  BR: {
    defaultLocale: "pt-BR",
    currencyDefault: "BRL",
    ageGateRequired: true,
    ageGateMinimum: 18,
  },
  US: {
    defaultLocale: "en-US",
    currencyDefault: "USD",
    ageGateRequired: true,
    ageGateMinimum: 21,
  },
  MX: {
    defaultLocale: "es-419",
    currencyDefault: "MXN",
    ageGateRequired: true,
    ageGateMinimum: 18,
  },
  FR: {
    defaultLocale: "fr-FR",
    currencyDefault: "EUR",
    ageGateRequired: true,
    ageGateMinimum: 18,
  },
  DEFAULT: {
    defaultLocale: "en-US",
    currencyDefault: "USD",
    ageGateRequired: true,
    ageGateMinimum: 18,
  },
};

export function isKnownMarketCountry(value: unknown): value is MarketCountry {
  return typeof value === "string" && value.toUpperCase() in MARKETS;
}

export function normalizeMarketCountry(value: unknown): MarketCountry {
  if (typeof value === "string") {
    const upper = value.toUpperCase();
    if (upper in MARKETS) return upper;
  }
  return DEFAULT_MARKET_COUNTRY;
}

export function getMarketDefaults(country: unknown): MarketDefaults {
  const normalized = normalizeMarketCountry(country);
  return MARKETS[normalized] ?? FALLBACK_MARKET_DEFAULTS;
}

export function deriveMarketFromLocale(locale: unknown): MarketCountry {
  if (!isAppLocale(locale)) return DEFAULT_MARKET_COUNTRY;
  switch (locale) {
    case "pt-BR":
      return "BR";
    case "en-US":
      return "US";
    case "es-419":
      return "MX";
    case "fr-FR":
      return "FR";
  }
}

export function isValidCurrencyCode(value: unknown): value is CurrencyCode {
  return typeof value === "string" && /^[A-Z]{3}$/.test(value);
}

export function getMarketAgeGate(country: unknown): AgeGatePolicy {
  const defaults = getMarketDefaults(country);
  return {
    required: defaults.ageGateRequired,
    minimumAge: defaults.ageGateMinimum,
  };
}
