#!/usr/bin/env python3
"""
dedup_crossref.py — Deduplicação cross-reference: vinhos de lojas (local) x Vivino (Render).

3 níveis de matching:
  L1: Nome normalizado exato (in-memory, muito rápido)
  L2: Fuzzy pg_trgm (batch queries no Render, similarity > 0.6)
  L3: Produtor + safra (in-memory, rápido)

Uso:
  python dedup_crossref.py          # todos os países
  python dedup_crossref.py br       # só Brasil
  python dedup_crossref.py br us    # Brasil e EUA
"""

import os
import re
import sys
import time
import unicodedata
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras

# ─── Config ──────────────────────────────────────────────────────────────────

RENDER_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://winegod_user:iNIIVWEOOCVWTCtgSNWtGlgn6RqFYT96@dpg-d6o56scr85hc73843pvg-a.oregon-postgres.render.com/winegod",
)
LOCAL_URL = os.getenv(
    "WINEGOD_LOCAL_URL",
    "postgresql://postgres:postgres123@localhost:5432/winegod_db",
)

PAISES = [
    "ae", "ar", "at", "au", "be", "bg", "br", "ca", "ch", "cl",
    "cn", "co", "cz", "de", "dk", "es", "fi", "fr", "gb", "ge",
    "gr", "hk", "hr", "hu", "ie", "il", "in", "it", "jp", "kr",
    "lu", "md", "mx", "nl", "no", "nz", "pe", "ph", "pl", "pt",
    "ro", "ru", "se", "sg", "th", "tr", "tw", "us", "uy", "za",
]

BATCH_INSERT = 500
BATCH_FUZZY = 500
MAX_FUZZY_PER_PAIS = 100_000


# ─── Utils ───────────────────────────────────────────────────────────────────

def normalizar(texto):
    """Lowercase, sem acentos, sem caracteres especiais."""
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKD", texto).encode("ASCII", "ignore").decode("ASCII")
    texto = texto.lower().strip()
    texto = re.sub(r"[^a-z0-9\s]", "", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto


def extract_domain(url):
    """Extrai domínio de uma URL, removendo www."""
    if not url:
        return None
    try:
        netloc = urlparse(url).netloc
        if not netloc and "//" not in url:
            netloc = urlparse("http://" + url).netloc
        return netloc.replace("www.", "").lower().strip() if netloc else None
    except Exception:
        return None


def table_exists(cur, name):
    cur.execute("SELECT EXISTS (SELECT 1 FROM pg_tables WHERE tablename = %s)", (name,))
    return cur.fetchone()[0]


# ─── Load helpers ────────────────────────────────────────────────────────────

def load_hash_set(conn):
    """Set de todos hash_dedup no Render (para pular vinhos já matchados)."""
    print("  Carregando hash_set...", end="", flush=True)
    cur = conn.cursor()
    cur.execute("SELECT hash_dedup FROM wines WHERE hash_dedup IS NOT NULL")
    result = set()
    while True:
        rows = cur.fetchmany(100_000)
        if not rows:
            break
        result.update(h for (h,) in rows)
    cur.close()
    print(f" {len(result):,}")
    return result


def load_domain_map(conn):
    """domínio -> store_id."""
    print("  Carregando domain_map...", end="", flush=True)
    cur = conn.cursor()
    cur.execute("SELECT id, dominio FROM stores WHERE dominio IS NOT NULL")
    result = {d: sid for sid, d in cur.fetchall()}
    cur.close()
    print(f" {len(result):,}")
    return result


def load_render_wines(conn, pais):
    """
    Carrega wines do Render para um país.
    Retorna (name_map, ps_map, count).
      name_map: normalizar(nome) -> [(wine_id, produtor_norm_raw, safra)]
      ps_map:   (normalizar(produtor), safra) -> [wine_id]
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT id, nome_normalizado, produtor_normalizado, safra
        FROM wines
        WHERE pais = %s AND nome_normalizado IS NOT NULL AND nome_normalizado != ''
    """, (pais,))
    rows = cur.fetchall()
    cur.close()

    name_map = {}
    ps_map = {}

    for wine_id, nome_norm, prod_norm, safra in rows:
        key = normalizar(nome_norm)
        if key:
            name_map.setdefault(key, []).append((wine_id, prod_norm, safra))

        if prod_norm and safra:
            ps_key = (normalizar(prod_norm), safra.strip())
            ps_map.setdefault(ps_key, []).append(wine_id)

    return name_map, ps_map, len(rows)


