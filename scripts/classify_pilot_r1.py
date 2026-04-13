"""
Demanda 8 -- Classificacao R1 (Claude) dos 120 wines do pilot + geracao de
dossie curto + pacote de revisao para Murilo.

READ-ONLY. Nao toca Postgres.

Entradas:
  - reports/tail_pilot_120_2026-04-10.csv               (pilot com bucket/per_wine)
  - reports/tail_working_pool_fanout_detail_2026-04-10.csv.gz  (top3 por canal por wine)

Saidas:
  - reports/tail_pilot_120_dossier_short_2026-04-10.csv (pilot + top3 render/import)
  - reports/tail_pilot_120_r1_claude_2026-04-10.csv     (R1 Claude classification)
  - reports/tail_pilot_120_for_murilo_2026-04-10.csv    (pacote de revisao para Murilo)

Logica de classificacao:

  Taxonomia oficial:
    business_class in {MATCH_RENDER, MATCH_IMPORT, STANDALONE_WINE, NOT_WINE}
    review_state   in {RESOLVED, SECOND_REVIEW, UNRESOLVED}
    confidence     in {HIGH, MEDIUM, LOW}
    action         in {ALIAS, IMPORT_THEN_ALIAS, KEEP_STANDALONE, SUPPRESS}
    data_quality   in {GOOD, FAIR, POOR}
    product_impact in {HIGH, MEDIUM, LOW}

  Arvore de decisao (aplicada em ordem, primeiro que bate, pronto):

    1) wine_filter.classify_product(nome) == 'not_wine' (com categoria forte)
       -> NOT_WINE, RESOLVED, HIGH, SUPPRESS

    2) nome vazio/curto (len<3)
       -> STANDALONE_WINE (best-guess), UNRESOLVED, LOW, KEEP_STANDALONE
          (UNRESOLVED marca que nao da para decidir)

    3) y2_any_not_wine_or_spirit=1 mas wine_filter nao bloqueou
       -> NOT_WINE como hipotese de trabalho, SECOND_REVIEW, MEDIUM, SUPPRESS
          (y2 e baseline nao verdade)

    4) Render STRONG: r_score >= 0.50 AND r_gap >= 0.10
       -> MATCH_RENDER, RESOLVED, HIGH, ALIAS

    5) Render MEDIUM: r_score >= 0.45 (mesmo com gap baixo/zero, o top1 tende a ser bom)
       -> MATCH_RENDER, SECOND_REVIEW, MEDIUM, ALIAS
          (tiebreak SQL cai em ids vizinhos; humano decide entre candidatos do top3)

    6) Import STRONG: i_score >= 0.40 AND i_gap >= 0.10
       -> MATCH_IMPORT, SECOND_REVIEW, MEDIUM, IMPORT_THEN_ALIAS

    7) Render WEAK: r_score >= 0.30 (ambiguo; nome parece vinho mas match fraco)
       -> STANDALONE_WINE, SECOND_REVIEW, LOW, KEEP_STANDALONE

    8) No meaningful candidate
       -> STANDALONE_WINE, UNRESOLVED, LOW, KEEP_STANDALONE

  data_quality:
    GOOD: len(nome)>=15 AND len(prod)>=5 AND (safra OR tipo)
    FAIR: len(nome)>=10 AND len(prod)>=3
    POOR: otherwise

  product_impact:
    HIGH:  wine_sources_count_live >= 5
    MEDIUM: 2..4
    LOW:   0..1 OR no_source_flag=1

  needs_murilo_review = 1 para todos os 120 (pilot inteiro vai para Murilo).
  murilo_review_reason varia com a classificacao.
"""

import csv
import gzip
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wine_filter import classify_product  # noqa: E402


REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports")

PILOT_CSV = os.path.join(REPORT_DIR, "tail_pilot_120_2026-04-10.csv")
WITH_BUCKETS = os.path.join(REPORT_DIR, "tail_working_pool_with_buckets_2026-04-10.csv")
DETAIL = os.path.join(REPORT_DIR, "tail_working_pool_fanout_detail_2026-04-10.csv.gz")
OUT_DOSSIER = os.path.join(REPORT_DIR, "tail_pilot_120_dossier_short_2026-04-10.csv")
OUT_R1 = os.path.join(REPORT_DIR, "tail_pilot_120_r1_claude_2026-04-10.csv")
OUT_MURILO = os.path.join(REPORT_DIR, "tail_pilot_120_for_murilo_2026-04-10.csv")


