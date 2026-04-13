"""
Demanda 9 -- Gera o template/artefato de adjudicacao dos disagreements
Claude vs Murilo.

READ-ONLY. Nao toca banco.

Dois modos:

1) **Modo template** (default, estado atual): quando o `for_murilo` CSV
   ainda nao tem preenchimento humano, gera um template CSV com o schema
   final de adjudicacao mas ZERO rows preenchidas. Util para congelar
   contrato de colunas antes da fase humana.

2) **Modo real**: quando Murilo ja preencheu, carrega os disagreements
   (via a mesma logica de compare_claude_vs_murilo) e gera uma linha para
   cada caso divergente, com campos `adjudicated_*` vazios para serem
   preenchidos na adjudicacao.

Uso:
  python scripts/build_adjudication_template.py                    # auto-detect
  python scripts/build_adjudication_template.py --template-only    # forca template
"""

import argparse
import csv
import os
import sys

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports")
DEFAULT_R1 = os.path.join(REPORT_DIR, "tail_pilot_120_r1_claude_2026-04-10.csv")
DEFAULT_MURILO = os.path.join(REPORT_DIR, "tail_pilot_120_for_murilo_2026-04-10.csv")
OUT_TEMPLATE = os.path.join(REPORT_DIR, "tail_pilot_120_adjudication_template_2026-04-10.csv")
OUT_ADJUD = os.path.join(REPORT_DIR, "tail_pilot_120_adjudication_2026-04-10.csv")


ADJUDICATION_COLUMNS = [
    "render_wine_id",
    "pilot_bucket_proxy",
    "nome",
    "produtor",
    "r1_business_class",
    "murilo_business_class",
    "r1_review_state",
    "murilo_review_state",
    "r1_confidence",
    "murilo_confidence",
    "r1_action",
    "murilo_action",
    "r1_reason_short",
    "murilo_notes",
    "adjudicated_business_class",
    "adjudicated_review_state",
    "adjudicated_confidence",
    "adjudicated_action",
    "adjudication_notes",
]


def norm(v):
    return (v or "").strip()


def load_indexed(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return {int(r["render_wine_id"]): r for r in csv.DictReader(f)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--r1-claude", default=DEFAULT_R1)
    ap.add_argument("--for-murilo", default=DEFAULT_MURILO)
    ap.add_argument("--out-template", default=OUT_TEMPLATE)
    ap.add_argument("--out-adjud", default=OUT_ADJUD)
    ap.add_argument("--template-only", action="store_true",
                    help="Forca geracao so do template, mesmo se Murilo estiver preenchido")
    args = ap.parse_args()

    # Sempre garantir o template (schema frozen)
    print(f"[template] escrevendo {args.out_template}")
    with open(args.out_template, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ADJUDICATION_COLUMNS)
        w.writeheader()
    print(f"[template] {args.out_template} criado com schema de {len(ADJUDICATION_COLUMNS)} colunas")

    if args.template_only:
        print("=== adjudication: TEMPLATE ONLY ===")
        return

    if not os.path.exists(args.for_murilo):
        print(f"[info] {args.for_murilo} nao existe; so template foi gerado")
        return

    print(f"[load] R1 Claude:  {args.r1_claude}")
    r1 = load_indexed(args.r1_claude)

    print(f"[load] for_murilo: {args.for_murilo}")
    mur = load_indexed(args.for_murilo)

    # Detect empty
    filled = sum(
        1 for r in mur.values()
        if norm(r.get("murilo_business_class")) and norm(r.get("murilo_review_state"))
    )
    print(f"[detect] murilo preenchido: {filled}/{len(mur)}")

    if filled == 0:
        print()
        print("=" * 60)
        print("ADJUDICATION PENDING: murilo ainda nao preencheu o CSV.")
        print(f"Template em {args.out_template} com schema frozen.")
        print("=" * 60)
        sys.exit(2)

    # Build adjudication rows (only disagreements)
    wids = sorted(set(r1.keys()) & set(mur.keys()))
    adjud_rows = []
    for wid in wids:
        rc = r1[wid]
        rm = mur[wid]
        # Skip if Murilo nao preencheu os 4 campos principais
        if not all(norm(rm.get(f"murilo_{f}")) for f in ("business_class", "review_state", "confidence", "action")):
            continue

        diffs = []
        for f in ("business_class", "review_state", "confidence", "action"):
            if norm(rc.get(f)) != norm(rm.get(f"murilo_{f}")):
                diffs.append(f)
        if not diffs:
            continue

        adjud_rows.append({
            "render_wine_id": wid,
            "pilot_bucket_proxy": norm(rm.get("pilot_bucket_proxy")),
            "nome": norm(rm.get("nome")),
            "produtor": norm(rm.get("produtor")),
            "r1_business_class": norm(rc.get("business_class")),
            "murilo_business_class": norm(rm.get("murilo_business_class")),
            "r1_review_state": norm(rc.get("review_state")),
            "murilo_review_state": norm(rm.get("murilo_review_state")),
            "r1_confidence": norm(rc.get("confidence")),
            "murilo_confidence": norm(rm.get("murilo_confidence")),
            "r1_action": norm(rc.get("action")),
            "murilo_action": norm(rm.get("murilo_action")),
            "r1_reason_short": norm(rc.get("reason_short")),
            "murilo_notes": norm(rm.get("murilo_notes")),
            "adjudicated_business_class": "",
            "adjudicated_review_state": "",
            "adjudicated_confidence": "",
            "adjudicated_action": "",
            "adjudication_notes": "",
        })

    with open(args.out_adjud, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ADJUDICATION_COLUMNS)
        w.writeheader()
        w.writerows(adjud_rows)
    print(f"[write] {args.out_adjud} ({len(adjud_rows)} disagreements)")
    print("=== adjudication: BUILT ===")


if __name__ == "__main__":
    main()
