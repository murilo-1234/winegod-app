INSTRUCAO: Este prompt implementa login com Facebook, Apple e Microsoft no WineGod.ai. ENTREGA POR FASES — implemente UMA fase por vez, mostre o codigo completo, e PARE. O fundador vai verificar com outro assistente antes de autorizar a proxima fase.

# MULTI-LOGIN — Facebook + Apple + Microsoft OAuth

## CONTEXTO

WineGod.ai e uma IA sommelier. O login com Google ja funciona em producao. Agora vamos adicionar 3 provedores: Facebook, Apple e Microsoft (Hotmail/Outlook).

URLs de producao:
- Frontend: `https://chat.winegod.ai` (Vercel)
- Backend: `https://winegod-app.onrender.com` (Render, Flask)
- Banco: PostgreSQL 16 no Render

## REGRA CRITICA DO BANCO

- NAO deletar dados existentes
- NAO alterar tipo de colunas existentes
- So adicionar novas colunas
- EXCECAO UNICA: a coluna `google_id` precisa virar nullable (ALTER COLUMN google_id DROP NOT NULL) — isso e seguro porque todos os registros existentes ja tem google_id preenchido. Sem essa mudanca, usuarios de Facebook/Apple/Microsoft nao conseguem ser inseridos.

## CODIGO ATUAL — LEIA TUDO ANTES DE COMECAR

### Arquivo: `C:\winegod-app\backend\routes\auth.py` (OAuth Google — REFERENCIA)

```python
import os
import jwt
import requests
from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, jsonify, redirect
from db.models_auth import upsert_user, get_user_by_id

auth_bp = Blueprint('auth', __name__)

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
JWT_SECRET = os.getenv("JWT_SECRET", os.urandom(32).hex())
JWT_EXPIRY_DAYS = 7

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


def _get_redirect_uri():
    """Monta o redirect URI baseado no ambiente."""
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    return f"{frontend_url}/auth/callback"


def _create_jwt(user_id, email):
    """Cria um JWT com user_id e email."""
    payload = {
        "user_id": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRY_DAYS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def decode_jwt(token):
    """Decodifica e valida um JWT. Retorna payload ou None."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


@auth_bp.route('/auth/google', methods=['GET'])
def google_login():
    """Redireciona para Google OAuth consent screen."""
    redirect_uri = _get_redirect_uri()
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
    }
    query = "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())
    return redirect(f"{GOOGLE_AUTH_URL}?{query}")


@auth_bp.route('/auth/google/callback', methods=['POST'])
def google_callback():
    """Recebe o code do Google (enviado pelo frontend), troca por token, cria/atualiza usuario."""
    data = request.get_json()
    code = data.get("code") if data else None
    if not code:
        return jsonify({"error": "Campo 'code' e obrigatorio"}), 400

    redirect_uri = _get_redirect_uri()

    token_resp = requests.post(GOOGLE_TOKEN_URL, data={
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    })

    if token_resp.status_code != 200:
        return jsonify({"error": "Falha ao trocar code por token"}), 400

    access_token = token_resp.json().get("access_token")

    userinfo_resp = requests.get(GOOGLE_USERINFO_URL, headers={
        "Authorization": f"Bearer {access_token}"
    })

    if userinfo_resp.status_code != 200:
        return jsonify({"error": "Falha ao obter dados do Google"}), 400

    userinfo = userinfo_resp.json()
    google_id = userinfo["id"]
    email = userinfo["email"]
    name = userinfo.get("name", "")
    picture = userinfo.get("picture", "")

    user = upsert_user(google_id, email, name, picture)
    token = _create_jwt(user["id"], user["email"])

    return jsonify({
        "token": token,
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "picture_url": user["picture_url"],
        }
    })


@auth_bp.route('/auth/me', methods=['GET'])
def get_me():
    """Retorna dados do usuario logado + creditos restantes."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return jsonify({"error": "Token nao fornecido"}), 401

    payload = decode_jwt(auth_header[7:])
    if not payload:
        return jsonify({"error": "Token invalido ou expirado"}), 401

    user = get_user_by_id(payload["user_id"])
    if not user:
        return jsonify({"error": "Usuario nao encontrado"}), 404

    from db.models_auth import count_messages_today
    used = count_messages_today(user["id"])
    remaining = max(0, 15 - used)

    return jsonify({
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "picture_url": user["picture_url"],
        },
        "credits": {
            "used": used,
            "remaining": remaining,
            "limit": 15,
        }
    })


@auth_bp.route('/auth/logout', methods=['POST'])
def logout():
    return jsonify({"message": "Logout realizado com sucesso"})
```

