"""
Guardrails de Owner — Validação e auditoria de produtores.

Detecta e bloqueia:
- Produtor vazio ou nulo
- Produtor muito curto (< 3 chars)
- Produtor genérico (lista blocklist)
- Conflito tinto/branco no mesmo match
- Owner com concentração anormal de wines

Uso:
  python scripts/guardrails_owner.py --audit          # relatório de auditoria
  python scripts/guardrails_owner.py --validate-y2    # validar y2_results
"""

import os
import sys
import argparse
import psycopg2
from datetime import datetime

# ============================================================
# Configuração
# ============================================================

LOCAL_DB = dict(host="localhost", port=5432, dbname="winegod_db", user="postgres", password="postgres123")
RENDER_DB = os.getenv("DATABASE_URL", "")

# Produtores genéricos que não devem ser usados como âncora de matching
GENERIC_PRODUCERS = {
    "", "n/a", "na", "unknown", "desconhecido", "sem produtor",
    "wine", "vinho", "vino", "wines", "vinhos", "winery",
    "red wine", "white wine", "vinho tinto", "vinho branco",
    "tinto", "branco", "rose", "rosé",
    "imported", "importado", "national", "nacional",
    "other", "outro", "varios", "various",
    "test", "teste", "sample", "amostra",
    "generic", "generico", "genérico",
    "no brand", "sem marca", "marca",
}

# Concentração máxima: se um produtor tem mais que X% dos wines, é suspeito
MAX_OWNER_CONCENTRATION_PCT = 2.0  # 2% do total

# Comprimento mínimo de nome de produtor
MIN_PRODUCER_LEN = 3


# ============================================================
# Funções de validação
# ============================================================

def is_producer_valid(producer):
    """Retorna (válido, razão) para um produtor."""
    if not producer or not producer.strip():
        return False, "vazio"

    clean = producer.strip().lower()

    if len(clean) < MIN_PRODUCER_LEN:
        return False, f"muito_curto ({len(clean)} chars)"

    if clean in GENERIC_PRODUCERS:
        return False, f"genérico ({clean})"

    return True, "ok"


def has_type_conflict(tipo_loja, tipo_vivino):
    """Detecta conflito tinto/branco entre match de loja e Vivino."""
    if not tipo_loja or not tipo_vivino:
        return False

    tl = tipo_loja.strip().lower()
    tv = tipo_vivino.strip().lower()

    # Mapeamento simplificado
    RED = {"tinto", "red", "rosso", "rojo", "rot"}
    WHITE = {"branco", "white", "bianco", "blanco", "weiss"}

    is_red_loja = any(r in tl for r in RED)
    is_white_loja = any(w in tl for w in WHITE)
    is_red_viv = any(r in tv for r in RED)
    is_white_viv = any(w in tv for w in WHITE)

    if (is_red_loja and is_white_viv) or (is_white_loja and is_red_viv):
        return True

    return False


def validate_match_row(prod_banco, vinho_banco, vivino_produtor, vivino_nome,
                       match_score, cor_loja=None, cor_vivino=None):
    """Valida um match individual. Retorna (válido, problemas[])."""
    problems = []

    # Produtor da loja
    ok, reason = is_producer_valid(prod_banco)
    if not ok:
        problems.append(f"produtor_loja_{reason}")

    # Produtor Vivino
    ok, reason = is_producer_valid(vivino_produtor)
    if not ok:
        problems.append(f"produtor_vivino_{reason}")

    # Conflito de tipo
    if cor_loja and cor_vivino and has_type_conflict(cor_loja, cor_vivino):
        problems.append("conflito_tipo_tinto_branco")

    return len(problems) == 0, problems


# ============================================================
# Auditoria no banco Render
# ============================================================

