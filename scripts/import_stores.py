"""
import_stores.py — Importa lojas e wine_sources do banco LOCAL para o Render.

Passos:
  1. Importar ~12.8K lojas (status=sucesso, dificuldade<5) para stores no Render
  2. Carregar mapas hash->wine_id e dominio->store_id em memoria
  3. Para cada pais, cruzar vinhos_{pais}_fontes com wines via hash_dedup
  4. Atualizar preco_min/preco_max/total_fontes em wines
"""

import os
import sys
import time
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras
import _env

# ─── Conexoes ────────────────────────────────────────────────────────────────

LOCAL_DB = os.getenv(
    "LOCAL_DB",
    "postgresql://postgres:postgres123@localhost:5432/winegod_db",
)
RENDER_DB = os.environ["getenv" == "getenv" and "DATABASE_URL" or "DATABASE_URL"]

PAISES = [
    "ae", "ar", "at", "au", "be", "bg", "br", "ca", "ch", "cl",
    "cn", "co", "cz", "de", "dk", "es", "fi", "fr", "gb", "ge",
    "gr", "hk", "hr", "hu", "ie", "il", "in", "it", "jp", "kr",
    "lu", "md", "mx", "nl", "no", "nz", "pe", "ph", "pl", "pt",
    "ro", "ru", "se", "sg", "th", "tr", "tw", "us", "uy", "za",
]

BATCH_STORES = 500
BATCH_SOURCES = 1000


def extract_domain(url):
    """Extrai dominio de uma URL, removendo www."""
    if not url:
        return None
    try:
        netloc = urlparse(url).netloc
        if not netloc and "//" not in url:
            netloc = urlparse("http://" + url).netloc
        return netloc.replace("www.", "").lower().strip() if netloc else None
    except Exception:
        return None


def connect(dsn, name="db"):
    """Conecta no banco e retorna conexao."""
    print(f"  Conectando em {name}...")
    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    print(f"  {name} OK")
    return conn


# ─── PASSO 1: Importar lojas ────────────────────────────────────────────────

def import_stores(local_conn, render_conn):
    print("\n" + "=" * 60)
    print("PASSO 1 — Importar lojas para stores no Render")
    print("=" * 60)

    local_cur = local_conn.cursor()
    render_cur = render_conn.cursor()

    local_cur.execute("""
        SELECT nome, url, url_normalizada, pais_codigo, plataforma,
               vinhos_extraidos, tier_usado, modelo_ia_usado,
               tipo_loja, regiao, cidade, notas,
               classificado_em, atualizado_em
        FROM lojas_scraping
        WHERE status = 'sucesso'
          AND (dificuldade IS NULL OR dificuldade < 5)
        ORDER BY id
    """)

    rows = local_cur.fetchall()
    total = len(rows)
    print(f"  Lojas com sucesso (dificuldade<5): {total}")

    inserted = 0
    skipped = 0

    for i in range(0, total, BATCH_STORES):
        batch = rows[i : i + BATCH_STORES]
        values = []

        for row in batch:
            (nome, url, url_normalizada, pais_codigo, plataforma,
             vinhos_extraidos, tier_usado, modelo_ia_usado,
             tipo_loja, regiao, cidade, notas,
             classificado_em, atualizado_em) = row

            dominio = extract_domain(url_normalizada or url)
            if not dominio:
                skipped += 1
                continue

            como_descobriu = None
            if tier_usado:
                como_descobriu = f"tier_{tier_usado}"
            elif modelo_ia_usado:
                como_descobriu = modelo_ia_usado

            # Truncar campos VARCHAR para caber no schema do Render
            _tipo = (tipo_loja or "")[:50] or None
            _plat = (plataforma or "")[:50] or None
            _como = (como_descobriu or "")[:50] or None
            _reg = (regiao or "")[:100] or None
            _cid = (cidade or "")[:100] or None

            values.append((
                (nome or "")[:200] or None, url, dominio[:200],
                pais_codigo, _tipo, _plat,
                _reg, _cid, None, vinhos_extraidos or 0, True,
                _como, notas, classificado_em, atualizado_em,
            ))

        if values:
            psycopg2.extras.execute_values(
                render_cur,
                """
                INSERT INTO stores
                    (nome, url, dominio, pais, tipo, plataforma,
                     regiao, cidade, abrangencia, total_vinhos, ativa,
                     como_descobriu, observacoes, descoberta_em, atualizada_em)
                VALUES %s
                ON CONFLICT (dominio) DO NOTHING
                """,
                values,
                page_size=BATCH_STORES,
            )
            inserted += render_cur.rowcount

        if (i + BATCH_STORES) % 1000 < BATCH_STORES or i + BATCH_STORES >= total:
            print(f"  ... {min(i + BATCH_STORES, total):,}/{total:,}  "
                  f"(inseridos: {inserted:,}, pulados: {skipped:,})")

    render_conn.commit()
    print(f"\n  TOTAL inseridos em stores: {inserted:,}")
    print(f"  Pulados (sem dominio): {skipped:,}")
    return inserted