### Arquivo: `C:\winegod-app\backend\db\models_auth.py` (banco de usuarios)

```python
from db.connection import get_connection, release_connection


def create_tables():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    google_id VARCHAR(255) UNIQUE NOT NULL,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    name VARCHAR(255),
                    picture_url TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    last_login TIMESTAMP DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS message_log (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    session_id VARCHAR(255),
                    ip_address VARCHAR(45),
                    cost INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_message_log_user_date
                    ON message_log (user_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_message_log_session
                    ON message_log (session_id, created_at);
            """)
            conn.commit()
    finally:
        release_connection(conn)

    ensure_cost_column()


def ensure_cost_column():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'message_log' AND column_name = 'cost'
                    ) THEN
                        ALTER TABLE message_log ADD COLUMN cost INTEGER DEFAULT 1;
                    END IF;
                END $$;
            """)
            conn.commit()
    finally:
        release_connection(conn)


def upsert_user(google_id, email, name, picture_url):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (google_id, email, name, picture_url, last_login)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (google_id)
                DO UPDATE SET
                    email = EXCLUDED.email,
                    name = EXCLUDED.name,
                    picture_url = EXCLUDED.picture_url,
                    last_login = NOW()
                RETURNING id, google_id, email, name, picture_url, created_at, last_login
            """, (google_id, email, name, picture_url))
            user = cur.fetchone()
            conn.commit()
            return {
                "id": user[0],
                "google_id": user[1],
                "email": user[2],
                "name": user[3],
                "picture_url": user[4],
                "created_at": str(user[5]),
                "last_login": str(user[6]),
            }
    finally:
        release_connection(conn)


def get_user_by_id(user_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, google_id, email, name, picture_url, created_at, last_login
                FROM users WHERE id = %s
            """, (user_id,))
            user = cur.fetchone()
            if not user:
                return None
            return {
                "id": user[0],
                "google_id": user[1],
                "email": user[2],
                "name": user[3],
                "picture_url": user[4],
                "created_at": str(user[5]),
                "last_login": str(user[6]),
            }
    finally:
        release_connection(conn)


def log_message(user_id, session_id, ip_address, cost=1):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO message_log (user_id, session_id, ip_address, cost)
                VALUES (%s, %s, %s, %s)
            """, (user_id, session_id, ip_address, cost))
            conn.commit()
    finally:
        release_connection(conn)


def count_messages_today(user_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COALESCE(SUM(COALESCE(cost, 1)), 0) FROM message_log
                WHERE user_id = %s
                  AND created_at >= CURRENT_DATE
            """, (user_id,))
            return cur.fetchone()[0]
    finally:
        release_connection(conn)


def count_messages_session(session_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COALESCE(SUM(COALESCE(cost, 1)), 0) FROM message_log
                WHERE session_id = %s
                  AND created_at >= CURRENT_DATE
            """, (session_id,))
            return cur.fetchone()[0]
    finally:
        release_connection(conn)
```

### Arquivo: `C:\winegod-app\backend\app.py` (registro de blueprints)

```python
import re

from flask import Flask
from flask_cors import CORS
from config import Config
from routes.chat import chat_bp
from routes.health import health_bp
from routes.auth import auth_bp
from routes.credits import credits_bp
from routes.sharing import sharing_bp


def create_app():
    flask_app = Flask(__name__)
    flask_app.config.from_object(Config)

    CORS(flask_app, origins=[
        "http://localhost:3000",
        "https://chat.winegod.ai",
        re.compile(r"https://winegod.*\.vercel\.app"),
    ])

    flask_app.register_blueprint(chat_bp, url_prefix='/api')
    flask_app.register_blueprint(health_bp)
    flask_app.register_blueprint(auth_bp, url_prefix='/api')
    flask_app.register_blueprint(credits_bp, url_prefix='/api')
    flask_app.register_blueprint(sharing_bp, url_prefix='/api')

    return flask_app


app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(Config.FLASK_PORT), debug=True)
```

