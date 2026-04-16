# Master State -- Auditoria da Cauda Vivino

Data de consolidacao: 2026-04-11
Repositorio: `C:\winegod-app`
Modo atual do projeto: `sample-first audit`
Status geral: `EM ANDAMENTO, COM FULL FAN-OUT BLOQUEADO POR PERFORMANCE`

## Objetivo deste documento

Este arquivo existe para permitir que qualquer nova aba do Codex ou Claude retome o trabalho sem depender do historico do terminal.

Ele consolida:

- o objetivo do projeto;
- as regras metodologicas congeladas;
- o que ja foi feito e aprovado;
- o que foi testado e reprovado;
- o estado atual do sistema;
- o que ainda falta fazer;
- qual e a proxima demanda recomendada.

Se houver conflito entre conversa antiga e este documento, este documento deve ser lido primeiro e os artefatos citados devem ser tratados como fonte oficial.

---

## 1. Objetivo do projeto

Auditar a cauda de `779.383` wines do Render que estao sem `vivino_id` e responder, com numeros e classificacao defensavel:

- quanto deveria encaixar em canonico Vivino ja existente no Render;
- quanto exigiria `IMPORT_THEN_ALIAS`;
- quanto e `STANDALONE_WINE`;
- quanto e `NOT_WINE`;
- qual e o risco real de lancamento.

O projeto NAO e um projeto de matching cego em massa.
E uma auditoria disciplinada, auditavel e com gates metodologicos.

---

## 2. Regras metodologicas congeladas

Estas regras continuam valendo:

- `live > historico`
- `y2_results` e baseline historico, NAO verdade
- `y2_results.vivino_id = wines.id do Render`, NAO o `vivino_id` real do Vivino
- `UNRESOLVED` NAO e `business_class`
- `pilot_bucket_proxy` NAO e `business_class`
- match so vale com evidencia forte e sem bloqueadores
- qualquer hipotese causal precisa ser rotulada como hipotese, NAO como fato
- nenhum script ate aqui deve escrever em producao
- a logica de candidatos da Demanda 5 ficou congelada:
  - mesmos 6 canais
  - mesma score function
  - mesmo tiebreak `candidate_id ASC`
  - mesma restricao Import via `_only_vivino`

Taxonomia oficial usada na R1:

- `business_class`: `MATCH_RENDER`, `MATCH_IMPORT`, `STANDALONE_WINE`, `NOT_WINE`
- `review_state`: `RESOLVED`, `SECOND_REVIEW`, `UNRESOLVED`
- `confidence`: `HIGH`, `MEDIUM`, `LOW`
- `action`: `ALIAS`, `IMPORT_THEN_ALIAS`, `KEEP_STANDALONE`, `SUPPRESS`

---

## 3. Snapshot oficial do projeto

Fonte oficial:

- [tail_audit_snapshot_2026-04-10.md](/C:/winegod-app/reports/tail_audit_snapshot_2026-04-10.md)
- [tail_audit_reconciliation_2026-04-10.md](/C:/winegod-app/reports/tail_audit_reconciliation_2026-04-10.md)
- [tail_audit_contradictions_2026-04-10.md](/C:/winegod-app/reports/tail_audit_contradictions_2026-04-10.md)

Numeros oficiais congelados em 2026-04-10:

- `wines = 2.506.441`
- `wines com vivino_id = 1.727.058`
- `wines sem vivino_id = 779.383`
- `wine_aliases approved = 43`
- `canonical_wine_id distintos = 23`
- `wine_sources = 3.484.975`
- `stores = 19.889`
- `cauda sem wine_sources = 8.071`
- `cauda com wine_sources = 771.312`
- `vivino_vinhos = 1.738.585`
- `y2 matched vivino_id != null = 1.465.480`
- `y2 matched score >= 0.7 = 648.374`
- `in_both = 1.727.058`
- `only_vivino_db = 11.527`
- `only_render = 0`

---

## 4. Historico consolidado por demanda

### D1-D2 -- Snapshot, reconciliacao e contradicoes

Status: `APROVADO`

Arquivos principais:

- [scripts/audit_tail_snapshot.py](/C:/winegod-app/scripts/audit_tail_snapshot.py)
- [tail_audit_snapshot_2026-04-10.md](/C:/winegod-app/reports/tail_audit_snapshot_2026-04-10.md)
- [tail_audit_reconciliation_2026-04-10.md](/C:/winegod-app/reports/tail_audit_reconciliation_2026-04-10.md)
- [tail_audit_contradictions_2026-04-10.md](/C:/winegod-app/reports/tail_audit_contradictions_2026-04-10.md)

Resultado:

- snapshot live oficial fechado;
- reconciliacao Render vs `vivino_db` fechada;
- contradicoes historico vs live registradas.

### D3 -- Base extract da cauda

Status: `APROVADO`

Arquivos principais:

- [scripts/extract_tail_base.py](/C:/winegod-app/scripts/extract_tail_base.py)
- [tail_base_extract_2026-04-10.csv.gz](/C:/winegod-app/reports/tail_base_extract_2026-04-10.csv.gz)
- [tail_base_summary_2026-04-10.md](/C:/winegod-app/reports/tail_base_summary_2026-04-10.md)

Resultado:

- extract base da cauda gerado;
- flags operacionais e campos basicos materializados.

### D4 -- Enriquecimento y2 + linhagem local

Status: `APROVADO`

Arquivos principais:

- [scripts/enrich_tail_y2_lineage.py](/C:/winegod-app/scripts/enrich_tail_y2_lineage.py)
- [tail_y2_lineage_enriched_2026-04-10.csv.gz](/C:/winegod-app/reports/tail_y2_lineage_enriched_2026-04-10.csv.gz)
- [tail_y2_lineage_summary_2026-04-10.md](/C:/winegod-app/reports/tail_y2_lineage_summary_2026-04-10.md)

Resultado:

- baseline `y2_results` incorporado como historico;
- linhagem local ate `vinhos_XX_fontes` materializada;
- ambiguidades e perdas de join documentadas.

### D5 -- Gerador de candidatos + controles

Status: `APROVADO`

Arquivos principais:

