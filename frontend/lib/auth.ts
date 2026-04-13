const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";
const TOKEN_KEY = "winegod_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(jwt: string): void {
  localStorage.setItem(TOKEN_KEY, jwt);
}

export function removeToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export function isLoggedIn(): boolean {
  return !!getToken();
}

export interface UserData {
  id: number;
  name: string;
  email: string;
  picture_url: string;
}

export interface CreditsData {
  used: number;
  remaining: number;
  limit: number;
  type: "user" | "guest";
}

export interface AuthResponse {
  user: UserData;
  credits: { used: number; remaining: number; limit: number };
}

export async function getUser(): Promise<AuthResponse | null> {
  const token = getToken();
  if (!token) return null;

  try {
    const res = await fetch(`${API_URL}/api/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      if (res.status === 401) removeToken();
      return null;
    }
    return res.json();
  } catch {
    return null;
  }
}

export async function getCredits(sessionId?: string): Promise<CreditsData | null> {
  const token = getToken();
  const params = new URLSearchParams();
  if (!token && sessionId) params.set("session_id", sessionId);

  try {
    const res = await fetch(`${API_URL}/api/credits?${params}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function exchangeCodeForToken(
  code: string,
  provider: "google" | "facebook" | "apple" | "microsoft" = "google"
): Promise<{ token: string; user: UserData } | null> {
  try {
    const url = `${API_URL}/api/auth/${provider}/callback`;
    console.log("[auth] exchanging code with:", url);
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    });
    if (!res.ok) {
      const errText = await res.text();
      console.error(`[auth] ${provider} callback failed (${res.status}):`, errText);
      return null;
    }
    return res.json();
  } catch (err) {
    console.error("[auth] network error:", err);
    return null;
  }
}

export function getGoogleLoginUrl(): string {
  return `${API_URL}/api/auth/google`;
}

export function getFacebookLoginUrl(): string {
  return `${API_URL}/api/auth/facebook`;
}

export function getAppleLoginUrl(): string {
  return `${API_URL}/api/auth/apple`;
}

export function getMicrosoftLoginUrl(): string {
  return `${API_URL}/api/auth/microsoft`;
}

export async function logout(): Promise<void> {
  const token = getToken();
  if (token) {
    fetch(`${API_URL}/api/auth/logout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    }).catch(() => {});
  }
  removeToken();
}
