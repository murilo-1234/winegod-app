# ETAPA 1 — Investigação nota_estimada

> STATUS EM 2026-04-12: documento histórico/arquivado.
> `nota_estimada` saiu da decisão do produto na `nota_wcf v2`.
> Para a direção atual, usar como referência principal:
> `C:\winegod-app\reports\2026-04-12_pesquisa_06_remocao_nota_estimada.md`

**Data da investigação:** 2026-04-11
**Escopo:** somente leitura. Nenhum `UPDATE`, nenhuma migration, nenhuma mudança em produção.

## 1. Fórmula real da `nota_estimada` no broker local

Fonte: `C:\Users\muril\vivino-broker\server.js`

- Constante real `ESTIMATED_RATING_GLOBAL_MEAN = 3.5`
- Constante real `ESTIMATED_RATING_DUMMY_WEIGHT = 3.0`

Trecho confirmado:

```js
const ESTIMATED_RATING_GLOBAL_MEAN = 3.5;
const ESTIMATED_RATING_DUMMY_WEIGHT = 3.0;
```

Resumo:
- Cada review recebe peso `max(1, sqrt(usuario_total_ratings))`
- A média ponderada é suavizada para `3.5` com peso dummy `3.0`
- Resultado final é salvo em `vivino_db.public.vivino_vinhos.nota_estimada`

## 2. O que é o `nota_wcf` atual do Render

### 2.1 Pipeline localizado

O pipeline atual do `nota_wcf` no Render **não** é a fórmula nova do broker.

Origem localizada:

1. `vivino_db.public.wcf_calculado`
   - Colunas: `vinho_id`, `nota_wcf`, `total_reviews_wcf`
   - Contagem atual: **1.289.183** linhas
   - Range `nota_wcf`: **1.00 – 5.00**
   - Média `nota_wcf`: **3.70**
   - Range `total_reviews_wcf`: **1 – 128**

2. Export local:
   - Arquivo `C:\winegod-app\scripts\wcf_results.csv`
   - Linhas de dados: **1.289.183**
   - Última modificação local observada: **2026-03-27 17:14:30**

3. Carga no Render:
   - `C:\winegod-app\scripts\calc_wcf.py`
   - `C:\winegod-app\scripts\calc_wcf_fast.py`
   - `C:\winegod-app\scripts\calc_wcf_batched.py`

4. Complemento no Render:
   - `C:\winegod-app\scripts\calc_wcf_step5.py`
   - Preenche faltantes por **média de região**
   - Depois fallback por **média de país**
   - Define `confianca_nota = 0.1`

### 2.2 Fórmula/fonte do `nota_wcf` atual

Conclusão objetiva:

- O Render hoje recebe um `nota_wcf` vindo da tabela local `wcf_calculado`
- Esse fluxo é **determinístico**
- Não encontrei uso de LLM nesse pipeline de carga
- Os arquivos `C:\natura-automation\_test_ct_score_precision_r*.py` usam **Gemini** para testes de score do CellarTracker, mas **não** são o pipeline que popula `nota_wcf` no Render

### 2.3 Evidência do lote que está no ar hoje

Estado live do Render em 2026-04-11:

- `wines.total`: **2.506.441**
- `wines.com_vivino_id`: **1.727.058**
- `wines.com_nota_wcf`: **1.727.054**
- `wines.com_confianca_nota`: **1.727.054**
- `wines.com_nota_wcf_sample_size`: **0**

Distribuição live de `confianca_nota` nos vinhos com `nota_wcf`:

- `0.20`: **651.609**
- `0.10`: **445.651**
- `0.40`: **243.497**
- `1.00`: **146.569**
- `0.60`: **138.480**
- `0.80`: **101.248**

Leitura:

- O miolo do pipeline bate com `wcf_calculado` + escada de confiança do `calc_wcf.py`
- O bloco de `0.10` é compatível com o fallback do `calc_wcf_step5.py`

**Inferência forte, mas ainda inferência:** o lote atual do Render parece ser:

