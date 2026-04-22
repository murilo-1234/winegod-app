"use client";

// H4 F1.3 - Camada UI que traduz ErrorDescriptor para string no locale ativo.
//
// Consome next-intl via useTranslations. Complementa a camada pura
// frontend/lib/i18n/translateError.ts (toErrorDescriptor).
//
// Uso:
//   const translate = useTranslatedError();
//   const msg = translate(descriptor);

import { useTranslations } from "next-intl";
import type { ErrorDescriptor } from "./translateError";

// Codes curtos -> path no namespace errors.
// Mantido aqui (nao na camada pura) porque so a UI precisa resolver isso.
const CODE_TO_KEY: Record<string, string> = {
  // auth
  missing_code: "auth.missing_code",
  token_exchange_failed: "auth.token_exchange_failed",
  userinfo_fetch_failed: "auth.userinfo_fetch_failed",
  missing_id_token: "auth.missing_id_token",
  missing_email: "auth.missing_email",
  unauthorized: "auth.unauthorized",
  user_not_found: "auth.user_not_found",
  invalid_json: "auth.invalid_json",
  missing_preferences: "auth.missing_preferences",
  invalid_preferences: "auth.invalid_preferences",
  no_preferences_fields: "auth.no_preferences_fields",
  unknown_preference_field: "auth.unknown_preference_field",
  invalid_ui_locale: "auth.invalid_ui_locale",
  invalid_market_country: "auth.invalid_market_country",
  invalid_currency_override: "auth.invalid_currency_override",
  // chat
  missing_message: "chat.missing_message",
  baco_model_failed: "chat.baco_model_failed",
  // conversations
  conversation_not_found: "conversations.conversation_not_found",
  access_denied: "conversations.access_denied",
  missing_id: "conversations.missing_id",
  invalid_messages: "conversations.invalid_messages",
  duplicate_id: "conversations.duplicate_id",
  invalid_saved: "conversations.invalid_saved",
  invalid_limit: "conversations.invalid_limit",
  invalid_offset: "conversations.invalid_offset",
  // frontend-origin
  network_error: "network_error",
  streaming_unsupported: "streaming_unsupported",
};

function stripErrorsPrefix(key: string): string {
  return key.startsWith("errors.") ? key.slice("errors.".length) : key;
}

export function useTranslatedError(): (d: ErrorDescriptor) => string {
  const t = useTranslations("errors");

  return (d: ErrorDescriptor): string => {
    switch (d.kind) {
      case "messageCode":
        return t(stripErrorsPrefix(d.messageCode));
      case "code": {
        const key = CODE_TO_KEY[d.code] ?? "generic.fallback";
        return t(key);
      }
      case "reason":
        return t(`reasons.${d.reason}`);
      case "raw":
        return d.text;
      case "status":
        return `${t("generic.fallback")} (HTTP ${d.status})`;
      case "generic":
        return d.note
          ? `${t("generic.fallback")} (${d.note})`
          : t("generic.fallback");
    }
  };
}
