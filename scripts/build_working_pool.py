"""
Demanda 7 -- Montar working pool deterministico de 1.200 wines da cauda.

READ-ONLY. Nao toca em Postgres. Le os artefatos existentes:
  - reports/tail_base_extract_2026-04-10.csv.gz          (nome/produtor/preco/no_source_flag)
  - reports/tail_y2_lineage_enriched_2026-04-10.csv.gz    (y2_any_not_wine_or_spirit)
  - reports/tail_candidate_controls_positive_2026-04-10.csv
  - reports/tail_candidate_controls_negative_2026-04-10.csv

Saida:
  - reports/tail_working_pool_1200_2026-04-10.csv

Estrategia determinstica:
  - Chave de ordenacao pseudo-aleatoria = sha1(f"{seed}:{render_wine_id}").hexdigest()
  - seed fixa = "winegod-demanda-7-working-pool-2026-04-10"
  - ordem crescente dessa chave dentro de cada bloco

Blocos:
  Bloco 1 -- Main random:           800  wines (universo = cauda - controles)
  Bloco 2 -- no_source supplemental: 200  wines (no_source_flag=1, excluir bloco 1)
  Bloco 3 -- suspect_not_wine suppl: 200  wines (wine_filter!=wine OR y2_nw=1, excluir b1+b2)

  Total: 1200. Zero overlap.

Uso:
  python scripts/build_working_pool.py
"""

import csv
import gzip
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wine_filter import classify_product  # noqa: E402


REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports")

TAIL_BASE = os.path.join(REPORT_DIR, "tail_base_extract_2026-04-10.csv.gz")
TAIL_Y2 = os.path.join(REPORT_DIR, "tail_y2_lineage_enriched_2026-04-10.csv.gz")
CONTROLS_POS = os.path.join(REPORT_DIR, "tail_candidate_controls_positive_2026-04-10.csv")
CONTROLS_NEG = os.path.join(REPORT_DIR, "tail_candidate_controls_negative_2026-04-10.csv")
OUT_CSV = os.path.join(REPORT_DIR, "tail_working_pool_1200_2026-04-10.csv")

SEED = "winegod-demanda-7-working-pool-2026-04-10"

BLOCK1_SIZE = 800
BLOCK2_SIZE = 200
BLOCK3_SIZE = 200
POOL_SIZE = BLOCK1_SIZE + BLOCK2_SIZE + BLOCK3_SIZE


def hash_key(render_wine_id):
    return hashlib.sha1(f"{SEED}:{render_wine_id}".encode()).hexdigest()


