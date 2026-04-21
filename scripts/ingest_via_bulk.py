#!/usr/bin/env python3
"""CLI wrapper pro pipeline unico de ingestao.

Caminho migrado: qualquer fluxo externo (CSV/JSON/JSONL) consegue mandar
dados pro banco usando o mesmo filtro/dedup/upsert da API.
Nao chama IA paga (REGRA 6). Dry-run por default.

Uso:

    # dry-run lendo CSV (delim default = ,)
    python scripts/ingest_via_bulk.py --input wines.csv --source scraping_x

    # apply com batch custom
    python scripts/ingest_via_bulk.py --input wines.jsonl --apply --source wcf --batch-size 5000

    # stdin JSON array
    cat wines.json | python scripts/ingest_via_bulk.py --format json --stdin --source import_x

Formato aceito: cada linha/registro precisa ter ao menos "nome".
Campos opcionais: produtor, safra, tipo, pais, regiao, sub_regiao, uvas,
teor_alcoolico, harmonizacao, descricao, volume_ml, ean_gtin, imagem_url,
preco_min, preco_max, moeda.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "backend"))

from services.bulk_ingest import process_bulk  # noqa: E402


def _read_jsonl(path: Path) -> list[dict]:
    items = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items


def _read_json(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data["items"]
    raise ValueError("JSON precisa ser array ou objeto com chave 'items'")


def _read_csv(path: Path, delim: str = ",") -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=delim)
        return [{k: v for k, v in row.items() if v not in (None, "")} for row in reader]


def _read_stdin(fmt: str) -> list[dict]:
    data = sys.stdin.read()
    if fmt == "jsonl":
        return [json.loads(line) for line in data.splitlines() if line.strip()]
    parsed = json.loads(data)
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict) and isinstance(parsed.get("items"), list):
        return parsed["items"]
    raise ValueError("stdin JSON precisa ser array ou objeto com 'items'")


def _load_items(args) -> list[dict]:
    if args.stdin:
        return _read_stdin(args.format)
    path = Path(args.input)
    if not path.exists():
        raise FileNotFoundError(path)
    fmt = args.format
    if fmt == "auto":
        ext = path.suffix.lower()
        if ext == ".jsonl":
            fmt = "jsonl"
        elif ext == ".json":
            fmt = "json"
        elif ext == ".csv":
            fmt = "csv"
        elif ext == ".tsv":
            fmt = "csv"
            args.delim = "\t"
        else:
            raise ValueError(f"formato nao detectado pra extensao {ext!r} — passar --format")
    if fmt == "jsonl":
        return _read_jsonl(path)
    if fmt == "json":
        return _read_json(path)
    if fmt == "csv":
        return _read_csv(path, delim=args.delim)
    raise ValueError(f"formato desconhecido: {fmt}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingestao em bulk via pipeline unico")
    parser.add_argument("--input", help="arquivo CSV/JSON/JSONL")
    parser.add_argument("--stdin", action="store_true", help="ler de stdin")
    parser.add_argument("--format", choices=["auto", "json", "jsonl", "csv"], default="auto")
    parser.add_argument("--delim", default=",", help="delimitador CSV (default ,)")
    parser.add_argument("--source", default="cli", help="identificador da fonte")
    parser.add_argument("--apply", action="store_true", help="aplica de verdade (default: dry-run)")
    parser.add_argument("--batch-size", type=int, default=None)
    args = parser.parse_args()

    if not args.stdin and not args.input:
        parser.error("informar --input OU --stdin")

    items = _load_items(args)
    print(f"[ingest_via_bulk] carregados {len(items)} items de {'stdin' if args.stdin else args.input}", flush=True)

    result = process_bulk(
        items,
        dry_run=not args.apply,
        source=args.source,
        batch_size=args.batch_size,
    )

    print(json.dumps({
        "dry_run": result["dry_run"],
        "source": result["source"],
        "received": result["received"],
        "valid": result["valid"],
        "duplicates_in_input": result["duplicates_in_input"],
        "would_insert": result["would_insert"],
        "would_update": result["would_update"],
        "inserted": result["inserted"],
        "updated": result["updated"],
        "rejected_count": len(result["rejected"]),
        "filtered_notwine_count": len(result["filtered_notwine"]),
        "batches": result["batches"],
        "errors": result["errors"],
    }, indent=2, ensure_ascii=False))

    if result["rejected"]:
        print(f"\n[rejected amostra] primeiros {min(10, len(result['rejected']))}:", flush=True)
        for r in result["rejected"][:10]:
            print(" ", r)
    if result["filtered_notwine"]:
        print(f"\n[filtered_notwine amostra] primeiros {min(10, len(result['filtered_notwine']))}:", flush=True)
        for r in result["filtered_notwine"][:10]:
            print(" ", r)

    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
