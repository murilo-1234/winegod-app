"""
D17 rowset validator: read-only independent check against Render.

Checks invariants of reports/tail_d17_alias_candidates_2026-04-16.csv.gz:
  - source_wine_id active (vivino_id IS NULL, suppressed_at IS NULL)
  - canonical_wine_id active Vivino (vivino_id NOT NULL, suppressed_at IS NULL)
  - no overlap with approved wine_aliases.source_wine_id
  - every row has gap > 0
  - uniqueness of (source_wine_id)

Emits reports/tail_d17_alias_rowset_validation_2026-04-16.md.
"""
from __future__ import annotations

import csv
import gzip
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
DATE = "2026-04-16"
IN_CSV = REPORTS / f"tail_d17_alias_candidates_{DATE}.csv.gz"
OUT_MD = REPORTS / f"tail_d17_alias_rowset_validation_{DATE}.md"

BATCH = 10000


def connect_render():
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / "backend" / ".env", override=False)
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL nao encontrado.")
    conn = psycopg2.connect(url, connect_timeout=30, keepalives=1, keepalives_idle=30)
    conn.set_session(readonly=True, autocommit=True)
    return conn


def fmt(n):
    return f"{int(n):,}".replace(",", ".")


def load_rows():
    rows = []
    with gzip.open(IN_CSV, "rt", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rows.append(row)
    return rows


def fetch_wines(conn, ids):
    out = {}
    cur = conn.cursor()
    ids = sorted(set(int(i) for i in ids))
    for i in range(0, len(ids), BATCH):
        chunk = ids[i : i + BATCH]
        cur.execute(
            "SELECT id, vivino_id, suppressed_at FROM wines WHERE id = ANY(%s)",
            (chunk,),
        )
        for wid, vivino_id, suppressed_at in cur.fetchall():
            out[int(wid)] = (vivino_id, suppressed_at)
    cur.close()
    return out


def fetch_approved_aliases(conn):
    cur = conn.cursor()
    cur.execute("SELECT source_wine_id FROM wine_aliases WHERE review_status = 'approved'")
    out = {int(row[0]) for row in cur.fetchall()}
    cur.close()
    return out


def main():
    print(f"[1] Load rowset: {IN_CSV}")
    rows = load_rows()
    print(f"    rows={len(rows):,}")

    source_ids = {int(r["source_wine_id"]) for r in rows}
    canonical_ids = {int(r["canonical_wine_id"]) for r in rows}
    print(f"    unique_sources={len(source_ids):,} unique_canonicals={len(canonical_ids):,}")

    print("[2] Connect Render (read-only)")
    conn = connect_render()
    try:
        print("[3] Fetch approved aliases")
        approved = fetch_approved_aliases(conn)
        print(f"    approved_aliases={len(approved):,}")

        print("[4] Fetch source wine status")
        source_status = fetch_wines(conn, source_ids)
        print(f"    source_hits={len(source_status):,}")

        print("[5] Fetch canonical wine status")
        canon_status = fetch_wines(conn, canonical_ids)
        print(f"    canonical_hits={len(canon_status):,}")
    finally:
        conn.close()

    issues = Counter()
    dup_sources = Counter()
    gap_zero = 0
    source_bad = 0
    canon_bad = 0
    approved_overlap = 0

    seen_sources = set()
    lane_counts = Counter()
    stratum_counts = Counter()

    for row in rows:
        sid = int(row["source_wine_id"])
        cid = int(row["canonical_wine_id"])
        lane_counts[row["lane"]] += 1
        stratum_counts[row["source_stratum"]] += 1

        if sid in seen_sources:
            dup_sources[sid] += 1
            issues["duplicate_source_wine_id"] += 1
        else:
            seen_sources.add(sid)

        gap = float(row.get("gap") or 0)
        if gap <= 0:
            gap_zero += 1
            issues["gap_not_positive"] += 1

        if sid in approved:
            approved_overlap += 1
            issues["source_already_approved"] += 1

        s_state = source_status.get(sid)
        if s_state is None:
            source_bad += 1
            issues["source_missing_in_render"] += 1
        else:
            s_vivino, s_suppressed = s_state
            if s_vivino is not None:
                source_bad += 1
                issues["source_has_vivino_id"] += 1
            if s_suppressed is not None:
                source_bad += 1
                issues["source_suppressed"] += 1

        c_state = canon_status.get(cid)
        if c_state is None:
            canon_bad += 1
            issues["canonical_missing_in_render"] += 1
        else:
            c_vivino, c_suppressed = c_state
            if c_vivino is None:
                canon_bad += 1
                issues["canonical_has_no_vivino_id"] += 1
            if c_suppressed is not None:
                canon_bad += 1
                issues["canonical_suppressed"] += 1

    print(
        f"[6] Summary: source_bad={source_bad} canon_bad={canon_bad} "
        f"approved_overlap={approved_overlap} gap_zero={gap_zero} dup_sources={len(dup_sources)}"
    )

    status = "PASS" if not issues else "FAIL"
    lines = [
        f"# D17 Rowset Validation -- {DATE}",
        "",
        f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Arquivo: `{IN_CSV}`",
        f"Modo: read-only contra Render",
        "",
        f"## Resultado: `{status}`",
        "",
        f"- Linhas: `{fmt(len(rows))}`",
        f"- source_bad: `{fmt(source_bad)}`",
        f"- canon_bad: `{fmt(canon_bad)}`",
        f"- approved_alias_overlap: `{fmt(approved_overlap)}`",
        f"- gap_zero_or_negative: `{fmt(gap_zero)}`",
        f"- duplicate_source_ids: `{fmt(len(dup_sources))}`",
        "",
        "## Contagem por lane",
        "",
        "| lane | candidatos |",
        "| --- | --- |",
    ]
    for lane, count in sorted(lane_counts.items()):
        lines.append(f"| {lane} | {fmt(count)} |")
    lines += ["", "## Contagem por estrato", "", "| estrato | candidatos |", "| --- | --- |"]
    for name, count in stratum_counts.most_common():
        lines.append(f"| {name} | {fmt(count)} |")

    if issues:
        lines += ["", "## Issues encontradas", "", "| motivo | ocorrencias |", "| --- | --- |"]
        for name, count in issues.most_common():
            lines.append(f"| {name} | {fmt(count)} |")
    else:
        lines += ["", "## Issues", "", "Nenhuma issue encontrada. Rowset passou nas invariantes read-only."]

    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"OK markdown: {OUT_MD}")
    if issues:
        sys.exit(1)


if __name__ == "__main__":
    main()