# ─── PASSO 2 + 3: Carregar mapas e popular wine_sources ─────────────────────

def load_hash_map(render_conn):
    """Carrega hash_dedup -> wine_id do Render em memoria."""
    print("\n  Carregando mapa hash_dedup -> wine_id ...")
    cur = render_conn.cursor()
    cur.execute("SELECT id, hash_dedup FROM wines WHERE hash_dedup IS NOT NULL")
    hash_to_id = {}
    while True:
        rows = cur.fetchmany(100_000)
        if not rows:
            break
        for wine_id, h in rows:
            hash_to_id[h] = wine_id
    cur.close()
    print(f"  Mapa carregado: {len(hash_to_id):,} hashes")
    return hash_to_id


def load_domain_map(render_conn):
    """Carrega dominio -> store_id do Render em memoria."""
    print("  Carregando mapa dominio -> store_id ...")
    cur = render_conn.cursor()
    cur.execute("SELECT id, dominio FROM stores WHERE dominio IS NOT NULL")
    domain_to_id = {row[1]: row[0] for row in cur.fetchall()}
    cur.close()
    print(f"  Mapa carregado: {len(domain_to_id):,} dominios")
    return domain_to_id


# DQ V3 Escopo 6 -- nova porta unica de ingestao.
# Versao DEPRECATED abaixo (`import_wine_sources`) continua funcionando para
# rollback rapido, mas em producao voce deve usar
# `import_wine_sources_via_bulk`, que consolida em
# `backend.services.bulk_ingest.process_sources_only` -- o pipeline central
# DQ V3 Escopo 6.

