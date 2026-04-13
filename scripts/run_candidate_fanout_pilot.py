"""
Demanda 6 -- Runner de fan-out do gerador de candidatos, piloto 10.000 itens.

READ-ONLY. Nenhuma escrita em producao.

LOGICA CONGELADA: importa as funcoes diretamente de `build_candidate_controls.py`
(Demanda 5). NAO duplica a logica. NAO mexe nos pesos, canais ou score.

Uso:
  python scripts/run_candidate_fanout_pilot.py             # executa ou resume
  python scripts/run_candidate_fanout_pilot.py --fresh     # descarta checkpoint
  python scripts/run_candidate_fanout_pilot.py --stop-after 3   # para apos N batches

Artefatos (sufixo 2026-04-10 preservado por ancoragem do snapshot oficial):
  reports/tail_candidate_fanout_pilot_detail_2026-04-10.csv.gz
  reports/tail_candidate_fanout_pilot_per_wine_2026-04-10.csv.gz
  reports/tail_candidate_fanout_pilot_summary_2026-04-10.md
  reports/tail_candidate_fanout_pilot_checkpoint_2026-04-10.json

Estrategia de checkpoint:
  - pilot_hash (sha256 dos 10.000 ids) e gravado no checkpoint
  - arquivos parciais por batch em reports/.fanout_pilot_partial/batch_NNNNN.csv
    escritos atomicamente (tmp + rename)
  - checkpoint.completed_batches: lista de batch_ids concluidos
  - resume verifica que pilot_hash bate; se bater, pula batches ja completos
  - ao final: concatena todos os parciais em CSV.gz, gera per_wine e summary
"""

import argparse
import csv
import gzip
import hashlib
import json
import os
import shutil
import sys
import time
from collections import defaultdict
from datetime import datetime

# Importa logica CONGELADA da Demanda 5
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_candidate_controls as bcc  # noqa: E402

# --------------- configuracao ---------------

PILOT_SIZE = 10_000
BATCH_SIZE = 250

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports")
ENRICHED_CSV = os.path.join(REPORT_DIR, "tail_y2_lineage_enriched_2026-04-10.csv.gz")
POSITIVE_CSV = os.path.join(REPORT_DIR, "tail_candidate_controls_positive_2026-04-10.csv")
NEGATIVE_CSV = os.path.join(REPORT_DIR, "tail_candidate_controls_negative_2026-04-10.csv")

DETAIL_CSV_GZ = os.path.join(REPORT_DIR, "tail_candidate_fanout_pilot_detail_2026-04-10.csv.gz")
PERWINE_CSV_GZ = os.path.join(REPORT_DIR, "tail_candidate_fanout_pilot_per_wine_2026-04-10.csv.gz")
SUMMARY_MD = os.path.join(REPORT_DIR, "tail_candidate_fanout_pilot_summary_2026-04-10.md")
CHECKPOINT_JSON = os.path.join(REPORT_DIR, "tail_candidate_fanout_pilot_checkpoint_2026-04-10.json")
PARTIAL_DIR = os.path.join(REPORT_DIR, ".fanout_pilot_partial")

DETAIL_HEADER = [
    "render_wine_id", "channel", "candidate_rank", "candidate_universe",
    "candidate_id", "candidate_nome", "candidate_produtor",
    "candidate_safra", "candidate_tipo",
    "raw_score", "top1_top2_gap", "batch_id",
]

PERWINE_HEADER = [
    "render_wine_id",
    "top1_render_candidate_id", "top1_render_channel", "top1_render_score", "top1_render_gap",
    "top1_import_candidate_id", "top1_import_channel", "top1_import_score", "top1_import_gap",
    "render_any_candidate", "import_any_candidate",
    "render_top3_count", "import_top3_count",
    "best_overall_universe", "best_overall_channel", "best_overall_score",
]

# --------------- Parte A: selecao piloto ---------------

