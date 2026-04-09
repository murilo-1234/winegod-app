"""
Triagem de candidatos reais para wine_aliases no Render.

Ferramenta de REVISAO MANUAL, nao executor automatico.
Gera CSV com campos de decisao para aprovar/rejeitar cada candidato.

Candidato = vinho de loja materializado em wines (vivino_id IS NULL)
que duplica um canonico Vivino (vivino_id IS NOT NULL) com nome/produtor
similar mas hash_dedup diferente.

Quem vai consumir wine_aliases no futuro:
  1. search.py — ao encontrar source_wine_id, resolver para canonical e
     apresentar dados do canonico (rating, score) em vez do vazio da loja.
     Implementacao: LEFT JOIN wine_aliases no resultado, COALESCE campos.
  2. details.py — ao mostrar detalhes de um wine de loja, enriquecer
     com dados do canonico se alias aprovado existir.
  3. Rebuild/sombra (Fase 2) — usar aliases como mapa de dedup
     para reconstruir banco limpo sem merge destrutivo.
  NOTA: a tabela sozinha nao muda comportamento do app. Precisa de
  integracao explicita nos pontos acima.

Uso:
  python scripts/find_alias_candidates.py --cases              # 5 casos criticos
  python scripts/find_alias_candidates.py --sample 500 --csv   # amostra com CSV
  python scripts/find_alias_candidates.py --priority --csv     # priorizado por impacto

Saida: reports/alias_candidates_review.csv e reports/alias_candidates.txt
"""

import os
import sys
import csv
import argparse
import psycopg2
from datetime import datetime

# Faixas de confianca para triagem manual
TIER_HIGH = 0.65     # >= 0.65: alta confianca (jaccard alto + produtor match)
TIER_MEDIUM = 0.40   # >= 0.40: media confianca (tokens compartilhados, produtor parcial)
# < 0.40: baixa confianca / descartar

CRITICAL_CASES = {
    "chaski petit verdot": {"loja_ids": [1796520], "canon_id": 94874},
    "finca las moras cabernet sauvignon": {"loja_ids": [1803853], "canon_id": 40743},
    "dom perignon": {"loja_ids": [1800714, 1844319], "canon_id": None},
    "luigi bosca de sangre malbec": {"loja_ids": [1814050], "canon_id": None},
}

CSV_FIELDS = [
    "source_id", "canonical_id",
    "source_nome", "canonical_nome",
    "source_produtor", "canonical_produtor",
    "source_safra", "canonical_safra",
    "canonical_rating", "canonical_vivino_id",
    "score_total", "score_jaccard", "score_produtor", "score_safra",
    "match_reason", "tier",
    "decision",  # approve / reject / pending
]


def get_render_conn():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'backend', '.env'))
    url = os.getenv("DATABASE_URL", "")
    if url and "sslmode" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return psycopg2.connect(url, connect_timeout=30)


def score_pair(loja_nome, canon_nome, loja_prod, canon_prod, loja_safra, canon_safra):
    """Pontua similaridade entre par loja/canonico."""
    lt = set(loja_nome.lower().split()) if loja_nome else set()
    ct = set(canon_nome.lower().split()) if canon_nome else set()
    if not lt or not ct:
        return 0.0, 0.0, 0.0, 0.0, "sem_tokens"

    common = lt & ct
    union = lt | ct
    jaccard = len(common) / len(union) if union else 0

    prod_score = 0.0
    if loja_prod and canon_prod:
        lp = loja_prod.lower().strip()
        cp = canon_prod.lower().strip()
        if lp == cp:
            prod_score = 1.0
        elif lp in cp or cp in lp:
            prod_score = 0.7
        else:
            # Tokens do produtor
            lpt = set(lp.split())
            cpt = set(cp.split())
            if lpt and cpt:
                pj = len(lpt & cpt) / len(lpt | cpt)
                if pj >= 0.5:
                    prod_score = 0.5

    safra_score = 0.0
    if loja_safra and canon_safra and str(loja_safra).strip() == str(canon_safra).strip():
        safra_score = 1.0
    elif not loja_safra or not canon_safra:
        safra_score = 0.3

    total = jaccard * 0.5 + prod_score * 0.3 + safra_score * 0.2

    # Motivo do match
    reasons = []
    if jaccard >= 0.8:
        reasons.append("nome_quase_identico")
    elif jaccard >= 0.5:
        reasons.append("tokens_compartilhados")
    if prod_score >= 0.7:
        reasons.append("produtor_match")
    if safra_score == 1.0:
        reasons.append("safra_identica")
    reason = "+".join(reasons) if reasons else "tokens_parciais"

    return round(total, 3), round(jaccard, 3), round(prod_score, 2), round(safra_score, 2), reason


def classify_tier(score):
    if score >= TIER_HIGH:
        return "alta"
    elif score >= TIER_MEDIUM:
        return "media"
    else:
        return "baixa"


