"""Tool de estatisticas: get_wine_stats — contagens e agregacoes sobre o banco."""

from db.connection import get_connection, release_connection


METRICS = {
    "count": "COUNT(*)",
    "count_distinct": "COUNT(DISTINCT {column})",
    "avg_rating": "ROUND(AVG(nota_wcf)::numeric, 2)",
    "avg_price": "ROUND(AVG(preco_min)::numeric, 2)",
    "min_price": "MIN(preco_min)",
    "max_price": "MAX(preco_min)",
    "avg_score": "ROUND(AVG(winegod_score)::numeric, 2)",
    "min_vintage": "MIN(safra)",
    "max_vintage": "MAX(safra)",
    "max_reviews": "MAX(vivino_reviews)",
}

GROUP_COLUMNS = {
    "pais": "pais_nome",
    "regiao": "regiao",
    "tipo": "tipo",
    "produtor": "produtor",
    "safra": "safra",
    "moeda": "moeda",
}


def get_wine_stats(
    metric="count",
    group_by=None,
    filter_pais=None,
    filter_tipo=None,
    filter_regiao=None,
    filter_produtor=None,
    filter_nota_min=None,
    filter_nota_max=None,
    filter_preco_min=None,
    filter_preco_max=None,
    filter_safra_min=None,
    filter_safra_max=None,
    order="desc",
    limit=10,
):
    """Retorna estatisticas agregadas sobre vinhos."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Construir filtros PRIMEIRO
            where_clauses = ["suppressed_at IS NULL"]
            params = []

            if filter_pais:
                where_clauses.append("LOWER(pais_nome) = LOWER(%s)")
                params.append(filter_pais)
            if filter_tipo:
                where_clauses.append("LOWER(tipo) = LOWER(%s)")
                params.append(filter_tipo)
            if filter_regiao:
                where_clauses.append("LOWER(regiao) = LOWER(%s)")
                params.append(filter_regiao)
            if filter_produtor:
                where_clauses.append("produtor ILIKE %s")
                params.append(f"%{filter_produtor}%")
            if filter_nota_min is not None:
                where_clauses.append("nota_wcf >= %s")
                params.append(filter_nota_min)
            if filter_nota_max is not None:
                where_clauses.append("nota_wcf <= %s")
                params.append(filter_nota_max)
            if filter_preco_min is not None:
                where_clauses.append("preco_min >= %s")
                params.append(filter_preco_min)
            if filter_preco_max is not None:
                where_clauses.append("preco_min <= %s")
                params.append(filter_preco_max)
            if filter_safra_min is not None:
                where_clauses.append("safra >= %s")
                params.append(str(filter_safra_min))
            if filter_safra_max is not None:
                where_clauses.append("safra <= %s")
                params.append(str(filter_safra_max))

            # Metricas que precisam de COUNT DISTINCT (query separada otimizada)
            if metric in ("count_producers", "count_regions", "count_countries"):
                return _count_distinct(cur, metric, where_clauses, params)
            elif metric == "count_stores":
                return _count_stores(cur, filter_pais)
            elif metric == "count_sources":
                return _count_sources(cur, filter_pais)
            elif metric in METRICS:
                select_expr = METRICS[metric]
            else:
                return {"error": f"Metrica '{metric}' nao reconhecida."}

            where_sql = ""
            if where_clauses:
                where_sql = "WHERE " + " AND ".join(where_clauses)

            if group_by and group_by in GROUP_COLUMNS:
                col = GROUP_COLUMNS[group_by]
                order_dir = "DESC" if order == "desc" else "ASC"
                sql = f"""
                    SELECT {col} as grupo, {select_expr} as valor
                    FROM wines
                    {where_sql}
                    GROUP BY {col}
                    HAVING {col} IS NOT NULL
                    ORDER BY valor {order_dir}
                    LIMIT %s
                """
                params.append(limit)
                cur.execute(sql, params)
                rows = cur.fetchall()
                results = [{"grupo": r[0], "valor": _to_number(r[1])} for r in rows]
                return {
                    "metric": metric,
                    "group_by": group_by,
                    "results": results,
                    "total_groups": len(results),
                }
            else:
                sql = f"SELECT {select_expr} as valor FROM wines {where_sql}"
                cur.execute(sql, params)
                row = cur.fetchone()
                value = _to_number(row[0]) if row else 0

                # Construir descricao dos filtros
                filters = {}
                if filter_pais: filters["pais"] = filter_pais
                if filter_tipo: filters["tipo"] = filter_tipo
                if filter_regiao: filters["regiao"] = filter_regiao
                if filter_produtor: filters["produtor"] = filter_produtor
                if filter_nota_min: filters["nota_min"] = filter_nota_min
                if filter_preco_max: filters["preco_max"] = filter_preco_max

                return {
                    "metric": metric,
                    "value": value,
                    "filters": filters if filters else "nenhum",
                }
    finally:
        release_connection(conn)


def _count_distinct(cur, metric, where_clauses, params):
    """COUNT DISTINCT otimizado com timeout."""
    col_map = {
        "count_producers": "produtor",
        "count_regions": "regiao",
        "count_countries": "pais_nome",
    }
    col = col_map[metric]
    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)
    try:
        cur.execute("SET LOCAL statement_timeout = '15s'")
        sql = f"SELECT COUNT(*) FROM (SELECT 1 FROM wines {where_sql} GROUP BY {col}) sub"
        cur.execute(sql, params)
        row = cur.fetchone()
        return {"metric": metric, "value": row[0] if row else 0}
    except Exception:
        cur.connection.rollback()
        # Fallback: estimativa rapida com LIMIT
        prefix = f"{where_sql} AND" if where_sql else "WHERE"
        sql = f"SELECT {col} FROM wines {prefix} {col} IS NOT NULL GROUP BY {col} LIMIT 5000"
        try:
            cur.execute(sql, params)
            rows = cur.fetchall()
            count = len(rows)
            approx = count >= 5000
            return {"metric": metric, "value": count, "approximate": approx}
        except Exception:
            cur.connection.rollback()
            return {"metric": metric, "value": "query muito pesada, tente filtrar por pais ou regiao"}


def _count_stores(cur, filter_pais=None):
    """Conta lojas, opcionalmente filtrado por pais."""
    if filter_pais:
        cur.execute("SELECT COUNT(*) FROM stores WHERE pais ILIKE %s", (f"%{filter_pais}%",))
    else:
        cur.execute("SELECT COUNT(*) FROM stores")
    row = cur.fetchone()
    return {"metric": "count_stores", "value": row[0] if row else 0}


def _count_sources(cur, filter_pais=None):
    """Conta wine_sources (vinhos disponiveis em lojas)."""
    if filter_pais:
        cur.execute("""
            SELECT COUNT(*) FROM wine_sources ws
            JOIN stores s ON ws.store_id = s.id
            JOIN wines w ON w.id = ws.wine_id
            WHERE s.pais ILIKE %s
              AND w.suppressed_at IS NULL
        """, (f"%{filter_pais}%",))
    else:
        cur.execute("""
            SELECT COUNT(*)
            FROM wine_sources ws
            JOIN wines w ON w.id = ws.wine_id
            WHERE w.suppressed_at IS NULL
        """)
    row = cur.fetchone()
    return {"metric": "count_sources", "value": row[0] if row else 0}


def _to_number(val):
    """Converte Decimal/int para float/int para JSON."""
    if val is None:
        return 0
    if hasattr(val, 'as_integer_ratio'):
        return float(val)
    return val
