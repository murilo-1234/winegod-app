"""
Demanda 7 -- Gera o review pack curto do pilot_120 para revisao R1 humana.

READ-ONLY. Consome:
  - reports/tail_pilot_120_2026-04-10.csv (pilot com bucket_proxy e reason)
  - reports/tail_working_pool_fanout_detail_2026-04-10.csv.gz (top1 legivel por canal)

Saida:
  - sobrescreve reports/tail_pilot_120_2026-04-10.csv com o schema completo
    pedido na Tarefa E, na ordem especificada pela demanda.

Schema esperado:
  render_wine_id, nome, produtor, safra, tipo,
  preco_min, wine_sources_count_live, stores_count_live, no_source_flag,
  y2_present, y2_status_set,
  pilot_bucket_proxy,
  top1_render_candidate_id, top1_render_channel, top1_render_score, top1_render_gap,
  top1_import_candidate_id, top1_import_channel, top1_import_score, top1_import_gap,
  best_overall_universe, best_overall_channel, best_overall_score,
  reason_short_proxy,
  top1_render_human, top1_import_human,  (resumo legivel)
  block, hash_key, overflow_from  (trilha)
"""

import csv
import gzip
import os
import sys

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports")

PILOT_IN = os.path.join(REPORT_DIR, "tail_pilot_120_2026-04-10.csv")
DETAIL = os.path.join(REPORT_DIR, "tail_working_pool_fanout_detail_2026-04-10.csv.gz")
PILOT_OUT = os.path.join(REPORT_DIR, "tail_pilot_120_2026-04-10.csv")  # sobrescreve


REVIEW_FIELDS = [
    "render_wine_id", "nome", "produtor", "safra", "tipo",
    "preco_min", "wine_sources_count_live", "stores_count_live", "no_source_flag",
    "y2_present", "y2_status_set",
    "pilot_bucket_proxy",
    "top1_render_candidate_id", "top1_render_channel", "top1_render_score", "top1_render_gap",
    "top1_import_candidate_id", "top1_import_channel", "top1_import_score", "top1_import_gap",
    "best_overall_universe", "best_overall_channel", "best_overall_score",
    "reason_short_proxy",
    "top1_render_human", "top1_import_human",
    "block", "hash_key", "overflow_from",
]


def load_top1_humans(detail_path, wids):
    """Para cada wid e universo (render|import), achar o candidato que
    combina (rank=1, melhor score). A per_wine ja tem o top1_*_candidate_id
    resolvido, aqui so pegamos nome_produtor do detail para texto humano."""
    # wid -> universe -> candidate_id -> (nome, produtor, safra, tipo, score, gap)
    index = {}
    wids_set = set(wids)
    with gzip.open(detail_path, "rt", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            wid = int(r["render_wine_id"])
            if wid not in wids_set:
                continue
            if int(r["candidate_rank"]) != 1:
                continue
            uni = r["candidate_universe"]
            idx_wid = index.setdefault(wid, {}).setdefault(uni, [])
            idx_wid.append({
                "cid": r["candidate_id"],
                "ch": r["channel"],
                "nome": r.get("candidate_nome", ""),
                "produtor": r.get("candidate_produtor", ""),
                "safra": r.get("candidate_safra", ""),
                "tipo": r.get("candidate_tipo", ""),
                "score": r.get("raw_score", ""),
                "gap": r.get("top1_top2_gap", ""),
            })
    return index


def main():
    pilot_rows = []
    with open(PILOT_IN, "r", encoding="utf-8", newline="") as f:
        pilot_rows = list(csv.DictReader(f))
    print(f"[pilot] {len(pilot_rows)} wines")

    wids = [int(r["render_wine_id"]) for r in pilot_rows]
    print(f"[detail] carregando top1 humans...")
    index = load_top1_humans(DETAIL, wids)
    print(f"[detail] {len(index)} wines com top1 no detail")

    def build_human(wid, universe):
        entries = index.get(wid, {}).get(universe, [])
        if not entries:
            return ""
        # maior score, tiebreak id ASC -- mesma logica da D5
        entries.sort(key=lambda e: (-float(e["score"] or 0), int(e["cid"] or 0)))
        top = entries[0]
        parts = []
        if top.get("produtor"):
            parts.append(top["produtor"])
        if top.get("nome"):
            parts.append(top["nome"])
        human = " | ".join(parts) if parts else f"id={top['cid']}"
        safra = top.get("safra", "") or ""
        tipo = top.get("tipo", "") or ""
        extras = []
        if safra:
            extras.append(f"safra={safra}")
        if tipo:
            extras.append(f"tipo={tipo}")
        extras.append(f"score={top['score']}")
        return f"{human}  [{top['ch']}]  ({', '.join(extras)})"

    enriched = []
    for r in pilot_rows:
        wid = int(r["render_wine_id"])
        out = {}
        for k in REVIEW_FIELDS:
            out[k] = r.get(k, "")
        out["top1_render_human"] = build_human(wid, "render")
        out["top1_import_human"] = build_human(wid, "import")
        enriched.append(out)

    with open(PILOT_OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=REVIEW_FIELDS)
        w.writeheader()
        w.writerows(enriched)
    print(f"[write] {PILOT_OUT}")


if __name__ == "__main__":
    main()
