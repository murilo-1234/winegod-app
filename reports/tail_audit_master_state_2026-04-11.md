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

---

## 5. Onde o sistema esta agora

Estado atual resumido:

- snapshot oficial: pronto
- base da cauda: pronta
- enriquecimento y2/linhagem: pronto
- gerador de candidatos: pronto para uso controlado
- full fan-out: bloqueado por performance
- working pool 1.200: pronto
- pilot_120: pronto
- R1 Claude: pronta
- pacote para Murilo: existe, mas deve ser endurecido antes da comparacao humana

Em uma frase:

O sistema esta pronto para a fase de revisao humana do `pilot_120`, mas NAO esta pronto para varrer a cauda inteira.

---

## 6. O que NAO fazer a partir daqui

Enquanto este estado for valido, NAO fazer:

- reabrir a frente de performance do full fan-out
- rodar full fan-out dos `779.383`
- recalibrar score do gerador
- mudar canais da Demanda 5
- usar `pilot_bucket_proxy` como `business_class`
- usar `y2_results` como verdade
- abrir representativa `600` antes de fechar a fase Murilo/concordancia
- abrir impacto `120` antes de fechar concordancia/adjudicacao

---

## 7. O que falta fazer

### Proximo passo recomendado: D9

Objetivo:

Preparar a infraestrutura da fase Murilo, sem reclassificar o pilot.

Entregas recomendadas:

- endurecer `tail_pilot_120_for_murilo_2026-04-10.csv` com flags cruas:
  - `y2_any_not_wine_or_spirit`
  - `wine_filter_category`
  - `block`
  - `overflow_from`
  - `reason_short_proxy`
- criar validador do CSV preenchido por Murilo
- criar comparador Claude vs Murilo
- criar fluxo/CSV de adjudicacao
- criar instrucoes operacionais curtas para Murilo

Resultado esperado:

- pacote pronto para Murilo preencher;
- infraestrutura pronta para medir concordancia;
- nenhuma reabertura de classificacao ou performance.

### Depois de D9

Depois que Murilo preencher o CSV:

- rodar comparacao Claude vs Murilo
- medir concordancia por campo
- listar disagreements
- adjudicar divergencias
- usar esse resultado para calibrar a proxima etapa:
  - ou representativa `600`
  - ou impacto `120`
  - ou refinamento de thresholds de R2

---

## 8. Riscos abertos

Riscos reais ainda abertos:

1. Full fan-out continua inviavel com a arquitetura atual.
2. O pilot tem alta carga de `SECOND_REVIEW`, o que e esperado, mas transfere trabalho real para Murilo.
3. `UNRESOLVED` no pilot ainda empurra parte dos casos para `STANDALONE_WINE` como best-guess, o que pode inflar essa classe na leitura do pilot.
4. O pacote Murilo precisa de flags cruas para a comparacao ficar mais robusta.
5. Ainda nao existe metrica de concordancia Claude vs Murilo porque Murilo ainda nao preencheu o CSV.

---

## 9. Protocolo de retomada para qualquer nova aba

Se uma nova aba do Codex ou Claude precisar retomar o trabalho:

1. ler este arquivo inteiro primeiro
2. depois ler, nesta ordem:
   - [tail_audit_snapshot_2026-04-10.md](/C:/winegod-app/reports/tail_audit_snapshot_2026-04-10.md)
   - [tail_y2_lineage_summary_2026-04-10.md](/C:/winegod-app/reports/tail_y2_lineage_summary_2026-04-10.md)
   - [tail_candidate_controls_summary_2026-04-10.md](/C:/winegod-app/reports/tail_candidate_controls_summary_2026-04-10.md)
   - [tail_working_pool_summary_2026-04-10.md](/C:/winegod-app/reports/tail_working_pool_summary_2026-04-10.md)
   - [tail_pilot_120_r1_summary_2026-04-10.md](/C:/winegod-app/reports/tail_pilot_120_r1_summary_2026-04-10.md)
3. assumir como estado oficial:
   - projeto em `sample-first audit`
   - full fan-out bloqueado
   - `pilot_120` pronto
   - R1 Claude pronta
   - proxima demanda recomendada = endurecer pacote Murilo + concordancia

---

## 10. Resumo executivo de uma linha

Tudo que era engenharia exploratoria necessaria para chegar a um `pilot_120` revisavel ja foi feito; o proximo passo util nao e mais matching em massa, e sim fechar a fase de revisao humana e concordancia Claude vs Murilo.
