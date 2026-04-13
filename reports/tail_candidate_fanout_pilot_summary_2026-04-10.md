# Tail Candidate Fan-out Pilot -- Summary (Demanda 6A)

Data de execucao: 2026-04-11 14:27:00
Executor: `scripts/run_candidate_fanout_pilot.py` + `scripts/finalize_d6_partial.py`

Snapshot oficial do projeto ancorado em 2026-04-10. Artefatos preservam o sufixo `2026-04-10` mesmo quando a execucao ocorre em data posterior.

## VEREDICTO

**NAO PRONTO**

O runner da Demanda 6 NAO esta pronto para fan-out full. Motivo: **inviabilidade operacional por throughput observado**. Detalhes abaixo.

## Estado inicial encontrado (Tarefa A)

- checkpoint existente (`tail_candidate_fanout_pilot_checkpoint_2026-04-10.json`) com:
  - `completed_batches = []`
  - `processed_items = 0`
  - `done = false`
  - `started_at = 2026-04-11 10:45:33`
- diretorio `reports/.fanout_pilot_partial/` existia mas **estava vazio** (0 parciais)
- artefatos finais nao existiam

**Acao tomada:** checkpoint zerado sem parciais reais NAO conta como prova de resume. Estado classificado como **STALE** e **descartado** com `--fresh`. Reinicio limpo.

## Tarefa B -- Prova de `--stop-after 3`

Execucao: `python scripts/run_candidate_fanout_pilot.py --fresh --stop-after 3`

Evidencia (do checkpoint imediatamente apos o stop):

- `completed_batches = [0, 1, 2]`
- `processed_items = 750`
- `batch_timings_sec = [1442.961, 2253.460, 2024.929]`
- 3 arquivos parciais em disco: `batch_00000.csv`, `batch_00001.csv`, `batch_00002.csv`
- exit 0 do processo
- log: `[--stop-after=3] parando apos 3 batches desta sessao`

**`--stop-after 3` comprovado.**

## Tarefa C -- Prova de `resume` por execucao

Execucao: `python scripts/run_candidate_fanout_pilot.py` (sem `--fresh`)

Evidencias:

- log: `[checkpoint] RESUME de 3 batches ja completos (resume #1)`
- `resume_count = 1` no checkpoint apos retomada
- batches completos apos a retomada: `[3, 4]` (continuaram do proximo batch nao-completo)
- nenhum recomputo de batches 0-2 (preservados do run anterior)

**Resume comprovado por execucao real.**

## Tarefa D -- Decisao administrativa de parada

Apos 5 batches concluidos (1.250 itens = 12.5% do piloto), a projecao de tempo baseada na mediana dos batches pos-bootstrap indicou inviabilidade operacional. A parada foi ordenada pelo administrador em `2026-04-11 ~14:30`.

- processo Python PID 20392 foi terminado via `taskkill`
- batch 5 (que estava em processamento no momento da parada) foi perdido
- checkpoint mantido integro: `completed_batches=[0,1,2,3,4]`, `done=false`
- artefatos finais foram consolidados pelo script `finalize_d6_partial.py` a partir dos 5 parciais existentes

## Parte A -- Selecao do piloto

1. Leitura de `tail_y2_lineage_enriched_2026-04-10.csv.gz` (779.383 ids).
2. `ORDER BY render_wine_id ASC` (deterministico).
3. Exclusao dos 40 controles (positivo + negativo, Demanda 5).
4. Take dos primeiros 10.000.

- `PILOT_SIZE` (target) = 10,000
- `PILOT_SIZE` (efetivamente executado) = **1,250**
- Controles excluidos: 40
- `pilot_hash` (sha256): `5baa898d7b7d6eae...`
- Primeiro id processado: 1740586
- Ultimo id processado: 1742002

## Parte B -- Checkpoint

- `BATCH_SIZE` = 250
- Total de batches (target): 40
- Batches concluidos: **5** (12.5%)
- `resume_count` = 1
- Resume testado por execucao real: **SIM**
- `done` = False

## Parte C -- Execucao efetiva

- Itens submetidos aos batches concluidos: **1,250**
- Rows no detail CSV: **12,617**
- Rows no per_wine CSV: **1,250**

## QA -- Validacoes

| check | valor | resultado |
|---|---|---|
| target 10.000 atingido | 1,250/10.000 | **FALHA (parado por decisao administrativa)** |
| render_wine_id unico em per_wine | 1,250/1,250 | OK |
| nenhum controle entre os submetidos | 0 | OK |
| detail rows > 0 | 12,617 | OK |
| logica D5 congelada (import de `build_candidate_controls`) | sim | OK |

## Cobertura por universo (sobre 1.250 itens)

| metrica | wines | % |
|---|---|---|
| pelo menos 1 candidato Render | 1,250 | 100.00% |
| pelo menos 1 candidato Import | 496 | 39.68% |
| 0 candidatos Render | 0 | 0.00% |
| 0 candidatos Import | 754 | 60.32% |
| 0 candidatos em ambos | 0 | 0.00% |

## Distribuicao de canal top1 por universo

