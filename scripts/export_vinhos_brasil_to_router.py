#!/usr/bin/env python3
"""Exporta base legada vinhos_brasil -> JSONL pro pre_ingest_router.

Ponte oficial entre o catalogo antigo em `C:\\natura-automation\\vinhos_brasil`
(146k wines + fontes comerciais reais: vtex/magento/mercadolivre/evino/...)
e o pipeline novo (`pre_ingest_router.py` -> `bulk_ingest`).

Somente leitura: abre conexao via `db_vinhos.get_connection()` e roda
`SET TRANSACTION READ ONLY`. Nao faz UPDATE/DELETE, nao toca schema.
Nao imprime DATABASE_URL nem credencial.

Uso tipico:
    python scripts/export_vinhos_brasil_to_router.py --fonte vtex --limit 500
    python scripts/export_vinhos_brasil_to_router.py --limit 200 --min-quality ready_like

Saida JSONL em: reports/ingest_pipeline_inputs/<ts>_vinhos_brasil_<fonte|all>.jsonl

Cada linha tem:
    nome, produtor, safra (str 4-digit), tipo, pais (ISO-2 lower),
    regiao, sub_regiao, uvas (JSON string), ean_gtin, imagem_url,
    harmonizacao, descricao, preco_min, preco_max, moeda,
    _origem_vinho_id, _source_dataset, _source_table,
    _source_scraper, _fonte_original, _preco_fonte, _mercado

Os campos `_source_*` / `_origem_*` sao preservados pelo router e
ignorados pelo bulk_ingest — sao so linhagem/auditoria.

IMPORTANTE:
- Nao roda --apply.
- Nao toca o banco antigo (read only) nem o banco novo.
- Nao chama Gemini.
- --limit default = 500 (smoke); acima precisa --allow-large.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

_LEGACY_DIR = Path(r"C:\natura-automation\vinhos_brasil")
if str(_LEGACY_DIR) not in sys.path:
    sys.path.insert(0, str(_LEGACY_DIR))

try:
    from db_vinhos import get_connection  # type: ignore  # noqa: E402
except Exception as e:
    print(
        f"[export] ERRO ao importar db_vinhos.get_connection: "
        f"{type(e).__name__}: {e}",
        file=sys.stderr,
    )
    sys.exit(1)

import psycopg2.extras  # noqa: E402


_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_OUT_DIR = _REPO_ROOT / "reports" / "ingest_pipeline_inputs"
_MAX_LIMIT_SAFE = 500

# Fontes scraper conhecidas (ver scripts scraper_*.py no repo legado).
# Warning soft se usuario pedir fora dessa lista.
_KNOWN_FONTES = {
    "vtex", "vtex_io", "magento", "loja_integrada", "dooca", "tray",
    "mercadolivre", "woocommerce", "shopify", "mistral", "sonoma",
    "wine_com_br", "evino", "nuvemshop", "videiras", "tenda",
    "amazon", "vivino_br", "generico", "html", "nacional",
}


_DADOS_EXTRAS_LOJA_KEYS = ("loja", "store", "seller")


# ---------- Helpers de normalizacao ----------

def _safra_to_str(safra) -> str | None:
    """INTEGER no banco -> string YYYY compativel com bulk_ingest._clean_safra."""
    if safra is None:
        return None
    try:
        s = int(safra)
        if 1900 <= s <= 2099:
            return str(s)
    except (TypeError, ValueError):
        pass
    return None


def _uvas_field(value) -> str | None:
    """Mantem JSON string de lista. Aceita list, string JSON, CSV."""
    if value is None:
        return None
    if isinstance(value, list):
        parts = [str(v).strip() for v in value if str(v).strip()]
        return json.dumps(parts, ensure_ascii=False) if parts else None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # Se ja for JSON valido, repassa
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return json.dumps(parsed, ensure_ascii=False)
        except Exception:
            pass
        # Senao, tenta CSV
        parts = [p.strip() for p in s.split(",") if p.strip()]
        return json.dumps(parts, ensure_ascii=False) if parts else None
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return None


def _clean_pais_iso(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip().lower()
    return s if len(s) == 2 and s.isalpha() else None


def _extract_loja_from_extras(extras) -> str | None:
    """Procura `loja` / `store` / `seller` dentro de dados_extras (JSON ou dict)."""
    if extras is None:
        return None
    data = extras
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return None
    if not isinstance(data, dict):
        return None
    for key in _DADOS_EXTRAS_LOJA_KEYS:
        v = data.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict):
            # alguns scrapers aninham: loja={"name": "..."}
            inner = v.get("name") or v.get("nome")
            if isinstance(inner, str) and inner.strip():
                return inner.strip()
    return None


def _is_ready_like(item: dict) -> bool:
    """Heuristica client-side que espelha o classifier novo.

    Usada so pra contagem em stdout — o filtro real vai ser aplicado
    pelo pre_ingest_router.py downstream.
    """
    nome = (item.get("nome") or "").strip()
    produtor = (item.get("produtor") or "").strip()
    if len(nome) < 8 or len(produtor) < 3:
        return False
    return any(
        item.get(k)
        for k in ("pais", "regiao", "sub_regiao", "ean_gtin")
    )


# ---------- Construcao da query ----------

_BASE_SQL = """
SELECT
    v.id, v.nome, v.produtor, v.safra,
    v.tipo, v.pais, v.pais_nome, v.regiao, v.sub_regiao, v.uvas,
    v.preco_min, v.preco_max, v.moeda,
    v.ean_gtin, v.imagem_url, v.harmonizacao, v.descricao,
    f.fonte AS fonte_scraper,
    f.url_original AS loja_url,
    f.preco AS preco_fonte,
    f.mercado,
    f.dados_extras AS fonte_dados_extras