def load_controls():
    ids = set()
    for path in (CONTROLS_POS, CONTROLS_NEG):
        with open(path, "r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if row.get("render_wine_id"):
                    ids.add(int(row["render_wine_id"]))
    return ids


def load_tail_base():
    rows = {}
    with gzip.open(TAIL_BASE, "rt", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            wid = int(r["render_wine_id"])
            rows[wid] = r
    return rows


def load_y2():
    rows = {}
    with gzip.open(TAIL_Y2, "rt", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            wid = int(r["render_wine_id"])
            rows[wid] = r
    return rows


def is_suspect_not_wine(base_row, y2_row):
    """True se wine_filter bloqueia nome OU y2_any_not_wine_or_spirit=1."""
    nome = base_row.get("nome") or ""
    cls, _ = classify_product(nome)
    if cls == "not_wine":
        return True
    if y2_row and y2_row.get("y2_any_not_wine_or_spirit") == "1":
        return True
    return False


def main():
    print("[ctrl] carregando 40 controles D5...")
    controls = load_controls()
    print(f"    {len(controls)} controles para excluir")

    print("[base] carregando tail_base_extract...")
    base = load_tail_base()
    print(f"    {len(base):,} wines na tail_base")

    print("[y2] carregando tail_y2_lineage_enriched...")
    y2 = load_y2()
    print(f"    {len(y2):,} wines com linhagem y2")

    # Universo base = cauda menos controles
    all_ids = sorted(base.keys())
    universe = [w for w in all_ids if w not in controls]
    print(f"[univ] universo apos excluir controles: {len(universe):,}")

    # Ordem pseudo-aleatoria deterministica
    keyed = sorted(universe, key=hash_key)

    # ---------- BLOCO 1 ----------
    print(f"[block1] sorteando {BLOCK1_SIZE} wines random deterministicos...")
    block1 = keyed[:BLOCK1_SIZE]
    block1_set = set(block1)
    print(f"    {len(block1)} wines")

    # ---------- BLOCO 2 ----------
    print(f"[block2] sorteando {BLOCK2_SIZE} wines com no_source_flag=1...")
    no_src_pool = [
        w for w in keyed
        if w not in block1_set and base[w].get("no_source_flag") == "1"
    ]
    print(f"    candidatos no_source_flag=1 (fora do bloco 1): {len(no_src_pool):,}")
    block2 = no_src_pool[:BLOCK2_SIZE]
    block2_set = set(block2)
    if len(block2) < BLOCK2_SIZE:
        print(f"    AVISO: so {len(block2)} disponiveis (esperado {BLOCK2_SIZE})")

    # ---------- BLOCO 3 ----------
    print(f"[block3] sorteando {BLOCK3_SIZE} wines suspect_not_wine...")
    excluded = block1_set | block2_set
    suspect_pool = [
        w for w in keyed
        if w not in excluded and is_suspect_not_wine(base[w], y2.get(w))
    ]
    print(f"    candidatos suspect_not_wine (fora dos blocos 1+2): {len(suspect_pool):,}")
    block3 = suspect_pool[:BLOCK3_SIZE]
    if len(block3) < BLOCK3_SIZE:
        print(f"    AVISO: so {len(block3)} disponiveis (esperado {BLOCK3_SIZE})")

    # ---------- Sanity ----------
    all_pool = block1 + block2 + block3
    all_set = set(all_pool)
    assert len(all_set) == len(all_pool), "OVERLAP ENTRE BLOCOS"
    assert len(all_set & controls) == 0, "CONTROLES NO POOL"
    print(f"[check] {len(all_pool)} wines total, 0 overlap, 0 controles")

    # ---------- Escrever CSV ----------
    print(f"[write] {OUT_CSV}")
    fields = [
        "render_wine_id", "block", "hash_key",
        "nome", "produtor", "safra", "tipo",
        "preco_min", "moeda",
        "wine_sources_count_live", "stores_count_live",
        "has_sources", "no_source_flag",
        "y2_present", "y2_status_set", "y2_any_not_wine_or_spirit",
        "wine_filter_category",
    ]

    def row_of(wid, block_name):
        b = base[wid]
        y = y2.get(wid, {})
        cls, cat = classify_product(b.get("nome") or "")
        return {
            "render_wine_id": wid,
            "block": block_name,
            "hash_key": hash_key(wid),
            "nome": b.get("nome", ""),
            "produtor": b.get("produtor", ""),
            "safra": b.get("safra", ""),
            "tipo": b.get("tipo", ""),
            "preco_min": b.get("preco_min", ""),
            "moeda": b.get("moeda", ""),
            "wine_sources_count_live": b.get("wine_sources_count_live", ""),
            "stores_count_live": b.get("stores_count_live", ""),
            "has_sources": b.get("has_sources", ""),
            "no_source_flag": b.get("no_source_flag", ""),
            "y2_present": y.get("y2_present", ""),
            "y2_status_set": y.get("y2_status_set", ""),
            "y2_any_not_wine_or_spirit": y.get("y2_any_not_wine_or_spirit", ""),
            "wine_filter_category": cat if cls == "not_wine" else "",
        }

    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for wid in block1:
            w.writerow(row_of(wid, "block1_main_random"))
        for wid in block2:
            w.writerow(row_of(wid, "block2_no_source"))
        for wid in block3:
            w.writerow(row_of(wid, "block3_suspect_not_wine"))

    print(f"    bloco1 main_random:       {len(block1):>4}")
    print(f"    bloco2 no_source:         {len(block2):>4}")
    print(f"    bloco3 suspect_not_wine:  {len(block3):>4}")
    print(f"    TOTAL:                    {len(all_pool):>4}")


if __name__ == "__main__":
    main()
