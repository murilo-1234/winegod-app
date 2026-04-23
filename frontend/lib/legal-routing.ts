export const LEGAL_DOCS = [
  "privacy",
  "terms",
  "data-deletion",
  "cookies",
] as const;

export type LegalDoc = (typeof LEGAL_DOCS)[number];
export type LegalLocale = "pt-BR" | "en-US" | "es-419" | "fr-FR";
export type LegalCountry = "BR" | "DEFAULT";

type LegalCell = {
  country: LegalCountry;
  lang: LegalLocale;
};

const LEGAL_LOCALES: readonly LegalLocale[] = [
  "pt-BR",
  "en-US",
  "es-419",
  "fr-FR",
] as const;

const LEGAL_CELL_BY_LOCALE: Record<LegalLocale, LegalCell> = {
  "pt-BR": { country: "BR", lang: "pt-BR" },
  "en-US": { country: "DEFAULT", lang: "en-US" },
  "es-419": { country: "DEFAULT", lang: "es-419" },
  "fr-FR": { country: "DEFAULT", lang: "fr-FR" },
};

export const PUBLISHED_LEGAL_MATRIX: Record<
  LegalCountry,
  Partial<Record<LegalLocale, readonly LegalDoc[]>>
> = {
  BR: {
    "pt-BR": LEGAL_DOCS,
  },
  DEFAULT: {
    "en-US": LEGAL_DOCS,
    "es-419": LEGAL_DOCS,
    "fr-FR": LEGAL_DOCS,
  },
};

export function isLegalDoc(value: string): value is LegalDoc {
  return (LEGAL_DOCS as readonly string[]).includes(value);
}

export function isLegalLocale(value: unknown): value is LegalLocale {
  return (
    typeof value === "string" &&
    (LEGAL_LOCALES as readonly string[]).includes(value)
  );
}

export function isLegalCountry(value: unknown): value is LegalCountry {
  return value === "BR" || value === "DEFAULT";
}

export function normalizeLegalLocale(value: unknown): LegalLocale {
  return isLegalLocale(value) ? value : "en-US";
}

export function resolveLegalCell(value: unknown): LegalCell {
  return LEGAL_CELL_BY_LOCALE[normalizeLegalLocale(value)];
}

export function buildLegalPath(locale: unknown, doc: LegalDoc): string {
  const cell = resolveLegalCell(locale);
  return `/legal/${cell.country}/${cell.lang}/${doc}`;
}

export function isPublishedLegalDoc(
  country: unknown,
  lang: unknown,
  doc: LegalDoc,
): boolean {
  if (!isLegalCountry(country) || !isLegalLocale(lang)) {
    return false;
  }
  return PUBLISHED_LEGAL_MATRIX[country]?.[lang]?.includes(doc) ?? false;
}
