"""
D18 executor: apply D17-approved aliases into Render wine_aliases.

Defaults to --dry-run. Requires --execute to actually write.
Source of truth: reports/tail_d17_alias_approved_2026-04-16.csv.gz (ALIAS_AUTO rows
that are not in the QA ERROR list), produced by a future freeze step.

Safety rails:
  - reads only rows where QA gate passed (upstream enforcement)
  - drops rows whose source_wine_id already has an approved alias
  - drops rows whose source is no longer active tail
  - drops rows whose canonical is no longer active Vivino
  - batches of 5000 (per CLAUDE.md REGRA 5)
  - backup of current wine_aliases snapshot to reports/d18_backup_*.csv.gz
  - emits per-batch diff to reports/d18_apply_diff_*.csv
  - rollback SQL pre-generated per run
"""
from __future__ import annotations

import argparse
import csv
import gzip
import os
import sys
from datetime import datetime
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
DATE = "2026-04-16"
IN_APPROVED = REPORTS / f"tail_d17_alias_approved_{DATE}.csv.gz"
BATCH = 5000


def fmt(n):
    return f"{int(n):,}".replace(",", ".")


def connect_render(readonly=False):
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / "backend" / ".env", override=False)
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL nao configurada.")
    conn = psycopg2.connect(url, connect_timeout=30, keepalives=1, keepalives_idle=30)
    if readonly:
        conn.set_session(readonly=True, autocommit=True)
    return conn


def load_approved(path):
    rows = []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rows.append(row)
    return rows


def fetch_existing_sources(conn):
    cur = conn.cursor()
    cur.execute("SELECT source_wine_id FROM wine_aliases")
    out = {int(r[0]) for r in cur.fetchall()}
    cur.close()
    return out


def fetch_wine_states(conn, ids):
    out = {}
    cur = conn.cursor()
    ids = sorted(set(int(i) for i in ids))
    for i in range(0, len(ids), 10000):
        chunk = ids[i : i + 10000]
        cur.execute(
            "SELECT id, vivino_id, suppressed_at FROM wines WHERE id = ANY(%s)",
            (chunk,),
        )
        for wid, vivino_id, suppressed_at in cur.fetchall():
            out[int(wid)] = (vivino_id, suppressed_at)
    cur.close()
    return out


def backup_aliases(conn, ts):
    path = REPORTS / f"d18_backup_wine_aliases_{ts}.csv.gz"
    cur = conn.cursor()
    cur.execute(
        "SELECT id, source_wine_id, canonical_wine_id, source_type, reason, confidence, review_status "
        "FROM wine_aliases ORDER BY id"
    )
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "source_wine_id", "canonical_wine_id", "source_type", "reason", "confidence", "review_status"])
        for row in cur.fetchall():
            writer.writerow(row)
    cur.close()
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="ATIVA writes (sem isso, dry-run).")
    parser.add_argument("--input", type=str, default=str(IN_APPROVED))
    parser.add_argument("--max-rows", type=int, default=0, help="Teto de segurança para total de inserts.")
    args = parser.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"[ERRO] input {in_path} nao existe. Rode o freeze step primeiro.")
        sys.exit(2)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    diff_path = REPORTS / f"d18_apply_diff_{ts}.csv"
    rollback_sql = REPORTS / f"d18_rollback_{ts}.sql"
    mode = "EXECUTE" if args.execute else "DRY-RUN"

    print(f"[{mode}] D18 -- input {in_path}  ts={ts}")
    rows = load_approved(in_path)
    print(f"[1] rows_loaded={fmt(len(rows))}")
    if args.max_rows and len(rows) > args.max_rows:
        print(f"    truncating to max_rows={args.max_rows}")
        rows = rows[: args.max_rows]

    conn = connect_render(readonly=False)
    try:
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute("SET LOCAL lock_timeout = '10s'")
        cur.close()

        print("[2] Fetch existing aliases")
        existing = fetch_existing_sources(conn)
        print(f"    existing_aliases={fmt(len(existing))}")

        print("[3] Fetch source/canonical live states")
        source_ids = [int(r["source_wine_id"]) for r in rows]
        canonical_ids = [int(r["canonical_wine_id"]) for r in rows]
        source_states = fetch_wine_states(conn, source_ids)
        canonical_states = fetch_wine_states(conn, canonical_ids)

        planned = []
        drops = {
            "source_already_alias": 0,
            "source_not_active_tail": 0,
            "canonical_not_active_vivino": 0,
        }
        for r in rows:
            sid = int(r["source_wine_id"])
            cid = int(r["canonical_wine_id"])
            if sid in existing:
                drops["source_already_alias"] += 1
                continue
            s = source_states.get(sid)
            if not s or s[0] is not None or s[1] is not None:
                drops["source_not_active_tail"] += 1
                continue
            c = canonical_states.get(cid)
            if not c or c[0] is None or c[1] is not None:
                drops["canonical_not_active_vivino"] += 1
                continue
            planned.append(r)
        print(f"[4] planned={fmt(len(planned))} drops={drops}")

        with open(diff_path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["source_wine_id", "canonical_wine_id", "lane", "score", "gap", "evidence_reason"])
            for r in planned:
                writer.writerow([
                    r["source_wine_id"], r["canonical_wine_id"], r["lane"],
                    r["score"], r["gap"], r["evidence_reason"],
                ])
        print(f"[5] diff: {diff_path}")

        if not planned:
            print("[6] Nada para aplicar. Fim.")
            return

        if not args.execute:
            print(f"[6] DRY-RUN: nenhum INSERT executado. Para aplicar: passar --execute.")
            return

        backup_path = backup_aliases(conn, ts)
        print(f"[6] backup: {backup_path}")

        rollback_sql.write_text(
            "-- Rollback gerado automaticamente antes do D18 apply em " + ts + "\n"
            "BEGIN;\n"
            "DELETE FROM wine_aliases\n"
            "WHERE review_status = 'approved'\n"
            f"  AND source_type = 'd17_batch_{ts}';\n"
            "COMMIT;\n",
            encoding="utf-8",
        )
        print(f"[6] rollback script: {rollback_sql}")

        inserted = 0
        cur = conn.cursor()
        try:
            for start in range(0, len(planned), BATCH):
                batch = planned[start : start + BATCH]
                values = [
                    (
                        int(r["source_wine_id"]),
                        int(r["canonical_wine_id"]),
                        f"d17_batch_{ts}",
                        f"D17 {r['lane']} score={r['score']} gap={r['gap']} ev={r['evidence_reason']}",
                        float(r["score"]),
                        "approved",
                    )
                    for r in batch
                ]
                args_str = b",".join(
                    cur.mogrify("(%s,%s,%s,%s,%s,%s)", v) for v in values
                ).decode("utf-8")
                sql = (
                    "INSERT INTO wine_aliases "
                    "(source_wine_id, canonical_wine_id, source_type, reason, confidence, review_status) "
                    f"VALUES {args_str} "
                    "ON CONFLICT (source_wine_id) DO NOTHING"
                )
                cur.execute(sql)
                conn.commit()
                inserted += len(batch)
                print(f"    applied batch={start // BATCH + 1} cumulative={fmt(inserted)}")
            cur.close()
        except Exception as exc:
            conn.rollback()
            print(f"[ERROR] batch failed, rolled back: {exc}")
            print(f"        rollback completo disponivel em {rollback_sql}")
            sys.exit(3)

        print(f"[7] Done. inserted={fmt(inserted)}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
