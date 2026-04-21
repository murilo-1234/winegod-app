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

DQ V3 Escopo 1+2 (2026-04-21):
  7. Cada item aceita `sources: [{store_id, url, preco, moeda, disponivel,
     external_id}]` opcional. Apos resolver wine_id, o pipeline cria/atualiza
     `wine_sources` com ON CONFLICT (wine_id, store_id, url) DO UPDATE.
  8. `process_bulk` aceita `run_id` opcional. Quando fornecido, marca
     `wines.ingestion_run_id` e `wine_sources.ingestion_run_id`, e persiste
     stats em `ingestion_run_log`. Todas operacoes de tracking degradam
     graciosamente quando a migration 018 nao esta aplicada (colunas/tabelas
     ausentes sao detectadas via information_schema e puladas).
  9. NOT_WINE rejections sao persistidas em `not_wine_rejections` quando
     disponivel (tambem depende da migration 018).

Enrichment pesado (IA, Gemini) fica FORA desta camada por design — o pipeline
cuida de cadastro/dedup/filtro; a camada de scoring/enrichment e separada e
controlada pelo usuario (REGRA 6).

Fuzzy/review tier NAO esta neste patch (Escopo 4 futuro). O matching usa
apenas hash_dedup + tripla (produtor_normalizado, nome_normalizado, safra).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
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


_BOOL_TRUE = {"true", "1", "yes", "y", "sim", "s", "on"}
_BOOL_FALSE = {"false", "0", "no", "n", "nao", "não", "off"}


def _to_bool(value: Any, default: bool | None) -> bool | None:
    """Parser seguro de bool. Aceita bool, int, str em varios idiomas.

    Motivacao: em Python, `bool("false") == True` (string nao-vazia). Isso
    causa bugs silenciosos no payload JSON que chega do cliente com strings
    `"false"`, `"0"`, etc. Este parser e explicito.

    Retorna `default` apenas quando value e None/"".
    """
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, float):
        return value != 0.0
    # String
    text = str(value).strip().lower()
    if text in _BOOL_TRUE:
        return True
    if text in _BOOL_FALSE:
        return False
    # Fallback: trata como default. Nao levanta porque e campo opcional.
    return default


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


# ---------------------------------------------------------------------------
# DQ V3 Escopo 1+2: sources (wine_sources)
# ---------------------------------------------------------------------------

def _validate_source(raw: Any) -> tuple[dict | None, str | None]:
    """Valida uma source individual.

    Retorna (payload, None) se OK ou (None, reason) se rejeitada.

    Requisitos minimos:
      - store_id inteiro
      - url nao vazia, <= 2000 chars

    Opcionais aceitos:
      - preco (numerico), moeda, disponivel (bool, default True),
        preco_anterior, em_promocao, external_id (guardado no payload mas
        nao persistido em wine_sources por nao ter coluna dedicada).
    """
    if not isinstance(raw, dict):
        return None, "source_not_a_dict"

    store_id_raw = raw.get("store_id")
    if store_id_raw is None or store_id_raw == "":
        return None, "store_id_missing"
    try:
        store_id = int(store_id_raw)
    except (TypeError, ValueError):
        return None, "store_id_not_int"

    url = _clean(raw.get("url"))
    if not url:
        return None, "url_missing"
    if len(url) > 2000:
        return None, "url_too_long"

    preco = _to_float(raw.get("preco"))
    preco_anterior = _to_float(raw.get("preco_anterior"))
    moeda = _clean(raw.get("moeda"))

    # Bool parsing explicito -- `bool("false") == True` em Python, entao
    # precisa de parser dedicado pra aceitar `"false"`, `"0"`, `"no"` etc.
    disponivel = _to_bool(raw.get("disponivel"), default=True)
    em_promocao = _to_bool(raw.get("em_promocao"), default=False)

    return {
        "store_id": store_id,
        "url": url,
        "preco": preco,
        "preco_anterior": preco_anterior,
        "moeda": moeda,
        "disponivel": disponivel,
        "em_promocao": em_promocao,
        # external_id nao tem coluna em wine_sources; guardamos para rastreio/log.
        "external_id": _clean(raw.get("external_id")),
    }, None


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
    """Valida e normaliza um item. Retorna (payload, None) ou (None, motivo).

    Para cada item, aceita tambem um bloco opcional `sources: list`.
    Sources sao validadas individualmente via `_validate_source`. Uma source
    invalida NAO invalida o item -- o wine e aceito e a source rejeitada
    aparece em `sources_rejected` no payload de retorno.
    """
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

    # Sources (DQ V3 Escopo 1+2)
    validated_sources: list[dict] = []
    sources_rejected: list[dict] = []
    raw_sources = item.get("sources")
    if isinstance(raw_sources, list):
        for sidx, rs in enumerate(raw_sources):
            sp, sreason = _validate_source(rs)
            if sp is None:
                sources_rejected.append({
                    "source_index": sidx,
                    "reason": sreason or "invalid",
                })
            else:
                validated_sources.append(sp)
    elif raw_sources is not None:
        # sources veio mas nao eh lista
        sources_rejected.append({"source_index": -1, "reason": "sources_not_a_list"})

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
        "_sources": validated_sources,
        "_sources_rejected": sources_rejected,
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