def load_local_wines(conn, pais):
    """Vinhos locais que TÊM fontes (JOIN com tabela de fontes)."""
    tab_v = f"vinhos_{pais}"
    tab_f = f"vinhos_{pais}_fontes"

    cur = conn.cursor()
    if not table_exists(cur, tab_v) or not table_exists(cur, tab_f):
        cur.close()
        return []

    cur.execute(f"""
        SELECT DISTINCT v.id, v.nome, v.produtor, v.safra, v.hash_dedup
        FROM {tab_v} v
        JOIN {tab_f} f ON f.vinho_id = v.id
    """)
    wines = cur.fetchall()
    cur.close()
    return wines


def load_fontes_batch(conn, pais, wine_ids):
    """Carrega fontes de vinhos locais em batch."""
    tab_f = f"vinhos_{pais}_fontes"
    cur = conn.cursor()
    fontes = {}

    ids = list(wine_ids)
    for i in range(0, len(ids), 10_000):
        chunk = ids[i : i + 10_000]
        cur.execute(f"""
            SELECT vinho_id, url_original, preco, moeda, disponivel,
                   descoberto_em, atualizado_em
            FROM {tab_f}
            WHERE vinho_id = ANY(%s)
        """, (chunk,))
        for row in cur.fetchall():
            fontes.setdefault(row[0], []).append(row[1:])

    cur.close()
    return fontes


# ─── Matching Level 1 — Exato ───────────────────────────────────────────────

def match_exact(local_wines, name_map, hash_set):
    """
    Match exato por nome normalizado (in-memory).
    Também desambigua múltiplos candidatos por produtor/safra.
    Retorna (matches, remaining).
    """
    matches = {}   # local_id -> wine_id
    remaining = []

    for local_id, nome, produtor, safra, hash_dedup in local_wines:
        # Pular já matchados por hash
        if hash_dedup and hash_dedup in hash_set:
            continue

        nome_norm = normalizar(nome)
        if not nome_norm:
            continue

        candidates = name_map.get(nome_norm, [])

        if len(candidates) == 1:
            matches[local_id] = candidates[0][0]
            continue

        if len(candidates) > 1:
            # Desambiguar por safra
            if safra:
                safra_str = str(safra).strip()
                filtered = [c for c in candidates if c[2] and c[2].strip() == safra_str]
                if len(filtered) == 1:
                    matches[local_id] = filtered[0][0]
                    continue

            # Desambiguar por produtor
            if produtor:
                prod_norm = normalizar(produtor)
                filtered = [c for c in candidates if c[1] and normalizar(c[1]) == prod_norm]
                if len(filtered) == 1:
                    matches[local_id] = filtered[0][0]
                    continue

        remaining.append((local_id, nome, produtor, safra))

    return matches, remaining


# ─── Matching Level 3 — Produtor + Safra ────────────────────────────────────

def match_produtor_safra(remaining, ps_map):
    """Match por produtor normalizado + safra (in-memory)."""
    matches = {}
    still_remaining = []

    for local_id, nome, produtor, safra in remaining:
        if produtor and safra:
            prod_key = normalizar(produtor)
            safra_str = str(safra).strip()
            if prod_key and safra_str:
                candidates = ps_map.get((prod_key, safra_str), [])
                if len(candidates) == 1:
                    matches[local_id] = candidates[0]
                    continue

        still_remaining.append((local_id, nome, produtor, safra))

    return matches, still_remaining


# ─── Matching Level 2 — Fuzzy pg_trgm ───────────────────────────────────────

