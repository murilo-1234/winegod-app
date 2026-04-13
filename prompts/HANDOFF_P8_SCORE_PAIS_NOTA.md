# HANDOFF P8 — Execução Final de Nota e Custo-Benefício

## Quem é você neste chat
Você é um engenheiro sênior responsável por IMPLEMENTAR a correção final de notas e scores do WineGod.ai em `C:\winegod-app`.

Este handoff substitui a estratégia anterior baseada em `mediana_global_usd` como referência principal de preço.

Agora a decisão de produto e de modelagem já está tomada:

- `nota` e `custo-benefício` são conceitos diferentes
- `nota_wcf` bruta NÃO pode ser sobrescrita
- o cap do WCF (`±0.30` vs nota pública) existe apenas na camada de exibição/runtime
- `winegod_score` sem preço deve ser `NULL`
- NÃO materializar `display_note` no banco
- persistir só metadado cru necessário do WCF
- o novo `custo-benefício` deve usar referência de preço por `mesmo país + nota com peso por proximidade`

Seu trabalho é executar isso de ponta a ponta com validação, sem inventar regra nova.

---

## Estado atual do sistema (já verificado)

O sistema AINDA está no estado antigo. Assuma que nada do plano novo foi aplicado.

### Score atual ainda está antigo
Arquivo: `C:\winegod-app\scripts\calc_score.py`

Hoje o código ainda faz:

```python
preco_norm = round(preco_min_usd / mediana_usd, 4)
score = min(round(nota_ajustada / preco_norm, 2), 5.00) if preco_norm > 0 else nota_ajustada
...
else:
    score = round(nota_ajustada, 2)
```

Isso significa:
- fórmula antiga linear por mediana global ainda está ativa
- sem preço, `winegod_score = nota_ajustada`

### WCF ainda não persiste sample size
Arquivo: `C:\winegod-app\scripts\calc_wcf.py`

Hoje o script ainda atualiza só:
- `nota_wcf`
- `confianca_nota`
- `winegod_score_type`

Ele NÃO persiste `nota_wcf_sample_size`.

### Busca ainda expõe campos crus
Arquivo: `C:\winegod-app\backend\tools\search.py`

Hoje retorna:
- `vivino_rating`
- `winegod_score`
- `winegod_score_type`
- `nota_wcf`

Ainda NÃO existe camada canônica com:
- `display_note`
- `display_note_type`
- `display_note_source`
- `display_score`
- `display_score_available`

### Share page ainda mistura nota crua
Arquivo: `C:\winegod-app\frontend\app\c\[id]\page.tsx`

Hoje faz:

```ts
nota: w.nota_wcf || w.vivino_rating || 0,
nota_tipo: w.nota_wcf ? "verified" : "estimated",
score: w.winegod_score || 0,
```

Ou seja:
- ainda usa `nota_wcf || vivino_rating`
- ainda trata qualquer `nota_wcf` como `verified`
- ainda mostra `score` como `0` se não existir

### OG image ainda mistura nota crua
Arquivo: `C:\winegod-app\frontend\app\c\[id]\opengraph-image.tsx`

Hoje faz:

```ts
(wine.nota_wcf || wine.vivino_rating)
```

### API de share ainda serve campos crus
Arquivo: `C:\winegod-app\backend\db\models_share.py`

Hoje a query do share retorna:
- `vivino_rating`
- `nota_wcf`
- `winegod_score`
- `preco_min`, `preco_max`, `moeda`

Sem campos canônicos de display.

---

## Decisão final da métrica de custo-benefício

### Métrica escolhida
A referência de preço NÃO será mais a mediana global pura.

A nova referência será:

`mesmo país + nota com peso por proximidade`

Em termos práticos:
- comparar cada vinho com outros vinhos do MESMO `pais_nome`
- usar pares com nota próxima
- dar mais peso aos vinhos com nota mais próxima da nota alvo
- usar fallback quando a massa de pares for insuficiente

### Importante: qual “país” usar
Use `pais_nome` da tabela `wines` como país de origem do vinho.

Não tente resolver agora por país de loja/mercado final, porque o preço disponível no vinho é `preco_min` agregado e hoje não há um campo simples e estável no registro do vinho representando “mercado do preço mínimo”.

Isso deve ser documentado como limitação e melhoria futura.

---

## Evidência empírica já validada

Use estes números como base de decisão e referência para validação:

- base local com vinho + preço + nota: `46.879` vinhos
- mediana global do menor preço em USD: `US$ 19,62`

### País sozinho quase não ajuda
Medianas por país de origem ficaram todas muito parecidas:
- França: `US$ 19,68`
- Itália: `US$ 19,44`
- EUA: `US$ 19,04`
- Espanha: `US$ 19,99`
- Argentina: `US$ 19,79`
- Chile: `US$ 19,44`
- Portugal: `US$ 19,99`
- Brasil: `US$ 20,47`

Conclusão:
- `país` sozinho quase não muda nada
- `mediana por país` não basta

