# Tail Candidate Runner -- Diagnostico de Performance (Demanda 6B)

Data de execucao: 2026-04-11
Executor: medicoes diretas no runner `scripts/run_candidate_fanout_pilot.py` (D6A) em um subset real da cauda.

Snapshot oficial do projeto ancorado em 2026-04-10.

## Primeira acao obrigatoria

- Processo `python scripts/run_candidate_fanout_pilot.py` **nao estava rodando** no inicio desta demanda.
  - `tasklist | findstr python` sem resultados.
  - Checkpoint oficial (`tail_candidate_fanout_pilot_checkpoint_2026-04-10.json`) ja marcava `finalized_partial = true`, `done = false`, `verdict = NAO_PRONTO`, com 5/40 batches concluidos, coerente com o fechamento administrativo da D6A.
- Nenhum processo foi encerrado nesta sessao. Registrado como: **processo ja encerrado**.

## Fatos oficiais de D6A

Fonte: `tail_candidate_fanout_pilot_checkpoint_2026-04-10.json` + `tail_candidate_fanout_pilot_summary_2026-04-10.md`.

- batches concluidos: 5
- itens executados: 1.250
- detail rows: 12.617
- per_wine rows: 1.250
- batch timings (s): `1442.961, 2253.460, 2024.929, 1970.054, 2629.141`
- mediana pos-bootstrap: **2139.2s por batch de 250** (~8.56s por wine)
- piloto 10.000 projetado: **~23.6h**
- full 779.383 projetado: **~77.2 dias**
- veredito: **NAO PRONTO**

## Desenho do runner D6A (resumo)

O runner D6A (`scripts/run_candidate_fanout_pilot.py`):
- seleciona 10.000 render_wine_ids determinsticamente do enriched CSV
- para cada batch de 250 wines:
  - `fetch_source_info(batch_ids)` -- 1 query Render para buscar metadados dos 250
  - para cada wine sequencial:
    - 6 canais (3 Render + 3 Import), cada um = 1 query (com fallback ILIKE no `channel_render_produtor` se trgm retornar 0)
- escreve arquivo parcial atomico e atualiza checkpoint
- consolida no final em `detail.csv.gz` + `per_wine.csv.gz`

## Contagem de round-trips (baseline D6A)

Por wine:
- 6 queries (3 local/Render + 3 local/vivino_db)
- `channel_render_produtor` pode adicionar 1 fallback ILIKE quando trgm retorna 0 (medido: raro na cauda nas medicoes)

Por batch de 250:
- 1 query Render (fetch_source_info)
- 250 × 6 queries = **1.500 queries** ao pool local (winegod_db + vivino_db)
- total: **~1.501 queries/batch**

Por piloto 10.000:
- 40 × 1.501 = **60.040 queries** ao local
- 40 × 1 = **40 queries** ao Render (fetch source)
- + 2 queries Render pesadas de bootstrap (carregar vivino_id_set)
- + 1 query vivino_db pesada de bootstrap (carregar vivino_ids) + insercao em TEMP TABLE

Por full 779.383:
- 3.118 batches × 1.501 = **~4.680.000 queries** ao local
- 3.118 queries fetch_source_info ao Render

## Custo observado (medicao direta, amostra real)

Medicao por wine, 3 wines reais do inicio do piloto (`pilot_ids[:3]` = 1740586, 1740587, 1740588):

| wine | produtor / nome | total (ms) |
|---|---|---|
| 1740586 | sakuramasamune / `012022 sakuramasamune ...` | 10.819 |
| 1740587 | artadi / `033 pecado del paraiso` | 13.147 |
| 1740588 | adobe / `01 adobe gewurz` | 6.976 |

Quebra por canal (ms):

| canal | 1740586 | 1740587 | 1740588 |
|---|---|---|---|
| render_nome_produtor | 5.587,8 | 8.449,5 | 2.873,3 |
| render_nome | 1.715,4 | 2.179,6 | 1.438,1 |
| render_produtor | 1.200,8 | 1.697,8 | 1.663,0 |
| import_nome_produtor | 1.814,4 | 321,5 | 379,5 |
| import_nome | 263,3 | 246,5 | 311,7 |
| import_produtor | 237,9 | 250,2 | 309,8 |

