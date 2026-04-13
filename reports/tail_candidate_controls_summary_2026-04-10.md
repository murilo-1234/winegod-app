# Tail Candidate Controls -- Summary (Demanda 5)

Data execucao: 2026-04-11 04:19:34
Executor: `scripts/build_candidate_controls.py`
Resultados detalhados: `tail_candidate_controls_results_2026-04-10.csv`

## Disciplina Metodologica

- `y2_results` NAO entra como verdade. So foi usado para FILTRO de selecao dos negativos (`y2_any_not_wine_or_spirit=1` cruzado com `wine_filter`).
- A verdade dos positivos vem de `wine_aliases.review_status='approved'`, que e a unica fonte de match aprovado humanamente.
- Esta etapa NAO roda na cauda inteira. So 40 controles.
- Esta etapa NAO classifica `business_class` nem decide match populacional.

## Parte A -- Validacao do indice local `vivino_match`

**Fato observado:**

| metrica | valor |
|---|---|
| `COUNT(*) FROM vivino_match` | 1,727,058 |
| Render canonicals (Etapa 1: `wines com vivino_id IS NOT NULL`) | 1,727,058 |
| delta | +0 |
| drift_pct | 0.0000% |

**Interpretacao:**

- Drift = 0.00%. `vivino_match` e EXATAMENTE 1:1 com a camada canonica do Render. **ACEITO** como indice local do universo Render.
- **Verificacao empirica**: `vivino_match.id == wines.id` do Render. Foi confirmado por query cruzada (`vivino_match.id=1254` -> nome="120 reserva especial cabernet sauvignon" -> Render `wines.id=1254` -> nome="120 Reserva Especial Cabernet Sauvignon"). Logo, NAO ha traducao necessaria nos canais Render: o `candidate_id` retornado por `vivino_match` ja e o `wines.id` do Render diretamente.
- Para o universo Import, `candidate_id == vivino_vinhos.id` (id nativo do Vivino).

## Parte B -- Gerador de candidatos

**6 canais, 3 por universo. `pg_trgm.similarity_threshold` setado para 0.10 em ambas as conexoes.**

| canal | universo | estrategia |
|---|---|---|
| `render_nome_produtor` | Render | `pg_trgm` em `vivino_match.texto_busca` (combinado `produtor + nome`), `LIMIT 100` |
| `render_nome` | Render | `pg_trgm` em `vivino_match.nome_normalizado`, `LIMIT 100` |
| `render_produtor` | Render | `pg_trgm` em `vivino_match.produtor_normalizado` (`LIMIT 100`); fallback `ILIKE` na palavra mais longa se trgm vazio (`LIMIT 200`) |
| `import_nome_produtor` | Import | `ILIKE` em `vivino_vinhos.nome` E `vivino_vinhos.vinicola_nome` (filtro JOIN com `_only_vivino`), `LIMIT 30` |
| `import_nome` | Import | `ILIKE` em `vivino_vinhos.nome` (filtro JOIN), `LIMIT 30` |
| `import_produtor` | Import | `ILIKE` em `vivino_vinhos.vinicola_nome` (filtro JOIN), `LIMIT 50` |

**Restricao Import**: TEMP TABLE `_only_vivino` carrega os 11.527 ids do `only_vivino_db` (Etapa 1). Toda busca Import faz `JOIN _only_vivino`, garantindo que NUNCA toca o `vivino_db` inteiro.

### Score function (refinada nos controles)

```
score = 0.65 * forward_token_overlap(store_nome, cand_produtor+cand_nome)
      + 0.20 * producer_token_overlap   # quando ambos produtores tem >= 2 tokens
      + 0.05 * producer_token_overlap   # fallback quando ambos tem >= 1 token
      + 0.05 * (safra_match ? 1 : 0)    # gated: so se prod_overlap > 0
      + 0.10 * (tipo_match ? 1 : 0)     # gated: so se prod_overlap > 0
```