### Arquivo: `C:\winegod-app\frontend\lib\auth.ts` (frontend auth)

```typescript
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
  code: string
): Promise<{ token: string; user: UserData } | null> {
  try {
    const res = await fetch(`${API_URL}/api/auth/google/callback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export function getGoogleLoginUrl(): string {
  return `${API_URL}/api/auth/google`;
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
```

### Arquivo: `C:\winegod-app\frontend\components\auth\LoginButton.tsx`

```typescript
"use client";

import { getGoogleLoginUrl } from "@/lib/auth";

interface LoginButtonProps {
  compact?: boolean;
}

export function LoginButton({ compact = false }: LoginButtonProps) {
  const handleLogin = () => {
    window.location.href = getGoogleLoginUrl();
  };

  if (compact) {
    return (
      <button
        onClick={handleLogin}
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-wine-surface border border-wine-border text-wine-text text-sm hover:border-wine-accent transition-colors"
      >
        <GoogleIcon />
        <span>Entrar</span>
      </button>
    );
  }

  return (
    <button
      onClick={handleLogin}
      className="flex items-center justify-center gap-3 w-full px-4 py-3 rounded-xl bg-wine-surface border border-wine-border text-wine-text text-sm hover:border-wine-accent transition-colors"
    >
      <GoogleIcon />
      <span>Entrar com Google</span>
    </button>
  );
}

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 01-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z" fill="#4285F4" />
      <path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.26c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 009 18z" fill="#34A853" />
      <path d="M3.964 10.71A5.41 5.41 0 013.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.997 8.997 0 000 9c0 1.452.348 2.827.957 4.042l3.007-2.332z" fill="#FBBC05" />
      <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 00.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z" fill="#EA4335" />
    </svg>
  );
}
```

### Arquivo: `C:\winegod-app\frontend\app\auth\callback\page.tsx`

```typescript
"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { exchangeCodeForToken, setToken } from "@/lib/auth";

function CallbackHandler() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [error, setError] = useState("");

  useEffect(() => {
    const code = searchParams.get("code");
    if (!code) {
      setError("Codigo de autorizacao nao encontrado");
      return;
    }

    exchangeCodeForToken(code).then((result) => {
      if (result) {
        setToken(result.token);
        router.replace("/");
      } else {
        setError("Falha ao fazer login. Tente novamente.");
      }
    });
  }, [searchParams, router]);

  if (error) {
    return (
      <div className="text-center p-6">
        <p className="text-wine-text mb-4">{error}</p>
        <a href="/" className="text-wine-accent hover:underline text-sm">
          Voltar ao chat
        </a>
      </div>
    );
  }

  return (
    <div className="text-center">
      <div className="w-8 h-8 border-2 border-wine-accent border-t-transparent rounded-full animate-spin mx-auto mb-4" />
      <p className="text-wine-muted text-sm">Entrando...</p>
    </div>
  );
}

export default function AuthCallback() {
  return (
    <main className="flex items-center justify-center h-dvh bg-wine-bg">
      <Suspense
        fallback={
          <div className="text-center">
            <div className="w-8 h-8 border-2 border-wine-accent border-t-transparent rounded-full animate-spin mx-auto mb-4" />
            <p className="text-wine-muted text-sm">Carregando...</p>
          </div>
        }
      >
        <CallbackHandler />
      </Suspense>
    </main>
  );
}
```

### Arquivo: `C:\winegod-app\frontend\components\auth\CreditsBanner.tsx`

```typescript
"use client";

import { LoginButton } from "./LoginButton";

interface CreditsBannerProps {
  isLoggedIn: boolean;
  reason: "guest_limit" | "daily_limit";
}

