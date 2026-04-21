#!/usr/bin/env python3
"""Parser dry-run de `wines.descricao` em campos estruturados.

Contexto: os 139k wines enriquecidos pelo Gemini v3 tem `descricao` no
formato:

    ABV: 13.5 | Classificacao: DOC | Corpo: medio | Docura: seco |
    Harmonizacao: carne vermelha | Envelhecimento: 3-5 anos |
    Temperatura: 16-18C

Este script:

1. Le wines.descricao em streaming (sem carregar tudo na memoria).
2. Extrai campos regex-based.
3. Gera relatorio de cobertura e CSV com amostras.
4. NAO ESCREVE NADA no banco (REGRA 2 + feedback "fases auditadas").

Decisao pro apply real fica com o humano apos ver o relatorio.

Uso:
    python scripts/parse_gemini_descricao_fields.py
    python scripts/parse_gemini_descricao_fields.py --sample 5000
    python scripts/parse_gemini_descricao_fields.py --out reports/WINEGOD_PAIS_RECOVERY_PARSER_DRYRUN.md
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import psycopg2
from urllib.parse import urlparse

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ENV_FILE = _REPO_ROOT / "backend" / ".env"

try:
    from dotenv import load_dotenv
    load_dotenv(_ENV_FILE)
except ImportError:
    pass


FIELDS = [
    "abv",
    "classificacao",
    "corpo",
    "docura",
    "harmonizacao",
    "envelhecimento",
    "temperatura",
]

# Regex flexiveis: aceitam variacoes de acento e case
# Os campos vem separados por " | " no output tipico do Gemini
_PATTERNS = {
    "abv": re.compile(r"ABV\s*:\s*([0-9]+(?:[.,][0-9]+)?)\s*%?", re.IGNORECASE),
    "classificacao": re.compile(r"Classifica[cç][aã]o\s*:\s*([^|]+)", re.IGNORECASE),
    "corpo": re.compile(r"Corpo\s*:\s*([^|]+)", re.IGNORECASE),
    "docura": re.compile(r"Do[cç]ura\s*:\s*([^|]+)", re.IGNORECASE),
    "harmonizacao": re.compile(r"Harmoniza[cç][aã]o\s*:\s*([^|]+)", re.IGNORECASE),
    "envelhecimento": re.compile(r"Envelhecimento\s*:\s*([^|]+)", re.IGNORECASE),
    "temperatura": re.compile(r"Temperatura\s*:\s*([^|]+)", re.IGNORECASE),
}

_CORPO_NORM = {"leve", "medio", "encorpado", "muito encorpado", "robusto"}
_DOCURA_NORM = {"seco", "meio-seco", "meio seco", "suave", "meio-doce", "meio doce", "doce"}


def _strip(text: str) -> str:
    return text.strip().strip(".").strip()


def parse_descricao(descricao: str) -> dict:
    if not descricao:
        return {}
    out = {}
    for field, pat in _PATTERNS.items():
        m = pat.search(descricao)
        if not m:
            continue
        raw = _strip(m.group(1))
        if not raw:
            continue
        if field == "abv":
            try:
                val = float(raw.replace(",", "."))
                if 0 < val < 30:
                    out["abv"] = val
            except ValueError:
                pass
        else:
            out[field] = raw
    return out


def get_conn():
    dsn = os.environ["DATABASE_URL"]
    u = urlparse(dsn)
    return psycopg2.connect(
        host=u.hostname, port=u.port, database=u.path[1:],
        user=u.username, password=u.password,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=None,
                        help="processa apenas N wines (default: todos)")
    parser.add_argument("--out", default=None,
                        help="caminho do relatorio markdown")
    parser.add_argument("--csv", default=None,
                        help="caminho do CSV de amostras")
    parser.add_argument("--batch-size", type=int, default=10000)
    args = parser.parse_args()

    if not args.out:
        args.out = str(_REPO_ROOT / "reports" / "WINEGOD_PAIS_RECOVERY_PARSER_DRYRUN.md")
    if not args.csv:
        args.csv = str(_REPO_ROOT / "reports" / "WINEGOD_PAIS_RECOVERY_PARSER_DRYRUN_samples.csv")

    conn = get_conn()
    cur = conn.cursor(name="parse_cursor")  # server-side cursor para streaming
    cur.itersize = args.batch_size

    limit_clause = f"LIMIT {args.sample}" if args.sample else ""

    print(f"[parse] lendo wines com descricao...", flush=True)
    cur.execute(f"""
        SELECT id, nome, produtor, teor_alcoolico, harmonizacao, descricao
        FROM wines
        WHERE descricao IS NOT NULL AND descricao <> ''
          AND suppressed_at IS NULL
        {limit_clause}
    """)

    total = 0
    extracted_per_field = Counter()
    extracted_any = 0
    abv_agreement = {"match": 0, "mismatch": 0, "only_extracted": 0, "only_column": 0, "both_null": 0}
    harmonizacao_divergente = 0
    corpo_values = Counter()
    docura_values = Counter()
    classificacao_top = Counter()
    samples = []
    samples_limit = 200

    for row in cur:
        wid, nome, produtor, teor_col, harm_col, descricao = row
        total += 1
        parsed = parse_descricao(descricao)

        if parsed:
            extracted_any += 1
        for f in FIELDS:
            if f in parsed:
                extracted_per_field[f] += 1

        # ABV consistency
        abv_parsed = parsed.get("abv")
        teor_float = float(teor_col) if teor_col is not None else None
        if abv_parsed is None and teor_float is None:
            abv_agreement["both_null"] += 1
        elif abv_parsed is not None and teor_float is None:
            abv_agreement["only_extracted"] += 1
        elif abv_parsed is None and teor_float is not None:
            abv_agreement["only_column"] += 1
        else:
            if abs(abv_parsed - teor_float) <= 0.21:
                abv_agreement["match"] += 1
            else:
                abv_agreement["mismatch"] += 1

        # Harmonizacao
        if "harmonizacao" in parsed and harm_col and parsed["harmonizacao"].lower() != harm_col.lower():
            harmonizacao_divergente += 1

        # Distribuicao de valores
        if "corpo" in parsed:
            corpo_values[parsed["corpo"].lower()] += 1
        if "docura" in parsed:
            docura_values[parsed["docura"].lower()] += 1
        if "classificacao" in parsed:
            classificacao_top[parsed["classificacao"]] += 1

        if len(samples) < samples_limit and parsed:
            samples.append({
                "id": wid,
                "nome": nome,
                "teor_col": teor_col,
                "abv_parsed": parsed.get("abv"),
                "classificacao": parsed.get("classificacao"),
                "corpo": parsed.get("corpo"),
                "docura": parsed.get("docura"),
                "harmonizacao_col": harm_col,
                "harmonizacao_parsed": parsed.get("harmonizacao"),
                "envelhecimento": parsed.get("envelhecimento"),
                "temperatura": parsed.get("temperatura"),
            })

        if total % 20000 == 0:
            print(f"[parse] {total:,} processados...", flush=True)

    cur.close()
    conn.close()

    # CSV
    csv_path = args.csv
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(samples[0].keys()) if samples else ["id"])
        writer.writeheader()
        for row in samples:
            writer.writerow(row)
    print(f"[parse] CSV amostra -> {csv_path}", flush=True)

    # Relatorio markdown
    out_path = args.out
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    lines = []
    lines.append(f"# WINEGOD_PAIS_RECOVERY — Parser Descricao (DRY-RUN)")
    lines.append("")
    lines.append(f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Wines processados: **{total:,}**")
    lines.append(f"Com pelo menos 1 campo extraido: **{extracted_any:,}** ({extracted_any*100.0/max(total,1):.2f}%)")
    lines.append("")
    lines.append("## Cobertura por campo")
    lines.append("")
    lines.append("| Campo | Extraidos | % |")
    lines.append("|---|---:|---:|")
    for f in FIELDS:
        n = extracted_per_field[f]
        pct = n * 100.0 / max(total, 1)
        lines.append(f"| {f} | {n:,} | {pct:.2f}% |")
    lines.append("")
    lines.append("## ABV: parsed vs coluna `teor_alcoolico`")
    lines.append("")
    lines.append("| Categoria | Count |")
    lines.append("|---|---:|")
    lines.append(f"| match (<= 0.2 diff) | {abv_agreement['match']:,} |")
    lines.append(f"| mismatch | {abv_agreement['mismatch']:,} |")
    lines.append(f"| so extraido (coluna null) | {abv_agreement['only_extracted']:,} |")
    lines.append(f"| so coluna (extraido null) | {abv_agreement['only_column']:,} |")
    lines.append(f"| ambos null | {abv_agreement['both_null']:,} |")
    lines.append("")
    lines.append(f"## Harmonizacao divergente da coluna existente: {harmonizacao_divergente:,}")
    lines.append("")
    lines.append("## Top 15 valores extraidos")
    lines.append("")
    lines.append("### Corpo")
    for v, c in corpo_values.most_common(15):
        norm_tag = " (padrao)" if v in _CORPO_NORM else ""
        lines.append(f"- `{v}`: {c:,}{norm_tag}")
    lines.append("")
    lines.append("### Docura")
    for v, c in docura_values.most_common(15):
        norm_tag = " (padrao)" if v in _DOCURA_NORM else ""
        lines.append(f"- `{v}`: {c:,}{norm_tag}")
    lines.append("")
    lines.append("### Classificacao (top 15 distintas)")
    for v, c in classificacao_top.most_common(15):
        lines.append(f"- `{v}`: {c:,}")
    lines.append("")
    lines.append("## Decisao pendente (gate humano)")
    lines.append("")
    lines.append("- Aprovar UPDATE real em `wines` (colunas novas ou existentes)?")
    lines.append("- Criar colunas: `abv` (ou reutilizar `teor_alcoolico`), `classificacao`, `corpo`, `docura`, `envelhecimento`, `temperatura_servico`?")
    lines.append("- Estrategia de apply: desativar `trg_score_recalc`, UPDATE em chunks de 2.000, reativar — mesma receita do pais_recovery.")
    lines.append("")
    lines.append(f"CSV de amostras: `{csv_path}`")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[parse] Relatorio -> {out_path}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