_INSERT_SQL_LEGACY = """
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

# DQ V3 Escopo 1+2: INSERT com tracking por run_id.
# Usado quando a migration 018 esta aplicada (coluna ingestion_run_id existe).
_INSERT_SQL_V2 = """
INSERT INTO wines (
    hash_dedup, nome, nome_normalizado, produtor, produtor_normalizado,
    safra, tipo, pais, pais_nome, regiao, sub_regiao,
    uvas, teor_alcoolico, harmonizacao, descricao,
    volume_ml, ean_gtin, imagem_url,
    preco_min, preco_max, moeda,
    total_fontes, fontes, descoberto_em, atualizado_em,
    ingestion_run_id
) VALUES (
    %(hash_dedup)s, %(nome)s, %(nome_normalizado)s, %(produtor)s, %(produtor_normalizado)s,
    %(safra)s, %(tipo)s, %(pais)s, %(pais_nome)s, %(regiao)s, %(sub_regiao)s,
    %(uvas)s::jsonb, %(teor_alcoolico)s, %(harmonizacao)s, %(descricao)s,
    %(volume_ml)s, %(ean_gtin)s, %(imagem_url)s,
    %(preco_min)s, %(preco_max)s, %(moeda)s,
    0, %(fontes)s::jsonb, NOW(), NOW(),
    %(ingestion_run_id)s
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
_UPDATE_SQL_LEGACY = """
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

# DQ V3 Escopo 1+2: UPDATE que tambem marca ingestion_run_id.
# O run_id e sobrescrito no UPDATE porque queremos saber qual foi o
# *ultimo* run que tocou o wine. Hash_dedup continua preservado.
_UPDATE_SQL_V2 = """
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
    END,
    ingestion_run_id = COALESCE(%(ingestion_run_id)s, wines.ingestion_run_id)
WHERE id = %(id)s
"""

# ---------------------------------------------------------------------------
# DQ V3 Escopo 1+2: SQL para wine_sources.
# ---------------------------------------------------------------------------
_INSERT_SOURCE_SQL_LEGACY = """
INSERT INTO wine_sources (
    wine_id, store_id, url, preco, preco_anterior, moeda,
    disponivel, em_promocao, descoberto_em, atualizado_em
) VALUES (
    %(wine_id)s, %(store_id)s, %(url)s, %(preco)s, %(preco_anterior)s, %(moeda)s,
    %(disponivel)s, %(em_promocao)s, NOW(), NOW()
)
ON CONFLICT (wine_id, store_id, url) DO UPDATE SET
    preco = COALESCE(EXCLUDED.preco, wine_sources.preco),
    preco_anterior = COALESCE(EXCLUDED.preco_anterior, wine_sources.preco_anterior),
    moeda = COALESCE(EXCLUDED.moeda, wine_sources.moeda),
    disponivel = EXCLUDED.disponivel,
    em_promocao = EXCLUDED.em_promocao,
    atualizado_em = NOW()
RETURNING (xmax = 0) AS inserted  -- true se foi INSERT; false se foi UPDATE
"""

_INSERT_SOURCE_SQL_V2 = """
INSERT INTO wine_sources (
    wine_id, store_id, url, preco, preco_anterior, moeda,
    disponivel, em_promocao, descoberto_em, atualizado_em,
    ingestion_run_id
) VALUES (
    %(wine_id)s, %(store_id)s, %(url)s, %(preco)s, %(preco_anterior)s, %(moeda)s,
    %(disponivel)s, %(em_promocao)s, NOW(), NOW(),
    %(ingestion_run_id)s
)
ON CONFLICT (wine_id, store_id, url) DO UPDATE SET
    preco = COALESCE(EXCLUDED.preco, wine_sources.preco),
    preco_anterior = COALESCE(EXCLUDED.preco_anterior, wine_sources.preco_anterior),
    moeda = COALESCE(EXCLUDED.moeda, wine_sources.moeda),
    disponivel = EXCLUDED.disponivel,
    em_promocao = EXCLUDED.em_promocao,
    atualizado_em = NOW(),
    ingestion_run_id = COALESCE(EXCLUDED.ingestion_run_id, wine_sources.ingestion_run_id)
RETURNING (xmax = 0) AS inserted
"""


# ---------------------------------------------------------------------------
# DQ V3 Escopo 1+2: detecao de schema (migration 018 aplicada?).
#
# Sem cache global -- cache global causaria stale state apos aplicar a migration
# sem restart do processo. Cada `process_bulk` recebe/cria um `schema_cache`
# dict local e passa aos helpers, entao dentro da mesma call so fazemos 1 query
# por check, mas entre calls a verificacao e refeita.
#
# Se a query falhar por qualquer razao (permissao, DB down, etc.), tratamos
# como "nao aplicada" e o pipeline cai no SQL legacy sem ingestion_run_id.
# ---------------------------------------------------------------------------

def _schema_check(conn, sql: str, cache: dict | None, key: str) -> bool:
    if cache is not None and key in cache:
        return cache[key]
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            ok = cur.fetchone()[0] is not None
    except Exception:
        ok = False
    if cache is not None:
        cache[key] = ok
    return ok


def _has_wines_run_id(conn, cache: dict | None = None) -> bool:
    return _schema_check(conn, """
        SELECT column_name FROM information_schema.columns
        WHERE table_name='wines' AND column_name='ingestion_run_id'
    """, cache, "wines_run_id")


def _has_wine_sources_run_id(conn, cache: dict | None = None) -> bool:
    return _schema_check(conn, """
        SELECT column_name FROM information_schema.columns
        WHERE table_name='wine_sources' AND column_name='ingestion_run_id'
    """, cache, "wine_sources_run_id")


def _has_run_log(conn, cache: dict | None = None) -> bool:
    return _schema_check(conn, """
        SELECT to_regclass('public.ingestion_run_log')
    """, cache, "run_log")


def _has_notwine_table(conn, cache: dict | None = None) -> bool:
    return _schema_check(conn, """
        SELECT to_regclass('public.not_wine_rejections')
    """, cache, "notwine")


# ---------------------------------------------------------------------------
def _apply_batch(conn, batch: list[dict], source: str,
                 hash_to_id: dict[str, int],
                 run_id: str | None,
                 schema_cache: dict | None = None) -> tuple[int, int, dict[str, int]]:
    """Aplica um batch de wines.

    Para cada row:
      - Se existe id via hash_to_id (match direto OU tripla): UPDATE por id.
      - Senao: INSERT ON CONFLICT DO NOTHING (safety net contra race).

    Tambem popula `row["_wine_id"]` com o id resolvido, para uso posterior
    por `_apply_sources_batch`.

    Se a migration 018 nao estiver aplicada (coluna `ingestion_run_id`
    ausente em wines), usa SQL legacy e ignora run_id silenciosamente.

    Retorna (inserted, updated, id_lookup_cache) onde id_lookup_cache
    mapeia hash_dedup -> wine_id (inclui ids recem inseridos).
    """
    has_run_id = _has_wines_run_id(conn, schema_cache)
    insert_sql = _INSERT_SQL_V2 if has_run_id else _INSERT_SQL_LEGACY
    update_sql = _UPDATE_SQL_V2 if has_run_id else _UPDATE_SQL_LEGACY

    inserted = 0
    updated = 0
    id_lookup: dict[str, int] = dict(hash_to_id)  # comeca com os ja conhecidos

    with conn.cursor() as cur:
        for row in batch:
            fontes_payload = json.dumps([f"bulk_ingest:{source}"])
            wid = hash_to_id.get(row["hash_dedup"])
            params = dict(row)
            params["fontes"] = fontes_payload
            if has_run_id:
                params["ingestion_run_id"] = run_id
            # remover chaves auxiliares que nao existem na tabela
            params.pop("_sources", None)
            params.pop("_sources_rejected", None)
            params.pop("_payload_index", None)
            params.pop("_wine_id", None)

            if wid is not None:
                params["id"] = wid
                cur.execute(update_sql, params)
                if cur.rowcount > 0:
                    updated += 1
                row["_wine_id"] = wid
            else:
                cur.execute(insert_sql, params)
                result = cur.fetchone()
                if result is not None:
                    new_id = result[0]
                    inserted += 1
                    row["_wine_id"] = new_id
                    id_lookup[row["hash_dedup"]] = new_id
                else:
                    # ON CONFLICT DO NOTHING disparou -> wine ja existia
                    # com mesmo hash_dedup por race. Conta como update logico.
                    # Precisamos resolver wine_id para as sources.
                    cur.execute(
                        "SELECT id FROM wines WHERE hash_dedup = %s LIMIT 1",
                        (row["hash_dedup"],),
                    )
                    r = cur.fetchone()
                    if r:
                        row["_wine_id"] = r[0]
                        id_lookup[row["hash_dedup"]] = r[0]
                    updated += 1
    conn.commit()
    return inserted, updated, id_lookup


def _resolve_existing_sources(conn, wine_source_keys: list[tuple]) -> set[tuple]:
    """Retorna conjunto de tuplas (wine_id, store_id, url) que ja existem.

    Usado em dry-run para calcular would_insert_sources vs would_update_sources.
    Se wine_source_keys estiver vazio, retorna set() vazio.
    """
    if not wine_source_keys:
        return set()
    existing: set[tuple] = set()
    # Postgres IN de tuplas grandes pode ser lento; batch por chunks de 1000.
    with conn.cursor() as cur:
        for i in range(0, len(wine_source_keys), 1000):
            chunk = wine_source_keys[i:i + 1000]
            cur.execute(
                """
                SELECT wine_id, store_id, url FROM wine_sources
                WHERE (wine_id, store_id, url) IN %s
                """,
                (tuple(chunk),),
            )
            for wid, sid, url in cur.fetchall():
                existing.add((wid, sid, url))
    return existing


def _prevalidate_store_ids(conn, store_ids: set[int]) -> set[int]:
    """Retorna subset de store_ids que existem em `stores`.

    Filtro batchado -- evita ForeignKeyViolation rompendo transacao e
    descartando inserts previos. Sources com store_id invalido sao
    reportadas em `sources_rejected` com motivo `store_id_fk_missing`.
    """
    if not store_ids:
        return set()
    valid: set[int] = set()
    with conn.cursor() as cur:
        ids_list = list(store_ids)
        for i in range(0, len(ids_list), 1000):
            chunk = ids_list[i:i + 1000]
            cur.execute("SELECT id FROM stores WHERE id = ANY(%s)", (chunk,))
            for (sid,) in cur.fetchall():
                valid.add(sid)
    return valid


def _apply_sources_batch(conn, items_with_sources: list[dict],
                         run_id: str | None,
                         schema_cache: dict | None = None) -> tuple[int, int]:
    """Aplica sources de items que ja tem `_wine_id` resolvido.

    Pre-condicao: sources com FK invalida ja foram filtradas em
    `process_bulk` via `_prevalidate_store_ids`. Este metodo NAO captura
    `ForeignKeyViolation` -- se ocorrer, propaga para o caller (que ja
    trata via conn.rollback() no batch_fail).

    Retorna (sources_inserted, sources_updated). Sources sem `_wine_id`
    resolvido sao ignoradas (wine insert falhou por alguma razao).
    """
    has_run_id = _has_wine_sources_run_id(conn, schema_cache)
    sql = _INSERT_SOURCE_SQL_V2 if has_run_id else _INSERT_SOURCE_SQL_LEGACY

    inserted = 0
    updated = 0
    with conn.cursor() as cur:
        for item in items_with_sources:
            wine_id = item.get("_wine_id")
            if wine_id is None:
                continue
            sources = item.get("_sources") or []
            for src in sources:
                params = {
                    "wine_id": wine_id,
                    "store_id": src["store_id"],
                    "url": src["url"],
                    "preco": src.get("preco"),
                    "preco_anterior": src.get("preco_anterior"),
                    "moeda": src.get("moeda"),
                    "disponivel": src.get("disponivel", True),
                    "em_promocao": src.get("em_promocao", False),
                }
                if has_run_id:
                    params["ingestion_run_id"] = run_id
                cur.execute(sql, params)
                r = cur.fetchone()
                if r and r[0]:  # xmax = 0 -> foi INSERT
                    inserted += 1
                else:
                    updated += 1
    conn.commit()
    return inserted, updated


def _log_run(conn, run_id: str, source: str, result: dict) -> None:
    """Persiste um row em ingestion_run_log. No-op se tabela nao existe."""
    if not run_id or not _has_run_log(conn):
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ingestion_run_log (
                    run_id, source, finished_at, dry_run,
                    received, valid, duplicates_in_input,
                    would_insert, would_update, inserted, updated,
                    sources_in_input, sources_duplicates_in_input,
                    sources_rejected_count,
                    would_insert_sources, would_update_sources,
                    sources_inserted, sources_updated,
                    filtered_notwine, rejected, errors, params
                ) VALUES (
                    %s, %s, NOW(), %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s::jsonb
                )
                ON CONFLICT (run_id) DO UPDATE SET
                    finished_at = NOW(),
                    received = EXCLUDED.received,
                    valid = EXCLUDED.valid,
                    duplicates_in_input = EXCLUDED.duplicates_in_input,
                    would_insert = EXCLUDED.would_insert,
                    would_update = EXCLUDED.would_update,
                    inserted = EXCLUDED.inserted,
                    updated = EXCLUDED.updated,
                    sources_in_input = EXCLUDED.sources_in_input,
                    sources_duplicates_in_input = EXCLUDED.sources_duplicates_in_input,
                    sources_rejected_count = EXCLUDED.sources_rejected_count,
                    would_insert_sources = EXCLUDED.would_insert_sources,
                    would_update_sources = EXCLUDED.would_update_sources,
                    sources_inserted = EXCLUDED.sources_inserted,
                    sources_updated = EXCLUDED.sources_updated,
                    filtered_notwine = EXCLUDED.filtered_notwine,
                    rejected = EXCLUDED.rejected,
                    errors = EXCLUDED.errors,
                    params = EXCLUDED.params
                """,
                (
                    run_id, source, result.get("dry_run", False),
                    result.get("received", 0), result.get("valid", 0),
                    result.get("duplicates_in_input", 0),
                    result.get("would_insert", 0), result.get("would_update", 0),
                    result.get("inserted", 0), result.get("updated", 0),
                    result.get("sources_in_input", 0),
                    result.get("sources_duplicates_in_input", 0),
                    # DQ V3 hardening V2: usar contadores totais, nao len(lista_amostra).
                    result.get("sources_rejected_count", 0),
                    result.get("would_insert_sources", 0),
                    result.get("would_update_sources", 0),
                    result.get("sources_inserted", 0),
                    result.get("sources_updated", 0),
                    result.get("filtered_notwine_count", 0),
                    result.get("rejected_count", 0),
                    len(result.get("errors", [])),
                    json.dumps({
                        "source": source,
                        "batch_size": result.get("batches", 0),
                    }),
                ),
            )
        conn.commit()
        # DQ V3 Escopo 4: grava contadores extras se migration 019 aplicada.
        # Segundo UPDATE isolado (nao mexe no ON CONFLICT principal, entao
        # coexiste com schema pre-019 sem quebrar).
        try:
            if _has_run_log_v3_columns(conn):
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE ingestion_run_log SET
                            enqueued_review = %s,
                            auto_merge_strict = %s,
                            blocked = %s
                        WHERE run_id = %s
                        """,
                        (
                            result.get("enqueue_for_review_count", 0),
                            result.get("auto_merge_strict_count", 0),
                            result.get("blocked"),
                            run_id,
                        ),
                    )
                conn.commit()
        except Exception:
            conn.rollback()
    except Exception:
        # nao falha o pipeline se log der erro
        conn.rollback()


def _log_not_wine(conn, run_id: str | None, source: str,
                  rejections: list[dict]) -> None:
    """Persiste NOT_WINE rejections em `not_wine_rejections`. No-op se tabela ausente."""
    if not rejections or not _has_notwine_table(conn):
        return
    try:
        with conn.cursor() as cur:
            for r in rejections:
                cur.execute(
                    """
                    INSERT INTO not_wine_rejections
                        (run_id, source, index_in_payload, nome, produtor, reason)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (run_id, source,
                     r.get("index"),
                     (r.get("nome") or "")[:500] or None,
                     (r.get("produtor") or "")[:500] or None,
                     r.get("reason") or ""),
                )
        conn.commit()
    except Exception:
        conn.rollback()


