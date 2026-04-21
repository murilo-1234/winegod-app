"""Pipeline unico de ingestao em bulk.

Unifica os 4 caminhos historicos (chat auto_create, scraping externo,
WCF, scripts ad-hoc) em uma unica entrada:

    from services.bulk_ingest import process_bulk

    result = process_bulk(items, dry_run=True, source="wcf")

Etapas deterministicas, sem chamada a IA paga:
  1. Valida payload item por item
  2. Filtra NOT_WINE via pre_ingest_filter.should_skip_wine
  3. Normaliza nome/produtor (tools.normalize.normalizar) e resolve pais_nome
     via utils.country_names.iso_to_name (pais ISO canonico, REGRA pais/pais_nome)
  4. Gera hash_dedup (produtor_norm|nome_norm|safra)
  5. Dedup interno (mesmo hash no mesmo payload conta 1x)
  6. Dry-run: produz relatorio sem mexer no banco.
     Apply: UPSERT em batches de BULK_INGEST_BATCH_SIZE (default 10k, REGRA 5)
     com ON CONFLICT (hash_dedup) DO UPDATE merge-friendly.

Enrichment pesado (IA, Gemini) fica FORA desta camada por design — o pipeline
cuida de cadastro/dedup/filtro; a camada de scoring/enrichment e separada e
controlada pelo usuario (REGRA 6).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from db.connection import get_connection, release_connection
from tools.normalize import normalizar
from utils.country_names import iso_to_name

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from pre_ingest_filter import should_skip_wine  # noqa: E402

try:
    from config import Config
except ImportError:  # pragma: no cover
    from backend.config import Config  # type: ignore


WINE_STYLES = {"tinto", "branco", "rose", "espumante", "fortificado", "sobremesa"}

REQUIRED_FIELDS = ("nome",)
OPTIONAL_TEXT_FIELDS = (
    "produtor",
    "safra",
    "tipo",
    "pais",
    "regiao",
    "sub_regiao",
    "uvas",
    "harmonizacao",
    "descricao",
    "ean_gtin",
    "imagem_url",
    "moeda",
)
OPTIONAL_NUMERIC_FIELDS = (
    "teor_alcoolico",
    "volume_ml",
    "preco_min",
    "preco_max",
)


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "null":
        return None
    return text


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _clean_pais(value: Any) -> str | None:
    text = _clean(value)
    if not text:
        return None
    code = text.lower()
    if len(code) != 2 or not code.isalpha():
        return None
    return code


def _clean_safra(value: Any) -> str | None:
    text = _clean(value)
    if not text:
        return None
    if len(text) == 4 and text.isdigit():
        return text
    return None


def _clean_tipo(value: Any) -> str | None:
    text = _clean(value)
    if not text:
        return None
    low = text.lower()
    return low if low in WINE_STYLES else None


def _clean_uvas(value: Any) -> str | None:
    """Normaliza uvas para string JSON de lista; aceita lista, CSV ou string solta."""
    if value is None:
        return None
    if isinstance(value, list):
        parts = [str(v).strip() for v in value if str(v).strip()]
    else:
        text = str(value).strip()
        if not text:
            return None
        parts = [p.strip() for p in text.split(",") if p.strip()]
    if not parts:
        return None
    return json.dumps(parts)


def _generate_hash_dedup(nome_norm: str, produtor_norm: str, safra: str | None) -> str:
    chave = f"{produtor_norm or ''}|{nome_norm or ''}|{safra or ''}"
    return hashlib.md5(chave.encode()).hexdigest()


def _validate(item: dict) -> tuple[dict | None, str | None]:
    """Valida e normaliza um item. Retorna (payload, None) ou (None, motivo)."""
    nome = _clean(item.get("nome"))
    if not nome:
        return None, "nome_ausente"
    if len(nome) < 3:
        return None, "nome_curto"

    produtor = _clean(item.get("produtor")) or ""

    skip, reason = should_skip_wine(nome, produtor)
    if skip:
        return None, f"not_wine:{reason}"

    nome_norm = normalizar(nome)
    produtor_norm = normalizar(produtor) if produtor else ""
    safra = _clean_safra(item.get("safra"))
    pais = _clean_pais(item.get("pais"))
    pais_nome = iso_to_name(pais) if pais else None

    payload = {
        "hash_dedup": _generate_hash_dedup(nome_norm, produtor_norm, safra),
        "nome": nome,
        "nome_normalizado": nome_norm,
        "produtor": produtor or None,
        "produtor_normalizado": produtor_norm or None,
        "safra": safra,
        "tipo": _clean_tipo(item.get("tipo")),
        "pais": pais,
        "pais_nome": pais_nome,
        "regiao": _clean(item.get("regiao")),
        "sub_regiao": _clean(item.get("sub_regiao")),
        "uvas": _clean_uvas(item.get("uvas")),
        "teor_alcoolico": _to_float(item.get("teor_alcoolico")),
        "harmonizacao": _clean(item.get("harmonizacao")),
        "descricao": _clean(item.get("descricao")),
        "volume_ml": _to_float(item.get("volume_ml")),
        "ean_gtin": _clean(item.get("ean_gtin")),
        "imagem_url": _clean(item.get("imagem_url")),
        "preco_min": _to_float(item.get("preco_min")),
        "preco_max": _to_float(item.get("preco_max")),
        "moeda": _clean(item.get("moeda")),
    }
    return payload, None


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _existing_hashes_to_ids(conn, hashes: list[str]) -> dict[str, int]:
    if not hashes:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT hash_dedup, id FROM wines WHERE hash_dedup = ANY(%s)",
            (hashes,),
        )
        return {r[0]: r[1] for r in cur.fetchall()}


def _resolve_existing(conn, batch: list[dict]) -> tuple[set[str], dict[str, int]]:
    """Dedup robusto contra o legado.

    Retorna:
      - existing_hashes: conjunto de hash_dedup (do payload) que tem match.
      - hash_to_id: mapa hash_dedup -> id do wine existente, usado no apply
        para UPDATE por id em vez de INSERT ON CONFLICT (que so cobre
        conflito por hash_dedup identico).

    Considera dois caminhos:
      - match direto por hash_dedup
      - match por tripla (produtor_normalizado, nome_normalizado, safra),
        porque vinhos legados (Vivino, import_render_z) foram inseridos
        com hash gerado por outra formula e nao bateriam no lookup direto.
    """
    if not batch:
        return set(), {}

    hash_to_id = _existing_hashes_to_ids(conn, [row["hash_dedup"] for row in batch])
    existing_hashes: set[str] = set(hash_to_id.keys())

    remainder = [
        row for row in batch
        if row["hash_dedup"] not in existing_hashes
    ]
    if not remainder:
        return existing_hashes, hash_to_id

    # Dois lookups: com safra NOT NULL (IN rapido) e safra NULL (separado).
    # Retornamos o id tambem, para permitir UPDATE por id no apply.
    with_safra = [r for r in remainder if r.get("safra")]
    without_safra = [r for r in remainder if not r.get("safra")]

    tripla_to_id: dict[tuple, int] = {}

    if with_safra:
        keys = [
            (r.get("produtor_normalizado") or "",
             r.get("nome_normalizado") or "",
             r.get("safra"))
            for r in with_safra
        ]
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, produtor_normalizado, nome_normalizado, safra
                FROM wines
                WHERE (produtor_normalizado, nome_normalizado, safra) IN %s
                """,
                (tuple(keys),),
            )
            for wid, pn, nn, sf in cur.fetchall():
                tripla_to_id[(pn or "", nn or "", sf)] = wid

    if without_safra:
        keys = [
            (r.get("produtor_normalizado") or "",
             r.get("nome_normalizado") or "")
            for r in without_safra
        ]
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, produtor_normalizado, nome_normalizado
                FROM wines
                WHERE safra IS NULL
                  AND (produtor_normalizado, nome_normalizado) IN %s
                """,
                (tuple(keys),),
            )
            for wid, pn, nn in cur.fetchall():
                tripla_to_id[(pn or "", nn or "", None)] = wid

    for row in remainder:
        k = (
            row.get("produtor_normalizado") or "",
            row.get("nome_normalizado") or "",
            row.get("safra"),
        )
        if k in tripla_to_id:
            wid = tripla_to_id[k]
            existing_hashes.add(row["hash_dedup"])
            hash_to_id[row["hash_dedup"]] = wid
    return existing_hashes, hash_to_id


_INSERT_SQL = """
INSERT INTO wines (
    hash_dedup, nome, nome_normalizado, produtor, produtor_normalizado,
    safra, tipo, pais, pais_nome, regiao, sub_regiao,
    uvas, teor_alcoolico, harmonizacao, descricao,
    volume_ml, ean_gtin, imagem_url,
    preco_min, preco_max, moeda,
    total_fontes, fontes, descoberto_em, atualizado_em
) VALUES (
    %(hash_dedup)s, %(nome)s, %(nome_normalizado)s, %(produtor)s, %(produtor_normalizado)s,
    %(safra)s, %(tipo)s, %(pais)s, %(pais_nome)s, %(regiao)s, %(sub_regiao)s,
    %(uvas)s::jsonb, %(teor_alcoolico)s, %(harmonizacao)s, %(descricao)s,
    %(volume_ml)s, %(ean_gtin)s, %(imagem_url)s,
    %(preco_min)s, %(preco_max)s, %(moeda)s,
    0, %(fontes)s::jsonb, NOW(), NOW()
)
ON CONFLICT (hash_dedup) WHERE hash_dedup IS NOT NULL AND hash_dedup != ''
DO NOTHING
RETURNING id
"""
# total_fontes = 0 no INSERT porque bulk_ingest NAO cria linha em
# wine_sources. O frontend renderiza total_fontes como "loja/lojas"
# (WineCard.tsx); new_wines.py (chat auto-create) tambem insere com 0.
# `fontes` mantem a provenance textual ("bulk_ingest:<source>") mas nao
# conta como fonte comercial. Quando uma linha em wine_sources for
# efetivamente criada depois, o contador sera atualizado por aquele
# pipeline comercial, nao por aqui.

# UPDATE por id, com merge conservador:
# - nao sobrescreve campos ja preenchidos (COALESCE(wines.x, EXCLUDED.x)).
# - NUNCA mexe em hash_dedup existente nao-nulo (wines.hash_dedup e
#   preservado). Se o hash existente for null/vazio, completa com o novo.
# - total_fontes NAO e incrementado aqui: historicamente representa
#   contagem de wine_sources comerciais (ver scripts/import_render_z.py),
#   nao tentativas de ingestao bulk. Reapply do mesmo payload nao deve
#   inflar o contador.
# - fontes: merge deduplicado por elemento.
_UPDATE_SQL = """
UPDATE wines SET
    atualizado_em = NOW(),
    hash_dedup = CASE
        WHEN wines.hash_dedup IS NULL OR wines.hash_dedup = '' THEN %(hash_dedup)s
        ELSE wines.hash_dedup
    END,
    pais = COALESCE(wines.pais, %(pais)s),
    pais_nome = COALESCE(wines.pais_nome, %(pais_nome)s),
    regiao = COALESCE(wines.regiao, %(regiao)s),
    sub_regiao = COALESCE(wines.sub_regiao, %(sub_regiao)s),
    tipo = COALESCE(wines.tipo, %(tipo)s),
    uvas = COALESCE(wines.uvas, %(uvas)s::jsonb),
    teor_alcoolico = COALESCE(wines.teor_alcoolico, %(teor_alcoolico)s),
    harmonizacao = COALESCE(wines.harmonizacao, %(harmonizacao)s),
    descricao = COALESCE(wines.descricao, %(descricao)s),
    volume_ml = COALESCE(wines.volume_ml, %(volume_ml)s),
    ean_gtin = COALESCE(wines.ean_gtin, %(ean_gtin)s),
    imagem_url = COALESCE(wines.imagem_url, %(imagem_url)s),
    moeda = COALESCE(wines.moeda, %(moeda)s),
    preco_min = COALESCE(wines.preco_min, %(preco_min)s),
    preco_max = COALESCE(wines.preco_max, %(preco_max)s),
    fontes = CASE
        WHEN wines.fontes IS NULL THEN %(fontes)s::jsonb
        WHEN wines.fontes @> %(fontes)s::jsonb THEN wines.fontes
        ELSE wines.fontes || %(fontes)s::jsonb
    END
