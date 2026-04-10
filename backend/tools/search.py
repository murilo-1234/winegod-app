"""Tools de busca: search_wine, get_similar_wines."""

import time
import psycopg2

from db.connection import get_connection, release_connection
from services.cache import cache_get, cache_set, cache_key, TTL_SEARCH
from services.display import enrich_wines
from tools.normalize import normalizar

# Colunas retornadas em todas as buscas
_WINE_COLUMNS = """
    id, nome, produtor, safra, tipo, pais_nome, regiao,
    vivino_rating, preco_min, preco_max, moeda,
    winegod_score, winegod_score_type, nota_wcf, nota_wcf_sample_size
"""

# ORDER padrao: prioriza vinhos com dados canonicos, depois reviews.
# Soma de sinais canonicos (0-4): cada campo nao-nulo soma 1 ponto.
# Isso garante que entre vinhos igualmente relevantes, o registro
# canonico Vivino (com rating, score etc) aparece acima da versao
# de loja sem nota.
_CANONICAL_RANK = """(
    CASE WHEN vivino_rating IS NOT NULL THEN 1 ELSE 0 END
  + CASE WHEN nota_wcf IS NOT NULL THEN 1 ELSE 0 END
  + CASE WHEN winegod_score IS NOT NULL THEN 1 ELSE 0 END
  + CASE WHEN vivino_id IS NOT NULL THEN 1 ELSE 0 END
)"""
_ORDER_CLAUSE = f"ORDER BY {_CANONICAL_RANK} DESC, vivino_reviews DESC NULLS LAST, vivino_rating DESC NULLS LAST"


def search_wine(query, limit=10, produtor=None, pais=None, regiao=None, tipo=None, safra=None, allow_fuzzy=True, skip_tokens=False):
    """Busca vinhos em camadas: exato -> prefixo -> produtor -> fuzzy.

    Parametros opcionais permitem filtros estruturados vindos do OCR ou do Claude.
    allow_fuzzy=False pula a camada fuzzy (pg_trgm) — usar no pre-resolve para evitar queries pesadas.
    skip_tokens=True pula o complemento por tokens LIKE — usar no multi-flow para velocidade.
    """
    key = cache_key(
        "search_v4",
        query=query.lower().strip(),
        limit=limit,
        produtor=produtor,
        pais=pais,
        regiao=regiao,
        tipo=tipo,
        safra=safra,
        allow_fuzzy=allow_fuzzy,
        skip_tokens=skip_tokens,
    )
    cached = cache_get(key)
    if cached:
        return cached

    # Normalizar query com a mesma logica do ingest
    q_norm = normalizar(query)
    if not q_norm:
        return {"wines": [], "total": 0, "search_layer": "empty_query"}

    # Normalizar produtor se fornecido
    p_norm = normalizar(produtor) if produtor else None

    conn = get_connection()
    try:
        results = []
        layer_used = "none"

        # Montar filtros opcionais (aplicados em TODAS as camadas)
        extra_where, extra_params = _build_filters(pais, regiao, tipo, safra, p_norm)

        # Camada 1: match exato em nome_normalizado
        if not results:
            results, layer_used = _try_layer("exact", lambda: _search_exact(conn, q_norm, limit, extra_where, extra_params), conn, layer_used)

        # Camada 2: prefixo em nome_normalizado
        if not results:
            results, layer_used = _try_layer("prefix", lambda: _search_prefix(conn, q_norm, limit, extra_where, extra_params), conn, layer_used)

        # Camada 3: match exato/prefixo em produtor_normalizado
        if not results:
            search_producer = p_norm or q_norm
            results, layer_used = _try_layer("producer", lambda: _search_producer(conn, search_producer, limit, extra_where, extra_params), conn, layer_used)

        # Camada 4: fuzzy com pg_trgm — apenas se allow_fuzzy=True
        if not results and allow_fuzzy:
            results, layer_used = _try_layer("fuzzy", lambda: _search_fuzzy(conn, q_norm, limit, extra_where, extra_params), conn, layer_used)

        # Complemento/fallback por tokens LIKE: busca por palavras individuais
        # para encontrar canonicos com nome em ordem diferente.
        # skip_tokens=True pula esta secao (multi-flow usa validacao propria).
        if not skip_tokens:
            try:
                conn.rollback()
            except Exception:
                pass
            if not results or not _has_canonical(results):
                token_results = _search_tokens(conn, q_norm, limit, extra_where, extra_params)
                if token_results:
                    if results:
                        results = _merge_results(results, token_results, limit)
                    else:
                        results = token_results
                    layer_used = f"{layer_used}+tokens" if layer_used != "none" else "tokens"

        # Converter Decimal para float
        for r in results:
            for k, v in r.items():
                if hasattr(v, 'as_integer_ratio'):
                    r[k] = float(v)

        enrich_wines(results)

        result = {"wines": results, "total": len(results), "search_layer": layer_used}
        cache_set(key, result, TTL_SEARCH)
        return result
    finally:
        release_connection(conn)


