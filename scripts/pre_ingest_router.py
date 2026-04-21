#!/usr/bin/env python3
"""Router operacional do pipeline de ingestao.

Fase 2 do plano `WINEGOD_PRE_INGEST_ROUTER`. Le um JSONL de entrada,
aplica `scripts/_ingest_classifier.classify`, e escreve saidas
separadas por status em `reports/ingest_pipeline/<ts>_<source>/`.

Nao chama Gemini, nao abre DB, nao faz HTTP.

Uso:
    python scripts/pre_ingest_router.py \\
        --input caminho/input.jsonl \\
        --source nome_da_fonte

Opcoes:
    --out-dir DIR       (default reports/ingest_pipeline)
    --timestamp YYYYMMDD_HHMMSS  (default agora)

Saidas em <out-dir>/<timestamp>_<source>/:
    ready.jsonl                   (compativel com ingest_via_bulk.py)
    needs_enrichment.jsonl
    rejected_notwine.jsonl
    uncertain_review.csv          (saida lateral, nunca bloqueia)
    summary.md                    (contadores + warning 20%)

Exit codes:
    0 - processou, mesmo com uncertain > 0
    1 - erro real (input inexistente, JSONL invalido, erro de escrita)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _ingest_classifier import classify  # noqa: E402


_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_OUT_SUBDIR = Path("reports") / "ingest_pipeline"
_SOURCE_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")


STATUS_TO_BUCKET = {
    "ready": "ready",
    "needs_enrichment": "needs_enrichment",
    "not_wine": "rejected_notwine",
    "uncertain": "uncertain",
}

JSONL_BUCKETS = ("ready", "needs_enrichment", "rejected_notwine")

CSV_COLS = [
    "router_index",
    "source",
    "nome",
    "produtor",
    "safra",
    "pais",
    "regiao",
    "sub_regiao",
    "ean_gtin",
    "reasons",
    "raw_json",
]


class RouterError(Exception):
    """Erro real de execucao (input/parse/escrita). Leva a exit 1."""


def _validate_source(source: str | None) -> str:
    """Valida --source. Levanta RouterError em qualquer problema.

    Regras:
      - nao vazio, nao so espacos
      - apenas [A-Za-z0-9_.-] (sem espacos, sem acentos, sem / \\ : ..)
    """
    if source is None or not str(source).strip():
        raise RouterError("source_invalido: vazio")
    src = str(source)
    # bloqueios explicitos mais informativos que a regex
    if ".." in src:
        raise RouterError(f"source_invalido: path_traversal ({src!r})")
    if any(ch in src for ch in "/\\"):
        raise RouterError(f"source_invalido: contem_barra ({src!r})")
    if any(ch.isspace() for ch in src):
        raise RouterError(f"source_invalido: contem_espaco ({src!r})")
    if not _SOURCE_RE.match(src):
        raise RouterError(
            f"source_invalido: so_aceita_[A-Za-z0-9_.-] ({src!r})"
        )
    return src


def _resolve_out_dir(out_dir: str | None) -> Path:
    """Se --out-dir omitido, ancora em <repo_root>/reports/ingest_pipeline.

    Se passado, respeita o valor (relativo resolvido contra CWD).
    """
    if out_dir:
        return Path(out_dir)
    return _REPO_ROOT / _DEFAULT_OUT_SUBDIR


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        raise RouterError(f"input_nao_existe: {path}")
    items: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for lineno, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise RouterError(
                    f"jsonl_invalido linha={lineno}: {e.msg}"
                )
            if not isinstance(obj, dict):
                raise RouterError(
                    f"jsonl_linha_nao_objeto linha={lineno}: type={type(obj).__name__}"
                )
            items.append(obj)
    return items


def _annotate(item: dict, status: str, reasons: list[str],
              source: str, index: int) -> dict:
    """Adiciona metadata _router_* sem tocar nos campos originais."""
    out = dict(item)
    out["_router_status"] = status
    out["_router_reasons"] = list(reasons)
    out["_router_source"] = source
    out["_router_index"] = index
    return out


def _clean(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    return json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else str(v)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_uncertain_csv(path: Path, rows: list[dict], source: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS)
        w.writeheader()
        for row in rows:
            idx = row.get("_router_index", "")
            reasons = row.get("_router_reasons") or []
            raw = {k: v for k, v in row.items() if not k.startswith("_router_")}
            w.writerow({
                "router_index": idx,
                "source": source,
                "nome": _clean(raw.get("nome")),
                "produtor": _clean(raw.get("produtor")),
                "safra": _clean(raw.get("safra")),
                "pais": _clean(raw.get("pais")),
                "regiao": _clean(raw.get("regiao")),
                "sub_regiao": _clean(raw.get("sub_regiao")),
                "ean_gtin": _clean(raw.get("ean_gtin")),
                "reasons": ";".join(reasons),
                "raw_json": json.dumps(raw, ensure_ascii=False),
            })


def _pct(n: int, total: int) -> float:
    return (n * 100.0 / total) if total else 0.0


def _write_summary(path: Path, *, input_path: str, source: str,
                   timestamp: str, counts: dict, out_dir: Path) -> None:
    total = counts["total"]
    r = counts["ready"]
    e = counts["needs_enrichment"]
    n = counts["rejected_notwine"]
    u = counts["uncertain"]
    u_pct = _pct(u, total)

    lines: list[str] = []
    lines.append(f"# Pre-ingest router — summary")
    lines.append("")
    lines.append(f"- Input: `{input_path}`")
    lines.append(f"- Source: `{source}`")
    lines.append(f"- Timestamp: `{timestamp}`")
    lines.append(f"- Output dir: `{out_dir.as_posix()}`")
    lines.append("")
    lines.append("## Contadores")
    lines.append("")
    lines.append("| Bucket | Count | % |")
    lines.append("|---|---:|---:|")
    lines.append(f"| total received | {total} | 100.00% |")
    lines.append(f"| ready | {r} | {_pct(r, total):.2f}% |")
    lines.append(f"| needs_enrichment | {e} | {_pct(e, total):.2f}% |")
    lines.append(f"| rejected_notwine | {n} | {_pct(n, total):.2f}% |")
    lines.append(f"| uncertain | {u} | {u_pct:.2f}% |")
    lines.append("")
    if u_pct > 20.0:
        lines.append("## WARNING")
        lines.append("")
        lines.append(
            f"`uncertain_pct = {u_pct:.2f}%` excede o soft gate de 20%. "
            "Revise a qualidade do primeiro filtro ou do input antes de "
            "disparar enrichment em volume. Nao bloqueia o pipeline."
        )
        lines.append("")
    lines.append("## Proximo passo recomendado")
    lines.append("")
    lines.append("Dry-run dos items `ready` via CLI canonica:")
    lines.append("")
    lines.append("```bash")
    lines.append(
        f"python scripts/ingest_via_bulk.py \\\n"
        f"  --input {(out_dir / 'ready.jsonl').as_posix()} \\\n"
        f"  --source {source}"
    )
    lines.append("```")
    lines.append("")
    lines.append("Sem `--apply`. Rodar dry-run primeiro e inspecionar contadores.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def run_router(input_path: str, source: str,
               out_dir: str | None = None,
               timestamp: str | None = None) -> dict:
    """Core do router. Retorna dict com counts, out_dir, timestamp.

    Pode levantar RouterError para erros de execucao (trata o caller).

    Ordem de validacao (nao cria diretorio antes de validar input/source):
      1. source sanitizada
      2. input existe e e JSONL valido (le todos os items)
      3. so entao cria o diretorio de saida e escreve
    """
    validated_source = _validate_source(source)

    items = _read_jsonl(Path(input_path))

    ts = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    base_out = _resolve_out_dir(out_dir)
    run_out = base_out / f"{ts}_{validated_source}"
    run_out.mkdir(parents=True, exist_ok=True)

    # A partir daqui `source` e validado — usar validated_source
    source = validated_source

    buckets: dict[str, list[dict]] = {
        "ready": [],
        "needs_enrichment": [],
        "rejected_notwine": [],
        "uncertain": [],
    }

    for idx, item in enumerate(items):
        status, reasons = classify(item)
        bucket = STATUS_TO_BUCKET.get(status, "uncertain")
        annotated = _annotate(item, status, reasons, source, idx)
        buckets[bucket].append(annotated)

    try:
        for b in JSONL_BUCKETS:
            _write_jsonl(run_out / f"{b}.jsonl", buckets[b])
        _write_uncertain_csv(run_out / "uncertain_review.csv",
                             buckets["uncertain"], source)
        counts = {
            "total": len(items),
            "ready": len(buckets["ready"]),
            "needs_enrichment": len(buckets["needs_enrichment"]),
            "rejected_notwine": len(buckets["rejected_notwine"]),
            "uncertain": len(buckets["uncertain"]),
        }
        _write_summary(
            run_out / "summary.md",
            input_path=input_path,
            source=source,
            timestamp=ts,
            counts=counts,
            out_dir=run_out,
        )
    except OSError as e:
        raise RouterError(f"erro_de_escrita: {e}")

    return {
        "counts": counts,
        "out_dir": run_out,
        "timestamp": ts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", required=True, help="arquivo JSONL de entrada")
    parser.add_argument("--source", required=True, help="identificador da fonte")
    parser.add_argument("--out-dir", default=None,
                        help="diretorio base de saida (default: <repo_root>/reports/ingest_pipeline)")
    parser.add_argument("--timestamp", default=None,
                        help="timestamp YYYYMMDD_HHMMSS (default: agora)")
    args = parser.parse_args()

    try:
        result = run_router(
            input_path=args.input,
            source=args.source,
            out_dir=args.out_dir,
            timestamp=args.timestamp,
        )
    except RouterError as e:
        print(f"[router] ERRO: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # pragma: no cover
        print(f"[router] ERRO inesperado: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    counts = result["counts"]
    out_dir = result["out_dir"]
    total = counts["total"]
    u_pct = _pct(counts["uncertain"], total)
    print(json.dumps({
        "out_dir": out_dir.as_posix(),
        "timestamp": result["timestamp"],
        **counts,
        "uncertain_pct": round(u_pct, 2),
    }, indent=2, ensure_ascii=False))
    if u_pct > 20.0:
        print(f"[router] WARNING: uncertain_pct={u_pct:.2f}% > 20% "
              "(nao bloqueante, veja summary.md)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