export function CreditsBanner({ isLoggedIn, reason }: CreditsBannerProps) {
  return (
    <div className="mx-4 mb-2 p-4 rounded-xl bg-wine-surface border border-wine-accent/30 text-center">
      <p className="text-wine-text text-sm mb-1">
        Voce usou suas mensagens gratuitas
      </p>

      {reason === "guest_limit" && !isLoggedIn ? (
        <div className="mt-3">
          <p className="text-wine-muted text-xs mb-3">
            Entre com Google para ganhar mais 15 mensagens
          </p>
          <LoginButton />
        </div>
      ) : (
        <p className="text-wine-muted text-xs">
          Seus creditos renovam amanha
        </p>
      )}
    </div>
  );
}
```

### Arquivo: `C:\winegod-app\frontend\app\page.tsx` (onde o LoginButton e usado)

```typescript
// Importacoes relevantes:
import { LoginButton } from "@/components/auth/LoginButton";
import { UserMenu } from "@/components/auth/UserMenu";
import { CreditsBanner } from "@/components/auth/CreditsBanner";
import { getUser, logout as doLogout, isLoggedIn as checkLoggedIn } from "@/lib/auth";
import type { UserData } from "@/lib/auth";

// No header (linha 121-130):
{user ? (
  <UserMenu
    user={user}
    creditsUsed={creditsUsed}
    creditsLimit={creditsLimit}
    onLogout={handleLogout}
  />
) : (
  <LoginButton compact />
)}
```

### Arquivo: `C:\winegod-app\backend\requirements.txt`

```
flask==3.1.0
flask-cors==5.0.1
anthropic==0.49.0
psycopg2-binary==2.9.10
python-dotenv==1.0.1
gunicorn==23.0.0
google-genai>=1.0.0
openai>=1.0.0
opencv-python-headless>=4.8.0
PyJWT>=2.8.0
requests>=2.31.0
redis>=5.0.0
ffmpeg-python>=0.2.0
imageio-ffmpeg>=0.5.1
pdfplumber>=0.11.0
Pillow>=10.0.0
pypdfium2>=4.30.0
```

## ENV VARS ATUAIS NO RENDER

```
ANTHROPIC_API_KEY=xxx
DATABASE_URL=xxx
GOOGLE_CLIENT_ID=xxx
GOOGLE_CLIENT_SECRET=xxx
JWT_SECRET=xxx
FRONTEND_URL=https://chat.winegod.ai
UPSTASH_REDIS_URL=xxx
```

## FLUXO OAUTH ATUAL (como funciona o Google — os novos devem seguir o mesmo padrao)

1. Usuario clica "Entrar com Google" no frontend
2. Frontend redireciona para `API_URL/api/auth/google` (backend)
3. Backend monta a URL do Google com `redirect_uri = FRONTEND_URL + "/auth/callback"` e redireciona
4. Google autentica o usuario e redireciona para `FRONTEND_URL/auth/callback?code=xxx`
5. Frontend (callback page) pega o `code` da URL e faz POST para `API_URL/api/auth/google/callback`
6. Backend troca o code por access_token, busca dados do usuario, cria/atualiza no banco, gera JWT
7. Frontend recebe o JWT e salva no localStorage

IMPORTANTE: Todos os novos provedores DEVEM seguir esse mesmo fluxo. A callback page do frontend (`/auth/callback`) precisa ser atualizada para detectar QUAL provedor retornou e chamar o endpoint correto do backend.

## DETECCAO DO PROVEDOR NA CALLBACK

O Google retorna `?code=xxx` na callback. Facebook tambem retorna `?code=xxx`. Apple retorna via POST (form_post). Microsoft retorna `?code=xxx`.

Solucao: adicionar `&state=google`, `&state=facebook`, `&state=microsoft` no redirect para o provedor. Assim a callback page le `searchParams.get("state")` para saber qual backend chamar. Para Apple (que usa form_post), criar uma rota separada no backend que recebe o POST e redireciona para o frontend com os parametros na URL.

---

# FASES DE IMPLEMENTACAO

---

## FASE 1 — Migracao do banco + refactor do upsert (backend only)

### O que fazer:

1. **Adicionar colunas na tabela `users`** — editar `C:\winegod-app\backend\db\models_auth.py`, na funcao `create_tables()`:

```sql
-- Adicionar DEPOIS do CREATE TABLE existente (usar DO $$ para ser idempotente):
DO $$
BEGIN
    -- Tornar google_id nullable (necessario para usuarios de outros provedores)
    ALTER TABLE users ALTER COLUMN google_id DROP NOT NULL;
