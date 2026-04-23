from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable

import psycopg2

from sdk.plugs.common import load_repo_envs, normalize_domain, resolve_store_id
from .schemas import ExportBundle


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))


def _winegod_dsn() -> str | None:
    return (
        os.environ.get("WINEGOD_DATABASE_URL")
        or os.environ.get("DATABASE_URL_LOCAL_WINEGOD")
        or os.environ.get("WINEGOD_DB_URL")
    )


def _vinhos_brasil_dsn() -> str | None:
    return os.environ.get("VINHOS_BRASIL_DATABASE_URL")


def _fetch_rows(dsn: str, sql: str, params: tuple = ()) -> list[tuple]:
    conn = psycopg2.connect(dsn, connect_timeout=10)
    try:
        conn.set_session(readonly=True, autocommit=True)
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout TO 15000")
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


def _list_tables(dsn: str, pattern: str) -> list[str]:
    rows = _fetch_rows(
        dsn,
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name LIKE %s
        ORDER BY table_name
        """,
        (pattern,),
    )
    return [str(row[0]) for row in rows]


def _make_item(
    *,
    source_name: str,
    row: tuple,
    lookup: dict[str, int],
) -> tuple[dict, str | None]:
    (
        wine_id,
        nome,
        produtor,
        safra,
        tipo,
        pais,
        regiao,
        sub_regiao,
        uvas,
        ean_gtin,
        imagem_url,
        harmonizacao,
        descricao,
        url_original,
        preco,
        moeda,
        disponivel,
        fonte,
        mercado,
        source_pointer,
    ) = row

    domain = normalize_domain(url_original)
    store_id = resolve_store_id(url_original, lookup)
    item = {
        "nome": nome,
        "produtor": produtor,
        "safra": str(safra) if safra else None,
        "tipo": tipo,
        "pais": (pais or "").lower() or None,
        "regiao": regiao,
        "sub_regiao": sub_regiao,
        "uvas": uvas,
        "ean_gtin": ean_gtin,
        "imagem_url": imagem_url,
        "harmonizacao": harmonizacao,
        "descricao": descricao,
        "preco_min": float(preco) if preco is not None else None,
        "preco_max": float(preco) if preco is not None else None,
        "moeda": moeda,
        "_source_dataset": source_name,
        "_source_pointer": source_pointer,
        "_source_domain": domain,
        "_source_fonte": fonte,
        "_source_market": mercado,
        "_source_wine_id": wine_id,
    }
    if store_id:
        item["sources"] = [
            {
                "store_id": store_id,
                "url": url_original,
                "preco": float(preco) if preco is not None else None,
                "moeda": moeda,
                "disponivel": bool(disponivel) if disponivel is not None else True,
            }
        ]
        return item, None
    item["sources"] = []
    item["_source_url_unresolved"] = url_original
    return item, domain


def _collect_winegod_candidates(
    *,
    limit: int,
    lookup: dict[str, int],
    source_filter: Callable[[str], bool] | None = None,
    source_name: str,
) -> ExportBundle:
    dsn = _winegod_dsn()
    if not dsn:
        return ExportBundle(
            source=source_name,
            state="blocked_missing_source",
            notes=["WINEGOD_DATABASE_URL ausente"],
        )

    source_tables = _list_tables(dsn, "vinhos_%_fontes")
    source_tables = [name for name in source_tables if name.endswith("_fontes")]
    items: list[dict] = []
    unresolved: list[str] = []
    per_table = max(5, min(limit, 20))
    for source_table in source_tables:
        if len(items) >= limit:
            break
        base_table = source_table[: -len("_fontes")]
        sql = f"""
            SELECT
              v.id,
              v.nome,
              COALESCE(v.vinicola_nome, v.produtor_normalizado),
              v.safra,
              v.tipo_nome,
              v.pais_codigo,
              v.regiao_nome,
              v.sub_regiao,
              v.uvas,
              v.ean_gtin,
              v.url_imagem,
              v.harmonizacao,
              v.descricao,
              f.url_original,
              f.preco,
              f.moeda,
              f.disponivel,
              f.fonte,
              f.mercado,
              %s
            FROM public.{base_table} v
            JOIN public.{source_table} f ON f.vinho_id = v.id
            WHERE f.url_original IS NOT NULL
              AND f.preco IS NOT NULL
            ORDER BY COALESCE(f.atualizado_em, f.descoberto_em, v.atualizado_em, v.descoberto_em) DESC NULLS LAST, f.id DESC
            LIMIT %s
        """
        rows = _fetch_rows(dsn, sql, (f"{base_table}+{source_table}", per_table))
        for row in rows:
            fonte = str(row[17] or "")
            url = str(row[13] or "")
            if source_filter and not source_filter(fonte) and "amazon." not in url.lower():
                continue
            item, unresolved_domain = _make_item(
                source_name=source_name,
                row=row,
                lookup=lookup,
            )
            items.append(item)
            if unresolved_domain:
                unresolved.append(unresolved_domain)
            if len(items) >= limit:
                break

    return ExportBundle(
        source=source_name,
        state="observed" if items else "blocked_missing_source",
        items=items[:limit],
        unresolved_domains=sorted(set(unresolved))[:50],
        notes=[f"items_exported={len(items[:limit])}", f"source_tables_scanned={len(source_tables)}"],
    )


def export_winegod_admin_world_to_dq(*, limit: int, lookup: dict[str, int]) -> ExportBundle:
    return _collect_winegod_candidates(
        limit=limit,
        lookup=lookup,
        source_name="winegod_admin_world",
    )


def export_amazon_local_to_dq(*, limit: int, lookup: dict[str, int]) -> ExportBundle:
    return _collect_winegod_candidates(
        limit=limit,
        lookup=lookup,
        source_filter=lambda fonte: fonte.lower().startswith("amazon"),
        source_name="amazon_local",
    )


def export_vinhos_brasil_legacy_to_dq(*, limit: int, lookup: dict[str, int]) -> ExportBundle:
    load_repo_envs()
    dsn = _vinhos_brasil_dsn()
    if not dsn:
        return ExportBundle(
            source="vinhos_brasil_legacy",
            state="blocked_missing_source",
            notes=["VINHOS_BRASIL_DATABASE_URL ausente"],
        )

    from export_vinhos_brasil_to_router import build_query, row_to_item  # type: ignore

    sql, params = build_query(None, False, limit=limit, offset=0)
    conn = psycopg2.connect(dsn, connect_timeout=10)
    items: list[dict] = []
    unresolved: list[str] = []
    try:
        conn.set_session(readonly=True, autocommit=True)
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout TO 15000")
            cur.execute(sql, params)
            columns = [desc[0] for desc in cur.description]
            for row in cur.fetchall():
                legacy = row_to_item(dict(zip(columns, row)))
                url = legacy.get("url_original")
                domain = normalize_domain(url)
                store_id = resolve_store_id(url, lookup)
                item = {
                    "nome": legacy.get("nome"),
                    "produtor": legacy.get("produtor"),
                    "safra": legacy.get("safra"),
                    "tipo": legacy.get("tipo"),
                    "pais": legacy.get("pais"),
                    "regiao": legacy.get("regiao"),
                    "sub_regiao": legacy.get("sub_regiao"),
                    "uvas": legacy.get("uvas"),
                    "ean_gtin": legacy.get("ean_gtin"),
                    "imagem_url": legacy.get("imagem_url"),
                    "harmonizacao": legacy.get("harmonizacao"),
                    "descricao": legacy.get("descricao"),
                    "preco_min": legacy.get("preco_fonte") or legacy.get("preco_min"),
                    "preco_max": legacy.get("preco_fonte") or legacy.get("preco_max"),
                    "moeda": legacy.get("moeda"),
                    "_source_dataset": "vinhos_brasil_db",
                    "_source_pointer": "vinhos_brasil+vinhos_brasil_fontes",
                    "_source_domain": domain,
                    "_source_fonte": legacy.get("fonte_original"),
                    "_source_market": legacy.get("mercado"),
                    "_source_wine_id": legacy.get("_origem_vinho_id"),
                }
                if store_id and url:
                    item["sources"] = [
                        {
                            "store_id": store_id,
                            "url": url,
                            "preco": legacy.get("preco_fonte"),
                            "moeda": legacy.get("moeda"),
                            "disponivel": True,
                        }
                    ]
                else:
                    item["sources"] = []
                    if domain:
                        unresolved.append(domain)
                items.append(item)
    finally:
        conn.close()

    return ExportBundle(
        source="vinhos_brasil_legacy",
        state="observed" if items else "blocked_missing_source",
        items=items[:limit],
        unresolved_domains=sorted(set(unresolved))[:50],
        notes=[f"items_exported={len(items[:limit])}"],
    )


def export_amazon_mirror_to_dq_stub(*, limit: int, lookup: dict[str, int]) -> ExportBundle:
    return ExportBundle(
        source="amazon_mirror",
        state="blocked_external_host",
        notes=["host_externo_sem_acesso_local"],
        command_hint="powershell -File scripts/data_ops_shadow/run_commerce_amazon_mirror_shadow.ps1",
    )


def export_tier1_global_to_dq_stub(*, limit: int, lookup: dict[str, int]) -> ExportBundle:
    return ExportBundle(
        source="tier1_global",
        state="blocked_contract_missing",
        notes=["persistido_local_nao_isola_tier1_do_restante_do_winegod_admin"],
        command_hint="powershell -File scripts/data_ops_shadow/run_commerce_tier1_global_shadow.ps1",
    )


def export_tier2_to_dq_stub(*, source: str) -> ExportBundle:
    return ExportBundle(
        source=source,
        state="blocked_contract_missing",
        notes=["saida_por_chat_sem_artefato_local_padronizado"],
        command_hint=f"powershell -File scripts/data_ops_shadow/run_commerce_{source}_shadow.ps1",
    )


EXPORTERS = {
    "winegod_admin_world": export_winegod_admin_world_to_dq,
    "vinhos_brasil_legacy": export_vinhos_brasil_legacy_to_dq,
    "amazon_local": export_amazon_local_to_dq,
    "amazon_mirror": export_amazon_mirror_to_dq_stub,
    "tier1_global": export_tier1_global_to_dq_stub,
}
