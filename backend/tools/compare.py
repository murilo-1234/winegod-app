"""Tools de comparacao e recomendacao: compare_wines, get_recommendations."""

from db.connection import get_connection, release_connection
from services.cache import cache_get, cache_set, cache_key, TTL_RECOMMENDATIONS
from services.display import enrich_wines


def compare_wines(wine_ids):
    """Compara 2 a 5 vinhos lado a lado."""
    if len(wine_ids) < 2 or len(wine_ids) > 5:
        return {"error": "Envie entre 2 e 5 IDs de vinhos para comparar."}

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = """
                SELECT id, nome, produtor, safra, tipo, pais_nome, regiao, uvas,
                       vivino_rating, preco_min, preco_max, moeda,
                       winegod_score, winegod_score_type, nota_wcf, nota_wcf_sample_size
                FROM wines
                WHERE id = ANY(%s)
            """
            cur.execute(sql, (wine_ids,))
            columns = [desc[0] for desc in cur.description]
            results = [dict(zip(columns, row)) for row in cur.fetchall()]

            for r in results:
                for k, v in r.items():
                    if hasattr(v, 'as_integer_ratio'):
                        r[k] = float(v)

            if not results:
                return {"error": "Nenhum dos vinhos foi encontrado."}

            enrich_wines(results)
            return {"wines": results, "total": len(results)}
    finally:
        release_connection(conn)


def get_recommendations(tipo=None, pais=None, regiao=None, uva=None,
                        preco_min=None, preco_max=None, limit=5):
    """Retorna top N vinhos por score/rating com filtros."""
    key = cache_key("recs", tipo=tipo, pais=pais, regiao=regiao, uva=uva,
                    preco_min=preco_min, preco_max=preco_max, limit=limit)
    cached = cache_get(key)
    if cached:
        return cached

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            conditions = []
            params = []

            if tipo:
                conditions.append("tipo ILIKE %s")
                params.append(f"%{tipo}%")
            if pais:
                conditions.append("pais_nome ILIKE %s")
                params.append(f"%{pais}%")
            if regiao:
                conditions.append("regiao ILIKE %s")
                params.append(f"%{regiao}%")
            if uva:
                conditions.append("uvas ILIKE %s")
                params.append(f"%{uva}%")
            if preco_min is not None:
                conditions.append("preco_min >= %s")
                params.append(preco_min)
            if preco_max is not None:
                conditions.append("preco_min <= %s")
                params.append(preco_max)

            where = "WHERE " + " AND ".join(conditions) if conditions else ""
            params.append(limit)

            sql = f"""
                SELECT id, nome, produtor, safra, tipo, pais_nome, regiao,
                       vivino_rating, preco_min, preco_max, moeda,
                       winegod_score, winegod_score_type, nota_wcf, nota_wcf_sample_size
                FROM wines
                {where}
                ORDER BY winegod_score DESC NULLS LAST,
                         vivino_rating DESC NULLS LAST
                LIMIT %s
            """
            cur.execute(sql, params)
            columns = [desc[0] for desc in cur.description]
            results = [dict(zip(columns, row)) for row in cur.fetchall()]

            for r in results:
                for k, v in r.items():
                    if hasattr(v, 'as_integer_ratio'):
                        r[k] = float(v)

            enrich_wines(results)
            result = {"wines": results, "total": len(results)}
            cache_set(key, result, TTL_RECOMMENDATIONS)
            return result
    finally:
        release_connection(conn)
