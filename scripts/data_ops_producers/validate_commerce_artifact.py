"""CLI local para validar artefato commerce contra docs/TIER_COMMERCE_CONTRACT.md.

Modo padrao: **full scan** do JSONL inteiro (le todas as linhas nao vazias).
Modo janela opcional: `--window <N>` valida apenas as primeiras N linhas.

Uso tipico (antes de plugar o JSONL via dry-run do plug):

    python scripts/data_ops_producers/validate_commerce_artifact.py \
        --artifact-dir reports/data_ops_artifacts/amazon_mirror \
        --expected-family amazon_mirror_primary

Uso com janela curta (smoke rapido de JSONL gigante; NAO substitui
validacao full antes de plugar):

    python scripts/data_ops_producers/validate_commerce_artifact.py \
        --artifact-dir reports/data_ops_artifacts/amazon_mirror \
        --expected-family amazon_mirror_primary \
        --window 50

Saida:

    OK mode=full artifact=<nome> items_validados=<n> lines_validated=<n> sha256=<hex12>
    ou
    FAIL mode=<modo> reason=<motivo> notes=<lista>

Exit codes:

    0 = contrato OK
    1 = contrato invalido (campos faltando, summary, SHA mismatch, linha invalida pos-janela, items_emitted divergente)
    2 = diretorio ausente ou sem JSONL

Nao escreve no banco. Nao chama o plug. Apenas le o artefato do disco e
reaproveita os validadores em `sdk.plugs.commerce_dq_v3.artifact_contract`.

Modo full garante que erros depois da janela curta nao passem despercebidos
e tambem compara `summary.items_emitted` com o total real de linhas JSON
validas nao vazias do JSONL.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sdk.plugs.commerce_dq_v3.artifact_contract import (
    validate_artifact_dir,
    validate_artifact_dir_full,
)


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
    parser.add_argument(
        "--window",
        type=int,
        default=None,
        help=(
            "Valida apenas as primeiras N linhas (modo janela, smoke rapido). "
            "Sem esse flag, o CLI faz FULL SCAN do JSONL inteiro (recomendado "
            "antes de plugar o artefato)."
        ),
    )
    parser.add_argument(
        "--item-limit",
        type=int,
        default=None,
        help="DEPRECATED: use --window. Preservado para compatibilidade.",
    )
    args = parser.parse_args()

    window = args.window if args.window is not None else args.item_limit

    if window is None:
        result = validate_artifact_dir_full(
            artifact_dir=args.artifact_dir,
            expected_family=args.expected_family,
        )
        mode_label = "full"
    else:
        result = validate_artifact_dir(
            artifact_dir=args.artifact_dir,
            expected_family=args.expected_family,
            item_limit=window,
        )
        mode_label = f"window={window}"

    if result.ok:
        sha_short = (result.artifact_sha256 or "")[:12]
        artifact_name = result.artifact_path.name if result.artifact_path else "?"
        lines_note = next((n for n in result.notes if n.startswith("lines_validated=")), None)
        lines_str = f" {lines_note}" if lines_note else ""
        print(
            f"OK mode={mode_label} artifact={artifact_name} "
            f"items_validados={len(result.items)}{lines_str} sha256={sha_short}"
        )
        return 0

    if result.artifact_path is None:
        print(f"FAIL mode={mode_label} reason={result.reason or 'artefato_ausente'}")
        if result.notes:
            print("notes:", "; ".join(result.notes[:20]))
        return 2

    print(
        f"FAIL mode={mode_label} reason={result.reason or 'contrato_invalido'} "
        f"artifact={result.artifact_path.name}"
    )
    if result.notes:
        print("notes:", "; ".join(result.notes[:20]))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