- [scripts/build_candidate_controls.py](/C:/winegod-app/scripts/build_candidate_controls.py)
- [tail_candidate_controls_summary_2026-04-10.md](/C:/winegod-app/reports/tail_candidate_controls_summary_2026-04-10.md)

Resultado:

- gerador top3 criado;
- `20+20` controles rodados;
- recall top3 positivo = `18/20 = 90%`;
- gate passou no piso exato;
- aprovacao apenas para uso controlado, NAO para full fan-out.

### D6A -- Runner do piloto com checkpoint/resume

Status: `APROVADO`, mas com veredito `NAO PRONTO`

Arquivos principais:

- [scripts/run_candidate_fanout_pilot.py](/C:/winegod-app/scripts/run_candidate_fanout_pilot.py)
- [scripts/finalize_d6_partial.py](/C:/winegod-app/scripts/finalize_d6_partial.py)
- [tail_candidate_fanout_pilot_summary_2026-04-10.md](/C:/winegod-app/reports/tail_candidate_fanout_pilot_summary_2026-04-10.md)

Resultado:

- `--stop-after 3` provado;
- `resume` provado;
- runner funcional;
- full fan-out projetado em ~`77,2 dias`;
- conclusao: `NAO PRONTO` por performance.

### D6B -- Runner rapido com paralelismo

Status: `APROVADO`, mas com veredito `NAO PRONTO`

Arquivos principais:

- [scripts/run_candidate_fanout_fast.py](/C:/winegod-app/scripts/run_candidate_fanout_fast.py)
- [tail_candidate_runner_perf_diagnosis_2026-04-10.md](/C:/winegod-app/reports/tail_candidate_runner_perf_diagnosis_2026-04-10.md)
- [tail_candidate_runner_equivalence_2026-04-10.md](/C:/winegod-app/reports/tail_candidate_runner_equivalence_2026-04-10.md)
- [tail_candidate_runner_benchmark_2026-04-10.md](/C:/winegod-app/reports/tail_candidate_runner_benchmark_2026-04-10.md)

Resultado:

- runner acelerado implementado;
- equivalencia funcional aceita;
- full fan-out ainda projetado em ~`29 dias`;
- conclusao: ainda `NAO PRONTO`.

### D6C -- Cache persistente por chave

Status: `APROVADO`, mas com veredito `NAO APTO`

Arquivos principais:

- [scripts/measure_candidate_key_cardinality.py](/C:/winegod-app/scripts/measure_candidate_key_cardinality.py)
- [scripts/build_candidate_cache.py](/C:/winegod-app/scripts/build_candidate_cache.py)
- [scripts/run_candidate_fanout_cached.py](/C:/winegod-app/scripts/run_candidate_fanout_cached.py)
- [tail_candidate_cacheability_2026-04-10.md](/C:/winegod-app/reports/tail_candidate_cacheability_2026-04-10.md)
- [tail_candidate_cache_equivalence_2026-04-10.md](/C:/winegod-app/reports/tail_candidate_cache_equivalence_2026-04-10.md)
- [tail_candidate_cache_benchmark_2026-04-10.md](/C:/winegod-app/reports/tail_candidate_cache_benchmark_2026-04-10.md)

Resultado:

- cache persistente testado;
- semanticamente valido;
- nao resolve o gargalo dominante porque os canais mais caros tem 94-95% de chaves unicas;
- frente de performance do full fan-out encerrada;
- full continua em semanas.

Nota:

- D8 corrigiu o residual documental do report de cacheabilidade para alinhar `render_nome` com o CSV oficial.

### D7 -- Pivot para sample-first audit

Status: `APROVADO`

Arquivos principais:

- [scripts/build_working_pool.py](/C:/winegod-app/scripts/build_working_pool.py)
- [scripts/run_fanout_on_pool.py](/C:/winegod-app/scripts/run_fanout_on_pool.py)
- [scripts/assign_pilot_buckets.py](/C:/winegod-app/scripts/assign_pilot_buckets.py)
- [scripts/export_pilot_review_pack.py](/C:/winegod-app/scripts/export_pilot_review_pack.py)
- [tail_working_pool_1200_2026-04-10.csv](/C:/winegod-app/reports/tail_working_pool_1200_2026-04-10.csv)
- [tail_working_pool_fanout_detail_2026-04-10.csv.gz](/C:/winegod-app/reports/tail_working_pool_fanout_detail_2026-04-10.csv.gz)
- [tail_working_pool_fanout_per_wine_2026-04-10.csv.gz](/C:/winegod-app/reports/tail_working_pool_fanout_per_wine_2026-04-10.csv.gz)
- [tail_working_pool_with_buckets_2026-04-10.csv](/C:/winegod-app/reports/tail_working_pool_with_buckets_2026-04-10.csv)
- [tail_working_pool_summary_2026-04-10.md](/C:/winegod-app/reports/tail_working_pool_summary_2026-04-10.md)
- [tail_pilot_120_2026-04-10.csv](/C:/winegod-app/reports/tail_pilot_120_2026-04-10.csv)
- [tail_pilot_120_reservas_2026-04-10.csv](/C:/winegod-app/reports/tail_pilot_120_reservas_2026-04-10.csv)
- [tail_pilot_120_summary_2026-04-10.md](/C:/winegod-app/reports/tail_pilot_120_summary_2026-04-10.md)

Resultado:

- working pool `1.200` montado;
- pilot `120` montado;
- reservas `60` montadas;
- projeto mudou oficialmente para `sample-first`.

Distribuicao do working pool por proxy bucket:

- `P1 = 222`
- `P2 = 198`
- `P3 = 225`
- `P4 = 153`
- `P5 = 1`
- `P6 = 401`

Distribuicao do pilot:

- `P1 = 20`
- `P2 = 20`
- `P3 = 20`
- `P4 = 20`
- `P5 = 1`
- `P6 = 39`

### D8 -- R1 Claude do pilot_120

Status: `APROVADO`

Arquivos principais:

