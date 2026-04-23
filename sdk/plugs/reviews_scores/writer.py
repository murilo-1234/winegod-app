"""Writer de sinais derivados para o banco principal WineGod.

Responsabilidades:
  - Resolver wine_id para cada item do ExportBundle.
  - UPSERT em public.wine_scores (chave unica wine_id+fonte).
  - UPDATE incremental em public.wines.vivino_rating/vivino_reviews quando a
    fonte for `vivino_wines_to_ratings` (isto aciona trigger fn_enqueue_score_recalc
    que reenqueue o vinho para recalculo de winegod_score).

Regras:
  - NAO persiste texto bruto de review nem PII. Textos ja vem como hash.
  - Batches de 10_000 por transacao ATOMICA (REGRA 5 - Render sensivel).
    wine_scores + wines do mesmo lote sobem na mesma transacao; rollback
    fecha os dois em caso de falha.
  - Idempotencia forte: re-run com mesmo input produz ZERO mudanca de linha
    (ON CONFLICT DO UPDATE tem WHERE IS DISTINCT FROM; criado_em nao e
    mutado; wines UPDATE ja guardava por IS DISTINCT FROM).
  - Per-review source (`vivino_reviews_to_scores_reviews`) nao grava em wine_scores.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import psycopg2
from psycopg2.extras import Json, execute_values

from .schemas import (
    PER_REVIEW_SOURCES,
    SIGNAL_KIND_BY_SOURCE,
    SOURCES_THAT_UPDATE_WINES,
)


DEFAULT_BATCH_SIZE = 10_000
# wine_scores.score = numeric(4,2) => 99.99 max; wines.vivino_rating = numeric(3,2) => 9.99 max.
WINE_SCORES_SCORE_MAX = 99.99
VIVINO_RATING_MAX = 9.99


@dataclass
class WriterResult:
    source: str
    processed: int = 0
    matched: int = 0
    unmatched: int = 0
    wine_scores_upserted: int = 0
    wine_scores_changed: int = 0
    wines_rating_updated: int = 0
    skipped_per_review: int = 0
    skipped_no_score: int = 0
    batches_committed: int = 0
    errors: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "processed": self.processed,
            "matched": self.matched,
            "unmatched": self.unmatched,
            "wine_scores_upserted": self.wine_scores_upserted,
            "wine_scores_changed": self.wine_scores_changed,
            "wines_rating_updated": self.wines_rating_updated,
            "skipped_per_review": self.skipped_per_review,
            "skipped_no_score": self.skipped_no_score,
            "batches_committed": self.batches_committed,
            "errors": self.errors[:10],
        }


def _clamp(value: float | None, max_value: float) -> float | None:
    if value is None:
        return None
    v = float(value)
    if v > max_value:
        return max_value
    if v < 0:
        return 0.0
    return round(v, 2)


def _resolve_vivino_wine_ids(cur, vivino_ids: list[int]) -> dict[int, int]:
    if not vivino_ids:
        return {}
    lookup: dict[int, int] = {}
    step = 5_000
    for i in range(0, len(vivino_ids), step):
        chunk = vivino_ids[i : i + step]
        cur.execute(
            "SELECT vivino_id, id FROM public.wines WHERE vivino_id = ANY(%s)",
            (chunk,),
        )
        for vivino_id, wine_id in cur.fetchall():
            if vivino_id is not None:
                lookup[int(vivino_id)] = int(wine_id)
    return lookup


def _prepare_wine_scores_rows(
    items: list[dict[str, Any]],
    lookup: dict[int, int],
) -> tuple[list[tuple], int, int]:
    rows: list[tuple] = []
    unmatched = 0
    skipped_no_score = 0
    for item in items:
        source = item.get("source", "")
        fonte = SIGNAL_KIND_BY_SOURCE.get(source, source)
        identity = item.get("wine_identity") or {}
        vivino_id = identity.get("vivino_id")
        if vivino_id is None:
            unmatched += 1
            continue
        wine_id = lookup.get(int(vivino_id))
        if wine_id is None:
            unmatched += 1
            continue
        score = item.get("score") or {}
        score_value = _clamp(score.get("value"), WINE_SCORES_SCORE_MAX)
        normalized_100 = item.get("score_normalized_100")
        final_score = normalized_100 if normalized_100 is not None else score_value
        if final_score is None:
            skipped_no_score += 1
            continue
        confianca = item.get("source_confidence")
        dados_extra = {
            "scale_original": score.get("scale"),
            "score_original": score.get("value"),
            "sample_size": (item.get("review") or {}).get("sample_size"),
            "review_freshness_at": item.get("review_freshness_at"),
            "canonical_match_key": item.get("canonical_match_key"),
            "market_price_signal": item.get("market_price_signal"),
            "reviewer_ref": item.get("reviewer_ref"),
            "source_lineage": item.get("source_lineage"),
            "signal_kind": item.get("signal_kind"),
            "review_text_present": item.get("review_text_present"),
        }
        dados_extra = {k: v for k, v in dados_extra.items() if v is not None}
        rows.append(
            (
                int(wine_id),
                fonte,
                _clamp(final_score, WINE_SCORES_SCORE_MAX),
                (score.get("value") if score.get("value") is not None else None),
                round(float(confianca), 2) if confianca is not None else None,
                Json(dados_extra),
            )
        )
    return rows, unmatched, skipped_no_score


def _prepare_wines_updates(
    items: list[dict[str, Any]],
    lookup: dict[int, int],
) -> list[tuple]:
    rows: list[tuple] = []
    for item in items:
        identity = item.get("wine_identity") or {}
        vivino_id = identity.get("vivino_id")
        if vivino_id is None:
            continue
        wine_id = lookup.get(int(vivino_id))
        if wine_id is None:
            continue
        score = item.get("score") or {}
        rating = _clamp(score.get("value"), VIVINO_RATING_MAX)
        sample = (item.get("review") or {}).get("sample_size")
        if rating is None and sample is None:
            continue
        rows.append(
            (
                rating,
                int(sample) if sample is not None else None,
                int(wine_id),
            )
        )
    return rows


# Idempotencia forte:
#   - criado_em NAO e tocado (mantem o timestamp do primeiro insert);
#   - UPDATE so roda quando ha diferenca real em qualquer campo relevante;
#   - o `WHERE` dentro do DO UPDATE usa a linha corrente da tabela (wine_scores)
#     e a candidata (EXCLUDED).
_UPSERT_WINE_SCORES_SQL = """
INSERT INTO public.wine_scores (wine_id, fonte, score, score_raw, confianca, dados_extra)
VALUES %s
ON CONFLICT (wine_id, fonte) DO UPDATE
SET score = EXCLUDED.score,
    score_raw = EXCLUDED.score_raw,
    confianca = EXCLUDED.confianca,
    dados_extra = EXCLUDED.dados_extra