### País + nota tem cobertura suficiente
Cobertura usando `mesmo país + bin de nota 0,1` e exigindo pelo menos `20` pares:
- cobre `94,8%` dos vinhos com preço

Cobertura usando janela contínua `mesmo país + nota ±0,10` e exigindo pelo menos `20` pares:
- cobre `97,9%`

Cobertura usando janela contínua `mesmo país + nota ±0,20` e exigindo pelo menos `20` pares:
- cobre `98,8%`

### Faixa 4,1–4,2 por país tem massa forte em países grandes
Contagens já observadas:
- França: `1.093`
- EUA: `653`
- Itália: `559`
- Espanha: `164`
- Austrália: `147`
- Alemanha: `125`
- Portugal: `101`
- África do Sul: `59`
- Argentina: `56`
- Áustria: `61`
- New Zealand: `40`
- Suíça: `37`
- Chile: `31`
- Canadá: `30`
- Brasil: `7`

Conclusão:
- a métrica tem lastro suficiente para a maior parte da base com preço
- para países menores, precisa fallback

---

## Regra final de nota (qualidade)

### Dados-fonte
- `vivino_rating` = nota pública
- `nota_wcf` = nota recalculada pelo WineGod
- `nota_wcf_sample_size` = quantas reviews individuais entraram no cálculo WCF

### Regras obrigatórias
NÃO sobrescrever `nota_wcf`.
NÃO persistir `display_note` em coluna.

Resolver a nota em runtime no backend com esta regra:

1. Se `nota_wcf` existe, `nota_wcf_sample_size >= 100` e `vivino_rating > 0`
   - usar `clamp(nota_wcf, vivino_rating - 0.30, vivino_rating + 0.30)`
   - `display_note_type = "verified"`
   - `display_note_source = "wcf"`

2. Se `nota_wcf` existe, `nota_wcf_sample_size >= 25` e `< 100`, e `vivino_rating > 0`
   - usar `clamp(nota_wcf, vivino_rating - 0.30, vivino_rating + 0.30)`
   - `display_note_type = "estimated"`
   - `display_note_source = "wcf"`

3. Senão, se `vivino_rating > 0`
   - usar `vivino_rating`
   - `display_note_type = "estimated"`
   - `display_note_source = "vivino"`

4. Senão
   - `display_note = null`

Não invente uma regra alternativa.

---

## Regra final de custo-benefício

### Conceito
`custo-benefício = nota_base + ajuste_logaritmico_de_preco`

Mas a referência de preço agora NÃO é mais global.

### Nota base para o score
Use uma nota-base consistente com a regra de qualidade do produto.

Recomendação obrigatória para esta implementação:
- derive uma `nota_base_score` com a mesma lógica da nota canônica de qualidade
- ou seja: WCF capado quando a amostra permitir, senão fallback para nota pública

Não use `nota_wcf` bruta de sample fraco como base de score.

### Fórmula do score

```python
score = clamp(nota_base_score + 0.35 * ln(preco_referencia_usd / preco_min_usd), 0, 5)
```

Se não houver preço válido:
- `winegod_score = NULL`

### Referência de preço (ordem obrigatória)

Calcule `preco_referencia_usd` com esta hierarquia:

1. `mesmo pais_nome + nota próxima com peso por proximidade`
   - janela inicial recomendada: `±0,10`
   - exigir pelo menos `20` pares válidos
   - dar mais peso para pares com nota mais próxima da nota alvo

2. Se a etapa 1 não atingir massa mínima:
   - ampliar a janela para `±0,20`
   - manter peso por proximidade

3. Se ainda assim não atingir massa mínima:
   - usar mediana do `pais_nome`

4. Se ainda assim não houver massa:
   - usar mediana global

### Como ponderar a proximidade
Você deve implementar um método simples, auditável e estável.

Pode usar, por exemplo:
- peso triangular
- peso inversamente proporcional à distância
- ou kernel gaussiano simples

Requisito:
- notas mais próximas precisam pesar mais
- o método deve ser fácil de explicar internamente
- o resultado precisa ficar persistido em `winegod_score_components`

Documente a escolha e justifique.

### O que NÃO fazer
- não volte para `mediana_global_usd` como referência principal
- não use só `pais_nome`
- não compare por uva, região ou produtor neste ciclo
- não bloqueie a entrega esperando a solução “perfeita”

---

## Persistência e schema

