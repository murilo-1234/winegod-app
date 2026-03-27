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
    return get_pool().getconn()


def release_connection(conn):
    get_pool().putconn(conn)