- [scripts/classify_pilot_r1.py](/C:/winegod-app/scripts/classify_pilot_r1.py)
- [tail_pilot_120_dossier_short_2026-04-10.csv](/C:/winegod-app/reports/tail_pilot_120_dossier_short_2026-04-10.csv)
- [tail_pilot_120_r1_claude_2026-04-10.csv](/C:/winegod-app/reports/tail_pilot_120_r1_claude_2026-04-10.csv)
- [tail_pilot_120_for_murilo_2026-04-10.csv](/C:/winegod-app/reports/tail_pilot_120_for_murilo_2026-04-10.csv)
- [tail_pilot_120_r1_summary_2026-04-10.md](/C:/winegod-app/reports/tail_pilot_120_r1_summary_2026-04-10.md)

Resultado:

- R1 Claude completa dos `120` wines;
- pacote para Murilo gerado;
- o projeto entrou no gate de revisao humana.

Distribuicao R1 por `business_class`:

- `MATCH_RENDER = 53`
- `STANDALONE_WINE = 46`
- `NOT_WINE = 20`
- `MATCH_IMPORT = 1`

Distribuicao R1 por `review_state`:

- `SECOND_REVIEW = 64`
- `RESOLVED = 33`
- `UNRESOLVED = 23`

Ressalva registrada:

- o pacote para Murilo ainda precisa ser endurecido com flags cruas, especialmente `y2_any_not_wine_or_spirit`, para evitar inferencia textual em comparacao futura.

### D9 -- Infraestrutura de revisao humana

Status: `APROVADO`

Arquivos principais:

- [scripts/validate_murilo_csv.py](/C:/winegod-app/scripts/validate_murilo_csv.py)
- [scripts/compare_claude_vs_murilo.py](/C:/winegod-app/scripts/compare_claude_vs_murilo.py)
- [scripts/build_adjudication_template.py](/C:/winegod-app/scripts/build_adjudication_template.py)
- [tail_pilot_120_murilo_instructions_2026-04-10.md](/C:/winegod-app/reports/tail_pilot_120_murilo_instructions_2026-04-10.md)
- [tail_pilot_120_concordance_ready_2026-04-10.md](/C:/winegod-app/reports/tail_pilot_120_concordance_ready_2026-04-10.md)
- [tail_pilot_120_adjudication_template_2026-04-10.csv](/C:/winegod-app/reports/tail_pilot_120_adjudication_template_2026-04-10.csv)

Resultado:

- pacote `for_murilo` endurecido com 5 flags cruas (`y2_any_not_wine_or_spirit`, `wine_filter_category`, `block`, `overflow_from`, `reason_short_proxy`);
- validador, comparador e gerador de adjudicacao criados;
- instrucoes operacionais para Murilo geradas;
- ferramenta visual HTML criada para revisao interativa;
- ressalva de D8 resolvida.

### D10 -- Concordancia Claude vs Murilo

Status: `APROVADO`

Arquivos principais:

- [tail_pilot_120_for_murilo_2026-04-10.csv](/C:/winegod-app/reports/tail_pilot_120_for_murilo_2026-04-10.csv) (preenchido 120/120)
- [tail_pilot_120_concordance_2026-04-10.md](/C:/winegod-app/reports/tail_pilot_120_concordance_2026-04-10.md)
- [tail_pilot_120_concordance_summary_2026-04-10.md](/C:/winegod-app/reports/tail_pilot_120_concordance_summary_2026-04-10.md)
- [tail_pilot_120_disagreements_2026-04-10.csv](/C:/winegod-app/reports/tail_pilot_120_disagreements_2026-04-10.csv)
- [tail_pilot_120_adjudication_2026-04-10.csv](/C:/winegod-app/reports/tail_pilot_120_adjudication_2026-04-10.csv)

Resultado:

- Murilo preencheu `120/120` wines, validador passou sem erros;
- concordancia calculada e materializada;
- `83` disagreements identificados e materializados para adjudicacao.

Concordancia global por campo:

- `business_class = 74/120 = 61.7%`
- `review_state = 49/120 = 40.8%`
- `confidence = 45/120 = 37.5%`
- `action = 74/120 = 61.7%`

Concordancia por bucket (business_class):

- `P1 = 95.0%` (melhor)
- `P2 = 75.0%`
- `P4 = 75.0%`
- `P3 = 55.0%`
- `P6 = 35.9%` (pior)

Concordancia por confidence do Claude (business_class):

- `HIGH = 93.9%`
- `MEDIUM = 51.2%`
- `LOW = 47.8%`

Distribuicao Murilo:

- `MATCH_RENDER = 42`
- `STANDALONE_WINE = 40`
- `NOT_WINE = 38`
- `MATCH_IMPORT = 0`

Fatos chave:

- Claude HIGH confidence e confiavel (94% de acerto);
- zona ambigua (P6) e o ponto fraco principal (36%);
- Murilo classificou mais NOT_WINE que Claude (+18), menos MATCH_RENDER (-11);
- Murilo nunca usou UNRESOLVED; resolveu todos os 23 que Claude deixou em aberto.

Nota: existe um artefato auxiliar em [2026-04-13_handoff_d10_concordance.md](/C:/winegod-app/reports/2026-04-13_handoff_d10_concordance.md) com analise adicional. A fonte central e este master state.

### D11 -- Adjudicacao dos disagreements

Status: `APROVADO`

Arquivos principais:

- [scripts/adjudicate_pilot.py](/C:/winegod-app/scripts/adjudicate_pilot.py)
- [tail_pilot_120_adjudication_2026-04-10.csv](/C:/winegod-app/reports/tail_pilot_120_adjudication_2026-04-10.csv) (83/83 preenchidos)
- [tail_pilot_120_final_adjudicated_2026-04-10.csv](/C:/winegod-app/reports/tail_pilot_120_final_adjudicated_2026-04-10.csv) (120 wines)
- [tail_pilot_120_adjudication_summary_2026-04-10.md](/C:/winegod-app/reports/tail_pilot_120_adjudication_summary_2026-04-10.md)

Resultado:

- 83 disagreements adjudicados (83/83);
- Murilo sustentado em 76/83 (91.6%), Claude em 7/83 (8.4%);
- classificacao final fechada para os 120 wines.

Distribuicao final adjudicada:

- `STANDALONE_WINE = 41`
- `MATCH_RENDER = 40`
- `NOT_WINE = 39`
- `MATCH_IMPORT = 0`

Erros sistematicos do Claude documentados:

