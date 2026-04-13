# Snapshot Oficial -- Auditoria da Cauda Vivino (Etapa 1)

Data execucao: 2026-04-10 19:08:17
Executor: `scripts/audit_tail_snapshot.py`
Referencia: `prompts/PROMPT_CLAUDE_EXECUTOR_ETAPA1_SNAPSHOT_RECONCILIACAO_AUDITORIA_CAUDA_VIVINO_2026-04-10.md`

## Contagens Oficiais -- Render (live)

| Metrica | Query | Resultado |
|---|---|---|
| wines total | `SELECT COUNT(*) FROM wines` | 2,506,441 |
| wines com vivino_id | `SELECT COUNT(*) FROM wines WHERE vivino_id IS NOT NULL` | 1,727,058 |
| wines sem vivino_id (cauda) | `SELECT COUNT(*) FROM wines WHERE vivino_id IS NULL` | 779,383 |
| wine_aliases total | `SELECT COUNT(*) FROM wine_aliases` | 43 |
| wine_aliases approved | `SELECT COUNT(*) FROM wine_aliases WHERE review_status = 'approved'` | 43 |
| canonical_wine_id distintos (approved) | `SELECT COUNT(DISTINCT canonical_wine_id) FROM wine_aliases WHERE review_status='approved'` | 23 |
| wine_sources total | `SELECT COUNT(*) FROM wine_sources` | 3,484,975 |
| stores total | `SELECT COUNT(*) FROM stores` | 19,889 |
| cauda sem wine_sources | `...vivino_id IS NULL AND NOT EXISTS...` | 8,071 |
| cauda com wine_sources | `...vivino_id IS NULL AND EXISTS...` | 771,312 (FALLBACK por subtracao: wines_sem_vivino_id - cauda_sem_sources; query EXISTS original derrubou a conexao SSL) |

### Distribuicao wine_aliases

| review_status | source_type | count |
|---|---|---|
| approved | manual | 43 |

## Contagens Oficiais -- Bancos Locais

| Base | Metrica | Query | Resultado |
|---|---|---|---|
| vivino_db | vivino_vinhos total | `SELECT COUNT(*) FROM vivino_vinhos` | 1,738,585 |
| winegod_db | y2_results matched com vivino_id NOT NULL | `SELECT COUNT(*) FROM y2_results WHERE status='matched' AND vivino_id IS NOT NULL` | 1,465,480 |
| winegod_db | y2_results matched com score>=0.7 | `SELECT COUNT(*) FROM y2_results WHERE status='matched' AND match_score>=0.7 AND vivino_id IS NOT NULL` | 648,374 |

## Comparacao com Numeros de Referencia (prompt Etapa 1)

| Metrica | Referencia | Live | Delta | Drift % | Status |
|---|---|---|---|---|---|
| wines_total | 2,506,441 | 2,506,441 | +0 | 0.00% | OK |
| wines_com_vivino_id | 1,727,058 | 1,727,058 | +0 | 0.00% | OK |
| wines_sem_vivino_id | 779,383 | 779,383 | +0 | 0.00% | OK |
| wine_aliases_total | 43 | 43 | +0 | 0.00% | OK |
| wine_aliases_approved | 43 | 43 | +0 | 0.00% | OK |
| canonical_distintos | 23 | 23 | +0 | 0.00% | OK |
| wine_sources_total | 3,484,975 | 3,484,975 | +0 | 0.00% | OK |
| stores_total | 19,889 | 19,889 | +0 | 0.00% | OK |
| cauda_sem_sources | 8,071 | 8,071 | +0 | 0.00% | OK |
| cauda_com_sources | 771,312 | 771,312 | +0 | 0.00% | OK |
| vivino_vinhos_total | 1,738,585 | 1,738,585 | +0 | 0.00% | OK |
| y2_matched_vivino | 1,465,480 | 1,465,480 | +0 | 0.00% | OK |
| y2_matched_07 | 648,374 | 648,374 | +0 | 0.00% | OK |
| only_vivino_db | 11,527 | 11,527 | +0 | 0.00% | OK |
| only_render | 0 | 0 | +0 | 0.00% | OK |

## Veredito

**SNAPSHOT ESTAVEL.** Todas as metricas dentro da margem aceitavel (<5%). Contexto estavel para a Etapa 2.

## Notas

- `cauda_com_sources` foi calculado por FALLBACK (subtracao) porque a query EXISTS derrubou a conexao SSL no plano Render Basic. A subtracao e matematicamente equivalente: os subconjuntos `cauda_sem_sources` e `cauda_com_sources` particionam exatamente a cauda (`vivino_id IS NULL`), entao `cauda_com_sources = wines_sem_vivino_id - cauda_sem_sources`.
- Documentos historicos (HANDOFF_AUDITORIA 2026-04-06, PROMPT_RECRIAR) usam numeros diferentes. Detalhes em `tail_audit_contradictions_2026-04-10.md`.

