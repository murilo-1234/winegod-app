"""winegod_scraper_sdk.adapters — observers read-only de fontes reais (Fase 4).

Cada adapter:
- Lê SELECT de uma fonte existente (sem INSERT/UPDATE/DELETE).
- Calcula métricas sintéticas.
- Usa SDK para reportar via /ops/*.
- items_final_inserted sempre 0.
- Sem PII em ops.*.
"""
