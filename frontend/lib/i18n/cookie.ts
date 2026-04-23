// F2.9a/F2.9b - Helpers minimos de cookie de preferencia de locale
// (client-only).
//
// Dois cookies trabalhando em par:
//   wg_locale_choice     -> AppLocale Tier 1 (escolha manual do usuario)
//   wg_locale_choice_at  -> ms epoch da ultima escrita (prova de recencia)
//
// TTL fixo de 1 ano em ambos. SameSite=Lax para sobreviver navegacoes
// top-level e nao vazar em iframes cross-site. Sem Secure aqui porque o
// cookie e usado tambem em dev (http://localhost). Em producao Vercel ja
// serve HTTPS only por padrao, entao nao perdemos seguranca.
//
// Cookie legado (wg_locale_choice sem timestamp pareado) e tratado como
// "sem prova de recencia": NAO assumir que e mais novo que user.last_login.
//
// NUNCA setar estes cookies do servidor: representam escolha MANUAL do
// usuario e o frontend e a fonte de verdade.

import { isAppLocale, type AppLocale } from "@/i18n/routing";

export const LOCALE_COOKIE_NAME = "wg_locale_choice";
export const LOCALE_COOKIE_AT_NAME = "wg_locale_choice_at";
export const LOCALE_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 365; // 1 ano

function readRawCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const prefix = `${name}=`;
  const found = document.cookie.split("; ").find((row) => row.startsWith(prefix));
  if (!found) return null;
  return decodeURIComponent(found.split("=", 2)[1] ?? "");
}

function writeRawCookie(name: string, value: string): void {
  if (typeof document === "undefined") return;
  document.cookie =
    `${name}=${encodeURIComponent(value)}; ` +
    `Max-Age=${LOCALE_COOKIE_MAX_AGE_SECONDS}; ` +
    `Path=/; ` +
    `SameSite=Lax`;
}

function deleteRawCookie(name: string): void {
  if (typeof document === "undefined") return;
  document.cookie = `${name}=; Max-Age=0; Path=/; SameSite=Lax`;
}

export function readLocaleCookie(): AppLocale | null {
  const value = readRawCookie(LOCALE_COOKIE_NAME);
  return value && isAppLocale(value) ? value : null;
}

/**
 * Le o timestamp pareado (ms epoch). Retorna null quando o cookie nao
 * existe ou tem valor invalido. Cookie legado (sem este pareado) cai aqui
 * e o caller deve tratar como "sem prova de recencia".
 */
export function readLocaleCookieAt(): number | null {
  const raw = readRawCookie(LOCALE_COOKIE_AT_NAME);
  if (!raw) return null;
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0) return null;
  return n;
}

/**
 * Escreve locale + timestamp atomicamente. Se `atMillis` for omitido,
 * usa Date.now(). Garante que cookie e timestamp sempre saem juntos
 * pelo caminho preferencial.
 */
export function writeLocalePreference(
  locale: AppLocale,
  atMillis?: number,
): void {
  if (!isAppLocale(locale)) return;
  const ts =
    typeof atMillis === "number" && Number.isFinite(atMillis) && atMillis > 0
      ? Math.floor(atMillis)
      : Date.now();
  writeRawCookie(LOCALE_COOKIE_NAME, locale);
  writeRawCookie(LOCALE_COOKIE_AT_NAME, String(ts));
}

/** Remove ambos os cookies de uma vez. */
export function clearLocalePreference(): void {
  deleteRawCookie(LOCALE_COOKIE_NAME);
  deleteRawCookie(LOCALE_COOKIE_AT_NAME);
}

/**
 * Compatibilidade F2.9a: callers existentes (locale-context.setUiLocale)
 * continuam usando esta funcao. Agora delega para `writeLocalePreference`
 * e tambem atualiza o timestamp com Date.now() (escolha manual = agora).
 */
export function writeLocaleCookie(locale: AppLocale): void {
  writeLocalePreference(locale, Date.now());
}

/**
 * Compatibilidade F2.9a: agora limpa ambos os cookies.
 */
export function clearLocaleCookie(): void {
  clearLocalePreference();
}