- carga principal do CSV local `wcf_results.csv`
- mais complemento por região/país no próprio Render

### 2.4 Ponto crítico descoberto

Hoje o campo `nota_wcf_sample_size` está **NULL em 100%** dos vinhos.

Isso importa muito porque:

- `C:\winegod-app\backend\services\display.py`
- `C:\winegod-app\scripts\calc_score.py`
- `C:\winegod-app\scripts\calc_score_incremental.py`

todos exigem `nota_wcf_sample_size >= 25` para usar `nota_wcf`.

Na prática, hoje:

- a **nota pública** cai para `vivino_rating`
- o **winegod_score** também tende a usar `vivino_rating`, não `nota_wcf`

Ou seja:

**subir só uma nova nota sem decidir também sample/confiança/lógica não garante efeito no score do sistema.**

## 3. Cobertura da `nota_estimada` local

Fonte: `vivino_db.public.vivino_vinhos`

- Total de vinhos: **1.738.585**
- Com `nota_estimada`: **932.222**
- Cobertura: **53,6%**
- Range: **1.05 – 4.98**
- Média: **3.65**

## 4. Interseção local x Render

Ligação usada: `winegod.public.wines.vivino_id = vivino_db.public.vivino_vinhos.id`

Contagens em 2026-04-11:

- Vinhos do Render com `vivino_id` mas **sem** `nota_estimada` no local: **800.032**
- Vinhos com `nota_estimada` no local mas fora do Render: **5.196**
- Vinhos presentes nos dois lados e aptos a update: **927.026**

Observação:

- `wines.vivino_id` no Render está **sem duplicata** hoje
- `COUNT(vivino_id) = COUNT(DISTINCT vivino_id) = 1.727.058`

## 5. Correlação e impacto esperado

### 5.1 Amostra aleatória de 1.000 vinhos

Amostra: 1.000 vinhos aleatórios presentes nos dois lados, com os 3 valores disponíveis:

- `nota_wcf` atual do Render
- `nota_estimada` local
- `rating_medio` oficial

Matriz de correlação Pearson:

| Comparação | Correlação |
|---|---:|
| `nota_wcf` vs `nota_estimada` | **0,857613** |
| `nota_wcf` vs `rating_medio` | **0,197171** |
| `nota_estimada` vs `rating_medio` | **0,168016** |

Estatística de diferença na amostra (`nota_wcf` atual vs `nota_estimada` local):

- Diferença absoluta média: **0,1186**
- Diferença absoluta máxima: **2,57**
- Diferença `> 0,05`: **55,5%**
- Diferença `> 0,10`: **32,1%**
- Diferença `> 0,20`: **13,4%**

Leitura:

- sobrescrever `nota_wcf` por `nota_estimada` **não é ajuste cosmético**
- em muitos vinhos a troca será pequena
- em uma fatia relevante a troca será material

### 5.2 Checagem no banco inteiro

Para validar se a amostra não era azar:

- Correlação global no local `nota_estimada` vs `rating_medio`: **0,165159** em **932.222** vinhos
- Correlação global no Render `nota_wcf` vs `vivino_rating`: **0,084478** em **1.727.054** vinhos

Leitura:

- o `nota_wcf` atual do Render já é bem diferente da nota pública oficial
- a `nota_estimada` local também não anda colada no `rating_medio`
- portanto a decisão de sobrescrever campo existente é **decisão de produto**, não só técnica

## 6. Histograma 0–5 em buckets de 0,5

### 6.1 `nota_estimada` local

| Bucket | Qtd |
|---|---:|
| 1.0 | 1.157 |
| 1.5 | 2.754 |
| 2.0 | 11.043 |
| 2.5 | 46.549 |
| 3.0 | 215.666 |
| 3.5 | 480.010 |
| 4.0 | 163.683 |
| 4.5 | 11.360 |

### 6.2 `nota_wcf` atual do Render

