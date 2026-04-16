# Plano de Execucao Revisado: `nota_wcf v2`

**Data:** 2026-04-16  
**Status:** plano de execucao; implementacao ainda nao feita neste documento  
**Base:** handoff `2026-04-16_handoff_nota_wcf_v2_fechamento_produto.md` + decisoes adicionais fechadas em conversa

---

## 1. Objetivo

Implementar a `nota_wcf v2` no `winegod-app` com uma camada canonica unica de nota, separando:

- nota exibida
- fonte interna da nota
- selo publico de confianca
- metrica publica de quantidade de ratings

O sistema deve preservar a tese principal:

- WCF continua sendo a base tecnica principal quando existe amostra propria suficiente.
- Vivino e ancora forte quando existe evidencia publica, mas o scraping WCF local esta raso.
- Contextual fica reservado para vinhos que realmente dependem de contexto estrutural.
- Dados brutos nunca devem ser truncados, apagados ou substituidos por rotulos visuais.

---

## 2. Decisoes fechadas que a implementacao deve seguir

### 2.1. Selo publico

O selo publico passa a ser definido pelo contador publico canonico de ratings (`public_ratings_count`, equivalente ao `total_ratings` quando validado).

Regra fechada:

```text
public_ratings_count >= 75 -> verified sempre
25 <= public_ratings_count < 75 -> estimated
public_ratings_count < 25 -> nao ganha verified por evidencia publica
```

Importante:

- `nota_wcf_sample_size` nao decide se um vinho com `75+` ratings publicos e verified.
- `nota_wcf_sample_size` decide a fonte numerica da nota.
- `total_ratings`/`public_ratings_count` decide a confianca publica.

### 2.2. Fonte numerica da nota para vinhos com Vivino

Para vinho com `vivino_rating > 0`:

```text
nota_wcf_sample_size >= 25
-> usar WCF v2 com shrinkage por nota_base e clamp contra Vivino

nota_wcf_sample_size < 25
-> usar Vivino como ancora
-> tentar delta contextual aprendido pela Cascata B
-> usar nota_base como freio
-> aplicar clamp final
-> se nao houver contexto suficiente, usar Vivino direto com 2 casas
```

Isto substitui a ideia de copiar Vivino puro como regra principal e tambem evita um `delta global` grosseiro como regra principal.

### 2.3. Delta contextual

Para `nota_wcf_sample_size < 25`, a nota ancorada no Vivino deve tentar usar um delta contextual:

```text
vivino_proxy = vivino_rating + delta_contextual
```

O `delta_contextual` deve ser aprendido a partir de vinhos confiaveis do mesmo contexto, usando a Cascata B quando houver suporte suficiente.

Direcao tecnica:

- usar o bucket mais especifico disponivel e confiavel
- preferir delta por `sub_regiao + tipo`
- depois `regiao + tipo`
- depois `pais + tipo`
- depois `vinicola + tipo`
- se nenhum bucket tiver suporte defensavel, usar fallback Vivino direto

O delta global pode existir apenas como fallback tecnico muito conservador, mas nao deve ser a regra principal.

### 2.4. Fallback Vivino direto

Se `nota_wcf_sample_size < 25`, existe `vivino_rating > 0` e nao ha contexto suficiente:

```text
display_note = vivino_rating formatado com 2 casas
```

Exemplo:

```text
Vivino = 4.2
WineGod = 4.20
```

Este fallback deve ser raro, mas precisa existir para nao deixar vinho com evidencia publica sem nota.

### 2.5. Clamp fixo

O clamp fixo esta mantido:

```text
minimo = vivino_rating - 0.30
maximo = vivino_rating + 0.20
```

Uso:

- quando a nota vier de WCF e houver `vivino_rating`, aplicar clamp contra Vivino
- quando a nota vier de Vivino + delta contextual, aplicar clamp final
- quando a nota for Vivino direto, o clamp nao altera o valor, mas a regra pode ser aplicada de forma uniforme

Motivo:

- Vivino e ancora publica.
- WCF pequeno ou ajuste contextual pode corrigir um pouco.
- Nenhum ajuste deve exagerar sem evidencia forte.

### 2.6. Nota base e shrinkage

Manter a formula de shrinkage:

```text
nota_final = (n / (n + 20)) * nota_wcf
           + (20 / (n + 20)) * nota_base
```

Onde:

- `n` = `nota_wcf_sample_size`
- `nota_base` = media ponderada do bucket com teto `min(n, 50)`

Comportamento:

- a `nota_base` influencia de forma decrescente
- nao ha corte brusco
- em `n = 25`, a `nota_base` ainda pesa cerca de 44%
- em `n = 100`, a `nota_base` ainda pesa cerca de 17%
- quanto maior o sample WCF, mais a nota vira WCF propria

### 2.7. Penalidade contextual

