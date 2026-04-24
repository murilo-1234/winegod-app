from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Callable, Iterable

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


def export_amazon_local_legacy_backfill_to_dq(*, limit: int, lookup: dict[str, int]) -> ExportBundle:
    """Backfill controlado do historico amazon_local.

    Marca lineage como `legacy_local_backfill` para diferenciar do feed primario
    do espelho. Nao cria wine_sources paralelo; apenas anota _source_pipeline e
    _source_dataset para o dashboard reconhecer que a fonte e legado.

    Regras:
    - ainda consome o mesmo `vinhos_*` + `vinhos_*_fontes` do winegod_db;
    - filtra por `fonte ILIKE 'amazon%'`;
    - marca cada item com `_source_pipeline='amazon_local_legacy_backfill'`;
    - serve para rodar em lotes controlados apos o espelho virar primario;
    - NAO deve ser promovido a feed recorrente principal.
    """

    bundle = _collect_winegod_candidates(
        limit=limit,
        lookup=lookup,
        source_filter=lambda fonte: fonte.lower().startswith("amazon"),
        source_name="amazon_local_legacy_backfill",
    )
    for item in bundle.items:
        item["_source_pipeline"] = "amazon_local_legacy_backfill"
        item["_source_lineage"] = "legacy_local"
    bundle.notes.append("lineage=legacy_local_backfill")
    return bundle


def _amazon_mirror_artifact_dir() -> Path:
    explicit = os.environ.get("AMAZON_MIRROR_ARTIFACT_DIR")
    if explicit:
        return Path(explicit)
    return REPO_ROOT / "reports" / "data_ops_artifacts" / "amazon_mirror"


def _load_jsonl_artifact(path: Path, limit: int) -> list[dict]:
    items: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(items) >= limit:
                break
    return items


