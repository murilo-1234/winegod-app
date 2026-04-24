"""CLI local para validar artefato commerce contra docs/TIER_COMMERCE_CONTRACT.md.

Uso tipico (antes de plugar o JSONL via dry-run do plug):

    python scripts/data_ops_producers/validate_commerce_artifact.py \
        --artifact-dir reports/data_ops_artifacts/amazon_mirror \
        --expected-family amazon_mirror_primary \
        --item-limit 50

Saida:

    OK artifact=<nome> items_validados=<n> sha256=<hex12>
    ou
    FAIL reason=<motivo> notes=<lista>

Exit codes:

    0 = contrato OK
    1 = contrato invalido (falta item, summary, ou SHA nao confere)
    2 = diretorio ausente ou sem JSONL

Nao escreve no banco. Nao chama o plug. Apenas le o artefato do disco e
reaproveita `sdk.plugs.commerce_dq_v3.artifact_contract.validate_artifact_dir`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sdk.plugs.commerce_dq_v3.artifact_contract import validate_artifact_dir


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Valida artefato commerce (JSONL + summary) contra TIER_COMMERCE_CONTRACT."
    )
    parser.add_argument("--artifact-dir", required=True, type=Path)
    parser.add_argument(
        "--expected-family",
        default=None,
        help="Familia esperada (ex: amazon_mirror_primary, tier1, tier2). Omitir = nao checa.",
    )
    parser.add_argument("--item-limit", type=int, default=50)
    args = parser.parse_args()

    result = validate_artifact_dir(
        artifact_dir=args.artifact_dir,
        expected_family=args.expected_family,
        item_limit=args.item_limit,
    )

    if result.ok:
        sha_short = (result.artifact_sha256 or "")[:12]
        artifact_name = result.artifact_path.name if result.artifact_path else "?"
        print(f"OK artifact={artifact_name} items_validados={len(result.items)} sha256={sha_short}")
        return 0

    if result.artifact_path is None:
        print(f"FAIL reason={result.reason or 'artefato_ausente'}")
        if result.notes:
            print("notes:", "; ".join(result.notes[:20]))
        return 2

    print(f"FAIL reason={result.reason or 'contrato_invalido'} artifact={result.artifact_path.name}")
    if result.notes:
        print("notes:", "; ".join(result.notes[:20]))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