def import_wine_sources_via_bulk(local_conn, hash_to_id, domain_to_id,
                                  dry_run=False, run_id=None,
                                  source_label="import_stores_v6",
                                  pais_filter=None, limit=None,
                                  insert_only=False, render_conn=None):
    """Versao consolidada do PASSO 3 usando process_sources_only.

    Substituicao direta de `import_wine_sources`. Mesmo comportamento
    funcional (itera vinhos_{pais}_fontes, resolve hash -> wine_id, mapeia
    dominio -> store_id, popula wine_sources). A diferenca: ESCRITA vai
    centralizada pelo pipeline unico do Escopo 6 (nao faz mais INSERT
    paralelo direto), o que preserva o contrato de guardrail, FK
    prevalidation, deduplicacao por (wine_id, store_id, url) e tracking
    por `ingestion_run_id`.

    Args:
        local_conn: conexao ao banco LOCAL (leitura de fontes).
        hash_to_id: mapa hash_dedup -> wine_id ja carregado.
        domain_to_id: mapa dominio -> store_id ja carregado.
        dry_run: se True, nenhuma escrita no Render.
        run_id: opcional, amarra tracking granular.
        source_label: string livre para `wine_sources.fontes` e run_log.
    """
    # Import local para nao forcar dependencia do backend se o script for
    # carregado em um ambiente minimo.
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from services.bulk_ingest import process_sources_only

    print("\n" + "=" * 60)
    print(f"PASSO 3 (via bulk_ingest) -- dry_run={dry_run} "
          f"pais_filter={pais_filter} limit={limit}")
    print("=" * 60)

    local_cur = local_conn.cursor()

    # DQ V3 Escopo 6 (piloto pequeno):
    # `pais_filter` limita a iteracao a uma lista de paises (ex: ["lu"]).
    # `limit` corta o total de ITEMS montados globalmente apos filtros (nao
    # rows do SELECT) para viabilizar piloto real pequeno sem varrer o pais
    # inteiro. None = sem limite (comportamento original).
    paises_iter = PAISES
    if pais_filter:
        if isinstance(pais_filter, str):
            pais_filter = [p.strip().lower() for p in pais_filter.split(",") if p.strip()]
        paises_iter = [p for p in PAISES if p in pais_filter]
        if not paises_iter:
            print(f"  [WARN] pais_filter={pais_filter} nao casa nenhum pais da lista PAISES")

    total_processados = 0
    total_items_montados = 0
    total_sem_wine = 0
    total_sem_store = 0
    limit_reached = False

    grand = {
        "sources_in_input": 0, "sources_inserted": 0, "sources_updated": 0,
        "sources_rejected_count": 0, "sources_duplicates_in_input": 0,
        "would_insert_sources": 0, "would_update_sources": 0,
        "batches": 0, "errors": [],
    }

    for pais in paises_iter:
        if limit_reached:
            break
        tab_fontes = f"vinhos_{pais}_fontes"
        tab_vinhos = f"vinhos_{pais}"

        local_cur.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_tables WHERE tablename = %s)",
            (tab_fontes,),
        )
        if not local_cur.fetchone()[0]:
            print(f"  [{pais.upper()}] tabela {tab_fontes} nao existe, pulando")
            continue

        local_cur.execute(f"""
            SELECT v.hash_dedup, f.url_original, f.preco, f.moeda, f.disponivel
            FROM {tab_fontes} f
            JOIN {tab_vinhos} v ON v.id = f.vinho_id
            WHERE v.hash_dedup IS NOT NULL
        """)

        pais_items: list[dict] = []
        pais_total = 0
        pais_sem_wine = 0
        pais_sem_store = 0

        while True:
            rows = local_cur.fetchmany(5000)
            if not rows:
                break
            for hash_dedup, url_original, preco, moeda, disponivel in rows:
                pais_total += 1
                wine_id = hash_to_id.get(hash_dedup)
                if not wine_id:
                    pais_sem_wine += 1
                    continue
                dominio = extract_domain(url_original)
                store_id = domain_to_id.get(dominio) if dominio else None
                if not store_id:
                    pais_sem_store += 1
                    continue
                pais_items.append({
                    "wine_id": wine_id,
                    "sources": [{
                        "store_id": store_id,
                        "url": url_original,
                        "preco": preco,
                        "moeda": moeda,
                        "disponivel": disponivel if disponivel is not None else True,
                    }],
                })
                # Cap de coleta por pais. Em modo `insert_only`, o corte
                # verdadeiro acontece apos o filtro anti-existence -- entao
                # coletamos um pool maior (limit * 20) para ter margem,
                # e interrompemos a coleta por pais ao atingir o pool.
                # `limit_reached` GLOBAL (entre paises) so e acionado mais
                # abaixo, depois do anti-existence confirmar que ja temos
                # items INSERT-only suficientes.
                if limit is not None:
                    pool_cap = (limit * 100) if insert_only else limit
                    if (total_items_montados + len(pais_items)) >= pool_cap:
                        break
            # Saida do while externo (fetchmany): quando a coleta do pool
            # do pais ja atingiu o cap, ou quando limit_reached global
            # (acionado por outro pais, improvavel aqui).
            if limit_reached:
                break
            if limit is not None:
                pool_cap = (limit * 100) if insert_only else limit
                if (total_items_montados + len(pais_items)) >= pool_cap:
                    break

        # DQ V3 Escopo 6 (piloto INSERT-only):
        # Anti-existence -- consulta batchada no Render e remove items
        # cujas (wine_id, store_id, url) JA EXISTEM em wine_sources. Isso
        # garante que o piloto seja 100% INSERT real. Depois aplica o
        # corte final de `limit`.
        if insert_only and pais_items and render_conn is not None:
            from services.bulk_ingest import _resolve_existing_sources  # noqa
            keys = [
                (it["wine_id"], it["sources"][0]["store_id"], it["sources"][0]["url"])
                for it in pais_items
            ]
            existing = _resolve_existing_sources(render_conn, keys)
            pre = len(pais_items)
            pais_items = [
                it for it in pais_items
                if (it["wine_id"],
                    it["sources"][0]["store_id"],
                    it["sources"][0]["url"]) not in existing
            ]
            print(f"  [{pais.upper()}] anti-existence: {pre} -> {len(pais_items)} "
                  f"(descartados {pre - len(pais_items)} ja presentes em wine_sources)")
            # Recorta ao limit depois do anti-existence (cap global sobre
            # INSERT-only real). `total_items_montados` ainda nao inclui
            # estes items (eles so vao contar quando chamarmos o pipeline).
            if limit is not None:
                restante = limit - total_items_montados
                if restante <= 0:
                    pais_items = []
                elif len(pais_items) > restante:
                    pais_items = pais_items[:restante]
                if (total_items_montados + len(pais_items)) >= limit:
                    limit_reached = True

        if pais_items:
            r = process_sources_only(
                pais_items,
                dry_run=dry_run,
                source=f"{source_label}:{pais}",
                run_id=run_id,
            )
            for k in ("sources_in_input", "sources_inserted", "sources_updated",
                      "sources_rejected_count", "sources_duplicates_in_input",
                      "would_insert_sources", "would_update_sources", "batches"):
                grand[k] += r.get(k, 0)
            if r.get("errors"):
                grand["errors"].extend(r["errors"])

        total_processados += pais_total
        total_items_montados += len(pais_items)
        total_sem_wine += pais_sem_wine
        total_sem_store += pais_sem_store

        if pais_total > 0:
            print(f"  [{pais.upper()}] fontes: {pais_total:,}  "
                  f"items_montados: {len(pais_items):,}  "
                  f"sem_wine: {pais_sem_wine:,}  sem_store: {pais_sem_store:,}")

    print(f"\n  TOTAL fontes processadas: {total_processados:,}")
    print(f"  TOTAL items montados: {total_items_montados:,}")
    print(f"  TOTAL sem_wine: {total_sem_wine:,} | sem_store: {total_sem_store:,}")
    print(f"  RESULT process_sources_only: {grand}")
    return grand


