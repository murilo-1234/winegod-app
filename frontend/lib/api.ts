import { getToken } from "./auth";

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
  onError: (error: string) => void;
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
    const body: Record<string, unknown> = {
      message,
      session_id: getSessionId(),
    };
    if (media) {
      if (media.type === "image" && media.images && media.images.length > 0) {
        body.images = media.images;
      } else {
        body[media.type] = media.base64;
      }
    }

    const headers: Record<string, string> = { "Content-Type": "application/json" };
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
      const text = await response.text();
      if (response.status === 429 && onCreditsExhausted) {
        try {
          const body = JSON.parse(text);
          if (body.reason) {
            onCreditsExhausted(body.reason);
            return;
          }
        } catch {}
      }
      onError(`Erro do servidor (${response.status}): ${text}`);
      return;
    }

    const reader = response.body?.getReader();
    if (!reader) {
      onError("Navegador nao suporta streaming");
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
            onError(event.content);
          }
        } catch {
          // linha SSE incompleta, ignora
        }
      }
    }

    // Se nunca recebeu "end", finaliza mesmo assim
    onDone();
  } catch (err) {
    onError(
      err instanceof Error
        ? `Erro de conexão: ${err.message}`
        : "Erro de conexão com o servidor"
    );
  }
}
