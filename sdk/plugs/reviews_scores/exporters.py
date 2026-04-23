from __future__ import annotations

import hashlib
import os
from typing import Any

import psycopg2

from sdk.plugs.common import load_repo_envs, sha256_text
from .confidence import confidence as _confidence
from .schemas import ExportBundle, SIGNAL_KIND_BY_SOURCE


def _normalized_100(value: float | None, scale: int | None) -> float | None:
    if value is None or scale is None:
        return None
    if scale == 100:
        return round(float(value), 2)
    if scale == 5:
        return round(float(value) * 20.0, 2)
    return None


def _canonical_match_key(
    nome: str | None,
    produtor: str | None,
    safra: str | None,
    pais: str | None,
) -> str:
    parts = [
        (nome or "").strip().lower(),
        (produtor or "").strip().lower(),
        str(safra or "").strip().lower(),
        (pais or "").strip().lower(),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _decorate(
    item: dict[str, Any],
    *,
    source: str,
    review_text_present: bool,
    freshness_at: Any = None,
    source_confidence: float | None = None,
    market_price_signal: float | None = None,
) -> dict[str, Any]:
    identity = item.get("wine_identity") or {}
    score = item.get("score") or {}
    value = score.get("value")
    scale = score.get("scale")
    item["signal_kind"] = SIGNAL_KIND_BY_SOURCE.get(source, source)
    if value is not None:
        item["score_normalized_100"] = _normalized_100(value, scale)
    item["review_text_present"] = bool(review_text_present)
    if freshness_at is not None:
        item["review_freshness_at"] = (
            freshness_at.isoformat() if hasattr(freshness_at, "isoformat") else str(freshness_at)
        )
    item["canonical_match_key"] = _canonical_match_key(
        identity.get("nome"),
        identity.get("produtor"),
        identity.get("safra"),
        identity.get("pais"),
    )
    if source_confidence is not None:
        item["source_confidence"] = round(float(source_confidence), 3)
    if market_price_signal is not None:
        item["market_price_signal"] = float(market_price_signal)
    return item


def _fetch(dsn: str, sql: str, params: tuple) -> list[tuple]:
    conn = psycopg2.connect(dsn, connect_timeout=10)
    try:
        conn.set_session(readonly=True, autocommit=True)
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout TO 45000")
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


def export_vivino_wines_to_ratings(
    limit: int,
    *,
    mode: str = "incremental_recent",
    after_id: int = 0,
) -> ExportBundle:
    """Agregados pre-calculados por vinho direto de vivino_vinhos.

    Alimenta:
      - wine_scores(fonte='vivino', score=rating_medio*20, confianca, dados_extra)
      - wines.vivino_rating, wines.vivino_reviews

    Modos:
      - `incremental_recent` (default): ORDER BY atualizado_em DESC LIMIT N.
        Sempre captura o topo mais recentemente atualizado. Bom para sync
        continuo. NAO varre a base sozinho.
      - `backfill_windowed`: WHERE id > after_id ORDER BY id ASC LIMIT N.
        Progresso real; o runner persiste o maior id retornado como
        proximo `after_id` no checkpoint.
    """
    dsn = os.environ.get("VIVINO_DATABASE_URL")
    source = "vivino_wines_to_ratings"
    if not dsn:
        return ExportBundle(source=source, notes=["VIVINO_DATABASE_URL ausente"])
    if mode == "backfill_windowed":
        sql = """
            SELECT
                id, nome, vinicola_nome, safra, pais_codigo, regiao_nome,
                rating_medio, total_ratings, reviews_atualizado_em, atualizado_em,
                url_vivino
            FROM public.vivino_vinhos
            WHERE rating_medio IS NOT NULL AND total_ratings IS NOT NULL
              AND id > %s
            ORDER BY id ASC
            LIMIT %s
        """
        params: tuple = (int(after_id), limit)
    else:
        sql = """
            SELECT
                id, nome, vinicola_nome, safra, pais_codigo, regiao_nome,
                rating_medio, total_ratings, reviews_atualizado_em, atualizado_em,
                url_vivino
            FROM public.vivino_vinhos
            WHERE rating_medio IS NOT NULL AND total_ratings IS NOT NULL
            ORDER BY atualizado_em DESC NULLS LAST, id DESC
            LIMIT %s
        """
        params = (limit,)
    rows = _fetch(dsn, sql, params)
    items: list[dict[str, Any]] = []
    for row in rows:
        vivino_id, nome, produtor, safra, pais, regiao, rating, total, reviews_at, atualizado_em, url = row
        total_int = int(total) if total is not None else 0
        confidence = _confidence(total_int)
        rating_float = float(rating) if rating is not None else None
        item: dict[str, Any] = {
            "source": source,
            "wine_identity": {
                "vivino_id": int(vivino_id),
                "nome": nome,
                "produtor": produtor,
                "safra": str(safra) if safra else None,
                "pais": (pais or "").lower() or None,
                "regiao": regiao,
            },
            "score": {"value": rating_float, "scale": 5},
            "review": {
                "sample_size": total_int,
                "reviews_updated_at": reviews_at.isoformat() if reviews_at else None,
                "vivino_url": url,
            },
            "reviewer_ref": None,
            "source_lineage": {
                "source_system": "vivino_db",
                "source_kind": "table",
                "source_pointer": "vivino_vinhos",
                "source_record_count": 1,
            },
        }
        _decorate(
            item,
            source=source,
            review_text_present=False,
            freshness_at=reviews_at or atualizado_em,
            source_confidence=confidence,
        )
        items.append(item)
    max_id = max((int(r[0]) for r in rows), default=int(after_id))
    return ExportBundle(
        source=source,
        items=items,
        notes=[f"items_exported={len(items)}", f"mode={mode}", f"max_id={max_id}"],
    )


def export_vivino_reviews(limit: int) -> ExportBundle:
    dsn = os.environ.get("VIVINO_DATABASE_URL")
    source = "vivino_reviews_to_scores_reviews"
    if not dsn:
        return ExportBundle(source=source, notes=["VIVINO_DATABASE_URL ausente"])
    rows = _fetch(
        dsn,
        """
        WITH recent_reviews AS (
          SELECT id, vinho_id, rating, nota_texto, idioma, usuario_id, criado_em
          FROM public.vivino_reviews
          ORDER BY id DESC
          LIMIT %s
        )
        SELECT
          r.id, r.vinho_id, r.rating, r.nota_texto, r.idioma, r.usuario_id, r.criado_em,
          v.nome, v.vinicola_nome, v.safra, v.pais_codigo, v.regiao_nome
        FROM recent_reviews r
        JOIN public.vivino_vinhos v ON v.id = r.vinho_id
        ORDER BY r.id DESC
        """,
        (limit,),
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        review_text = row[3] or ""
        review_hash = sha256_text(review_text)
        item: dict[str, Any] = {
            "source": source,
            "wine_identity": {
                "vivino_id": row[1],
                "nome": row[7],
                "produtor": row[8],
                "safra": str(row[9]) if row[9] else None,
                "pais": (row[10] or "").lower() or None,
                "regiao": row[11],
            },
            "score": {"value": float(row[2]) if row[2] is not None else None, "scale": 5},
            "review": {
                "review_id": row[0],
                "review_text_hash": review_hash,
                "language": row[4],
                "created_at": row[6].isoformat() if row[6] else None,
            },
            "reviewer_ref": {"reviewer_id": row[5], "reviewer_hash": sha256_text(str(row[5]))},
            "source_lineage": {
                "source_system": "vivino_db",
                "source_pointer": "vivino_reviews+vivino_vinhos",
                "source_record_count": 1,
            },
        }
        _decorate(
            item,
            source=source,
            review_text_present=bool(review_text.strip()),
            freshness_at=row[6],
        )
        items.append(item)
    return ExportBundle(source=source, items=items, notes=[f"items_exported={len(items)}"])


def export_cellartracker(limit: int) -> ExportBundle:
    dsn = os.environ.get("WINEGOD_DATABASE_URL")
    source = "cellartracker_to_scores_reviews"
    if not dsn:
        return ExportBundle(source=source, notes=["WINEGOD_DATABASE_URL ausente"])
    rows = _fetch(
        dsn,
        """
        SELECT id, nome, produtor, safra, pais, regiao, ct_score, ct_drink_window,
               ct_flavor_summary, atualizado_em
        FROM public.ct_vinhos
        ORDER BY atualizado_em DESC NULLS LAST, id DESC
        LIMIT %s
        """,
        (limit,),
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        flavor_text = row[8] or ""
        item = {
            "source": source,
            "wine_identity": {
                "source_wine_id": row[0],
                "nome": row[1],
                "produtor": row[2],
                "safra": str(row[3]) if row[3] else None,
                "pais": (row[4] or "").lower() or None,
                "regiao": row[5],
            },
            "score": {"value": float(row[6]) if row[6] is not None else None, "scale": 100},
            "review": {"drink_window": row[7], "flavor_summary_hash": sha256_text(flavor_text)},
            "reviewer_ref": {"source": "cellartracker"},
            "source_lineage": {
                "source_system": "winegod_db",
                "source_pointer": "ct_vinhos",
                "source_record_count": 1,
            },
        }
        _decorate(
            item,
            source=source,
            review_text_present=bool(flavor_text.strip()),
            freshness_at=row[9],
        )
        items.append(item)
    return ExportBundle(source=source, items=items, notes=[f"items_exported={len(items)}"])


def export_decanter(limit: int) -> ExportBundle:
    dsn = os.environ.get("WINEGOD_DATABASE_URL")
    source = "decanter_to_critic_scores"
    if not dsn:
        return ExportBundle(source=source, notes=["WINEGOD_DATABASE_URL ausente"])
    rows = _fetch(
        dsn,
        """
        SELECT id, nome, produtor_normalizado, safra, pais, regiao, decanter_score,
               decanter_reviewer, decanter_review, decanter_uri, atualizado_em
        FROM public.decanter_vinhos
        ORDER BY atualizado_em DESC NULLS LAST, id DESC
        LIMIT %s
        """,
        (limit,),
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        review_text = row[8] or ""
        item = {
            "source": source,
            "wine_identity": {
                "source_wine_id": row[0],
                "nome": row[1],
                "produtor": row[2],
                "safra": str(row[3]) if row[3] else None,
                "pais": (row[4] or "").lower() or None,
                "regiao": row[5],
            },
            "score": {"value": float(row[6]) if row[6] is not None else None, "scale": 100},
            "review": {"review_text_hash": sha256_text(review_text), "reference_uri": row[9]},
            "reviewer_ref": {"critic_name": row[7]},
            "source_lineage": {
                "source_system": "winegod_db",
                "source_pointer": "decanter_vinhos",
                "source_record_count": 1,
            },
        }
        _decorate(
            item,
            source=source,
            review_text_present=bool(review_text.strip()),
            freshness_at=row[10],
        )
        items.append(item)
    return ExportBundle(source=source, items=items, notes=[f"items_exported={len(items)}"])


def export_wine_enthusiast(limit: int) -> ExportBundle:
    dsn = os.environ.get("WINEGOD_DATABASE_URL")
    source = "wine_enthusiast_to_critic_scores"
    if not dsn:
        return ExportBundle(source=source, notes=["WINEGOD_DATABASE_URL ausente"])
    rows = _fetch(
        dsn,
        """
        SELECT id, nome, produtor_normalizado, safra, pais, regiao, we_score,
               we_reviewer, we_category, atualizado_em
        FROM public.we_vinhos
        ORDER BY atualizado_em DESC NULLS LAST, id DESC
        LIMIT %s
        """,
        (limit,),
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        item = {
            "source": source,
            "wine_identity": {
                "source_wine_id": row[0],
                "nome": row[1],
                "produtor": row[2],
                "safra": str(row[3]) if row[3] else None,
                "pais": (row[4] or "").lower() or None,
                "regiao": row[5],
            },
            "score": {"value": float(row[6]) if row[6] is not None else None, "scale": 100},
            "reviewer_ref": {"critic_name": row[7]},
            "review": {"category": row[8]},
            "source_lineage": {
                "source_system": "winegod_db",
                "source_pointer": "we_vinhos",
                "source_record_count": 1,
            },
        }
        _decorate(
            item,
            source=source,
            review_text_present=False,
            freshness_at=row[9],
        )
        items.append(item)
    return ExportBundle(source=source, items=items, notes=[f"items_exported={len(items)}"])


def export_winesearcher(limit: int) -> ExportBundle:
    dsn = os.environ.get("WINEGOD_DATABASE_URL")
    source = "winesearcher_to_market_signals"
    if not dsn:
        return ExportBundle(source=source, notes=["WINEGOD_DATABASE_URL ausente"])
    rows = _fetch(
        dsn,
        """
        SELECT id, nome, produtor_normalizado, safra, pais, regiao, ws_critic_score,
               ws_critic_name, ws_avg_price_usd, atualizado_em
        FROM public.ws_vinhos
        ORDER BY atualizado_em DESC NULLS LAST, id DESC
        LIMIT %s
        """,
        (limit,),
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        avg_price = float(row[8]) if row[8] is not None else None
        item = {
            "source": source,
            "wine_identity": {
                "source_wine_id": row[0],
                "nome": row[1],
                "produtor": row[2],
                "safra": str(row[3]) if row[3] else None,
                "pais": (row[4] or "").lower() or None,
                "regiao": row[5],
            },
            "score": {"value": float(row[6]) if row[6] is not None else None, "scale": 100},
            "reviewer_ref": {"critic_name": row[7]},
            "review": {"avg_price_usd": avg_price},
            "source_lineage": {
                "source_system": "winegod_db",
                "source_pointer": "ws_vinhos",
                "source_record_count": 1,
            },
        }
        _decorate(
            item,
            source=source,
            review_text_present=False,
            freshness_at=row[9],
            market_price_signal=avg_price,
        )
        items.append(item)
    return ExportBundle(source=source, items=items, notes=[f"items_exported={len(items)}"])


EXPORTERS = {
    "vivino_wines_to_ratings": export_vivino_wines_to_ratings,
    "vivino_reviews_to_scores_reviews": export_vivino_reviews,
    "cellartracker_to_scores_reviews": export_cellartracker,
    "decanter_to_critic_scores": export_decanter,
    "wine_enthusiast_to_critic_scores": export_wine_enthusiast,
    "winesearcher_to_market_signals": export_winesearcher,
}


load_repo_envs()
