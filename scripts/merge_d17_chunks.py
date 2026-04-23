"""
Merge D17 per-chunk CSVs into the canonical reports/tail_d17_alias_candidates_2026-04-16.csv.gz.

Also rebuilds the QA pack deterministically from the merged rowset and writes a fresh summary.
Read-only in spirit: does not touch Render, only aggregates local artifacts.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
DATE = "2026-04-16"
OUT_CANDIDATES = REPORTS / f"tail_d17_alias_candidates_{DATE}.csv.gz"
OUT_QA = REPORTS / f"tail_d17_alias_qa_pack_{DATE}.csv"
OUT_SUMMARY = REPORTS / f"tail_d17_alias_candidates_summary_{DATE}.md"
SEED = "winegod_d17_alias_qa_2026-04-16"

FIELDS = [
    "source_wine_id", "canonical_wine_id", "lane", "confidence", "review_state",
    "recommended_action", "score", "gap", "source_stratum", "source_nome",
    "source_produtor", "source_safra", "source_tipo", "canonical_nome",
    "canonical_produtor", "canonical_safra", "canonical_tipo", "channels",
    "evidence_reason", "source_wine_sources_count", "source_stores_count",
    "y2_status_set", "y2_match_score_max", "y2_any_not_wine_or_spirit",
    "qa_required", "qa_sample_rate",
]


def fmt(n):
    return f"{int(n):,}".replace(",", ".")


def det_hash(*parts):
    return hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()


def main():
    chunk_files = sorted(REPORTS.glob(f"tail_d17_alias_candidates_{DATE}_chunk_*.csv.gz"))
    print(f"[1] Found {len(chunk_files)} chunk files")
    rows = []
    per_chunk = []
    seen_sources = set()
    duplicates = 0
    for path in chunk_files:
        count = 0
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                sid = row["source_wine_id"]
                if sid in seen_sources:
                    duplicates += 1
                    continue
                seen_sources.add(sid)
                rows.append(row)
                count += 1
        per_chunk.append((path.name, count))
        print(f"    {path.name}: {count:,}")
    print(f"    duplicates_dropped={duplicates:,}")
    print(f"    total_unique={len(rows):,}")

    rows.sort(key=lambda row: (row["lane"], row["source_stratum"], int(row["source_wine_id"])))

    print(f"[2] Write merged CSV -> {OUT_CANDIDATES}")
    with gzip.open(OUT_CANDIDATES, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print("[3] Rebuild QA pack")
    by_lane = defaultdict(list)
    for row in rows:
        by_lane[row["lane"]].append(row)
    sampled = []
    for lane, lane_rows in sorted(by_lane.items()):
        rate = 0.05 if lane == "ALIAS_AUTO" else 0.10
        needed = math.ceil(len(lane_rows) * rate)
        ordered = sorted(
            lane_rows,
            key=lambda row: det_hash(SEED, row["source_wine_id"], row["canonical_wine_id"], row["lane"]),
        )
        for row in ordered[:needed]:
            qa_row = dict(row)
            qa_row["qa_sample_rate"] = f"{rate:.2f}"
            qa_row["qa_verdict"] = ""
            qa_row["qa_notes"] = ""
            qa_row["reviewer"] = ""
            sampled.append(qa_row)
    sampled.sort(key=lambda row: (row["lane"], row["source_stratum"], int(row["source_wine_id"])))

    qa_fields = FIELDS + ["qa_verdict", "qa_notes", "reviewer"]
    with open(OUT_QA, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=qa_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sampled)

    print("[4] Write summary")
    by_lane_count = Counter(row["lane"] for row in rows)
    by_stratum = Counter(row["source_stratum"] for row in rows)
    by_evidence = Counter(row["evidence_reason"] for row in rows)
    qa_by_lane = Counter(row["lane"] for row in sampled)

    lines = [
        f"# D17 Alias Candidates -- Merged from chunks ({DATE})",
        "",
        f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Modo: merge deterministico de chunks read-only (sem INSERT em wine_aliases)",
        "",
        "## Resultado curto",
        "",
        f"- Candidatos D17 validados (mergeados): `{fmt(len(rows))}`",
        f"- `ALIAS_AUTO`: `{fmt(by_lane_count.get('ALIAS_AUTO', 0))}`",
        f"- `ALIAS_QA`: `{fmt(by_lane_count.get('ALIAS_QA', 0))}`",
        f"- QA pack: `{fmt(len(sampled))}`",
        f"- Chunks agregados: `{len(chunk_files)}`",
        f"- Duplicatas dropadas no merge: `{fmt(duplicates)}`",
        "",
        "## Artefatos",
        "",
        f"- Full rowset: `{OUT_CANDIDATES}`",
        f"- QA CSV: `{OUT_QA}`",
        "",
        "## Contagem por chunk",
        "",
        "| chunk | rows |",
        "| --- | --- |",
    ]
    for name, count in per_chunk:
        lines.append(f"| {name} | {fmt(count)} |")

    lines += ["", "## Contagem por lane", "", "| lane | candidatos | qa_sample |", "| --- | --- | --- |"]
    for lane in sorted(by_lane_count):
        lines.append(f"| {lane} | {fmt(by_lane_count[lane])} | {fmt(qa_by_lane.get(lane, 0))} |")
    lines += ["", "## Contagem por estrato", "", "| estrato | candidatos |", "| --- | --- |"]
    for name, count in by_stratum.most_common():
        lines.append(f"| {name} | {fmt(count)} |")
    lines += ["", "## Evidencia principal", "", "| evidencia | candidatos |", "| --- | --- |"]
    for name, count in by_evidence.most_common(20):
        lines.append(f"| {name} | {fmt(count)} |")

    OUT_SUMMARY.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"OK merged: {OUT_CANDIDATES}")
    print(f"OK qa_pack: {OUT_QA}")
    print(f"OK summary: {OUT_SUMMARY}")


if __name__ == "__main__":
    main()
