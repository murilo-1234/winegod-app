// F11.3 + F11.4 - Inicializacao PostHog browser-side.
//
// F11 CORRETIVO:
//   - bootstrap sincrono no primeiro acesso ao modulo no client (em vez
//     de depender de useEffect tardio)
//   - `capture_pageview: false`: nao delegamos o primeiro $pageview ao
//     posthog-js. Em vez disso, esperamos o `LocaleContext` registrar
//     `locale`/`market_country` e so entao disparamos `$pageview` manual
//     (`capturePageviewOnce()`), garantindo que o primeiro pageview sempre
//     saia com contexto de locale completo
//   - eventos enviados ANTES do init sao bufferizados numa fila (FIFO) e
//     drenados apos init + register; evita perder `translation_missing_key`
//     do primeiro render
//
// Guarded por `NEXT_PUBLIC_POSTHOG_API_KEY`. Sem key, todas as funcoes
// sao no-op silencioso (fila descartada sem erro), build fica verde.

import posthog from "posthog-js";

const DEFAULT_HOST = "https://us.i.posthog.com";

type QueuedEvent = {
  event: string;
  properties: Record<string, unknown>;
};

let initialized = false;
let registeredContext = false;
let pageviewSent = false;
const eventQueue: QueuedEvent[] = [];

function resolveApiKey(): string | null {
  const key = process.env.NEXT_PUBLIC_POSTHOG_API_KEY?.trim();
  return key ? key : null;
}

function doInitialize(): boolean {
  if (initialized) return true;
  if (typeof window === "undefined") return false;
  const apiKey = resolveApiKey();
  if (!apiKey) return false;

  const host = process.env.NEXT_PUBLIC_POSTHOG_HOST?.trim() || DEFAULT_HOST;

  try {
    posthog.init(apiKey, {
      api_host: host,
      // F11 CORRETIVO: pageview automatico desligado. O disparo manual
      // acontece em `capturePageviewOnce()` apos o contexto de locale
      // ter sido registrado.
      capture_pageview: false,
      capture_pageleave: true,
      persistence: "localStorage+cookie",
      disable_session_recording: true,
    });
    initialized = true;
    return true;
  } catch (err) {
    console.warn("[posthog] init_failed", err);
    return false;
  }
}

function drainQueue(): void {
  if (!initialized) return;
  while (eventQueue.length > 0) {
    const item = eventQueue.shift();
    if (!item) break;
    try {
      posthog.capture(item.event, item.properties);
    } catch {
      // silencioso
    }
  }
}

/**
 * F11.3 - Inicializacao publica. Idempotente. Retorna true se ativou.
 *
 * Seguranca contra race: chamar mais de uma vez e seguro. Drena fila
 * acumulada desde o modulo-eval.
 */
export function initPosthogBrowser(): boolean {
  const ok = doInitialize();
  if (ok) drainQueue();
  return ok;
}

/**
 * F11.4 - Captura um evento. Pode ser chamada ANTES do init: o evento
 * fica em fila e e drenado depois que `initPosthogBrowser()` roda. Quando
 * nao ha API key (env ausente), a fila descarta silenciosamente.
 *
 * Isso elimina a race do primeiro `translation_missing_key`, que pode
 * disparar durante o render inicial antes do `useEffect` do
 * AnalyticsProvider ter rodado.
 */
export function capture(
  event: string,
  properties?: Record<string, unknown>,
): void {
  // Se env nao esta presente, nem enfileira.
  if (!resolveApiKey()) return;

  if (!initialized) {
    eventQueue.push({ event, properties: properties ?? {} });
    return;
  }
  try {
    posthog.capture(event, properties ?? {});
  } catch {
    // silencioso
  }
}

/**
 * F11.3 + F11.4 CORRETIVO - registra contexto de locale como super
 * properties. Idempotente. Emite o primeiro `$pageview` manual apenas
 * APOS registrar o contexto - garante que `locale`/`market_country`
 * estao presentes no `$pageview` inicial do dashboard F11.5.
 */
export function registerLocaleContext(
  locale: string | null,
  marketCountry: string | null,
): void {
  if (!initialized) return;
  try {
    posthog.register({
      locale: locale ?? "unknown",
      market_country: marketCountry ?? "unknown",
    });
    registeredContext = true;
    capturePageviewOnce();
  } catch {
    // silencioso
  }
}

/**
 * F11.4 CORRETIVO - emite o primeiro `$pageview` manual uma unica vez,
 * somente depois que `registerLocaleContext` populou as super properties.
 * Chamadas subsequentes sao no-op.
 */
export function capturePageviewOnce(): void {
  if (pageviewSent) return;
  if (!initialized || !registeredContext) return;
  if (typeof window === "undefined") return;
  try {
    posthog.capture("$pageview", {
      $current_url: window.location.href,
    });
    pageviewSent = true;
  } catch {
    // silencioso
  }
}

export function isPosthogReady(): boolean {
  return initialized;
}

/**
 * F11 CORRETIVO - reset de estado interno para testes. Nao usar em
 * runtime de producao.
 */
export function __resetPosthogForTests(): void {
  initialized = false;
  registeredContext = false;
  pageviewSent = false;
  eventQueue.length = 0;
}

export function __getQueueSizeForTests(): number {
  return eventQueue.length;
}

// F11 CORRETIVO - bootstrap sincrono no primeiro eval deste modulo no
// client. Em Next.js App Router, este modulo so e avaliado client-side
// quando um "use client" component o importa (ex: AnalyticsProvider).
// O ponto crucial e que isso acontece ANTES do primeiro useEffect, o que
// elimina a janela onde `translation_missing_key` do primeiro render se
// perdia. Sem NEXT_PUBLIC_POSTHOG_API_KEY, `doInitialize()` e no-op.
if (typeof window !== "undefined") {
  doInitialize();
}
