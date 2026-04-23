"use client";

// F11.4 - Handler client-side de erros do next-intl.
//
// Passado ao `NextIntlClientProvider` via prop `onError`. Quando uma chave
// nao e resolvida (MISSING_MESSAGE), captura o evento `translation_missing_key`
// no PostHog com o namespace/chave faltante e o locale ativo. Erros de outros
// tipos (ex: MessageFormat syntax) sao ignorados aqui para nao poluir o feed
// de i18n: eles sao bugs de codigo, nao regressao de traducao.

import type { IntlError } from "next-intl";

import { capture } from "./posthog";

export function handleIntlError(error: IntlError): void {
  try {
    // `IntlError.code === "MISSING_MESSAGE"` indica chave faltando no
    // bundle do locale ativo E em toda a fallback chain.
    if (error.code === "MISSING_MESSAGE") {
      capture("translation_missing_key", {
        message: error.message,
        // `IntlError` nao expoe `originalMessage`/chave de forma estavel
        // entre minors; seguimos com a mensagem textual para MVP.
      });
    }
  } catch {
    // silencioso - telemetria nunca quebra render
  }
}