| canal | top1_render | top1_import |
|---|---|---|
| `import_nome` | 0 | 396 |
| `import_nome_produtor` | 0 | 2 |
| `import_produtor` | 0 | 98 |
| `render_nome` | 745 | 0 |
| `render_nome_produtor` | 459 | 0 |
| `render_produtor` | 46 | 0 |

## Scores

| metrica | valor |
|---|---|
| mediana top1_render_score | 0.4349 |
| p90 top1_render_score | 0.5778 |
| mediana top1_import_score | 0.2167 |
| p90 top1_import_score | 0.3503 |
| mediana top1_render_gap | 0.0000 |
| mediana top1_import_gap | 0.0000 |

## Throughput (leitura com disciplina)

**Tempo por batch registrado:**

| batch | tempo (s) | tempo (min) | observacao |
|---|---|---|---|
| 0 | 1443.0 | 24.05 | com bootstrap (run 1) |
| 1 | 2253.5 | 37.56 | pos-bootstrap (run 1) |
| 2 | 2024.9 | 33.75 | pos-bootstrap (run 1) |
| 3 | 1970.1 | 32.83 | pos-bootstrap (run 2, resume) |
| 4 | 2629.1 | 43.82 | pos-bootstrap (run 2, resume) |

**Agregados:**

- tempo batch 0 (com bootstrap): **1443.0s (24.0 min)**
- mediana batches 1..N (pos-bootstrap, n=4): **2139.2s (35.7 min)**
- p90 batches 1..N: **2516.4s (41.9 min)**
- media batches 1..N: **2219.4s (37.0 min)**
- tempo total efetivo (soma dos timings): **10320.5s (172.0 min)**
- itens por minuto (sobre 1,250 itens em 172.0 min): **7.27**

**Projecao do piloto de 10.000 (se tivesse sido concluido):**

- formula: `batch0 + mediana_pos_bootstrap * 39 = 1443s + 2139s * 39`
- tempo total estimado: **84872s = 1415 min = 23.6h**

**Projecao do fan-out full (779.383 itens) usando a mesma taxa pos-bootstrap:**

- formula: `(mediana_pos_bootstrap / batch_size) * 779.383 + batch0`
- tempo estimado: **6670450s = 1853h = 77.2 dias**

## Leitura operacional

- Esta demanda valida OPERACAO do runner. NAO substitui o gate de qualidade da Demanda 5.
- O gate de qualidade ja foi atingido no piso exato (90% top3 positivos) em D5 e permanece valido.
- O motivo da reprovacao desta demanda e **exclusivamente operacional**: throughput observado e incompativel com o tamanho do universo alvo.

## Erros e retries observados

- **Nenhum erro** registrado durante os 5 batches concluidos.
- A parada do processo em batch 5 foi ordenada administrativamente (nao foi falha).

## Bloqueios reais para fan-out full

1. **Throughput inviavel**: ~36 min/batch implica ~77 dias para os 779.383 itens. Inviavel para qualquer cronograma de produto.
2. **Batch 0 pago a cada sessao**: bootstrap carrega 1.727.058 vivino_ids do Render + constroi TEMP TABLE `_only_vivino`. Custo fixo ~5 min por run (pode ser aceitavel isolado, mas empilha quando o runner precisa de muitos resumes).
3. **Sem paralelismo**: runner atual e sequencial single-thread. Nao tem pool de conexoes nem worker por canal.
4. **Conexao Render distante**: latencia Brasil -> Oregon, plano Basic, risco de SSL drop em execucao longa.

## O que seria necessario para liberar fan-out full

(NAO escopo desta demanda. Registrado apenas como bloqueio real.)

- paralelizar o loop de canais (por exemplo, batch de N wines rodando em paralelo contra cada canal), mantendo a logica D5 congelada
- ou rodar os candidate lookups em batch unico por canal ao inves de loop por wine
- ou rodar o fan-out nao no seu laptop em Brasil, e sim em um worker proximo ao Render (Oregon) para eliminar latencia de rede
- remedir throughput e revalidar antes de fan-out

## Artefatos gerados

| artefato | status |
|---|---|
| `tail_candidate_fanout_pilot_detail_2026-04-10.csv.gz` | gerado (12,617 rows, sobre 1.250 itens) |
| `tail_candidate_fanout_pilot_per_wine_2026-04-10.csv.gz` | gerado (1,250 rows = submetidos) |
| `tail_candidate_fanout_pilot_summary_2026-04-10.md` | este arquivo |
| `tail_candidate_fanout_pilot_checkpoint_2026-04-10.json` | mantido (`done=false`, 5/40 batches) |

## Veredicto final

**NAO PRONTO PARA FAN-OUT FULL.**

- Runner COMPILA e EXECUTA corretamente: `--stop-after` e `resume` comprovados por execucao real.
- Logica da Demanda 5 preservada sem drift (importada do script original).
- Nenhum erro registrado no que foi executado.
- **Bloqueio unico e decisivo: throughput operacional.**

Fan-out full fica bloqueado. Proxima frente precisa endereca throughput antes de tentar o universo inteiro.