**Observacao critica**: os **3 canais Render** sao os donos do custo. Somam ~75% do tempo por wine. `channel_render_nome_produtor` sozinho gasta 3-8s por wine, dominando tudo.

Custo total sequencial medido (10 wines): **89,8s = 8,98s por wine**. Extrapolando para 250: ~2.245s, alinhado com os 2.139s da mediana pos-bootstrap oficial.

## Onde esta o custo -- mapa linha-a-linha

### Canais Render (lentos)

- Arquivo: `scripts/build_candidate_controls.py`
  - `channel_render_nome_produtor` (linhas ~453-475): `similarity(texto_busca, %s)` com GIN trgm index `idx_vm_texto_trgm` em `vivino_match.texto_busca`. Query texto e `prod + ' ' + nome` (longo), a `ORDER BY sim DESC LIMIT 100` forca o walk do indice GIN para todos os trigramas do texto combinado e re-ranking em memoria. **Esta e a query mais cara observada (2,8-8,5s)**.
  - `channel_render_nome` (linhas ~478-498): mesma estrutura contra `nome_normalizado`. ~1,4-2,2s.
  - `channel_render_produtor` (linhas ~501-539): similaridade em `produtor_normalizado` + fallback ILIKE com longest word. ~1,2-1,7s.

### Canais Import (baratos)

- Arquivo: `scripts/build_candidate_controls.py`
  - `channel_import_nome_produtor` (linhas ~554-576), `channel_import_nome` (linhas ~579-599), `channel_import_produtor` (linhas ~602-622): ILIKE com `JOIN _only_vivino t ON t.id = v.id` em `vivino_vinhos`. O JOIN reduz drasticamente a superficie para ~11.527 rows (`only_vivino_db`), entao os ILIKEs sao baratos (~200-1800ms mesmo com o pior caso). **Nao sao o gargalo.**

### Bootstrap (pago 1x por sessao)

- `bootstrap_render_vivino_id_set` (linhas ~208-237 do D5): stream de `SELECT vivino_id FROM wines WHERE vivino_id IS NOT NULL` no Render (Oregon), ~1.727.058 rows. Varia muito por execucao devido a latencia Brasil->Oregon (medicoes desta sessao: 67-247s).
- `bootstrap_only_vivino_db_set` (linhas ~240-262 do D5): stream de `SELECT id FROM vivino_vinhos` no vivino_db local, ~1.738.585 rows. Rapido (<15s, local).
- `setup_only_vivino_temp` (linhas ~643-655 do D5): CREATE TEMP TABLE `_only_vivino` + INSERT de ~11.527 ids via `execute_values`. ~1-3s por conexao vivino_db.

Nenhum deles e custo **por wine**. O bootstrap e **custo fixo por processo** e amortiza ao longo do piloto.

### Fetch source info

- `fetch_source_info` (runner D6A): `SELECT ... FROM wines WHERE id = ANY(%s)` ao Render, **1 query por batch de 250**. Custa 1-5s (rede Brasil->Oregon). Total por piloto: **40 queries = ~100s** -- **nao e o gargalo**.

## O que dessa lista e local vs Render

- **Render** (remoto, Oregon): `bootstrap_render_vivino_id_set` + `fetch_source_info` por batch. Total ~250s numa sessao.
- **Local `winegod_db`** (localhost): os 3 canais Render de busca via `vivino_match` trgm. Esta e a fonte dominante do custo (~75% do tempo de batch).
- **Local `vivino_db`** (localhost): os 3 canais Import + setup temp table. Custo marginal.

## O que e intrinsicamente lento no desenho atual

