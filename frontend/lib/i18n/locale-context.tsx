"use client";

// F2.9a - Provider client-side de locale/preferencias.
//
// Esta fase (F2.9a) entrega APENAS a fundacao:
//   - estado de uiLocale, marketCountry, currencyOverride
//   - persistencia do cookie wg_locale_choice (TTL 1 ano)
//   - inicializacao a partir do locale ja resolvido pelo server
//     (frontend/i18n/request.ts, layout.tsx)
//
// NAO faz nesta fase (fica para F2.9b/c):
//   - sync bidirecional com /api/auth/me apos login
//   - envio de X-WG-* em fetch (lib/api.ts)
//   - banner de sugestao (LocaleSuggestionBanner)
//   - seletor de idioma na UI
//
// Cookie wg_locale_choice = escolha MANUAL do usuario. Se ele nunca trocou
// idioma, o cookie nao existe e o estado vem do locale resolvido pelo
// server (geo header / fallback). Se trocar, gravamos o cookie.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { type AppLocale, defaultLocale, isAppLocale } from "@/i18n/routing";

import { capture as posthogCapture } from "@/lib/observability/posthog";

import { readLocaleCookie, writeLocaleCookie } from "./cookie";
import {
  DEFAULT_MARKET_COUNTRY,
  type CurrencyCode,
  type MarketCountry,
  deriveMarketFromLocale,
  getMarketDefaults,
  isValidCurrencyCode,
  normalizeMarketCountry,
} from "./markets";

export interface LocaleContextValue {
  uiLocale: AppLocale;
  marketCountry: MarketCountry;
  currencyOverride: CurrencyCode | null;
  /** Currency efetivamente em uso = override do usuario OU default do market. */
  effectiveCurrency: CurrencyCode;
  /**
   * F2.9c2: pais detectado pelo geo header (X-Vercel-IP-Country) na carga
   * SSR. Uppercased quando conhecido, null se o header nao veio ou foi
   * invalido. Usado pelo LocaleSuggestionBanner e telemetria de mismatch.
   * NAO muda em runtime: o geo server-side e imutavel por sessao.
   */
  geoCountry: MarketCountry | null;
  /** Atualiza locale e PERSISTE no cookie wg_locale_choice (escolha manual). */
  setUiLocale: (locale: AppLocale) => void;
  /** Atualiza market sem tocar no cookie de locale. */
  setMarketCountry: (country: MarketCountry) => void;
  /** Atualiza override; passe null para limpar e voltar ao default do market. */
  setCurrencyOverride: (currency: CurrencyCode | null) => void;
}

const LocaleContext = createContext<LocaleContextValue | null>(null);

export interface LocaleProviderProps {
  /** Locale resolvido pelo server (ex: getLocale() do next-intl). */
  initialUiLocale: AppLocale;
  /** Market inicial; default BR. */
  initialMarketCountry?: MarketCountry;
  /** Override inicial; null mantem default do market. */
  initialCurrencyOverride?: CurrencyCode | null;
  /**
   * F2.9c2: pais detectado pelo server via X-Vercel-IP-Country na request
   * atual. Passe `null` quando o header nao veio (dev local sem proxy).
   */
  initialGeoCountry?: MarketCountry | null;
  children: ReactNode;
}

function normalizeLocale(value: unknown, fallback: AppLocale): AppLocale {
  return isAppLocale(value) ? value : fallback;
}

function normalizeCurrency(value: unknown): CurrencyCode | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== "string") return null;
  const upper = value.toUpperCase();
  return isValidCurrencyCode(upper) ? upper : null;
}

function normalizeOptionalGeoCountry(
  value: unknown,
): MarketCountry | null {
  if (typeof value !== "string") return null;
  const upper = value.toUpperCase().trim();
  if (!upper) return null;
  // Aceita qualquer ISO alpha-2; o consumidor decide se esta em
  // LOCALE_BY_COUNTRY. Mantemos a capitalizacao consistente.
  return /^[A-Z]{2}$/.test(upper) ? upper : null;
}

