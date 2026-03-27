from db.connection import get_connection, release_connection


def search_wines(query, limit=5):
    """Busca vinhos por nome (LIKE simples por enquanto, pg_trgm depois)"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = """
                SELECT id, nome, produtor, safra, tipo, pais_nome, regiao,
                       vivino_rating, vivino_reviews, preco_min, preco_max, moeda
                FROM wines
                WHERE nome_normalizado ILIKE %s
                ORDER BY vivino_reviews DESC NULLS LAST
                LIMIT %s
            """
            cur.execute(sql, (f"%{query}%", limit))
            columns = [desc[0] for desc in cur.description]
            results = [dict(zip(columns, row)) for row in cur.fetchall()]
            return results
    finally:
        release_connection(conn)


def get_wines_count():
    """Retorna total de vinhos no banco"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM wines")
            return cur.fetchone()[0]
    finally:
        release_connection(conn)