def import_wine_sources(local_conn, render_conn, hash_to_id, domain_to_id):
    """DEPRECATED (DQ V3 Escopo 6). Mantido para rollback rapido.

    Use `import_wine_sources_via_bulk` em producao. Esta versao escreve
    direto em `wine_sources` via INSERT paralelo, sem passar pelo pipeline
    central -- foge do guardrail do DQ V3.
    """
    import warnings
    warnings.warn(
        "import_wine_sources esta DEPRECATED (DQ V3 Escopo 6). "
        "Use import_wine_sources_via_bulk.",
        DeprecationWarning,
        stacklevel=2,
    )
    print("\n" + "=" * 60)
    print("PASSO 3 (DEPRECATED) — Popular wine_sources direto")
    print("=" * 60)

    local_cur = local_conn.cursor()
    render_cur = render_conn.cursor()

    total_inserted = 0
    total_no_wine = 0
    total_no_store = 0
    total_processed = 0

    for pais in PAISES:
        tab_fontes = f"vinhos_{pais}_fontes"
        tab_vinhos = f"vinhos_{pais}"

        # Verificar se tabelas existem
        local_cur.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_tables WHERE tablename = %s)",
            (tab_fontes,),
        )
        if not local_cur.fetchone()[0]:
            print(f"  [{pais.upper()}] tabela {tab_fontes} nao existe, pulando")
            continue

        # Ler fontes JOIN vinhos para pegar hash_dedup
        local_cur.execute(f"""
            SELECT v.hash_dedup, f.url_original, f.preco, f.moeda,
                   f.disponivel, f.descoberto_em, f.atualizado_em
            FROM {tab_fontes} f
            JOIN {tab_vinhos} v ON v.id = f.vinho_id
            WHERE v.hash_dedup IS NOT NULL
        """)

        pais_inserted = 0
        pais_no_wine = 0
        pais_no_store = 0
        pais_total = 0
        batch_values = []

        while True:
            rows = local_cur.fetchmany(5000)
            if not rows:
                break

            for hash_dedup, url_original, preco, moeda, disponivel, descoberto_em, atualizado_em in rows:
                pais_total += 1

                wine_id = hash_to_id.get(hash_dedup)
                if not wine_id:
                    pais_no_wine += 1
                    continue

                dominio = extract_domain(url_original)
                store_id = domain_to_id.get(dominio) if dominio else None
                if not store_id:
                    pais_no_store += 1
                    continue

                batch_values.append((
                    wine_id, store_id, url_original,
                    preco, moeda,
                    disponivel if disponivel is not None else True,
                    descoberto_em, atualizado_em,
                ))

                if len(batch_values) >= BATCH_SOURCES:
                    pais_inserted += _flush_sources(render_cur, batch_values)
                    batch_values = []

        # Flush remaining
        if batch_values:
            pais_inserted += _flush_sources(render_cur, batch_values)

        render_conn.commit()

        total_inserted += pais_inserted
        total_no_wine += pais_no_wine
        total_no_store += pais_no_store
        total_processed += pais_total

        if pais_total > 0:
            print(f"  [{pais.upper()}] fontes: {pais_total:,}  "
                  f"inseridos: {pais_inserted:,}  "
                  f"sem wine: {pais_no_wine:,}  "
                  f"sem store: {pais_no_store:,}")

    print(f"\n  TOTAL processados: {total_processed:,}")
    print(f"  TOTAL inseridos em wine_sources: {total_inserted:,}")
    print(f"  Sem match wine (hash): {total_no_wine:,}")
    print(f"  Sem match store (dominio): {total_no_store:,}")
    return total_inserted


