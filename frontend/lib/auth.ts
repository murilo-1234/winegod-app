import { isAppLocale, type AppLocale } from "@/i18n/routing";
import {
  readLocaleCookie,
  readLocaleCookieAt,
  writeLocalePreference,
} from "@/lib/i18n/cookie";
import { getOutboundLocaleHeaders } from "@/lib/i18n/outbound";
import {
  APIError,
  type APIErrorSource,
  parseApiErrorBody,
} from "@/lib/api-error";

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
  provider?: string;
  last_login?: string;
}

export interface CreditsData {
  used: number;
  remaining: number;
  limit: number;
  type: "user" | "guest";
}

// F1.7 / F2.9a: backend agora retorna `preferences` no top-level de
// /api/auth/me. Tipado aqui apenas para que consumidores futuros (sync
// pos-login em F2.9b) possam ler sem cast. Nenhum consumidor usa ainda.
export interface UserPreferences {
  ui_locale: string;
  market_country: string;
  currency_override: string | null;
}

export interface AuthResponse {
  user: UserData;
  credits: { used: number; remaining: number; limit: number };
  preferences?: UserPreferences;
}

// F4.0b - Slot leve de erro recente. Cada funcao publica de auth grava
// APIError estruturado em caso de falha e limpa em sucesso. Contratos
// publicos (null/false/void) preservados; o erro fica disponivel via
// getLastAuthError() para callers que queiram traduzir (ex.: tela de
// callback OAuth). Slot global em module scope: simples, sem RxJS nem
// observable; evita mudar assinaturas.
let lastAuthError: APIError | null = null;

function setLastAuthError(err: APIError | null): void {
  lastAuthError = err;
}

export function getLastAuthError(): APIError | null {
  return lastAuthError;
}

export function clearLastAuthError(): void {
  lastAuthError = null;
}

/**
 * F4.0b - Tenta transformar uma Response em APIError estruturado. Le
 * body como texto, roda `parseApiErrorBody`; se nao houver JSON util,
 * cai para APIError com serverMessage cru. Nunca lanca.
 */