| Bucket | Qtd |
|---|---:|
| 1.0 | 4.759 |
| 1.5 | 5.068 |
| 2.0 | 19.728 |
| 2.5 | 59.539 |
| 3.0 | 302.514 |
| 3.5 | 955.078 |
| 4.0 | 322.311 |
| 4.5 | 38.183 |
| 5.0 | 19.874 |

Leitura:

- os dois formatos concentram em `3.5`
- o `nota_wcf` atual do Render é mais espalhado na ponta alta
- o bucket `5.0` no Render não existe na `nota_estimada` local atual

## 7. Amostra dos 3 vinhos do handoff

| vivino_id | `rating_medio` local | `nota_estimada` local | `vivino_rating` Render | `nota_wcf` Render |
|---|---:|---:|---:|---:|
| 66284 | 4.60 | 4.54 | 4.60 | 4.59 |
| 1136137 | 4.10 | 4.14 | 4.10 | 4.17 |
| 1163903 | 4.10 | 4.13 | 4.10 | 4.19 |

Nos exemplos do handoff, os 3 valores ficam próximos. Mas isso **não** representa a base toda.

## 8. Resposta objetiva às perguntas da Etapa 1

### Pergunta 1 — valores reais da fórmula do broker

- `ESTIMATED_RATING_GLOBAL_MEAN = 3.5`
- `ESTIMATED_RATING_DUMMY_WEIGHT = 3.0`

### Pergunta 2 — quem populou o `nota_wcf` atual do Render

Melhor reconstrução encontrada:

- fonte local: `vivino_db.public.wcf_calculado`
- export: `C:\winegod-app\scripts\wcf_results.csv`
- carga: `C:\winegod-app\scripts\calc_wcf.py` / `calc_wcf_fast.py` / `calc_wcf_batched.py`
- complemento: `C:\winegod-app\scripts\calc_wcf_step5.py`
- natureza: **cálculo determinístico**, sem LLM

Observação importante:

- não localizei, no workspace atual, o script que gera a tabela local `wcf_calculado`
- localizei apenas a tabela pronta e os scripts de export/carga

### Pergunta 3 — sobrescrever `nota_wcf` mudaria muito ou pouco?

Resposta curta:

- **mudaria de forma material**
- não é um ajuste mínimo
- na amostra, **32,1%** dos vinhos mudaram mais de `0,10`
- **13,4%** mudaram mais de `0,20`

### Pergunta 4 — contagens de interseção

- Render com `vivino_id` mas sem `nota_estimada` local: **800.032**
- Local com `nota_estimada` mas fora do Render: **5.196**
- Presentes nos dois e aptos a update: **927.026**

### Pergunta 5 — distribuição

- `nota_estimada` local: mais concentrada em `3.5`, sem bucket forte em `5.0`
- `nota_wcf` Render: mais alta e mais espalhada, com bucket relevante em `5.0`

## 9. Conclusão prática

**Leitura histórica:** a seção abaixo registra o estado da investigação em 2026-04-11. Ela não substitui a decisão posterior de remover `nota_estimada` da camada de produto.

Se o objetivo é **atualizar o que realmente alimenta score e nota do WG com segurança**, os fatos de hoje são:

1. Em 2026-04-11, a métrica local analisada como candidata era `vivino_vinhos.nota_estimada`
2. O `nota_wcf` atual do Render veio de outro pipeline
3. O Render hoje está com `nota_wcf_sample_size = NULL` em toda a base
4. Por causa disso, o código atual tende a cair para `vivino_rating`
5. Então a decisão não é só “subir uma nota”

Ela precisa definir:

- qual campo receberá a nova nota
- se a nova nota deve entrar na nota pública
- se também sobe um campo de suporte para o score usar essa nota de verdade

## 10. Recomendação antes da Etapa 2

Recomendação técnica mais segura:

- **não sobrescrever nada ainda**
- primeiro decidir o destino da nova nota
- se a meta é mexer no score de verdade, tratar junto:
  - nota
  - confiança
  - e o papel do `sample_size`/campo equivalente

**Próximo passo:** parar aqui e validar esta investigação antes de qualquer migration ou import.
