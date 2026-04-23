"""
Freeze D17 approved aliases from full rowset after human QA.

Inputs:
  reports/tail_d17_alias_candidates_2026-04-16.csv.gz   (full rowset)
  reports/tail_d17_alias_qa_pack_2026-04-16.csv        (QA with qa_verdict filled)

Outputs:
  reports/tail_d17_alias_approved_2026-04-16.csv.gz
  reports/tail_d17_alias_freeze_summary_2026-04-16.md

Policy:
  - ALIAS_AUTO rows with no ERROR verdict in QA sample pass through.
  - ALIAS_QA rows require explicit CORRECT verdict to pass.
  - Any sampled row with ERROR is excluded (its neighbors by (source_wine_id) only).
  - Un-reviewed ALIAS_QA rows are excluded.
"""
from __future__ import annotations

import csv
import gzip
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
DATE = "2026-04-16"
IN_CSV = REPORTS / f"tail_d17_alias_candidates_{DATE}.csv.gz"
QA_CSV = REPORTS / f"tail_d17_alias_qa_pack_{DATE}.csv"
OUT_CSV = REPORTS / f"tail_d17_alias_approved_{DATE}.csv.gz"
OUT_MD = REPORTS / f"tail_d17_alias_freeze_summary_{DATE}.md"

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


def main():
    if not IN_CSV.exists() or not QA_CSV.exists():
        raise SystemExit(f"Esperado {IN_CSV} e {QA_CSV}. Rode materializer e QA antes.")

    qa_verdict = {}
    with open(QA_CSV, "r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (row["source_wine_id"], row["canonical_wine_id"])
            qa_verdict[key] = row.get("qa_verdict") or ""

    approved = []
    reasons = Counter()
    counts_in = Counter()
    counts_out = Counter()
    with gzip.open(IN_CSV, "rt", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            counts_in[row["lane"]] += 1
            key = (row["source_wine_id"], row["canonical_wine_id"])
            verdict = qa_verdict.get(key)
            if verdict == "ERROR":
                reasons["qa_error"] += 1
                continue
            if row["lane"] == "ALIAS_QA":
                if verdict != "CORRECT":
                    reasons["alias_qa_unreviewed_or_not_correct"] += 1
                    continue
            elif row["lane"] == "ALIAS_AUTO":
                pass
            else:
                reasons[f"unexpected_lane_{row['lane']}"] += 1
                continue
            approved.append(row)
            counts_out[row["lane"]] += 1

    with gzip.open(OUT_CSV, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(approved)

    lines = [
        f"# D17 Freeze Summary -- {DATE}",
        "",
        f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Input rowset: `{IN_CSV}`",
        f"Input QA: `{QA_CSV}`",
        f"Output approved: `{OUT_CSV}`",
        "",
        "## Resultado",
        "",
        f"- Rows in (full rowset): `{fmt(sum(counts_in.values()))}`",
        f"- Rows approved (for D18): `{fmt(len(approved))}`",
        "",
        "## Por lane",
        "",
        "| lane | in | out |",
        "| --- | --- | --- |",
    ]
    for lane in sorted(set(list(counts_in) + list(counts_out))):
        lines.append(f"| {lane} | {fmt(counts_in.get(lane, 0))} | {fmt(counts_out.get(lane, 0))} |")
    lines += ["", "## Exclusoes", "", "| motivo | ocorrencias |", "| --- | --- |"]
    for name, count in reasons.most_common():
        lines.append(f"| {name} | {fmt(count)} |")

    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"OK approved: {OUT_CSV}")
    print(f"OK summary:  {OUT_MD}")


if __name__ == "__main__":
    main()