def audit_render(cur):
    """Auditoria de owners no banco Render."""
    lines = []
    lines.append("=" * 60)
    lines.append("AUDITORIA DE OWNERS — Banco Render")
    lines.append(f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 60)

    # Total de wines
    cur.execute("SELECT COUNT(*) FROM wines")
    total = cur.fetchone()[0]
    lines.append(f"\nTotal wines: {total:,}")

    # Produtores vazios ou nulos
    cur.execute("SELECT COUNT(*) FROM wines WHERE produtor IS NULL OR TRIM(produtor) = ''")
    empty = cur.fetchone()[0]
    lines.append(f"Produtor vazio/nulo: {empty:,} ({empty*100/total:.1f}%)")

    # Produtores curtos (< 3 chars)
    cur.execute("SELECT COUNT(*) FROM wines WHERE LENGTH(TRIM(COALESCE(produtor, ''))) > 0 AND LENGTH(TRIM(produtor)) < 3")
    short = cur.fetchone()[0]
    lines.append(f"Produtor curto (< 3 chars): {short:,}")

    # Top 20 produtores por concentração
    cur.execute("""
        SELECT COALESCE(NULLIF(TRIM(produtor), ''), '<vazio>') as prod,
               COUNT(*) as cnt,
               ROUND(COUNT(*) * 100.0 / %s, 2) as pct
        FROM wines
        GROUP BY prod
        ORDER BY cnt DESC
        LIMIT 20
    """, (total,))
    rows = cur.fetchall()
    lines.append("\n--- Top 20 Produtores (concentração) ---")
    for prod, cnt, pct in rows:
        flag = " ⚠ CONCENTRADO" if pct > MAX_OWNER_CONCENTRATION_PCT else ""
        lines.append(f"  {prod:<40} {cnt:>8,} ({pct}%){flag}")

    # Vinhos sem vivino_id
    cur.execute("SELECT COUNT(*) FROM wines WHERE vivino_id IS NULL")
    sem_viv = cur.fetchone()[0]
    lines.append(f"\nSem vivino_id: {sem_viv:,} ({sem_viv*100/total:.1f}%)")

    # Vinhos sem rating
    cur.execute("SELECT COUNT(*) FROM wines WHERE vivino_rating IS NULL")
    sem_rat = cur.fetchone()[0]
    lines.append(f"Sem vivino_rating: {sem_rat:,} ({sem_rat*100/total:.1f}%)")

    return lines


# ============================================================
# Validar y2_results
# ============================================================

def validate_y2(cur):
    """Valida matches em y2_results."""
    lines = []
    lines.append("\n" + "=" * 60)
    lines.append("VALIDAÇÃO y2_results — matches")
    lines.append("=" * 60)

    cur.execute("""
        SELECT id, prod_banco, vinho_banco, vivino_produtor, vivino_nome,
               match_score, cor
        FROM y2_results
        WHERE status = 'matched'
        ORDER BY match_score ASC
        LIMIT 500
    """)
    rows = cur.fetchall()

    problemas_total = 0
    problemas_por_tipo = {}

    for row in rows:
        y_id, prod, vin, viv_prod, viv_nome, score, cor = row
        valid, problems = validate_match_row(prod, vin, viv_prod, viv_nome, score)
        if not valid:
            problemas_total += 1
            for p in problems:
                problemas_por_tipo[p] = problemas_por_tipo.get(p, 0) + 1

    lines.append(f"\nAnalisados: {len(rows)} (amostra dos 500 com menor score)")
    lines.append(f"Com problemas: {problemas_total}")
    lines.append("\n--- Problemas por tipo ---")
    for tipo, cnt in sorted(problemas_por_tipo.items(), key=lambda x: -x[1]):
        lines.append(f"  {tipo:<40} {cnt:>6}")

    # Exemplos
    cur.execute("""
        SELECT id, prod_banco, vinho_banco, vivino_produtor, vivino_nome, match_score
        FROM y2_results
        WHERE status = 'matched'
        AND (prod_banco IS NULL OR TRIM(prod_banco) = '' OR LENGTH(TRIM(prod_banco)) < 3)
        ORDER BY match_score DESC
        LIMIT 10
    """)
    rows = cur.fetchall()
    if rows:
        lines.append("\n--- Exemplos: produtor inválido com match aceito ---")
        for r in rows:
            lines.append(f"  id={r[0]} score={r[5]:.3f} prod='{r[1]}' → vivino='{r[3]}'")
            lines.append(f"    loja: {r[2]}")
            lines.append(f"    vivino: {r[4]}")

    return lines


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Guardrails de owner")
    parser.add_argument("--audit", action="store_true", help="Auditoria no Render")
    parser.add_argument("--validate-y2", action="store_true", help="Validar y2_results")
    args = parser.parse_args()

    lines = []

    if args.audit:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
        url = os.getenv("DATABASE_URL", RENDER_DB)
        if not url:
            print("[ERRO] DATABASE_URL não configurada")
            sys.exit(1)
        conn = psycopg2.connect(url)
        cur = conn.cursor()
        lines.extend(audit_render(cur))
        conn.close()

    if args.validate_y2:
        conn = psycopg2.connect(**LOCAL_DB)
        cur = conn.cursor()
        lines.extend(validate_y2(cur))
        conn.close()

    if not lines:
        parser.print_help()
        return

    report = "\n".join(lines)
    print(report)

    output_file = os.path.join(os.path.dirname(__file__), '..', 'reports', 'guardrails_owner_audit.txt')
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"\nRelatório salvo em: {output_file}")


if __name__ == "__main__":
    main()