# ---------------------------------------------------------------------------
# DQ V3 Escopo 4: fuzzy tier + ingestion_review_queue
#
# Terceiro caminho entre UPDATE (hash/tripla) e INSERT. Quando um item
# nao bate hash nem tripla mas "parece proximo" de um canonical Vivino
# (chave K3 = nome_normalizado_sem_safra + pais + tipo), entra em:
#
#   - AUTO_MERGE ESTRITO (vira UPDATE no canonical) quando TODOS forem verdade:
#       * exatamente 1 candidato K3
#       * produtor e prefixo claro de um lado para o outro
#       * nao ha conflito de safra quando ambos preenchidos
#   - REVIEW QUEUE (ingestion_review_queue) nos demais casos:
#       * 2+ candidatos K3 -> fuzzy_k3_multi_candidate
#       * safra conflitante (ambos preenchidos e diferentes) -> fuzzy_k3_safra_conflict
#       * Levenshtein <= 2 em produtor mas nao e prefixo -> fuzzy_k3_levenshtein_close
#       * caso restante -> fuzzy_k3_disjoint_producer
#
# Levenshtein <= 2 SOZINHO nunca gera auto-merge nesta versao. Ele so
# serve para priorizar revisao manual (sinal via match_tier).
#
# Corte defensivo BLOCKED_QUEUE_EXPLOSION: se enqueue > INGEST_QUEUE_ABS_CAP
# ou > INGEST_QUEUE_PCT_CAP * valid, o apply eh abortado sem nenhum write.
# ---------------------------------------------------------------------------

