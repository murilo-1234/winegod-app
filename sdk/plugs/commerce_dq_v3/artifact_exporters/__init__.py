"""Exporters de artefato commerce (producers locais).

Cada modulo neste pacote le dados produzidos por scrapers externos (em
`C:\\natura-automation\\` ou bancos locais `winegod_db`/`vinhos_brasil_db`)
e gera o par `<prefix>.jsonl` + `<prefix>_summary.json` no contrato
`docs/TIER_COMMERCE_CONTRACT.md`. Nao escreve em `winegod_db` nem em
`public.wines` / `public.wine_sources`. O plug `commerce_dq_v3.runner`
consome o JSONL depois, em dry-run ou apply gated.

Exporters:

- `amazon_legacy`: one-time backfill do historico Amazon (fonte in
  {`amazon`, `amazon_scraper`, `amazon_scrapingdog`}).
- `amazon_mirror`: feed recorrente do Amazon espelho (fonte = `amazon_playwright`).
- `tier1_global`: feed semanal Tier1 (APIs/sitemap determinstico).
- `tier2_global`: feed semanal Tier2 global (Playwright+IA, pais != br).
- `tier2_br`: feed semanal Tier2 Brasil (Playwright+IA, pais == br).
"""

from __future__ import annotations

from .base import (
    ExportRow,
    ExporterResult,
    build_item,
    write_artifact,
    load_state,
    save_state,
)

__all__ = [
    "ExportRow",
    "ExporterResult",
    "build_item",
    "write_artifact",
    "load_state",
    "save_state",
]
