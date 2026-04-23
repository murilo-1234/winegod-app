// F11.1 - Inicializacao Sentry browser-side.
//
// Guarded por `NEXT_PUBLIC_SENTRY_DSN`: se a env nao esta setada, a chamada
// vira no-op silenciosa. Permite dev local sem credenciais e build verde
// antes do operator prover o DSN no Vercel.
//
// Arquitetura: um unico point-of-init chamado no AnalyticsProvider
// (`lib/observability/analytics-provider.tsx`). Nao ha sentry.client.config
// nem sentry.server.config; Next.js App Router permite init via componente
// client, o que e o menor surface possivel para Rally 5 (F11.1). Server-side
// errors do frontend ficarao sem Sentry nesta rodada - documentado em
// "pendencias" do resultado.

import * as Sentry from "@sentry/browser";

let initialized = false;

function doInit(): boolean {
  if (typeof window === "undefined") return false;
  if (initialized) return true;

  const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN?.trim();
  if (!dsn) return false;

  try {
    Sentry.init({
      dsn,
      environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT ?? undefined,
      release: process.env.NEXT_PUBLIC_SENTRY_RELEASE ?? undefined,
      tracesSampleRate: 0,
      sendDefaultPii: false,
    });
    initialized = true;
    return true;
  } catch (err) {
    console.warn("[sentry] init_failed", err);
    return false;
  }
}

export function initSentryBrowser(): boolean {
  return doInit();
}

// F11 CORRETIVO - bootstrap sincrono no primeiro eval client. Alinha com
// PostHog: erros que aconteçam durante o primeiro render sao capturados
// mesmo antes de qualquer useEffect rodar.
if (typeof window !== "undefined") {
  doInit();
}

export function setSentryLocaleTags(
  locale: string | null,
  marketCountry: string | null,
): void {
  if (!initialized) return;
  try {
    Sentry.setTag("locale", locale ?? "unknown");
    Sentry.setTag("market_country", marketCountry ?? "unknown");
  } catch {
    // silencioso
  }
}
