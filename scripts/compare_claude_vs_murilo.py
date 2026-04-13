"""
Demanda 9 -- Comparador Claude R1 vs Murilo R1.

READ-ONLY. Nao toca banco.

Entradas:
  - reports/tail_pilot_120_r1_claude_2026-04-10.csv    (R1 do Claude, sempre preenchida)
  - reports/tail_pilot_120_for_murilo_2026-04-10.csv   (contem tanto r1_* quanto murilo_*)

Se o `for_murilo` nao estiver preenchido (todas as colunas murilo_* vazias),
o script detecta isso e sai com mensagem clara sem gerar relatorios.

Saidas (quando ha dados Murilo):
  - reports/tail_pilot_120_concordance_2026-04-10.md       (relatorio human-readable)
  - reports/tail_pilot_120_disagreements_2026-04-10.csv    (lista de divergencias)

Metricas computadas:
  1) concordancia global por campo (business_class, review_state, confidence, action)
  2) matriz de confusao por campo (Claude linhas, Murilo colunas)
  3) concordancia por pilot_bucket_proxy
  4) concordancia por confidence do Claude
  5) lista de disagreements com contexto curto (reason_short do Claude + murilo_notes)

Uso:
  python scripts/compare_claude_vs_murilo.py
  python scripts/compare_claude_vs_murilo.py --for-murilo <path> --r1-claude <path>
"""

import argparse
import csv
import os
import sys
from collections import Counter, defaultdict

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports")
DEFAULT_R1 = os.path.join(REPORT_DIR, "tail_pilot_120_r1_claude_2026-04-10.csv")
DEFAULT_MURILO = os.path.join(REPORT_DIR, "tail_pilot_120_for_murilo_2026-04-10.csv")
OUT_CONCORDANCE = os.path.join(REPORT_DIR, "tail_pilot_120_concordance_2026-04-10.md")
OUT_DISAGREEMENTS = os.path.join(REPORT_DIR, "tail_pilot_120_disagreements_2026-04-10.csv")

COMPARE_FIELDS = ["business_class", "review_state", "confidence", "action"]


def load_csv_indexed(path, key="render_wine_id"):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return {int(r[key]): r for r in csv.DictReader(f)}


