// F2.6 - Formatters i18n puros baseados em Intl.* nativo.
//
// Este arquivo NAO usa "use client": pode ser importado tanto em client
// quanto em server components. Sem dependencia externa.
//
// Locales suportados: pt-BR, en-US, es-419, fr-FR.
// Locale invalido cai em pt-BR sem lancar erro.

const SUPPORTED_LOCALES = ["pt-BR", "en-US", "es-419", "fr-FR"] as const;
type SupportedLocale = (typeof SUPPORTED_LOCALES)[number];

const DEFAULT_LOCALE: SupportedLocale = "pt-BR";

const CURRENCY_BY_LOCALE: Record<SupportedLocale, string> = {
  "pt-BR": "BRL",
  "en-US": "USD",
  "es-419": "MXN",
  "fr-FR": "EUR",
};

function isSupportedLocale(value: unknown): value is SupportedLocale {
  return (
    typeof value === "string" &&
    (SUPPORTED_LOCALES as readonly string[]).includes(value)
  );
}

function resolveLocale(locale?: string): SupportedLocale {
  return isSupportedLocale(locale) ? locale : DEFAULT_LOCALE;
}

function defaultCurrencyFor(locale: SupportedLocale): string {
  return CURRENCY_BY_LOCALE[locale];
}

export function formatCurrency(
  value: number,
  locale?: string,
  currency?: string,
  options?: Intl.NumberFormatOptions,
): string {
  const resolved = resolveLocale(locale);
  const finalCurrency =
    typeof currency === "string" && currency.length === 3
      ? currency.toUpperCase()
      : defaultCurrencyFor(resolved);
  const finalOptions: Intl.NumberFormatOptions = {
    style: "currency",
    currency: finalCurrency,
    ...(options ?? {}),
  };
  return new Intl.NumberFormat(resolved, finalOptions).format(value);
}

export function formatDate(
  value: Date | string | number,
  locale?: string,
  options?: Intl.DateTimeFormatOptions,
): string {
  const resolved = resolveLocale(locale);
  const date =
    value instanceof Date
      ? value
      : typeof value === "number"
        ? new Date(value)
        : new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const finalOptions: Intl.DateTimeFormatOptions = options ?? {
    dateStyle: "medium",
  };
  return new Intl.DateTimeFormat(resolved, finalOptions).format(date);
}

export function formatNumber(
  value: number,
  locale?: string,
  options?: Intl.NumberFormatOptions,
): string {
  const resolved = resolveLocale(locale);
  return new Intl.NumberFormat(resolved, options).format(value);
}

export function formatRelativeTime(
  value: number,
  unit: Intl.RelativeTimeFormatUnit,
  locale?: string,
  options?: Intl.RelativeTimeFormatOptions,
): string {
  const resolved = resolveLocale(locale);
  const finalOptions: Intl.RelativeTimeFormatOptions = {
    numeric: "auto",
    ...(options ?? {}),
  };
  return new Intl.RelativeTimeFormat(resolved, finalOptions).format(value, unit);
}
