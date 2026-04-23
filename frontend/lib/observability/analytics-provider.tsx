"use client";

// F11.1 + F11.3 + F11.4 - Provider unico que mantem as tags de
// locale/market em sincronia com `LocaleContext`.
//
// F11 CORRETIVO:
//   - A inicializacao dos SDKs (`@sentry/browser` e `posthog-js`) NAO vive
//     mais dentro de `useEffect`. Ela acontece no module-eval dos arquivos
//     `lib/observability/sentry.ts` e `lib/observability/posthog.ts`, ou
//     seja, quando este provider e importado pelo client (antes do
//     primeiro render do componente). Isso elimina a race em que o
//     primeiro `translation_missing_key` disparava antes do init.
//   - O registro de contexto (`locale` / `market_country`) e feito de
//     forma sincrona no corpo do render, nao em `useEffect`. Assim o
//     primeiro `$pageview` manual (emitido dentro de `registerLocaleContext`)
//     ja sai com o contexto correto.
//
// Render continua seguro porque:
//   - `registerLocaleContext` e no-op quando `posthog` nao esta inicializado
//     (ex: env ausente). Nao lanca, nao emite.
//   - `setSentryLocaleTags` tambem e no-op sem Sentry inicializado.

import { useRef } from "react";

import { useLocaleContext } from "@/lib/i18n/locale-context";

import { registerLocaleContext } from "./posthog";
import { setSentryLocaleTags } from "./sentry";

export function AnalyticsProvider({ children }: { children: React.ReactNode }) {
  const { uiLocale, marketCountry } = useLocaleContext();
  const lastContextRef = useRef<string>("");

  // F11 CORRETIVO: sync sincrono, antes do primeiro effect/pageview.
  // Evita race entre render inicial e eventos tipo `translation_missing_key`
  // que podem disparar durante o proprio render.
  const key = `${uiLocale}|${marketCountry}`;
  if (lastContextRef.current !== key) {
    lastContextRef.current = key;
    // `registerLocaleContext` ja dispara `$pageview` manual uma unica vez
    // (primeiro registro). Subsequent atualizacoes de locale apenas refazem
    // `register()`; `$pageview` nao repete.
    registerLocaleContext(uiLocale, marketCountry);
    setSentryLocaleTags(uiLocale, marketCountry);
  }

  return <>{children}</>;
}
