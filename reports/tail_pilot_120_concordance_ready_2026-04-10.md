# Tail Pilot 120 -- Concordance Infrastructure READY (Demanda 9)

Data: 2026-04-11
Snapshot oficial do projeto ancorado em 2026-04-10.

## Status

**READY** -- toda a infraestrutura de revisao humana e comparacao Claude vs Murilo
esta no lugar. O pilot **ainda nao foi revisado por Murilo**; a comparacao real
depende exclusivamente do preenchimento humano e **nao foi executada nesta demanda**.

## O que foi endurecido em D9

### Tarefa A -- Pacote `for_murilo` com flags cruas

O CSV `reports/tail_pilot_120_for_murilo_2026-04-10.csv` foi regenerado via
`scripts/classify_pilot_r1.py` (atualizado) com join adicional contra
`reports/tail_working_pool_with_buckets_2026-04-10.csv`. Agora carrega
explicitamente:

| coluna | tipo | origem |
|---|---|---|
| `block` | trilha | working_pool_with_buckets |
| `overflow_from` | trilha | pilot_120 |
| `y2_any_not_wine_or_spirit` | **raw flag** | working_pool_with_buckets |
| `wine_filter_category` | **raw flag** | working_pool_with_buckets |
| `reason_short_proxy` | **raw flag** | working_pool_with_buckets |

O classificador R1 continua usando `reason_short_proxy` como fallback mas agora
tambem le `y2_any_not_wine_or_spirit` diretamente quando disponivel. A R1 em si
**nao mudou** -- os numeros de D8 sao preservados:

- MATCH_RENDER: 53, STANDALONE_WINE: 46, NOT_WINE: 20, MATCH_IMPORT: 1
- RESOLVED: 33, SECOND_REVIEW: 64, UNRESOLVED: 23

(Regressao zero. Endurecimento apenas de proveniencia.)

## Ferramentas criadas

| script | funcao |
|---|---|
| `scripts/validate_murilo_csv.py` | valida schema e valores validos do CSV preenchido por Murilo. Aceita CSV vazio (exit 2 = PENDING), parcial ou completo (exit 0 = OK) ou com erros (exit 1 = FAIL). |
| `scripts/compare_claude_vs_murilo.py` | compara R1 do Claude com preenchimento do Murilo. Calcula concordancia global por campo, matriz de confusao, concordancia por `pilot_bucket_proxy` e por `r1_confidence`, lista de disagreements. Detecta CSV vazio e sai com PENDING. |
| `scripts/build_adjudication_template.py` | em modo template, congela o schema de adjudicacao em `reports/tail_pilot_120_adjudication_template_2026-04-10.csv` (criado). Em modo real, le os disagreements e gera `reports/tail_pilot_120_adjudication_2026-04-10.csv` com so os casos divergentes e colunas `adjudicated_*` vazias. |

## O que sera comparado (campos)

Os 4 campos da taxonomia oficial comparados entre Claude R1 e Murilo R1:

| campo Claude | campo Murilo |
|---|---|
| `business_class` | `murilo_business_class` |
| `review_state` | `murilo_review_state` |
| `confidence` | `murilo_confidence` |
| `action` | `murilo_action` |

`murilo_notes` e livre e nao entra na concordancia.

Metricas que o comparador vai gerar quando houver preenchimento:

1. **Concordancia global por campo** -- % de match em cada um dos 4 campos.
2. **Matriz de confusao por campo** -- Claude (linhas) x Murilo (colunas).
3. **Concordancia por `pilot_bucket_proxy`** -- calibragem por bucket (P1..P6).
4. **Concordancia por `r1_confidence` do Claude** -- onde Claude tem HIGH, Murilo concorda mais? LOW tem mais drift?
5. **Lista de disagreements** com contexto curto (nome, produtor, reason_short_proxy, murilo_notes).

Saidas quando houver dados:
- `reports/tail_pilot_120_concordance_2026-04-10.md`
- `reports/tail_pilot_120_disagreements_2026-04-10.csv`
- `reports/tail_pilot_120_adjudication_2026-04-10.csv`

## O que falta

### Bloqueio real unico: **preenchimento humano**

A unica coisa que falta para a concordancia ser computada e Murilo preencher as 5 colunas `murilo_*` em `tail_pilot_120_for_murilo_2026-04-10.csv`. Nenhuma barreira tecnica.

As instrucoes operacionais estao em `reports/tail_pilot_120_murilo_instructions_2026-04-10.md`.

## Fluxo ponta-a-ponta (quando Murilo terminar)

```
# 1. Validador (schema + values check)
cd C:\winegod-app
python scripts/validate_murilo_csv.py
# exit 0 = ok / exit 1 = erros estruturais / exit 2 = pending (vazio)

# 2. Comparador Claude vs Murilo
python scripts/compare_claude_vs_murilo.py
# gera concordance.md + disagreements.csv

# 3. Builder da adjudicacao
python scripts/build_adjudication_template.py
# gera adjudication.csv com so os disagreements

# 4. Abrir o adjudication.csv e preencher as colunas adjudicated_*
#    (esta etapa e humana + Claude juntos, na proxima demanda)
```

## Dry-run executado nesta demanda

| etapa | resultado | exit code |
|---|---|---|
| validator | PENDING (120 rows, schema ok, 0/120 preenchidos) | 2 |
| comparator | PENDING (detecta 0 preenchidos) | 2 |
| adjudication builder | TEMPLATE gerado, PENDING para dados reais | 2 |

Nenhuma das ferramentas quebra em estado vazio. Todas sao idempotentes e
re-executaveis quando Murilo preencher.

## Escopo reafirmado

Esta demanda **NAO**:
- reclassifica o pilot (R1 Claude continua identica a D8)
- abre representativa 600
- abre impacto 120
- gera estimativa populacional
- reabre full fan-out
- executa a comparacao real

Esta demanda **produz**:
- for_murilo endurecido com flags cruas
- validador com 3 estados (OK/FAIL/PENDING)
- comparador com detecao de estado vazio
- builder de adjudicacao em 2 modos (template + real)
- instrucoes operacionais para Murilo
- este documento de status

## Artefatos gerados em D9

| artefato | tipo |
|---|---|
| `reports/tail_pilot_120_for_murilo_2026-04-10.csv` | CSV (regenerado com flags cruas) |
| `reports/tail_pilot_120_dossier_short_2026-04-10.csv` | CSV (regenerado) |
| `reports/tail_pilot_120_r1_claude_2026-04-10.csv` | CSV (regenerado, classificacao identica) |
| `reports/tail_pilot_120_adjudication_template_2026-04-10.csv` | CSV (19 cols, 0 rows) |
| `reports/tail_pilot_120_murilo_instructions_2026-04-10.md` | documento operacional |
| `reports/tail_pilot_120_concordance_ready_2026-04-10.md` | este documento |
| `scripts/classify_pilot_r1.py` | atualizado (D9 Tarefa A) |
| `scripts/validate_murilo_csv.py` | novo |
| `scripts/compare_claude_vs_murilo.py` | novo |
| `scripts/build_adjudication_template.py` | novo |
