"""
Demanda 7 -- Atribuir pilot_bucket_proxy a cada wine do working pool e
selecionar o pilot_120 + 60 reservas.

READ-ONLY. Nao toca Postgres.

Entradas:
  - reports/tail_working_pool_1200_2026-04-10.csv
  - reports/tail_working_pool_fanout_per_wine_2026-04-10.csv.gz
  - reports/tail_working_pool_fanout_detail_2026-04-10.csv.gz  (opcional, nao usado)

Saidas:
  - reports/tail_pilot_120_2026-04-10.csv
  - reports/tail_pilot_120_reservas_2026-04-10.csv
  - reports/tail_working_pool_with_buckets_2026-04-10.csv  (pool + bucket + reason)

Regras de atribuicao (prioridade descendente, exclusiva -- primeiro que bate, pronto):

  P1 SUSPECT_NOT_WINE_PROXY:
     wine_filter_category != '' (classify_product == 'not_wine')
     OR y2_any_not_wine_or_spirit == '1'

  P2 NO_SOURCE_PROXY:
     no_source_flag == '1'

  P3 POOR_DATA_OR_NO_CANDIDATE_PROXY:
     produtor vazio/generico  (len(strip()) < 3)
     OR nome muito curto      (len(strip()) < 5)
     OR nenhum candidato em nenhum universo (render_any==0 AND import_any==0)
     OR best_overall_score vazio ou < 0.20

  P4 STRONG_RENDER_PROXY:
     best_overall_universe == 'render'
     AND best_overall_score >= 0.35
     AND top1_render_gap >= 0.05

  P5 STRONG_IMPORT_PROXY:
     best_overall_universe == 'import'
     AND best_overall_score >= 0.35
     AND top1_import_gap >= 0.05

  P6 AMBIGUOUS_PROXY:
     sobra -- score >= 0.20 mas gap baixo, ou empate forte, ou render/import
     disputando top1 com diff pequena.

O pilot_bucket_proxy e OPERACIONAL. NAO e business_class final. E usado
APENAS para calibracao/revisao R1.

Selecao do pilot_120:
  - alvo: 20 por bucket (P1..P6)
  - ordem deterministica por hash_key (ja computado no working pool CSV)
  - se um bucket tem < 20: marcar deficit no summary e preencher com overflow
    do bucket de proxima prioridade (P6 -> P3 -> P4/P5)
  - reservas: 60 no total, 10 por bucket (ordem deterministica), para
    substituicao futura
"""

import argparse
import csv
import gzip
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports")

POOL_CSV = os.path.join(REPORT_DIR, "tail_working_pool_1200_2026-04-10.csv")
PER_WINE = os.path.join(REPORT_DIR, "tail_working_pool_fanout_per_wine_2026-04-10.csv.gz")
OUT_POOL_WITH_BUCKETS = os.path.join(REPORT_DIR, "tail_working_pool_with_buckets_2026-04-10.csv")
OUT_PILOT = os.path.join(REPORT_DIR, "tail_pilot_120_2026-04-10.csv")
OUT_RESERVAS = os.path.join(REPORT_DIR, "tail_pilot_120_reservas_2026-04-10.csv")

BUCKET_ORDER = [
    "P1_SUSPECT_NOT_WINE_PROXY",
    "P2_NO_SOURCE_PROXY",
    "P3_POOR_DATA_OR_NO_CANDIDATE_PROXY",
    "P4_STRONG_RENDER_PROXY",
    "P5_STRONG_IMPORT_PROXY",
    "P6_AMBIGUOUS_PROXY",
]

TARGET_PER_BUCKET = 20
PILOT_SIZE = 120
RESERVAS_PER_BUCKET = 10


# Thresholds (documentados)
STRONG_SCORE = 0.35
STRONG_GAP = 0.05
POOR_SCORE = 0.20
MIN_PROD_LEN = 3
MIN_NOME_LEN = 5