export function LocaleProvider({
  initialUiLocale,
  initialMarketCountry,
  initialCurrencyOverride = null,
  initialGeoCountry = null,
  children,
}: LocaleProviderProps) {
  const seedLocale = normalizeLocale(initialUiLocale, defaultLocale);
  const seedMarket = normalizeMarketCountry(
    initialMarketCountry ?? deriveMarketFromLocale(seedLocale),
  );
  const seedCurrency = normalizeCurrency(initialCurrencyOverride);
  const seedGeo = normalizeOptionalGeoCountry(initialGeoCountry);

  const [uiLocale, setUiLocaleState] = useState<AppLocale>(seedLocale);
  const [marketCountry, setMarketCountryState] = useState<MarketCountry>(
    seedMarket,
  );
  const [currencyOverride, setCurrencyOverrideState] = useState<
    CurrencyCode | null
  >(seedCurrency);
  // geoCountry e frozen: nao ha setter publico. O valor vive so para
  // consumo de banner/telemetria e nao muda por sessao.
  const [geoCountry] = useState<MarketCountry | null>(seedGeo);

  // Hidratacao client-side: se o usuario ja escolheu manualmente em sessao
  // anterior, o cookie wg_locale_choice vence o seed do server. Roda 1 vez
  // por mount. Intencional ler `uiLocale` na closure inicial (nao re-disparar
  // quando o estado muda); por isso `[]` como deps.
  useEffect(() => {
    const cookieLocale = readLocaleCookie();
    if (cookieLocale && cookieLocale !== uiLocale) {
      setUiLocaleState(cookieLocale);
    }
  }, []);

  const setUiLocale = useCallback((locale: AppLocale) => {
    if (!isAppLocale(locale)) return;
    setUiLocaleState((prev) => {
      // F11.4 - emite `locale_switch` ao setar manualmente um locale
      // diferente do atual. Evita emitir em re-seed do mesmo valor.
      if (prev !== locale) {
        posthogCapture("locale_switch", {
          from_locale: prev,
          to_locale: locale,
        });
      }
      return locale;
    });
    writeLocaleCookie(locale);
  }, []);

  const setMarketCountry = useCallback((country: MarketCountry) => {
    setMarketCountryState(normalizeMarketCountry(country));
  }, []);

  const setCurrencyOverride = useCallback(
    (currency: CurrencyCode | null) => {
      setCurrencyOverrideState(normalizeCurrency(currency));
    },
    [],
  );

  const effectiveCurrency = useMemo<CurrencyCode>(() => {
    if (currencyOverride) return currencyOverride;
    return getMarketDefaults(marketCountry).currencyDefault;
  }, [currencyOverride, marketCountry]);

  const value = useMemo<LocaleContextValue>(
    () => ({
      uiLocale,
      marketCountry,
      currencyOverride,
      effectiveCurrency,
      geoCountry,
      setUiLocale,
      setMarketCountry,
      setCurrencyOverride,
    }),
    [
      uiLocale,
      marketCountry,
      currencyOverride,
      effectiveCurrency,
      geoCountry,
      setUiLocale,
      setMarketCountry,
      setCurrencyOverride,
    ],
  );

  return (
    <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>
  );
}

export function useLocaleContext(): LocaleContextValue {
  const ctx = useContext(LocaleContext);
  if (!ctx) {
    // Defensivo: se um componente for renderizado fora do provider, retorna
    // defaults sem quebrar a UI. Acontece em testes isolados ou em arvores
    // server-only que vazem props.
    return {
      uiLocale: defaultLocale,
      marketCountry: DEFAULT_MARKET_COUNTRY,
      currencyOverride: null,
      effectiveCurrency: getMarketDefaults(DEFAULT_MARKET_COUNTRY)
        .currencyDefault,
      geoCountry: null,
      setUiLocale: () => {},
      setMarketCountry: () => {},
      setCurrencyOverride: () => {},
    };
  }
  return ctx;
}