def match_fuzzy(conn, pais, remaining, batch_size=BATCH_FUZZY):
    """
    Fuzzy matching com pg_trgm usando batch + temp table.
    Similarity >= 0.8: aceita se claramente melhor candidato.
    Similarity 0.6-0.8: valida com produtor.
    """
    if not remaining:
        return {}

    to_match = []
    for local_id, nome, produtor, _safra in remaining:
        nome_norm = normalizar(nome)
        if nome_norm and len(nome_norm) >= 5:
            to_match.append((local_id, nome_norm, normalizar(produtor) if produtor else ""))

    if not to_match:
        return {}

    if len(to_match) > MAX_FUZZY_PER_PAIS:
        print(f"      (limitando fuzzy a {MAX_FUZZY_PER_PAIS:,} de {len(to_match):,})")
        to_match = to_match[:MAX_FUZZY_PER_PAIS]

    cur = conn.cursor()
    cur.execute("SET pg_trgm.similarity_threshold = 0.6")

    matches = {}
    total = len(to_match)

    for i in range(0, total, batch_size):
        batch = to_match[i : i + batch_size]

        try:
            cur.execute("DROP TABLE IF EXISTS _dedup_batch")
            cur.execute("""
                CREATE TEMP TABLE _dedup_batch (
                    local_id integer,
                    nome_norm text,
                    produtor_norm text
                )
            """)
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO _dedup_batch (local_id, nome_norm, produtor_norm) VALUES %s",
                batch,
                page_size=batch_size,
            )

            cur.execute("""
                WITH ranked AS (
                    SELECT d.local_id, d.produtor_norm AS local_prod,
                           w.id AS wine_id, w.produtor_normalizado AS render_prod,
                           similarity(w.nome_normalizado, d.nome_norm) AS sim,
                           ROW_NUMBER() OVER (
                               PARTITION BY d.local_id
                               ORDER BY similarity(w.nome_normalizado, d.nome_norm) DESC
                           ) AS rn
                    FROM _dedup_batch d
                    JOIN wines w ON w.pais = %s AND w.nome_normalizado %% d.nome_norm
                )
                SELECT local_id, wine_id, sim, local_prod, render_prod
                FROM ranked
                WHERE rn <= 3
            """, (pais,))

            by_local = {}
            for lid, wid, sim, lprod, rprod in cur.fetchall():
                by_local.setdefault(lid, []).append((wid, sim, lprod, rprod))

            for lid, results in by_local.items():
                results.sort(key=lambda x: -x[1])
                best_wid, best_sim, lprod, rprod = results[0]

                if best_sim >= 0.8:
                    if len(results) == 1 or results[1][1] < best_sim - 0.05:
                        matches[lid] = best_wid
                elif best_sim >= 0.6:
                    if lprod and rprod:
                        lp = lprod.strip()
                        rp = normalizar(rprod)
                        if lp and rp and (lp in rp or rp in lp):
                            matches[lid] = best_wid

        except Exception as e:
            print(f"\n      [ERRO fuzzy batch {i}] {e}")
            conn.rollback()
            cur.execute("SET pg_trgm.similarity_threshold = 0.6")
            continue

        done = min(i + batch_size, total)
        if done % 5000 < batch_size or done == total:
            print(f"      fuzzy {done:,}/{total:,} -> {len(matches):,} matches", flush=True)

    cur.execute("DROP TABLE IF EXISTS _dedup_batch")
    cur.execute("SET pg_trgm.similarity_threshold = 0.3")
    cur.close()

    return matches


# ─── Insert wine_sources ────────────────────────────────────────────────────