def find_canonical_for(cur, nome_norm, limit=3):
    """Busca canonicos por tokens LIKE com timeout e rollback."""
    tokens = [t for t in (nome_norm or "").split() if len(t) >= 3]
    if len(tokens) < 2:
        return []

    def _try_query(token_list):
        clauses = " AND ".join("nome_normalizado LIKE %s" for _ in token_list)
        params = [f"%{t}%" for t in token_list] + [limit]
        try:
            cur.execute("SET LOCAL statement_timeout = '5s'")
            cur.execute(f"""
                SELECT id, nome, nome_normalizado, produtor, safra,
                       vivino_rating, vivino_id, vivino_reviews
                FROM wines
                WHERE vivino_id IS NOT NULL AND ({clauses})
                ORDER BY vivino_reviews DESC NULLS LAST
                LIMIT %s
            """, params)
            return cur.fetchall()
        except Exception:
            try:
                cur.connection.rollback()
            except Exception:
                pass
            return None

    # All tokens
    rows = _try_query(tokens)
    if rows:
        return rows

    # Subsets N-1
    if len(tokens) >= 3:
        for skip in range(len(tokens)):
            subset = [t for i, t in enumerate(tokens) if i != skip]
            rows = _try_query(subset)
            if rows:
                return rows

    return []


def build_candidate(loja, canon, sc_total, sc_jaccard, sc_prod, sc_safra, reason):
    """Monta dict de candidato para CSV de revisao."""
    tier = classify_tier(sc_total)
    return {
        "source_id": loja[0],
        "canonical_id": canon[0],
        "source_nome": loja[1] or "",
        "canonical_nome": canon[1] or "",
        "source_produtor": loja[3] or "",
        "canonical_produtor": canon[3] or "",
        "source_safra": loja[4] or "",
        "canonical_safra": canon[4] or "",
        "canonical_rating": canon[5],
        "canonical_vivino_id": canon[6],
        "score_total": sc_total,
        "score_jaccard": sc_jaccard,
        "score_produtor": sc_prod,
        "score_safra": sc_safra,
        "match_reason": reason,
        "tier": tier,
        "decision": "pending",
    }


def run_critical_cases(cur):
    """Valida e gera candidatos para os 5 casos criticos."""
    lines = []
    candidates = []
    lines.append("\n--- CASOS CRITICOS ---")

    for nome, info in CRITICAL_CASES.items():
        lines.append(f"\n  {nome}:")
        for lid in info["loja_ids"]:
            try:
                cur.execute("SET LOCAL statement_timeout = '5s'")
                cur.execute("""SELECT id, nome, nome_normalizado, produtor, safra
                    FROM wines WHERE id = %s""", (lid,))
            except Exception:
                try:
                    cur.connection.rollback()
                except Exception:
                    pass
                lines.append(f"    LOJA id={lid}: ERRO ao buscar")
                continue

            loja = cur.fetchone()
            if not loja:
                lines.append(f"    LOJA id={lid}: NAO ENCONTRADO")
                continue
            lines.append(f"    LOJA id={loja[0]} nome='{loja[1]}' prod='{loja[3]}' safra={loja[4]}")

            canonicals = find_canonical_for(cur, loja[2])
            if not canonicals:
                lines.append(f"    => NENHUM canonico encontrado")
            else:
                for c in canonicals:
                    sc_total, sc_j, sc_p, sc_s, reason = score_pair(
                        loja[2], c[2], loja[3], c[3], loja[4], c[4])
                    tier = classify_tier(sc_total)
                    lines.append(
                        f"    => [{tier.upper()} {sc_total:.3f}] canon id={c[0]} "
                        f"rating={c[5]} nome='{c[1][:50]}' prod='{c[3]}' "
                        f"(j={sc_j} p={sc_p} s={sc_s} {reason})")
                    if sc_total >= TIER_MEDIUM:
                        candidates.append(build_candidate(
                            loja, c, sc_total, sc_j, sc_p, sc_s, reason))

        if info["canon_id"]:
            try:
                cur.execute("SET LOCAL statement_timeout = '5s'")
                cur.execute("SELECT id, nome, vivino_rating FROM wines WHERE id = %s",
                            (info["canon_id"],))
                canon = cur.fetchone()
                if canon:
                    lines.append(f"    CANONICO ESPERADO: id={canon[0]} nome='{canon[1]}' rating={canon[2]}")
            except Exception:
                try:
                    cur.connection.rollback()
                except Exception:
                    pass
        else:
            lines.append(f"    CANONICO ESPERADO: NENHUM (lacuna de dados)")

    return lines, candidates