EXCEPTION WHEN others THEN NULL;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='facebook_id') THEN
        ALTER TABLE users ADD COLUMN facebook_id VARCHAR(255) UNIQUE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='apple_id') THEN
        ALTER TABLE users ADD COLUMN apple_id VARCHAR(255) UNIQUE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='microsoft_id') THEN
        ALTER TABLE users ADD COLUMN microsoft_id VARCHAR(255) UNIQUE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='provider') THEN
        ALTER TABLE users ADD COLUMN provider VARCHAR(20) DEFAULT 'google';
    END IF;
END $$;
```

2. **Refatorar `upsert_user`** para aceitar qualquer provedor. Nova assinatura:

```python
def upsert_user(provider, provider_id, email, name, picture_url):
    """
    provider: 'google', 'facebook', 'apple', 'microsoft'
    provider_id: o ID unico do usuario naquele provedor
    """
```

Logica:
- Montar o nome da coluna: `{provider}_id` (ex: `google_id`, `facebook_id`)
- Fazer INSERT com ON CONFLICT na coluna do provedor
- Se o email ja existe com OUTRO provedor, vincular (atualizar a coluna do novo provedor no registro existente via email)
- Retornar o mesmo formato de dict que ja retorna

3. **Atualizar `get_user_by_id`** para incluir o campo `provider` no retorno.

4. **Atualizar a chamada em `auth.py`** — trocar `upsert_user(google_id, email, name, picture)` por `upsert_user("google", google_id, email, name, picture)`.

### O que NAO fazer nesta fase:
- NAO criar rotas novas
- NAO tocar no frontend
- NAO adicionar dependencias

### Como testar:
- O login com Google deve continuar funcionando normalmente
- Rodar o app e fazer login — se funcionar igual antes, a fase 1 esta OK

### Entrega:
Mostre o codigo completo dos arquivos alterados (`models_auth.py` e `auth.py`). PARE e espere verificacao.

---

## FASE 2 — Facebook OAuth (backend + frontend)

### Pre-requisito externo (o fundador faz manualmente):
1. Criar app em https://developers.facebook.com/
2. Tipo: "Consumer"
3. Adicionar produto "Facebook Login for Web"
4. Em Settings > Basic: pegar App ID e App Secret
5. Em Facebook Login > Settings:
   - Valid OAuth Redirect URIs: `https://chat.winegod.ai/auth/callback`, `https://winegod-app.vercel.app/auth/callback`, `http://localhost:3000/auth/callback`
6. Setar no Render: `FACEBOOK_APP_ID` e `FACEBOOK_APP_SECRET`

### O que fazer no backend:

1. **Criar `C:\winegod-app\backend\routes\auth_facebook.py`** — novo arquivo, novo blueprint `auth_facebook_bp`:

Rotas:
- `GET /auth/facebook` — redireciona para Facebook OAuth com:
  - `client_id = FACEBOOK_APP_ID`
  - `redirect_uri = FRONTEND_URL + "/auth/callback"`
  - `state=facebook` (para o frontend saber qual provedor retornou)
  - `scope=email,public_profile`
  - URL base: `https://www.facebook.com/v19.0/dialog/oauth`

- `POST /auth/facebook/callback` — recebe `{"code": "xxx"}` do frontend:
  - Troca code por token em `https://graph.facebook.com/v19.0/oauth/access_token`
  - Busca dados do usuario em `https://graph.facebook.com/v19.0/me?fields=id,name,email,picture.type(large)`
  - A foto vem em `data["picture"]["data"]["url"]`
  - Chama `upsert_user("facebook", facebook_id, email, name, picture_url)`
  - Gera JWT com `_create_jwt` (importar de `routes.auth`)
  - Retorna mesmo formato: `{"token": "...", "user": {...}}`

