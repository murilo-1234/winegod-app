# Delivery Report: nota_wcf v2

**Data:** 2026-04-16
**Status:** IMPLEMENTADO — aguardando deploy

---

## Gate 0: Decisao do contador publico

`vivino_reviews` foi APROVADO como `public_ratings_count` canonico.

Evidencias:
- 691.995 vinhos com `vivino_rating > 0`, TODOS com `vivino_reviews` preenchido (zero gap).
- Range: 1 ate ~6.752 (sample). Valores >1.000 existem abundantemente.
- Distribuicao consistente com contagem publica de ratings.
- Bloco 309k estimado: ~297.400 (coerente com handoff de 309.616).
- Decisao: usar `vivino_reviews` diretamente como alias em runtime, sem migration.

---

## Arquivos criados

| Arquivo | Descricao |
|---|---|
| `backend/services/note_v2.py` | Engine canonica de resolucao de nota v2 |
| `scripts/rebuild_context_buckets.py` | Script idempotente de rebuild da Cascata B |
| `scripts/validate_note_v2.py` | Script de validacao read-only |
| `backend/tests/test_note_v2.py` | 29 testes unitarios |
| `database/migrations/013_add_context_buckets.sql` | Migration da tabela de buckets |
| `database/rollback/013_rollback.sql` | Rollback da migration |
| `reports/2026-04-16_nota_wcf_v2_delivery.md` | Este relatorio |

## Arquivos modificados

| Arquivo | Mudanca |
|---|---|
| `backend/services/display.py` | Delega para note_v2. Legacy preservada como `_resolve_note_legacy` |
| `backend/tools/search.py` | SELECT: +vivino_reviews, +pais, +sub_regiao |
| `backend/db/models_share.py` | SELECT: +vivino_reviews, +pais, +sub_regiao |
| `backend/tools/compare.py` | 2 SELECTs: +vivino_reviews, +pais, +sub_regiao |
| `backend/tools/resolver.py` | Expoe public_ratings_bucket no contexto (3 pontos) |
| `backend/routes/chat.py` | Bucket no batch context builder |
| `backend/prompts/baco_system.py` | Contextual + bucket no prompt full e short |
| `scripts/calc_score.py` | Usa note_v2 + BucketCache (fail-fast) |
| `scripts/calc_score_incremental.py` | Idem |
| `scripts/calc_wcf_fast.py` | Removido winegod_score_type write |
| `scripts/calc_wcf.py` | Removido winegod_score_type write |
| `scripts/upload_wcf_render.py` | Removido winegod_score_type write |
| `scripts/upload_wcf_remaining.py` | Removido winegod_score_type write |
| `scripts/upload_wcf_batched_remaining.py` | Removido winegod_score_type write |
| `scripts/calc_wcf_batched.py` | Removido winegod_score_type write |
| `scripts/calc_wcf_step5.py` | Removido winegod_score_type write |
| `frontend/lib/types.ts` | nota: number|null, nota_tipo: +contextual+null, +nota_bucket |
| `frontend/components/wine/ScoreBadge.tsx` | Null guard, contextual visual |
| `frontend/components/wine/WineCard.tsx` | Null guard no ScoreBadge render |
| `frontend/app/c/[id]/page.tsx` | toWineData sem coercao, ShareWine com contextual+bucket |

## Arquivos NAO modificados (confirmados OK)

| Arquivo | Motivo |
|---|---|
| `backend/tools/details.py` | Usa SELECT * — ja traz todos os campos |
| `backend/routes/chat.py` | Nao toca na nota diretamente (exceto batch context) |

---

## Testes

29 testes unitarios criados e passando:
- 8 testes de selo (verified/estimated/contextual/None)
- 7 testes de fonte (wcf_shrunk/direct, vivino_delta/fallback, contextual, ai, none)
- 3 testes de clamp (upper, lower, assimetrico)
- 3 testes de shrinkage (50/50, high sample, low sample)
- 1 teste de bucket ranges (16 assertions)
- 1 teste de preservacao de dados (nao muta wine dict)
- 3 testes de consistencia (public_ratings_count, null, 2 casas decimais)
- 3 testes de integracao (contextual confirmed, payload structure, cenario 309k)

---

## Buckets materializados

Tabela `wine_context_buckets` criada e populada (confirmado):
- sub_regiao_tipo: 590 buckets
- regiao_tipo: 6.358 buckets
- pais_tipo: 302 buckets
- vinicola_tipo: 195.328 buckets
- **Total: 202.578 buckets**

Rebuild usa INSERT ON CONFLICT (sem janela vazia).

---

## Validacao com dados reais (com buckets carregados)

BucketCache: 202.578 buckets carregados.

| Cenario | Wines | Selo v2 | Fonte v2 |
|---|---|---|---|
| 309k (75+ ratings, WCF<25) | 50 | 100% verified | 94% vivino_contextual_delta, 6% vivino_fallback |
| WCF robusto (sample>=50) | 50 | 98% verified, 2% estimated | 100% wcf_shrunk |
| Sem vivino + WCF | 0 | (sample vazio) | - |
| Estimated 25-74 | 50 | 100% estimated | 92% vivino_contextual_delta, 4% vivino_fallback, 4% wcf_shrunk |
| Sem dados | 50 | 94% None, 6% contextual | 94% none, 6% contextual |

Distribuicao global:
- Tipos: verified=99, estimated=51, None=47, contextual=3
- Fontes: vivino_contextual_delta=93, wcf_shrunk=52, none=47, vivino_fallback=5, contextual=3

Deltas vs legacy:
- 132 vinhos com delta > 0.01
- Delta maximo: 0.36 (vivino_contextual_delta vs estimated legacy)
- Maioria dos deltas entre 0.10-0.30 (esperado pelo clamp assimetrico e shrinkage)

Integridade:
- vivino_reviews > 500: ~113.900 (dado bruto intacto)

Testes com buckets reais:
- WCF shrunk (Mendoza tinto): nota=4.16 (bucket com 13.722 feeders)
- Vivino+delta (Mendoza tinto): nota=3.98
- Contextual puro (Mendoza tinto): nota=3.37 (stddev=0.538, penalidade aplicada)

---

## Ordem de deploy recomendada

1. ~~Aplicar migration 013~~ (ja aplicada)
2. ~~Popular buckets~~ (ja populada)
3. Deploy frontend PRIMEIRO (retrocompativel)
4. Validar frontend com backend antigo
5. Deploy backend
6. Validar amostras reais
7. Snapshot de scores: `CREATE TABLE scores_backup_pre_v2 AS SELECT id, winegod_score, winegod_score_type, winegod_score_components FROM wines WHERE winegod_score IS NOT NULL`
8. Rodar recalculo de score (batch)
9. Validar scores

---

## Rollback

- **Antes do recalculo de score (passos 1-6):** reverter backend para legacy. Zero inconsistencia.
- **Depois do recalculo (passo 7+):** restaurar scores do snapshot + reverter backend.
- Frontend novo e retrocompativel — nao precisa de rollback obrigatorio.
- Dados brutos nunca tocados.

---

## Pendencias para apos deploy

- Monitorar distribuicao de `display_note_type` em producao
- Agendar rebuild periodico de buckets (semanal)
- Enrichment de `pais` para vinhos sem pais (maior alavanca de cobertura)
- Considerar `uvas` como refinador em versao futura