_SAFRA_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
# Lookahead `(?=\W|$)` em vez de `\b` final para capturar "n.v." antes do
# ponto final conflitar com word boundary (`.` e non-word, fim de string
# tambem -- sem boundary entre eles).
_NV_RE = re.compile(r"\bn\.?\s*v\.?(?=\W|$)", re.IGNORECASE)
_PRODUCER_PREFIX_MIN_LEN = 4
_PRODUCER_PREFIX_MIN_DIFF = 2
_FUZZY_CANDIDATE_CAP = 5


def _strip_safra(nome_norm: str) -> str:
    """Espelha a regra da Fase 6: remove ano 19xx/20xx e 'NV'/'N.V.'."""
    if not nome_norm:
        return ""
    out = _SAFRA_YEAR_RE.sub("", nome_norm)
    out = _NV_RE.sub("", out)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def _levenshtein(a: str, b: str, cap: int = 3) -> int:
    """Levenshtein com corte. Retorna min(distance, cap) sem lib externa.

    Early exit quando a diferenca minima de linha ja atingiu cap.
    Usado apenas como sinal de "proximo mas nao prefixo" (match_tier).
    """
    if a == b:
        return 0
    if not a:
        return min(len(b), cap)
    if not b:
        return min(len(a), cap)
    if abs(len(a) - len(b)) >= cap:
        return cap
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        min_row = curr[0]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
            if curr[j] < min_row:
                min_row = curr[j]
        if min_row >= cap:
            return cap
        prev = curr
    return min(prev[-1], cap)


def _producer_prefix_match(a: str, b: str) -> bool:
    """True se um produtor e prefixo claro do outro.

    Exige comprimento minimo (_PRODUCER_PREFIX_MIN_LEN) dos dois lados e
    diferenca minima de _PRODUCER_PREFIX_MIN_DIFF caracteres quando um
    esta estritamente contido no outro (evita match trivial entre
    "el" e "el-mosto").

    Se forem exatamente iguais, True (conta como prefixo degenerado).
    """
    if not a or not b:
        return False
    a2 = a.strip().lower()
    b2 = b.strip().lower()
    if len(a2) < _PRODUCER_PREFIX_MIN_LEN or len(b2) < _PRODUCER_PREFIX_MIN_LEN:
        return False
    if a2 == b2:
        return True
    if a2.startswith(b2) and (len(a2) - len(b2)) >= _PRODUCER_PREFIX_MIN_DIFF:
        return True
    if b2.startswith(a2) and (len(b2) - len(a2)) >= _PRODUCER_PREFIX_MIN_DIFF:
        return True
    return False


def _has_review_queue(conn, cache: dict | None = None) -> bool:
    return _schema_check(conn, """
        SELECT to_regclass('public.ingestion_review_queue')
    """, cache, "review_queue")


def _has_run_log_v3_columns(conn, cache: dict | None = None) -> bool:
    """True se migration 019 foi aplicada (coluna `enqueued_review` existe)."""
    return _schema_check(conn, """
        SELECT column_name FROM information_schema.columns
        WHERE table_name='ingestion_run_log' AND column_name='enqueued_review'
    """, cache, "run_log_v3")


def _resolve_fuzzy_k3(conn, remainder: list[dict]) -> dict[str, list[dict]]:
    """Para items que nao bateram em hash/tripla, busca candidatos via K3.

    K3 = (nome_normalizado_sem_safra, pais, tipo).
    Universo = canonicals ativos Vivino (vivino_id NOT NULL, suppressed_at NULL).

    Retorna dict hash_dedup -> lista de ate _FUZZY_CANDIDATE_CAP candidatos
    ordenados por id. Items sem K3 completo (faltou nome/pais/tipo) nao
    participam e caem em INSERT normal.
    """
    if not remainder:
        return {}

    lookup_keys: set[tuple] = set()
    key_to_hashes: dict[tuple, list[str]] = {}

    for row in remainder:
        nn = row.get("nome_normalizado")
        pais = row.get("pais")
        tipo = row.get("tipo")
        if not nn or not pais or not tipo:
            continue
        nn_sem_safra = _strip_safra(nn)
        if not nn_sem_safra:
            continue
        # Cachear no row pra nao recalcular depois
        row["_nome_sem_safra"] = nn_sem_safra
        key = (nn_sem_safra, pais, tipo)
        lookup_keys.add(key)
        key_to_hashes.setdefault(key, []).append(row["hash_dedup"])

    if not lookup_keys:
        return {}

    key_to_candidates: dict[tuple, list[dict]] = {}
    unique_keys = list(lookup_keys)
    with conn.cursor() as cur:
        for i in range(0, len(unique_keys), 500):
            chunk = unique_keys[i:i + 500]
            cur.execute(
                """
                SELECT id, produtor_normalizado, safra,
                       nome_normalizado_sem_safra, pais, tipo
                FROM wines
                WHERE (nome_normalizado_sem_safra, pais, tipo) IN %s
                  AND vivino_id IS NOT NULL
                  AND suppressed_at IS NULL
                ORDER BY id
                """,
                (tuple(chunk),),
            )
            for wid, pn, sf, nss, p, t in cur.fetchall():
                k = (nss, p, t)
                lst = key_to_candidates.setdefault(k, [])
                if len(lst) < _FUZZY_CANDIDATE_CAP:
                    lst.append({
                        "id": wid,
                        "produtor_normalizado": pn or "",
                        "safra": sf,
                        "nome_normalizado_sem_safra": nss,
                    })

    candidates_by_hash: dict[str, list[dict]] = {}
    for key, hashes in key_to_hashes.items():
        cands = key_to_candidates.get(key)
        if cands:
            for h in hashes:
                candidates_by_hash[h] = cands
    return candidates_by_hash