async function apiErrorFromResponse(
  res: Response,
  source: APIErrorSource = "http",
): Promise<APIError> {
  let text = "";
  try {
    text = await res.text();
  } catch {
    // Body ilegivel: prossegue com vazio; APIError usa status/fallback.
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

/**
 * F2.9b - Helper minimo do PATCH /api/auth/me/preferences. Retorna o
 * objeto preferences atualizado pelo backend ou null em qualquer falha
 * (rede, 4xx/5xx, JSON invalido). Nunca lanca.
 */
export async function patchUserPreferences(
  changes: Partial<UserPreferences>,
): Promise<UserPreferences | null> {
  const token = getToken();
  if (!token) {
    setLastAuthError(
      new APIError({
        source: "unknown",
        code: "no_token",
        serverMessage: "No token",
      }),
    );
    return null;
  }
  try {
    const res = await fetch(`${API_URL}/api/auth/me/preferences`, {
      method: "PATCH",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        ...getOutboundLocaleHeaders(),
      },
      body: JSON.stringify({ preferences: changes }),
    });
    if (!res.ok) {
      setLastAuthError(await apiErrorFromResponse(res));
      return null;
    }
    let body: { preferences?: UserPreferences };
    try {
      body = (await res.json()) as { preferences?: UserPreferences };
    } catch (parseErr) {
      setLastAuthError(
        new APIError({
          status: res.status,
          source: "parse",
          code: "invalid_response_json",
          cause: parseErr,
        }),
      );
      return null;
    }
    clearLastAuthError();
    return body?.preferences ?? null;
  } catch (err) {
    setLastAuthError(apiErrorFromNetwork(err));
    return null;
  }
}

/**
 * F2.9b - Parseia `user.last_login` (string ISO ou postgres) em ms epoch.
 * Retorna null se invalido. Aceitar varios formatos protege a sync de
 * regressao se o backend mudar a serializacao no futuro.
 */
function parseTimestampMs(value: unknown): number | null {
  if (typeof value !== "string" || !value) return null;
  const t = new Date(value).getTime();
  return Number.isFinite(t) ? t : null;
}

/**
 * F2.9b - Aplica a regra unica de sync de locale apos /api/auth/me.
 *
 * 1. Sem cookie + backend valido     -> escreve cookie (timestamp = last_login || now).
 * 2. Cookie igual a backend          -> noop.
 * 3. Cookie != backend, cookie tem timestamp confiavel E > last_login
 *    -> PATCH backend com cookie; em sucesso, muta `data.preferences`.
 * 4. Caso contrario (cookie legado sem timestamp, ou cookie nao mais
 *    recente que last_login): backend ganha, reescreve cookie + timestamp.
 *
 * Falha de PATCH nao lanca, nao loop, nao mexe no cookie.
 * Funcao mutates `data` in place quando precisa refletir o resultado do
 * PATCH, sem reatribuir referencia.
 */
async function syncLocalePreferenceAfterAuth(
  data: AuthResponse,
): Promise<void> {
  if (typeof document === "undefined") return; // SSR ou env sem cookie

  const backendLocaleRaw = data.preferences?.ui_locale;
  if (!isAppLocale(backendLocaleRaw)) return; // backend ainda nao expoe (pre-F1.7) ou invalido
  const backendLocale: AppLocale = backendLocaleRaw;

  const cookieLocale = readLocaleCookie();
  const cookieAt = readLocaleCookieAt();
  const lastLoginMs = parseTimestampMs(data.user?.last_login);

  // Caso 1: sem cookie, backend define a preferencia.
  if (!cookieLocale) {
    const stamp = lastLoginMs ?? Date.now();
    writeLocalePreference(backendLocale, stamp);
    return;
  }

  // Caso 2: alinhados, nada a fazer.
  if (cookieLocale === backendLocale) {
    return;
  }

  // Caso 3: cookie tem prova de recencia e e estritamente mais novo -> cookie ganha.
  if (
    cookieAt !== null &&
    lastLoginMs !== null &&
    cookieAt > lastLoginMs
  ) {
    const updated = await patchUserPreferences({ ui_locale: cookieLocale });
    if (updated && isAppLocale(updated.ui_locale)) {
      // Reflete no objeto retornado por getUser() sem trocar referencia.
      data.preferences = {
        ui_locale: updated.ui_locale,
        market_country: updated.market_country,
        currency_override: updated.currency_override,
      };
    }
    // Falha do PATCH: cookie permanece como esta, contrato preservado.
    return;
  }

  // Caso 4: cookie legado sem timestamp confiavel, ou cookie velho ->
  // backend ganha. Reescreve cookie + timestamp.
  const stamp = lastLoginMs ?? Date.now();
  writeLocalePreference(backendLocale, stamp);
}

// F2.9b-fix - Deduplicacao de chamadas concorrentes de getUser().
//
// Problema: paginas como /conta, /plano, /favoritos podem ter mais de um
// caller simultaneo (useAuth + AppShell self-managed). Sem dedupe, isso
// gera dois GET /api/auth/me e, no caso "cookie > backend", DOIS PATCH
// /api/auth/me/preferences concorrentes -- desnecessario e ruim.
//
// Solucao: enquanto houver uma promise em voo para `getUser()` no MESMO
// token, callers concorrentes recebem a MESMA promise. Quando ela termina
// (sucesso ou erro), o slot e limpo. Nao mantemos cache memoizado: a
// proxima chamada apos o termino refaz o fetch normalmente.
//
// Chave = token atual (snapshot no momento da chamada). Se o token
// mudar entre callers, cada um faz sua propria request (sessao diferente).
let inflightGetUserToken: string | null = null;
let inflightGetUserPromise: Promise<AuthResponse | null> | null = null;

async function fetchUserAndSync(token: string): Promise<AuthResponse | null> {
  try {
    const res = await fetch(`${API_URL}/api/auth/me`, {
      headers: {
        Authorization: `Bearer ${token}`,
        ...getOutboundLocaleHeaders(),
      },
    });
    if (!res.ok) {
      // F4.0b: grava APIError ANTES do removeToken para que callers
      // consigam ler `getLastAuthError()` apos receber null.
      const err = await apiErrorFromResponse(res);
      setLastAuthError(err);
      // Regra preexistente (F2.9b-fix): 401 remove o token local.
      if (res.status === 401) removeToken();
      return null;
    }
    let data: AuthResponse;
    try {
      data = (await res.json()) as AuthResponse;
    } catch (parseErr) {
      setLastAuthError(
        new APIError({
          status: res.status,
          source: "parse",
          code: "invalid_response_json",
          cause: parseErr,
        }),
      );
      return null;
    }

    // F2.9b: sync de locale pos-login. Defensivo: nao deixa sync
    // quebrar o contrato de getUser() em hipotese alguma.
    try {
      await syncLocalePreferenceAfterAuth(data);
    } catch {
      // Engole erros de sync; preferencia atual mantida.
    }

    clearLastAuthError();
    return data;
  } catch (err) {
    setLastAuthError(apiErrorFromNetwork(err));
    return null;
  }
}

export async function getUser(): Promise<AuthResponse | null> {
  const token = getToken();
  if (!token) return null;

  // Caller concorrente para o mesmo token: reaproveita a promise em voo.
  if (inflightGetUserPromise && inflightGetUserToken === token) {
    return inflightGetUserPromise;
  }

  const promise = fetchUserAndSync(token).finally(() => {
    // Limpa o slot APENAS se ainda estivermos no mesmo ciclo. Se um novo
    // getUser() chegou enquanto este resolvia (ja substituiu o slot),
    // nao apagamos o do outro.
    if (inflightGetUserPromise === promise) {
      inflightGetUserPromise = null;
      inflightGetUserToken = null;
    }
  });
  inflightGetUserPromise = promise;
  inflightGetUserToken = token;
  return promise;
}

export async function getCredits(sessionId?: string): Promise<CreditsData | null> {
  const token = getToken();
  const params = new URLSearchParams();
  if (!token && sessionId) params.set("session_id", sessionId);

  try {
    const res = await fetch(`${API_URL}/api/credits?${params}`, {
      headers: {
        ...getOutboundLocaleHeaders(),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });
    if (!res.ok) {
      setLastAuthError(await apiErrorFromResponse(res));
      if (res.status === 401) removeToken();
      return null;
    }
    let data: CreditsData;
    try {
      data = (await res.json()) as CreditsData;
    } catch (parseErr) {
      setLastAuthError(
        new APIError({
          status: res.status,
          source: "parse",
          code: "invalid_response_json",
          cause: parseErr,
        }),
      );
      return null;
    }
    clearLastAuthError();
    return data;
  } catch (err) {
    setLastAuthError(apiErrorFromNetwork(err));
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
      headers: {
        "Content-Type": "application/json",
        ...getOutboundLocaleHeaders(),
      },
      body: JSON.stringify({ code }),
    });
    if (!res.ok) {
      const err = await apiErrorFromResponse(res);
      setLastAuthError(err);
      console.error(
        `[auth] ${provider} callback failed (${res.status}):`,
        err.serverMessage ?? err.code ?? err.messageCode ?? "",
      );
      return null;
    }
    let data: { token: string; user: UserData };
    try {
      data = (await res.json()) as { token: string; user: UserData };
    } catch (parseErr) {
      setLastAuthError(
        new APIError({
          status: res.status,
          source: "parse",
          code: "invalid_response_json",
          cause: parseErr,
        }),
      );
      return null;
    }
    clearLastAuthError();
    return data;
  } catch (err) {
    setLastAuthError(apiErrorFromNetwork(err));
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

export async function deleteAccount(): Promise<boolean> {
  const token = getToken();
  if (!token) {
    setLastAuthError(
      new APIError({
        source: "unknown",
        code: "no_token",
        serverMessage: "No token",
      }),
    );
    return false;
  }
  try {
    const res = await fetch(`${API_URL}/api/auth/me`, {
      method: "DELETE",
      headers: {
        Authorization: `Bearer ${token}`,
        ...getOutboundLocaleHeaders(),
      },
    });
    if (res.ok) {
      clearLastAuthError();
      removeToken();
      return true;
    }
    setLastAuthError(await apiErrorFromResponse(res));
    return false;
  } catch (err) {
    setLastAuthError(apiErrorFromNetwork(err));
    return false;
  }
}

export async function logout(): Promise<void> {
  const token = getToken();
  if (token) {
    // Fire-and-forget. Falha no backend nao bloqueia o logout local.
    // Limpa last error: logout explicito zera o estado de auth.
    fetch(`${API_URL}/api/auth/logout`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        ...getOutboundLocaleHeaders(),
      },
    }).catch(() => {});
  }
  clearLastAuthError();
  removeToken();
}