def _try_layer(name, fn, conn, current_layer):
    """Executa uma camada de busca com logging de tempo e protecao contra DB morto."""
    t0 = time.time()
    print(f"[search] layer={name} START", flush=True)
    try:
        results = fn()
        ms = round((time.time() - t0) * 1000)
        print(f"[search] layer={name} DONE {ms}ms found={len(results)}", flush=True)
        if results:
            return results, name
        return [], current_layer
    except Exception as e:
        ms = round((time.time() - t0) * 1000)
        print(f"[search] layer={name} FAIL {ms}ms {type(e).__name__}: {e}", flush=True)
        try:
            conn.rollback()
        except Exception:
            pass
        return [], current_layer


def _build_filters(pais, regiao, tipo, safra, p_norm=None):
    """Constroi WHERE clauses e params para filtros opcionais.

    Quando p_norm e fornecido, restringe por produtor_normalizado
    em TODAS as camadas (exato, prefixo, fuzzy), nao apenas na camada 3.
    """
    clauses = []
    params = []

    if p_norm:
        clauses.append("produtor_normalizado LIKE %s")
        params.append(f"{p_norm}%")
    if pais:
        clauses.append("pais_nome ILIKE %s")
        params.append(f"%{pais}%")
    if regiao:
        clauses.append("regiao ILIKE %s")
        params.append(f"%{regiao}%")
    if tipo:
        clauses.append("tipo ILIKE %s")
        params.append(f"%{tipo}%")
    if safra:
        # wines.safra e VARCHAR(4) no banco — comparar como string
        clauses.append("safra = %s")
        params.append(str(int(safra)))

    where = ""
    if clauses:
        where = " AND " + " AND ".join(clauses)
    return where, params


def _search_exact(conn, q_norm, limit, extra_where, extra_params):
    """Camada 1: nome_normalizado = query (match exato)."""
    sql = f"""
        SELECT {_WINE_COLUMNS}
        FROM wines
        WHERE nome_normalizado = %s {extra_where}
        {_ORDER_CLAUSE}
        LIMIT %s
    """
    params = [q_norm] + extra_params + [limit]
    return _execute_search(conn, sql, params)


def _search_prefix(conn, q_norm, limit, extra_where, extra_params):
    """Camada 2: nome_normalizado LIKE 'query%' (prefixo)."""
    sql = f"""
        SELECT {_WINE_COLUMNS}
        FROM wines
        WHERE nome_normalizado LIKE %s {extra_where}
        {_ORDER_CLAUSE}
        LIMIT %s
    """
    params = [f"{q_norm}%"] + extra_params + [limit]
    return _execute_search(conn, sql, params)


def _search_producer(conn, p_norm, limit, extra_where, extra_params):
    """Camada 3: match em produtor_normalizado (exato + prefixo)."""
    # Primeiro tenta exato no produtor
    sql = f"""
        SELECT {_WINE_COLUMNS}
        FROM wines
        WHERE produtor_normalizado = %s {extra_where}
        {_ORDER_CLAUSE}
        LIMIT %s
    """
    params = [p_norm] + extra_params + [limit]
    results = _execute_search(conn, sql, params)
    if results:
        return results

    # Depois prefixo no produtor
    sql = f"""
        SELECT {_WINE_COLUMNS}
        FROM wines
        WHERE produtor_normalizado LIKE %s {extra_where}
        {_ORDER_CLAUSE}
        LIMIT %s
    """
    params = [f"{p_norm}%"] + extra_params + [limit]
    return _execute_search(conn, sql, params)


