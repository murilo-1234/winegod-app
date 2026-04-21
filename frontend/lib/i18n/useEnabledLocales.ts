"use client";

// F2.4c - Hook client-side para consumir GET /api/config/enabled-locales.
//
// Apenas leitura. Sem cookie cross-domain, sem headers X-WG-* (nao precisa
// de auth). Em qualquer falha (rede, JSON invalido, locale fora da
// whitelist, lista vazia), cai em FALLBACK_LOCALES = ["pt-BR"].
//
// Nesta fase NAO ha consumidor: o hook fica disponivel para o seletor de
// idioma e para qualquer componente que precise filtrar a UI por locales
// ativos em fases futuras (Onda 2 / Onda 4).

import useSWR from "swr";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";
const ENDPOINT = `${API_URL}/api/config/enabled-locales`;

type SupportedLocale = "pt-BR" | "en-US" | "es-419" | "fr-FR";

const SUPPORTED_LOCALES: readonly SupportedLocale[] = [
  "pt-BR",
  "en-US",
  "es-419",
  "fr-FR",
];

const FALLBACK_LOCALES: SupportedLocale[] = ["pt-BR"];
const DEFAULT_LOCALE: SupportedLocale = "pt-BR";

type EnabledLocalesResponse = {
  enabled_locales?: unknown;
  default_locale?: unknown;
  updated_at?: unknown;
  source?: unknown;
};

type NormalizedConfig = {
  locales: SupportedLocale[];
  defaultLocale: SupportedLocale;
};

function isSupportedLocale(value: unknown): value is SupportedLocale {
  return (
    typeof value === "string" &&
    (SUPPORTED_LOCALES as readonly string[]).includes(value)
  );
}

function normalizeLocalesList(value: unknown): SupportedLocale[] {
  if (!Array.isArray(value)) {
    return [...FALLBACK_LOCALES];
  }
  const seen = new Set<SupportedLocale>();
  const cleaned: SupportedLocale[] = [];
  for (const item of value) {
    if (isSupportedLocale(item) && !seen.has(item)) {
      seen.add(item);
      cleaned.push(item);
    }
  }
  if (cleaned.length === 0) {
    return [...FALLBACK_LOCALES];
  }
  return cleaned;
}

function normalizeDefault(value: unknown): SupportedLocale {
  return isSupportedLocale(value) ? value : DEFAULT_LOCALE;
}

function normalize(payload: EnabledLocalesResponse | null | undefined): NormalizedConfig {
  if (!payload) {
    return {
      locales: [...FALLBACK_LOCALES],
      defaultLocale: DEFAULT_LOCALE,
    };
  }
  return {
    locales: normalizeLocalesList(payload.enabled_locales),
    defaultLocale: normalizeDefault(payload.default_locale),
  };
}

async function fetcher(url: string): Promise<EnabledLocalesResponse> {
  const response = await fetch(url, { credentials: "omit" });
  if (!response.ok) {
    throw new Error(`enabled-locales http ${response.status}`);
  }
  return (await response.json()) as EnabledLocalesResponse;
}

export type UseEnabledLocalesResult = {
  locales: string[];
  defaultLocale: string;
  isLoading: boolean;
};

export function useEnabledLocales(): UseEnabledLocalesResult {
  const { data, error, isLoading } = useSWR<EnabledLocalesResponse>(
    ENDPOINT,
    fetcher,
    {
      refreshInterval: 30000,
      revalidateOnFocus: true,
      shouldRetryOnError: true,
      errorRetryInterval: 5000,
    },
  );

  if (error || !data) {
    return {
      locales: [...FALLBACK_LOCALES],
      defaultLocale: DEFAULT_LOCALE,
      isLoading,
    };
  }

  const normalized = normalize(data);
  return {
    locales: normalized.locales,
    defaultLocale: normalized.defaultLocale,
    isLoading,
  };
}