2. **Registrar blueprint em `app.py`**:
```python
from routes.auth_facebook import auth_facebook_bp
flask_app.register_blueprint(auth_facebook_bp, url_prefix='/api')
```

### O que fazer no frontend:

1. **Editar `C:\winegod-app\frontend\lib\auth.ts`**:
   - Adicionar `getFacebookLoginUrl()`: retorna `API_URL + "/api/auth/facebook"`
   - Modificar `exchangeCodeForToken` para aceitar um parametro `provider`:
     ```typescript
     export async function exchangeCodeForToken(
       code: string,
       provider: "google" | "facebook" | "apple" | "microsoft" = "google"
     ): Promise<{ token: string; user: UserData } | null> {
       const res = await fetch(`${API_URL}/api/auth/${provider}/callback`, {
         method: "POST",
         headers: { "Content-Type": "application/json" },
         body: JSON.stringify({ code }),
       });
       ...
     }
     ```

2. **Editar `C:\winegod-app\frontend\app\auth\callback\page.tsx`**:
   - Ler `searchParams.get("state")` para detectar o provedor
   - Default para `"google"` se nao tiver state (retrocompativel)
   - Passar o provedor para `exchangeCodeForToken(code, provider)`

3. **Editar `C:\winegod-app\frontend\components\auth\LoginButton.tsx`**:
   - Em vez de um botao unico, mostrar uma lista de provedores
   - Botao Google (como ja esta) + botao Facebook (icone azul do Facebook)
   - No modo `compact`, mostrar um botao "Entrar" que abre um dropdown/modal com as opcoes
   - No modo normal (CreditsBanner), mostrar os botoes empilhados verticalmente
   - Icone do Facebook: usar SVG inline (como o Google) — cor `#1877F2`

### Como testar:
- Login com Google continua funcionando
- Botao "Entrar com Facebook" aparece ao lado do Google
- Clicar redireciona para o Facebook
- Apos autenticar, volta para o chat logado

### Entrega:
Mostre todos os arquivos criados/alterados. PARE e espere verificacao.

---

## FASE 3 — Apple Sign-In (backend + frontend)

### Pre-requisito externo (o fundador faz manualmente):
1. Ir em https://developer.apple.com/ (precisa ter conta Apple Developer — custa US$99/ano)
2. Em Certificates, Identifiers & Profiles:
   - Criar um App ID com Sign In with Apple habilitado
   - Criar um Services ID (tipo: "Web") — esse e o `client_id`
     - Domains: `chat.winegod.ai`, `winegod-app.vercel.app`
     - Return URLs: `https://winegod-app.onrender.com/api/auth/apple/web-callback`
     - NOTA: Apple Sign-In na web usa `response_mode=form_post`, entao o return URL aponta pro BACKEND, nao pro frontend. O backend recebe o POST e redireciona pro frontend.
   - Criar uma Key com Sign In with Apple habilitado — baixar o arquivo .p8
3. Setar no Render:
   - `APPLE_CLIENT_ID` = Services ID
   - `APPLE_TEAM_ID` = Team ID (aparece no topo do portal)
   - `APPLE_KEY_ID` = Key ID da key criada
   - `APPLE_PRIVATE_KEY` = conteudo do arquivo .p8 (incluindo BEGIN/END PRIVATE KEY)

### Por que Apple e diferente:
- Apple usa `response_mode=form_post` — o callback vem como POST para o backend, nao como redirect para o frontend
- O `client_secret` nao e uma string fixa — e um JWT gerado dinamicamente usando a private key
- Apple pode esconder o email do usuario (retorna um email relay @privaterelay.appleid.com)
- Apple so envia o nome do usuario na PRIMEIRA autorizacao

### O que fazer no backend:

1. **Criar `C:\winegod-app\backend\routes\auth_apple.py`** — novo blueprint `auth_apple_bp`:

