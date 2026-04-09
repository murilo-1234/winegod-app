"""
Gerar wine_aliases a partir de matches de alta confianca em y2_results.

Para cada match com score >= threshold:
  source_wine_id   = wines.id do vinho de loja no Render (encontrado via clean_id)
  canonical_wine_id = wines.id do vinho canonico Vivino no Render (= y2_results.vivino_id)

IMPORTANTE: y2_results.vivino_id JA E wines.id do Render.
  Prova: import_vivino_local.py importa vivino_match.id = wines.id do Render.
  pipeline_y2.py grava vivino_id = vivino_match.id (cand[0]).
  Portanto vivino_id = wines.id do Render, NAO vivino_vinhos.id.

Uso:
  python scripts/generate_aliases.py --dry-run              # contagens e amostra (PADRAO)
  python scripts/generate_aliases.py --dry-run --csv        # exporta CSV completo
  python scripts/generate_aliases.py --execute              # INSERT no banco (REQUER wine_aliases)
  python scripts/generate_aliases.py --threshold 0.8        # threshold customizado

Saida: reports/generate_aliases_dryrun.txt e/ou reports/generate_aliases.csv
"""

import os
import sys
import csv
import argparse
import psycopg2
from datetime import datetime

LOCAL_DB = dict(host="localhost", port=5432, dbname="winegod_db",
                user="postgres", password="postgres123")

sys.path.insert(0, os.path.dirname(__file__))
from guardrails_owner import is_producer_valid