1. NOT_WINE subdetectado: de 20 (R1) para 39 (final) = +19 wines que eram NOT_WINE mas Claude nao detectou. Causa: wine_filter permissivo + falta de heuristica de nome.
2. MATCH_RENDER inflado: de 53 (R1) para 40 (final) = -13 falsos positivos por gap=0 ou candidato errado.
3. UNRESOLVED excessivo: 23 wines marcados UNRESOLVED, todos resolvidos na adjudicacao. Threshold pode ser relaxado.

### D12 -- Recalibracao R2 do classificador

Status: `APROVADO`

Arquivos principais:

- [scripts/classify_pilot_r2.py](/C:/winegod-app/scripts/classify_pilot_r2.py)
- [tail_pilot_120_r2_claude_2026-04-10.csv](/C:/winegod-app/reports/tail_pilot_120_r2_claude_2026-04-10.csv) (120 wines)
- [tail_pilot_120_r2_evaluation_2026-04-10.md](/C:/winegod-app/reports/tail_pilot_120_r2_evaluation_2026-04-10.md)

Resultado:

- R2 atingiu `80.0%` de concordancia em business_class vs final adjudicado (alvo >= 80%);
- melhoria de `+12.5pp` vs R1 (67.5% -> 80.0%);
- P6 melhorou de `41%` para `72%` (+31pp);
- NOT_WINE recall: `51%` (R1) -> `97%` (R2);
- MATCH_RENDER precision: `66%` (R1) -> `90%` (R2);
- UNRESOLVED: `23` (R1) -> `0` (R2).

Veredito: **APTO PARA DISCUTIR REPRESENTATIVA 600**

Ressalvas:
- MATCH_RENDER recall caiu de 88% para 68% (trade-off do bloqueio de gap=0);
- 7 falsos positivos em NOT_WINE (4 reais, 3 defensaveis);
- P6 ainda e o ponto fraco (72% vs 100% em P1);
- a decisao de abrir representativa 600 continua sendo do administrador.

### D13 -- Representativa 600

Status: `APROVADO`

Arquivos principais:

- [scripts/build_representativa_600.py](/C:/winegod-app/scripts/build_representativa_600.py)
- [tail_representativa_600_frame_2026-04-10.csv](/C:/winegod-app/reports/tail_representativa_600_frame_2026-04-10.csv)
- [tail_representativa_600_weights_2026-04-10.csv](/C:/winegod-app/reports/tail_representativa_600_weights_2026-04-10.csv)
- [tail_representativa_600_fanout_detail_2026-04-10.csv.gz](/C:/winegod-app/reports/tail_representativa_600_fanout_detail_2026-04-10.csv.gz)
- [tail_representativa_600_fanout_per_wine_2026-04-10.csv.gz](/C:/winegod-app/reports/tail_representativa_600_fanout_per_wine_2026-04-10.csv.gz)
- [tail_representativa_600_r2_claude_2026-04-10.csv](/C:/winegod-app/reports/tail_representativa_600_r2_claude_2026-04-10.csv)
- [tail_representativa_600_for_review_2026-04-10.csv](/C:/winegod-app/reports/tail_representativa_600_for_review_2026-04-10.csv)
- [tail_representativa_600_summary_2026-04-10.md](/C:/winegod-app/reports/tail_representativa_600_summary_2026-04-10.md)

Resultado:

- amostra estratificada de `600` wines (100/estrato, 6 estratos);
- universo amostral: `778.143` wines (cauda 779.383 - 1.240 excluidos);
- fan-out completo com `6.145` detail rows (8 workers, 2.347s);
- cobertura render: `592/600 = 99%`;
- cobertura import: `279/600 = 46%`;
- R2 classificou os 600.

Estratos populacionais:

- `S1_SUSPECT_NOT_WINE = 16.902` (peso 169.0)
- `S2_NO_SOURCE = 7.751` (peso 77.5)
- `S3_NO_LINEAGE_OR_ORPHAN = 1.314` (peso 13.1)
- `S4_MULTI_CLEAN_OR_AMBIG_LINEAGE = 20.769` (peso 207.7)
- `S5_SOURCE_RICH_STRUCTURED = 25.530` (peso 255.3)
- `S6_GENERAL_REMAINDER = 705.877` (peso 7.058.8)

Distribuicao R2 da representativa:

- `NOT_WINE = 207 (34.5%)`
- `STANDALONE_WINE = 222 (37.0%)`
- `MATCH_RENDER = 168 (28.0%)`
- `MATCH_IMPORT = 3 (0.5%)`

Distribuicao R2 por estrato:

- `S1`: 100% NOT_WINE (como esperado)
- `S2`: 32 MR, 48 SW, 20 NW
- `S3`: 40 MR, 56 SW, 4 NW
- `S4`: 36 MR, 46 SW, 18 NW
- `S5`: 35 MR, 33 SW, 30 NW, 2 MI
- `S6`: 25 MR, 39 SW, 35 NW, 1 MI

Nota: a representativa esta **preparada** mas ainda **NAO** e estimativa populacional. A proxima etapa e leitura com pesos ou revisao humana.

Correcao D13A: o review pack (`for_review`) foi corrigido para incluir `population_n`, `sample_n`, `sampling_fraction` e `design_weight` por estrato. O review pack agora e autocontido para estimativa populacional.

### D14 -- Primeira leitura populacional (provisoria)

Status: `APROVADO`

Arquivos principais:

- [tail_representativa_600_estimate_detail_2026-04-10.csv](/C:/winegod-app/reports/tail_representativa_600_estimate_detail_2026-04-10.csv)
- [tail_representativa_600_estimate_summary_2026-04-10.md](/C:/winegod-app/reports/tail_representativa_600_estimate_summary_2026-04-10.md)

Resultado:

- primeira leitura ponderada da cauda produzida;
- alvo da inferencia: `778.143` wines (frame amostral, exclui 1.240 de calibracao);
- leitura e **PROVISORIA**, NAO e estimativa final.

Estimativa ponderada principal:

- `STANDALONE_WINE = 297.727 (38.3%)`
- `NOT_WINE = 276.959 (35.6%)`
- `MATCH_RENDER = 195.888 (25.2%)`
- `MATCH_IMPORT = 7.569 (1.0%)`