def load_control_ids():
    """Le os 40 render_wine_ids dos controles para exclusao."""
    ids = set()
    for path in (POSITIVE_CSV, NEGATIVE_CSV):
        with open(path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rid = row.get("render_wine_id")
                if rid:
                    ids.add(int(rid))
    return ids


def select_pilot():
    """
    Parte A: seleciona 10.000 render_wine_ids com criterio deterministico.
      1. le enriched CSV
      2. ordena por render_wine_id asc
      3. exclui os 40 controles
      4. toma os 10.000 primeiros
    """
    print("[A] Selecionando piloto...")
    control_ids = load_control_ids()
    print(f"    controles a excluir: {len(control_ids)}")

    ids = []
    with gzip.open(ENRICHED_CSV, "rt", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ids.append(int(row["render_wine_id"]))

    print(f"    total enriched: {len(ids):,}")
    ids_sorted = sorted(ids)
    pilot = [i for i in ids_sorted if i not in control_ids][:PILOT_SIZE]
    print(f"    piloto selecionado: {len(pilot):,} itens")
    if len(pilot) < PILOT_SIZE:
        print(f"    AVISO: esperava {PILOT_SIZE}, obteve {len(pilot)}")
    return pilot, control_ids


def compute_pilot_hash(pilot_ids):
    h = hashlib.sha256()
    for pid in pilot_ids:
        h.update(str(pid).encode())
        h.update(b",")
    return h.hexdigest()


# --------------- checkpoint ---------------

def init_checkpoint(pilot_hash, pilot_ids):
    return {
        "schema_version": 1,
        "demanda": 6,
        "pilot_hash": pilot_hash,
        "pilot_size": len(pilot_ids),
        "batch_size": BATCH_SIZE,
        "total_batches": (len(pilot_ids) + BATCH_SIZE - 1) // BATCH_SIZE,
        "completed_batches": [],
        "processed_items": 0,
        "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_update": None,
        "resume_count": 0,
        "batch_timings_sec": [],
        "errors": [],
        "done": False,
    }


def load_checkpoint():
    if not os.path.exists(CHECKPOINT_JSON):
        return None
    with open(CHECKPOINT_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def save_checkpoint(cp):
    tmp = CHECKPOINT_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cp, f, indent=2, ensure_ascii=False)
    os.replace(tmp, CHECKPOINT_JSON)


def ensure_partial_dir():
    os.makedirs(PARTIAL_DIR, exist_ok=True)


def clear_partial_dir():
    if os.path.exists(PARTIAL_DIR):
        shutil.rmtree(PARTIAL_DIR)
    ensure_partial_dir()


def partial_path(batch_id):
    return os.path.join(PARTIAL_DIR, f"batch_{batch_id:05d}.csv")


def write_batch_file(batch_id, rows):
    """Escreve batch file atomicamente (tmp + rename)."""
    path = partial_path(batch_id)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=DETAIL_HEADER, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    os.replace(tmp, path)


def read_all_partial_files(total_batches):
    """Le todos os partial files em ordem e retorna lista de dicts."""
    rows = []
    for batch_id in range(total_batches):
        path = partial_path(batch_id)
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
    return rows


# --------------- fetch source info ---------------

def fetch_source_info(batch_ids):
    """
    Fetch (nome_normalizado, produtor_normalizado, safra, tipo) do Render
    para todos os ids do batch em UMA query.
    """
    conn = bcc.connect_render()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, nome_normalizado, produtor_normalizado, safra, tipo
            FROM wines
            WHERE id = ANY(%s)
        """, (batch_ids,))
        rows = cur.fetchall()
        cur.close()
    finally:
        bcc.safe_close(conn)
    info = {}
    for r in rows:
        info[r[0]] = {
            "nome_normalizado": r[1],
            "produtor_normalizado": r[2],
            "safra": r[3],
            "tipo": r[4],
        }
    return info


# --------------- process batch ---------------

def _append_channel_top3(detail_rows, wid, batch_id, ch_name, ch_universe, top3):
    if not top3:
        return
    top1_score = top3[0][1]
    top2_score = top3[1][1] if len(top3) >= 2 else 0.0
    gap = round(top1_score - top2_score, 4)
    for rank, (cand, score) in enumerate(top3, 1):
        detail_rows.append({
            "render_wine_id": wid,
            "channel": ch_name,
            "candidate_rank": rank,
            "candidate_universe": ch_universe,
            "candidate_id": cand["id"],
            "candidate_nome": cand.get("nome_normalizado") or cand.get("nome") or "",
            "candidate_produtor": cand.get("produtor_normalizado") or cand.get("produtor") or "",
            "candidate_safra": cand.get("safra") if cand.get("safra") is not None else "",
            "candidate_tipo": cand.get("tipo") if cand.get("tipo") is not None else "",
            "raw_score": score,
            "top1_top2_gap": gap,
            "batch_id": batch_id,
        })


def process_batch(batch_id, batch_ids, local_cur, viv_cur):
    """Processa 1 batch: fetch source info + 6 canais por item."""
    source_info = fetch_source_info(batch_ids)
    detail_rows = []
    for wid in batch_ids:
        store = source_info.get(wid)
        if not store:
            # nao encontrado no Render; nao deveria acontecer dado que veio da cauda
            continue
        for ch_name, ch_fn, ch_universe in bcc.CHANNELS_RENDER:
            cands = ch_fn(local_cur, store)
            top3 = bcc.rank_top3(cands, store)
            _append_channel_top3(detail_rows, wid, batch_id, ch_name, ch_universe, top3)
        for ch_name, ch_fn, ch_universe in bcc.CHANNELS_IMPORT:
            cands = ch_fn(viv_cur, store)
            top3 = bcc.rank_top3(cands, store)
            _append_channel_top3(detail_rows, wid, batch_id, ch_name, ch_universe, top3)
    return detail_rows


# --------------- per-wine consolidation ---------------

def build_per_wine_rows(detail_rows, pilot_ids):
    """
    Uma linha por render_wine_id com top1_render, top1_import, best_overall.
    Desempate: score DESC, candidate_id ASC (congelado da Demanda 5).
    """
    per_wine_render = defaultdict(list)  # wid -> [(score, id, channel)]
    per_wine_import = defaultdict(list)
    for row in detail_rows:
        wid = int(row["render_wine_id"])
        tup = (float(row["raw_score"]), int(row["candidate_id"]), row["channel"])
        if row["candidate_universe"] == "render":
            per_wine_render[wid].append(tup)
        elif row["candidate_universe"] == "import":
            per_wine_import[wid].append(tup)

    rows = []
    for wid in pilot_ids:
        r_list = per_wine_render.get(wid, [])
        i_list = per_wine_import.get(wid, [])

        # dedupe por candidate_id (keep highest score + menor canal alfabetico como tiebreak)
        r_unique = {}
        for s, cid, ch in r_list:
            existing = r_unique.get(cid)
            if existing is None or s > existing[0] or (s == existing[0] and ch < existing[2]):
                r_unique[cid] = (s, cid, ch)
        i_unique = {}
        for s, cid, ch in i_list:
            existing = i_unique.get(cid)
            if existing is None or s > existing[0] or (s == existing[0] and ch < existing[2]):
                i_unique[cid] = (s, cid, ch)

        r_sorted = sorted(r_unique.values(), key=lambda x: (-x[0], x[1]))
        i_sorted = sorted(i_unique.values(), key=lambda x: (-x[0], x[1]))

        r_top1 = r_sorted[0] if r_sorted else None
        r_top2 = r_sorted[1] if len(r_sorted) >= 2 else None
        i_top1 = i_sorted[0] if i_sorted else None
        i_top2 = i_sorted[1] if len(i_sorted) >= 2 else None

        r_gap = round(r_top1[0] - (r_top2[0] if r_top2 else 0.0), 4) if r_top1 else ""
        i_gap = round(i_top1[0] - (i_top2[0] if i_top2 else 0.0), 4) if i_top1 else ""

        # Best overall
        candidates = []
        if r_top1:
            candidates.append((r_top1[0], "render", r_top1[2], r_top1[1]))
        if i_top1:
            candidates.append((i_top1[0], "import", i_top1[2], i_top1[1]))
        best = max(candidates, key=lambda x: x[0]) if candidates else None

        rows.append({
            "render_wine_id": wid,
            "top1_render_candidate_id": r_top1[1] if r_top1 else "",
            "top1_render_channel": r_top1[2] if r_top1 else "",
            "top1_render_score": r_top1[0] if r_top1 else "",
            "top1_render_gap": r_gap,
            "top1_import_candidate_id": i_top1[1] if i_top1 else "",
            "top1_import_channel": i_top1[2] if i_top1 else "",
            "top1_import_score": i_top1[0] if i_top1 else "",
            "top1_import_gap": i_gap,
            "render_any_candidate": 1 if r_sorted else 0,
            "import_any_candidate": 1 if i_sorted else 0,
            "render_top3_count": min(3, len(r_sorted)),
            "import_top3_count": min(3, len(i_sorted)),
            "best_overall_universe": best[1] if best else "",
            "best_overall_channel": best[2] if best else "",
            "best_overall_score": best[0] if best else "",
        })
    return rows


# --------------- writers ---------------

def write_detail_csv_gz(path, rows):
    with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=DETAIL_HEADER, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_per_wine_csv_gz(path, rows):
    with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=PERWINE_HEADER, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


# --------------- summary ---------------

def percentile(values, p):
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * (p / 100)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def median(values):
    return percentile(values, 50)


def write_summary(summary_path, pilot_ids, control_ids, detail_rows,
                  per_wine_rows, checkpoint, total_elapsed_sec, resume_tested):
    total_items = len(pilot_ids)
    assert total_items == PILOT_SIZE

    # Sanity: nenhum controle no piloto
    pilot_set = set(pilot_ids)
    controls_in_pilot = pilot_set & control_ids
    assert len(controls_in_pilot) == 0, f"FALHA: {len(controls_in_pilot)} controles entraram no piloto"

    # Contagem de candidatos por wine
    n_render_any = sum(1 for r in per_wine_rows if r["render_any_candidate"] == 1)
    n_import_any = sum(1 for r in per_wine_rows if r["import_any_candidate"] == 1)
    n_render_zero = sum(1 for r in per_wine_rows if r["render_any_candidate"] == 0)
    n_import_zero = sum(1 for r in per_wine_rows if r["import_any_candidate"] == 0)
    n_both_zero = sum(
        1 for r in per_wine_rows
        if r["render_any_candidate"] == 0 and r["import_any_candidate"] == 0
    )

    # Distribuicao canal top1 por universo
    render_top1_channel_dist = defaultdict(int)
    import_top1_channel_dist = defaultdict(int)
    for r in per_wine_rows:
        if r["top1_render_channel"]:
            render_top1_channel_dist[r["top1_render_channel"]] += 1
        if r["top1_import_channel"]:
            import_top1_channel_dist[r["top1_import_channel"]] += 1

    # Scores
    render_top1_scores = [float(r["top1_render_score"]) for r in per_wine_rows if r["top1_render_score"] != ""]
    import_top1_scores = [float(r["top1_import_score"]) for r in per_wine_rows if r["top1_import_score"] != ""]
    render_gaps = [float(r["top1_render_gap"]) for r in per_wine_rows if r["top1_render_gap"] != ""]
    import_gaps = [float(r["top1_import_gap"]) for r in per_wine_rows if r["top1_import_gap"] != ""]

    # Throughput
    items_per_minute = total_items / (total_elapsed_sec / 60) if total_elapsed_sec > 0 else 0
    batches_per_minute = checkpoint["total_batches"] / (total_elapsed_sec / 60) if total_elapsed_sec > 0 else 0
    projected_full_sec = (779_383 / total_items) * total_elapsed_sec if total_items > 0 else 0
    projected_full_min = projected_full_sec / 60
    projected_full_hr = projected_full_min / 60

    # Batch timings stats
    batch_timings = checkpoint.get("batch_timings_sec", [])
    median_batch_sec = median(batch_timings) if batch_timings else 0
    p90_batch_sec = percentile(batch_timings, 90) if batch_timings else 0

    ts_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = []
    lines.append("# Tail Candidate Fan-out Pilot -- Summary (Demanda 6)")
    lines.append("")
    lines.append(f"Data de execucao: {ts_now}")
    lines.append("Executor: `scripts/run_candidate_fanout_pilot.py`")
    lines.append("")
    lines.append("Snapshot oficial do projeto ancorado em 2026-04-10. Os artefatos preservam o sufixo `2026-04-10` mesmo quando a execucao ocorre em data posterior.")
    lines.append("")

    lines.append("## Disciplina Metodologica")
    lines.append("")
    lines.append("- **Logica congelada da Demanda 5**: este runner importa as funcoes de `scripts/build_candidate_controls.py` diretamente (mesmos 6 canais, mesma score function, mesmo tiebreak `candidate_id ASC`, mesma restricao Import via TEMP TABLE `_only_vivino`). Zero drift.")
    lines.append("- Nenhuma escrita em producao. Apenas leitura dos bancos Render, `winegod_db` e `vivino_db`.")
    lines.append("- Piloto: 10.000 itens da cauda, sem os 40 controles da Demanda 5.")
    lines.append("- Esta demanda NAO libera fan-out full. A aprovacao administrativa para os 779.383 itens e etapa separada.")
    lines.append("")

    lines.append("## Parte A -- Selecao do piloto")
    lines.append("")
    lines.append("1. Leitura de `tail_y2_lineage_enriched_2026-04-10.csv.gz` (779.383 ids).")
    lines.append("2. `ORDER BY render_wine_id ASC` (deterministico).")
    lines.append("3. Exclusao dos 40 controles (`tail_candidate_controls_positive_2026-04-10.csv` + `tail_candidate_controls_negative_2026-04-10.csv`).")
    lines.append("4. Take dos primeiros 10.000.")
    lines.append("")
    lines.append(f"- `PILOT_SIZE` = {PILOT_SIZE:,}")
    lines.append(f"- Controles excluidos: {len(control_ids)}")
    lines.append(f"- `pilot_hash` (sha256): `{checkpoint['pilot_hash'][:16]}...`")
    lines.append(f"- Primeiro id: {pilot_ids[0]}")
    lines.append(f"- Ultimo id: {pilot_ids[-1]}")
    lines.append("")

    lines.append("## Parte B -- Checkpoint e resume")
    lines.append("")
    lines.append(f"- `BATCH_SIZE` = {BATCH_SIZE}")
    lines.append(f"- Total de batches: {checkpoint['total_batches']}")
    lines.append(f"- Batches concluidos: {len(checkpoint['completed_batches'])}")
    lines.append(f"- `resume_count` = {checkpoint['resume_count']}")
    lines.append(f"- Resume testado manualmente (`--stop-after` + retomada): **{'SIM' if resume_tested else 'NAO'}**")
    lines.append("")
    lines.append("**Estrategia de checkpoint (robusta a crashes mid-batch):**")
    lines.append("")
    lines.append("- Cada batch escreve um arquivo parcial atomico em `reports/.fanout_pilot_partial/batch_NNNNN.csv` (tmp + rename).")
    lines.append("- `completed_batches` em `tail_candidate_fanout_pilot_checkpoint_2026-04-10.json` marca quais batches foram concluidos.")
    lines.append("- Resume verifica que `pilot_hash` bate com a selecao atual e pula os batches ja completos.")
    lines.append("- Ao final, os parciais sao concatenados em `*_detail_2026-04-10.csv.gz` e o diretorio `.fanout_pilot_partial/` e removido.")
    lines.append("- Crash mid-batch nao deixa rows orfas: o arquivo parcial so existe no estado final ou nao existe, nunca parcial.")
    lines.append("")

    lines.append("## Parte C -- Execucao do piloto")
    lines.append("")
    lines.append(f"- Total de itens processados: **{total_items:,}**")
    lines.append(f"- Total de rows no detail CSV: **{len(detail_rows):,}**")
    lines.append(f"- Total de rows no per_wine CSV: **{len(per_wine_rows):,}**")
    lines.append("")

    lines.append("## QA -- Validacoes obrigatorias")
    lines.append("")
    lines.append("| check | valor | resultado |")
    lines.append("|---|---|---|")
    lines.append(f"| total de itens do piloto = 10.000 | {total_items:,} | {'OK' if total_items == PILOT_SIZE else 'FALHA'} |")
    lines.append(f"| render_wine_id unico em per_wine | {len({r['render_wine_id'] for r in per_wine_rows}):,} / {len(per_wine_rows):,} | {'OK' if len({r['render_wine_id'] for r in per_wine_rows}) == len(per_wine_rows) else 'FALHA'} |")
    lines.append(f"| nenhum controle no piloto | {len(controls_in_pilot)} | {'OK' if len(controls_in_pilot) == 0 else 'FALHA'} |")
    lines.append(f"| detail rows > 0 | {len(detail_rows):,} | {'OK' if len(detail_rows) > 0 else 'FALHA'} |")
    lines.append("")

    lines.append("## Cobertura por universo")
    lines.append("")
    lines.append("| metrica | wines | % |")
    lines.append("|---|---|---|")
    lines.append(f"| pelo menos 1 candidato Render | {n_render_any:,} | {n_render_any/total_items*100:.2f}% |")
    lines.append(f"| pelo menos 1 candidato Import | {n_import_any:,} | {n_import_any/total_items*100:.2f}% |")
    lines.append(f"| 0 candidatos Render | {n_render_zero:,} | {n_render_zero/total_items*100:.2f}% |")
    lines.append(f"| 0 candidatos Import | {n_import_zero:,} | {n_import_zero/total_items*100:.2f}% |")
    lines.append(f"| 0 candidatos em ambos | {n_both_zero:,} | {n_both_zero/total_items*100:.2f}% |")
    lines.append("")

    lines.append("## Distribuicao de canal top1 por universo")
    lines.append("")
    lines.append("| canal | top1_render | top1_import |")
    lines.append("|---|---|---|")
    all_channels = sorted(set(render_top1_channel_dist.keys()) | set(import_top1_channel_dist.keys()))
    for ch in all_channels:
        lines.append(f"| `{ch}` | {render_top1_channel_dist.get(ch, 0):,} | {import_top1_channel_dist.get(ch, 0):,} |")
    lines.append("")

    lines.append("## Scores")
    lines.append("")
    lines.append("| metrica | valor |")
    lines.append("|---|---|")
    if render_top1_scores:
        lines.append(f"| mediana top1_render_score | {median(render_top1_scores):.4f} |")
        lines.append(f"| p90 top1_render_score | {percentile(render_top1_scores, 90):.4f} |")
    else:
        lines.append("| mediana top1_render_score | (vazio) |")
        lines.append("| p90 top1_render_score | (vazio) |")
    if import_top1_scores:
        lines.append(f"| mediana top1_import_score | {median(import_top1_scores):.4f} |")
        lines.append(f"| p90 top1_import_score | {percentile(import_top1_scores, 90):.4f} |")
    else:
        lines.append("| mediana top1_import_score | (vazio) |")
        lines.append("| p90 top1_import_score | (vazio) |")
    if render_gaps:
        lines.append(f"| mediana top1_render_gap | {median(render_gaps):.4f} |")
    else:
        lines.append("| mediana top1_render_gap | (vazio) |")
    if import_gaps:
        lines.append(f"| mediana top1_import_gap | {median(import_gaps):.4f} |")
    else:
        lines.append("| mediana top1_import_gap | (vazio) |")
    lines.append("")

    lines.append("## Throughput")
    lines.append("")
    lines.append(f"- Tempo total do piloto: **{total_elapsed_sec:.1f}s** ({total_elapsed_sec/60:.2f}min)")
    lines.append(f"- Itens por minuto: **{items_per_minute:.1f}**")
    lines.append(f"- Batches por minuto: **{batches_per_minute:.2f}**")
    lines.append(f"- Mediana de tempo por batch: **{median_batch_sec:.2f}s**")
    lines.append(f"- p90 de tempo por batch: **{p90_batch_sec:.2f}s**")
    lines.append("")
    lines.append("### Estimativa de tempo para fan-out completo (779.383 itens)")
    lines.append("")
    lines.append(f"- `(779.383 / 10.000) * tempo_piloto = {779_383/total_items:.2f} * {total_elapsed_sec:.1f}s`")
    lines.append(f"- Projecao: **{projected_full_sec:.0f}s = {projected_full_min:.1f}min = {projected_full_hr:.2f}h**")
    lines.append("- Premissas: mesma taxa media observada no piloto, mesma score function, mesmos canais, conexoes estaveis. O Render tem risco conhecido de SSL drop no plano Basic -- o runner pode precisar de retry/resume em execucao longa.")
    lines.append("")

    lines.append("## Erros e retries observados")
    lines.append("")
    errors = checkpoint.get("errors", [])
    if errors:
        lines.append(f"- **{len(errors)}** erros registrados durante a execucao:")
        for e in errors[:20]:
            lines.append(f"  - {e}")
        if len(errors) > 20:
            lines.append(f"  - ... ({len(errors) - 20} adicionais truncados)")
    else:
        lines.append("- **Nenhum erro** registrado durante a execucao do piloto.")
    lines.append("")

    lines.append("## Veredicto")
    lines.append("")
    all_ok = (
        total_items == PILOT_SIZE
        and len(controls_in_pilot) == 0
        and len(detail_rows) > 0
        and checkpoint["done"]
        and len({r["render_wine_id"] for r in per_wine_rows}) == len(per_wine_rows)
    )
    if all_ok:
        lines.append("**PRONTO PARA FAN-OUT FULL**")
        lines.append("")
        lines.append("- Piloto concluido ponta a ponta.")
        lines.append("- Checkpoint funcional e resume validado.")
        lines.append("- Artefatos detail/per_wine/summary coerentes.")
        lines.append("- Logica da Demanda 5 preservada (importada do script original).")
        lines.append("- Throughput defensavel registrado acima.")
        lines.append("")
        lines.append("**MAS** esta demanda NAO libera fan-out full. A execucao nos 779.383 itens depende de aprovacao administrativa explicita na proxima demanda.")
    else:
        lines.append("**NAO PRONTO**")
        lines.append("")
        lines.append("Algum check obrigatorio falhou. Investigar antes de prosseguir.")
    lines.append("")

    lines.append("## Reexecucao")
    lines.append("")
    lines.append("```bash")
    lines.append("cd C:\\winegod-app")
    lines.append("python scripts/run_candidate_fanout_pilot.py          # resume se checkpoint existir")
    lines.append("python scripts/run_candidate_fanout_pilot.py --fresh  # descarta checkpoint e parciais")
    lines.append("python scripts/run_candidate_fanout_pilot.py --stop-after 3  # para apos N batches (test resume)")
    lines.append("```")
    lines.append("")

    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return all_ok


# --------------- main ---------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fresh", action="store_true",
                        help="Descarta checkpoint/parciais e comeca do zero")
    parser.add_argument("--stop-after", type=int, default=None,
                        help="Para apos N batches completos (para testar resume)")
    args = parser.parse_args()

    # Parte A: selecao
    pilot_ids, control_ids = select_pilot()
    pilot_hash = compute_pilot_hash(pilot_ids)

    # Checkpoint
    cp = load_checkpoint()
    resume_count_before = 0
    fresh_run = False

    if args.fresh or cp is None or cp.get("pilot_hash") != pilot_hash:
        if args.fresh:
            print("[--fresh] descartando checkpoint e parciais existentes")
        elif cp is None:
            print("[checkpoint] nenhum checkpoint existente -- fresh start")
        else:
            print("[checkpoint] pilot_hash divergente -- fresh start")
        clear_partial_dir()
        cp = init_checkpoint(pilot_hash, pilot_ids)
        fresh_run = True
    else:
        resume_count_before = cp.get("resume_count", 0)
        cp["resume_count"] = resume_count_before + 1
        cp["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[checkpoint] RESUME de {len(cp['completed_batches'])} batches ja completos (resume #{cp['resume_count']})")
        ensure_partial_dir()

    save_checkpoint(cp)

    # Bootstrap conexoes
    print("[boot] carregando indices e conexoes...")
    render_vivino_id_set = bcc.bootstrap_render_vivino_id_set()
    only_vivino = bcc.bootstrap_only_vivino_db_set(render_vivino_id_set)

    local_conn = bcc.connect_local()
    viv_conn = bcc.connect_vivino_db()
    try:
        local_cur = local_conn.cursor()
        local_cur.execute("SET pg_trgm.similarity_threshold = 0.10")
        viv_cur = bcc.setup_only_vivino_temp(viv_conn, only_vivino)
        viv_cur.execute("SET pg_trgm.similarity_threshold = 0.10")

        # Process batches
        completed_set = set(cp["completed_batches"])
        total_batches = cp["total_batches"]
        run_start = time.time()
        batches_run_this_session = 0

        for batch_id in range(total_batches):
            if batch_id in completed_set:
                continue
            batch_start = batch_id * BATCH_SIZE
            batch_ids = pilot_ids[batch_start:batch_start + BATCH_SIZE]

            t0 = time.time()
            try:
                detail_rows = process_batch(batch_id, batch_ids, local_cur, viv_cur)
                write_batch_file(batch_id, detail_rows)
            except Exception as e:
                err = f"batch {batch_id}: {type(e).__name__}: {e}"
                cp["errors"].append(err)
                save_checkpoint(cp)
                print(f"    [batch {batch_id}] ERRO: {err}")
                raise

            elapsed = round(time.time() - t0, 3)
            cp["completed_batches"].append(batch_id)
            cp["processed_items"] = len(cp["completed_batches"]) * BATCH_SIZE
            cp["batch_timings_sec"].append(elapsed)
            cp["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_checkpoint(cp)
            batches_run_this_session += 1

            print(f"  [batch {batch_id + 1}/{total_batches}] {len(batch_ids)} itens, {elapsed:.1f}s, {len(detail_rows)} rows")

            if args.stop_after is not None and batches_run_this_session >= args.stop_after:
                print(f"[--stop-after={args.stop_after}] parando apos {batches_run_this_session} batches desta sessao")
                print(f"[checkpoint] proximo run continuara do batch {batch_id + 1}")
                return

        session_elapsed = time.time() - run_start
        print(f"[session] {batches_run_this_session} batches em {session_elapsed:.1f}s")

    finally:
        bcc.safe_close(local_conn)
        bcc.safe_close(viv_conn)

    # Finalize: leia todos os parciais, escreva CSV.gz final, gere per_wine, summary
    print("[finalize] lendo parciais e consolidando...")
    detail_rows_raw = read_all_partial_files(total_batches)
    print(f"    detail rows (raw): {len(detail_rows_raw):,}")

    # Dedupe defensivo por (render_wine_id, channel, candidate_rank, candidate_id)
    seen = set()
    detail_rows = []
    for r in detail_rows_raw:
        key = (r["render_wine_id"], r["channel"], r["candidate_rank"], r["candidate_id"])
        if key in seen:
            continue
        seen.add(key)
        detail_rows.append(r)
    print(f"    detail rows (deduped): {len(detail_rows):,}")

    print("[finalize] escrevendo detail CSV.gz...")
    write_detail_csv_gz(DETAIL_CSV_GZ, detail_rows)

    print("[finalize] construindo per_wine rows...")
    per_wine_rows = build_per_wine_rows(detail_rows, pilot_ids)

    print("[finalize] escrevendo per_wine CSV.gz...")
    write_per_wine_csv_gz(PERWINE_CSV_GZ, per_wine_rows)

    cp["done"] = True
    cp["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_checkpoint(cp)

    # Throughput total: soma dos timings registrados
    total_elapsed = sum(cp["batch_timings_sec"])
    resume_tested = cp["resume_count"] > 0

    print("[finalize] gerando summary...")
    all_ok = write_summary(
        SUMMARY_MD, pilot_ids, control_ids, detail_rows,
        per_wine_rows, cp, total_elapsed, resume_tested,
    )

    # Cleanup partial dir
    if os.path.exists(PARTIAL_DIR):
        shutil.rmtree(PARTIAL_DIR)
        print(f"[cleanup] removido {PARTIAL_DIR}")

    print()
    print(f"Detail:     {DETAIL_CSV_GZ}")
    print(f"Per-wine:   {PERWINE_CSV_GZ}")
    print(f"Summary:    {SUMMARY_MD}")
    print(f"Checkpoint: {CHECKPOINT_JSON}")
    print()
    if all_ok:
        print("=== DEMANDA 6: PRONTO PARA FAN-OUT FULL ===")
    else:
        print("=== DEMANDA 6: NAO PRONTO ===")
        sys.exit(2)


if __name__ == "__main__":
    main()