def _classify_match(row: dict, candidates: list[dict]) -> tuple[str, str | None, int | None]:
    """Aplica as 4 regras aprovadas do Escopo 4.

    Retorna (decision, match_tier, auto_merge_wine_id):
      - ("auto_merge", "fuzzy_k3_prefix_unique", wine_id)
      - ("enqueue", "fuzzy_k3_multi_candidate", None)
      - ("enqueue", "fuzzy_k3_safra_conflict", None)
      - ("enqueue", "fuzzy_k3_levenshtein_close", None)
      - ("enqueue", "fuzzy_k3_disjoint_producer", None)
      - ("none", None, None)  -> INSERT normal
    """
    if not candidates:
        return "none", None, None

    if len(candidates) > 1:
        return "enqueue", "fuzzy_k3_multi_candidate", None

    cand = candidates[0]
    source_prod = row.get("produtor_normalizado") or ""
    cand_prod = cand.get("produtor_normalizado") or ""
    source_safra = row.get("safra")
    cand_safra = cand.get("safra")

    # Conflito de safra com ambos preenchidos: nunca auto-merge.
    if source_safra and cand_safra and source_safra != cand_safra:
        return "enqueue", "fuzzy_k3_safra_conflict", None

    # Auto-merge estrito: produtor e prefixo claro de um lado para o outro.
    if _producer_prefix_match(source_prod, cand_prod):
        return "auto_merge", "fuzzy_k3_prefix_unique", cand["id"]

    # Levenshtein <= 2 eh SINAL para review, nao gatilho de auto-merge.
    if source_prod and cand_prod:
        dist = _levenshtein(source_prod, cand_prod, cap=3)
        if dist <= 2:
            return "enqueue", "fuzzy_k3_levenshtein_close", None

    return "enqueue", "fuzzy_k3_disjoint_producer", None


_INSERT_REVIEW_SQL = """
INSERT INTO ingestion_review_queue (
    run_id, source, source_payload, match_tier, candidate_wine_ids, status
) VALUES (
    %(run_id)s, %(source)s, %(source_payload)s::jsonb,
    %(match_tier)s, %(candidate_wine_ids)s, 'pending'
)
"""


def _payload_for_review(row: dict) -> dict:
    """Reconstroi um payload JSON-serializavel a partir do row validado.

    Preserva todas as chaves de negocio e o bloco `sources` intacto, de forma
    que o endpoint de aprovacao possa re-aplicar o item. Chaves internas
    (que comecam com `_`) e `hash_dedup` sao omitidas.
    """
    out: dict = {}
    for k, v in row.items():
        if k.startswith("_"):
            continue
        if k == "hash_dedup":
            continue
        out[k] = v
    sources = row.get("_sources") or []
    if sources:
        out["sources"] = [dict(s) for s in sources]
    return out


def _enqueue_review_batch(conn, enqueue_list: list[dict],
                          run_id: str | None, source: str,
                          schema_cache: dict | None = None) -> int:
    """Grava cada entrada em ingestion_review_queue. No-op se tabela ausente.

    Retorna contagem inserida. Cada entrada em enqueue_list e um dict
    {"row": row, "match_tier": str, "candidate_wine_ids": list[int]}.
    """
    if not enqueue_list:
        return 0
    if not _has_review_queue(conn, schema_cache):
        return 0
    inserted = 0
    try:
        with conn.cursor() as cur:
            for entry in enqueue_list:
                row = entry["row"]
                payload = _payload_for_review(row)
                cur.execute(
                    _INSERT_REVIEW_SQL,
                    {
                        "run_id": run_id,
                        "source": source,
                        "source_payload": json.dumps(payload, default=str),
                        "match_tier": entry["match_tier"],
                        "candidate_wine_ids": entry.get("candidate_wine_ids") or [],
                    },
                )
                inserted += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return inserted


def _check_queue_explosion(result: dict) -> tuple[str | None, str | None]:
    """Aplica o cut-off defensivo BLOCKED_QUEUE_EXPLOSION.

    Retorna (blocked_code, reason) ou (None, None) se passou.
    Thresholds configuraveis via Config.INGEST_QUEUE_ABS_CAP e
    Config.INGEST_QUEUE_PCT_CAP.
    """
    try:
        abs_cap = int(getattr(Config, "INGEST_QUEUE_ABS_CAP", 20000))
    except Exception:
        abs_cap = 20000
    try:
        pct_cap = float(getattr(Config, "INGEST_QUEUE_PCT_CAP", 0.05))
    except Exception:
        pct_cap = 0.05

    enqueue_total = int(result.get("would_enqueue_review", 0))
    valid = int(result.get("valid", 0))

    if enqueue_total > abs_cap:
        return (
            "BLOCKED_QUEUE_EXPLOSION",
            f"enqueue_count={enqueue_total} > abs_cap={abs_cap}",
        )
    if valid > 0:
        ratio = enqueue_total / valid
        if ratio > pct_cap:
            pct = ratio * 100.0
            return (
                "BLOCKED_QUEUE_EXPLOSION",
                f"enqueue_count={enqueue_total} of valid={valid} = {pct:.2f}% > pct_cap={pct_cap * 100:.1f}%",
            )
    return None, None


# ---------------------------------------------------------------------------
# DQ V3 Escopo 6: caminho publico SO-SOURCES para importadores legados.
#
# `process_sources_only` e a porta de entrada unica para scripts (como
# import_stores.py Passo 3 e import_render_z.py Fase 1) que JA tem o
# wine_id ou hash_dedup resolvido e so precisam anexar/atualizar rows em
# `wine_sources`. Nao cria nem atualiza `wines`.
#
# Reusa as mesmas primitivas do `process_bulk`:
#   - `_validate_source` para validar cada source
#   - `_prevalidate_store_ids` para FK filtering batchado
#   - `_existing_hashes_to_ids` para resolver hash_dedup -> wine_id
#   - `_resolve_existing_sources` para contagem dry-run
#   - `_apply_sources_batch` para escrita batchada
#
# Pay-off: scripts antigos deixam de inserir em `wine_sources` direto via
# SQL paralelo. Centralizam no pipeline unico. Cut-off BLOCKED_QUEUE_* NAO
# se aplica aqui (ninguem vai pra review queue, entao o risco de explosao
# e estrutural zero).
# ---------------------------------------------------------------------------

