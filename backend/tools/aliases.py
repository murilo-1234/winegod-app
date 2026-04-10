"""Helper compartilhado para resolucao de wine_aliases.

Usado por search.py e details.py para enriquecer resultados de loja
com dados canonicos quando alias aprovado existir.
"""

import psycopg2

# Campos do canonico que sobrescrevem a source via COALESCE
_CANONICAL_FIELDS = (
    'vivino_rating', 'nota_wcf', 'nota_wcf_sample_size',
    'winegod_score', 'winegod_score_type', 'vivino_reviews', 'vivino_id',
)


def resolve_aliases(conn, results):
    """Resolve wine_aliases aprovados em uma lista de resultados.

    Para cada resultado que tem alias aprovado, enriquece com dados
    do canonico via COALESCE. Mantem nome/preco da source.

    Args:
        conn: conexao psycopg2 ativa
        results: lista de dicts com pelo menos 'id' key
    """
    if not results:
        return

    source_ids = [r['id'] for r in results]

    try:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '3000'")
            cur.execute("""
                SELECT wa.source_wine_id,
                       wc.id,
                       wc.vivino_rating,
                       wc.nota_wcf,
                       wc.nota_wcf_sample_size,
                       wc.winegod_score,
                       wc.winegod_score_type,
                       wc.vivino_reviews,
                       wc.vivino_id,
                       wc.produtor
                FROM wine_aliases wa
                JOIN wines wc ON wc.id = wa.canonical_wine_id
                WHERE wa.source_wine_id = ANY(%s)
                  AND wa.review_status = 'approved'
            """, (source_ids,))

            alias_map = {}
            for row in cur.fetchall():
                alias_map[row[0]] = {
                    'canonical_id': row[1],
                    'vivino_rating': row[2],
                    'nota_wcf': row[3],
                    'nota_wcf_sample_size': row[4],
                    'winegod_score': row[5],
                    'winegod_score_type': row[6],
                    'vivino_reviews': row[7],
                    'vivino_id': row[8],
                    'canonical_produtor': row[9],
                }
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return

    for r in results:
        canon = alias_map.get(r['id'])
        if not canon:
            continue
        r['canonical_id'] = canon['canonical_id']
        r['resolved_via'] = 'alias'
        for field in _CANONICAL_FIELDS:
            if r.get(field) is None and canon.get(field) is not None:
                r[field] = canon[field]
        if not r.get('produtor') and canon.get('canonical_produtor'):
            r['produtor'] = canon['canonical_produtor']

    # Dedup: se o canonico real ja aparece nos resultados E um alias
    # tambem aponta para ele, o alias e redundante. Tambem remove
    # aliases duplicados que apontam para o mesmo canonical_id.
    seen_canonical = set()
    to_remove = []
    # Primeira passada: marcar IDs canonicos que aparecem diretamente
    for r in results:
        if r.get('resolved_via') != 'alias':
            vid = r.get('vivino_id')
            if vid:
                seen_canonical.add(r['id'])
    # Segunda passada: marcar aliases redundantes
    for i, r in enumerate(results):
        if r.get('resolved_via') != 'alias':
            continue
        cid = r.get('canonical_id')
        if cid in seen_canonical:
            to_remove.append(i)
        else:
            seen_canonical.add(cid)
    # Remover de tras pra frente
    for i in reversed(to_remove):
        results.pop(i)


def resolve_alias_single(conn, result):
    """Resolve alias para um unico resultado (dict). Wrapper de resolve_aliases."""
    if not result or 'id' not in result:
        return
    results = [result]
    resolve_aliases(conn, results)
