"""Producer local de artefato padronizado de commerce.

Gera JSONL + `<prefix>_summary.json` no formato definido em
`docs/TIER_COMMERCE_CONTRACT.md`, consumindo o `winegod_db` local.

Uso tipico para Tier1 (HTTP deterministico):

    python scripts/data_ops_producers/build_commerce_artifact.py \
      --pipeline-family tier1 \
      --output-dir reports/data_ops_artifacts/tier1 \
      --tier-filter api_shopify,api_woocommerce,api_vtex,sitemap_html,sitemap_jsonld \
      --limit 200

Uso tipico para Tier2 (Playwright + IA):

    python scripts/data_ops_producers/build_commerce_artifact.py \
      --pipeline-family tier2_br \
      --output-dir reports/data_ops_artifacts/tier2/br \
      --tier-filter playwright_ia \
      --pais-codigo br \
      --limit 200

**Evidencia tecnica do tier**: cruzamos `lojas_scraping.metodo_recomendado`
com `vinhos_{pais}_fontes.fonte` via `lojas_scraping.url` vs URL da fonte.
Isso bate com `scraper_tier1.py` (APIs/sitemap) vs `scraper_tier2.py`
(Playwright+IA). Nao inventa rotulo; usa o marcador tecnico persistido.

O producer NAO escreve em public.wines/wine_sources. Ele apenas gera o
JSONL + summary para o plug_commerce_dq_v3 consumir depois via dry-run/apply.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_env():
    for p in (REPO_ROOT / ".env", REPO_ROOT / "backend" / ".env"):
        if p.exists():
            load_dotenv(p, override=False)


def _winegod_dsn() -> str | None:
    return (
        os.environ.get("WINEGOD_DATABASE_URL")
        or os.environ.get("DATABASE_URL_LOCAL_WINEGOD")
    )


def _list_source_tables(cur) -> list[str]:
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema='public' AND table_name LIKE %s
        ORDER BY table_name
        """,
        ("vinhos_%_fontes",),
    )
    return [r[0] for r in cur.fetchall() if r[0].endswith("_fontes")]


def _domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = (urlparse(url if "://" in url else "https://" + url).hostname or "").lower()
    except Exception:
        return None
    return host.lstrip("www.") if host else None


def _build_item(row: dict, *, pipeline_family: str, run_id: str) -> dict:
    """Converte row do join (vinhos_* + vinhos_*_fontes + lojas_scraping)
    para o contrato `docs/TIER_COMMERCE_CONTRACT.md`."""

    store_domain = row.get("store_domain") or _domain(row.get("loja_url")) or _domain(row.get("url_original"))
    return {
        "pipeline_family": pipeline_family,
        "run_id": run_id,
        "country": (row.get("pais_codigo") or "").lower() or "xx",
        "store_name": row.get("store_name") or "unknown_store",
        "store_domain": store_domain or "unknown.domain",
        "url_original": row.get("url_original") or "",
        "nome": row.get("nome") or "",
        "produtor": row.get("produtor") or "",
        "safra": row.get("safra"),
        "preco": float(row["preco"]) if row.get("preco") is not None else None,
        "moeda": row.get("moeda") or "XXX",
        "captured_at": (row.get("atualizado_em") or row.get("descoberto_em") or datetime.now(timezone.utc)).isoformat(),
        "source_pointer": f"{row.get('source_table')}#{row.get('fonte_id')}",
    }


def normalize_host(value: str | None) -> str | None:
    """Extrai e normaliza o host de uma URL ou dominio bruto.

    Remove protocolo, porta, www. e espacos em branco. Retorna None se
    nao conseguir derivar host valido.
    """

    if not value:
        return None
    raw = value.strip().lower()
    if not raw:
        return None
    try:
        parsed = urlparse(raw if "://" in raw else "https://" + raw)
    except Exception:
        return None
    host = (parsed.hostname or "").strip()
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]
    return host


def _host_eligible(fonte_host: str | None, loja_hosts: set[str]) -> bool:
    """Matching por host normalizado com boundary real.

    Aceita igualdade exata OU subdominio legitimo (ex: `shop.amazon.com`
    bate com `amazon.com`). REJEITA substring interna enganosa como
    `mazon.com.br` batendo com `amazon.com.br`.
    """

    if not fonte_host:
        return False
    if fonte_host in loja_hosts:
        return True
    for loja_host in loja_hosts:
        # boundary real: precisa terminar em `.<loja_host>` (subdominio)
        if fonte_host.endswith("." + loja_host):
            return True
    return False


