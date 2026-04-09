import psycopg2
from psycopg2 import pool
from config import Config

_pool = None


def get_pool():
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1,
            maxconn=5,
            dsn=Config.DATABASE_URL
        )
    return _pool


def get_connection():
    """Pega conexao do pool e valida que esta viva.
    Se a conexao estiver morta, descarta e tenta outra.
    Se nenhuma conexao valida existir, levanta a excecao."""
    p = get_pool()
    last_err = None
    for _attempt in range(3):
        conn = p.getconn()
        try:
            # Ping: timeout de sessao 3s -> SELECT 1 -> reset timeout
            with conn.cursor() as cur:
                cur.execute("SET statement_timeout = '3s'")
                cur.execute("SELECT 1")
                cur.execute("RESET statement_timeout")
            conn.commit()
            return conn
        except Exception as e:
            last_err = e
            try:
                p.putconn(conn, close=True)
            except Exception:
                pass
    raise psycopg2.OperationalError(f"No valid connection after 3 attempts: {last_err}")


def release_connection(conn):
    """Devolve conexao ao pool. Se estiver quebrada, descarta."""
    p = get_pool()
    try:
        if conn.closed:
            p.putconn(conn, close=True)
        else:
            # Resetar estado da conexao antes de devolver
            try:
                conn.rollback()
            except Exception:
                pass
            p.putconn(conn)
    except Exception:
        # Pool pode estar fechado ou conn invalida
        try:
            conn.close()
        except Exception:
            pass
