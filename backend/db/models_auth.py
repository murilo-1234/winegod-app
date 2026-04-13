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
    ensure_multi_provider_columns()


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
                    RETURNING id, google_id, email, name, picture_url, created_at, last_login
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
                        RETURNING id, google_id, email, name, picture_url, created_at, last_login
                    """, (provider_id, name, picture_url, provider, email))
                else:
                    # 3) Usuario novo
                    cur.execute(f"""
                        INSERT INTO users ({id_col}, email, name, picture_url, provider, last_login)
                        VALUES (%s, %s, %s, %s, %s, NOW())
                        RETURNING id, google_id, email, name, picture_url, created_at, last_login
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
            }
    finally:
        release_connection(conn)


def get_user_by_id(user_id):
    """Retorna dados do usuario por ID."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, google_id, email, name, picture_url, created_at, last_login, provider
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