def _fetch_candidates(
    cur,
    *,
    source_tables: list[str],
    methods: list[str],
    pais_codigo: str | None,
    limit: int,
) -> list[dict]:
    """Busca candidatos Tier1/Tier2 com matching por host normalizado exato.

    Estrategia para evitar falso positivo de substring:
    1. Busca elegiveis de `lojas_scraping` (filtrada por metodo + pais).
    2. Normaliza host de cada loja e guarda em Python set.
    3. Faz scan paginado em `vinhos_*_fontes` e filtra em Python por
       `_host_eligible` com boundary real (igualdade ou subdominio).
    Isso elimina o falso positivo `mazon.com.br` == `amazon.com.br`.
    """

    rows: list[dict] = []
    remaining = limit
    for source_table in source_tables:
        if remaining <= 0:
            break
        base = source_table[: -len("_fontes")]
        if pais_codigo and not base.endswith("_" + pais_codigo.lower()):
            continue
        country_suffix = base.rsplit("_", 1)[-1]
        method_placeholders = ",".join(["%s"] * len(methods))
        # 1. Lojas elegiveis por pais + metodo
        cur.execute(
            f"""
            SELECT nome, url, url_normalizada, metodo_recomendado
            FROM public.lojas_scraping
            WHERE metodo_recomendado IN ({method_placeholders})
              AND url_normalizada IS NOT NULL
              AND length(url_normalizada) > 3
              AND pais_codigo = %s
            """,
            list(methods) + [country_suffix.upper()],
        )
        lojas = cur.fetchall()
        if not lojas:
            continue
        # Normaliza hosts das lojas (host real, sem protocolo/porta/www)
        host_to_loja: dict[str, dict] = {}
        for nome, url, url_normalizada, metodo in lojas:
            for candidate in (url_normalizada, url):
                h = normalize_host(candidate)
                if h and h not in host_to_loja:
                    host_to_loja[h] = {
                        "nome": nome,
                        "url": url,
                        "url_normalizada": url_normalizada,
                        "metodo": metodo,
                    }
        if not host_to_loja:
            continue
        loja_hosts = set(host_to_loja.keys())
        # 2. Scan dos fontes daquele pais, paginado
        sql = f"""
            SELECT
              v.id AS vinho_id,
              v.nome,
              COALESCE(v.vinicola_nome, v.produtor_normalizado) AS produtor,
              v.safra,
              %s AS pais_codigo,
              f.id AS fonte_id,
              f.url_original,
              f.preco,
              f.moeda,
              f.fonte,
              COALESCE(f.atualizado_em, f.descoberto_em) AS atualizado_em,
              f.descoberto_em,
              '{source_table}' AS source_table
            FROM public.{source_table} f
            JOIN public.{base} v ON v.id = f.vinho_id
            WHERE f.url_original IS NOT NULL
            ORDER BY f.id DESC
            LIMIT %s
        """
        # Lemos um multiplo do limit remanescente porque filtramos em Python
        scan_limit = min(remaining * 10, 5000)
        cur.execute(sql, [country_suffix, scan_limit])
        columns = [c.name for c in cur.description]
        for db_row in cur.fetchall():
            if remaining <= 0:
                break
            row = dict(zip(columns, db_row))
            host = normalize_host(row.get("url_original"))
            if not _host_eligible(host, loja_hosts):
                continue
            loja = host_to_loja.get(host)
            if loja is None:
                # subdominio legitimo: recupera loja via endswith
                for loja_host, loja_info in host_to_loja.items():
                    if host and host.endswith("." + loja_host):
                        loja = loja_info
                        break
            row["store_name"] = (loja or {}).get("nome")
            row["loja_url"] = (loja or {}).get("url")
            row["store_domain"] = host
            row["metodo"] = (loja or {}).get("metodo")
            rows.append(row)
            remaining -= 1
    return rows[:limit]


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera artefato commerce padronizado a partir do winegod_db local.")
    parser.add_argument(
        "--pipeline-family",
        required=True,
        help="Valor gravado em items.pipeline_family e summary.pipeline_family. "
        "Deve bater com o expected_family do consumer (ex: 'tier1', 'tier2', 'amazon_mirror_primary').",
    )
    parser.add_argument(
        "--source-label",
        default=None,
        help="Rotulo opcional gravado como prefixo do JSONL (ex: 'tier1_global'). "
        "Se omitido, usa --pipeline-family.",
    )
    parser.add_argument("--output-dir", required=True, type=Path, help="Diretorio destino do JSONL/summary")
    parser.add_argument("--tier-filter", required=True, help="CSV de metodo_recomendado de lojas_scraping (evidencia do tier)")
    parser.add_argument("--pais-codigo", default=None, help="Filtra por pais (ex: br). Opcional")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--input-scope", default=None, help="Rotulo livre para o summary (ex: FR,ES,PT)")
    args = parser.parse_args()

    _load_env()
    dsn = _winegod_dsn()
    if not dsn:
        print("ERR: WINEGOD_DATABASE_URL ausente", file=sys.stderr)
        return 2

    methods = [m.strip() for m in args.tier_filter.split(",") if m.strip()]
    if not methods:
        print("ERR: --tier-filter vazio", file=sys.stderr)
        return 2

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    source_label = args.source_label or args.pipeline_family
    started_at = datetime.now(timezone.utc)
    run_id = f"{source_label}_{started_at.strftime('%Y%m%d_%H%M%S')}"

    conn = psycopg2.connect(dsn, connect_timeout=15)
    conn.set_session(readonly=True, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout TO 180000")
            source_tables = _list_source_tables(cur)
            raw_rows = _fetch_candidates(
                cur,
                source_tables=source_tables,
                methods=methods,
                pais_codigo=args.pais_codigo,
                limit=args.limit,
            )
    finally:
        conn.close()

    items_all = [_build_item(r, pipeline_family=args.pipeline_family, run_id=run_id) for r in raw_rows]
    # Respeita contrato: produtor e nome sao nao-nullable e nao-vazios.
    # Items incompletos nao viram artefato valido. Pulamos honestamente.
    items = [
        it for it in items_all
        if it["nome"] and it["produtor"] and it["store_domain"] != "unknown.domain"
    ]

    jsonl_path = output_dir / f"{started_at.strftime('%Y%m%d_%H%M%S')}_{source_label}.jsonl"
    jsonl_path.write_text("\n".join(json.dumps(it, default=str) for it in items), encoding="utf-8")

    finished_at = datetime.now(timezone.utc)
    summary = {
        "run_id": run_id,
        "pipeline_family": args.pipeline_family,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "host": socket.gethostname() or "este_pc",
        "input_scope": args.input_scope or args.pais_codigo or "global",
        "items_emitted": len(items),
        "artifact_sha256": _hash_file(jsonl_path),
    }
    (jsonl_path.with_name(jsonl_path.stem + "_summary.json")).write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )

    print(
        f"OK items={len(items)} jsonl={jsonl_path.name} sha256={summary['artifact_sha256'][:12]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