Rotas:
- `GET /auth/apple` — redireciona para Apple com:
  - URL: `https://appleid.apple.com/auth/authorize`
  - `client_id = APPLE_CLIENT_ID`
  - `redirect_uri = BACKEND_URL + "/api/auth/apple/web-callback"` (BACKEND, nao frontend!)
  - `response_type=code`
  - `response_mode=form_post`
  - `scope=name email`
  - `state=apple`

- `POST /auth/apple/web-callback` — Apple faz POST aqui com form data:
  - Recebe `code` e `user` (JSON com nome, so na primeira vez) do form data
  - Gera o client_secret (JWT assinado com a private key):
    ```python
    import jwt
    import time

    def _generate_apple_client_secret():
        now = int(time.time())
        payload = {
            "iss": APPLE_TEAM_ID,
            "iat": now,
            "exp": now + 86400 * 180,  # 6 meses
            "aud": "https://appleid.apple.com",
            "sub": APPLE_CLIENT_ID,
        }
        return jwt.encode(payload, APPLE_PRIVATE_KEY, algorithm="ES256",
                          headers={"kid": APPLE_KEY_ID})
    ```
  - Troca code por id_token em `https://appleid.apple.com/auth/token`
  - Decodifica o id_token (JWT da Apple) para extrair `sub` (apple_id) e `email`
  - Nome: vem no campo `user` do form data (JSON string), so na primeira vez. Se nao veio, usar o email como nome.
  - Foto: Apple nao fornece foto. Passar string vazia.
  - Chama `upsert_user("apple", apple_id, email, name, "")`
  - Gera JWT interno
  - Redireciona para `FRONTEND_URL + "/auth/callback?token=JWT_AQUI&provider=apple"`
    (Diferente dos outros! Como o Apple faz POST pro backend, o backend precisa redirecionar pro frontend com o token na URL)

2. **Registrar blueprint em `app.py`**

### O que fazer no frontend:

1. **Editar `C:\winegod-app\frontend\lib\auth.ts`**:
   - Adicionar `getAppleLoginUrl()`: retorna `API_URL + "/api/auth/apple"`

2. **Editar `C:\winegod-app\frontend\app\auth\callback\page.tsx`**:
   - Detectar se a URL tem `?token=xxx&provider=apple` (fluxo Apple)
   - Se tiver `token` direto, salvar no localStorage e redirecionar (nao precisa chamar o backend)
   - Se tiver `code` + `state`, fazer o fluxo normal (Google/Facebook/Microsoft)

3. **Editar `C:\winegod-app\frontend\components\auth\LoginButton.tsx`**:
   - Adicionar botao Apple (icone preto/branco da Apple)
   - Icone Apple: SVG do logo da Apple, fundo preto `#000`, texto branco

### Dependencia nova no backend:
- `cryptography>=42.0.0` (para o PyJWT assinar com ES256) — adicionar em `requirements.txt`

### Como testar:
- Login com Google e Facebook continuam funcionando
- Botao "Entrar com Apple" aparece
- Clicar redireciona para Apple
- Apos autenticar, volta para o chat logado
- Se o usuario escolheu esconder o email, o sistema ainda funciona (usa email relay)

### Entrega:
Mostre todos os arquivos criados/alterados. PARE e espere verificacao.

---

## FASE 4 — Microsoft OAuth (backend + frontend)

### Pre-requisito externo (o fundador faz manualmente):
1. Ir em https://portal.azure.com/ → Azure Active Directory → App registrations
2. "New registration":
   - Nome: `WineGod.ai`
   - Supported account types: "Accounts in any organizational directory and personal Microsoft accounts" (o mais amplo — pega Hotmail, Outlook, contas corporativas)
   - Redirect URI (Web): `https://chat.winegod.ai/auth/callback`
3. Depois de criar:
   - Copiar Application (client) ID
   - Em "Certificates & secrets" → "New client secret" → copiar o Value
4. Adicionar redirect URIs extras em "Authentication":
   - `https://winegod-app.vercel.app/auth/callback`
   - `http://localhost:3000/auth/callback`
5. Setar no Render: `MICROSOFT_CLIENT_ID` e `MICROSOFT_CLIENT_SECRET`

