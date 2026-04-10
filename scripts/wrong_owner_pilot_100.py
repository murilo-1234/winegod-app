"""
Micro-piloto wrong_owner: 100 linhas com prova forte.
DELETE da linha errada + INSERT no owner correto.
Auto-abort se qualquer inconsistencia.
"""
import csv
import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse
import _env

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import psycopg2

RENDER_DB = os.environ["DATABASE_URL"]

SOURCE_CSV = os.path.join(os.path.dirname(__file__), "wrong_owner_pilot_candidates.csv")
PILOT_CSV = os.path.join(os.path.dirname(__file__), "wrong_owner_pilot_100.csv")
REVERT_CSV = os.path.join(os.path.dirname(__file__), "wrong_owner_pilot_100_revert.csv")

MIN_PATH_LEN = 15  # path minimo para considerar URL de produto


def is_product_url(url):
    """Rejeita homepages, raiz, paths curtos ou genericos."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")
        # Rejeitar raiz
        if not path or path == "":
            return False
        # Rejeitar paths muito curtos (homepage, categorias)
        if len(path) < MIN_PATH_LEN:
            return False
        # Rejeitar paths que parecem categorias genericas
        parts = [p for p in path.split("/") if p]
        if len(parts) < 2 and not parsed.query:
            # /products ou /wines sozinho = categoria, nao produto
            return False
        return True
    except Exception:
        return False


def main():
    print("=" * 80, flush=True)
    print("MICRO-PILOTO WRONG_OWNER: 100 LINHAS", flush=True)
    print("=" * 80, flush=True)

    # Carregar CSV fonte
    with open(SOURCE_CSV, encoding="utf-8") as f:
        all_cases = list(csv.DictReader(f))
    print(f"CSV fonte: {len(all_cases):,} linhas", flush=True)

    # Filtrar
    filtered = []
    rejeitados = {"homepage/raiz": 0, "path curto": 0, "sem dados": 0}

    for c in all_cases:
        url = c["url"]
        exp = c["expected_wine_id"]
        act = c["actual_wine_id"]
        sid = c["store_id"]

        if not url or not exp or not act or not sid:
            rejeitados["sem dados"] += 1
            continue

        if not is_product_url(url):
            rejeitados["homepage/raiz"] += 1
            continue

        filtered.append(c)

    print(f"Apos filtros: {len(filtered):,} casos fortes", flush=True)
    print(f"Rejeitados: {rejeitados}", flush=True)

    if len(filtered) < 100:
        print(f"\n*** MENOS DE 100 CASOS FORTES ({len(filtered)}). Usando todos. ***", flush=True)

    pilot = filtered[:100]
    print(f"Piloto: {len(pilot)} linhas", flush=True)

    # Conectar ao Render
    rc = psycopg2.connect(
        RENDER_DB, options="-c statement_timeout=300000",
        keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=5,
    )
    r = rc.cursor()

    # ══════════════════════════════════════════════════════════════════════════
    # ARTEFATO 1: CSV do piloto
    # ══════════════════════════════════════════════════════════════════════════
    with open(PILOT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "url", "store_id", "expected_wine_id", "actual_wine_id", "clean_id", "pais",
        ])
        writer.writeheader()
        writer.writerows(pilot)
    print(f"\nCSV piloto: {PILOT_CSV}", flush=True)

    # ══════════════════════════════════════════════════════════════════════════
    # ARTEFATO 2: CSV de revert (snapshot ANTES do delete)
    # ══════════════════════════════════════════════════════════════════════════
    print("\nColetando snapshot para revert...", flush=True)
    revert_rows = []
    inconsistencias = []

    for c in pilot:
        url = c["url"]
        act_wine_id = int(c["actual_wine_id"])
        exp_wine_id = int(c["expected_wine_id"])
        store_id = int(c["store_id"])

        # Buscar a linha atual em wine_sources
        r.execute("""
            SELECT id, wine_id, store_id, url, preco, moeda, disponivel, descoberto_em, atualizado_em
            FROM wine_sources
            WHERE wine_id = %s AND url = %s
            LIMIT 1
        """, (act_wine_id, url))
        row = r.fetchone()

        if not row:
            inconsistencias.append(f"URL nao encontrada em wine_sources: wine_id={act_wine_id} url={url[:60]}")
            continue

        ws_id, ws_wine, ws_store, ws_url, ws_preco, ws_moeda, ws_disp, ws_desc, ws_atua = row

        # Verificar consistencia
        if ws_wine != act_wine_id:
            inconsistencias.append(f"wine_id diverge: esperado={act_wine_id} encontrado={ws_wine}")
            continue

        revert_rows.append({
            "ws_id": ws_id,
            "wine_id_errado": ws_wine,
            "store_id": ws_store,
            "url": ws_url,
            "preco": ws_preco,
            "moeda": ws_moeda,
            "disponivel": ws_disp,
            "descoberto_em": str(ws_desc),
            "atualizado_em": str(ws_atua),
            "wine_id_correto": exp_wine_id,
        })

    print(f"  Linhas para revert: {len(revert_rows)}", flush=True)
    print(f"  Inconsistencias: {len(inconsistencias)}", flush=True)

    if inconsistencias:
        print(f"\n  *** INCONSISTENCIAS DETECTADAS ***", flush=True)
        for inc in inconsistencias[:10]:
            print(f"    {inc}", flush=True)

    # Auto-abort se muitas inconsistencias
    if len(inconsistencias) > len(pilot) * 0.1:
        print(f"\n  *** AUTO-ABORT: {len(inconsistencias)} inconsistencias (>{len(pilot)*0.1:.0f} limite) ***", flush=True)
        r.close(); rc.close()
        return

    # Escrever CSV de revert
    with open(REVERT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "ws_id", "wine_id_errado", "store_id", "url", "preco", "moeda",
            "disponivel", "descoberto_em", "atualizado_em", "wine_id_correto",
        ])
        writer.writeheader()
        writer.writerows(revert_rows)
    print(f"  CSV revert: {REVERT_CSV}", flush=True)

    # ══════════════════════════════════════════════════════════════════════════
    # EXECUCAO
    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n--- EXECUTANDO: {len(revert_rows)} operacoes ---", flush=True)
    ts = datetime.now(timezone.utc)

    deleted = 0
    inserted = 0
    already_existed = 0
    errors = 0

    BATCH = 20
    for batch_start in range(0, len(revert_rows), BATCH):
        batch = revert_rows[batch_start:batch_start + BATCH]

        try:
            r.execute("SAVEPOINT wo_batch")

            for rv in batch:
                # DELETE do owner errado
                r.execute(
                    "DELETE FROM wine_sources WHERE id = %s",
                    (rv["ws_id"],),
                )
                deleted += r.rowcount

                # INSERT no owner correto
                r.execute("""
                    INSERT INTO wine_sources
                        (wine_id, store_id, url, preco, moeda, disponivel, descoberto_em, atualizado_em)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (wine_id, store_id, url) WHERE url IS NOT NULL DO NOTHING
                """, (
                    rv["wine_id_correto"],
                    rv["store_id"],
                    rv["url"],
                    rv["preco"],
                    rv["moeda"],
                    rv["disponivel"],
                    ts,
                    ts,
                ))
                if r.rowcount > 0:
                    inserted += 1
                else:
                    already_existed += 1

            r.execute("RELEASE SAVEPOINT wo_batch")
            rc.commit()

        except Exception as ex:
            print(f"  ERRO batch {batch_start}: {ex}", flush=True)
            r.execute("ROLLBACK TO SAVEPOINT wo_batch")
            rc.commit()
            errors += 1

    # ══════════════════════════════════════════════════════════════════════════
    # RESULTADO
    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{'=' * 80}", flush=True)
    print(f"RESULTADO", flush=True)
    print(f"{'=' * 80}", flush=True)
    print(f"  Deletadas:       {deleted}", flush=True)
    print(f"  Inseridas:       {inserted}", flush=True)
    print(f"  Ja existiam:     {already_existed}", flush=True)
    print(f"  Erros de batch:  {errors}", flush=True)
    print(f"  Timestamp:       {ts}", flush=True)

    # 20 exemplos conferidos
    print(f"\n  20 exemplos conferidos no Render:", flush=True)
    for i, rv in enumerate(revert_rows[:20], 1):
        # Verificar que o link agora esta no owner correto
        r.execute(
            "SELECT wine_id FROM wine_sources WHERE url = %s AND store_id = %s",
            (rv["url"], rv["store_id"]),
        )
        atual = r.fetchone()
        atual_id = atual[0] if atual else "NAO ENCONTRADO"

        r.execute("SELECT nome, produtor FROM wines WHERE id = %s", (rv["wine_id_correto"],))
        w = r.fetchone()
        nome = f"{w[1]} - {(w[0] or '')[:25]}" if w else "???"

        status = "OK" if atual_id == rv["wine_id_correto"] else f"ERRO (atual={atual_id})"
        print(f"  [{i:>2}] {rv['url'][:55]}", flush=True)
        print(f"       {rv['wine_id_errado']} -> {rv['wine_id_correto']} | {nome} | {status}", flush=True)

    # Queries de revert
    print(f"\n  QUERIES DE REVERT:", flush=True)
    print(f"    -- Apagar inserts novos:", flush=True)
    print(f"    DELETE FROM wine_sources WHERE descoberto_em = '{ts}';", flush=True)
    print(f"    -- Re-inserir linhas originais: usar {REVERT_CSV}", flush=True)
    print(f"    -- Script: para cada linha do CSV, INSERT com wine_id_errado, store_id, url, preco, moeda, disponivel, descoberto_em, atualizado_em originais", flush=True)

    r.close(); rc.close()
    print(f"\nFim.", flush=True)


if __name__ == "__main__":
    main()
