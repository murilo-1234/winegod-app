"""Modelo de compartilhamento: tabela shares + funcoes CRUD."""

import secrets
import string
from decimal import Decimal
from datetime import datetime

from db.connection import get_connection, release_connection
from services.display import enrich_wine
from utils.country_names import iso_to_name


def generate_share_id():
    """Gera ID curto (7 chars, base62: a-zA-Z0-9)."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(7))


def create_tables_share():
    """Cria tabela shares se nao existir."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS shares (
                    id VARCHAR(8) PRIMARY KEY,
                    title VARCHAR(255),
                    context TEXT,
                    wine_ids INTEGER[] NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    view_count INTEGER DEFAULT 0
                );
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_shares_created
                ON shares (created_at DESC);
            """)
        conn.commit()
    finally:
        release_connection(conn)


def create_share(title, context, wine_ids):
    """Cria compartilhamento. Retorna share_id."""
    conn = get_connection()
    try:
        share_id = generate_share_id()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO shares (id, title, context, wine_ids)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (share_id, title, context, wine_ids),
            )
            result = cur.fetchone()
        conn.commit()
        return result[0]
    finally:
        release_connection(conn)


def _convert_value(val):
    """Converte Decimal/datetime para tipos JSON-safe."""
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, datetime):
        return val.isoformat() + "Z"
    return val


def get_share(share_id):
    """Busca compartilhamento + dados dos vinhos. Retorna dict ou None."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Buscar share
            cur.execute(
                "SELECT id, title, context, wine_ids, created_at, view_count "
                "FROM shares WHERE id = %s",
                (share_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

            share = {
                "share_id": row[0],
                "title": row[1],
                "context": row[2],
                "wine_ids": row[3],
                "created_at": _convert_value(row[4]),
                "view_count": row[5],
            }

            # Buscar dados dos vinhos
            if share["wine_ids"]:
                cur.execute(
                    """
                    SELECT w.id, w.nome, w.produtor, w.safra, w.tipo,
                           w.pais_nome, w.pais, w.regiao, w.sub_regiao,
                           w.vivino_rating, w.vivino_reviews,
                           w.nota_wcf, w.winegod_score,
                           w.preco_min, w.preco_max, w.moeda,
                           w.nota_wcf_sample_size, w.confianca_nota
                    FROM wines w
                    WHERE w.id = ANY(%s)
                      AND w.suppressed_at IS NULL
                    """,
                    (share["wine_ids"],),
                )
                cols = [
                    "id", "nome", "produtor", "safra", "tipo",
                    "pais_nome", "pais", "regiao", "sub_regiao",
                    "vivino_rating", "vivino_reviews",
                    "nota_wcf", "winegod_score",
                    "preco_min", "preco_max", "moeda",
                    "nota_wcf_sample_size", "confianca_nota",
                ]
                wines = []
                for wine_row in cur.fetchall():
                    wine = {
                        cols[i]: _convert_value(wine_row[i])
                        for i in range(len(cols))
                    }
                    # Contrato de share/OG: pais_display e canonico derivado de
                    # pais (ISO). pais_nome e mantido como compat para clientes
                    # legados e ainda preenchido via fallback quando vazio.
                    pais_display = iso_to_name(wine["pais"]) if wine.get("pais") else ""
                    wine["pais_display"] = pais_display
                    if not wine.get("pais_nome") and pais_display:
                        wine["pais_nome"] = pais_display
                    enrich_wine(wine)
                    wines.append(wine)
                share["wines"] = wines
            else:
                share["wines"] = []

            del share["wine_ids"]
            return share
    finally:
        release_connection(conn)


def increment_views(share_id):
    """Incrementa view_count do compartilhamento."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE shares SET view_count = view_count + 1 WHERE id = %s",
                (share_id,),
            )
        conn.commit()
    finally:
        release_connection(conn)