def _pick_latest_artifact(base: Path, suffix: str = ".jsonl") -> Path | None:
    if not base.exists():
        return None
    candidates = sorted(
        (p for p in base.iterdir() if p.is_file() and p.suffix == suffix),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def export_amazon_mirror_primary_to_dq(*, limit: int, lookup: dict[str, int]) -> ExportBundle:
    """Feed primario oficial da Amazon, alimentado por artefato do PC espelho.

    Contrato:
    - um JSONL por execucao do espelho, com campos minimos
      (pipeline_family, run_id, country, store_name, store_domain,
       url_original, nome, produtor, safra, preco, moeda, captured_at,
       source_pointer);
    - o diretorio padrao e `reports/data_ops_artifacts/amazon_mirror/`
      (configuravel via `AMAZON_MIRROR_ARTIFACT_DIR`);
    - o exporter pega o artefato mais recente e aplica lookup de store_id;
    - se nao houver artefato, retorna `blocked_external_host` com command_hint.
    """

    base = _amazon_mirror_artifact_dir()
    latest = _pick_latest_artifact(base)
    if latest is None:
        return ExportBundle(
            source="amazon_mirror_primary",
            state="blocked_external_host",
            notes=[
                "nenhum_artefato_jsonl_em=" + str(base),
                "host_externo_pc_espelho",
                "entregar_jsonl_em=reports/data_ops_artifacts/amazon_mirror/",
            ],
            command_hint="powershell -File scripts/data_ops_shadow/run_commerce_amazon_mirror_primary_shadow.ps1",
        )

    raw_items = _load_jsonl_artifact(latest, limit)
    items: list[dict] = []
    unresolved: list[str] = []
    for raw in raw_items:
        url = raw.get("url_original") or raw.get("url")
        domain = normalize_domain(url)
        store_id = resolve_store_id(url, lookup)
        price = raw.get("preco")
        item = {
            "nome": raw.get("nome"),
            "produtor": raw.get("produtor"),
            "safra": str(raw.get("safra")) if raw.get("safra") is not None else None,
            "tipo": raw.get("tipo"),
            "pais": (raw.get("country") or raw.get("pais") or "").lower() or None,
            "regiao": raw.get("regiao"),
            "sub_regiao": raw.get("sub_regiao"),
            "uvas": raw.get("uvas"),
            "ean_gtin": raw.get("ean_gtin") or raw.get("asin"),
            "imagem_url": raw.get("imagem_url") or raw.get("url_imagem"),
            "harmonizacao": raw.get("harmonizacao"),
            "descricao": raw.get("descricao"),
            "preco_min": float(price) if price is not None else None,
            "preco_max": float(price) if price is not None else None,
            "moeda": raw.get("moeda"),
            "_source_dataset": "amazon_mirror",
            "_source_pipeline": raw.get("pipeline_family") or "amazon_mirror_primary",
            "_source_pointer": raw.get("source_pointer") or str(latest.name),
            "_source_run_id": raw.get("run_id"),
            "_source_captured_at": raw.get("captured_at"),
            "_source_domain": domain,
            "_source_lineage": "primary",
        }
        if store_id and url:
            item["sources"] = [
                {
                    "store_id": store_id,
                    "url": url,
                    "preco": float(price) if price is not None else None,
                    "moeda": raw.get("moeda"),
                    "disponivel": bool(raw.get("disponivel", True)),
                }
            ]
        else:
            item["sources"] = []
            if domain:
                unresolved.append(domain)
        items.append(item)

    return ExportBundle(
        source="amazon_mirror_primary",
        state="observed" if items else "blocked_missing_source",
        items=items[:limit],
        unresolved_domains=sorted(set(unresolved))[:50],
        notes=[
            f"items_exported={len(items[:limit])}",
            f"artifact={latest.name}",
            f"artifact_sha256={hashlib.sha256(latest.read_bytes()).hexdigest()}",
            "lineage=primary",
        ],
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


def _tier_artifact_dir(family: str, chat: str | None = None) -> Path:
    explicit = os.environ.get(f"{family.upper()}_ARTIFACT_DIR")
    if explicit:
        return Path(explicit)
    base = REPO_ROOT / "reports" / "data_ops_artifacts" / family
    if chat:
        return base / chat
    return base


def _export_tier_from_artifact(
    *,
    source_name: str,
    pipeline_family: str,
    limit: int,
    lookup: dict[str, int],
    artifact_dir: Path,
) -> ExportBundle:
    """Exporter generico para Tier1/Tier2 consumindo artefato padronizado JSONL.

    Contrato minimo por item (ver docs/TIER_COMMERCE_CONTRACT.md):
      pipeline_family, run_id, country, store_name, store_domain,
      url_original, nome, produtor, safra, preco, moeda, captured_at,
      source_pointer

    Retorna `blocked_contract_missing` se o diretorio nao existir ou se o
    artefato mais recente nao for JSONL valido.
    """

    latest = _pick_latest_artifact(artifact_dir)
    if latest is None:
        return ExportBundle(
            source=source_name,
            state="blocked_contract_missing",
            notes=[
                f"nenhum_artefato_jsonl_em={artifact_dir}",
                f"entregar_jsonl_em={artifact_dir}",
                "contrato=docs/TIER_COMMERCE_CONTRACT.md",
            ],
            command_hint=f"powershell -File scripts/data_ops_shadow/run_commerce_{source_name}_shadow.ps1",
        )

    raw_items = _load_jsonl_artifact(latest, limit)
    items: list[dict] = []
    unresolved: list[str] = []
    for raw in raw_items:
        if raw.get("pipeline_family") and raw["pipeline_family"] not in (pipeline_family, source_name):
            continue
        url = raw.get("url_original") or raw.get("url")
        domain = normalize_domain(url)
        store_id = resolve_store_id(url, lookup)
        price = raw.get("preco")
        item = {
            "nome": raw.get("nome"),
            "produtor": raw.get("produtor"),
            "safra": str(raw.get("safra")) if raw.get("safra") is not None else None,
            "tipo": raw.get("tipo"),
            "pais": (raw.get("country") or raw.get("pais") or "").lower() or None,
            "regiao": raw.get("regiao"),
            "sub_regiao": raw.get("sub_regiao"),
            "uvas": raw.get("uvas"),
            "ean_gtin": raw.get("ean_gtin"),
            "imagem_url": raw.get("imagem_url") or raw.get("url_imagem"),
            "harmonizacao": raw.get("harmonizacao"),
            "descricao": raw.get("descricao"),
            "preco_min": float(price) if price is not None else None,
            "preco_max": float(price) if price is not None else None,
            "moeda": raw.get("moeda"),
            "_source_dataset": source_name,
            "_source_pipeline": raw.get("pipeline_family") or pipeline_family,
            "_source_pointer": raw.get("source_pointer") or str(latest.name),
            "_source_run_id": raw.get("run_id"),
            "_source_captured_at": raw.get("captured_at"),
            "_source_domain": domain,
            "_source_store_name": raw.get("store_name"),
            "_source_lineage": "primary" if pipeline_family in ("tier1", "tier2") else "mixed",
        }
        if store_id and url:
            item["sources"] = [
                {
                    "store_id": store_id,
                    "url": url,
                    "preco": float(price) if price is not None else None,
                    "moeda": raw.get("moeda"),
                    "disponivel": bool(raw.get("disponivel", True)),
                }
            ]
        else:
            item["sources"] = []
            if domain:
                unresolved.append(domain)
        items.append(item)

    return ExportBundle(
        source=source_name,
        state="observed" if items else "blocked_contract_missing",
        items=items[:limit],
        unresolved_domains=sorted(set(unresolved))[:50],
        notes=[
            f"items_exported={len(items[:limit])}",
            f"artifact={latest.name}",
            f"artifact_sha256={hashlib.sha256(latest.read_bytes()).hexdigest()}",
            f"pipeline_family={pipeline_family}",
        ],
    )


def export_tier1_global_to_dq(*, limit: int, lookup: dict[str, int]) -> ExportBundle:
    return _export_tier_from_artifact(
        source_name="tier1_global",
        pipeline_family="tier1",
        limit=limit,
        lookup=lookup,
        artifact_dir=_tier_artifact_dir("tier1"),
    )


def export_tier2_from_artifact(*, source: str, limit: int, lookup: dict[str, int]) -> ExportBundle:
    chat = source.replace("tier2_", "")
    return _export_tier_from_artifact(
        source_name=source,
        pipeline_family="tier2",
        limit=limit,
        lookup=lookup,
        artifact_dir=_tier_artifact_dir("tier2", chat=chat),
    )


# Stubs mantidos para retrocompatibilidade dos schedulers antigos que ainda
# apontam para nomes genericos. Nao sao mais o caminho recomendado.
def export_amazon_mirror_to_dq_stub(*, limit: int, lookup: dict[str, int]) -> ExportBundle:
    return ExportBundle(
        source="amazon_mirror",
        state="blocked_external_host",
        notes=[
            "host_externo_sem_acesso_local",
            "prefira=amazon_mirror_primary_via_artifact",
        ],
        command_hint="powershell -File scripts/data_ops_shadow/run_commerce_amazon_mirror_shadow.ps1",
    )


def export_tier1_global_to_dq_stub(*, limit: int, lookup: dict[str, int]) -> ExportBundle:
    return ExportBundle(
        source="tier1_global",
        state="blocked_contract_missing",
        notes=[
            "persistido_local_nao_isola_tier1_do_restante_do_winegod_admin",
            "prefira=tier1_global_via_artifact",
        ],
        command_hint="powershell -File scripts/data_ops_shadow/run_commerce_tier1_global_shadow.ps1",
    )


def export_tier2_to_dq_stub(*, source: str) -> ExportBundle:
    return ExportBundle(
        source=source,
        state="blocked_contract_missing",
        notes=[
            "saida_por_chat_sem_artefato_local_padronizado",
            "prefira=tier2_from_artifact",
        ],
        command_hint=f"powershell -File scripts/data_ops_shadow/run_commerce_{source}_shadow.ps1",
    )


def export_winegod_admin_legacy_mixed_to_dq(*, limit: int, lookup: dict[str, int]) -> ExportBundle:
    """Backfill honesto do historico Tier1/Tier2 misturado.

    Quando nao e possivel provar qual linha veio de Tier1 ou Tier2 sem
    reconstruir metadados, este exporter deixa a lineage explicita como
    `legacy_mixed`. Aparece no dashboard como fonte separada e nao finge ser
    Tier1 ou Tier2 puro.
    """

    bundle = _collect_winegod_candidates(
        limit=limit,
        lookup=lookup,
        source_filter=lambda fonte: not fonte.lower().startswith("amazon"),
        source_name="winegod_admin_legacy_mixed",
    )
    for item in bundle.items:
        item["_source_pipeline"] = "winegod_admin_legacy_mixed"
        item["_source_lineage"] = "legacy_mixed"
    bundle.notes.append("lineage=legacy_mixed")
    return bundle


EXPORTERS = {
    "winegod_admin_world": export_winegod_admin_world_to_dq,
    "vinhos_brasil_legacy": export_vinhos_brasil_legacy_to_dq,
    "amazon_local": export_amazon_local_to_dq,
    "amazon_local_legacy_backfill": export_amazon_local_legacy_backfill_to_dq,
    "amazon_mirror": export_amazon_mirror_to_dq_stub,
    "amazon_mirror_primary": export_amazon_mirror_primary_to_dq,
    "tier1_global": export_tier1_global_to_dq,
    "winegod_admin_legacy_mixed": export_winegod_admin_legacy_mixed_to_dq,
}
