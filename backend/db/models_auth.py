from db.connection import get_connection, release_connection


def create_tables():
    """Cria tabelas users e message_log se nao existirem."""
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
                    last_login TIMESTAMP DEFAULT NOW(),
                    ui_locale TEXT DEFAULT 'pt-BR',
                    market_country TEXT DEFAULT 'BR',
                    currency_override TEXT
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
    ensure_multi_provider_columns()
    ensure_user_i18n_columns()


def ensure_multi_provider_columns():
    """Adiciona colunas para multi-provider OAuth (idempotente)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
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
            """)
            conn.commit()
    finally:
        release_connection(conn)


def ensure_cost_column():
    """Adiciona coluna cost ao message_log se nao existir (retrocompativel)."""
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


def ensure_user_i18n_columns():
    """F1.4 - Colunas de i18n em users (idempotente).

    Adiciona ui_locale, market_country, currency_override se nao existirem.
    Aplica forward-fix de NULL para defaults seguros.
    Adiciona constraint users_ui_locale_check (whitelist Tier 1).
    Espelha o conteudo de database/migrations/015_add_user_i18n_fields.sql
    para bancos que sobem via create_tables() sem rodar a migration avulsa.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS ui_locale TEXT DEFAULT 'pt-BR';

                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS market_country TEXT DEFAULT 'BR';

                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS currency_override TEXT;

                UPDATE users SET ui_locale = 'pt-BR' WHERE ui_locale IS NULL;
                UPDATE users SET market_country = 'BR' WHERE market_country IS NULL;

                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'users_ui_locale_check'
                          AND conrelid = 'users'::regclass
                    ) THEN
                        ALTER TABLE users
                        ADD CONSTRAINT users_ui_locale_check
                        CHECK (ui_locale IN ('pt-BR', 'en-US', 'es-419', 'fr-FR'));
                    END IF;
                END $$;
            """)
            conn.commit()
    finally:
        release_connection(conn)


def upsert_user(provider, provider_id, email, name, picture_url):
    """Cria ou atualiza usuario com qualquer provedor OAuth."""
    valid = ("google", "facebook", "apple", "microsoft")
    if provider not in valid:
        raise ValueError(f"Provider invalido: {provider}")

    id_col = f"{provider}_id"
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # 1) Buscar por provider_id (usuario retornando pelo mesmo provedor)
            cur.execute(
                f"SELECT id FROM users WHERE {id_col} = %s", (provider_id,)
            )
            found = cur.fetchone()

            if found:
                cur.execute(f"""
                    UPDATE users SET
                        email = %s,
                        name = COALESCE(NULLIF(%s, ''), name),
                        picture_url = COALESCE(NULLIF(%s, ''), picture_url),
                        provider = %s,
                        last_login = NOW()
                    WHERE {id_col} = %s
                    RETURNING id, google_id, email, name, picture_url, created_at, last_login,
                              ui_locale, market_country, currency_override
                """, (email, name, picture_url, provider, provider_id))
            else:
                # 2) Buscar por email (vincular conta de outro provedor)
                cur.execute("SELECT id FROM users WHERE email = %s", (email,))
                found = cur.fetchone()

                if found:
                    cur.execute(f"""
                        UPDATE users SET
                            {id_col} = %s,
                            name = COALESCE(NULLIF(%s, ''), name),
                            picture_url = COALESCE(NULLIF(%s, ''), picture_url),
                            provider = %s,
                            last_login = NOW()
                        WHERE email = %s
                        RETURNING id, google_id, email, name, picture_url, created_at, last_login,
                                  ui_locale, market_country, currency_override
                    """, (provider_id, name, picture_url, provider, email))
                else:
                    # 3) Usuario novo
                    cur.execute(f"""
                        INSERT INTO users ({id_col}, email, name, picture_url, provider, last_login)
                        VALUES (%s, %s, %s, %s, %s, NOW())
                        RETURNING id, google_id, email, name, picture_url, created_at, last_login,
                                  ui_locale, market_country, currency_override
                    """, (provider_id, email, name, picture_url, provider))

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
                "ui_locale": user[7] or "pt-BR",
                "market_country": user[8] or "BR",
                "currency_override": user[9],
            }
    finally:
        release_connection(conn)


def update_user_preferences(user_id, preferences):
    """F1.7 - Atualiza preferencias i18n do usuario.

    Atualiza apenas os campos presentes em `preferences`:
      - ui_locale
      - market_country
      - currency_override (pode ser None para limpar)

    Campos omitidos sao preservados. Assume que `preferences` ja veio
    validado pela rota (whitelist de ui_locale, formato ISO, etc).

    Retorna dict com ui_locale, market_country, currency_override
    (com fallback "pt-BR"/"BR"/None) ou None se o user_id nao existir.
    """
    allowed = ("ui_locale", "market_country", "currency_override")
    set_clauses = []
    values = []
    for key in allowed:
        if key in preferences:
            set_clauses.append(f"{key} = %s")
            values.append(preferences[key])

    if not set_clauses:
        # Sem nada para atualizar: apenas retorna estado atual.
        user = get_user_by_id(user_id)
        if not user:
            return None
        return {
            "ui_locale": user.get("ui_locale") or "pt-BR",
            "market_country": user.get("market_country") or "BR",
            "currency_override": user.get("currency_override"),
        }

    values.append(user_id)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE users SET {', '.join(set_clauses)}
                WHERE id = %s
                RETURNING ui_locale, market_country, currency_override
                """,
                values,
            )
            row = cur.fetchone()
            if not row:
                conn.rollback()
                return None
            conn.commit()
            return {
                "ui_locale": row[0] or "pt-BR",
                "market_country": row[1] or "BR",
                "currency_override": row[2],
            }
    finally:
        release_connection(conn)


def delete_user(user_id):
    """Deleta usuario por ID. Retorna True se existia, False se nao.
    Cascade: conversations deletadas, message_log.user_id set NULL."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
            deleted = cur.rowcount > 0
            conn.commit()
            return deleted
    finally:
        release_connection(conn)


def get_user_by_id(user_id):
    """Retorna dados do usuario por ID."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, google_id, email, name, picture_url, created_at, last_login, provider,
                       ui_locale, market_country, currency_override
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
                "provider": user[7] or "google",
                "ui_locale": user[8] or "pt-BR",
                "market_country": user[9] or "BR",
                "currency_override": user[10],
            }
    finally:
        release_connection(conn)


def log_message(user_id, session_id, ip_address, cost=1):
    """Registra uma mensagem no log com custo variavel."""
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
    """Conta creditos usados pelo usuario hoje (UTC), somando cost."""
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
    """Conta creditos de uma sessao (guest), somando cost."""
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