WHERE id = %(id)s
"""


def _apply_batch(conn, batch: list[dict], source: str,
                 hash_to_id: dict[str, int]) -> tuple[int, int]:
    """Aplica um batch.

    Para cada row:
      - Se existe id via hash_to_id (match direto OU tripla): UPDATE por id.
      - Senao: INSERT ON CONFLICT DO NOTHING (safety net contra race).

    Retorna (inserted, updated).
    """
    inserted = 0
    updated = 0
    with conn.cursor() as cur:
        for row in batch:
            fontes_payload = json.dumps([f"bulk_ingest:{source}"])
            wid = hash_to_id.get(row["hash_dedup"])
            if wid is not None:
                params = dict(row)
                params["fontes"] = fontes_payload
                params["id"] = wid
                cur.execute(_UPDATE_SQL, params)
                if cur.rowcount > 0:
                    updated += 1
            else:
                params = dict(row)
                params["fontes"] = fontes_payload
                cur.execute(_INSERT_SQL, params)
                result = cur.fetchone()
                if result is not None:
                    inserted += 1
                else:
                    # ON CONFLICT DO NOTHING disparou -> wine ja existia
                    # com mesmo hash_dedup por race. Conta como update logico.
                    updated += 1
    conn.commit()
    return inserted, updated


def process_bulk(
    items: list[dict],
    *,
    dry_run: bool = True,
    source: str = "unknown",
    batch_size: int | None = None,
    max_items: int | None = None,
) -> dict:
    """Pipeline unico de ingestao.

    Args:
        items: lista de dicts com ao menos {nome}.
        dry_run: se True (default), nao toca no banco.
        source: identificador da fonte (ex: "wcf", "scraping_x", "chat_auto").
        batch_size: override de batch (default Config.BULK_INGEST_BATCH_SIZE).
        max_items: limite defensivo (default Config.BULK_INGEST_MAX_ITEMS).

    Returns dict com contadores e amostras de rejeicao.
    """
    batch_size = batch_size or Config.BULK_INGEST_BATCH_SIZE
    max_items = max_items or Config.BULK_INGEST_MAX_ITEMS

    result: dict[str, Any] = {
        "dry_run": dry_run,
        "source": source,
        "received": len(items or []),
        "valid": 0,
        "rejected": [],
        "filtered_notwine": [],
        "duplicates_in_input": 0,
        "would_insert": 0,
        "would_update": 0,
        "inserted": 0,
        "updated": 0,
        "errors": [],
        "batches": 0,
    }

    if not items:
        return result

    if len(items) > max_items:
        result["errors"].append(
            f"payload_too_big: {len(items)} > limite {max_items}"
        )
        return result

    seen_hash: dict[str, int] = {}
    validated: list[dict] = []

    for idx, raw in enumerate(items):
        if not isinstance(raw, dict):
            result["rejected"].append({"index": idx, "reason": "not_a_dict"})
            continue
        payload, reason = _validate(raw)
        if reason:
            bucket = "filtered_notwine" if reason.startswith("not_wine:") else "rejected"
            if len(result[bucket]) < 100:
                result[bucket].append({"index": idx, "reason": reason})
            continue
        h = payload["hash_dedup"]
        if h in seen_hash:
            result["duplicates_in_input"] += 1
            continue
        seen_hash[h] = idx
        validated.append(payload)

    result["valid"] = len(validated)

    if not validated:
        return result

    conn = get_connection()
    try:
        for batch in _chunks(validated, batch_size):
            hashes = [row["hash_dedup"] for row in batch]
            existing, hash_to_id = _resolve_existing(conn, batch)
            would_insert = sum(1 for h in hashes if h not in existing)
            would_update = len(hashes) - would_insert
            result["would_insert"] += would_insert
            result["would_update"] += would_update
            result["batches"] += 1

            if not dry_run:
                try:
                    ins, upd = _apply_batch(conn, batch, source, hash_to_id)
                    result["inserted"] += ins
                    result["updated"] += upd
                except Exception as e:
                    conn.rollback()
                    result["errors"].append(
                        f"batch_fail: {type(e).__name__}: {e}"
                    )
    finally:
        release_connection(conn)

    return result