# Campos crus que o for_murilo precisa carregar explicitamente (D9 Tarefa A).
# Vem do working_pool_with_buckets, que e a fonte autoritativa.
RAW_FLAG_FIELDS = [
    "y2_any_not_wine_or_spirit",
    "wine_filter_category",
    "block",
    "reason_short_proxy",
]


# ---------- helpers ----------

def pf(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def pi(s):
    try:
        return int(s)
    except (TypeError, ValueError):
        return 0


def compute_data_quality(nome, prod, safra, tipo):
    lnome = len((nome or "").strip())
    lprod = len((prod or "").strip())
    has_meta = bool((safra or "").strip()) or bool((tipo or "").strip())
    if lnome >= 15 and lprod >= 5 and has_meta:
        return "GOOD"
    if lnome >= 10 and lprod >= 3:
        return "FAIR"
    return "POOR"


def compute_product_impact(wsc, no_source):
    if no_source or wsc == 0:
        return "LOW"
    if wsc >= 5:
        return "HIGH"
    if wsc >= 2:
        return "MEDIUM"
    return "LOW"


# ---------- top3 per universe from detail ----------

def build_top3_by_universe(detail_path, wids):
    """
    Para cada wid, construir top3 render (melhores 3 candidates distintos
    dentre TODOS os canais render) e top3 import.

    Ordenacao: (raw_score DESC, candidate_id ASC)
    """
    wids_set = set(wids)
    per_wine = defaultdict(lambda: {"render": [], "import": []})
    with gzip.open(detail_path, "rt", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            wid = int(r["render_wine_id"])
            if wid not in wids_set:
                continue
            uni = r["candidate_universe"]
            per_wine[wid][uni].append({
                "id": r["candidate_id"],
                "nome": r.get("candidate_nome", ""),
                "produtor": r.get("candidate_produtor", ""),
                "safra": r.get("candidate_safra", ""),
                "tipo": r.get("candidate_tipo", ""),
                "score": float(r.get("raw_score", 0) or 0),
                "channel": r["channel"],
            })

    # Para cada wid, dedupe por candidate_id (keep best score, tiebreak por canal),
    # sort, take top3
    out = {}
    for wid, universes in per_wine.items():
        top3 = {"render": [], "import": []}
        for uni in ("render", "import"):
            # dedupe por id
            seen = {}
            for c in universes[uni]:
                cid = c["id"]
                if cid not in seen or c["score"] > seen[cid]["score"]:
                    seen[cid] = c
            sorted_cands = sorted(seen.values(), key=lambda c: (-c["score"], int(c["id"] or 0)))
            top3[uni] = sorted_cands[:3]
        out[wid] = top3
    return out


def format_top3_summary(top3_list):
    """Retorna string legivel para top3."""
    if not top3_list:
        return ""
    parts = []
    for i, c in enumerate(top3_list, 1):
        prod = c.get("produtor", "") or ""
        nome = c.get("nome", "") or ""
        label = f"{prod} | {nome}".strip(" |") or f"id={c['id']}"
        meta = []
        if c.get("safra"):
            meta.append(f"safra={c['safra']}")
        if c.get("tipo"):
            meta.append(f"tipo={c['tipo']}")
        meta.append(f"score={c['score']:.3f}")
        meta.append(c.get("channel", ""))
        parts.append(f"[{i}] {label}  ({', '.join(meta)})")
    return " || ".join(parts)


# ---------- classifier ----------

def classify_wine(wine, top3):
    nome = wine.get("nome", "") or ""
    prod = wine.get("produtor", "") or ""
    safra = wine.get("safra", "") or ""
    tipo = wine.get("tipo", "") or ""
    bucket = wine.get("pilot_bucket_proxy", "") or ""
    ns = wine.get("no_source_flag", "") == "1"
    # y2_any_not_wine_or_spirit nao esta no pilot CSV; detecta via reason_short_proxy
    # (assign_pilot_buckets.py grava "y2_any_not_wine_or_spirit=1" como reason
    # quando esse foi o gatilho do P1 bucket)
    reason_proxy = wine.get("reason_short_proxy", "") or ""
    y2_nw = (
        wine.get("y2_any_not_wine_or_spirit", "") == "1"
        or "y2_any_not_wine_or_spirit" in reason_proxy
    )
    wsc = pi(wine.get("wine_sources_count_live", ""))

    r_score = pf(wine.get("top1_render_score", ""))
    r_gap = pf(wine.get("top1_render_gap", ""))
    r_cand = (wine.get("top1_render_candidate_id", "") or "").strip()
    r_ch = wine.get("top1_render_channel", "") or ""
    r_human = wine.get("top1_render_human", "") or ""

    i_score = pf(wine.get("top1_import_score", ""))
    i_gap = pf(wine.get("top1_import_gap", ""))
    i_cand = (wine.get("top1_import_candidate_id", "") or "").strip()
    i_human = wine.get("top1_import_human", "") or ""

    data_quality = compute_data_quality(nome, prod, safra, tipo)
    product_impact = compute_product_impact(wsc, ns)

    # Step 1: wine_filter blocks the nome
    cls, cat = classify_product(nome)
    if cls == "not_wine" and cat and cat != "nome_vazio_ou_curto":
        return {
            "business_class": "NOT_WINE",
            "review_state": "RESOLVED",
            "confidence": "HIGH",
            "action": "SUPPRESS",
            "recommended_universe": "",
            "recommended_candidate_id": "",
            "match_blockers": f"wine_filter={cat}",
            "reason_short": f"nome bloqueado por wine_filter ({cat})",
            "reason_long": (
                f"wine_filter.classify_product retornou not_wine com match '{cat}'. "
                f"Nome: '{nome[:120]}'. Acao recomendada: SUPPRESS."
            ),
            "data_quality": data_quality,
            "product_impact": product_impact,
        }

    # Step 2: nome vazio/curto
    if cls == "not_wine" and cat == "nome_vazio_ou_curto":
        return {
            "business_class": "STANDALONE_WINE",
            "review_state": "UNRESOLVED",
            "confidence": "LOW",
            "action": "KEEP_STANDALONE",
            "recommended_universe": "",
            "recommended_candidate_id": "",
            "match_blockers": "nome_vazio_ou_curto",
            "reason_short": "dados minimos insuficientes para classificar",
            "reason_long": (
                f"nome com len<3 (ou vazio). Nao da para decidir "
                f"business_class. Marcado como STANDALONE_WINE best-guess com "
                f"review_state=UNRESOLVED; humano decide se deve ser suprimido."
            ),
            "data_quality": "POOR",
            "product_impact": product_impact,
        }

    # Step 3: y2 flagged not_wine mas wine_filter nao bloqueou
    if y2_nw:
        return {
            "business_class": "NOT_WINE",
            "review_state": "SECOND_REVIEW",
            "confidence": "MEDIUM",
            "action": "SUPPRESS",
            "recommended_universe": "",
            "recommended_candidate_id": "",
            "match_blockers": "y2_flagged_wine_filter_did_not",
            "reason_short": "y2_any_not_wine_or_spirit=1 (baseline, nao verdade)",
            "reason_long": (
                f"y2_any_not_wine_or_spirit=1 em alguma run de y2, mas "
                f"wine_filter.classify_product NAO bloqueou. Hipotese de "
                f"trabalho: NOT_WINE. Precisa confirmacao humana -- y2 e "
                f"baseline, nao verdade. Nome: '{nome[:120]}'."
            ),
            "data_quality": data_quality,
            "product_impact": product_impact,
        }

    # Step 4: Render STRONG (RESOLVED, HIGH)
    if (r_score is not None and r_score >= 0.50
            and r_gap is not None and r_gap >= 0.10):
        return {
            "business_class": "MATCH_RENDER",
            "review_state": "RESOLVED",
            "confidence": "HIGH",
            "action": "ALIAS",
            "recommended_universe": "render",
            "recommended_candidate_id": r_cand,
            "match_blockers": "",
            "reason_short": f"render score={r_score:.3f} gap={r_gap:.3f} (forte)",
            "reason_long": (
                f"top1 render '{r_human[:120]}' tem score >= 0.50 e gap ao "
                f"top2 >= 0.10. Match forte e sem ambiguidade. Acao: ALIAS "
                f"do render_wine_id={wine.get('render_wine_id')} para "
                f"candidate_id={r_cand}."
            ),
            "data_quality": data_quality,
            "product_impact": product_impact,
        }

    # Step 5a: Render MEDIUM-with-score >= 0.45 (tiebreak possivel no gap)
    if r_score is not None and r_score >= 0.45:
        return {
            "business_class": "MATCH_RENDER",
            "review_state": "SECOND_REVIEW",
            "confidence": "MEDIUM",
            "action": "ALIAS",
            "recommended_universe": "render",
            "recommended_candidate_id": r_cand,
            "match_blockers": (
                f"tiebreak_gap={r_gap:.3f}" if r_gap is not None else "no_gap"
            ),
            "reason_short": f"render score={r_score:.3f} gap={r_gap}",
            "reason_long": (
                f"top1 render '{r_human[:120]}' tem score >= 0.45 mas gap "
                f"pequeno ou zero ao top2 (empate no LIMIT 100). Recomenda-se "
                f"MATCH_RENDER mas humano precisa escolher entre os top3 "
                f"empatados. Ver dossier_short para o top3 completo."
            ),
            "data_quality": data_quality,
            "product_impact": product_impact,
        }

    # Step 5b: Render MEDIUM-with-gap (0.35 <= score < 0.45 AND gap >= 0.05)
    # Alinha com o criterio do P4 bucket: score forte o bastante + gap real
    if (r_score is not None and r_score >= 0.35
            and r_gap is not None and r_gap >= 0.05):
        return {
            "business_class": "MATCH_RENDER",
            "review_state": "SECOND_REVIEW",
            "confidence": "MEDIUM",
            "action": "ALIAS",
            "recommended_universe": "render",
            "recommended_candidate_id": r_cand,
            "match_blockers": f"score_medio={r_score:.3f}",
            "reason_short": f"render score={r_score:.3f} gap={r_gap:.3f}",
            "reason_long": (
                f"top1 render '{r_human[:120]}' tem score 0.35..0.45 com gap "
                f">= 0.05. Passou o filtro do P4 (strong render proxy) por um "
                f"fio. Match plausivel mas merece humano. Ver top3 render no dossier."
            ),
            "data_quality": data_quality,
            "product_impact": product_impact,
        }

    # Step 6: Import STRONG (SECOND_REVIEW, MEDIUM)
    if (i_score is not None and i_score >= 0.40
            and i_gap is not None and i_gap >= 0.10):
        return {
            "business_class": "MATCH_IMPORT",
            "review_state": "SECOND_REVIEW",
            "confidence": "MEDIUM",
            "action": "IMPORT_THEN_ALIAS",
            "recommended_universe": "import",
            "recommended_candidate_id": i_cand,
            "match_blockers": (
                f"render_score={r_score}" if r_score is not None else "no_render_score"
            ),
            "reason_short": f"import score={i_score:.3f} gap={i_gap:.3f}",
            "reason_long": (
                f"top1 import '{i_human[:120]}' tem score forte e gap >= 0.10. "
                f"Nenhum render forte concorre. Acao: IMPORT_THEN_ALIAS -- "
                f"primeiro trazer canonico do vivino_db para Render, depois "
                f"criar alias. Requer SECOND_REVIEW."
            ),
            "data_quality": data_quality,
            "product_impact": product_impact,
        }

    # Step 7: Render weak (STANDALONE_WINE, SECOND_REVIEW, LOW)
    if r_score is not None and r_score >= 0.30:
        return {
            "business_class": "STANDALONE_WINE",
            "review_state": "SECOND_REVIEW",
            "confidence": "LOW",
            "action": "KEEP_STANDALONE",
            "recommended_universe": "",
            "recommended_candidate_id": "",
            "match_blockers": f"render_score={r_score:.3f}_below_match_threshold",
            "reason_short": f"match fraco (r={r_score:.3f})",
            "reason_long": (
                f"top1 render '{r_human[:120]}' tem score entre 0.30 e 0.45 "
                f"(insuficiente para HIGH ou MEDIUM match). Nome sugere vinho "
                f"real mas sem canonico claramente igual. Provavel "
                f"STANDALONE_WINE. Humano confirma."
            ),
            "data_quality": data_quality,
            "product_impact": product_impact,
        }

    # Step 8: No meaningful candidate
    return {
        "business_class": "STANDALONE_WINE",
        "review_state": "UNRESOLVED",
        "confidence": "LOW",
        "action": "KEEP_STANDALONE",
        "recommended_universe": "",
        "recommended_candidate_id": "",
        "match_blockers": "no_strong_candidate_in_any_channel",
        "reason_short": "sem candidato defensavel",
        "reason_long": (
            f"nenhum canal (render/import) produziu top1 com score >= 0.30. "
            f"Metadata pode indicar vinho real, mas nao ha canonico claro. "
            f"Humano decide entre KEEP_STANDALONE e SUPPRESS."
        ),
        "data_quality": data_quality,
        "product_impact": product_impact,
    }


def build_murilo_review_reason(r1):
    """Motivo curto pelo qual este wine precisa dos olhos de Murilo."""
    rs = r1["review_state"]
    bc = r1["business_class"]
    conf = r1["confidence"]

    if rs == "UNRESOLVED":
        return "incerteza real -- Claude nao decidiu"
    if rs == "SECOND_REVIEW":
        if bc == "MATCH_RENDER":
            return "match render ambiguo (tiebreak)"
        if bc == "MATCH_IMPORT":
            return "import candidato -- validar antes de IMPORT_THEN_ALIAS"
        if bc == "NOT_WINE":
            return "y2 flagou not_wine mas wine_filter nao -- confirmar"
        if bc == "STANDALONE_WINE":
            return "match fraco -- validar standalone vs match"
    if rs == "RESOLVED" and bc == "MATCH_RENDER" and conf == "HIGH":
        return "validar calibragem R1 Claude em match HIGH"
    if rs == "RESOLVED" and bc == "NOT_WINE" and conf == "HIGH":
        return "validar calibragem R1 Claude em not_wine bloqueado"
    return "validacao generica do pilot"


# ---------- main ----------

def main():
    print("[load] pilot_120...")
    with open(PILOT_CSV, "r", encoding="utf-8", newline="") as f:
        pilot = list(csv.DictReader(f))
    print(f"    {len(pilot)} wines")

    print("[load] working_pool_with_buckets (raw flags)...")
    raw_by_wid = {}
    with open(WITH_BUCKETS, "r", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            raw_by_wid[int(r["render_wine_id"])] = r
    print(f"    {len(raw_by_wid)} rows no with_buckets")

    # D9 Tarefa A: injeta raw flags em cada pilot row (in-place, nao muda classificacao,
    # so propaga proveniencia).
    for wine in pilot:
        wid = int(wine["render_wine_id"])
        raw = raw_by_wid.get(wid, {})
        for f in RAW_FLAG_FIELDS:
            if f not in wine or not wine.get(f):
                wine[f] = raw.get(f, "")

    wids = [int(r["render_wine_id"]) for r in pilot]
    print(f"[load] detail top3 por wine...")
    top3_by_wine = build_top3_by_universe(DETAIL, wids)
    print(f"    {len(top3_by_wine)} wines com top3")

    # ---------- DOSSIER ----------
    dossier_rows = []
    r1_rows = []
    murilo_rows = []

    for wine in pilot:
        wid = int(wine["render_wine_id"])
        top3 = top3_by_wine.get(wid, {"render": [], "import": []})

        top3_render_str = format_top3_summary(top3["render"])
        top3_import_str = format_top3_summary(top3["import"])

        # Dossier row (com flags cruas endurecidas em D9)
        dossier = {
            "render_wine_id": wid,
            "pilot_bucket_proxy": wine["pilot_bucket_proxy"],
            "block": wine.get("block", ""),
            "overflow_from": wine.get("overflow_from", ""),
            "nome": wine.get("nome", ""),
            "produtor": wine.get("produtor", ""),
            "safra": wine.get("safra", ""),
            "tipo": wine.get("tipo", ""),
            "preco_min": wine.get("preco_min", ""),
            "wine_sources_count_live": wine.get("wine_sources_count_live", ""),
            "stores_count_live": wine.get("stores_count_live", ""),
            "no_source_flag": wine.get("no_source_flag", ""),
            "y2_present": wine.get("y2_present", ""),
            "y2_status_set": wine.get("y2_status_set", ""),
            "y2_any_not_wine_or_spirit": wine.get("y2_any_not_wine_or_spirit", ""),
            "wine_filter_category": wine.get("wine_filter_category", ""),
            "reason_short_proxy": wine.get("reason_short_proxy", ""),
            "top1_render_candidate_id": wine.get("top1_render_candidate_id", ""),
            "top1_render_channel": wine.get("top1_render_channel", ""),
            "top1_render_score": wine.get("top1_render_score", ""),
            "top1_render_gap": wine.get("top1_render_gap", ""),
            "top1_import_candidate_id": wine.get("top1_import_candidate_id", ""),
            "top1_import_channel": wine.get("top1_import_channel", ""),
            "top1_import_score": wine.get("top1_import_score", ""),
            "top1_import_gap": wine.get("top1_import_gap", ""),
            "best_overall_universe": wine.get("best_overall_universe", ""),
            "best_overall_channel": wine.get("best_overall_channel", ""),
            "best_overall_score": wine.get("best_overall_score", ""),
            "top1_render_human": wine.get("top1_render_human", ""),
            "top1_import_human": wine.get("top1_import_human", ""),
            "top3_render_summary": top3_render_str,
            "top3_import_summary": top3_import_str,
        }
        dossier_rows.append(dossier)

        # R1 classification
        r1 = classify_wine(wine, top3)
        murilo_reason = build_murilo_review_reason(r1)

        r1_row = {
            "render_wine_id": wid,
            "pilot_bucket_proxy": wine["pilot_bucket_proxy"],
            "business_class": r1["business_class"],
            "review_state": r1["review_state"],
            "confidence": r1["confidence"],
            "action": r1["action"],
            "data_quality": r1["data_quality"],
            "product_impact": r1["product_impact"],
            "recommended_universe": r1["recommended_universe"],
            "recommended_candidate_id": r1["recommended_candidate_id"],
            "reason_short": r1["reason_short"],
            "reason_long": r1["reason_long"],
            "match_blockers": r1["match_blockers"],
            "needs_murilo_review": 1,
            "murilo_review_reason": murilo_reason,
        }
        r1_rows.append(r1_row)

        # Murilo pack row (pilot info + R1 classification + empty murilo fields)
        murilo_row = {
            **dossier,
            "r1_business_class": r1["business_class"],
            "r1_review_state": r1["review_state"],
            "r1_confidence": r1["confidence"],
            "r1_action": r1["action"],
            "r1_data_quality": r1["data_quality"],
            "r1_product_impact": r1["product_impact"],
            "r1_recommended_universe": r1["recommended_universe"],
            "r1_recommended_candidate_id": r1["recommended_candidate_id"],
            "r1_reason_short": r1["reason_short"],
            "r1_reason_long": r1["reason_long"],
            "r1_match_blockers": r1["match_blockers"],
            "murilo_review_reason": murilo_reason,
            "murilo_business_class": "",   # preencher na revisao
            "murilo_review_state": "",
            "murilo_confidence": "",
            "murilo_action": "",
            "murilo_notes": "",
        }
        murilo_rows.append(murilo_row)

    # ---------- write DOSSIER ----------
    dossier_fields = list(dossier_rows[0].keys())
    with open(OUT_DOSSIER, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=dossier_fields)
        w.writeheader()
        w.writerows(dossier_rows)
    print(f"[write] {OUT_DOSSIER}")

    # ---------- write R1 ----------
    r1_fields = list(r1_rows[0].keys())
    with open(OUT_R1, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=r1_fields)
        w.writeheader()
        w.writerows(r1_rows)
    print(f"[write] {OUT_R1}")

    # ---------- write MURILO pack ----------
    murilo_fields = list(murilo_rows[0].keys())
    with open(OUT_MURILO, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=murilo_fields)
        w.writeheader()
        w.writerows(murilo_rows)
    print(f"[write] {OUT_MURILO}")

    # ---------- Resumo stdout ----------
    from collections import Counter
    print()
    print("=== DISTRIBUICOES R1 CLAUDE ===")
    for field in ("business_class", "review_state", "confidence", "action", "data_quality", "product_impact"):
        c = Counter(r[field] for r in r1_rows)
        print(f"  {field}:")
        for k, v in sorted(c.items(), key=lambda x: -x[1]):
            print(f"    {k:20s} = {v:>4}")

    print()
    print("=== bucket x business_class ===")
    cross = defaultdict(lambda: Counter())
    for r in r1_rows:
        cross[r["pilot_bucket_proxy"]][r["business_class"]] += 1
    for b in sorted(cross.keys()):
        print(f"  {b}:")
        for k, v in sorted(cross[b].items(), key=lambda x: -x[1]):
            print(f"    {k:20s} = {v:>4}")


if __name__ == "__main__":
    main()
