// F2.4 - Routing oficial do next-intl para o WineGod.
//
// Tier 1 fechado: pt-BR (default), en-US, es-419, fr-FR.
// localePrefix: "as-needed" -> URLs em pt-BR nao ganham prefixo; outros
// locales podem aparecer como /en, /es, /fr se middleware/routing futuro
// decidir usar path-prefix (F2.5 / SEO).
// localeDetection: false -> next-intl NAO redireciona automaticamente pelo
// Accept-Language. A decisao de locale segue a precedencia F2.9 (cookie ->
// header geo -> default), aplicada em request.ts.

import { defineRouting } from "next-intl/routing";

export const locales = ["pt-BR", "en-US", "es-419", "fr-FR"] as const;
export type AppLocale = (typeof locales)[number];

export const defaultLocale: AppLocale = "pt-BR";

export const routing = defineRouting({
  locales,
  defaultLocale,
  localePrefix: "as-needed",
  localeDetection: false,
});

export function isAppLocale(value: unknown): value is AppLocale {
  return (
    typeof value === "string" && (locales as readonly string[]).includes(value)
  );
}
