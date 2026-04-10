"""Enfileira recalculo de score quando campos relevantes mudam.

Uso dentro do backend (complemento ao trigger DB-level).
O trigger em wines e o mecanismo oficial; este helper serve para
pontos de codigo no winegod-app que sabem que precisam recalcular.

Usa ON CONFLICT para dedup: requer idx_recalc_pending_dedup (migration 008).
"""

from db.connection import get_connection, release_connection


def enqueue_recalc(wine_id, reason="app_request"):
    """Add wine_id to score_recalc_queue (dedup: ignora se ja pendente)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO score_recalc_queue (wine_id, reason)
                   VALUES (%s, %s)
                   ON CONFLICT (wine_id) WHERE processed_at IS NULL DO NOTHING""",
                (wine_id, reason),
            )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        release_connection(conn)


def enqueue_batch(wine_ids, reason="app_request"):
    """Enqueue multiple wine_ids (dedup per wine_id)."""
    if not wine_ids:
        return
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            from psycopg2.extras import execute_values
            execute_values(
                cur,
                """INSERT INTO score_recalc_queue (wine_id, reason) VALUES %s
                   ON CONFLICT (wine_id) WHERE processed_at IS NULL DO NOTHING""",
                [(wid, reason) for wid in wine_ids],
            )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        release_connection(conn)
