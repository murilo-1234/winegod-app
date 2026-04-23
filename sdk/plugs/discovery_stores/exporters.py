from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from sdk.plugs.common import normalize_domain, resolve_store_id
from .schemas import ExportBundle


NATURA_ROOT = Path("C:/natura-automation")
DISCOVERY_PHASES_PATH = NATURA_ROOT / "agent_discovery" / "discovery_phases.json"
DISCOVERY_GLOB = "ecommerces_vinhos_*_v2.json"
TIER1_PLATFORMS = {
    "dooca",
    "loja_integrada",
    "magento",
    "mercado_shops",
    "nuvemshop",
    "shopify",
    "tray",
    "vtex",
    "vtex_io",
    "woocommerce",
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def infer_tier_hint(platform: str | None) -> str:
    value = (platform or "").strip().lower()
    if value in TIER1_PLATFORMS:
        return "tier1_template"
    if value in {"", "custom", "erro", "nextjs_custom", "unknown", "wix"}:
        return "tier2_manual"
    return "tier1_candidate"


def infer_recipe_candidate(platform: str | None, url: str | None) -> dict[str, Any] | None:
    if not url:
        return None
    value = (platform or "").strip().lower()
    if not value or value == "erro":
        return None

    metodo_listagem = "sitemap"
    metodo_extracao = "html"
    usa_playwright = value in {"custom", "nextjs_custom", "wix"}
    anti_bot = "basic" if usa_playwright else "none"
    if value in {"shopify", "vtex", "vtex_io"}:
        metodo_listagem = "api"
    elif value in TIER1_PLATFORMS:
        metodo_listagem = "sitemap"

    return {
        "plataforma": value,
        "metodo_listagem": metodo_listagem,
        "metodo_extracao": metodo_extracao,
        "usa_playwright": usa_playwright,
        "anti_bot": anti_bot,
        "notas": "recipe_candidate_only; staging_only",
        "url_sitemap": url.rstrip("/") + "/sitemap.xml",
    }


def infer_validation_status(store: dict[str, Any]) -> str:
    url = store.get("url")
    if not url:
        return "missing_url"
    if store.get("tem_ecommerce") is False:
        return "no_ecommerce"
    if bool(store.get("verificado")):
        return "verified"
    platform = str(store.get("plataforma") or "").strip().lower()
    if platform in {"", "erro", "unknown"}:
        return "needs_validation"
    return "observed"


def export_agent_discovery(*, limit: int, lookup: dict[str, int]) -> ExportBundle:
    files = sorted(
        NATURA_ROOT.glob(DISCOVERY_GLOB),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    phases = _load_json(DISCOVERY_PHASES_PATH) if DISCOVERY_PHASES_PATH.exists() else {}
    phase_map = (phases.get("countries") or {}) if isinstance(phases, dict) else {}

    if not files:
        return ExportBundle(
            source="agent_discovery",
            state="blocked_missing_source",
            notes=["nenhum arquivo ecommerces_vinhos_*_v2.json encontrado"],
        )

    items: list[dict[str, Any]] = []
    statuses = Counter()
    platforms = Counter()
    known_store_hits = 0
    skipped_missing_domain = 0

    for path in files:
        payload = _load_json(path)
        country = str(payload.get("codigo") or payload.get("pais") or "").upper() or None
        gerado_em = payload.get("gerado_em")
        country_phase = phase_map.get(country or "", {})
        for store in payload.get("lojas") or []:
            if len(items) >= limit:
                break
            if not isinstance(store, dict):
                continue
            url = store.get("url")
            domain = normalize_domain(url)
            if not domain:
                skipped_missing_domain += 1
                continue

            platform = str(store.get("plataforma") or "unknown").strip().lower()
            validation_status = infer_validation_status(store)
            known_store_id = resolve_store_id(url, lookup)
            recipe_candidate = infer_recipe_candidate(platform, url)
            if known_store_id:
                known_store_hits += 1
            statuses[validation_status] += 1
            platforms[platform or "unknown"] += 1

            items.append(
                {
                    "source": "agent_discovery",
                    "domain": domain,
                    "normalized_domain": domain,
                    "url": url,
                    "store_name": store.get("nome"),
                    "country": country,
                    "platform": platform or None,
                    "validation_status": validation_status,
                    "tier_hint": infer_tier_hint(platform),
                    "already_known_store": bool(known_store_id),
                    "known_store_id": known_store_id,
                    "recipe_candidate": recipe_candidate,
                    "tem_ecommerce": store.get("tem_ecommerce"),
                    "verificado": bool(store.get("verificado")),
                    "city": store.get("cidade"),
                    "state_code": store.get("estado") or store.get("regiao"),
                    "scope_estimate": store.get("abrangencia_estimada"),
                    "discovery_method": store.get("como_descobriu"),
                    "discovery_phase_flags": {
                        key: value
                        for key, value in country_phase.items()
                        if key.startswith("f")
                    },
                    "source_lineage": {
                        "source_system": "agent_discovery",
                        "source_kind": "file",
                        "source_pointer": str(path),
                        "source_record_count": 1,
                        "notes": f"country={country}; generated={gerado_em}"[:256],
                    },
                }
            )
        if len(items) >= limit:
            break

    notes = [
        f"items_exported={len(items)}",
        f"countries_seen={len({item.get('country') for item in items if item.get('country')})}",
        f"known_store_hits={known_store_hits}",
        f"skipped_missing_domain={skipped_missing_domain}",
        f"phase_file_present={DISCOVERY_PHASES_PATH.exists()}",
    ]
    for name, count in platforms.most_common(5):
        notes.append(f"top_platform={name}:{count}")
    for name, count in statuses.most_common(5):
        notes.append(f"status_count={name}:{count}")

    return ExportBundle(
        source="agent_discovery",
        state="observed" if items else "blocked_missing_source",
        items=items,
        notes=notes,
    )


EXPORTERS = {
    "agent_discovery": export_agent_discovery,
}
