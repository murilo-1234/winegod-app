const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

function getSessionId(): string {
  let id = sessionStorage.getItem("winegod_session_id");
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem("winegod_session_id", id);
  }
  return id;
}

export interface StreamCallbacks {
  onChunk: (text: string) => void;
  onDone: () => void;
  onError: (error: string) => void;
}

export async function sendMessageStream(
  message: string,
  callbacks: StreamCallbacks,
  image?: string
): Promise<void> {
  const { onChunk, onDone, onError } = callbacks;

  try {
    const body: Record<string, string> = {
      message,
      session_id: getSessionId(),
    };
    if (image) {
      body.image = image;
    }

    const response = await fetch(`${API_URL}/api/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const err = await response.text();
      onError(`Erro do servidor (${response.status}): ${err}`);
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
        ? `Erro de conexao: ${err.message}`
        : "Erro de conexao com o servidor"
    );
  }
}