def norm(v):
    return (v or "").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--r1-claude", default=DEFAULT_R1)
    ap.add_argument("--for-murilo", default=DEFAULT_MURILO)
    ap.add_argument("--out-md", default=OUT_CONCORDANCE)
    ap.add_argument("--out-disagree", default=OUT_DISAGREEMENTS)
    args = ap.parse_args()

    if not os.path.exists(args.r1_claude):
        print(f"ERROR: {args.r1_claude} nao existe")
        sys.exit(1)
    if not os.path.exists(args.for_murilo):
        print(f"ERROR: {args.for_murilo} nao existe")
        sys.exit(1)

    print(f"[load] R1 Claude:  {args.r1_claude}")
    r1 = load_csv_indexed(args.r1_claude)
    print(f"       {len(r1)} rows")

    print(f"[load] for_murilo: {args.for_murilo}")
    mur = load_csv_indexed(args.for_murilo)
    print(f"       {len(mur)} rows")

    # Detect empty Murilo
    filled_count = sum(
        1 for r in mur.values()
        if norm(r.get("murilo_business_class")) or norm(r.get("murilo_review_state"))
    )
    print(f"[detect] murilo preenchido: {filled_count}/{len(mur)}")

    if filled_count == 0:
        print()
        print("=" * 60)
        print("CONCORDANCE PENDING: murilo ainda nao preencheu o CSV.")
        print("Execute este script novamente apos Murilo preencher")
        print(f"as colunas murilo_* em {args.for_murilo}.")
        print("=" * 60)
        sys.exit(2)

    if filled_count < len(mur):
        print(f"[aviso] somente {filled_count}/{len(mur)} rows preenchidas. "
              f"Concordance parcial sera computada.")

    # Join by render_wine_id
    wids_all = sorted(set(r1.keys()) & set(mur.keys()))
    print(f"[join] {len(wids_all)} wids em ambos")

    # Apenas rows preenchidas pelo Murilo
    wids = [
        w for w in wids_all
        if norm(mur[w].get("murilo_business_class"))
        and norm(mur[w].get("murilo_review_state"))
        and norm(mur[w].get("murilo_confidence"))
        and norm(mur[w].get("murilo_action"))
    ]
    print(f"[join] {len(wids)} rows com TODOS os 4 campos preenchidos (base de calculo)")

    if not wids:
        print()
        print("=" * 60)
        print("CONCORDANCE PENDING: nenhum row tem os 4 campos murilo_* preenchidos.")
        print("=" * 60)
        sys.exit(2)

    # ---- Per-field concordance ----
    field_stats = {}
    confusion = {f: defaultdict(lambda: Counter()) for f in COMPARE_FIELDS}
    for f in COMPARE_FIELDS:
        match = 0
        for wid in wids:
            c = norm(r1[wid].get(f))
            m = norm(mur[wid].get(f"murilo_{f}"))
            confusion[f][c][m] += 1
            if c == m:
                match += 1
        field_stats[f] = (match, len(wids), match / len(wids) if wids else 0)

    # ---- Per-bucket concordance (on business_class) ----
    per_bucket = defaultdict(lambda: [0, 0])  # [matches, total]
    for wid in wids:
        bucket = norm(mur[wid].get("pilot_bucket_proxy"))
        c = norm(r1[wid].get("business_class"))
        m = norm(mur[wid].get("murilo_business_class"))
        per_bucket[bucket][1] += 1
        if c == m:
            per_bucket[bucket][0] += 1

    # ---- Per-Claude-confidence concordance (on business_class) ----
    per_conf = defaultdict(lambda: [0, 0])
    for wid in wids:
        cconf = norm(r1[wid].get("confidence"))
        c = norm(r1[wid].get("business_class"))
        m = norm(mur[wid].get("murilo_business_class"))
        per_conf[cconf][1] += 1
        if c == m:
            per_conf[cconf][0] += 1

    # ---- Disagreement list ----
    disagreements = []
    for wid in wids:
        diffs = []
        for f in COMPARE_FIELDS:
            c = norm(r1[wid].get(f))
            m = norm(mur[wid].get(f"murilo_{f}"))
            if c != m:
                diffs.append(f)
        if diffs:
            m_row = mur[wid]
            disagreements.append({
                "render_wine_id": wid,
                "pilot_bucket_proxy": norm(m_row.get("pilot_bucket_proxy")),
                "nome": norm(m_row.get("nome")),
                "produtor": norm(m_row.get("produtor")),
                "fields_diff": ",".join(diffs),
                "r1_business_class": norm(r1[wid].get("business_class")),
                "murilo_business_class": norm(m_row.get("murilo_business_class")),
                "r1_review_state": norm(r1[wid].get("review_state")),
                "murilo_review_state": norm(m_row.get("murilo_review_state")),
                "r1_confidence": norm(r1[wid].get("confidence")),
                "murilo_confidence": norm(m_row.get("murilo_confidence")),
                "r1_action": norm(r1[wid].get("action")),
                "murilo_action": norm(m_row.get("murilo_action")),
                "r1_reason_short": norm(r1[wid].get("reason_short")),
                "murilo_notes": norm(m_row.get("murilo_notes")),
            })

    # Write disagreement CSV
    if disagreements:
        with open(args.out_disagree, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(disagreements[0].keys()))
            w.writeheader()
            w.writerows(disagreements)
        print(f"[write] {args.out_disagree} ({len(disagreements)} rows)")
    else:
        # Write empty header
        with open(args.out_disagree, "w", encoding="utf-8", newline="") as f:
            f.write("render_wine_id,pilot_bucket_proxy,nome,produtor,fields_diff\n")
        print(f"[write] {args.out_disagree} (sem disagreements)")

    # ---- Write MD report ----
    L = []
    L.append("# Tail Pilot 120 -- Concordance Claude vs Murilo")
    L.append("")
    L.append(f"- Base de calculo: {len(wids)} rows com 4 campos `murilo_*` preenchidos")
    L.append(f"- Comparacao sobre: `business_class`, `review_state`, `confidence`, `action`")
    L.append("")
    L.append("## Concordancia global por campo")
    L.append("")
    L.append("| campo | match | total | % |")
    L.append("|---|---|---|---|")
    for f in COMPARE_FIELDS:
        m, t, pct = field_stats[f]
        L.append(f"| {f} | {m} | {t} | {pct*100:.1f}% |")
    L.append("")

    L.append("## Matriz de confusao por campo")
    L.append("")
    L.append("Linhas = Claude. Colunas = Murilo.")
    L.append("")
    for f in COMPARE_FIELDS:
        L.append(f"### {f}")
        L.append("")
        # coletar labels
        labels = set()
        for k, d in confusion[f].items():
            labels.add(k)
            for m in d:
                labels.add(m)
        labels = sorted(labels)
        # header
        L.append("| Claude \\ Murilo | " + " | ".join(labels) + " |")
        L.append("|---" * (len(labels) + 1) + "|")
        for c in labels:
            row = [c]
            for m in labels:
                row.append(str(confusion[f][c].get(m, 0)))
            L.append("| " + " | ".join(row) + " |")
        L.append("")

    L.append("## Concordancia por pilot_bucket_proxy (em business_class)")
    L.append("")
    L.append("| bucket | match | total | % |")
    L.append("|---|---|---|---|")
    for b in sorted(per_bucket.keys()):
        m, t = per_bucket[b]
        pct = m / t * 100 if t else 0
        L.append(f"| {b} | {m} | {t} | {pct:.1f}% |")
    L.append("")

    L.append("## Concordancia por confidence Claude (em business_class)")
    L.append("")
    L.append("| r1_confidence | match | total | % |")
    L.append("|---|---|---|---|")
    for c in ("HIGH", "MEDIUM", "LOW"):
        m, t = per_conf.get(c, (0, 0))
        pct = m / t * 100 if t else 0
        L.append(f"| {c} | {m} | {t} | {pct:.1f}% |")
    L.append("")

    L.append("## Disagreements")
    L.append("")
    L.append(f"- Total de rows com pelo menos 1 campo divergente: **{len(disagreements)} / {len(wids)}**")
    L.append(f"- Detalhes em `{os.path.basename(args.out_disagree)}`")
    L.append("")
    if disagreements:
        L.append("### Amostra (primeiros 10)")
        L.append("")
        L.append("| wid | bucket | r1_bc -> m_bc | r1_rs -> m_rs | r1_conf -> m_conf | r1_act -> m_act |")
        L.append("|---|---|---|---|---|---|")
        for d in disagreements[:10]:
            L.append(
                f"| {d['render_wine_id']} "
                f"| {d['pilot_bucket_proxy']} "
                f"| {d['r1_business_class']} -> {d['murilo_business_class']} "
                f"| {d['r1_review_state']} -> {d['murilo_review_state']} "
                f"| {d['r1_confidence']} -> {d['murilo_confidence']} "
                f"| {d['r1_action']} -> {d['murilo_action']} |"
            )
        L.append("")

    with open(args.out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print(f"[write] {args.out_md}")

    print()
    print("=== concordance REPORT done ===")
    for f in COMPARE_FIELDS:
        m, t, pct = field_stats[f]
        print(f"  {f:20s}: {m}/{t} ({pct*100:.1f}%)")


if __name__ == "__main__":
    main()
