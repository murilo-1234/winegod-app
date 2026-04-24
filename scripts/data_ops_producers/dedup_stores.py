"""Dedup cross-check em public.stores - dry-run por default.

Le `public.stores` em batches de 10k (REGRA 5), canonicaliza dominios,
agrupa por dominio canonico, detecta duplicatas exatas e provaveis,
e grava relatorio em reports/data_ops_dedup/.

Apply NAO implementado nesta sessao. `--apply` e bloqueado duramente:
exige DEDUP_STORES_AUTHORIZED=1 e ainda assim este script nao commita.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from sdk.plugs.common import load_repo_envs, normalize_domain  # noqa: E402


DEDUP_ROOT = REPO_ROOT / "reports" / "data_ops_dedup"
AUTH_ENV = "DEDUP_STORES_AUTHORIZED"
DEFAULT_BATCH_SIZE = 10_000
SIMILARITY_THRESHOLD = 0.9
_PORT_RE = re.compile(r":(80|443)$")


def canonicalize_domain(raw: str | None) -> str | None:
    """Canonicaliza dominio: lowercase, remove www., porta default, remove path/query.

    Tambem normaliza sufixos `.com.br` / `.co.uk` implicitamente via
    `normalize_domain` do common.
    """
    if not raw:
        return None
    norm = normalize_domain(raw)
    if not norm:
        return None
    norm = _PORT_RE.sub("", norm)
    return norm.lower().rstrip(".")


@dataclass
class StoreRow:
    id: int
    dominio: str | None
    url: str | None
    canonical: str | None


@dataclass
class DuplicateGroup:
    canonical: str
    ids: list[int]
    canonical_id: int
    alias_ids: list[int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical": self.canonical,
            "canonical_id": self.canonical_id,
            "alias_ids": list(self.alias_ids),
        }


@dataclass
class SimilarityHit:
    a: str
    b: str
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {"a": self.a, "b": self.b, "score": round(self.score, 3)}


@dataclass
class DedupReport:
    generated_at_utc: str
    total_rows: int
    rows_without_domain: int
    unique_canonical: int
    exact_duplicate_groups: list[DuplicateGroup] = field(default_factory=list)
    similarity_hits: list[SimilarityHit] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [
            "# Stores Dedup Report",
            "",
            f"- generated_at_utc: `{self.generated_at_utc}`",
            f"- total_rows: `{self.total_rows}`",
            f"- rows_without_domain: `{self.rows_without_domain}`",
            f"- unique_canonical: `{self.unique_canonical}`",
            f"- exact_duplicate_groups: `{len(self.exact_duplicate_groups)}`",
            f"- similarity_hits: `{len(self.similarity_hits)}`",
            "",
            "## Exact duplicates (first 20)",
        ]
        for grp in self.exact_duplicate_groups[:20]:
            lines.append(
                f"- `{grp.canonical}` canonical_id=`{grp.canonical_id}` "
                f"aliases=`{grp.alias_ids}`"
            )
        lines.append("")
        lines.append("## Similarity hits (first 20)")
        for hit in self.similarity_hits[:20]:
            lines.append(
                f"- `{hit.a}` <-> `{hit.b}` score=`{hit.score:.3f}`"
            )
        return "\n".join(lines) + "\n"


def iter_store_rows(conn, *, batch_size: int = DEFAULT_BATCH_SIZE) -> Iterable[StoreRow]:
    with conn.cursor(name="dedup_stores_cursor") as cur:
        cur.itersize = batch_size
        cur.execute("SELECT id, dominio, url FROM public.stores ORDER BY id")
        for row in cur:
            yield StoreRow(
                id=int(row[0]),
                dominio=row[1],
                url=row[2],
                canonical=canonicalize_domain(row[1] or row[2]),
            )


def group_exact_duplicates(rows: list[StoreRow]) -> list[DuplicateGroup]:
    groups: dict[str, list[StoreRow]] = defaultdict(list)
    for row in rows:
        if row.canonical:
            groups[row.canonical].append(row)
    result: list[DuplicateGroup] = []
    for canonical, members in groups.items():
        if len(members) < 2:
            continue
        members.sort(key=lambda r: r.id)
        result.append(
            DuplicateGroup(
                canonical=canonical,
                ids=[m.id for m in members],
                canonical_id=members[0].id,
                alias_ids=[m.id for m in members[1:]],
            )
        )
    result.sort(key=lambda g: g.canonical)
    return result


def detect_similarity_hits(
    canonicals: list[str], *, threshold: float = SIMILARITY_THRESHOLD
) -> list[SimilarityHit]:
    hits: list[SimilarityHit] = []
    buckets: dict[str, list[str]] = defaultdict(list)
    for canon in canonicals:
        parts = canon.split(".")
        key = parts[-2] if len(parts) >= 2 else canon
        buckets[key].append(canon)
    seen: set[tuple[str, str]] = set()
    for _, group in buckets.items():
        if len(group) < 2:
            continue
        items = sorted(set(group))
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = items[i], items[j]
                if a == b:
                    continue
                score = SequenceMatcher(None, a, b).ratio()
                if score >= threshold:
                    key = (a, b)
                    if key in seen:
                        continue
                    seen.add(key)
                    hits.append(SimilarityHit(a=a, b=b, score=score))
    hits.sort(key=lambda h: -h.score)
    return hits


def build_report(rows: list[StoreRow]) -> DedupReport:
    without = sum(1 for r in rows if not r.canonical)
    canonicals = sorted({r.canonical for r in rows if r.canonical})
    exact = group_exact_duplicates(rows)
    hits = detect_similarity_hits(canonicals)
    return DedupReport(
        generated_at_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        total_rows=len(rows),
        rows_without_domain=without,
        unique_canonical=len(canonicals),
        exact_duplicate_groups=exact,
        similarity_hits=hits,
    )


def persist_report(report: DedupReport, *, timestamp: str | None = None) -> tuple[Path, Path]:
    DEDUP_ROOT.mkdir(parents=True, exist_ok=True)
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    md_path = DEDUP_ROOT / f"stores_dedup_{ts}.md"
    json_path = DEDUP_ROOT / f"stores_dedup_{ts}.json"
    md_path.write_text(report.to_markdown(), encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "generated_at_utc": report.generated_at_utc,
                "total_rows": report.total_rows,
                "rows_without_domain": report.rows_without_domain,
                "unique_canonical": report.unique_canonical,
                "exact_duplicate_groups": [g.to_dict() for g in report.exact_duplicate_groups],
                "similarity_hits": [h.to_dict() for h in report.similarity_hits],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return md_path, json_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Dedup stores (dry-run por default)")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--plan-only", action="store_true", default=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=None,
                        help="opcional: processar apenas N linhas (para debug)")
    args = parser.parse_args()

    if args.batch_size <= 0 or args.batch_size > DEFAULT_BATCH_SIZE:
        parser.error(f"--batch-size must be in (0, {DEFAULT_BATCH_SIZE}] (REGRA 5)")
    if args.apply and os.environ.get(AUTH_ENV) != "1":
        parser.error(f"--apply requires env {AUTH_ENV}=1")
    if args.apply:
        parser.error(
            "[dedup_stores] --apply disabled in this session (REGRA 1). "
            "Use the plan-only report and approve a merge script manually."
        )

    load_repo_envs()
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        parser.error("DATABASE_URL ausente - nao e possivel inspecionar public.stores")

    import psycopg2

    rows: list[StoreRow] = []
    conn = psycopg2.connect(dsn, connect_timeout=15)
    try:
        conn.set_session(readonly=True, autocommit=False)
        count = 0
        for row in iter_store_rows(conn, batch_size=args.batch_size):
            rows.append(row)
            count += 1
            if args.limit and count >= args.limit:
                break
    finally:
        conn.close()

    report = build_report(rows)
    md_path, json_path = persist_report(report)
    print(
        f"[dedup_stores] md={md_path}\n"
        f"[dedup_stores] json={json_path}\n"
        f"[dedup_stores] total={report.total_rows} unique={report.unique_canonical} "
        f"exact_groups={len(report.exact_duplicate_groups)} similarity_hits={len(report.similarity_hits)}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