FROM vinhos_brasil v
LEFT JOIN LATERAL (
    SELECT fonte, url_original, preco, mercado, dados_extras
    FROM vinhos_brasil_fontes
    WHERE vinho_id = v.id
    {fonte_join_filter}
    ORDER BY id
    LIMIT 1
) f ON TRUE
WHERE v.nome IS NOT NULL
{wine_filter}
{fonte_exists_filter}
ORDER BY v.id
LIMIT %(limit)s
OFFSET %(offset)s
"""


def build_query(
    fonte: str | None,
    ready_like: bool,
    limit: int = _MAX_LIMIT_SAFE,
    offset: int = 0,
) -> tuple[str, dict]:
    """Monta SQL + params. Parametros permanecem como placeholders (%()s)."""
    params: dict = {
        "limit": int(limit),
        "offset": int(offset),
    }
    fonte_join_filter = ""
    fonte_exists_filter = ""
    wine_filter = ""

    if fonte:
        fonte_join_filter = "AND fonte = %(fonte)s"
        # Exige pelo menos uma linha em vinhos_brasil_fontes com essa fonte
        fonte_exists_filter = (
            "AND EXISTS (SELECT 1 FROM vinhos_brasil_fontes fx "
            "WHERE fx.vinho_id = v.id AND fx.fonte = %(fonte)s)"
        )
        params["fonte"] = fonte

    if ready_like:
        wine_filter = (
            "AND LENGTH(TRIM(v.nome)) >= 8 "
            "AND v.produtor IS NOT NULL AND LENGTH(TRIM(v.produtor)) >= 3 "
            "AND (v.pais IS NOT NULL OR v.regiao IS NOT NULL "
            "     OR v.sub_regiao IS NOT NULL OR v.ean_gtin IS NOT NULL)"
        )

    sql = _BASE_SQL.format(
        fonte_join_filter=fonte_join_filter,
        fonte_exists_filter=fonte_exists_filter,
        wine_filter=wine_filter,
    )
    return sql, params


# ---------- Serializacao de linha ----------

def row_to_item(row: dict) -> dict:
    """Converte linha do SELECT pra JSONL compativel com pre_ingest_router.

    Convencao de nomenclatura (desambiguada apos feedback):

    - `url_original`     -> URL da pagina do produto na loja (pode ser
                            canonica da marca ou marketplace).
    - `loja`             -> nome humano da loja/seller (quando presente em
                            `dados_extras`).
    - `fonte_original`   -> mesmo valor que `_source_scraper`, mas exposto
                            explicitamente no payload. Representa o nome
                            do SCRAPER (vtex, magento, evino, etc), nao a URL.
    - `preco_fonte`      -> preco registrado na linha `vinhos_brasil_fontes`.
    - `mercado`          -> mercado geografico (geralmente "br").

    Mantem compat com os metadados legados `_source_*` / `_origem_*`.
    """
    fonte_scraper = row.get("fonte_scraper")
    loja_url = row.get("loja_url")
    loja_nome = _extract_loja_from_extras(row.get("fonte_dados_extras"))
    item: dict = {
        "nome": row.get("nome"),
        "produtor": row.get("produtor"),
        "safra": _safra_to_str(row.get("safra")),
        "tipo": row.get("tipo"),
        "pais": _clean_pais_iso(row.get("pais")),
        "regiao": row.get("regiao"),
        "sub_regiao": row.get("sub_regiao"),
        "uvas": _uvas_field(row.get("uvas")),
        "ean_gtin": row.get("ean_gtin"),
        "imagem_url": row.get("imagem_url"),
        "harmonizacao": row.get("harmonizacao"),
        "descricao": row.get("descricao"),
        "preco_min": float(row["preco_min"]) if row.get("preco_min") is not None else None,
        "preco_max": float(row["preco_max"]) if row.get("preco_max") is not None else None,
        "moeda": row.get("moeda"),
        # Campos de origem comercial explicitos (nao-underscore, entram no payload).
        # Preservados pelo router e ignorados pelo bulk_ingest.
        "url_original": loja_url,
        "loja": loja_nome,
        "fonte_original": fonte_scraper,
        "preco_fonte": (
            float(row["preco_fonte"])
            if row.get("preco_fonte") is not None else None
        ),
        "mercado": row.get("mercado"),
        # Linhagem de auditoria (underscore = metadata tecnica).
        "_origem_vinho_id": row.get("id"),
        "_source_dataset": "vinhos_brasil_db",
        "_source_table": "vinhos_brasil",
        "_source_scraper": fonte_scraper,
        # `_fonte_original` MANTIDO como alias historico da URL da loja, pra
        # nao quebrar consumers antigos. Novo codigo deve usar `url_original`.
        "_fonte_original": loja_url,
        "_preco_fonte": (
            float(row["preco_fonte"])
            if row.get("preco_fonte") is not None else None
        ),
        "_mercado": row.get("mercado"),
    }
    return {k: v for k, v in item.items() if v is not None}


# ---------- CLI ----------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export vinhos_brasil (legado) -> JSONL pro pre_ingest_router"
    )
    parser.add_argument("--limit", type=int, default=_MAX_LIMIT_SAFE,
                        help=f"quantidade maxima (default {_MAX_LIMIT_SAFE}, smoke)")
    parser.add_argument("--offset", type=int, default=0,
                        help="OFFSET na ORDER BY v.id (default 0); util pra paginar")
    parser.add_argument("--fonte", default=None,
                        help=("filtra por fonte scraper (vtex/magento/mercadolivre/"
                              "evino/loja_integrada/dooca/tray/mistral/sonoma/"
                              "shopify/woocommerce/wine_com_br/nuvemshop/nacional/..). "
                              "Se omitido: mistura de todas as fontes"))
    parser.add_argument("--out", default=None, help="path completo de saida")
    parser.add_argument("--min-quality", choices=["ready_like"], default=None,
                        help="ready_like: filtra no SQL nome>=8 + produtor>=3 + ancora geo")
    parser.add_argument("--allow-large", action="store_true",
                        help=f"permite --limit > {_MAX_LIMIT_SAFE} (default: bloqueado)")
    args = parser.parse_args()

    if args.limit <= 0:
        print("[export] ERRO: --limit deve ser > 0", file=sys.stderr)
        return 1
    if args.offset < 0:
        print("[export] ERRO: --offset deve ser >= 0", file=sys.stderr)
        return 1
    if args.limit > _MAX_LIMIT_SAFE and not args.allow_large:
        print(
            f"[export] ERRO: --limit={args.limit} > ceil de smoke "
            f"{_MAX_LIMIT_SAFE}. Passe --allow-large pra seguir.",
            file=sys.stderr,
        )
        return 1

    if args.fonte and args.fonte not in _KNOWN_FONTES:
        print(
            f"[export] WARN: fonte '{args.fonte}' fora da lista conhecida "
            f"({sorted(_KNOWN_FONTES)}). Prosseguindo.",
            file=sys.stderr,
        )

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fonte_tag = args.fonte or "all"
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        _DEFAULT_OUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = _DEFAULT_OUT_DIR / f"{ts}_vinhos_brasil_{fonte_tag}.jsonl"

    sql, params = build_query(
        args.fonte,
        args.min_quality == "ready_like",
        limit=args.limit,
        offset=args.offset,
    )

    rows: list[dict] = []
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute(sql, params)
                rows = cur.fetchall()
    except Exception as e:
        # Mensagem sem expor DSN/credencial
        print(
            f"[export] ERRO consulta: {type(e).__name__}",
            file=sys.stderr,
        )
        return 1

    total = 0
    with_produtor = 0
    with_pais = 0
    with_ean = 0
    ready_like_count = 0

    with out_path.open("w", encoding="utf-8") as f:
        for r in rows:
            item = row_to_item(dict(r))
            if item.get("produtor"):
                with_produtor += 1
            if item.get("pais"):
                with_pais += 1
            if item.get("ean_gtin"):
                with_ean += 1
            if _is_ready_like(item):
                ready_like_count += 1
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
            total += 1

    print(json.dumps({
        "out_path": out_path.as_posix(),
        "fonte_filter": args.fonte,
        "min_quality": args.min_quality,
        "offset": args.offset,
        "limit_requested": args.limit,
        "total_written": total,
        "with_produtor": with_produtor,
        "with_pais": with_pais,
        "with_ean": with_ean,
        "ready_like_estimate": ready_like_count,
        "next_step_cmd": (
            f"python scripts/pre_ingest_router.py --input {out_path.as_posix()} "
            f"--source vinhos_brasil_{fonte_tag}_{ts}"
        ),
    }, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