def _flush_sources(cur, values):
    """Insere batch de wine_sources."""
    psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO wine_sources
            (wine_id, store_id, url, preco, moeda, disponivel, descoberto_em, atualizado_em)
        VALUES %s
        ON CONFLICT (wine_id, store_id, url) DO NOTHING
        """,
        values,
        page_size=BATCH_SOURCES,
    )
    return cur.rowcount


# ─── PASSO 4: Atualizar preco_min/preco_max/total_fontes ────────────────────

def update_wine_prices(render_conn):
    print("\n" + "=" * 60)
    print("PASSO 4 — Atualizar preco_min/preco_max/total_fontes em wines")
    print("=" * 60)

    cur = render_conn.cursor()
    cur.execute("""
        UPDATE wines w SET
            preco_min = sub.min_preco,
            preco_max = sub.max_preco,
            total_fontes = sub.total
        FROM (
            SELECT wine_id,
                MIN(preco) FILTER (WHERE preco > 0) AS min_preco,
                MAX(preco) AS max_preco,
                COUNT(DISTINCT store_id) AS total
            FROM wine_sources
            WHERE disponivel = TRUE AND preco > 0
            GROUP BY wine_id
        ) sub
        WHERE w.id = sub.wine_id
    """)
    updated = cur.rowcount
    render_conn.commit()
    print(f"  Wines atualizados com precos: {updated:,}")
    return updated


# ─── VERIFICACAO ─────────────────────────────────────────────────────────────

def verify(render_conn):
    print("\n" + "=" * 60)
    print("VERIFICACAO")
    print("=" * 60)

    cur = render_conn.cursor()

    cur.execute("SELECT count(*) FROM stores")
    print(f"  stores: {cur.fetchone()[0]:,}")

    cur.execute("SELECT pais, count(*) FROM stores GROUP BY pais ORDER BY count(*) DESC LIMIT 10")
    print("  Top 10 paises (stores):")
    for pais, cnt in cur.fetchall():
        print(f"    {pais}: {cnt:,}")

    cur.execute("SELECT count(*) FROM wine_sources")
    print(f"\n  wine_sources: {cur.fetchone()[0]:,}")

    cur.execute("SELECT count(*) FROM wines WHERE preco_min IS NOT NULL")
    print(f"  wines com preco: {cur.fetchone()[0]:,}")

    cur.execute("""
        SELECT s.nome, s.pais, count(*) AS vinhos
        FROM wine_sources ws JOIN stores s ON ws.store_id = s.id
        GROUP BY s.nome, s.pais
        ORDER BY vinhos DESC LIMIT 10
    """)
    print("\n  Top 10 lojas por vinhos:")
    for nome, pais, vinhos in cur.fetchall():
        safe_nome = nome.encode("ascii", "replace").decode("ascii") if nome else "?"
        print(f"    {safe_nome} ({pais}): {vinhos:,}")


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()

    # Aceitar argumento para rodar passo especifico
    step = sys.argv[1] if len(sys.argv) > 1 else "all"

    print("Conectando nos bancos...")
    local_conn = connect(LOCAL_DB, "LOCAL")
    render_conn = connect(RENDER_DB, "RENDER")

    try:
        if step in ("all", "1", "stores"):
            import_stores(local_conn, render_conn)

        if step in ("all", "2", "3", "sources"):
            hash_to_id = load_hash_map(render_conn)
            domain_to_id = load_domain_map(render_conn)
            # DQ V3 Escopo 6: pipeline central. Para rollback ao antigo,
            # setar env var IMPORT_STORES_LEGACY=1.
            if os.getenv("IMPORT_STORES_LEGACY") == "1":
                import_wine_sources(local_conn, render_conn, hash_to_id, domain_to_id)
            else:
                limit_env = os.getenv("IMPORT_STORES_LIMIT")
                import_wine_sources_via_bulk(
                    local_conn, hash_to_id, domain_to_id,
                    dry_run=(os.getenv("IMPORT_STORES_DRY_RUN") == "1"),
                    run_id=os.getenv("IMPORT_STORES_RUN_ID") or None,
                    pais_filter=os.getenv("IMPORT_STORES_PAIS") or None,
                    limit=(int(limit_env) if limit_env and limit_env.isdigit() else None),
                    insert_only=(os.getenv("IMPORT_STORES_INSERT_ONLY") == "1"),
                    render_conn=render_conn,
                )

        if step in ("all", "4", "prices"):
            update_wine_prices(render_conn)

        verify(render_conn)

    finally:
        local_conn.close()
        render_conn.close()

    elapsed = time.time() - t0
    print(f"\nTempo total: {elapsed / 60:.1f} minutos")


if __name__ == "__main__":
    main()