A penalidade contextual esta decidida e deve ser implementada assim:

```text
penalidade = -0.5 * bucket_stddev
```

Aplicacao:

- somente quando `n = 0`
- somente quando a nota for puramente contextual
- nao aplicar quando houver WCF proprio
- nao aplicar quando houver Vivino fallback/proxy

Esta decisao fica fechada mesmo sabendo que o fator `0.5` foi originalmente uma escolha conservadora nao calibrada. Para esta execucao, nao sera reaberta.

### 2.8. Cascata B

Implementar Cascata B:

```text
1. sub_regiao + tipo, min=10
2. regiao + tipo, min=10
3. pais + tipo, min=10
4. vinicola + tipo, min=2
5. senao sem nota contextual
```

Regras:

- `pais` e campo tecnico canonico
- `pais_nome` e campo de exibicao
- `uvas` nao e degrau principal
- `uvas` pode ser refinador opcional apenas quando houver suporte suficiente

### 2.9. Metrica publica de ratings

O usuario nao deve ver o numero exato de ratings. Deve ver uma faixa:

```text
25+
50+
100+
200+
300+
500+
```

Regra:

```text
25-49 -> 25+
50-99 -> 50+
100-199 -> 100+
200-299 -> 200+
300-499 -> 300+
500+ -> 500+
```

Importante:

- `500+` e apenas rotulo visual.
- O numero real deve continuar salvo integralmente.
- Se `public_ratings_count = 10000`, armazenar `10000` e exibir `500+`.
- Nunca truncar o dado bruto para `500`.

### 2.10. Preservacao de dados

Regras absolutas:

- nao apagar reviews
- nao truncar `total_ratings`
- nao sobrescrever `vivino_rating`
- nao sobrescrever `vivino_reviews`
- nao substituir dado bruto por bucket visual
- nao inventar `total_ratings` a partir de `nota_wcf_sample_size`

---

## 3. Fase 1: Auditoria tecnica curta

Ler os documentos obrigatorios e auditar o estado real do repo:

- `backend/services/display.py`
- `scripts/calc_score.py`
- `scripts/calc_score_incremental.py`
- `backend/prompts/baco_system.py`
- `backend/routes/chat.py`
- `backend/tools/resolver.py`
- `backend/tests/test_new_wines_pipeline.py`
- `backend/tests/test_item_status.py`
- `database/schema_atual.md`
- `database/schema_completo.md`

Objetivos:

- identificar onde a nota e resolvida hoje
- identificar duplicacao entre runtime e score
- identificar onde `display_note_type` e consumido
- identificar se `display_note_source` ja existe ou precisa ser criado
- identificar se o Baco/UI aceitam `contextual`
- confirmar as colunas reais de `wines`

---

## 4. Fase 2: Contador publico canonico

Confirmar se `wines.vivino_reviews` pode ser tratado como contador publico confiavel equivalente a `total_ratings`.

Se for confiavel:

- usar `vivino_reviews` como insumo canonico de `public_ratings_count`
- documentar explicitamente essa decisao
- derivar `public_ratings_bucket` em runtime ou camada canonica

Se nao for confiavel:

- criar campo canonico `public_ratings_count`
- criar migration segura
- criar script de backfill idempotente
- manter `vivino_reviews` intacto

Em todos os casos:

- o dado bruto fica integral
- o bucket visual e derivado
- `nota_wcf_sample_size` nunca substitui `public_ratings_count`

---

## 5. Fase 3: Camada canonica da nota

Criar modulo unico, por exemplo:

```text
backend/services/note_v2.py
```

Responsabilidade:

- receber os dados do vinho
- resolver nota final
- resolver selo publico
- resolver fonte interna
- resolver bucket publico de ratings
- expor metadados de contexto

Saida minima:

```text
display_note
display_note_type
display_note_source
public_ratings_count
public_ratings_bucket
wcf_sample_size
context_bucket_key
context_bucket_level
context_bucket_n
context_bucket_stddev
context_refined_by_uva
```

Tipos publicos:

```text
verified
estimated
contextual
None
```

Fontes internas:

```text
wcf_direct
wcf_shrunk
vivino_contextual_delta
vivino_fallback
contextual
none
```

---

## 6. Fase 4: Materializacao da Cascata B

Avaliar custo de calcular contexto em runtime.

Direcao preferida:

- criar tabela auxiliar/materializada de buckets v2
- criar script idempotente de rebuild/backfill
- usar somente vinhos com `nota_wcf` propria como feeders
- nunca reciclar nota contextual como insumo de outro contexto

Cada bucket deve guardar:

```text
bucket_level
bucket_key
bucket_n
nota_base
bucket_stddev
delta_contextual
delta_n
updated_at
```

`delta_contextual` deve ser calculado com cohort confiavel, por exemplo:

```text
vivino_rating > 0
nota_wcf_sample_size >= 25
public_ratings_count >= 75
```