def process_sources_only(
    items: list[dict],
    *,
    dry_run: bool = True,
    source: str = "unknown",
    batch_size: int | None = None,
    max_items: int | None = None,
    run_id: str | None = None,
) -> dict:
    """Anexa rows em `wine_sources` a wines existentes, sem tocar em `wines`.

    Cada item deve conter:
      - `wine_id` (int, opcional) OU `hash_dedup` (str, opcional) -- um dos dois.
        Se ambos forem fornecidos, `wine_id` prevalece.
      - `sources`: lista de dicts no formato aceito por `_validate_source`
        (`store_id`, `url` obrigatorios; `preco`, `moeda`, `disponivel`,
        `preco_anterior`, `em_promocao` opcionais).

    Items sem wine_id/hash_dedup, com hash nao-resolvido, ou sem sources,
    sao reportados em `rejected` / `rejected_count` e nao afetam nada.

    Dry-run nao escreve nada. Apply faz UPSERT em `wine_sources` (reusa
    `ON CONFLICT (wine_id, store_id, url)` via `_apply_sources_batch`) e
    opcionalmente marca `ingestion_run_id` se a migration 018 esta aplicada.

    Returns dict com os mesmos nomes de contadores de `process_bulk` que
    fazem sentido aqui: sources_in_input, sources_duplicates_in_input,
    sources_rejected_count, would_insert_sources, would_update_sources,
    sources_inserted, sources_updated, rejected_count, errors, batches.
    """
    batch_size = batch_size or Config.BULK_INGEST_BATCH_SIZE
    max_items = max_items or Config.BULK_INGEST_MAX_ITEMS

    if run_id is not None:
        run_id = str(run_id).strip()[:128] or None

    result: dict[str, Any] = {
        "dry_run": dry_run,
        "source": source,
        "run_id": run_id,
        "received": len(items or []),
        "valid": 0,
        "rejected": [],
        "sources_rejected": [],
        "rejected_count": 0,
        "sources_rejected_count": 0,
        "sources_in_input": 0,
        "sources_duplicates_in_input": 0,
        "would_insert_sources": 0,
        "would_update_sources": 0,
        "sources_inserted": 0,
        "sources_updated": 0,
        "errors": [],
        "batches": 0,
    }

    _SAMPLE_LIMIT = 100

    if not items:
        return result

    if len(items) > max_items:
        result["errors"].append(
            f"payload_too_big: {len(items)} > limite {max_items}"
        )
        return result

    # Fase 1: normaliza cada item em {_wine_id | _hash_dedup, _sources, _sources_rejected}
    prepared: list[dict] = []
    for idx, raw in enumerate(items):
        if not isinstance(raw, dict):
            result["rejected_count"] += 1
            if len(result["rejected"]) < _SAMPLE_LIMIT:
                result["rejected"].append({"index": idx, "reason": "not_a_dict"})
            continue

        wine_id = raw.get("wine_id")
        hash_dedup = _clean(raw.get("hash_dedup"))
        if wine_id is None and not hash_dedup:
            result["rejected_count"] += 1
            if len(result["rejected"]) < _SAMPLE_LIMIT:
                result["rejected"].append({
                    "index": idx,
                    "reason": "missing_wine_id_and_hash_dedup",
                })
            continue
        if wine_id is not None:
            try:
                wine_id = int(wine_id)
            except (TypeError, ValueError):
                result["rejected_count"] += 1
                if len(result["rejected"]) < _SAMPLE_LIMIT:
                    result["rejected"].append({
                        "index": idx, "reason": "wine_id_not_int",
                    })
                continue

        raw_sources = raw.get("sources")
        if not isinstance(raw_sources, list) or not raw_sources:
            result["rejected_count"] += 1
            if len(result["rejected"]) < _SAMPLE_LIMIT:
                result["rejected"].append({
                    "index": idx, "reason": "sources_missing_or_not_a_list",
                })
            continue

        validated_sources: list[dict] = []
        for sidx, rs in enumerate(raw_sources):
            sp, sreason = _validate_source(rs)
            if sp is None:
                result["sources_rejected_count"] += 1
                if len(result["sources_rejected"]) < _SAMPLE_LIMIT:
                    result["sources_rejected"].append({
                        "item_index": idx,
                        "source_index": sidx,
                        "reason": sreason or "invalid",
                    })
            else:
                validated_sources.append(sp)

        if not validated_sources:
            # Item sem nenhuma source valida: nao rejeita por isso (ja contou
            # cada source rejeitada acima); so nao entra em prepared.
            continue

        prepared.append({
            "_payload_index": idx,
            "_wine_id": wine_id,
            "_hash_dedup": hash_dedup,
            "_sources": validated_sources,
        })

    result["valid"] = len(prepared)

    # Dedup de sources no payload (por (wine_id_or_hash, store_id, url))
    seen: set[tuple] = set()
    for row in prepared:
        key_base = row["_wine_id"] if row["_wine_id"] is not None else row["_hash_dedup"]
        unique_srcs: list[dict] = []
        for s in row["_sources"]:
            k = (key_base, s["store_id"], s["url"])
            if k in seen:
                result["sources_duplicates_in_input"] += 1
                continue
            seen.add(k)
            unique_srcs.append(s)
        row["_sources"] = unique_srcs
        result["sources_in_input"] += len(unique_srcs)

    if not prepared:
        return result

    schema_cache: dict[str, bool] = {}
    conn = get_connection()
    try:
        for batch in _chunks(prepared, batch_size):
            # Resolve hash -> wine_id para os itens que so tem hash
            hashes_to_resolve = [
                r["_hash_dedup"] for r in batch
                if r["_wine_id"] is None and r["_hash_dedup"]
            ]
            if hashes_to_resolve:
                hash_to_id = _existing_hashes_to_ids(conn, hashes_to_resolve)
                for r in batch:
                    if r["_wine_id"] is None and r["_hash_dedup"]:
                        wid = hash_to_id.get(r["_hash_dedup"])
                        if wid is None:
                            result["rejected_count"] += 1
                            if len(result["rejected"]) < _SAMPLE_LIMIT:
                                result["rejected"].append({
                                    "index": r["_payload_index"],
                                    "reason": "hash_not_found",
                                })
                        else:
                            r["_wine_id"] = wid

            # Filtra items sem wine_id resolvido
            resolved = [r for r in batch if r["_wine_id"] is not None]
            if not resolved:
                result["batches"] += 1
                continue

            # FK prevalidation em stores
            batch_store_ids: set[int] = set()
            for r in resolved:
                for s in r["_sources"]:
                    batch_store_ids.add(s["store_id"])

            valid_store_ids = (
                _prevalidate_store_ids(conn, batch_store_ids)
                if batch_store_ids else set()
            )
            for r in resolved:
                kept: list[dict] = []
                for sidx, s in enumerate(r["_sources"]):
                    if s["store_id"] in valid_store_ids:
                        kept.append(s)
                    else:
                        result["sources_rejected_count"] += 1
                        if len(result["sources_rejected"]) < _SAMPLE_LIMIT:
                            result["sources_rejected"].append({
                                "item_index": r["_payload_index"],
                                "source_index": sidx,
                                "store_id": s["store_id"],
                                "reason": "store_id_fk_missing",
                            })
                r["_sources"] = kept

            # Dry-run: distinguir insert vs update
            known_src_keys: list[tuple] = []
            for r in resolved:
                for s in r["_sources"]:
                    known_src_keys.append((r["_wine_id"], s["store_id"], s["url"]))

            existing_source_keys = (
                _resolve_existing_sources(conn, known_src_keys)
                if dry_run else set()
            )

            for r in resolved:
                for s in r["_sources"]:
                    if dry_run:
                        if (r["_wine_id"], s["store_id"], s["url"]) in existing_source_keys:
                            result["would_update_sources"] += 1
                        else:
                            result["would_insert_sources"] += 1

            # Apply
            if not dry_run:
                items_with_sources = [r for r in resolved if r["_sources"]]
                if items_with_sources:
                    try:
                        s_ins, s_upd = _apply_sources_batch(
                            conn, items_with_sources, run_id, schema_cache
                        )
                        result["sources_inserted"] += s_ins
                        result["sources_updated"] += s_upd
                    except Exception as e:
                        conn.rollback()
                        result["errors"].append(
                            f"sources_batch_fail: {type(e).__name__}: {e}"
                        )

            result["batches"] += 1
    finally:
        release_connection(conn)

    return result


