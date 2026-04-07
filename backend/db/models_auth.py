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


def upsert_user(google_id, email, name, picture_url):
    """Cria ou atualiza usuario. Retorna o registro completo."""
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
    """Retorna dados do usuario por ID."""
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
