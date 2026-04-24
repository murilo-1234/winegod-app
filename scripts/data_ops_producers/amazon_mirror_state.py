"""CLI para manipular o state journal do exporter Amazon mirror.

Uso (tipico):

    # ver se existe pending e qual o ultimo oficial
    python scripts/data_ops_producers/amazon_mirror_state.py status

    # promover pending -> oficial (apos apply PASS no Render)
    python scripts/data_ops_producers/amazon_mirror_state.py commit

    # mover pending -> aborted/<ts>.json (apos apply FAIL)
    python scripts/data_ops_producers/amazon_mirror_state.py abort \
        --reason "apply_fail_run_20260424_001"

Journal pending/commit/abort adicionado na Fase 1 do plano
`reports/WINEGOD_CODEX_PLANO_FINAL_EXECUCAO_3_FASES_*`. Evita avanco
de `last_captured_at` antes do apply PASS no Render.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sdk.plugs.commerce_dq_v3.artifact_exporters.amazon_mirror import (  # noqa: E402
    STATE_KEY,
    abort_pending_state,
    commit_pending_state,
    has_pending_state,
)
from sdk.plugs.commerce_dq_v3.artifact_exporters.base import (  # noqa: E402
    STATE_DIR,
    load_state,
)


def _pending_payload(state_source_key: str) -> dict | None:
    path = STATE_DIR / f"{state_source_key}.pending.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"_error": "pending_json_invalido", "path": str(path)}


def cmd_status(args: argparse.Namespace) -> int:
    key = args.state_source_key
    pending = _pending_payload(key)
    official = load_state(key)
    payload = {
        "state_source_key": key,
        "state_dir": str(STATE_DIR),
        "has_pending": has_pending_state(key),
        "has_official": bool(official),
        "pending": pending,
        "official": official or None,
    }
    print(json.dumps(payload, indent=2, default=str, ensure_ascii=False))
    return 0


def cmd_commit(args: argparse.Namespace) -> int:
    key = args.state_source_key
    try:
        data = commit_pending_state(key)
    except FileNotFoundError as exc:
        print(json.dumps({"ok": False, "reason": "no_pending", "detail": str(exc)}))
        return 2
    print(json.dumps({"ok": True, "committed": data}, indent=2, default=str, ensure_ascii=False))
    return 0


def cmd_abort(args: argparse.Namespace) -> int:
    key = args.state_source_key
    try:
        aborted_path = abort_pending_state(key, reason=args.reason)
    except FileNotFoundError as exc:
        print(json.dumps({"ok": False, "reason": "no_pending", "detail": str(exc)}))
        return 2
    print(
        json.dumps(
            {"ok": True, "aborted_path": str(aborted_path), "reason": args.reason},
            indent=2,
            default=str,
            ensure_ascii=False,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-source-key",
        dest="state_source_key",
        default=STATE_KEY,
        help=f"Chave do state (default: {STATE_KEY}).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Imprime JSON com pending e oficial.")
    sub.add_parser("commit", help="Promove pending -> oficial (apos apply PASS).")

    abort_p = sub.add_parser("abort", help="Move pending -> aborted/<ts>.json.")
    abort_p.add_argument(
        "--reason",
        required=True,
        help="Motivo do abort (ex: 'apply_fail_run_20260424_001').",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "commit":
        return cmd_commit(args)
    if args.cmd == "abort":
        return cmd_abort(args)
    parser.error(f"comando desconhecido: {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