Cenarios de sensibilidade (base / conservador / otimista):

- `MATCH_RENDER: 25% / 30% / 23%`
- `NOT_WINE: 36% / 29% / 41%`
- `STANDALONE_WINE: 38% / 40% / 35%`

Cautelas principais:

1. S6 domina 91% da populacao com apenas 100 amostras (peso 7.059 por wine);
2. R2 tem 80% de concordancia, nao 100%;
3. fronteira NOT_WINE vs STANDALONE depende de heuristica de nome;
4. fronteira MATCH_RENDER vs STANDALONE depende de gap=0 (match visual nao captavel por regra).

---

## 5. Onde o sistema esta agora

Estado atual resumido:

- snapshot oficial: pronto
- base da cauda: pronta
- enriquecimento y2/linhagem: pronto
- gerador de candidatos: pronto para uso controlado
- full fan-out: bloqueado por performance
- working pool 1.200: pronto
- pilot_120: revisado, adjudicado, classificacao final fechada
- R1 Claude: pronta (erros sistematicos documentados)
- R2 Claude: pronta (80.0% vs final adjudicado)
- revisao Murilo pilot: completa (120/120)
- concordancia: calculada
- adjudicacao: completa
- classificacao final pilot: fechada (SW=41, MR=40, NW=39)
- representativa 600: montada, fan-out completo, R2 classificada
- leitura populacional provisoria: produzida (D14)
- estimativa final: ainda NAO feita (D14 e provisoria)
- D15 aprovada: politica operacional definida (4 filas, matriz 31 combinacoes, QA, rollback)
- D16 fase tecnica: pronta e auditada
- D16 lote real: `IN_D16_LOT = 21.485`, `BLOCKED_BY_POLICY = 1.651`, `OUT_OF_SCOPE_D16 = 755.007`
- D16 gap estrutural: `~20.883` (estimativa agregada, NAO rowset)
- D16 QA pack: pronto (`623` wines)
- D16 infraestrutura de gate: pronta (validador `pending/filled`, scorer `real/fixture`, workflow)
- D16 interface HTML de revisao humana: pronta
- D16 QA humano: `PENDENTE`
- roadmap D16-D20: oficial (ondas seguras ~17%, residual ~81%, fechamento)

Em uma frase:

D15 aprovada; D16 fase tecnica pronta e auditada. O bloqueio atual e humano: preencher o QA pack da D16 (`623` rows) na interface HTML e so depois fechar o gate da D16. Producao so em D18.

---

## 6. O que NAO fazer a partir daqui

Enquanto este estado for valido, NAO fazer:

- reabrir a frente de performance do full fan-out
- rodar full fan-out dos `779.383`
- mudar canais da Demanda 5
- usar `pilot_bucket_proxy` como `business_class`
- usar `y2_results` como verdade
- tratar a leitura D14 como estimativa final
- abrir rollout em massa sem passar pelo QA de D16/D17
- pular D16/D17 e ir direto para execucao em D18
- executar SUPPRESS ou ALIAS em S6 sem QA ampliado (peso 7.059 por wine)
- misturar os `1.240` excluidos de calibracao no alvo principal da leitura D14 sem separar

---

## 7. O que falta fazer

### Roadmap de fechamento da limpeza da base

O trabalho agora saiu da fase de descoberta e entrou na fase de execucao controlada. O plano de fechamento ate base limpa fica assim:

#### D15 -- Plano de execucao e regras de producao

Objetivo:

- transformar a leitura D14 em politica operacional;
- definir matriz `classe x confianca x estrato -> acao`;
- fixar regras de QA, rollback e limites de erro por lote.

Gate:

- so passa se ficar claro o que pode entrar em `SUPPRESS`, `ALIAS`, `IMPORT_THEN_ALIAS` e `MANUAL_REVIEW`.

#### D16 -- Onda 1 de baixo risco: NOT_WINE

Objetivo:

- preparar e validar a limpeza dos nao-vinhos obvios.

Escopo inicial:

- `S1_SUSPECT_NOT_WINE`;
- e, se fizer sentido, subfaixas adicionais de `NOT_WINE` de alta confianca.

Gate:

- dry-run aprovado e QA humano abaixo do limite de erro definido em D15.

#### D17 -- Onda 2 de baixo risco: duplicados fortes

Objetivo:

- preparar e validar a deduplicacao via alias dos `MATCH_RENDER` mais seguros.

Escopo inicial:

- `MATCH_RENDER HIGH`;
- foco em `S4/S5`;
- produtor compativel, score forte e gap real.

Gate:

- falso positivo de alias abaixo do piso aceito em D15.

#### D18 -- Execucao controlada em producao

Objetivo:

- executar apenas os lotes aprovados em D16/D17 com trilha completa.

Entregas esperadas:

- logs;
- diff antes/depois;
- contagens reconciliadas;
- relatorio pos-execucao.

#### D19 -- Residual dificil e MATCH_IMPORT

Objetivo:

- atacar o que sobrou fora das ondas seguras.

Escopo:

- `S6`;
- fronteiras `STANDALONE_WINE` vs `MATCH_RENDER`;
- fronteiras `STANDALONE_WINE` vs `NOT_WINE`;
- fila propria de `MATCH_IMPORT`.

Gate:

- residual precisa ficar pequeno, controlado e explicitamente separado em automatico vs manual.

#### D20 -- Fechamento final da base

Objetivo:

- declarar a auditoria encerrada com a base limpa e reconciliada.

Entregas esperadas:

- recontagem final da cauda;
- quantos viraram `SUPPRESS`;
- quantos viraram `ALIAS`;
- quantos ficaram em `IMPORT_THEN_ALIAS`;
- quantos permaneceram `STANDALONE_WINE`;
- quantos ficaram em backlog manual;
- relatorio final executivo.

Definicao de trabalho 100% concluido:

- nao-vinhos tratados;
- duplicados tratados;
- fila de import separada;
- residual ambiguo pequeno e explicitamente assumido;
- base final limpa e reconciliada.

### D15 -- Politica operacional de limpeza

Status: `APROVADO`

Arquivos principais:

- [tail_cleanup_execution_policy_2026-04-13.md](/C:/winegod-app/reports/tail_cleanup_execution_policy_2026-04-13.md)
- [tail_cleanup_action_matrix_2026-04-13.csv](/C:/winegod-app/reports/tail_cleanup_action_matrix_2026-04-13.csv)
- [tail_cleanup_qa_and_rollback_2026-04-13.md](/C:/winegod-app/reports/tail_cleanup_qa_and_rollback_2026-04-13.md)
- [tail_cleanup_roadmap_d15_d20_2026-04-13.md](/C:/winegod-app/reports/tail_cleanup_roadmap_d15_d20_2026-04-13.md)
- [scripts/build_cleanup_action_matrix.py](/C:/winegod-app/scripts/build_cleanup_action_matrix.py)

Resultado:

- politica operacional concreta com 4 filas (SUPPRESS, ALIAS, IMPORT_THEN_ALIAS, MANUAL_REVIEW);
- matriz operacional CSV com 31 combinacoes (classe x confianca x estrato -> acao);
- cada combinacao com: recommended_action, automation_level, qa_requirement, second_review_required, notes;
- protocolo de QA por lote: SUPPRESS max 5% erro, ALIAS max 3% erro, QA ampliado para S6;
- protocolo de rollback: backup pre-execucao, diff planejado, contagem pre/pos, script de reversao;
- roadmap D16-D20 detalhado com escopo e gate de cada demanda;
- ondas seguras (D16+D17) cobrem ~134k wines (~17% do frame);
- residual dificil (D19) contem ~629k wines (~81% do frame), concentrado em S6;
- contrato minimo para D18: --dry-run default, backup automatico, lotes de max 5000, rollback embutido.

Volumes da matriz (soma exata = 778.143):

- SUPPRESS_AUTO: 16.902 wines (somente S1 — unico estrato BATCH_AUTO)
- SUPPRESS_QA: 27.117 wines (NW HIGH fora de S1 + NW MEDIUM S2-S5 — QA 10% obrigatorio)
- SUPPRESS_REVIEW: 232.939 wines (NW MEDIUM S6 — reservado para D19, QA 20%)
- ALIAS_AUTO: 78.869 wines (MR HIGH todos os estratos — QA 5%)
- ALIAS_QA: 11.136 wines (MR MEDIUM S2-S5 — QA 10%)
- ALIAS_REVIEW: 105.882 wines (MR MEDIUM S6 — reservado para D19, QA 20%)
- IMPORT_THEN_ALIAS: 7.570 wines (revisao manual 100%)
- KEEP_STANDALONE: 15.389 wines (SW preservado)
- KEEP_STANDALONE_REVIEW: 282.339 wines (SW que precisa amostra para estimar MR perdidos)

### D16 -- Onda 1 de baixo risco: NOT_WINE

Status: `EM ANDAMENTO (FASE TECNICA APROVADA; QA HUMANO PENDENTE)`

Arquivos principais:

- [scripts/build_d16_suppress_lot.py](/C:/winegod-app/scripts/build_d16_suppress_lot.py)
- [tail_d16_suppress_candidates_2026-04-13.csv.gz](/C:/winegod-app/reports/tail_d16_suppress_candidates_2026-04-13.csv.gz)
- [tail_d16_suppress_blocked_2026-04-13.csv.gz](/C:/winegod-app/reports/tail_d16_suppress_blocked_2026-04-13.csv.gz)
- [tail_d16_suppress_counts_2026-04-13.csv](/C:/winegod-app/reports/tail_d16_suppress_counts_2026-04-13.csv)
- [tail_d16_suppress_dry_run_summary_2026-04-13.md](/C:/winegod-app/reports/tail_d16_suppress_dry_run_summary_2026-04-13.md)
- [tail_d16_suppress_feasibility_2026-04-13.md](/C:/winegod-app/reports/tail_d16_suppress_feasibility_2026-04-13.md)
- [tail_d16_suppress_qa_pack_2026-04-13.csv](/C:/winegod-app/reports/tail_d16_suppress_qa_pack_2026-04-13.csv)
- [tail_d16_suppress_qa_instructions_2026-04-13.md](/C:/winegod-app/reports/tail_d16_suppress_qa_instructions_2026-04-13.md)
- [scripts/validate_d16_suppress_qa_pack.py](/C:/winegod-app/scripts/validate_d16_suppress_qa_pack.py)
- [scripts/summarize_d16_suppress_qa.py](/C:/winegod-app/scripts/summarize_d16_suppress_qa.py)
- [tail_d16_suppress_qa_workflow_2026-04-13.md](/C:/winegod-app/reports/tail_d16_suppress_qa_workflow_2026-04-13.md)
- [scripts/export_d16_suppress_qa_review_html.py](/C:/winegod-app/scripts/export_d16_suppress_qa_review_html.py)
- [tail_d16_suppress_qa_review_2026-04-13.html](/C:/winegod-app/reports/tail_d16_suppress_qa_review_2026-04-13.html)
- [tail_d16_suppress_qa_review_ui_instructions_2026-04-13.md](/C:/winegod-app/reports/tail_d16_suppress_qa_review_ui_instructions_2026-04-13.md)

Resultado:

- frame D16 reproduzido com `778.143` wines (mesmas exclusoes da D13)
- lote real materializado: `21.485` wines
- `SUPPRESS_AUTO_S1 = 15.251`
- `SUPPRESS_QA = 6.234`
- `BLOCKED_BY_POLICY = 1.651` wines reais
- `OUT_OF_SCOPE_D16 = 755.007` wines reais
- gap estrutural `~20.883` tratado como **estimativa agregada**, NAO rowset
- QA pack de `623` wines preparado
- validador/scorer/workflow do gate criados e auditados
- interface HTML standalone de revisao humana criada e auditada
- nenhum script desta frente executou producao

Estado administrativo exato:

- a fase tecnica da D16 esta pronta
- o gate da D16 ainda NAO esta fechado
- o bloqueio atual e apenas o preenchimento humano do QA pack
- D17 continua fechada ate decisao administrativa explicita

### Proximo passo recomendado agora

- **Preencher o QA humano da D16 e depois fechar o gate da D16**

Acao correta agora:

1. abrir [tail_d16_suppress_qa_review_2026-04-13.html](/C:/winegod-app/reports/tail_d16_suppress_qa_review_2026-04-13.html)
2. preencher os `623` wines do QA pack oficial
3. exportar o CSV atualizado
4. validar com `validate_d16_suppress_qa_pack.py --mode filled`
5. rodar `summarize_d16_suppress_qa.py --report-kind real`
6. so depois submeter a D16 para gate administrativo final

D17 permanece fechada ate esse gate terminar. D16 continua sem producao.

---

## 8. Riscos abertos

Riscos reais ainda abertos:

1. Full fan-out continua inviavel com a arquitetura atual.
2. D14 e uma leitura provisoria, nao final. Ela herda o erro residual da R2.
3. `S6_REMAINDER` domina ~91% do frame e concentra a maior incerteza operacional. As ondas seguras (D16+D17) cobrem apenas ~17% do frame; os ~81% restantes dependem de D19.
4. A principal fronteira aberta continua sendo `STANDALONE_WINE` vs `MATCH_RENDER` e `STANDALONE_WINE` vs `NOT_WINE` em S6.
5. `MATCH_IMPORT` segue raro (~7.570 wines) e precisa de trilha propria; nao deve ser misturado com alias direto.
6. R2 HIGH tem 95.8% de acerto (2 erros em 48 no pilot), mas R2 MEDIUM tem 63.3% (18 erros em 49). A grande maioria dos wines em S6 tem confidence MEDIUM.
7. SUPPRESS_REVIEW em S6 (~233k wines) e o maior bloco unico. Se a taxa real de FP for maior que 5-6%, o impacto e dezenas de milhares de wines reais removidos. QA ampliado e obrigatorio.

---

## 9. Protocolo de retomada para qualquer nova aba

Se uma nova aba do Codex ou Claude precisar retomar o trabalho:

1. ler este arquivo inteiro primeiro
2. depois ler o prompt de continuidade mais recente:
   - [PROMPT_TAIL_AUDIT_CONTINUATION_2026-04-13.md](/C:/winegod-app/prompts/PROMPT_TAIL_AUDIT_CONTINUATION_2026-04-13.md)
3. depois ler, nesta ordem:
   - [tail_audit_snapshot_2026-04-10.md](/C:/winegod-app/reports/tail_audit_snapshot_2026-04-10.md)
   - [tail_y2_lineage_summary_2026-04-10.md](/C:/winegod-app/reports/tail_y2_lineage_summary_2026-04-10.md)
   - [tail_candidate_controls_summary_2026-04-10.md](/C:/winegod-app/reports/tail_candidate_controls_summary_2026-04-10.md)
   - [tail_working_pool_summary_2026-04-10.md](/C:/winegod-app/reports/tail_working_pool_summary_2026-04-10.md)
   - [tail_pilot_120_r1_summary_2026-04-10.md](/C:/winegod-app/reports/tail_pilot_120_r1_summary_2026-04-10.md)
4. assumir como estado oficial:
   - projeto em `sample-first audit`, fase de execucao controlada
   - full fan-out bloqueado
   - pilot_120 revisado, adjudicado, classificacao final fechada
   - R2 atingiu 80.0% vs final adjudicado
   - representativa 600 montada e classificada (D13)
   - leitura populacional provisoria produzida (D14): SW=38%, NW=36%, MR=25%
   - D15 aprovada: politica operacional definida
   - D16 fase tecnica pronta e auditada
   - D16 lote real = `21.485`, bloqueado real = `1.651`, gap estrutural = `~20.883`
   - D16 QA pack oficial pronto com `623` wines
   - infraestrutura do gate D16 pronta
   - interface HTML de revisao humana da D16 pronta (auto-avanco, autosave local, checkpoint/import de CSV)
   - proxima acao correta = preencher o QA humano da D16 e so depois fechar o gate
5. ler tambem:
   - [tail_pilot_120_adjudication_summary_2026-04-10.md](/C:/winegod-app/reports/tail_pilot_120_adjudication_summary_2026-04-10.md)
   - [tail_pilot_120_r2_evaluation_2026-04-10.md](/C:/winegod-app/reports/tail_pilot_120_r2_evaluation_2026-04-10.md)
   - [tail_cleanup_execution_policy_2026-04-13.md](/C:/winegod-app/reports/tail_cleanup_execution_policy_2026-04-13.md)
   - [tail_cleanup_action_matrix_2026-04-13.csv](/C:/winegod-app/reports/tail_cleanup_action_matrix_2026-04-13.csv)
   - [tail_cleanup_qa_and_rollback_2026-04-13.md](/C:/winegod-app/reports/tail_cleanup_qa_and_rollback_2026-04-13.md)
   - [tail_cleanup_roadmap_d15_d20_2026-04-13.md](/C:/winegod-app/reports/tail_cleanup_roadmap_d15_d20_2026-04-13.md)
   - [tail_d16_suppress_dry_run_summary_2026-04-13.md](/C:/winegod-app/reports/tail_d16_suppress_dry_run_summary_2026-04-13.md)
   - [tail_d16_suppress_feasibility_2026-04-13.md](/C:/winegod-app/reports/tail_d16_suppress_feasibility_2026-04-13.md)
   - [tail_d16_suppress_qa_workflow_2026-04-13.md](/C:/winegod-app/reports/tail_d16_suppress_qa_workflow_2026-04-13.md)
   - [tail_d16_suppress_qa_review_ui_instructions_2026-04-13.md](/C:/winegod-app/reports/tail_d16_suppress_qa_review_ui_instructions_2026-04-13.md)
   - [tail_audit_admin_session_history_2026-04-13.md](/C:/winegod-app/reports/tail_audit_admin_session_history_2026-04-13.md)

Nota:

- este handoff agora contem o roadmap de fechamento D15-D20 com politica operacional aprovada;
- qualquer nova aba deve tratar esse roadmap como plano oficial ate nova decisao administrativa;
- D15 esta aprovada; D16 esta tecnicamente pronta; a proxima acao correta e o QA humano da D16.
- existe um historico administrativo auxiliar da sessao atual para nao perder a trilha fina de prompts, aprovacoes e reprovacoes.

---

## 10. Resumo executivo de uma linha

