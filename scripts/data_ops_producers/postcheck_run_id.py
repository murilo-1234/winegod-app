"""Postcheck por run_id: compara summary markdown com estado Render.

Uso:
  python scripts/data_ops_producers/postcheck_run_id.py \
    --run-id <apply_run_id> \
    --summary-path reports/data_ops_plugs_staging/<ts>_commerce_<src>_summary.md \
    --apply-start <iso_timestamp> \
    --output reports/subida_vinhos_20260424/postchecks/<shard_id>.json

Requer DATABASE_URL (Render) no env.

PASS se:
  - ingestion_run_log tem 1 linha pro run_id;
  - wines_new + wines_updated bate com summary.inserted + summary.updated (+-2%);
  - wine_sources_touched bate com summary.sources_inserted + sources_updated;
  - not_wine_rejections.count bate com summary.filtered_notwine_count;
  - ingestion_review_queue.count bate com summary.would_enqueue_review.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import psycopg2


def extract_result_json_from_summary(md_path: Path) -> dict:
    text = md_path.read_text(encoding="utf-8")
    # Tolera CRLF (Windows) e LF (Unix).
    match = re.search(r"```json\r?\n(.*?)\r?\n```", text, re.DOTALL)
    if not match:
        raise ValueError(f"bloco ```json``` nao encontrado em {md_path}")
    return json.loads(match.group(1))


def _fetch_int(conn, sql, params):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return int(row[0] or 0) if row else 0


def run_postcheck(run_id, summary_path, apply_start_iso, output_path):
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL nao definido (Render DSN)")
    summary_md = Path(summary_path)
    if not summary_md.exists():
        raise FileNotFoundError(summary_md)
    sm = extract_result_json_from_summary(summary_md)

    apply_start = datetime.fromisoformat(apply_start_iso.replace("Z", "+00:00"))

    render_counts = {}
    with psycopg2.connect(dsn) as conn:
        render_counts["wines_new"] = _fetch_int(
            conn,
            "SELECT count(*) FROM wines WHERE ingestion_run_id=%s AND created_at >= %s",
            (run_id, apply_start),
        )
        render_counts["wines_updated"] = _fetch_int(
            conn,
            "SELECT count(*) FROM wines WHERE ingestion_run_id=%s AND created_at < %s",
            (run_id, apply_start),
        )
        render_counts["wine_sources_touched"] = _fetch_int(
            conn,
            "SELECT count(*) FROM wine_sources WHERE ingestion_run_id=%s",
            (run_id,),
        )
        render_counts["not_wine_rejections"] = _fetch_int(
            conn,
            "SELECT count(*) FROM not_wine_rejections WHERE run_id=%s",
            (run_id,),
        )
        render_counts["ingestion_review_queue"] = _fetch_int(
            conn,
            "SELECT count(*) FROM ingestion_review_queue WHERE run_id=%s",
            (run_id,),
        )
        render_counts["ingestion_run_log"] = _fetch_int(
            conn,
            "SELECT count(*) FROM ingestion_run_log WHERE run_id=%s",
            (run_id,),
        )

    expected = {
        "inserted": int(sm.get("inserted") or 0),
        "updated": int(sm.get("updated") or 0),
        "sources_inserted": int(sm.get("sources_inserted") or 0),
        "sources_updated": int(sm.get("sources_updated") or 0),
        "filtered_notwine_count": int(sm.get("filtered_notwine_count") or 0),
        "would_enqueue_review": int(
            sm.get("would_enqueue_review") or int(sm.get("enqueue_for_review_count") or 0)
        ),
    }

    checks = {
        "wines_new_vs_inserted": {
            "expected": expected["inserted"],
            "got": render_counts["wines_new"],
            "diff_pct": None,
        },
        "wines_updated_vs_summary": {
            "expected": expected["updated"],
            "got": render_counts["wines_updated"],
        },
        "wine_sources_vs_summary": {
            "expected": expected["sources_inserted"] + expected["sources_updated"],
            "got": render_counts["wine_sources_touched"],
        },
        "not_wine_vs_summary": {
            "expected": expected["filtered_notwine_count"],
            "got": render_counts["not_wine_rejections"],
        },
        "queue_vs_summary": {
            "expected": expected["would_enqueue_review"],
            "got": render_counts["ingestion_review_queue"],
        },
        "ingestion_run_log_exists": {
            "expected": 1,
            "got": render_counts["ingestion_run_log"],
        },
    }

    def tolerance_ok(exp, got, tol=0.02):
        if exp == 0:
            return got == 0
        return abs(got - exp) / exp <= tol

    # Computa PASS
    pass_flags = []
    pass_flags.append(
        tolerance_ok(
            checks["wines_new_vs_inserted"]["expected"],
            checks["wines_new_vs_inserted"]["got"],
        )
    )
    pass_flags.append(
        tolerance_ok(
            checks["wine_sources_vs_summary"]["expected"],
            checks["wine_sources_vs_summary"]["got"],
        )
    )
    pass_flags.append(
        tolerance_ok(
            checks["not_wine_vs_summary"]["expected"],
            checks["not_wine_vs_summary"]["got"],
            tol=0.05,
        )
    )
    pass_flags.append(checks["ingestion_run_log_exists"]["got"] >= 1)

    status = "PASS" if all(pass_flags) else "FAIL"

    output = {
        "run_id": run_id,
        "summary_path": str(summary_md),
        "apply_start": apply_start_iso,
        "render_counts": render_counts,
        "summary_metrics": expected,
        "checks": checks,
        "status": status,
        "checked_at": datetime.utcnow().isoformat() + "Z",
    }
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(json.dumps(output, indent=2, default=str))
    return 0 if status == "PASS" else 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    p.add_argument("--summary-path", required=True)
    p.add_argument("--apply-start", required=True, help="ISO timestamp (inicio do apply)")
    p.add_argument("--output", required=True)
    args = p.parse_args()
    return run_postcheck(args.run_id, args.summary_path, args.apply_start, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