def run_sample(cur, sample_size):
    """Amostra de wines de loja, busca canonicos e gera candidatos."""
    candidates = []

    try:
        cur.execute("SET LOCAL statement_timeout = '15s'")
        cur.execute("""
            SELECT id, nome, nome_normalizado, produtor, safra
            FROM wines WHERE vivino_id IS NULL
            ORDER BY id LIMIT %s
        """, (sample_size,))
    except Exception:
        try:
            cur.connection.rollback()
        except Exception:
            pass
        print("  [ERRO] Timeout ao carregar wines de loja. DB pode estar lento.", flush=True)
        return candidates

    loja_wines = cur.fetchall()
    print(f"  Carregados: {len(loja_wines)} wines de loja", flush=True)

    processed = 0
    for loja in loja_wines:
        processed += 1
        if processed % 100 == 0:
            print(f"  Processados: {processed}/{len(loja_wines)}", flush=True)

        canonicals = find_canonical_for(cur, loja[2], limit=1)
        if not canonicals:
            continue

        c = canonicals[0]
        sc_total, sc_j, sc_p, sc_s, reason = score_pair(
            loja[2], c[2], loja[3], c[3], loja[4], c[4])
        if sc_total >= TIER_MEDIUM:
            candidates.append(build_candidate(
                loja, c, sc_total, sc_j, sc_p, sc_s, reason))

    return candidates


def save_csv(candidates, path):
    """Salva CSV de revisao manual."""
    # Ordenar: alta primeiro, depois media, por score desc
    candidates.sort(key=lambda x: (-{'alta': 2, 'media': 1, 'baixa': 0}[x['tier']],
                                    -x['score_total']))
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(candidates)
    return len(candidates)


def main():
    parser = argparse.ArgumentParser(description="Triagem de candidatos para wine_aliases")
    parser.add_argument("--cases", action="store_true", help="5 casos criticos")
    parser.add_argument("--sample", type=int, default=0, help="Amostra de wines de loja")
    parser.add_argument("--csv", action="store_true", help="Exportar CSV de revisao")
    parser.add_argument("--priority", action="store_true",
                        help="Priorizar por impacto (wines com wine_sources)")
    args = parser.parse_args()

    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"TRIAGEM DE CANDIDATOS PARA WINE_ALIASES")
    print(f"Data: {ts}")
    print(f"Faixas: alta >= {TIER_HIGH} | media >= {TIER_MEDIUM} | baixa < {TIER_MEDIUM}")
    print("=" * 60)

    conn = get_render_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1")
    print("Render conectado.", flush=True)

    all_candidates = []
    lines = []

    # Casos criticos
    if args.cases or not args.sample:
        crit_lines, crit_candidates = run_critical_cases(cur)
        lines.extend(crit_lines)
        all_candidates.extend(crit_candidates)
        for l in crit_lines:
            print(l, flush=True)

    # Amostra
    if args.sample:
        print(f"\nProcessando amostra de {args.sample} wines de loja...", flush=True)
        sample_candidates = run_sample(cur, args.sample)
        all_candidates.extend(sample_candidates)

    # Sumario
    alta = sum(1 for c in all_candidates if c["tier"] == "alta")
    media = sum(1 for c in all_candidates if c["tier"] == "media")
    print(f"\n{'=' * 60}")
    print(f"SUMARIO")
    print(f"  Total candidatos (score >= {TIER_MEDIUM}): {len(all_candidates)}")
    print(f"  Alta confianca (>= {TIER_HIGH}): {alta}")
    print(f"  Media confianca ({TIER_MEDIUM}-{TIER_HIGH}): {media}")

    # CSV
    if args.csv and all_candidates:
        csv_path = os.path.join(os.path.dirname(__file__), '..', 'reports',
                                'alias_candidates_review.csv')
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        cnt = save_csv(all_candidates, csv_path)
        print(f"\nCSV de revisao: {csv_path} ({cnt} linhas)")
        print(f"  Coluna 'decision': preencher com approve/reject/pending")

    # Relatorio
    report_path = os.path.join(os.path.dirname(__file__), '..', 'reports',
                               'alias_candidates.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f"TRIAGEM DE CANDIDATOS PARA WINE_ALIASES\n")
        f.write(f"Data: {ts}\n")
        f.write(f"Faixas: alta >= {TIER_HIGH} | media >= {TIER_MEDIUM}\n")
        f.write(f"{'=' * 60}\n")
        f.write("\n".join(lines) + "\n")
        f.write(f"\nTotal candidatos: {len(all_candidates)}\n")
        f.write(f"Alta: {alta} | Media: {media}\n")
        f.write(f"\nCRITERIOS DE APROVACAO:\n")
        f.write(f"  APROVAR se: mesmo vinho, mesmo produtor, mesmo pais/regiao\n")
        f.write(f"  REJEITAR se: vinho diferente, produtor diferente, safra conflitante\n")
        f.write(f"  PENDENTE se: ambiguo, precisa verificacao extra\n")
        f.write(f"\nQUEM CONSOME wine_aliases:\n")
        f.write(f"  1. search.py — resolver source para canonical na busca\n")
        f.write(f"  2. details.py — enriquecer detalhes de loja com dados canonicos\n")
        f.write(f"  3. Rebuild Fase 2 — mapa de dedup para banco sombra\n")
        f.write(f"  NOTA: tabela sozinha nao muda comportamento do app\n")
    print(f"Relatorio: {report_path}")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
