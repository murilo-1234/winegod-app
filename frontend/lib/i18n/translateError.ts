// F4.0a + F5.5 + H4 F1.3 - Mapper puro de erro -> ErrorDescriptor.
//
// Esta camada NAO depende de React nem de next-intl. Funciona em qualquer
// contexto (browser, edge, server). Retorna um descriptor estrutural que
// a camada UI (frontend/lib/i18n/useTranslatedError.ts) traduz para string
// no locale ativo.
//
// Cascata de resolucao:
//   1. Se messageCode conhecido -> { kind: "messageCode", ... }
//   2. Senao, se code conhecido -> { kind: "code", ... }
//   3. Senao, se reason conhecido -> { kind: "reason", ... }
//   4. Senao, se serverMessage truthy -> { kind: "raw", ... }
//   5. Senao, se status numerico -> { kind: "status", ... }
//   6. Senao -> { kind: "generic" }

import { APIError } from "../api-error";

export type ErrorDescriptor =
  | { kind: "messageCode"; messageCode: string }
  | { kind: "code"; code: string }
  | { kind: "reason"; reason: string }
  | { kind: "raw"; text: string }
  | { kind: "status"; status: number }
  | { kind: "generic"; note?: string };

// Whitelist de message codes conhecidos. Mantida como set para O(1) lookup.
const KNOWN_MESSAGE_CODES = new Set<string>([
  "errors.auth.missing_code",
  "errors.auth.token_exchange_failed",
  "errors.auth.userinfo_fetch_failed",
  "errors.auth.missing_id_token",
  "errors.auth.missing_email",
  "errors.auth.unauthorized",
  "errors.auth.user_not_found",
  "errors.auth.invalid_json",
  "errors.auth.missing_preferences",
  "errors.auth.invalid_preferences",
  "errors.auth.no_preferences_fields",
  "errors.auth.unknown_preference_field",
  "errors.auth.invalid_ui_locale",
  "errors.auth.invalid_market_country",
  "errors.auth.invalid_currency_override",
  "errors.chat.missing_message",
  "errors.chat.baco_model_failed",
  "errors.conversations.unauthorized",
  "errors.conversations.invalid_limit",
  "errors.conversations.invalid_offset",
  "errors.conversations.conversation_not_found",
  "errors.conversations.access_denied",
  "errors.conversations.missing_id",
  "errors.conversations.invalid_messages",
  "errors.conversations.duplicate_id",
  "errors.conversations.invalid_saved",
]);

// Codes curtos (sem prefixo de dominio) mapeiam para a mesma i18n key.
// A camada UI (useTranslatedError) traduz codes para messageCode equivalente.
const KNOWN_CODES = new Set<string>([
  "missing_code",
  "token_exchange_failed",
  "userinfo_fetch_failed",
  "missing_id_token",
  "missing_email",
  "unauthorized",
  "user_not_found",
  "invalid_json",
  "missing_preferences",
  "invalid_preferences",
  "no_preferences_fields",
  "unknown_preference_field",
  "invalid_ui_locale",
  "invalid_market_country",
  "invalid_currency_override",
  "missing_message",
  "baco_model_failed",
  "conversation_not_found",
  "access_denied",
  "missing_id",
  "invalid_messages",
  "duplicate_id",
  "invalid_saved",
  "invalid_limit",
  "invalid_offset",
  // Codes emitidos pelo proprio frontend em api.ts.
  "network_error",
  "streaming_unsupported",
]);

const KNOWN_REASONS = new Set<string>(["guest_limit", "daily_limit"]);

export function toErrorDescriptor(err: unknown): ErrorDescriptor {
  if (err instanceof APIError) {
    if (err.messageCode && KNOWN_MESSAGE_CODES.has(err.messageCode)) {
      return { kind: "messageCode", messageCode: err.messageCode };
    }
    if (err.code && KNOWN_CODES.has(err.code)) {
      return { kind: "code", code: err.code };
    }
    if (err.reason && KNOWN_REASONS.has(err.reason)) {
      return { kind: "reason", reason: err.reason };
    }
    if (err.serverMessage && err.serverMessage.trim()) {
      return { kind: "raw", text: err.serverMessage.trim() };
    }
    if (typeof err.status === "number") {
      return { kind: "status", status: err.status };
    }
    return { kind: "generic" };
  }

  if (err instanceof Error && err.message) {
    return { kind: "generic", note: err.message };
  }

  if (typeof err === "string" && err.trim()) {
    return { kind: "raw", text: err.trim() };
  }

  return { kind: "generic" };
}
