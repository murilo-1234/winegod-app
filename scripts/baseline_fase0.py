"""
Baseline Fase 0 — Captura estado atual usando a logica real do backend.

Executa search_wine() do backend para cada caso critico,
garantindo que o baseline prove o comportamento real do app.

Uso:
  python scripts/baseline_fase0.py               # pre-hotfix
  python scripts/baseline_fase0.py --pos          # pos-hotfix para comparacao
  python scripts/baseline_fase0.py --skip-local   # pular y2_results (sem banco local)

Saida: reports/baseline_fase0.txt ou reports/pos_hotfix_fase0.txt
"""

import os
import sys
import json
from datetime import datetime
from decimal import Decimal

# Adicionar backend ao path para importar modulos reais
BACKEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'backend')
sys.path.insert(0, BACKEND_DIR)

# Carregar .env antes de qualquer import do backend
# .env fica em backend/, nao na raiz
from dotenv import load_dotenv
load_dotenv(os.path.join(BACKEND_DIR, '.env'))

# Render exige SSL. Garantir sslmode na URL se ausente.
_db_url = os.getenv("DATABASE_URL", "")
if _db_url and "sslmode" not in _db_url:
    _db_url += ("&" if "?" in _db_url else "?") + "sslmode=require"
    os.environ["DATABASE_URL"] = _db_url

CASOS_CRITICOS = [
    "Dom Perignon",
    "Finca Las Moras Cabernet Sauvignon",
    "Chaski Petit Verdot",
    "Luigi Bosca De Sangre Malbec",
    "Perez Cruz Piedra Seca",
]

LOCAL_DB_URL = os.getenv("LOCAL_DATABASE_URL",
                         "postgresql://postgres:postgres123@localhost:5432/winegod_db")


# ============================================================
# Relatorio usando logica real do backend (search_wine)
# ============================================================

def relatorio_backend_search():
    """Executa search_wine() real do backend para cada caso critico."""
    lines = []
    lines.append("\n" + "=" * 60)
    lines.append("BUSCAS CRITICAS — via backend/tools/search.search_wine()")
    lines.append("=" * 60)

    try:
        # Desabilitar cache para ver resultado fresco
        os.environ["UPSTASH_REDIS_URL"] = ""

        from tools.search import search_wine
    except ImportError as e:
        lines.append(f"\n[ERRO] Nao conseguiu importar search_wine: {e}")
        lines.append("  Verifique se DATABASE_URL esta configurada no .env")
        return lines

    for caso in CASOS_CRITICOS:
        lines.append(f"\n--- Busca: '{caso}' ---")
        try:
            result = search_wine(caso, limit=5)
            wines = result.get("wines", [])
            layer = result.get("search_layer", "?")
            lines.append(f"  Camada usada: {layer}")
            lines.append(f"  Resultados: {len(wines)}")

            if not wines:
                lines.append("  NENHUM resultado!")
            else:
                for i, w in enumerate(wines):
                    lines.append(f"  #{i+1} id={w.get('id')} nome={w.get('nome')}")
                    lines.append(f"     produtor={w.get('produtor')}")
                    lines.append(f"     rating={w.get('vivino_rating')} wcf={w.get('nota_wcf')} "
                                 f"score={w.get('winegod_score')} tipo={w.get('tipo')}")
                    lines.append(f"     preco={w.get('preco_min')} {w.get('moeda')}")
        except Exception as e:
            lines.append(f"  [ERRO] {e}")

    return lines


# ============================================================
# Contagens gerais via conexao direta (sem depender de tool)
# ============================================================

def relatorio_contagens():
    """Contagens gerais do banco Render."""
    lines = []
    lines.append("\n" + "=" * 60)
    lines.append("CONTAGENS GERAIS — Banco Render")
    lines.append("=" * 60)

    try:
        from db.connection import get_connection, release_connection
        conn = get_connection()
    except Exception as e:
        lines.append(f"\n[ERRO] Conexao Render falhou: {e}")
        return lines

    try:
        with conn.cursor() as cur:
            queries = [
                ("Total wines", "SELECT COUNT(*) FROM wines"),
                ("Com vivino_id", "SELECT COUNT(*) FROM wines WHERE vivino_id IS NOT NULL"),
                ("Com vivino_rating", "SELECT COUNT(*) FROM wines WHERE vivino_rating IS NOT NULL"),
                ("Com nota_wcf", "SELECT COUNT(*) FROM wines WHERE nota_wcf IS NOT NULL"),
                ("Com winegod_score", "SELECT COUNT(*) FROM wines WHERE winegod_score IS NOT NULL"),
                ("Sem nenhuma nota", "SELECT COUNT(*) FROM wines WHERE vivino_rating IS NULL AND nota_wcf IS NULL"),
                ("Total wine_sources", "SELECT COUNT(*) FROM wine_sources"),
                ("Total stores", "SELECT COUNT(*) FROM stores"),
            ]
            for label, sql in queries:
                try:
                    cur.execute(sql)
                    cnt = cur.fetchone()[0]
                    lines.append(f"  {label:<30} {cnt:>12,}")
                except Exception as e:
                    lines.append(f"  {label:<30} [ERRO: {e}]")
                    conn.rollback()
    finally:
        release_connection(conn)

    return lines


