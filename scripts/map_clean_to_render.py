"""
Mapeamento clean_id -> wines.id do Render para vinhos de loja materializados.

Resolve: dado um clean_id (wines_clean local), qual e o wines.id correspondente
no Render? Necessario para preencher source_wine_id nos wine_aliases.

Estrategia de mapeamento (em ordem de confianca):
  1. hash_dedup: wines_clean.hash_dedup = wines.hash_dedup no Render (deterministic)
  2. nome_normalizado exato: fallback se hash nao bater

Uso:
  python scripts/map_clean_to_render.py --report          # contagens e cobertura
  python scripts/map_clean_to_render.py --report --csv    # exporta CSV com amostra
  python scripts/map_clean_to_render.py --limit 1000      # limitar amostra

Saida: reports/map_clean_to_render.txt e reports/map_clean_to_render.csv
"""

import os
import sys
import csv
import argparse
import psycopg2
from datetime import datetime
from collections import defaultdict

LOCAL_DB = dict(host="localhost", port=5432, dbname="winegod_db",
                user="postgres", password="postgres123")


def get_render_conn():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'backend', '.env'))
    url = os.getenv("DATABASE_URL", "")
    if url and "sslmode" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    if not url:
        print("[ERRO] DATABASE_URL nao configurada")
        sys.exit(1)
    return psycopg2.connect(url, connect_timeout=30)