def parse_float(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def assign_bucket(pool_row, pw_row):
    """Retorna (bucket, reason_short_proxy)."""
    # P1 SUSPECT_NOT_WINE_PROXY
    wf_cat = (pool_row.get("wine_filter_category") or "").strip()
    y2_nw = pool_row.get("y2_any_not_wine_or_spirit") or ""
    if wf_cat:
        return ("P1_SUSPECT_NOT_WINE_PROXY", f"wine_filter={wf_cat}")
    if y2_nw == "1":
        return ("P1_SUSPECT_NOT_WINE_PROXY", "y2_any_not_wine_or_spirit=1")

    # P2 NO_SOURCE_PROXY
    if pool_row.get("no_source_flag") == "1":
        return ("P2_NO_SOURCE_PROXY", "no_source_flag=1")

    # Extract scoring fields from per_wine
    r_any = pw_row.get("render_any_candidate", "0") == "1"
    i_any = pw_row.get("import_any_candidate", "0") == "1"
    best_score = parse_float(pw_row.get("best_overall_score", ""))
    best_univ = pw_row.get("best_overall_universe", "")
    r_gap = parse_float(pw_row.get("top1_render_gap", ""))
    i_gap = parse_float(pw_row.get("top1_import_gap", ""))
    r_score = parse_float(pw_row.get("top1_render_score", ""))
    i_score = parse_float(pw_row.get("top1_import_score", ""))

    # P3 POOR_DATA_OR_NO_CANDIDATE_PROXY
    prod = (pool_row.get("produtor") or "").strip()
    nome = (pool_row.get("nome") or "").strip()
    if len(prod) < MIN_PROD_LEN:
        return ("P3_POOR_DATA_OR_NO_CANDIDATE_PROXY", f"produtor_curto len={len(prod)}")
    if len(nome) < MIN_NOME_LEN:
        return ("P3_POOR_DATA_OR_NO_CANDIDATE_PROXY", f"nome_curto len={len(nome)}")
    if not r_any and not i_any:
        return ("P3_POOR_DATA_OR_NO_CANDIDATE_PROXY", "sem candidatos em ambos universos")
    if best_score is None or best_score < POOR_SCORE:
        return ("P3_POOR_DATA_OR_NO_CANDIDATE_PROXY",
                f"best_score={best_score}")

    # P4 STRONG_RENDER_PROXY
    if (best_univ == "render"
            and best_score >= STRONG_SCORE
            and r_gap is not None and r_gap >= STRONG_GAP):
        return ("P4_STRONG_RENDER_PROXY",
                f"render score={r_score:.3f} gap={r_gap:.3f}")

    # P5 STRONG_IMPORT_PROXY
    if (best_univ == "import"
            and best_score >= STRONG_SCORE
            and i_gap is not None and i_gap >= STRONG_GAP):
        return ("P5_STRONG_IMPORT_PROXY",
                f"import score={i_score:.3f} gap={i_gap:.3f}")

    # P6 AMBIGUOUS_PROXY (sobra)
    # razao curta: motivo mais descritivo
    reasons = []
    if r_gap is not None and r_gap < STRONG_GAP:
        reasons.append(f"render_gap={r_gap:.3f}")
    if i_gap is not None and i_gap < STRONG_GAP:
        reasons.append(f"import_gap={i_gap:.3f}")
    if r_score is not None and i_score is not None and abs(r_score - i_score) < 0.05:
        reasons.append("render~import")
    if not reasons:
        reasons.append(f"best_score={best_score:.3f} universe={best_univ}")
    return ("P6_AMBIGUOUS_PROXY", "|".join(reasons))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default=POOL_CSV)
    ap.add_argument("--per-wine", default=PER_WINE)
    ap.add_argument("--out-pool", default=OUT_POOL_WITH_BUCKETS)
    ap.add_argument("--out-pilot", default=OUT_PILOT)
    ap.add_argument("--out-reservas", default=OUT_RESERVAS)
    args = ap.parse_args()

    # Ler pool
    pool = []
    with open(args.pool, "r", encoding="utf-8", newline="") as f:
        pool = list(csv.DictReader(f))
    print(f"[pool] {len(pool)} wines")

    # Ler per_wine
    per_wine = {}
    with gzip.open(args.per_wine, "rt", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            per_wine[int(r["render_wine_id"])] = r
    print(f"[per_wine] {len(per_wine)} wines com scores")

    # Atribuir bucket a cada wine
    annotated = []
    for row in pool:
        wid = int(row["render_wine_id"])
        pw = per_wine.get(wid, {})
        bucket, reason = assign_bucket(row, pw)
        enriched = dict(row)
        # merge per_wine fields (sem sobrescrever)
        for k, v in pw.items():
            if k not in enriched:
                enriched[k] = v
        enriched["pilot_bucket_proxy"] = bucket
        enriched["reason_short_proxy"] = reason
        annotated.append(enriched)

    # Count por bucket
    from collections import Counter
    bucket_counts = Counter(r["pilot_bucket_proxy"] for r in annotated)
    print(f"[buckets] distribuicao no working pool:")
    for b in BUCKET_ORDER:
        print(f"    {b:40s} = {bucket_counts.get(b, 0):>4}")
    print(f"    TOTAL                                    = {sum(bucket_counts.values()):>4}")

    # Escrever pool com buckets
    fieldnames = list(annotated[0].keys())
    with open(args.out_pool, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(annotated)
    print(f"[write] {args.out_pool}")

    # ---------- Selecao deterministica do pilot_120 ----------
    # Agrupar por bucket, ordenar por hash_key deterministico
    by_bucket = {b: [] for b in BUCKET_ORDER}
    for r in annotated:
        by_bucket[r["pilot_bucket_proxy"]].append(r)
    for b in BUCKET_ORDER:
        by_bucket[b].sort(key=lambda r: r["hash_key"])

    selected = []
    selected_set = set()
    deficits = {}
    # First pass: up to TARGET_PER_BUCKET per bucket
    for b in BUCKET_ORDER:
        avail = by_bucket[b]
        take = avail[:TARGET_PER_BUCKET]
        selected.extend(take)
        for r in take:
            selected_set.add(int(r["render_wine_id"]))
        if len(take) < TARGET_PER_BUCKET:
            deficits[b] = TARGET_PER_BUCKET - len(take)
            print(f"  [deficit] {b}: {deficits[b]} faltando")

    # Overflow: se deficit, preencher com wines ainda nao selecionados
    # ordem de doacao: P6 -> P3 -> P4 -> P5 -> P1 -> P2
    overflow_priority = [
        "P6_AMBIGUOUS_PROXY",
        "P3_POOR_DATA_OR_NO_CANDIDATE_PROXY",
        "P4_STRONG_RENDER_PROXY",
        "P5_STRONG_IMPORT_PROXY",
        "P1_SUSPECT_NOT_WINE_PROXY",
        "P2_NO_SOURCE_PROXY",
    ]
    overflow_log = []
    while sum(deficits.values()) > 0:
        needed = sum(deficits.values())
        filled = 0
        for donor_bucket in overflow_priority:
            if sum(deficits.values()) == 0:
                break
            for r in by_bucket[donor_bucket]:
                if int(r["render_wine_id"]) in selected_set:
                    continue
                r2 = dict(r)
                r2["overflow_from"] = donor_bucket
                selected.append(r2)
                selected_set.add(int(r["render_wine_id"]))
                filled += 1
                overflow_log.append((donor_bucket, int(r["render_wine_id"])))
                # debit the deficit of whichever bucket still needs
                for b in BUCKET_ORDER:
                    if deficits.get(b, 0) > 0:
                        deficits[b] -= 1
                        break
                if sum(deficits.values()) == 0:
                    break
        if filled == 0:
            print(f"  [overflow] nao sobrou ninguem para preencher {needed} vagas")
            break

    assert len(selected) == PILOT_SIZE, f"pilot tem {len(selected)} != {PILOT_SIZE}"

    # ---------- Reservas (alvo 60 = 10 por bucket, com overflow deterministico) ----------
    RESERVAS_TARGET = 60
    reservas = []
    reservas_set = set()
    # Passo 1: 10 per bucket quando possivel, ordem deterministica
    reservas_deficits = {}
    for b in BUCKET_ORDER:
        avail_not_selected = [
            r for r in by_bucket[b]
            if int(r["render_wine_id"]) not in selected_set
        ]
        take = avail_not_selected[:RESERVAS_PER_BUCKET]
        for r in take:
            r2 = dict(r)
            r2["reserva_origin"] = b
            reservas.append(r2)
            reservas_set.add(int(r["render_wine_id"]))
        if len(take) < RESERVAS_PER_BUCKET:
            reservas_deficits[b] = RESERVAS_PER_BUCKET - len(take)

    # Passo 2: overflow para reservas (se faltar, mesma prioridade do pilot overflow)
    reservas_overflow_log = []
    while len(reservas) < RESERVAS_TARGET:
        filled_this_round = False
        for donor_bucket in overflow_priority:
            if len(reservas) >= RESERVAS_TARGET:
                break
            for r in by_bucket[donor_bucket]:
                wid = int(r["render_wine_id"])
                if wid in selected_set or wid in reservas_set:
                    continue
                r2 = dict(r)
                r2["reserva_origin"] = f"overflow_from_{donor_bucket}"
                reservas.append(r2)
                reservas_set.add(wid)
                reservas_overflow_log.append((donor_bucket, wid))
                filled_this_round = True
                if len(reservas) >= RESERVAS_TARGET:
                    break
        if not filled_this_round:
            print(f"[reservas] nao ha mais wines disponiveis: {len(reservas)}/{RESERVAS_TARGET}")
            break

    if reservas_deficits:
        for b, d in reservas_deficits.items():
            print(f"  [reservas deficit] {b}: {d} faltando (preenchido via overflow)")

    print(f"[select] pilot: {len(selected)}, reservas: {len(reservas)}")

    # ---------- Escrever pilot e reservas ----------
    pilot_fields = list(selected[0].keys())
    if "overflow_from" not in pilot_fields:
        pilot_fields.append("overflow_from")
    with open(args.out_pilot, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=pilot_fields, extrasaction="ignore")
        w.writeheader()
        for r in selected:
            w.writerow(r)
    print(f"[write] {args.out_pilot}")

    res_fields = list(annotated[0].keys())
    with open(args.out_reservas, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=res_fields, extrasaction="ignore")
        w.writeheader()
        for r in reservas:
            w.writerow(r)
    print(f"[write] {args.out_reservas}")

    # Resumo bucket counts no pilot
    pilot_bucket_counts = Counter(r["pilot_bucket_proxy"] for r in selected)
    print()
    print(f"[pilot] distribuicao final:")
    for b in BUCKET_ORDER:
        print(f"    {b:40s} = {pilot_bucket_counts.get(b, 0):>4}")


if __name__ == "__main__":
    main()