def _flush_sources(cur, values):
    psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO wine_sources
            (wine_id, store_id, url, preco, moeda, disponivel, descoberto_em, atualizado_em)
        VALUES %s
        ON CONFLICT (wine_id, store_id, url) DO NOTHING
        """,
        values,
        page_size=BATCH_INSERT,
    )
    return cur.rowcount


def insert_wine_sources(conn, all_matches, fontes, domain_map):
    """Insere matches em wine_sources. Retorna (inseridos, sem_loja)."""
    cur = conn.cursor()
    batch = []
    inserted = 0
    no_store = 0

    for local_id, wine_id in all_matches.items():
        for url, preco, moeda, disponivel, desc_em, atua_em in fontes.get(local_id, []):
            dom = extract_domain(url)
            store_id = domain_map.get(dom) if dom else None
            if not store_id:
                no_store += 1
                continue

            batch.append((
                wine_id, store_id, url,
                preco, moeda,
                disponivel if disponivel is not None else True,
                desc_em, atua_em,
            ))

            if len(batch) >= BATCH_INSERT:
                inserted += _flush_sources(cur, batch)
                batch = []

    if batch:
        inserted += _flush_sources(cur, batch)

    conn.commit()
    cur.close()
    return inserted, no_store


# ─── Update preços ──────────────────────────────────────────────────────────

def update_prices(conn):
    """Atualiza preco_min/preco_max/total_fontes em wines."""
    print("\nAtualizando precos em wines...", end="", flush=True)
    cur = conn.cursor()
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
    conn.commit()
    cur.close()
    print(f" {updated:,} wines atualizados")
    return updated


# ─── Processar país ─────────────────────────────────────────────────────────

def processar_pais(pais, conn_local, conn_render, hash_set, domain_map):
    t0 = time.time()

    # Carregar vinhos locais com fontes
    local_wines = load_local_wines(conn_local, pais)
    if not local_wines:
        return None

    # Carregar wines do Render para este país
    name_map, ps_map, render_count = load_render_wines(conn_render, pais)
    if not name_map:
        print(f"  [{pais.upper()}] {len(local_wines):,} local | 0 Render wines | skip")
        return None

    # Level 1: match exato
    l1_matches, remaining = match_exact(local_wines, name_map, hash_set)

    # Level 3: produtor + safra (antes de L2 pois é mais rápido)
    l3_matches, remaining = match_produtor_safra(remaining, ps_map)

    # Level 2: fuzzy pg_trgm
    l2_matches = {}
    if remaining:
        print(f"    [{pais.upper()}] fuzzy: {len(remaining):,} restantes vs {render_count:,} Render")
        try:
            l2_matches = match_fuzzy(conn_render, pais, remaining)
        except Exception as e:
            print(f"    [ERRO fuzzy {pais.upper()}] {e}")
            conn_render.rollback()

    # Juntar todos os matches
    all_matches = {}
    all_matches.update(l1_matches)
    all_matches.update(l3_matches)
    all_matches.update(l2_matches)

    # Carregar fontes e inserir em wine_sources
    inserted = 0
    no_store = 0
    if all_matches:
        fontes = load_fontes_batch(conn_local, pais, set(all_matches.keys()))
        inserted, no_store = insert_wine_sources(conn_render, all_matches, fontes, domain_map)

    elapsed = time.time() - t0

    # Contar hash skips
    skipped_hash = sum(1 for _, _, _, _, h in local_wines if h and h in hash_set)

    stats = {
        "total": len(local_wines),
        "skipped_hash": skipped_hash,
        "l1": len(l1_matches),
        "l2": len(l2_matches),
        "l3": len(l3_matches),
        "inserted": inserted,
        "no_store": no_store,
    }

    total_match = stats["l1"] + stats["l2"] + stats["l3"]
    print(
        f"  [{pais.upper()}] {stats['total']:,} local | "
        f"hash:{stats['skipped_hash']:,} | "
        f"L1:{stats['l1']:,} L2:{stats['l2']:,} L3:{stats['l3']:,} = {total_match:,} | "
        f"ins:{stats['inserted']:,} | {elapsed:.0f}s"
    )

    return stats


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()

    # Aceitar países como argumentos
    paises = PAISES
    if len(sys.argv) > 1:
        paises = [p.lower() for p in sys.argv[1:]]
        print(f"Processando: {', '.join(p.upper() for p in paises)}")

    print("Conectando...")
    conn_local = psycopg2.connect(LOCAL_URL)
    conn_local.autocommit = False
    conn_render = psycopg2.connect(RENDER_URL)
    conn_render.autocommit = False

    try:
        # Mapas globais
        hash_set = load_hash_set(conn_render)
        domain_map = load_domain_map(conn_render)

        print(f"\nProcessando {len(paises)} paises...\n")

        totals = {
            "total": 0, "skipped_hash": 0,
            "l1": 0, "l2": 0, "l3": 0,
            "inserted": 0, "no_store": 0,
        }

        for pais in paises:
            stats = processar_pais(pais, conn_local, conn_render, hash_set, domain_map)
            if stats:
                for k in totals:
                    totals[k] += stats[k]

        # Resumo
        total_match = totals["l1"] + totals["l2"] + totals["l3"]
        print(f"\n{'=' * 60}")
        print("TOTAIS")
        print(f"{'=' * 60}")
        print(f"  Vinhos locais processados: {totals['total']:,}")
        print(f"  Ja com hash match:         {totals['skipped_hash']:,}")
        print(f"  Level 1 (exato):           {totals['l1']:,}")
        print(f"  Level 2 (fuzzy):           {totals['l2']:,}")
        print(f"  Level 3 (produtor+safra):  {totals['l3']:,}")
        print(f"  TOTAL matches novos:       {total_match:,}")
        print(f"  Inseridos em wine_sources: {totals['inserted']:,}")
        print(f"  Sem loja (dominio):        {totals['no_store']:,}")

        # Atualizar preços
        if totals["inserted"] > 0:
            update_prices(conn_render)

    finally:
        conn_local.close()
        conn_render.close()

    elapsed = time.time() - t0
    print(f"\nTempo total: {elapsed / 60:.1f} minutos")


if __name__ == "__main__":
    main()
