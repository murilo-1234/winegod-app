import { getToken } from "./auth";
import {
  APIError,
  type APIErrorSource,
  parseApiErrorBody,
} from "./api-error";
import { getOutboundLocaleHeaders } from "./i18n/outbound";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

export interface ConversationSummary {
  id: string;
  title: string | null;
  created_at: string | null;
  updated_at: string | null;
  is_saved?: boolean;
  saved_at?: string | null;
}

export interface ConversationFull {
  id: string;
  title: string | null;
  messages: { role: "user" | "assistant"; content: string }[];
  created_at: string | null;
  updated_at: string | null;
  is_saved?: boolean;
  saved_at?: string | null;
}

// F4.0c - Slot leve de erro recente para o dominio "conversations".
// Mantido separado de `lastAuthError` (F4.0b) para nao misturar dominios:
// um erro de listagem de conversas nao deve contaminar o fluxo de OAuth
// callback e vice-versa.
let lastConversationsError: APIError | null = null;

function setLastConversationsError(err: APIError | null): void {
  lastConversationsError = err;
}

export function getLastConversationsError(): APIError | null {
  return lastConversationsError;
}

export function clearLastConversationsError(): void {
  lastConversationsError = null;
}

async function apiErrorFromResponse(
  res: Response,
  source: APIErrorSource = "http",
): Promise<APIError> {
  let text = "";
  try {
    text = await res.text();
  } catch {
    // body ilegivel: prossegue com string vazia; APIError ainda tem status.
  }
  const parsed = text
    ? parseApiErrorBody(text, { status: res.status, source })
    : null;
  if (parsed) return parsed;
  return new APIError({
    status: res.status,
    serverMessage: text || undefined,
    source,
  });
}

function apiErrorFromNetwork(err: unknown): APIError {
  return new APIError({
    source: "network",
    code: "network_error",
    serverMessage: err instanceof Error ? err.message : undefined,
    cause: err,
  });
}

// -----------------------------------------------------------------------
// List functions: retornam array, PODEM lancar. Callers atuais (Sidebar,
// Favoritos, SearchModal) ja usam try/catch; preservar esse contrato e
// trocar `throw new Error("HTTP N")` por `throw APIError(...)` estruturado.
// -----------------------------------------------------------------------

export async function fetchConversations(): Promise<ConversationSummary[]> {
  const token = getToken();
  if (!token) return [];
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/conversations?limit=30`, {
      headers: {
        Authorization: `Bearer ${token}`,
        ...getOutboundLocaleHeaders(),
      },
      cache: "no-store",
    });
  } catch (err) {
    const netErr = apiErrorFromNetwork(err);
    setLastConversationsError(netErr);
    throw netErr;
  }
  if (!res.ok) {
    const err = await apiErrorFromResponse(res);
    setLastConversationsError(err);
    throw err;
  }
  try {
    const data = (await res.json()) as ConversationSummary[];
    clearLastConversationsError();
    return data;
  } catch (parseErr) {
    const err = new APIError({
      status: res.status,
      source: "parse",
      code: "invalid_response_json",
      cause: parseErr,
    });
    setLastConversationsError(err);
    throw err;
  }
}

export async function searchConversations(
  query: string
): Promise<ConversationSummary[]> {
  const token = getToken();
  if (!token) return [];
  let res: Response;
  try {
    res = await fetch(
      `${API_URL}/api/conversations?q=${encodeURIComponent(query)}&limit=10`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          ...getOutboundLocaleHeaders(),
        },
        cache: "no-store",
      }
    );
  } catch (err) {
    const netErr = apiErrorFromNetwork(err);
    setLastConversationsError(netErr);
    throw netErr;
  }
  if (!res.ok) {
    const err = await apiErrorFromResponse(res);
    setLastConversationsError(err);
    throw err;
  }
  try {
    const data = (await res.json()) as ConversationSummary[];
    clearLastConversationsError();
    return data;
  } catch (parseErr) {
    const err = new APIError({
      status: res.status,
      source: "parse",
      code: "invalid_response_json",
      cause: parseErr,
    });
    setLastConversationsError(err);
    throw err;
  }
}

export async function fetchSavedConversations(): Promise<ConversationSummary[]> {
  const token = getToken();
  if (!token) return [];
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/conversations?saved=true&limit=50`, {
      headers: {
        Authorization: `Bearer ${token}`,
        ...getOutboundLocaleHeaders(),
      },
      cache: "no-store",
    });
  } catch (err) {
    const netErr = apiErrorFromNetwork(err);
    setLastConversationsError(netErr);
    throw netErr;
  }
  if (!res.ok) {
    const err = await apiErrorFromResponse(res);
    setLastConversationsError(err);
    throw err;
  }
  try {
    const data = (await res.json()) as ConversationSummary[];
    clearLastConversationsError();
    return data;
  } catch (parseErr) {
    const err = new APIError({
      status: res.status,
      source: "parse",
      code: "invalid_response_json",
      cause: parseErr,
    });
    setLastConversationsError(err);
    throw err;
  }
}

// -----------------------------------------------------------------------
// Boolean / nullable functions: NAO lancam. Contratos preservados.
// -----------------------------------------------------------------------

export async function migrateGuestConversation(
  id: string,
  title: string,
  messages: { role: string; content: string }[]
): Promise<boolean> {
  const token = getToken();
  if (!token) return false;
  try {
    const res = await fetch(`${API_URL}/api/conversations`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
        ...getOutboundLocaleHeaders(),
      },
      body: JSON.stringify({ id, title, messages }),
    });
    // 201 = created, 409 = already exists (idempotent on retry/refresh)
    if (res.status === 201 || res.status === 409) {
      clearLastConversationsError();
      return true;
    }
    setLastConversationsError(await apiErrorFromResponse(res));
    return false;
  } catch (err) {
    setLastConversationsError(apiErrorFromNetwork(err));
    return false;
  }
}

export async function updateConversationSaved(
  id: string,
  saved: boolean
): Promise<boolean> {
  const token = getToken();
  if (!token) return false;
  try {
    const res = await fetch(
      `${API_URL}/api/conversations/${encodeURIComponent(id)}/saved`,
      {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
          ...getOutboundLocaleHeaders(),
        },
        body: JSON.stringify({ saved }),
      }
    );
    if (res.ok) {
      clearLastConversationsError();
      return true;
    }
    setLastConversationsError(await apiErrorFromResponse(res));
    return false;
  } catch (err) {
    setLastConversationsError(apiErrorFromNetwork(err));
    return false;
  }
}

export async function fetchConversation(
  id: string
): Promise<ConversationFull | null> {
  const token = getToken();
  if (!token) return null;
  try {
    const res = await fetch(
      `${API_URL}/api/conversations/${encodeURIComponent(id)}`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          ...getOutboundLocaleHeaders(),
        },
        cache: "no-store",
      }
    );
    if (!res.ok) {
      setLastConversationsError(await apiErrorFromResponse(res));
      return null;
    }
    try {
      const data = (await res.json()) as ConversationFull;
      clearLastConversationsError();
      return data;
    } catch (parseErr) {
      setLastConversationsError(
        new APIError({
          status: res.status,
          source: "parse",
          code: "invalid_response_json",
          cause: parseErr,
        }),
      );
      return null;
    }
  } catch (err) {
    setLastConversationsError(apiErrorFromNetwork(err));
    return null;
  }
}
