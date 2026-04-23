import { getToken } from "./auth";
import { APIError, parseApiErrorBody } from "./api-error";
import {
  getOutboundLocaleBodyFields,
  getOutboundLocaleHeaders,
} from "./i18n/outbound";
import {
  toErrorDescriptor,
  type ErrorDescriptor,
} from "./i18n/translateError";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

export function getSessionId(): string {
  let id = sessionStorage.getItem("winegod_session_id");
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem("winegod_session_id", id);
  }
  return id;
}

export function setSessionId(id: string): void {
  sessionStorage.setItem("winegod_session_id", id);
}

export function resetSessionId(): void {
  sessionStorage.removeItem("winegod_session_id");
}

export interface StreamCallbacks {
  onChunk: (text: string) => void;
  onDone: () => void;
  onError: (error: ErrorDescriptor) => void;
  onCreditsExhausted?: (reason: "guest_limit" | "daily_limit") => void;
}

export interface MediaPayload {
  type: "image" | "video" | "pdf";
  base64: string;
  images?: string[];
  previews?: string[];
}

export async function sendMessageStream(
  message: string,
  callbacks: StreamCallbacks,
  media?: MediaPayload
): Promise<void> {
  const { onChunk, onDone, onError, onCreditsExhausted } = callbacks;

  try {
    // F2.9c1: redundancia de locale no body do chat stream. Backend
    // (F2.4b decorator) le primeiro o header X-WG-UI-Locale; o body
    // existe como cinto de seguranca para requests legados/cached.
    const body: Record<string, unknown> = {
      message,
      session_id: getSessionId(),
      ...getOutboundLocaleBodyFields(),
    };
    if (media) {
      if (media.type === "image" && media.images && media.images.length > 0) {
        body.images = media.images;
      } else {
        body[media.type] = media.base64;
      }
    }

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...getOutboundLocaleHeaders(),
    };
    const token = getToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const response = await fetch(`${API_URL}/api/chat/stream`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      // F4.0a: caminho HTTP non-ok. Tenta parsear JSON de erro do backend;
      // se for 429 com reason conhecido, delega para onCreditsExhausted
      // (contrato preservado). Senao, constroi APIError estruturado e
      // converte em texto via translateError.
      const text = await response.text();
      const structured =
        parseApiErrorBody(text, {
          status: response.status,
          source: "http",
        }) ??
        new APIError({
          status: response.status,
          serverMessage: text || undefined,
          source: "http",
        });

      if (
        response.status === 429 &&
        onCreditsExhausted &&
        structured.reason &&
        (structured.reason === "guest_limit" ||
          structured.reason === "daily_limit")
      ) {
        onCreditsExhausted(structured.reason);
        return;
      }

      onError(toErrorDescriptor(structured));
      return;
    }

    const reader = response.body?.getReader();
    if (!reader) {
      onError(
        toErrorDescriptor(
          new APIError({
            source: "network",
            code: "streaming_unsupported",
          }),
        ),
      );
      return;
    }

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;

        try {
          const event = JSON.parse(line.slice(6));

          if (event.type === "text") {
            onChunk(event.content);
          } else if (event.type === "end") {
            onDone();
          } else if (event.type === "error") {
            // F4.0a: event.content pode ser string simples (backend atual
            // emite `{'type':'error','content': str(e)}`) OU objeto/JSON
            // serializado (pos-Onda 5). Parse defensivo em ambos os casos.
            let sseErr: APIError | null = null;
            const rawContent = event.content;
            if (typeof rawContent === "string") {
              sseErr = parseApiErrorBody(rawContent, { source: "sse" });
              if (!sseErr) {
                sseErr = new APIError({
                  source: "sse",
                  serverMessage: rawContent || undefined,
                });
              }
            } else if (rawContent && typeof rawContent === "object") {
              const obj = rawContent as Record<string, unknown>;
              sseErr = new APIError({
                source: "sse",
                code: typeof obj.error === "string" ? obj.error : undefined,
                messageCode:
                  typeof obj.message_code === "string"
                    ? obj.message_code
                    : undefined,
                reason:
                  typeof obj.reason === "string" ? obj.reason : undefined,
                serverMessage:
                  typeof obj.message === "string" ? obj.message : undefined,
              });
            } else {
              sseErr = new APIError({ source: "sse" });
            }
            onError(toErrorDescriptor(sseErr));
          }
        } catch {
          // linha SSE incompleta, ignora
        }
      }
    }

    // Se nunca recebeu "end", finaliza mesmo assim
    onDone();
  } catch (err) {
    // F4.0a + H4 F1.3: caminho de rede / excecao inesperada. Preserva a
    // causa original para debug; a UI resolve o texto via useTranslatedError.
    const networkErr = new APIError({
      source: "network",
      code: "network_error",
      serverMessage: err instanceof Error ? err.message : undefined,
      cause: err,
    });
    onError(toErrorDescriptor(networkErr));
  }
}