# ============================================================
# Relatorio y2_results (banco local — opcional)
# ============================================================

def relatorio_local():
    """Contagens de y2_results no banco local."""
    lines = []
    lines.append("\n" + "=" * 60)
    lines.append("y2_results — Banco Local")
    lines.append("=" * 60)

    import psycopg2
    try:
        conn = psycopg2.connect(LOCAL_DB_URL)
    except Exception as e:
        lines.append(f"\n[AVISO] Banco local indisponivel: {e}")
        return lines

    cur = conn.cursor()

    # Status
    cur.execute("SELECT status, COUNT(*) FROM y2_results GROUP BY status ORDER BY COUNT(*) DESC")
    lines.append("\n--- Por status ---")
    for status, cnt in cur.fetchall():
        lines.append(f"  {status or 'NULL':<20} {cnt:>10,}")

    # Faixas de score
    cur.execute("""
        SELECT
            CASE
                WHEN match_score >= 0.9 THEN '0.9-1.0'
                WHEN match_score >= 0.8 THEN '0.8-0.9'
                WHEN match_score >= 0.7 THEN '0.7-0.8'
                WHEN match_score >= 0.6 THEN '0.6-0.7'
                WHEN match_score >= 0.5 THEN '0.5-0.6'
                WHEN match_score >= 0.4 THEN '0.4-0.5'
                WHEN match_score >= 0.3 THEN '0.3-0.4'
                WHEN match_score >= 0.2 THEN '0.2-0.3'
                WHEN match_score >= 0.1 THEN '0.1-0.2'
                WHEN match_score >= 0.0 THEN '0.0-0.1'
                ELSE 'NULL'
            END as faixa,
            COUNT(*) as cnt
        FROM y2_results WHERE status = 'matched'
        GROUP BY faixa ORDER BY faixa DESC
    """)
    lines.append("\n--- Matched por faixa de score ---")
    total_matched = 0
    contaminados = 0
    for faixa, cnt in cur.fetchall():
        lines.append(f"  {faixa:<12} {cnt:>10,}")
        total_matched += cnt
        if faixa in ('0.0-0.1', '0.1-0.2', '0.2-0.3', '0.3-0.4', '0.4-0.5'):
            contaminados += cnt
    lines.append(f"  {'TOTAL':<12} {total_matched:>10,}")
    lines.append(f"  {'< 0.5':<12} {contaminados:>10,}")

    # Exemplos de score baixo
    cur.execute("""
        SELECT id, clean_id, vivino_id, match_score, vinho_banco, vivino_nome
        FROM y2_results
        WHERE status = 'matched' AND match_score < 0.5 AND match_score >= 0.0
        ORDER BY match_score ASC LIMIT 10
    """)
    rows = cur.fetchall()
    if rows:
        lines.append("\n--- Exemplos com score < 0.5 ---")
        for r in rows:
            lines.append(f"  id={r[0]} score={r[3]:.3f} banco='{r[4]}' => vivino='{r[5]}'")

    conn.close()
    return lines


# ============================================================
# Main
# ============================================================

def main():
    pos_hotfix = "--pos" in sys.argv
    skip_local = "--skip-local" in sys.argv

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    label = "POS-HOTFIX" if pos_hotfix else "PRE-HOTFIX (BASELINE)"
    filename = 'pos_hotfix_fase0.txt' if pos_hotfix else 'baseline_fase0.txt'
    output_file = os.path.join(os.path.dirname(__file__), '..', 'reports', filename)

    lines = []
    lines.append("=" * 60)
    lines.append(f"RELATORIO FASE 0 -- {label}")
    lines.append(f"Data: {timestamp}")
    lines.append("=" * 60)

    # y2_results local (opcional)
    if not skip_local:
        lines.extend(relatorio_local())

    # Buscas criticas via backend real
    lines.extend(relatorio_backend_search())

    # Contagens gerais
    lines.extend(relatorio_contagens())

    report = "\n".join(lines)
    print(report)

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"\nRelatorio salvo em: {output_file}")


if __name__ == "__main__":
    main()