D15 aprovada; D16 fase tecnica pronta e auditada (`21.485` no lote, `1.651` bloqueados, QA pack `623`, UI HTML pronta com auto-avanco, autosave local e checkpoint/import de CSV). Bloqueio atual = QA humano pendente. So depois disso fecha o gate da D16. North star: D20 = base limpa.

---

## 11. Atualizacao 2026-04-15 -- LIMPEZA NOT_WINE EM PRODUCAO (fora do protocolo D15-D20)

Apos aprovacao da D16 oficial em 2026-04-14, a administracao optou por uma frente
paralela de limpeza obvia de NOT_WINE, quebrando o protocolo D15-D20 para escalar
a remocao de produtos claramente nao-vinicolas. Essa frente **ja rodou em producao**
via soft delete (coluna `wines.suppressed_at` + `wines.suppress_reason`).

### Estado ao fim de 2026-04-15

- Total wines: `2.506.448` (inalterado)
- Base canonica Vivino (`vivino_id IS NOT NULL`): `1.727.058` -- INTACTA
- Cauda (`vivino_id IS NULL`): `779.390`
- **Suppressed acumulado**: `84.948` (3 rodadas + round 4 pendente)
- Cauda ativa: ~`694.000`

### Rodadas executadas

| rodada | reason tag | wines | base |
|--------|-----------|-------|------|
| 1 | `d16_strong_patterns_2026-04-15` | 59.902 | 15 padroes fortes validados em amostra humana 200 (97% precision) |
| 2 | `d16_wine_filter_expansion_2026-04-15` | 13.320 | expansao wine_filter.py com ratio >= 10x vs Vivino |
| 3 | `d16_wine_filter_round3_2026-04-15` | 11.726 | whiskies escoceses + sake + kits multilingua (ratio=inf) |
| 4 | `d16_wine_filter_round4_2026-04-15` (pendente) | ~10-15k esperado | termos ja no filter, aguardando rodar |

### Handoff oficial desta frente

- [PROMPT_TAIL_AUDIT_HANDOFF_NOT_WINE_CLEANUP_2026-04-15.md](/C:/winegod-app/prompts/PROMPT_TAIL_AUDIT_HANDOFF_NOT_WINE_CLEANUP_2026-04-15.md)
  contem todos os termos, metricas, rodadas, rollbacks e instrucoes de uso do
  wine_filter.py como pre-ingest para novos wines (Natura, e-commerces, etc.)
- [scripts/wine_filter.py](/C:/winegod-app/scripts/wine_filter.py) -- regex
  centralizado com ~400 termos multilingua
- [scripts/pre_ingest_filter.py](/C:/winegod-app/scripts/pre_ingest_filter.py) --
  helper `should_skip_wine(nome)` pronto para usar em qualquer pipeline de ingestao

### Pendencias que afetam o protocolo oficial

- D17/D18/D19/D20 seguem FECHADOS. A limpeza NOT_WINE feita aqui pode cobrir parte
  de D19 (SUPPRESS_REVIEW em S6) mas nao substitui D17 (alias de duplicados).
- Backend de busca (`backend/tools/search.py`) ainda nao filtra por
  `suppressed_at IS NULL`. Necessario adicionar para o suppress surtir efeito no
  produto.
- Round 4 aguarda execucao.

### Observacao sobre reuse

O `wine_filter.py` e `pre_ingest_filter.py` sao agora **contrato central de ingestao**.
Qualquer novo wine (da Natura, Vivino legacy, marketplaces) deve passar por eles antes
do INSERT/UPSERT. Isso reduz em ~10% o volume de entrada de NOT_WINE e evita que a
cauda volte a crescer.

---

## 12. Atualizacao 2026-04-16 -- VISIBILIDADE DO SUPPRESS + ABERTURA D17

Em 2026-04-16, o produto passou a respeitar `wines.suppressed_at IS NULL` nos
pontos principais de leitura do backend. Isso torna o soft delete NOT_WINE efetivo
para busca, detalhes, comparacao, precos, aliases, stats e compartilhamento.

Tambem foi adicionada a barreira de pre-ingestao baseada no catalogo completo de
termos NOT_WINE:

- `scripts/wine_filter.py`
- `scripts/pre_ingest_filter.py`
- `backend/services/new_wines.py`
- `scripts/import_render_z.py`
- `backend/routes/chat.py`

### Recontagem live da cauda

Artefato:

- [tail_active_recount_2026-04-16.md](/C:/winegod-app/reports/tail_active_recount_2026-04-16.md)

Resultado:

- Cauda ativa: `675.307`
- Cauda suprimida: `104.085`
- Cauda total sem `vivino_id`: `779.392`
- Aliases aprovados existentes: `43`

Distribuicao dos suppresses:

| reason | wines |
|--------|-------|
| `d16_strong_patterns_2026-04-15` | 59.902 |
| `d16_wine_filter_expansion_2026-04-15` | 13.320 |
| `d16_wine_filter_round3_2026-04-15` | 11.726 |
| `d16_wine_filter_round4_2026-04-15` | 19.137 |

### D17 aberto, mas ainda sem insert

Artefato:

- [tail_d17_opening_2026-04-16.md](/C:/winegod-app/reports/tail_d17_opening_2026-04-16.md)

D17 continua sendo a proxima frente logica: alias dos `MATCH_RENDER` mais fortes.
Porem, nao existe ainda rowset seguro `(source_wine_id, canonical_wine_id)` para
execucao. Os scripts antigos nao devem ser usados para insert:

- `scripts/find_alias_candidates.py` e triagem/amostra manual.
- `scripts/generate_aliases.py` usa `clean_id` local e registra que o
  `source_wine_id` Render nao esta resolvido corretamente.

Proximo artefato obrigatorio:

- `reports/tail_d17_alias_candidates_2026-04-16.csv.gz`

Regras desse materializador:

- source precisa ter `vivino_id IS NULL AND suppressed_at IS NULL`;
- canonical precisa ter `vivino_id IS NOT NULL AND suppressed_at IS NULL`;
- source nao pode ja ter alias aprovado;
- source nao pode bater no filtro NOT_WINE;
- match precisa ter `gap > 0`;
- produtor precisa ser compativel;
- D17 so prepara e valida; escrita em producao permanece reservada para D18.
