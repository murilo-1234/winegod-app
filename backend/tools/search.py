"""Tools de busca: search_wine, get_similar_wines."""

from db.connection import get_connection, release_connection


def search_wine(query, limit=5):
    """Busca vinhos por nome usando pg_trgm (fuzzy match)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Tenta busca fuzzy com pg_trgm primeiro
            sql = """
                SELECT id, nome, produtor, safra, tipo, pais_nome, regiao,
                       vivino_rating, vivino_reviews, preco_min, preco_max, moeda,
                       winegod_score, winegod_score_type, nota_wcf,
                       similarity(nome_normalizado, %s) as sim
                FROM wines
                WHERE nome_normalizado %% %s
                ORDER BY sim DESC, vivino_reviews DESC NULLS LAST
                LIMIT %s
            """
            try:
                cur.execute(sql, (query.lower(), query.lower(), limit))
            except Exception:
                # Fallback: se pg_trgm nao estiver habilitado, usa ILIKE
                conn.rollback()
                sql = """
                    SELECT id, nome, produtor, safra, tipo, pais_nome, regiao,
                           vivino_rating, vivino_reviews, preco_min, preco_max, moeda,
                           winegod_score, winegod_score_type, nota_wcf
                    FROM wines
                    WHERE nome_normalizado ILIKE %s
                    ORDER BY vivino_reviews DESC NULLS LAST
                    LIMIT %s
                """
                cur.execute(sql, (f"%{query}%", limit))

            columns = [desc[0] for desc in cur.description]
            results = [dict(zip(columns, row)) for row in cur.fetchall()]

            # Converter Decimal para float para JSON
            for r in results:
                for k, v in r.items():
                    if hasattr(v, 'as_integer_ratio'):
                        r[k] = float(v)

            return {"wines": results, "total": len(results)}
    finally:
        release_connection(conn)


def get_similar_wines(wine_id, limit=5):
    """Encontra vinhos similares por tipo, pais, regiao e faixa de preco."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Pegar vinho base
            cur.execute(
                "SELECT tipo, pais_nome, regiao, preco_min FROM wines WHERE id = %s",
                (wine_id,),
            )
            base = cur.fetchone()
            if not base:
                return {"error": "Vinho nao encontrado", "wines": []}

            tipo, pais, regiao, preco = base
            conditions = ["id != %s"]
            params = [wine_id]

            if tipo:
                conditions.append("tipo = %s")
                params.append(tipo)
            if pais:
                conditions.append("pais_nome = %s")
                params.append(pais)
            if regiao:
                conditions.append("regiao = %s")
                params.append(regiao)
            if preco:
                conditions.append("preco_min BETWEEN %s AND %s")
                params.extend([float(preco) * 0.5, float(preco) * 1.5])

            params.append(limit)
            where = " AND ".join(conditions)

            sql = f"""
                SELECT id, nome, produtor, pais_nome, regiao, tipo,
                       vivino_rating, preco_min, preco_max, moeda,
                       winegod_score, nota_wcf
                FROM wines
                WHERE {where}
                ORDER BY vivino_rating DESC NULLS LAST
                LIMIT %s
            """
            cur.execute(sql, params)
            columns = [desc[0] for desc in cur.description]
            results = [dict(zip(columns, row)) for row in cur.fetchall()]

            for r in results:
                for k, v in r.items():
                    if hasattr(v, 'as_integer_ratio'):
                        r[k] = float(v)

            # Se poucos resultados com regiao, buscar sem regiao
            if len(results) < limit and regiao:
                remaining = limit - len(results)
                found_ids = [r["id"] for r in results] + [wine_id]
                conditions2 = ["id != ALL(%s)"]
                params2 = [found_ids]
                if tipo:
                    conditions2.append("tipo = %s")
                    params2.append(tipo)
                if pais:
                    conditions2.append("pais_nome = %s")
                    params2.append(pais)
                if preco:
                    conditions2.append("preco_min BETWEEN %s AND %s")
                    params2.extend([float(preco) * 0.5, float(preco) * 1.5])
                params2.append(remaining)
                where2 = " AND ".join(conditions2)
                sql2 = f"""
                    SELECT id, nome, produtor, pais_nome, regiao, tipo,
                           vivino_rating, preco_min, preco_max, moeda,
                           winegod_score, nota_wcf
                    FROM wines
                    WHERE {where2}
                    ORDER BY vivino_rating DESC NULLS LAST
                    LIMIT %s
                """
                cur.execute(sql2, params2)
                columns2 = [desc[0] for desc in cur.description]
                extra = [dict(zip(columns2, row)) for row in cur.fetchall()]
                for r in extra:
                    for k, v in r.items():
                        if hasattr(v, 'as_integer_ratio'):
                            r[k] = float(v)
                results.extend(extra)

            return {"wines": results, "total": len(results)}
    finally:
        release_connection(conn)
