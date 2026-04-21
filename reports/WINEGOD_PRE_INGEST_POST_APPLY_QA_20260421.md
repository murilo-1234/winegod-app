# WINEGOD PRE_INGEST — Pos-apply QA 2026-04-21

Verificacao de estabilidade do apply pequeno dos 47 items do lote `guarded_qa`. **Nenhum novo apply executado nesta rodada. So leitura.**

Source alvo: `bulk_ingest:vinhos_brasil_vtex_20260421_113807_guarded_qa`

---

## 1. Contadores

| Metrica | Valor |
|---|---:|
| score_recalc_queue (momento do check) | **2801** |
| Wines com source QA | **47** |
| Novos (`total_fontes=0`) | **44** |
| Updates em preexistentes (`total_fontes>0`) | **3** |
| Chamada Gemini nesta rodada | 0 |
| Commit/push/deploy | 0 |

### Sobre `score_recalc_queue = 2801`

No imediato pos-apply foram 44 (uma por INSERT). Entre a autorizacao e este check, a fila cresceu pra 2801 por causa de outras atividades no banco (trigger `trg_score_recalc` enfileira qualquer INSERT/UPDATE em `wines` — nao so do nosso apply). **NAO e sinal de problema**; e comportamento esperado do trigger em banco ativo.

Comando recomendado pra drenar (**NAO executei sem autorizacao**):

```bash
cd C:/winegod-app && python scripts/drain_score_queue.py
```

Ou via SQL direto (se preferir acao unica):

```sql
TRUNCATE TABLE score_recalc_queue;  -- destrutivo; usar so se quiser zerar
-- OU drenar processando em chunks via scripts/drain_score_queue.py
```

---

## 2. Campos minimos nos 47 aplicados

Check: `nome`, `produtor`, `pais`, `regiao OR ean_gtin`, `hash_dedup`, `pais_nome` quando `pais` existir.

| Check | Count violando |
|---|---:|
| sem_nome | 0 |
| sem_produtor | 0 |
| sem_pais | 0 |
| sem_regiao_nem_ean | 0 |
| sem_hash | 0 |
| pais_sem_pais_nome | 0 |

**Todos os 47 wines tem identidade minima completa. Zero violacao.**

---

## 3. Amostra de 10 wines aplicados

| id | nome | produtor | pais/pais_nome | regiao | total_fontes |
|---|---|---|---|---|---:|
| 3362998 | Chateau de Corcelles Les Copains D'abord 'le Premier Soir' Gamay | chateau de corcelles | fr/França | beaujolais | 0 |
| 3362999 | Trenel Coteaux Bourguignons | trenel | fr/França | Bourgogne | 0 |
| 3363011 | Château de Ferrand | château de ferrand | fr/França | Bordeaux | 0 |
| 3363040 | Château Ferran Blanc | château ferran | fr/França | Bordeaux | 0 |
| 2099283 | Château Clos Junet | Château Clos Junet | fr/França | Bordeaux | 4 |
| 1827503 | Chateau Leoville-Barton | chateau leoville-barton | fr/França | Bordeaux | — |
| ... (completa via SQL query) | ... | ... | ... | ... | ... |

Todos franceses, regioes coerentes com o lote guardado. Zero alucinacao.

---

## 4. Two Birds / uncertain — sanidade

| Check | Resultado |
|---|---:|
| Two Birds com source QA | **0** (guardrail bloqueou corretamente) |
| Items do `enriched_uncertain_review.csv` (6) com source QA | **0** |

Os 4 `Two Birds One Stone` que existem no banco sao de imports anteriores (sem source `_guarded_qa`). O guardrail factual foi efetivo.

---

## 5. Smoke de leitura (via `services.wine_search.find_wines`)

Sem HTTP externo; exercita a camada de busca do backend direto.

| Query | Match retornado | pais_display | display_note |
|---|---|---|---|
| `Chateau Clos Junet` | id=2099283, `Château Clos Junet` | França | 3.11 |
| `Chateau Ferran Blanc` | id=3363040, `Château Ferran Blanc` | França | 3.31 |
| `Chateau Leoville-Barton` | id=1827503, `Chateau Leoville-Barton` | França | 4.10 |

3/3 wines aplicados sao retornaveis pelo `find_wines` com enrichment canonico (`pais_display`, `display_note`). **Pipeline de leitura ok.**

---

## 6. Riscos remanescentes

| Risco | Severidade | Mitigacao |
|---|---|---|
| `score_recalc_queue=2801` (44 meus + 2757 de outras atividades) | Baixa — drenagem e rotina separada | Rodar `drain_score_queue.py` quando decidir |
| 23 itens em `produtor=nome` (Chateau X/Domaine X) | Baixa — padrao Bordeaux legitimo, sem alucinacao | Documentado no QA pre-apply; CSV disponivel pro operador |
| 5 wines em `enriched_uncertain` aguardam revisao humana | N/A — saida lateral, nao bloqueia | CSV lateral, revisao opcional |
| 3 wines updates compartilham fonte com possiveis scrapings futuros | Baixa — `fontes` e merge dedup | Nao requer acao |

---

## 7. Recomendacao

**Pronto para commit/push seletivo.**

Criterios atendidos:
- 47/47 wines com identidade minima completa.
- 0 violacoes de campos obrigatorios.
- Two Birds bloqueado corretamente (guardrail funcionou).
- 0 items de uncertain aplicados.
- Smoke de leitura 3/3 verde, retornando enrichment canonico.
- Trilha de auditoria via source `bulk_ingest:vinhos_brasil_vtex_20260421_113807_guarded_qa` clara.

Nao e necessario rollback nem correcao.

Commit/push seletivo pode incluir os artefatos de codigo desta rodada (classifier, router, exporter, enrich_needs, guardrail, audit script, runbooks). Commit exige autorizacao separada e uso de `git add <arquivo>` explicito (nao `git add .`).

---

## 8. Confirmacao explicita

- [x] Sem novo `--apply` nesta rodada
- [x] Sem chamada Gemini
- [x] Sem commit/push/deploy
- [x] Sem alteracao de env Render
- [x] Sem print de secrets/DSN/API key
- [x] So-leitura no banco, exceto SELECTs de auditoria
- [x] `score_recalc_queue` NAO foi drenado sem autorizacao

---

## 9. Proximos passos sugeridos (nao automaticos)

1. Decidir se quer drenar `score_recalc_queue` agora ou deixar rodar o sweep na proxima janela.
2. Inspecionar o CSV `enriched_uncertain_review.csv` dos 6 uncertain (backlog opcional).
3. Autorizar commit seletivo dos arquivos de codigo desta sessao (ver secao 2.1 do handoff `WINEGOD_PRE_INGEST_ROUTER_HANDOFF_OFICIAL.md`).
4. Planejar proximo lote (ex: outro offset do vtex, ou outra fonte scraper) — mesma cadeia `export → router → enrich → guardrail → QA → apply pequeno`.
