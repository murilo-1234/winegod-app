# WINEGOD_PAIS_RECOVERY — Checkpoint Fase 0 (Preflight)

Data: 2026-04-21
Branch: i18n/onda-2

## Estado do banco

| Metrica | Valor |
|---|---|
| wines total | 2.506.450 |
| wines ativos (suppressed_at IS NULL) | 2.225.822 |
| com pais | 2.147.666 (96,49%) |
| sem pais (aceitos como residuais) | 78.156 (3,51%) |
| com teor_alcoolico | 415.088 |
| com harmonizacao | 397.179 |
| com descricao | 157.183 |
| score_recalc_queue | 0 |

## Buckets (wine_context_buckets)

| Tier | Buckets |
|---|---:|
| sub_regiao_tipo | 590 |
| pais_tipo | 304 |
| regiao_tipo | 6.358 |
| vinicola_tipo | 195.328 |
| **Total** | **202.580** |

## Tabelas temp

| Tabela | Status |
|---|---|
| tmp_gemini_v3_updates | AUSENTE (OK) |
| pais_enrichment_queue | AUSENTE (OK) |
| tmp_regiao_pais_lookup | AUSENTE (OK) |
| pais_recovery_candidates | AUSENTE (OK) |
| tmp_produtor_95_safe | AUSENTE (OK) |
| vivino_vinicolas_lookup | PRESENTE (mantida) |
| notwine_suppression_log | PRESENTE (mantida) |

## Triggers

- `trg_score_recalc` em `wines`: **habilitado** (state=O, origin enabled).

## Queries ativas no Postgres

Nenhuma query ativa alem do backend normal. Sem transacao pendurada.

## Processos locais

- `drain_score_queue.py`: morto
- `calc_score_incremental.py`: morto
- `rebuild_context_buckets.py`: terminado (ultimo update em buckets 35+ min atras)

## Git

Branch `i18n/onda-2` com mudancas pre-existentes (i18n wave 2). Para esta sessao de pais_recovery/housekeeping vou manter commits isolados e nao usar `git add .`.

## Conclusao

Banco consistente e pronto pra Fase 1. Housekeeping pos-Gemini fechado. Sem processos travados. Triggers no estado esperado. Proximo: pipeline unico de ingestao.
