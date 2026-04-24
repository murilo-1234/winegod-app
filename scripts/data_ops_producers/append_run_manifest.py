"""Anexa uma linha JSON ao reports/subida_vinhos_20260424/run_manifest.jsonl.

Uso:
  python scripts/data_ops_producers/append_run_manifest.py \
    --shard-id tier1_us_001 --phase phase_2_execution --source tier1_global \
    --country us --source-table vinhos_us_fontes --min-fonte-id 1 --max-fonte-id 50000 \
    --expected-rows 50000 --artifact-path reports/data_ops_artifacts/tier1/xyz.jsonl \
    --artifact-sha256 abc123 --apply-run-id plug_commerce_dq_v3_tier1_global_20260425_143022 \
    --status PASS --started-at 2026-04-25T14:30:22Z --finished-at 2026-04-25T14:32:45Z \
    --metrics-json '{"received":50000,...}' [--decision-rationale "..."]

Para testes, o caminho do manifest pode ser sobrescrito via env var
RUN_MANIFEST_PATH.
"""

import argparse
import json
import os
from pathlib import Path

DEFAULT_MANIFEST_PATH = "reports/subida_vinhos_20260424/run_manifest.jsonl"


def _manifest_path() -> Path:
    return Path(os.environ.get("RUN_MANIFEST_PATH", DEFAULT_MANIFEST_PATH))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--campaign", default="subida_vinhos_20260424")
    p.add_argument("--phase", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--shard-id", required=True)
    p.add_argument("--country", default="")
    p.add_argument("--source-table", default="")
    p.add_argument("--min-fonte-id", type=int, default=0)
    p.add_argument("--max-fonte-id", type=int, default=0)
    p.add_argument("--expected-rows", type=int, default=0)
    p.add_argument("--artifact-path", required=True)
    p.add_argument("--artifact-sha256", required=True)
    p.add_argument("--apply-run-id", required=True)
    p.add_argument(
        "--status",
        required=True,
        choices=[
            "PASS",
            "FAIL",
            "WARN",
            "ABORT",
            "SKIPPED",
            "SKIPPED_BLOCKED_STATE",
            "SKIPPED_BLOCKED_EXTERNAL",
            "BLOCKED_ENV",
        ],
    )
    p.add_argument("--started-at", required=True)
    p.add_argument("--finished-at", required=True)
    p.add_argument("--metrics-json", default="{}")
    p.add_argument("--decision-rationale", default="")
    args = p.parse_args()

    line = {
        "campaign": args.campaign,
        "phase": args.phase,
        "source": args.source,
        "shard_id": args.shard_id,
        "country": args.country,
        "source_table": args.source_table,
        "min_fonte_id": args.min_fonte_id,
        "max_fonte_id": args.max_fonte_id,
        "expected_rows": args.expected_rows,
        "artifact_path": args.artifact_path,
        "artifact_sha256": args.artifact_sha256,
        "apply_run_id": args.apply_run_id,
        "status": args.status,
        "started_at": args.started_at,
        "finished_at": args.finished_at,
        "metrics": json.loads(args.metrics_json),
        "decision_rationale": args.decision_rationale,
    }
    manifest_path = _manifest_path()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, default=str, ensure_ascii=False) + "\n")
    print(json.dumps(line, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
