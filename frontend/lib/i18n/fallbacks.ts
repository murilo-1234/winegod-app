// F2.7 - Fallback chain de locales (helper puro).
//
// Server-safe (sem "use client"). Sem dependencia externa.
// Espelha a chain canonica decidida no plano i18n:
//   pt-BR  -> [pt-BR]
//   en-US  -> [en-US, pt-BR]
//   es-419 -> [es-419, en-US, pt-BR]
//   fr-FR  -> [fr-FR, en-US, pt-BR]
//
// Locale invalido, ausente, vazio ou fora da whitelist Tier 1 cai em
// [pt-BR]. getFallbackChain sempre devolve uma copia nova do array
// interno para evitar mutacao acidental.

export type SupportedLocale = "pt-BR" | "en-US" | "es-419" | "fr-FR";

const SUPPORTED_LOCALES: readonly SupportedLocale[] = [
  "pt-BR",
  "en-US",
  "es-419",
  "fr-FR",
];

export const defaultLocale: SupportedLocale = "pt-BR";

const FALLBACK_CHAIN: Record<SupportedLocale, readonly SupportedLocale[]> = {
  "pt-BR": ["pt-BR"],
  "en-US": ["en-US", "pt-BR"],
  "es-419": ["es-419", "en-US", "pt-BR"],
  "fr-FR": ["fr-FR", "en-US", "pt-BR"],
};

export function isSupportedLocale(value: unknown): value is SupportedLocale {
  return (
    typeof value === "string" &&
    (SUPPORTED_LOCALES as readonly string[]).includes(value)
  );
}

export function getFallbackChain(locale?: string): SupportedLocale[] {
  if (!isSupportedLocale(locale)) {
    return [...FALLBACK_CHAIN[defaultLocale]];
  }
  return [...FALLBACK_CHAIN[locale]];
}