def process_bulk(
    items: list[dict],
    *,
    dry_run: bool = True,
    source: str = "unknown",
    batch_size: int | None = None,
    max_items: int | None = None,
    run_id: str | None = None,
    create_sources: bool = True,
) -> dict:
    """Pipeline unico de ingestao.

    Args:
        items: lista de dicts com ao menos {nome}. Cada item pode ter `sources`
            (lista de dicts com `store_id` + `url` obrigatorios).
        dry_run: se True (default), nao toca no banco.
        source: identificador textual da fonte (ex: "wcf", "scraping_x").
        batch_size: override de batch (default Config.BULK_INGEST_BATCH_SIZE).
        max_items: limite defensivo (default Config.BULK_INGEST_MAX_ITEMS).
        run_id: (DQ V3 Escopo 1+2) id textual deste run. Quando fornecido e a
            migration 018 esta aplicada, marca `wines.ingestion_run_id` e
            `wine_sources.ingestion_run_id`, e persiste stats em
            `ingestion_run_log`. No-op gracioso se schema nao tem as colunas.
        create_sources: (DQ V3 Escopo 1+2) se True (default), tenta
            criar/atualizar `wine_sources` a partir do bloco `sources` de cada
            item. Se False, ignora `sources` silenciosamente.

    Returns dict com contadores e amostras de rejeicao (inclui contadores de
    sources quando aplicavel).
    """
    batch_size = batch_size or Config.BULK_INGEST_BATCH_SIZE
    max_items = max_items or Config.BULK_INGEST_MAX_ITEMS

    if run_id is not None:
        run_id = str(run_id).strip()[:128] or None

    result: dict[str, Any] = {
        "dry_run": dry_run,
        "source": source,
        "run_id": run_id,
        "received": len(items or []),
        "valid": 0,
        # Listas amostra -- capadas em 100 items para response compacta
        "rejected": [],
        "filtered_notwine": [],
        "sources_rejected": [],
        "enqueue_for_review": [],
        # Contadores totais -- NAO dependem do cap das listas
        "rejected_count": 0,
        "filtered_notwine_count": 0,
        "sources_rejected_count": 0,
        "duplicates_in_input": 0,
        "would_insert": 0,
        "would_update": 0,
        "inserted": 0,
        "updated": 0,
        # sources (DQ V3 Escopo 1+2)
        "sources_in_input": 0,
        "sources_duplicates_in_input": 0,
        "would_insert_sources": 0,
        "would_update_sources": 0,
        "sources_inserted": 0,
        "sources_updated": 0,
        "create_sources": create_sources,
        # DQ V3 Escopo 4: fuzzy tier / review queue
        "would_auto_merge_strict": 0,
        "auto_merge_strict_count": 0,
        "would_enqueue_review": 0,
        "enqueue_for_review_count": 0,
        "enqueue_by_tier": {},
        "blocked": None,
        "block_reason": None,
        "errors": [],
        "batches": 0,
    }

    _SAMPLE_LIMIT = 100

    if not items:
        return result

    if len(items) > max_items:
        result["errors"].append(
            f"payload_too_big: {len(items)} > limite {max_items}"
        )
        return result

    seen_hash: dict[str, int] = {}
    validated: list[dict] = []
    notwine_raw: list[dict] = []  # para _log_not_wine

    for idx, raw in enumerate(items):
        if not isinstance(raw, dict):
            result["rejected_count"] += 1
            if len(result["rejected"]) < _SAMPLE_LIMIT:
                result["rejected"].append({"index": idx, "reason": "not_a_dict"})
            continue
        payload, reason = _validate(raw)
        if reason:
            is_notwine = reason.startswith("not_wine:")
            counter_key = "filtered_notwine_count" if is_notwine else "rejected_count"
            bucket_key = "filtered_notwine" if is_notwine else "rejected"
            result[counter_key] += 1
            if len(result[bucket_key]) < _SAMPLE_LIMIT:
                result[bucket_key].append({"index": idx, "reason": reason})
            if is_notwine:
                # notwine_raw nao e capado -- toda rejeicao NOT_WINE vai para
                # persistencia em `not_wine_rejections` (apply only).
                notwine_raw.append({
                    "index": idx,
                    "reason": reason,
                    "nome": _clean(raw.get("nome")),
                    "produtor": _clean(raw.get("produtor")),
                })
            continue

        # Coletar rejeicoes de sources deste item para o response global
        for sr in (payload.pop("_sources_rejected", []) or []):
            result["sources_rejected_count"] += 1
            if len(result["sources_rejected"]) < _SAMPLE_LIMIT:
                result["sources_rejected"].append({
                    "item_index": idx,
                    "source_index": sr.get("source_index"),
                    "reason": sr.get("reason"),
                })

        h = payload["hash_dedup"]
        if h in seen_hash:
            result["duplicates_in_input"] += 1
            continue
        seen_hash[h] = idx
        # Guarda o indice original do payload para que rejecoes de FK
        # downstream possam referenciar o item corretamente no response.
        payload["_payload_index"] = idx
        validated.append(payload)

    result["valid"] = len(validated)

    # Dedup de sources no payload (por (store_id, url) dentro do mesmo wine)
    seen_sources_in_input: set[tuple] = set()
    for payload in validated:
        sources = payload.get("_sources") or []
        if not sources:
            continue
        unique: list[dict] = []
        for s in sources:
            key = (payload["hash_dedup"], s["store_id"], s["url"])
            if key in seen_sources_in_input:
                result["sources_duplicates_in_input"] += 1
                continue
            seen_sources_in_input.add(key)
            unique.append(s)
        payload["_sources"] = unique
        result["sources_in_input"] += len(unique)

    if not validated:
        # DQ V3 hardening: dry-run NAO escreve nada. Apply sim persiste
        # NOT_WINE e registra o run_log (se houver run_id), mesmo que o
        # payload tenha sido 100% rejeitado -- auditoria e rollback granular
        # dependem dessa entrada.
        if not dry_run:
            try:
                conn = get_connection()
                try:
                    if notwine_raw:
                        _log_not_wine(conn, run_id, source, notwine_raw)
                    if run_id:
                        _log_run(conn, run_id, source, result)
                finally:
                    release_connection(conn)
            except Exception:
                pass
        return result

    # Schema cache local a esta chamada (nao global) -- evita stale state
    # pos-aplicacao da migration sem restart do processo.
    schema_cache: dict[str, bool] = {}

    # DQ V3 Escopo 4: estrategia de duas fases.
    #  FASE 1 (sempre roda): classificacao de todos os batches contra o banco
    #    (read-only). Produz `batch_plans` e contadores `would_*`.
    #  FASE 2 (so em apply e nao-bloqueado): escreve wines, wine_sources,
    #    ingestion_review_queue, logs. Se BLOCKED_QUEUE_EXPLOSION, nao escreve.
    batch_plans: list[dict] = []

    conn = get_connection()
    try:
        # ================================================================
        # FASE 1 -- classify (read-only, sempre roda)
        # ================================================================
        for batch in _chunks(validated, batch_size):
            hashes = [row["hash_dedup"] for row in batch]
            existing, hash_to_id = _resolve_existing(conn, batch)

            # Fuzzy K3 somente para items que nao bateram em hash/tripla
            remainder = [row for row in batch if row["hash_dedup"] not in existing]
            fuzzy_by_hash = _resolve_fuzzy_k3(conn, remainder)

            # Classifica os remainder
            enqueue_list: list[dict] = []
            auto_merge_count = 0
            for row in remainder:
                cands = fuzzy_by_hash.get(row["hash_dedup"], [])
                decision, match_tier, auto_merge_wid = _classify_match(row, cands)
                if decision == "auto_merge" and auto_merge_wid is not None:
                    hash_to_id[row["hash_dedup"]] = auto_merge_wid
                    existing.add(row["hash_dedup"])
                    auto_merge_count += 1
                    result["auto_merge_strict_count"] += 0  # incremento real so em apply
                    result["would_auto_merge_strict"] += 1
                    result["enqueue_by_tier"].setdefault("fuzzy_k3_prefix_unique", 0)
                    result["enqueue_by_tier"]["fuzzy_k3_prefix_unique"] += 1
                elif decision == "enqueue":
                    enqueue_list.append({
                        "row": row,
                        "match_tier": match_tier,
                        "candidate_wine_ids": [c["id"] for c in cands[:_FUZZY_CANDIDATE_CAP]],
                    })
                    result["would_enqueue_review"] += 1
                    result["enqueue_by_tier"].setdefault(match_tier, 0)
                    result["enqueue_by_tier"][match_tier] += 1
                    if len(result["enqueue_for_review"]) < _SAMPLE_LIMIT:
                        result["enqueue_for_review"].append({
                            "item_index": row.get("_payload_index"),
                            "match_tier": match_tier,
                            "candidate_wine_ids": [c["id"] for c in cands[:_FUZZY_CANDIDATE_CAP]],
                        })
                # "none" -> fica fora; vai para INSERT normal

            enqueue_hashes = {e["row"]["hash_dedup"] for e in enqueue_list}

            # Contadores would_insert / would_update (com fuzzy ja aplicado)
            would_insert = 0
            would_update = 0
            for h in hashes:
                if h in enqueue_hashes:
                    continue  # enqueue nao conta como insert nem update
                if h in existing:
                    would_update += 1
                else:
                    would_insert += 1
            result["would_insert"] += would_insert
            result["would_update"] += would_update
            result["batches"] += 1

            # ------------------------------------------------------------
            # FK pre-validation e dry-run counters de sources.
            # ------------------------------------------------------------
            if create_sources:
                batch_store_ids: set[int] = set()
                for row in batch:
                    for s in (row.get("_sources") or []):
                        batch_store_ids.add(s["store_id"])

                if batch_store_ids:
                    valid_store_ids = _prevalidate_store_ids(conn, batch_store_ids)
                else:
                    valid_store_ids = set()

                for row in batch:
                    srcs = row.get("_sources") or []
                    if not srcs:
                        continue
                    valid_srcs: list[dict] = []
                    for sidx, s in enumerate(srcs):
                        if s["store_id"] in valid_store_ids:
                            valid_srcs.append(s)
                        else:
                            result["sources_rejected_count"] += 1
                            if len(result["sources_rejected"]) < _SAMPLE_LIMIT:
                                result["sources_rejected"].append({
                                    "item_index": row.get("_payload_index"),
                                    "source_index": sidx,
                                    "store_id": s["store_id"],
                                    "reason": "store_id_fk_missing",
                                })
                    row["_sources"] = valid_srcs

                # Dry-run counters de sources (apos FK) -- NAO conta sources
                # de items que vao para review queue (a oferta fica presa na
                # queue ate aprovacao; nao vai para wine_sources neste run).
                known_src_keys: list[tuple] = []
                for row in batch:
                    if row["hash_dedup"] in enqueue_hashes:
                        continue
                    srcs = row.get("_sources") or []
                    if not srcs:
                        continue
                    wid = hash_to_id.get(row["hash_dedup"])
                    if wid is None:
                        continue
                    for s in srcs:
                        known_src_keys.append((wid, s["store_id"], s["url"]))

                existing_source_keys = (
                    _resolve_existing_sources(conn, known_src_keys)
                    if dry_run else set()
                )

                for row in batch:
                    if row["hash_dedup"] in enqueue_hashes:
                        continue
                    srcs = row.get("_sources") or []
                    wid = hash_to_id.get(row["hash_dedup"])
                    if wid is None:
                        result["would_insert_sources"] += len(srcs)
                    else:
                        for s in srcs:
                            if (wid, s["store_id"], s["url"]) in existing_source_keys:
                                result["would_update_sources"] += 1
                            else:
                                result["would_insert_sources"] += 1

            batch_plans.append({
                "batch": batch,
                "hash_to_id": hash_to_id,
                "enqueue_list": enqueue_list,
                "enqueue_hashes": enqueue_hashes,
                "auto_merge_planned": auto_merge_count,
            })

        # ================================================================
        # CUT-OFF -- BLOCKED_QUEUE_EXPLOSION
        # ================================================================
        blocked_code, block_reason = _check_queue_explosion(result)
        result["blocked"] = blocked_code
        result["block_reason"] = block_reason

        if blocked_code:
            # Aborta apply. Em dry-run mantem counters would_*.
            # Em apply NAO escreve NADA (nem NOT_WINE, nem log_run).
            return result

        # ================================================================
        # FASE 2 -- apply (so em apply e nao-bloqueado)
        # ================================================================
        if not dry_run:
            # NOT_WINE rejections -- apos cut-off (se bloqueou, nao grava).
            if notwine_raw:
                _log_not_wine(conn, run_id, source, notwine_raw)

            for plan in batch_plans:
                batch = plan["batch"]
                hash_to_id = plan["hash_to_id"]
                enqueue_list = plan["enqueue_list"]
                enqueue_hashes = plan["enqueue_hashes"]

                apply_batch_rows = [r for r in batch if r["hash_dedup"] not in enqueue_hashes]

                if apply_batch_rows:
                    try:
                        ins, upd, _id_cache = _apply_batch(
                            conn, apply_batch_rows, source, hash_to_id, run_id, schema_cache
                        )
                        result["inserted"] += ins
                        result["updated"] += upd
                        # auto_merge vai via hash_to_id como UPDATE normal
                        result["auto_merge_strict_count"] += plan["auto_merge_planned"]

                        if create_sources:
                            items_with_sources = [
                                row for row in apply_batch_rows if row.get("_sources")
                            ]
                            if items_with_sources:
                                try:
                                    s_ins, s_upd = _apply_sources_batch(
                                        conn, items_with_sources, run_id, schema_cache
                                    )
                                    result["sources_inserted"] += s_ins
                                    result["sources_updated"] += s_upd
                                except Exception as e:
                                    conn.rollback()
                                    result["errors"].append(
                                        f"sources_batch_fail: {type(e).__name__}: {e}"
                                    )
                    except Exception as e:
                        conn.rollback()
                        result["errors"].append(
                            f"batch_fail: {type(e).__name__}: {e}"
                        )

                if enqueue_list:
                    try:
                        enq = _enqueue_review_batch(
                            conn, enqueue_list, run_id, source, schema_cache
                        )
                        result["enqueue_for_review_count"] += enq
                    except Exception as e:
                        conn.rollback()
                        result["errors"].append(
                            f"enqueue_batch_fail: {type(e).__name__}: {e}"
                        )

            # Log do run ao final.
            if run_id:
                _log_run(conn, run_id, source, result)
    finally:
        release_connection(conn)

    return result