### Adicionar só o mínimo necessário
Crie migration nova em `C:\winegod-app\database\migrations\` para adicionar:

- `nota_wcf_sample_size INTEGER`

Não adicionar:
- `display_note`
- `display_note_type`
- `display_note_source`
- `score_version`

### Onde guardar a versão da fórmula
Em `winegod_score_components` JSONB, inclua algo como:

```json
{
  "formula_version": "peer_country_note_v1"
}
```

### Components obrigatórios
O JSONB final do score deve conter material suficiente para auditoria.

Inclua no mínimo:
- `formula_version`
- `nota_base_score`
- `nota_base_source`
- `preco_min_usd`
- `preco_reference_strategy`
- `preco_reference_usd`
- `peer_country`
- `peer_window`
- `peer_count`
- `peer_weighting`
- `micro_ajustes`
- `score`

Se score ficar `NULL` por falta de preço:
- grave isso explicitamente no JSONB

---

## Implementação obrigatória por entrega

### ENTREGA 1 — Baseline e metadado WCF

1. Inspecionar schema atual e confirmar ausência de `nota_wcf_sample_size`
2. Criar migration adicionando apenas `nota_wcf_sample_size`
3. Atualizar `scripts/calc_wcf.py` para persistir `total_reviews_wcf` em `nota_wcf_sample_size`
4. Manter `nota_wcf` bruta intacta
5. Gerar baseline “antes” do score atual

O baseline deve incluir:
- distribuição atual do `winegod_score`
- quantos vinhos estão em `5.00`
- score por faixa de preço
- score com preço vs sem preço
- exemplos concretos de vinhos

Salvar o baseline em artefato dentro de `scripts/` ou `reports/`.

### ENTREGA 2 — Nova fórmula de score por pares

Atualizar `C:\winegod-app\scripts\calc_score.py` para:

1. deixar de usar `mediana_global_usd` como referência principal
2. calcular a nota-base do score com a regra canônica de qualidade
3. montar referência de preço por:
   - mesmo país
   - nota próxima
   - peso por proximidade
   - fallback obrigatório
4. aplicar:

```python
score = clamp(nota_base_score + 0.35 * ln(preco_referencia_usd / preco_min_usd), 0, 5)
```

5. definir `winegod_score = NULL` quando não houver preço
6. persistir detalhes em `winegod_score_components`

### ENTREGA 3 — Camada canônica no backend

Criar uma função/helper canônica no backend que resolva:
- `display_note`
- `display_note_type`
- `display_note_source`
- `display_score`
- `display_score_available`

Essa lógica deve:
- aplicar o cap do WCF só em runtime
- usar `nota_wcf_sample_size`
- evitar duplicação

Atualizar `C:\winegod-app\backend\tools\search.py` para expor os campos canônicos.

### ENTREGA 4 — API de share

Atualizar:
- `C:\winegod-app\backend\db\models_share.py`
- e qualquer ponto necessário das rotas de share

para que a resposta do share já carregue campos canônicos suficientes para frontend e OG.

Evite deixar `page.tsx` e `opengraph-image.tsx` reimplementando regra de nota.

### ENTREGA 5 — Baco

Atualizar:
- `C:\winegod-app\backend\prompts\baco_system.py`

para deixar explícito:
- usar a nota canônica
- não inferir entre `vivino_rating` e `nota_wcf` no prompt
- só falar de custo-benefício quando score existir
- quando não houver score, explicar que falta preço suficiente na base

Depois rodar os testes/padrões do Baco existentes no projeto e registrar resultado.

### ENTREGA 6 — Frontend

Atualizar:
- `C:\winegod-app\frontend\app\c\[id]\page.tsx`
- `C:\winegod-app\frontend\app\c\[id]\opengraph-image.tsx`

para:
- usar os campos canônicos
- parar de usar `nota_wcf || vivino_rating`
- parar de marcar qualquer `nota_wcf` como `verified`
- esconder custo-benefício quando `display_score_available = false`

Garantir consistência entre:
- backend
- Baco
- share page
- OG image

### ENTREGA 7 — Validação final

Gerar relatório “antes vs depois” provando:
- queda da saturação em `5.00`
- score `NULL` sem preço
- uso real da referência `mesmo país + nota por proximidade`
- thresholds de nota funcionando (`100/25/fallback`)
- share page e OG usando a mesma regra do backend

---

## Restrições de implementação

- NÃO remova campos antigos
- NÃO quebre compatibilidade sem necessidade
- NÃO reverta mudanças alheias no git
- NÃO invente regra nova de nota
- NÃO materialize fields de display no banco
- NÃO transforme `winegod_score_type` em fonte de verdade da nota

---

## Critérios de aceite

O trabalho só está concluído se todos estes pontos forem verdadeiros:

- `nota_wcf` bruta foi preservada
- `nota_wcf_sample_size` foi adicionada e populada
- `winegod_score` sem preço virou `NULL`
- nova fórmula usa referência por `mesmo país + nota com peso por proximidade`
- existe fallback explícito para janelas/cobertura insuficiente
- `formula_version` e detalhes da referência estão no JSONB
- backend centraliza a lógica canônica de display
- Baco usa a nota canônica
- share page usa a nota canônica
- OG image usa a nota canônica
- não existe mais regra `qualquer nota_wcf => verified`
- há relatório de impacto antes/depois

---

## Forma de entrega esperada no final do chat

No final, entregue:

1. resumo do que mudou
2. arquivos tocados
3. migration criada
4. comandos/testes rodados
5. resultados do baseline
6. resultados do after
7. riscos remanescentes
8. qualquer decisão técnica tomada dentro da métrica de proximidade

Não faça commit, a menos que o usuário peça.