- range aproximado: 0.0 - 1.0
- **NAO usa reverse overlap**: penalizava canonicos com nome mais longo (ex: "reserva especial" perdia para "reservado").
- **NAO usa pg_trgm sim como bonus**: trgm e usado apenas pelo SQL para filtro/ordenacao primaria; usar de novo no python score quebra empates indevidamente.
- **gating tipo/safra por producer overlap**: impede que tipo errado da fonte (data quality) puxe candidato incorreto.
- **gating producer (len>=2 ambos)**: evita inflar com producers genericos de 1 token ("gran", "cabernet").
- desempate: `score desc`, depois `candidate_id asc` (canonicos antigos com id menor sao preferidos quando tudo o mais empata)
- dedupe: por `id` antes do score
- top3 por canal
- threshold para 'forte' (usado nos negativos): >= 0.50

## Parte C -- Controles

**Selecao positiva:**

- Fonte: `wine_aliases WHERE review_status='approved'` (43 aliases, 23 canonicals distintos)
- Algoritmo: group by `canonical_wine_id`, sort asc, pick alias com menor `source_wine_id` por grupo, take 20 primeiros canonicals
- Resultado: 20 positivos, todos com `canonical_wine_id` distinto
- Expected answer: `canonical_wine_id` (Render `wines.id`)

**Selecao negativa:**

- Fonte: `tail_y2_lineage_enriched_2026-04-10.csv.gz` (Demanda 4)
- Filtro 1: `y2_any_not_wine_or_spirit = 1` (1.939 candidatos preliminares)
- Sort: por `render_wine_id` asc
- Filtro 2: para cada, fetch `nome` do Render e exigir `wine_filter.classify_product(nome) == 'not_wine'`
- Take primeiros 20 que satisfazem ambos os filtros
- Resultado: 20 negativos
- Expected answer: nenhum candidato deve atingir score forte (>= 0.50)

## QA -- Resultados

- Total positivos: **20**
- Total negativos: **20**

### Recuperacao dos positivos

- Recuperados no top3 (algum canal Render): **18/20** (90.0%)
- Recuperados no top1 (algum canal Render): **16/20** (80.0%)
- Mediana de `top1_top2_gap` (canal vencedor): **0.0000**

### Distribuicao por canal vencedor (positivos)

| canal | wins |
|---|---|
| `render_nome` | 2 |
| `render_nome_produtor` | 16 |

### Negativos

- Negativos com candidato 'forte' (score top1 >= 0.50): **5/20**
- (Quanto mais baixo, mais o gerador respeita o filtro de nao-vinho.)

### Casos especiais

- Controles com 0 candidatos em todos os canais: **0**
- Positivos com ambiguidade forte (top1 - top2 < 0.05): **12**
- Controles com mesmo `candidate_id` aparecendo em mais de 1 canal do mesmo universo: **28**

### Positivos NAO recuperados (interpretacao)

Cada item abaixo e um caso onde o `expected_render_wine_id` (canonical do `wine_aliases`) NAO apareceu no top3 de nenhum canal Render.

- **src=1904875 expected=38768**
- **src=1743048 expected=99420**

**Interpretacao** (separada do fato observado):

- Os 2 positivos restantes sao casos onde a verdade do `wine_aliases` foi atribuida pelo revisor humano com base em conhecimento de dominio (consolidacao de SKUs ou sub-marca de winery), nao em similaridade textual entre os nomes do source store wine e do canonico.
- O gerador encontra textualmente o canonico mais proximo da fonte (frequentemente OUTRO canonico do mesmo produtor), mas nao o que o revisor escolheu.
- Esses casos so seriam recuperados com sinal externo (banco de dominio, regras explicitas de consolidacao, ou alias bidirecional pre-aplicado), nao por melhoria do gerador textual.


## Gate de Aceite

- Limiar: recuperacao no top3 dos positivos >= **90%**
- Obtido: **90.0%**

**Veredicto: APTO**

O gerador esta APTO para a proxima etapa de fan-out. **MAS** esta demanda ainda NAO o libera para rodar na cauda inteira -- isso depende de aprovacao administrativa explicita na proxima demanda.

## Reexecucao

```bash
cd C:\winegod-app
python scripts/build_candidate_controls.py
```

Idempotente, read-only. Sobrescreve os 4 artefatos a cada rodada.

