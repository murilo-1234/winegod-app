from __future__ import annotations

import os
from typing import Any

import psycopg2

from sdk.plugs.common import load_repo_envs, sha256_text
from .schemas import ExportBundle


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


def export_vivino_reviews(limit: int) -> ExportBundle:
    dsn = os.environ.get("VIVINO_DATABASE_URL")
    if not dsn:
        return ExportBundle(source="vivino_reviews_to_scores_reviews", notes=["VIVINO_DATABASE_URL ausente"])
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
        review_hash = sha256_text(row[3] or "")
        items.append(
            {
                "source": "vivino_reviews_to_scores_reviews",
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
        )
    return ExportBundle(source="vivino_reviews_to_scores_reviews", items=items, notes=[f"items_exported={len(items)}"])


def export_cellartracker(limit: int) -> ExportBundle:
    dsn = os.environ.get("WINEGOD_DATABASE_URL")
    if not dsn:
        return ExportBundle(source="cellartracker_to_scores_reviews", notes=["WINEGOD_DATABASE_URL ausente"])
    rows = _fetch(
        dsn,
        """
        SELECT id, nome, produtor, safra, pais, regiao, ct_score, ct_drink_window, ct_flavor_summary
        FROM public.ct_vinhos
        ORDER BY atualizado_em DESC NULLS LAST, id DESC
        LIMIT %s
        """,
        (limit,),
    )
    items = [
        {
            "source": "cellartracker_to_scores_reviews",
            "wine_identity": {
                "source_wine_id": row[0],
                "nome": row[1],
                "produtor": row[2],
                "safra": str(row[3]) if row[3] else None,
                "pais": (row[4] or "").lower() or None,
                "regiao": row[5],
            },
            "score": {"value": float(row[6]) if row[6] is not None else None, "scale": 100},
            "review": {"drink_window": row[7], "flavor_summary_hash": sha256_text(row[8] or "")},
            "reviewer_ref": {"source": "cellartracker"},
            "source_lineage": {
                "source_system": "winegod_db",
                "source_pointer": "ct_vinhos",
                "source_record_count": 1,
            },
        }
        for row in rows
    ]
    return ExportBundle(source="cellartracker_to_scores_reviews", items=items, notes=[f"items_exported={len(items)}"])


def export_decanter(limit: int) -> ExportBundle:
    dsn = os.environ.get("WINEGOD_DATABASE_URL")
    if not dsn:
        return ExportBundle(source="decanter_to_critic_scores", notes=["WINEGOD_DATABASE_URL ausente"])
    rows = _fetch(
        dsn,
        """
        SELECT id, nome, produtor_normalizado, safra, pais, regiao, decanter_score, decanter_reviewer, decanter_review, decanter_uri
        FROM public.decanter_vinhos
        ORDER BY atualizado_em DESC NULLS LAST, id DESC
        LIMIT %s
        """,
        (limit,),
    )
    items = [
        {
            "source": "decanter_to_critic_scores",
            "wine_identity": {
                "source_wine_id": row[0],
                "nome": row[1],
                "produtor": row[2],
                "safra": str(row[3]) if row[3] else None,
                "pais": (row[4] or "").lower() or None,
                "regiao": row[5],
            },
            "score": {"value": float(row[6]) if row[6] is not None else None, "scale": 100},
            "review": {"review_text_hash": sha256_text(row[8] or ""), "reference_uri": row[9]},
            "reviewer_ref": {"critic_name": row[7]},
            "source_lineage": {
                "source_system": "winegod_db",
                "source_pointer": "decanter_vinhos",
                "source_record_count": 1,
            },
        }
        for row in rows
    ]
    return ExportBundle(source="decanter_to_critic_scores", items=items, notes=[f"items_exported={len(items)}"])


def export_wine_enthusiast(limit: int) -> ExportBundle:
    dsn = os.environ.get("WINEGOD_DATABASE_URL")
    if not dsn:
        return ExportBundle(source="wine_enthusiast_to_critic_scores", notes=["WINEGOD_DATABASE_URL ausente"])
    rows = _fetch(
        dsn,
        """
        SELECT id, nome, produtor_normalizado, safra, pais, regiao, we_score, we_reviewer, we_category
        FROM public.we_vinhos
        ORDER BY atualizado_em DESC NULLS LAST, id DESC
        LIMIT %s
        """,
        (limit,),
    )
    items = [
        {
            "source": "wine_enthusiast_to_critic_scores",
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
        for row in rows
    ]
    return ExportBundle(source="wine_enthusiast_to_critic_scores", items=items, notes=[f"items_exported={len(items)}"])


def export_winesearcher(limit: int) -> ExportBundle:
    dsn = os.environ.get("WINEGOD_DATABASE_URL")
    if not dsn:
        return ExportBundle(source="winesearcher_to_market_signals", notes=["WINEGOD_DATABASE_URL ausente"])
    rows = _fetch(
        dsn,
        """
        SELECT id, nome, produtor_normalizado, safra, pais, regiao, ws_critic_score, ws_critic_name, ws_avg_price_usd
        FROM public.ws_vinhos
        ORDER BY atualizado_em DESC NULLS LAST, id DESC
        LIMIT %s
        """,
        (limit,),
    )
    items = [
        {
            "source": "winesearcher_to_market_signals",
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
            "review": {"avg_price_usd": float(row[8]) if row[8] is not None else None},
            "source_lineage": {
                "source_system": "winegod_db",
                "source_pointer": "ws_vinhos",
                "source_record_count": 1,
            },
        }
        for row in rows
    ]
    return ExportBundle(source="winesearcher_to_market_signals", items=items, notes=[f"items_exported={len(items)}"])


EXPORTERS = {
    "vivino_reviews_to_scores_reviews": export_vivino_reviews,
    "cellartracker_to_scores_reviews": export_cellartracker,
    "decanter_to_critic_scores": export_decanter,
    "wine_enthusiast_to_critic_scores": export_wine_enthusiast,
    "winesearcher_to_market_signals": export_winesearcher,
}


load_repo_envs()