A formula do delta deve comparar WCF v2 contra Vivino:

```text
delta = nota_wcf_v2_ou_wcf_shrunk - vivino_rating
```

Usar mediana ou media robusta para evitar outliers.

---

## 7. Fase 5: Resolucao final da nota

### 7.1. Vinho com Vivino e `public_ratings_count >= 75`

Selo:

```text
display_note_type = verified
```

Fonte:

```text
se nota_wcf_sample_size >= 25:
    usar WCF v2 + shrinkage + clamp

se nota_wcf_sample_size < 25:
    usar Vivino + delta contextual, se houver
    senao Vivino direto com 2 casas
    aplicar clamp
```

### 7.2. Vinho com Vivino e `25 <= public_ratings_count < 75`

Selo:

```text
display_note_type = estimated
```

Fonte:

```text
se nota_wcf_sample_size >= 25:
    usar WCF v2 + shrinkage + clamp

se nota_wcf_sample_size < 25:
    usar Vivino + delta contextual, se houver
    senao Vivino direto com 2 casas
    aplicar clamp
```

### 7.3. Vinho com Vivino e `public_ratings_count < 25`

Nao promover automaticamente a `verified`.

Direcao:

- se houver WCF suficiente, usar WCF com cautela
- se nao houver WCF suficiente, usar fallback conservador ou sem nota conforme regra final de produto
- nao chamar de `verified`

### 7.4. Vinho sem Vivino

Direcao:

```text
se nota_wcf_sample_size > 0:
    usar WCF com shrinkage quando houver nota_base

se nota_wcf_sample_size = 0 e houver contexto:
    usar contextual puro com penalidade -0.5 * stddev

se nao houver WCF nem contexto:
    sem nota
```

---

## 8. Fase 6: Alinhar consumidores

Atualizar consumidores para usar a camada canonica:

- `backend/services/display.py`
- `scripts/calc_score.py`
- `scripts/calc_score_incremental.py`
- `backend/prompts/baco_system.py`
- `backend/routes/chat.py`, se necessario
- `backend/tools/resolver.py`, se necessario

Objetivo:

- impedir divergencia entre UI/runtime e score
- garantir que `verified`, `estimated` e `contextual` tenham semantica consistente
- garantir que o Baco entenda `contextual`
- expor `public_ratings_bucket` quando necessario para UI/Baco

Semantica do Baco:

- `verified`: linguagem direta
- `estimated`: linguagem aproximada
- `contextual`: linguagem segura, sem parecer erro
- `public_ratings_bucket`: falar em faixa, nao numero exato

---

## 9. Fase 7: Migrations e scripts

Criar somente o necessario depois da auditoria:

- migration para `public_ratings_count`, se faltar campo canonico
- migration/tabela para buckets v2, se a cascata for materializada
- script idempotente de rebuild de buckets
- script incremental para novos vinhos, se necessario

Regras:

- nada destrutivo
- nada que apague dados
- nada que trunque ratings reais
- backfill pesado deve ser separado como etapa operacional

---

## 10. Fase 8: Testes

Adicionar testes cobrindo:

- `75+ public_ratings_count` sempre vira `verified`
- `25-74 public_ratings_count` vira `estimated`
- `nota_wcf_sample_size >= 25` usa WCF v2
- `nota_wcf_sample_size < 25` usa Vivino + delta contextual quando ha bucket
- sem bucket suficiente, usa Vivino direto com 2 casas
- clamp impede exagero acima de `vivino + 0.20` e abaixo de `vivino - 0.30`
- `public_ratings_bucket` gera `25+`, `50+`, `100+`, `200+`, `300+`, `500+`
- `public_ratings_count = 10000` continua bruto internamente e exibe `500+`
- contextual puro aplica `-0.5 * bucket_stddev`
- nenhuma regra usa `nota_wcf_sample_size` como contador publico
- score usa a mesma nota canonica
- Baco/resolver nao quebram com `contextual`

---

## 11. Fase 9: Validacao

Rodar testes automatizados relevantes.

Se banco estiver disponivel, fazer validacoes pequenas e somente leitura:

- amostras de vinhos `75+` com WCF baixo
- amostras de vinhos `75+` com WCF `>=25`
- amostras por bucket de ratings publico
- amostras de contextual puro
- checagem de que dado bruto de ratings nao foi truncado

Nao rodar backfill massivo sem necessidade.

---

## 12. Entrega final esperada

Ao final da implementacao:

- camada canonica unica de nota criada
- `display.py` alinhado
- score alinhado
- Baco alinhado
- Cascata B suportada
- fallback dos vinhos com Vivino e WCF raso implementado
- bucket publico de ratings implementado
- dados brutos preservados
- testes novos cobrindo regras centrais
- relatorio final em `reports/` com arquivos alterados, testes, validacoes e pendencias

