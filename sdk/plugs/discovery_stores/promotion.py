"""Discovery stores -> public.stores + public.store_recipes promotion.

Dry-run only by default. Real apply requires `authorized=True` AND
`os.environ['DISCOVERY_PROMOTION_AUTHORIZED'] == '1'`. Any other call
raises before touching the DB.

Contract: `docs/DISCOVERY_STORES_PROMOTION_CONTRACT.md`.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sdk.plugs.common import normalize_domain


REPO_ROOT = Path(__file__).resolve().parents[3]
PLANS_DIR = REPO_ROOT / "reports" / "data_ops_promotion_plans"

MIN_PRODUCTS = 10
MIN_SELECTOR_HIT_RATE = 0.8
MIN_CATALOG_URLS = 3
AUTH_ENV = "DISCOVERY_PROMOTION_AUTHORIZED"
_ISO2_RE = re.compile(r"^[A-Z]{2}$")


REASON_CODES = {
    "G1": "minimum_products_below_threshold",
    "G2": "selector_hit_rate_below_threshold",
    "G3": "catalog_pattern_not_validated",
    "G4": "domain_duplicate_after_normalization",
    "G5": "country_iso2_missing_or_invalid",
    "MISSING_LINEAGE": "source_lineage_missing",
}


@dataclass
class CandidateEvaluation:
    normalized_domain: str
    store_name: str | None
    approved: bool
    reason_code: str | None
    reason_detail: str | None
    gates: dict[str, bool]
    recipe_available: bool
    legacy_conflict: bool = False


@dataclass
class PromotionPlan:
    generated_at_utc: str
    total_candidates: int
    approved_stores: int
    approved_recipes: int
    skipped: list[dict] = field(default_factory=list)
    candidates: list[CandidateEvaluation] = field(default_factory=list)
    plan_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at_utc": self.generated_at_utc,
            "total_candidates": self.total_candidates,
            "approved_stores": self.approved_stores,
            "approved_recipes": self.approved_recipes,
            "plan_hash": self.plan_hash,
            "skipped": list(self.skipped),
            "candidates": [asdict(c) for c in self.candidates],
        }


@dataclass
class PromotionResult:
    plan_hash: str
    stores_inserted: int = 0
    recipes_inserted: int = 0
    batches_committed: int = 0
    errors: list[str] = field(default_factory=list)


class StorePromoter:
    """Plans and (if authorized) applies discovery -> stores promotion."""

    def __init__(self, *, existing_store_domains: set[str] | None = None,
                 existing_store_id_by_domain: dict[str, int] | None = None,
                 legacy_recipes_by_store_id: set[int] | None = None):
        self._existing_domains = set(existing_store_domains or ())
        self._existing_store_id_by_domain = dict(existing_store_id_by_domain or {})
        self._legacy_recipes = set(legacy_recipes_by_store_id or ())

    # ------------------------------------------------------------- gates

    def _evaluate_candidate(self, candidate: dict[str, Any]) -> CandidateEvaluation:
        gates = {"G1": False, "G2": False, "G3": False, "G4": False, "G5": False}
        reason_code: str | None = None
        reason_detail: str | None = None

        # lineage is a hard pre-requisite (not a business gate but a contract rule)
        if not candidate.get("source_lineage"):
            return CandidateEvaluation(
                normalized_domain=(candidate.get("normalized_domain") or "").lower(),
                store_name=candidate.get("store_name"),
                approved=False,
                reason_code=REASON_CODES["MISSING_LINEAGE"],
                reason_detail="source_lineage ausente",
                gates=gates,
                recipe_available=False,
            )

        # G5 country ISO2
        country = (candidate.get("country") or "").upper()
        if country and _ISO2_RE.match(country):
            gates["G5"] = True
        else:
            reason_code = REASON_CODES["G5"]
            reason_detail = f"country={candidate.get('country')!r}"

        # G4 duplicate after normalization
        norm = normalize_domain(candidate.get("normalized_domain") or candidate.get("url"))
        gates["G4"] = bool(norm) and norm not in self._existing_domains
        if not gates["G4"] and reason_code is None:
            reason_code = REASON_CODES["G4"]
            reason_detail = f"dominio normalizado ja existe: {norm}"

        # G1 min products
        sample = candidate.get("sample_scrape") or {}
        products = sample.get("products_extractable")
        if isinstance(products, int) and products >= MIN_PRODUCTS:
            gates["G1"] = True
        else:
            if reason_code is None:
                reason_code = REASON_CODES["G1"]
                reason_detail = f"products_extractable={products!r}"

        # G2 selector hit rate
        selectors_declared = sample.get("selectors_declared") or 0
        selectors_matched = sample.get("selectors_matched") or 0
        hit_rate = (
            (selectors_matched / selectors_declared)
            if selectors_declared
            else 0.0
        )
        if selectors_declared and hit_rate >= MIN_SELECTOR_HIT_RATE:
            gates["G2"] = True
        else:
            if reason_code is None:
                reason_code = REASON_CODES["G2"]
                reason_detail = f"selector_hit_rate={hit_rate:.2f}"

        # G3 catalog pattern validated against >=3 distinct URLs
        catalog_patterns = sample.get("catalog_patterns") or []
        distinct_urls = {u for u in catalog_patterns if isinstance(u, str)}
        if len(distinct_urls) >= MIN_CATALOG_URLS:
            gates["G3"] = True
        else:
            if reason_code is None:
                reason_code = REASON_CODES["G3"]
                reason_detail = f"catalog_distinct_urls={len(distinct_urls)}"

        approved = all(gates.values())
        store_id = (
            self._existing_store_id_by_domain.get(norm) if norm else None
        )
        legacy_conflict = bool(
            store_id and store_id in self._legacy_recipes
        )
        return CandidateEvaluation(
            normalized_domain=norm or "",
            store_name=candidate.get("store_name"),
            approved=approved,
            reason_code=None if approved else reason_code,
            reason_detail=None if approved else reason_detail,
            gates=gates,
            recipe_available=bool(candidate.get("recipe_candidate")),
            legacy_conflict=legacy_conflict,
        )

    # ---------------------------------------------------------------- plan

    def plan(self, candidates: list[dict[str, Any]]) -> PromotionPlan:
        evaluated = [self._evaluate_candidate(c) for c in candidates]
        approved = [c for c in evaluated if c.approved]
        skipped = [
            {
                "normalized_domain": c.normalized_domain,
                "reason_code": c.reason_code,
                "reason_detail": c.reason_detail,
            }
            for c in evaluated
            if not c.approved
        ]
        approved_recipes = sum(
            1
            for c in approved
            if c.recipe_available and not c.legacy_conflict
        )
        plan = PromotionPlan(
            generated_at_utc=datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            total_candidates=len(evaluated),
            approved_stores=len(approved),
            approved_recipes=approved_recipes,
            skipped=skipped,
            candidates=evaluated,
        )
        plan.plan_hash = self._plan_hash(plan)
        return plan

    @staticmethod
    def _plan_hash(plan: PromotionPlan) -> str:
        signature = sorted(
            (c.normalized_domain, c.approved, c.reason_code or "")
            for c in plan.candidates
        )
        return hashlib.sha256(
            json.dumps(signature, ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:32]

    # --------------------------------------------------------------- apply

    def apply(
        self,
        plan: PromotionPlan,
        *,
        authorized: bool,
        batch_size: int = 100,
        conn_factory=None,
    ) -> PromotionResult:
        if not authorized:
            raise PermissionError("apply() requires authorized=True")
        if os.environ.get(AUTH_ENV) != "1":
            raise PermissionError(
                f"apply() requires env {AUTH_ENV}=1"
            )
        if batch_size <= 0 or batch_size > 100:
            raise ValueError("batch_size must be in [1, 100] (REGRA 5)")
        if conn_factory is None:
            raise RuntimeError(
                "apply() requires conn_factory (production path not wired in "
                "this session)"
            )
        result = PromotionResult(plan_hash=plan.plan_hash)
        approved = [c for c in plan.candidates if c.approved]
        for i in range(0, len(approved), batch_size):
            batch = approved[i : i + batch_size]
            try:
                conn = conn_factory()
                try:
                    with conn.cursor() as cur:
                        for cand in batch:
                            cur.execute(
                                "INSERT INTO public.stores "
                                "(dominio, nome, pais, origem_descoberta, origem_promocao) "
                                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                                (
                                    cand.normalized_domain,
                                    cand.store_name,
                                    "",  # country backfilled by apply in real path
                                    "discovery_agent_global",
                                    "plug_discovery_stores",
                                ),
                            )
                            result.stores_inserted += 1
                        conn.commit()
                        result.batches_committed += 1
                finally:
                    conn.close()
            except Exception as exc:  # pragma: no cover - reached only if caller wires a broken conn
                result.errors.append(f"{type(exc).__name__}: {exc}")
                raise
        return result

    # --------------------------------------------------------- persistence

    def persist_plan(self, plan: PromotionPlan, *, timestamp: str | None = None) -> Path:
        PLANS_DIR.mkdir(parents=True, exist_ok=True)
        ts = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = PLANS_DIR / f"{ts}_plan.json"
        path.write_text(
            json.dumps(plan.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path


def summary_markdown(plan: PromotionPlan) -> str:
    lines = [
        "# Discovery Stores Promotion Plan",
        "",
        f"- generated_at_utc: `{plan.generated_at_utc}`",
        f"- plan_hash: `{plan.plan_hash}`",
        f"- total_candidates: `{plan.total_candidates}`",
        f"- approved_stores: `{plan.approved_stores}`",
        f"- approved_recipes: `{plan.approved_recipes}`",
        f"- skipped: `{len(plan.skipped)}`",
        "",
        "## Skipped by reason",
    ]
    from collections import Counter

    counter = Counter(s["reason_code"] for s in plan.skipped)
    for code, count in counter.most_common():
        lines.append(f"- `{code}`: `{count}`")
    lines.append("")
    lines.append("## Sample approved (first 5)")
    sample = [c for c in plan.candidates if c.approved][:5]
    for c in sample:
        lines.append(f"- `{c.normalized_domain}` - {c.store_name}")
    return "\n".join(lines) + "\n"


__all__ = [
    "StorePromoter",
    "PromotionPlan",
    "PromotionResult",
    "CandidateEvaluation",
    "MIN_PRODUCTS",
    "MIN_SELECTOR_HIT_RATE",
    "MIN_CATALOG_URLS",
    "AUTH_ENV",
    "REASON_CODES",
    "PLANS_DIR",
    "summary_markdown",
]