WHERE wine_scores.score IS DISTINCT FROM EXCLUDED.score
   OR wine_scores.score_raw IS DISTINCT FROM EXCLUDED.score_raw
   OR wine_scores.confianca IS DISTINCT FROM EXCLUDED.confianca
   OR wine_scores.dados_extra IS DISTINCT FROM EXCLUDED.dados_extra
"""


_UPDATE_WINES_SQL = """
UPDATE public.wines w
SET vivino_rating = b.rating,
    vivino_reviews = b.sample_size,
    atualizado_em = NOW()
FROM (VALUES %s) AS b(rating, sample_size, wine_id)
WHERE w.id = b.wine_id
  AND (
    w.vivino_rating IS DISTINCT FROM b.rating
    OR w.vivino_reviews IS DISTINCT FROM b.sample_size
  )
"""


def apply_bundle(
    items: list[dict[str, Any]],
    *,
    source: str,
    dsn: str | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> WriterResult:
    """Aplica um lote ja exportado no banco WineGod.

    - Atomico por lote: para cada janela de `batch_size`, a UPSERT em
      wine_scores e o UPDATE em wines sobem na mesma transacao.
    - Idempotencia forte: re-run identico produz zero rowcount.
    """
    result = WriterResult(source=source)
    result.processed = len(items)
    if source in PER_REVIEW_SOURCES:
        result.skipped_per_review = len(items)
        return result
    if not items:
        return result
    dsn = dsn or os.environ.get("DATABASE_URL")
    if not dsn:
        result.errors.append("DATABASE_URL ausente")
        return result

    vivino_ids = []
    for item in items:
        vid = ((item.get("wine_identity") or {}).get("vivino_id"))
        if vid is not None:
            vivino_ids.append(int(vid))
    vivino_ids = list(dict.fromkeys(vivino_ids))

    conn = psycopg2.connect(dsn, connect_timeout=15)
    conn.autocommit = False
    should_update_wines = source in SOURCES_THAT_UPDATE_WINES
    try:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout TO 120000")
            lookup = _resolve_vivino_wine_ids(cur, vivino_ids)
            conn.commit()  # fecha a transacao do lookup (readonly); lotes seguintes abrem novas
            result.matched = sum(
                1
                for item in items
                if ((item.get("wine_identity") or {}).get("vivino_id")) is not None
                and int(((item.get("wine_identity") or {}).get("vivino_id"))) in lookup
            )

            ws_rows, unmatched_ws, skipped_no_score = _prepare_wine_scores_rows(items, lookup)
            result.unmatched = unmatched_ws
            result.skipped_no_score = skipped_no_score

            wines_updates_all = (
                _prepare_wines_updates(items, lookup) if should_update_wines else []
            )
            # Indexa wines_updates por wine_id para fatiar coerente com o lote de wine_scores.
            wines_updates_by_wine: dict[int, tuple] = {row[2]: row for row in wines_updates_all}

            # Um lote atomico = N linhas de wine_scores + suas correspondencias em wines.
            for i in range(0, len(ws_rows), batch_size):
                ws_batch = ws_rows[i : i + batch_size]
                try:
                    execute_values(cur, _UPSERT_WINE_SCORES_SQL, ws_batch)
                    result.wine_scores_changed += cur.rowcount
                    result.wine_scores_upserted += len(ws_batch)

                    if should_update_wines and wines_updates_by_wine:
                        wine_ids_in_batch = {int(r[0]) for r in ws_batch}
                        wines_batch = [
                            wines_updates_by_wine[wid]
                            for wid in wine_ids_in_batch
                            if wid in wines_updates_by_wine
                        ]
                        if wines_batch:
                            execute_values(cur, _UPDATE_WINES_SQL, wines_batch)
                            result.wines_rating_updated += cur.rowcount

                    conn.commit()
                    result.batches_committed += 1
                except Exception:
                    conn.rollback()
                    raise
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        result.errors.append(f"{type(exc).__name__}: {str(exc)[:300]}")
        raise
    finally:
        conn.close()
    return result
