// F4.0a - Modelo minimo de erro estruturado para o client HTTP.
//
// Objetivo: deixar de montar erro cru ad hoc. Cada caminho de erro
// (HTTP non-ok, SSE `type: error`, falha de rede) constroi um APIError
// tipado e a UI converte para texto via translateError() em um unico lugar.
// Onda 5 do backend passa a emitir `message_code` consistente; ate la,
// temos `serverMessage` / `reason` como fallback.
//
// Esta classe e usada APENAS em lib/api.ts nesta rodada. F4.0b/F4.0c
// estendem para lib/auth.ts e lib/conversations.ts.

export type APIErrorSource = "http" | "sse" | "network" | "parse" | "unknown";

export interface APIErrorInit {
  /** HTTP status quando aplicavel. */
  status?: number;
  /** Codigo curto do backend (ex.: "invalid_json", "user_not_found"). */
  code?: string;
  /** Chave traduzivel do backend (ex.: "errors.auth.invalid_json"). */
  messageCode?: string;
  /**
   * Texto cru do servidor quando nao houve `message_code` ou a resposta
   * veio como string simples (pre-Onda 5).
   */
  serverMessage?: string;
  /** Motivo semantico extra (ex.: "guest_limit", "daily_limit"). */
  reason?: string;
  /** De onde o erro veio no pipeline (HTTP / SSE / rede / parse). */
  source?: APIErrorSource;
  /** Causa original preservada para debug (ex.: Error de rede). */
  cause?: unknown;
}

export class APIError extends Error {
  readonly status?: number;
  readonly code?: string;
  readonly messageCode?: string;
  readonly serverMessage?: string;
  readonly reason?: string;
  readonly source: APIErrorSource;

  constructor(init: APIErrorInit) {
    const base =
      init.messageCode ??
      init.code ??
      init.serverMessage ??
      (typeof init.status === "number" ? `HTTP ${init.status}` : "api_error");
    super(base);
    this.name = "APIError";
    this.status = init.status;
    this.code = init.code;
    this.messageCode = init.messageCode;
    this.serverMessage = init.serverMessage;
    this.reason = init.reason;
    this.source = init.source ?? "unknown";
    if (init.cause !== undefined) {
      (this as { cause?: unknown }).cause = init.cause;
    }
  }
}

export function isAPIError(value: unknown): value is APIError {
  return value instanceof APIError;
}

/**
 * Tenta extrair APIError de um body JSON do backend (formato Onda 5-like):
 *   { error, message_code, reason, message }
 * Retorna null se o body nao for parseavel ou nao for objeto. Caller
 * decide se cai para `serverMessage` cru.
 */
export function parseApiErrorBody(
  raw: string,
  context: { status?: number; source?: APIErrorSource },
): APIError | null {
  const trimmed = raw?.trim?.() ?? "";
  if (!trimmed) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return null;
  }
  const obj = parsed as Record<string, unknown>;
  const code = typeof obj.error === "string" ? obj.error : undefined;
  const messageCode =
    typeof obj.message_code === "string" ? obj.message_code : undefined;
  const reason = typeof obj.reason === "string" ? obj.reason : undefined;
  const serverMessage =
    typeof obj.message === "string"
      ? obj.message
      : typeof obj.error === "string" && !messageCode
        ? obj.error
        : undefined;

  if (!code && !messageCode && !reason && !serverMessage) return null;

  return new APIError({
    status: context.status,
    source: context.source,
    code,
    messageCode,
    reason,
    serverMessage,
  });
}