def _search_fuzzy(conn, q_norm, limit, extra_where, extra_params):
    """Camada 4: busca fuzzy com pg_trgm. Fallback para LIKE contains se trgm falhar."""
    sql = f"""
        SELECT {_WINE_COLUMNS},
               similarity(nome_normalizado, %s) as sim
        FROM wines
        WHERE nome_normalizado %% %s {extra_where}
        ORDER BY sim DESC, {_CANONICAL_RANK} DESC, vivino_reviews DESC NULLS LAST
        LIMIT %s
    """
    params = [q_norm, q_norm] + extra_params + [limit]
    try:
        results = _execute_search(conn, sql, params)
        if results:
            for r in results:
                r.pop('sim', None)
            return results
    except (psycopg2.ProgrammingError, psycopg2.OperationalError, psycopg2.InterfaceError):
        # ProgrammingError: pg_trgm nao habilitado
        # OperationalError: timeout ou conexao SSL cortada
        # InterfaceError: conexao ja fechada
        try:
            conn.rollback()
        except Exception:
            pass

    # Fallback: LIKE contains (ultimo recurso)
    # Se a conexao morreu no fuzzy, esse fallback tambem vai falhar —
    # retorna vazio em vez de propagar o erro
    try:
        sql = f"""
            SELECT {_WINE_COLUMNS}
            FROM wines
            WHERE nome_normalizado LIKE %s {extra_where}
            {_ORDER_CLAUSE}
            LIMIT %s
        """
        params = [f"%{q_norm}%"] + extra_params + [limit]
        return _execute_search(conn, sql, params)
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        return []


def _execute_search(conn, sql, params, timeout_ms=5000):
    """Executa query de busca com timeout e retorna lista de dicts."""
    with conn.cursor() as cur:
        cur.execute(f"SET LOCAL statement_timeout = '{timeout_ms}'")
        cur.execute(sql, params)
        if cur.description is None:
            return []
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def _has_canonical(results):
    """Retorna True se pelo menos 1 resultado tem sinal canonico."""
    for r in results:
        if (r.get('vivino_rating') is not None
                or r.get('nota_wcf') is not None
                or r.get('winegod_score') is not None
                or r.get('vivino_id') is not None):
            return True
    return False


def _search_tokens(conn, q_norm, limit, extra_where, extra_params):
    """Busca por tokens LIKE para encontrar canonicos com nome em ordem diferente.

    Estrategia:
    1. Tenta AND de todos os tokens significativos (len >= 3)
    2. Se nao encontrar canonico, tenta removendo 1 token por vez
    Cada query e rapida (~2s) porque LIKE com tokens filtra bem.
    """
    tokens = [t for t in q_norm.split() if len(t) >= 3]
    if len(tokens) < 2:
        return []

    # Tentativa 1: todos os tokens
    results = _tokens_query(conn, tokens, limit, extra_where, extra_params)
    if _has_canonical(results):
        return results

    # Tentativa 2: remover 1 token por vez (priorizar subsets maiores)
    if len(tokens) >= 3:
        for skip_idx in range(len(tokens)):
            subset = [t for i, t in enumerate(tokens) if i != skip_idx]
            results = _tokens_query(conn, subset, limit, extra_where, extra_params)
            if _has_canonical(results):
                return results

    return results


def _tokens_query(conn, tokens, limit, extra_where, extra_params):
    """Executa query LIKE AND com lista de tokens. Timeout de 5s para proteger
    contra combinacoes de tokens comuns (ex: 'perez' + 'cruz')."""
    clauses = " AND ".join(f"nome_normalizado LIKE %s" for _ in tokens)
    params = [f"%{t}%" for t in tokens] + extra_params + [limit]
    sql = f"""
        SELECT {_WINE_COLUMNS}
        FROM wines
        WHERE {clauses} {extra_where}
        {_ORDER_CLAUSE}
        LIMIT %s
    """
    try:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '5s'")
            cur.execute(sql, params)
            if cur.description is None:
                return []
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]
    except (psycopg2.ProgrammingError, psycopg2.OperationalError, psycopg2.InterfaceError):
        try:
            conn.rollback()
        except Exception:
            pass
        return []


def _merge_results(primary, secondary, limit):
    """Mescla resultados sem duplicar IDs. Canonicos do secondary sobem ao topo."""
    seen_ids = {r['id'] for r in primary}
    canonical_new = []
    other_new = []
    for r in secondary:
        if r['id'] in seen_ids:
            continue
        seen_ids.add(r['id'])
        if _has_canonical([r]):
            canonical_new.append(r)
        else:
            other_new.append(r)
    merged = canonical_new + primary + other_new
    return merged[:limit]


def get_similar_wines(wine_id, limit=5):
    """Encontra vinhos similares por tipo, pais, regiao e faixa de preco."""
    key = cache_key("similar", wine_id=wine_id, limit=limit)
    cached = cache_get(key)
    if cached:
        return cached

    conn = get_connection()
    try:
        with conn.cursor() as cur:
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
                       winegod_score, nota_wcf, nota_wcf_sample_size
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
                           winegod_score, nota_wcf, nota_wcf_sample_size
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

            enrich_wines(results)

            result = {"wines": results, "total": len(results)}
            cache_set(key, result, TTL_SEARCH)
            return result
    finally:
        release_connection(conn)