### O que fazer no backend:

1. **Criar `C:\winegod-app\backend\routes\auth_microsoft.py`** — novo blueprint `auth_microsoft_bp`:

Rotas:
- `GET /auth/microsoft` — redireciona para Microsoft com:
  - URL: `https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize`
  - IMPORTANTE: usar `/consumers/` no path (nao `/common/`) — isso garante que aceita contas pessoais (Hotmail/Outlook)
  - `client_id = MICROSOFT_CLIENT_ID`
  - `redirect_uri = FRONTEND_URL + "/auth/callback"`
  - `response_type=code`
  - `scope=openid email profile User.Read`
  - `state=microsoft`

- `POST /auth/microsoft/callback` — recebe `{"code": "xxx"}` do frontend:
  - Troca code por token em `https://login.microsoftonline.com/consumers/oauth2/v2.0/token`
  - Busca dados do usuario em `https://graph.microsoft.com/v1.0/me`
  - Campos: `id` (microsoft_id), `displayName` (nome), `mail` ou `userPrincipalName` (email)
  - Foto: Microsoft Graph tem endpoint de foto mas e complexo. Passar string vazia (como Apple).
  - Chama `upsert_user("microsoft", microsoft_id, email, name, "")`
  - Gera JWT, retorna mesmo formato

2. **Registrar blueprint em `app.py`**

### O que fazer no frontend:

1. **Editar `C:\winegod-app\frontend\lib\auth.ts`**:
   - Adicionar `getMicrosoftLoginUrl()`: retorna `API_URL + "/api/auth/microsoft"`

2. **Editar `C:\winegod-app\frontend\components\auth\LoginButton.tsx`**:
   - Adicionar botao Microsoft (icone colorido da Microsoft — 4 quadrados)
   - Icone Microsoft: SVG dos 4 quadrados coloridos (#F25022, #7FBA00, #00A4EF, #FFB900)

### Como testar:
- Todos os logins anteriores continuam funcionando
- Botao "Entrar com Microsoft" aparece
- Clicar redireciona para Microsoft
- Testar com conta Hotmail e com conta Outlook

### Entrega:
Mostre todos os arquivos criados/alterados. PARE e espere verificacao.

---

## RESUMO DAS FASES

| Fase | O que | Arquivos tocados |
|------|-------|-----------------|
| 1 | Migracao banco + refactor upsert | `models_auth.py`, `auth.py` |
| 2 | Facebook OAuth | `auth_facebook.py` (novo), `app.py`, `auth.ts`, `callback/page.tsx`, `LoginButton.tsx` |
| 3 | Apple Sign-In | `auth_apple.py` (novo), `app.py`, `auth.ts`, `callback/page.tsx`, `LoginButton.tsx`, `requirements.txt` |
| 4 | Microsoft OAuth | `auth_microsoft.py` (novo), `app.py`, `auth.ts`, `LoginButton.tsx` |

## REGRAS FINAIS

1. Cada fase DEVE ser retrocompativel — login com Google nunca pode quebrar
2. Todos os novos provedores devem retornar o MESMO formato JSON: `{"token": "...", "user": {"id", "name", "email", "picture_url"}}`
3. Usar `_create_jwt` e `decode_jwt` de `routes.auth` — NAO duplicar
4. NAO adicionar dependencias desnecessarias. So `cryptography` para Apple (ES256).
5. NAO alterar o sistema de creditos — funciona por user_id, independente do provedor
6. Usar caminhos completos para todos os arquivos (ex: `C:\winegod-app\backend\routes\auth_facebook.py`)
7. Manter o estilo do codigo existente (sem type hints Python, sem docstrings longas, sem classes desnecessarias)
8. O texto dos botoes deve estar em portugues: "Entrar com Google", "Entrar com Facebook", "Entrar com Apple", "Entrar com Microsoft"
9. Na CreditsBanner, trocar "Entre com Google para ganhar mais 15 mensagens" por "Entre para ganhar mais 15 mensagens" (generico, sem citar provedor)

## COMECE PELA FASE 1. MOSTRE O CODIGO E PARE.