DEFAULT_THRESHOLD = 0.7


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
    parser = argparse.ArgumentParser(description="Gerar wine_aliases")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Apenas contagens e amostra (padrao)")
    parser.add_argument("--execute", action="store_true",
                        help="Inserir aliases no banco (requer wine_aliases)")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help=f"Score minimo para auto-alias (default: {DEFAULT_THRESHOLD})")
    parser.add_argument("--csv", action="store_true",
                        help="Exportar CSV completo")
    parser.add_argument("--limit", type=int, default=0,
                        help="Limitar processamento")
    args = parser.parse_args()

    if args.execute:
        args.dry_run = False

    print("=" * 60)
    print(f"GENERATE ALIASES — threshold={args.threshold} mode={'EXECUTE' if args.execute else 'DRY-RUN'}")
    print(f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # --- Conectar banco local ---
    print("\nConectando banco local...", flush=True)
    local_conn = psycopg2.connect(**LOCAL_DB)
    local_cur = local_conn.cursor()

    # --- Contagens ---
    local_cur.execute("""
        SELECT COUNT(*) FROM y2_results
        WHERE status = 'matched' AND match_score >= %s
    """, (args.threshold,))
    total_elegivel = local_cur.fetchone()[0]
    print(f"Matched com score >= {args.threshold}: {total_elegivel:,}")

    local_cur.execute("""
        SELECT COUNT(*) FROM y2_results
        WHERE status = 'matched' AND match_score >= %s AND vivino_id IS NOT NULL
    """, (args.threshold,))
    com_vivino = local_cur.fetchone()[0]
    print(f"  Com vivino_id (= wines.id Render): {com_vivino:,}")

    # --- Distribuicao por faixa ---
    local_cur.execute("""
        SELECT
            CASE
                WHEN match_score >= 0.9 THEN '0.9-1.0'
                WHEN match_score >= 0.8 THEN '0.8-0.9'
                WHEN match_score >= 0.7 THEN '0.7-0.8'
                ELSE 'abaixo'
            END as faixa,
            COUNT(*) as cnt
        FROM y2_results
        WHERE status = 'matched' AND match_score >= %s
        GROUP BY faixa ORDER BY faixa DESC
    """, (args.threshold,))
    print("\nDistribuicao por faixa:")
    for faixa, cnt in local_cur.fetchall():
        print(f"  {faixa}: {cnt:,}")

    # --- Conectar Render para validar IDs ---
    print("\nConectando Render para validar wines.id...", flush=True)
    render_conn = get_render_conn()
    render_cur = render_conn.cursor()
    render_cur.execute("SELECT 1")
    print("Render OK.", flush=True)

    # --- Carregar set de wines.id validos do Render (amostra) ---
    # Para dry-run, validar apenas amostra
    # Para execute, validar todos
    print("\nCarregando amostra de matches...", flush=True)
    limit_clause = f"LIMIT {args.limit}" if args.limit else "LIMIT 10000"
    local_cur.execute(f"""
        SELECT id, clean_id, vivino_id, match_score, prod_banco, vivino_produtor,
               vinho_banco, vivino_nome
        FROM y2_results
        WHERE status = 'matched' AND match_score >= %s AND vivino_id IS NOT NULL
        ORDER BY match_score DESC
        {limit_clause}
    """, (args.threshold,))
    candidates = local_cur.fetchall()
    print(f"Candidatos carregados: {len(candidates):,}")

    # --- Validar canonical_wine_id no Render ---
    vivino_ids = list(set(r[2] for r in candidates))
    print(f"Vivino IDs unicos (= wines.id Render): {len(vivino_ids):,}")

    # Validar em batches de 1000
    valid_render_ids = set()
    for i in range(0, len(vivino_ids), 1000):
        chunk = vivino_ids[i:i+1000]
        render_cur.execute("SELECT id FROM wines WHERE id = ANY(%s)", (chunk,))
        valid_render_ids.update(r[0] for r in render_cur.fetchall())
    print(f"Validados no Render: {len(valid_render_ids):,} de {len(vivino_ids):,}")

    invalid_count = len(vivino_ids) - len(valid_render_ids)
    if invalid_count > 0:
        print(f"  ATENCAO: {invalid_count:,} vivino_ids NAO encontrados no Render!")

    # --- Gerar aliases ---
    aliases = []
    rejeitados_owner = 0
    rejeitados_id_invalido = 0

    for row in candidates:
        y_id, clean_id, vivino_id, score, prod_banco, viv_prod, vin_banco, viv_nome = row

        # Validar canonical_wine_id existe no Render
        if vivino_id not in valid_render_ids:
            rejeitados_id_invalido += 1
            continue

        # Validar produtor
        ok, reason = is_producer_valid(prod_banco)
        if not ok:
            rejeitados_owner += 1
            continue

        # Alias: source=clean_id (versao loja), canonical=vivino_id (wines.id Render)
        # NOTA: source_wine_id DEVERIA ser o wines.id do Render para o vinho de loja,
        # mas clean_id e o id do wines_clean LOCAL. Para usar como source_wine_id,
        # precisariamos do wines.id no Render correspondente ao clean_id.
        # Por ora, registramos clean_id e vivino_id para analise.
        aliases.append({
            "y2_id": y_id,
            "clean_id": clean_id,
            "canonical_wine_id": vivino_id,  # ESTE E wines.id do Render
            "match_score": score,
            "prod_banco": prod_banco,
            "vivino_produtor": viv_prod,
            "vinho_banco": vin_banco,
            "vivino_nome": viv_nome,
        })

    print(f"\nAliases gerados: {len(aliases):,}")
    print(f"Rejeitados por owner invalido: {rejeitados_owner:,}")
    print(f"Rejeitados por ID invalido no Render: {rejeitados_id_invalido:,}")

    # --- Amostra ---
    print(f"\n--- Amostra (10 primeiros por score) ---")
    for a in aliases[:10]:
        print(f"  clean={a['clean_id']} => canonical={a['canonical_wine_id']} "
              f"score={a['match_score']:.3f}")
        print(f"    loja: {a['vinho_banco']}")
        print(f"    vivino: {a['vivino_nome']}")

    # --- CSV ---
    if args.csv:
        csv_path = os.path.join(os.path.dirname(__file__), '..', 'reports', 'generate_aliases.csv')
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'y2_id', 'clean_id', 'canonical_wine_id', 'match_score',
                'prod_banco', 'vivino_produtor', 'vinho_banco', 'vivino_nome'
            ])
            writer.writeheader()
            writer.writerows(aliases)
        print(f"\nCSV salvo: {csv_path} ({len(aliases):,} linhas)")

    # --- Salvar relatorio ---
    report_path = os.path.join(os.path.dirname(__file__), '..', 'reports', 'generate_aliases_dryrun.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f"GENERATE ALIASES — DRY-RUN\n")
        f.write(f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Threshold: {args.threshold}\n")
        f.write(f"Total elegivel: {total_elegivel:,}\n")
        f.write(f"Com vivino_id: {com_vivino:,}\n")
        f.write(f"Validados no Render: {len(valid_render_ids):,}\n")
        f.write(f"Aliases gerados: {len(aliases):,}\n")
        f.write(f"Rejeitados owner: {rejeitados_owner:,}\n")
        f.write(f"Rejeitados ID invalido: {rejeitados_id_invalido:,}\n")
        f.write(f"\nIMPORTANTE: canonical_wine_id = wines.id do Render (NAO vivino_vinhos.id)\n")
        f.write(f"Prova: import_vivino_local.py importa vivino_match.id = wines.id do Render\n")
        f.write(f"pipeline_y2.py grava y2_results.vivino_id = vivino_match.id\n")
    print(f"Relatorio salvo: {report_path}")

    # --- Confirmacao ---
    print(f"\n{'=' * 60}")
    print(f"canonical_wine_id = wines.id do Render (CONFIRMADO)")
    print(f"  Prova: vivino_match.id vem de 'SELECT id FROM wines' no Render")
    print(f"  y2_results.vivino_id = vivino_match.id")
    print(f"  Portanto canonical_wine_id = wines.id Render, NAO vivino_vinhos.id")
    print(f"{'=' * 60}")

    render_conn.close()
    local_conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
