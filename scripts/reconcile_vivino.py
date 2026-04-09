"""
Reconciliacao Vivino DB vs Render — Fase 2 do rebuild.

Compara vinhos do vivino_db local com o snapshot atual do Render.
Classifica cada vinho em: ambos, so_vivino, so_render.

Uso:
  python scripts/reconcile_vivino.py --report       # relatorio de contagens
  python scripts/reconcile_vivino.py --sample 20    # amostra de cada grupo
  python scripts/reconcile_vivino.py --export        # exporta CSVs para analise

Saida: reports/reconciliacao_vivino.txt
"""

import os
import sys
import argparse
import psycopg2
from datetime import datetime

VIVINO_DB = "postgresql://postgres:postgres123@localhost:5432/vivino_db"
RENDER_DB = os.getenv("DATABASE_URL", "")
LOCAL_DB = dict(host="localhost", port=5432, dbname="winegod_db", user="postgres", password="postgres123")


def get_render_url():
    url = RENDER_DB
    if not url:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
        url = os.getenv("DATABASE_URL", "")
    return url


def report(args):
    lines = []
    lines.append("=" * 60)
    lines.append("RECONCILIACAO VIVINO DB vs RENDER")
    lines.append(f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 60)

    # Conectar Vivino local
    try:
        viv_conn = psycopg2.connect(VIVINO_DB)
        viv_cur = viv_conn.cursor()
        viv_cur.execute("SELECT COUNT(*) FROM vivino_vinhos")
        total_viv = viv_cur.fetchone()[0]
        lines.append(f"\nVivino DB local: {total_viv:,} vinhos")

        # IDs do Vivino
        viv_cur.execute("SELECT id FROM vivino_vinhos")
        vivino_ids = set(r[0] for r in viv_cur.fetchall())
        viv_conn.close()
    except Exception as e:
        lines.append(f"\n[ERRO] Vivino DB indisponivel: {e}")
        vivino_ids = set()
        total_viv = 0

    # Conectar Render
    render_url = get_render_url()
    if not render_url:
        lines.append("[ERRO] DATABASE_URL nao configurada")
        return lines

    try:
        render_conn = psycopg2.connect(render_url)
        render_cur = render_conn.cursor()
        render_cur.execute("SELECT COUNT(*) FROM wines")
        total_render = render_cur.fetchone()[0]
        lines.append(f"Render: {total_render:,} vinhos")

        # IDs no Render com vivino_id
        render_cur.execute("SELECT vivino_id FROM wines WHERE vivino_id IS NOT NULL")
        render_vivino_ids = set(r[0] for r in render_cur.fetchall())

        render_cur.execute("SELECT COUNT(*) FROM wines WHERE vivino_id IS NULL")
        sem_vivino = render_cur.fetchone()[0]
        lines.append(f"Render sem vivino_id: {sem_vivino:,}")

        # Cruzamento
        em_ambos = vivino_ids & render_vivino_ids
        so_vivino = vivino_ids - render_vivino_ids
        so_render = render_vivino_ids - vivino_ids

        lines.append(f"\n--- Cruzamento ---")
        lines.append(f"  Em ambos: {len(em_ambos):,}")
        lines.append(f"  So no Vivino DB: {len(so_vivino):,}")
        lines.append(f"  So no Render (vivino_id existente mas nao no DB): {len(so_render):,}")
        lines.append(f"  Render total sem vivino_id: {sem_vivino:,}")

        # Amostra dos que estao so no Render
        if so_render and args.sample:
            sample_ids = list(so_render)[:args.sample]
            render_cur.execute("""
                SELECT id, vivino_id, nome, produtor
                FROM wines WHERE vivino_id = ANY(%s)
                LIMIT %s
            """, (sample_ids, args.sample))
            rows = render_cur.fetchall()
            lines.append(f"\n--- Amostra: so no Render ({min(args.sample, len(rows))}) ---")
            for r in rows:
                lines.append(f"  id={r[0]} vivino_id={r[1]} nome={r[2]} prod={r[3]}")

        # Amostra dos que estao so no Vivino
        if so_vivino and args.sample:
            try:
                viv_conn2 = psycopg2.connect(VIVINO_DB)
                viv_cur2 = viv_conn2.cursor()
                sample_vids = list(so_vivino)[:args.sample]
                viv_cur2.execute("""
                    SELECT id, nome, vinicola_nome, rating_medio
                    FROM vivino_vinhos WHERE id = ANY(%s)
                    LIMIT %s
                """, (sample_vids, args.sample))
                rows = viv_cur2.fetchall()
                lines.append(f"\n--- Amostra: so no Vivino DB ({min(args.sample, len(rows))}) ---")
                for r in rows:
                    lines.append(f"  vivino_id={r[0]} nome={r[1]} prod={r[2]} rating={r[3]}")
                viv_conn2.close()
            except Exception as e:
                lines.append(f"  [ERRO ao amostrar Vivino]: {e}")

        render_conn.close()
    except Exception as e:
        lines.append(f"\n[ERRO] Render indisponivel: {e}")

    return lines


def main():
    parser = argparse.ArgumentParser(description="Reconciliacao Vivino vs Render")
    parser.add_argument("--report", action="store_true", help="Relatorio de contagens")
    parser.add_argument("--sample", type=int, default=0, help="Tamanho da amostra por grupo")
    parser.add_argument("--export", action="store_true", help="Exportar CSVs")
    args = parser.parse_args()

    if not args.report and not args.export:
        args.report = True
        args.sample = 10

    lines = report(args)

    output = "\n".join(lines)
    print(output)

    output_file = os.path.join(os.path.dirname(__file__), '..', 'reports', 'reconciliacao_vivino.txt')
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(output)
    print(f"\nSalvo em: {output_file}")


if __name__ == "__main__":
    main()
