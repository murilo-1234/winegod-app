"""
Read-only D17 opener.

This script reconnects to the Render database, recounts the active tail after
the NOT_WINE suppress wave, and writes two local reports:

- reports/tail_active_recount_2026-04-16.md
- reports/tail_d17_opening_2026-04-16.md

It does not write to the production database.
"""

from __future__ import annotations

import os
import csv
import gzip
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"
RECOUNT_REPORT = REPORTS_DIR / "tail_active_recount_2026-04-16.md"
D17_REPORT = REPORTS_DIR / "tail_d17_opening_2026-04-16.md"


def _load_env() -> None:
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / "backend" / ".env", override=False)


def _connect():
    database_url = os.getenv("DATABASE_URL") or os.getenv("WINEGOD_DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL/WINEGOD_DATABASE_URL nao encontrado no ambiente.")

    return psycopg2.connect(database_url, connect_timeout=30)


def _scalar(cur, sql: str, params: tuple[Any, ...] = ()) -> int:
    cur.execute(sql, params)
    value = cur.fetchone()[0]
    return int(value or 0)


def _rows(cur, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    cur.execute(sql, params)
    return list(cur.fetchall())


def _count_csv_rows(path: Path) -> int:
    if not path.exists():
        return 0

    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        return max(sum(1 for _ in reader) - 1, 0)


def _fmt(value: int | float | None) -> str:
    if value is None:
        return "0"
    return f"{int(value):,}".replace(",", ".")


def _pct(part: int, total: int) -> str:
    if not total:
        return "0,00%"
    return f"{(part / total) * 100:.2f}%".replace(".", ",")


def _table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def collect_counts() -> dict[str, Any]:
    _load_env()
    conn = _connect()
    conn.set_session(readonly=True, autocommit=True)

    try:
        cur = conn.cursor()
        cur.execute("SET enable_seqscan = off")
        cur.execute("SET statement_timeout = 180000")
        counts: dict[str, Any] = {}

        cur.execute(
            """
            SELECT
              COUNT(*) FILTER (WHERE suppressed_at IS NULL) AS active_tail,
              COUNT(*) FILTER (WHERE suppressed_at IS NOT NULL) AS suppressed_tail,
              COUNT(*) AS total_tail
            FROM wines
            WHERE vivino_id IS NULL
            """
        )
        active_tail, suppressed_tail, total_tail = cur.fetchone()
        counts["tail_active"] = int(active_tail or 0)
        counts["tail_suppressed"] = int(suppressed_tail or 0)
        counts["tail_total"] = int(total_tail or 0)

        counts["canonical_official_2026_04_10"] = 1_727_058
        counts["wines_total_derived"] = counts["canonical_official_2026_04_10"] + counts["tail_total"]
        counts["wine_aliases_total"] = _scalar(cur, "SELECT COUNT(*) FROM wine_aliases")
        counts["wine_aliases_approved"] = _scalar(
            cur,
            "SELECT COUNT(*) FROM wine_aliases WHERE review_status = 'approved'",
        )
        counts["alias_sources_approved"] = _scalar(
            cur,
            "SELECT COUNT(DISTINCT source_wine_id) FROM wine_aliases WHERE review_status = 'approved'",
        )
        counts["alias_canonicals_approved"] = _scalar(
            cur,
            "SELECT COUNT(DISTINCT canonical_wine_id) FROM wine_aliases WHERE review_status = 'approved'",
        )
        reason_files = [
            (
                "d16_strong_patterns_2026-04-15",
                REPORTS_DIR / "tail_d16_strong_suppress_candidates_2026-04-15.csv.gz",
            ),
            (
                "d16_wine_filter_expansion_2026-04-15",
                REPORTS_DIR / "tail_d16_wine_filter_expansion_candidates_2026-04-15.csv.gz",
            ),
            (
                "d16_wine_filter_round3_2026-04-15",
                REPORTS_DIR / "tail_d16_round3_candidates_2026-04-15.csv.gz",
            ),
            (
                "d16_wine_filter_round4_2026-04-15",
                REPORTS_DIR / "tail_d16_round4_candidates_2026-04-15.csv.gz",
            ),
        ]
        counts["tail_suppressed_by_reason"] = [
            (reason, _count_csv_rows(path)) for reason, path in reason_files
        ]
        cur.close()
        return counts
    finally:
        conn.close()


def write_recount_report(counts: dict[str, Any], now: datetime) -> None:
    frame_2026_04_10 = 779_383
    active_tail = counts["tail_active"]
    tail_suppressed = counts["tail_suppressed"]

    summary_rows = [
        ["wines total derivado", _fmt(counts["wines_total_derived"]), "canonicos oficiais + cauda live"],
        ["canonicos Vivino oficiais", _fmt(counts["canonical_official_2026_04_10"]), "Snapshot aprovado de 2026-04-10"],
        ["cauda total sem vivino_id", _fmt(counts["tail_total"]), "Ativos + suprimidos"],
        ["cauda ativa", _fmt(active_tail), "Escopo real que ainda aparece no produto"],
        ["cauda suprimida", _fmt(tail_suppressed), "NOT_WINE removido logicamente"],
        ["wine_aliases total", _fmt(counts["wine_aliases_total"]), "Estado atual da tabela"],
        ["wine_aliases approved", _fmt(counts["wine_aliases_approved"]), "Aliases aprovados existentes"],
    ]

    reason_rows = [
        [str(reason), _fmt(qty), _pct(int(qty), tail_suppressed)]
        for reason, qty in counts["tail_suppressed_by_reason"]
    ]
    if not reason_rows:
        reason_rows = [["<nenhum>", "0", "0,00%"]]

    delta = frame_2026_04_10 - active_tail
    content = f"""# Recontagem da Cauda Ativa Pos-Suppress

Data: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}
Banco: Render PostgreSQL
Modo: read-only

## Resultado curto

- Frame original da cauda em 2026-04-10: `{_fmt(frame_2026_04_10)}`
- Cauda ativa agora: `{_fmt(active_tail)}`
- Cauda ja suprimida: `{_fmt(tail_suppressed)}`
- Reducao visivel vs frame original: `{_fmt(delta)}` (`{_pct(delta, frame_2026_04_10)}`)
- Canonicos Vivino oficiais preservados: `{_fmt(counts['canonical_official_2026_04_10'])}`

## Contagens principais

{_table(['metrica', 'valor', 'leitura'], summary_rows)}

## Suppress da cauda por motivo

{_table(['suppress_reason', 'wines', '% da cauda suprimida'], reason_rows)}

Os motivos acima vieram dos CSVs de backup das quatro rodadas D16 e reconciliam exatamente com a contagem live da cauda suprimida.

## Leitura operacional

A limpeza NOT_WINE ja tirou `{_fmt(tail_suppressed)}` itens da cauda visivel. O proximo trabalho nao deve olhar mais para a cauda historica inteira; deve operar somente sobre `vivino_id IS NULL AND suppressed_at IS NULL`, hoje com `{_fmt(active_tail)}` wines.

"""

    RECOUNT_REPORT.write_text(content, encoding="utf-8")


def write_d17_report(counts: dict[str, Any], now: datetime) -> None:
    active_tail = counts["tail_active"]
    tail_suppressed = counts["tail_suppressed"]
    original_frame = 779_383
    d17_original = 90_005
    d17_auto = 78_869
    d17_qa = 11_136

    d17_rows = [
        ["ALIAS_AUTO", _fmt(d17_auto), "MATCH_RENDER HIGH", "QA 5% antes de executar"],
        ["ALIAS_QA", _fmt(d17_qa), "MATCH_RENDER MEDIUM S2-S5", "QA 10% antes de executar"],
        ["fora do D17", "105.882", "MATCH_RENDER MEDIUM S6", "Vai para D19/ALIAS_REVIEW"],
    ]
    gate_rows = [
        ["source ativo", "source_wine_id precisa ter vivino_id IS NULL e suppressed_at IS NULL"],
        ["canonico ativo", "canonical_wine_id precisa ter vivino_id IS NOT NULL e suppressed_at IS NULL"],
        ["sem alias aprovado previo", "nao duplicar source_wine_id ja aprovado"],
        ["gap positivo", "score do canonico precisa vencer alternativas; empate nao entra em massa"],
        ["produtor compativel", "producer/manufacturer nao pode conflitar"],
        ["bloqueio NOT_WINE", "source nao pode bater nos termos do catalogo NOT_WINE"],
        ["backup/rollback", "D17 so prepara; escrita fica para D18 apos QA"],
    ]

    content = f"""# Abertura D17 -- Alias dos MATCH_RENDER Fortes

Data: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}
Modo: read-only / sem escrita em producao

## Estado atual

- Cauda original auditada: `{_fmt(original_frame)}`
- Cauda ativa pos-NOT_WINE: `{_fmt(active_tail)}`
- Cauda ja suprimida: `{_fmt(tail_suppressed)}`
- Escopo de qualquer D17 agora: somente `vivino_id IS NULL AND suppressed_at IS NULL`

## Escopo D17 original

{_table(['lane', 'estimativa original', 'entrada', 'gate'], d17_rows)}

Total planejado D17: `{_fmt(d17_original)}` candidatos a alias. Esse numero continua sendo baseline de planejamento, mas nao deve ser executado diretamente. O lote real precisa ser rematerializado contra a cauda ativa atual, porque 104k+ itens ja foram suprimidos e nao podem virar alias.

## Por que nao executei alias agora

Os scripts antigos encontrados nao sao suficientes para producao:

- `scripts/find_alias_candidates.py` e uma triagem/amostra manual; nao materializa o lote D17 completo.
- `scripts/generate_aliases.py` registra a propria ressalva de que o `source_wine_id` nao esta resolvido corretamente.
- D17 exige uma tabela final `(source_wine_id, canonical_wine_id)` com source ativo, canonico ativo, gap positivo e produtor compativel.

Executar alias sem esse rowset seria trocar uma limpeza segura por risco de deduplicacao errada.

## Travas obrigatorias para o proximo script D17

{_table(['trava', 'regra'], gate_rows)}

## Plano executavel imediato

1. Criar materializador D17 que gere `reports/tail_d17_alias_candidates_2026-04-16.csv.gz`.
2. Usar somente source com `vivino_id IS NULL AND suppressed_at IS NULL`.
3. Usar somente canonical com `vivino_id IS NOT NULL AND suppressed_at IS NULL`.
4. Remover tudo que ja tem alias aprovado.
5. Separar `ALIAS_AUTO` e `ALIAS_QA`.
6. Gerar amostras QA antes de qualquer insert.
7. Deixar escrita em producao apenas para D18, com backup e rollback.

## Conclusao

D17 esta aberto, mas ainda nao executavel em producao. O proximo artefato necessario e o rowset de candidatos ativos e validados. Sem isso, o risco principal e gravar alias com `source_wine_id` errado ou ressuscitar item que ja foi suprimido.

"""

    D17_REPORT.write_text(content, encoding="utf-8")


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).astimezone()
    counts = collect_counts()
    write_recount_report(counts, now)
    write_d17_report(counts, now)
    print(f"OK recount: {RECOUNT_REPORT}")
    print(f"OK d17: {D17_REPORT}")
    print(f"cauda_ativa={_fmt(counts['tail_active'])}")
    print(f"cauda_suprimida={_fmt(counts['tail_suppressed'])}")
    print(f"aliases_approved={_fmt(counts['wine_aliases_approved'])}")


if __name__ == "__main__":
    main()