1. **Sequencialidade pura**: o runner D6A roda wine-a-wine, sem parallelismo. Cada batch de 250 espera cada query executar em serie, mesmo em conexoes locais que poderiam suportar concorrencia.
2. **Trgm GIN sobre texto longo com LIMIT 100**: `similarity(texto_busca, q) DESC LIMIT 100` onde `q` e 30-80 caracteres forca o indice a scanear muitos trigramas e retornar grande conjunto, que e re-ordenado. Este custo vive no Postgres e nao diminui por batching ingenuo.
3. **Temp table rebuild**: cada conexao vivino_db precisa do `_only_vivino` construido. O runner D6A faz 1x por sessao (aceitavel). Em qualquer desenho com pool de conexoes, cada conexao precisa do seu temp table (multiplicando o custo de setup).
4. **Custo fetch por wine nao ameliorado por batching SQL**: testes com `LATERAL JOIN` contra VALUES clause de 50 wines retornaram **1,34x mais lento** que o loop (96,7s vs 72,3s no canal `render_nome_produtor`). O planner do Postgres nao parametriza bem a similaridade com texto de coluna no LATERAL; o loop de single-row queries continua sendo competitivo ou melhor.

## Otimizacoes que preservam semantica

**Aplicadas no novo runner `run_candidate_fanout_fast.py`:**

1. **Pool de workers threads com conexoes persistentes** (impacto principal). Cada worker mantem 1 `local_conn` + 1 `viv_conn` por toda a sessao, constroi o temp table `_only_vivino` UMA UNICA VEZ, e processa multiplos wines sequencialmente dentro do worker. Com 32 workers em paralelo, o wall-time por wine cai de ~8,98s para **~3,23s**.
2. **Memoizacao compartilhada dos canais por produtor** (impacto secundario). Em sample real de 250 wines da cauda, 22% dos valores de `produtor_normalizado` se repetem. O cache guarda o resultado SQL (list de candidate dicts) por chave de produto e reusa entre wines; o scoring segue sendo per-wine. Como `score_candidate` nao usa `trgm_sim`, o resultado e deterministico.
3. **Prefetch de source info em 1 query unica** para todo o slice (vs 1 por batch). Reduz 40 queries Render para 1.

Observadas (estatisticas oficiais do checkpoint):
- `render_produtor_hits = 52 / misses = 183` (22,1% hit)
- `import_produtor_hits = 54 / misses = 181` (23,0% hit)
- `import_nome_hits = 48 / misses = 196` (19,7% hit)

## Otimizacoes que MUDARIAM logica (proibidas)

Estas NAO foram aplicadas:

1. Aumentar `pg_trgm.similarity_threshold` -- reduziria o conjunto de candidatos retornado do WHERE. **Proibido**: mudaria o universo que alimenta o scoring.
2. Substituir `ORDER BY similarity(...) DESC LIMIT 100` por um LIMIT menor -- menos candidatos para o re-rank Python. **Proibido**: muda top3 em empates.
3. Trocar os 6 canais por menos canais -- `ordem dos canais` e `existencia de cada canal` estao congelados.
4. Adicionar filtros determinativos (e.g. `pais_codigo = X`, `tipo = Y`) na clausula WHERE -- mudaria candidate set.
5. Modificar `score_candidate`, pesos, ou gated tipo/safra -- **congelado**.
6. Cortar candidatos "obviamente errados" antes do Python -- mudaria `raw_score` extremo e tiebreak.

Foi avaliada e **descartada** a batch LATERAL com VALUES table (o planner nao parametriza bem o operador `%` contra coluna externa; 1,34x regressao medida).

## Conclusao do diagnostico

- Round-trips totais NAO sao o gargalo isolado. O gargalo real sao as 3 queries trgm/GIN por wine contra `vivino_match`, que no modo sequencial somam ~7s por wine e dominam 75% do tempo.
- O custo esta **no Postgres local**, especificamente no planner/scan do GIN trgm com texto parametrizado longo sob LIMIT 100.
- A alavanca que extrai ganho sem mudar logica e **parallelismo com conexoes persistentes** (driver-side), nao batching SQL.
- Memoizacao de canais de produtor rende +20% em dedupe, mas nao e a alavanca principal.

Ganho material esperado: **~2,6x por batch de 250 wines** (806s vs 2139s mediana). Ver `tail_candidate_runner_benchmark_2026-04-10.md` para medicoes e projecoes.