def main():
    parser = argparse.ArgumentParser(description="Mapeamento clean_id -> wines.id Render")
    parser.add_argument("--report", action="store_true", default=True)
    parser.add_argument("--csv", action="store_true")
    parser.add_argument("--limit", type=int, default=10000,
                        help="Limitar amostra de clean_ids a processar")
    args = parser.parse_args()

    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"MAPEAMENTO clean_id -> wines.id Render")
    print(f"Data: {ts}")
    print("=" * 60)

    # --- Conectar local ---
    local_conn = psycopg2.connect(**LOCAL_DB)
    local_cur = local_conn.cursor()

    # --- Contagem total de y2_results matched que precisam de source_wine_id ---
    local_cur.execute("""
        SELECT COUNT(DISTINCT clean_id) FROM y2_results
        WHERE status = 'matched' AND match_score >= 0.7
    """)
    total_clean_ids = local_cur.fetchone()[0]
    print(f"\nclean_ids unicos com matched >= 0.7: {total_clean_ids:,}")

    # --- Carregar amostra de clean_ids com hash_dedup ---
    local_cur.execute(f"""
        SELECT DISTINCT y.clean_id, wc.hash_dedup, wc.nome_normalizado
        FROM y2_results y
        JOIN wines_clean wc ON wc.id = y.clean_id
        WHERE y.status = 'matched' AND y.match_score >= 0.7
        ORDER BY y.clean_id
        LIMIT {args.limit}
    """)
    clean_rows = local_cur.fetchall()
    print(f"Amostra carregada: {len(clean_rows):,} clean_ids")

    # Verificar se wines_clean tem hash_dedup
    local_cur.execute("SELECT COUNT(*) FROM wines_clean WHERE hash_dedup IS NOT NULL AND hash_dedup != ''")
    com_hash = local_cur.fetchone()[0]
    local_cur.execute("SELECT COUNT(*) FROM wines_clean")
    total_wc = local_cur.fetchone()[0]
    print(f"wines_clean com hash_dedup: {com_hash:,} de {total_wc:,} ({com_hash*100/total_wc:.1f}%)")

    # --- Conectar Render ---
    print("\nConectando Render...", flush=True)
    render_conn = get_render_conn()
    render_cur = render_conn.cursor()
    render_cur.execute("SELECT 1")
    print("Render OK.", flush=True)

    # --- Mapear por hash_dedup ---
    hashes = [r[1] for r in clean_rows if r[1]]
    print(f"\nMapeando por hash_dedup: {len(hashes):,} hashes para resolver...")

    hash_to_render_ids = defaultdict(list)
    for i in range(0, len(hashes), 500):
        chunk = hashes[i:i+500]
        render_cur.execute("""
            SELECT hash_dedup, id FROM wines
            WHERE hash_dedup = ANY(%s)
        """, (chunk,))
        for h, wid in render_cur.fetchall():
            hash_to_render_ids[h].append(wid)

    # --- Classificar resultados ---
    mapped_1to1 = 0
    mapped_ambiguous = 0
    not_mapped_no_hash = 0
    not_mapped_not_found = 0
    results = []

    for clean_id, hash_dedup, nome_norm in clean_rows:
        if not hash_dedup:
            not_mapped_no_hash += 1
            results.append({
                "clean_id": clean_id,
                "hash_dedup": "",
                "render_ids": "",
                "count": 0,
                "status": "no_hash",
                "nome": nome_norm or "",
            })
            continue

        render_ids = hash_to_render_ids.get(hash_dedup, [])
        if len(render_ids) == 1:
            mapped_1to1 += 1
            results.append({
                "clean_id": clean_id,
                "hash_dedup": hash_dedup,
                "render_ids": str(render_ids[0]),
                "count": 1,
                "status": "1:1",
                "nome": nome_norm or "",
            })
        elif len(render_ids) > 1:
            mapped_ambiguous += 1
            results.append({
                "clean_id": clean_id,
                "hash_dedup": hash_dedup,
                "render_ids": "|".join(str(x) for x in render_ids),
                "count": len(render_ids),
                "status": "ambiguous",
                "nome": nome_norm or "",
            })
        else:
            not_mapped_not_found += 1
            results.append({
                "clean_id": clean_id,
                "hash_dedup": hash_dedup,
                "render_ids": "",
                "count": 0,
                "status": "not_found",
                "nome": nome_norm or "",
            })

    total_amostra = len(clean_rows)
    print(f"\n{'=' * 60}")
    print(f"COBERTURA DO MAPEAMENTO (amostra de {total_amostra:,})")
    print(f"{'=' * 60}")
    print(f"  1:1 (hash_dedup unico):     {mapped_1to1:>8,} ({mapped_1to1*100/total_amostra:.1f}%)")
    print(f"  Ambiguo (>1 wines.id):       {mapped_ambiguous:>8,} ({mapped_ambiguous*100/total_amostra:.1f}%)")
    print(f"  Sem hash_dedup:              {not_mapped_no_hash:>8,} ({not_mapped_no_hash*100/total_amostra:.1f}%)")
    print(f"  Hash nao encontrado Render:  {not_mapped_not_found:>8,} ({not_mapped_not_found*100/total_amostra:.1f}%)")

    # Amostra de ambiguos
    ambiguous = [r for r in results if r["status"] == "ambiguous"]
    if ambiguous:
        print(f"\n--- Amostra de ambiguos ({min(10, len(ambiguous))}) ---")
        for a in ambiguous[:10]:
            print(f"  clean={a['clean_id']} => render_ids=[{a['render_ids']}] nome={a['nome'][:60]}")

    # Amostra de nao encontrados
    not_found = [r for r in results if r["status"] == "not_found"]
    if not_found:
        print(f"\n--- Amostra de nao encontrados ({min(10, len(not_found))}) ---")
        for n in not_found[:10]:
            print(f"  clean={n['clean_id']} hash={n['hash_dedup'][:20]}... nome={n['nome'][:60]}")

    # --- CSV ---
    if args.csv:
        csv_path = os.path.join(os.path.dirname(__file__), '..', 'reports', 'map_clean_to_render.csv')
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'clean_id', 'hash_dedup', 'render_ids', 'count', 'status', 'nome'
            ])
            writer.writeheader()
            writer.writerows(results)
        print(f"\nCSV salvo: {csv_path} ({len(results):,} linhas)")

    # --- Relatorio ---
    report_path = os.path.join(os.path.dirname(__file__), '..', 'reports', 'map_clean_to_render.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f"MAPEAMENTO clean_id -> wines.id Render\n")
        f.write(f"Data: {ts}\n")
        f.write(f"Total clean_ids matched >= 0.7: {total_clean_ids:,}\n")
        f.write(f"Amostra processada: {total_amostra:,}\n\n")
        f.write(f"1:1 (hash unico):       {mapped_1to1:,} ({mapped_1to1*100/total_amostra:.1f}%)\n")
        f.write(f"Ambiguo (>1 wines.id):   {mapped_ambiguous:,} ({mapped_ambiguous*100/total_amostra:.1f}%)\n")
        f.write(f"Sem hash:                {not_mapped_no_hash:,} ({not_mapped_no_hash*100/total_amostra:.1f}%)\n")
        f.write(f"Hash nao encontrado:     {not_mapped_not_found:,} ({not_mapped_not_found*100/total_amostra:.1f}%)\n")
    print(f"Relatorio salvo: {report_path}")

    render_conn.close()
    local_conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
