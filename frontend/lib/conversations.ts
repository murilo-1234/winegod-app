import { getToken } from "./auth";

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

export async function fetchConversations(): Promise<ConversationSummary[]> {
  const token = getToken();
  if (!token) return [];
  const res = await fetch(`${API_URL}/api/conversations?limit=30`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function searchConversations(
  query: string
): Promise<ConversationSummary[]> {
  const token = getToken();
  if (!token) return [];
  const res = await fetch(
    `${API_URL}/api/conversations?q=${encodeURIComponent(query)}&limit=10`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function fetchSavedConversations(): Promise<ConversationSummary[]> {
  const token = getToken();
  if (!token) return [];
  const res = await fetch(`${API_URL}/api/conversations?saved=true&limit=50`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

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
      },
      body: JSON.stringify({ id, title, messages }),
    });
    // 201 = created, 409 = already exists (idempotent on retry/refresh)
    return res.status === 201 || res.status === 409;
  } catch {
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
        },
        body: JSON.stringify({ saved }),
      }
    );
    return res.ok;
  } catch {
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
      { headers: { Authorization: `Bearer ${token}` } }
    );
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}
