"""Tools de preco: get_prices, get_store_wines."""

from db.connection import get_connection, release_connection


def get_prices(wine_id, country=None):
    """Retorna precos de um vinho nas lojas."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Tentar buscar em wine_sources
            if country:
                sql = """
                    SELECT ws.preco, ws.moeda, ws.url, ws.disponivel,
                           s.nome as loja, s.pais
                    FROM wine_sources ws
                    JOIN stores s ON ws.store_id = s.id
                    WHERE ws.wine_id = %s AND ws.disponivel = TRUE
                      AND s.pais ILIKE %s
                    ORDER BY ws.preco ASC
                """
                cur.execute(sql, (wine_id, f"%{country}%"))
            else:
                sql = """
                    SELECT ws.preco, ws.moeda, ws.url, ws.disponivel,
                           s.nome as loja, s.pais
                    FROM wine_sources ws
                    JOIN stores s ON ws.store_id = s.id
                    WHERE ws.wine_id = %s AND ws.disponivel = TRUE
                    ORDER BY ws.preco ASC
                """
                cur.execute(sql, (wine_id,))

            columns = [desc[0] for desc in cur.description]
            results = [dict(zip(columns, row)) for row in cur.fetchall()]

            for r in results:
                for k, v in r.items():
                    if hasattr(v, 'as_integer_ratio'):
                        r[k] = float(v)

            # Fallback: se nao tem em wine_sources, pegar da tabela wines
            if not results:
                cur.execute(
                    "SELECT id, nome, preco_min, preco_max, moeda FROM wines WHERE id = %s",
                    (wine_id,),
                )
                row = cur.fetchone()
                if row:
                    cols = [desc[0] for desc in cur.description]
                    wine = dict(zip(cols, row))
                    for k, v in wine.items():
                        if hasattr(v, 'as_integer_ratio'):
                            wine[k] = float(v)
                    return {
                        "prices": [],
                        "fallback": wine,
                        "message": "Precos de lojas nao disponiveis. Mostrando faixa de preco conhecida.",
                    }
                return {"error": "Vinho nao encontrado"}

            return {"prices": results, "total": len(results)}
    finally:
        release_connection(conn)


def get_store_wines(store_name, tipo=None, preco_max=None):
    """Busca vinhos de uma loja especifica."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            conditions = ["s.nome ILIKE %s", "ws.disponivel = TRUE"]
            params = [f"%{store_name}%"]

            if tipo:
                conditions.append("w.tipo ILIKE %s")
                params.append(f"%{tipo}%")
            if preco_max:
                conditions.append("ws.preco <= %s")
                params.append(preco_max)

            where = " AND ".join(conditions)
            sql = f"""
                SELECT w.id, w.nome, w.produtor, w.tipo, w.pais_nome,
                       ws.preco, ws.moeda, w.vivino_rating, w.winegod_score
                FROM wine_sources ws
                JOIN wines w ON ws.wine_id = w.id
                JOIN stores s ON ws.store_id = s.id
                WHERE {where}
                ORDER BY w.vivino_rating DESC NULLS LAST
                LIMIT 20
            """
            cur.execute(sql, params)
            columns = [desc[0] for desc in cur.description]
            results = [dict(zip(columns, row)) for row in cur.fetchall()]

            for r in results:
                for k, v in r.items():
                    if hasattr(v, 'as_integer_ratio'):
                        r[k] = float(v)

            if not results:
                return {
                    "wines": [],
                    "message": f"Nenhum vinho encontrado na loja '{store_name}'. A loja pode nao estar na nossa base ainda.",
                }

            return {"wines": results, "total": len(results)}
    finally:
        release_connection(conn)
