from db.connection import get_connection, release_connection


def search_wines(query, limit=5):
    """Busca vinhos por nome — delega para tools/search.search_wine."""
    from tools.search import search_wine
    result = search_wine(query, limit=limit)
    return result.get("wines", [])


def get_wines_count_estimate():
    """Retorna estimativa de vinhos via pg_class (sem seq scan)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT reltuples::bigint FROM pg_class WHERE relname = 'wines'"
            )
            row = cur.fetchone()
            return row[0] if row and row[0] > 0 else 0
    finally:
        release_connection(conn)
