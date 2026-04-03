# BRIEFING PARA O CTO — Analise dos 200 vinhos + proximos passos

## PRIMEIRO: RECONHECIMENTO

O trabalho que voce fez no Chat Y e excelente. Saimos de 0.6% de match (abordagem anterior com comparacao de strings) pra um sistema multi-estrategia funcional. Mesmo com os ajustes necessarios, o score >= 0.80 tem 95% de precisao — isso e muito bom. E o volume de 30%+ de matches ja representa ~1 milhao de vinhos conectados ao Vivino. Otimo trabalho.

## ANALISE DETALHADA DOS 200 VINHOS

Fizemos verificacao manual (humana) de cada um dos 200 vinhos. Resultado real:

### Precisao por faixa de score

| Score | Certos | Errados | Nao-vinho matchou | Total | Precisao |
|---|---|---|---|---|---|
| >= 0.80 | 20 | 1 | 0 | 21 | **95.2%** |
| 0.70-0.79 | 17 | 8 | 0 | 25 | **68.0%** |
| 0.55-0.69 | 13 | 14 | 0 | 27 | **48.1%** |
| 0.40-0.54 | 10 | 30 | 16 | 56 | **17.9%** |
| < 0.40 | 2 | 19 | 13 | 34 | **5.9%** |

### Categorias

| Categoria | Qtd | Descricao |
|---|---|---|
| CERTO | 55 | Match correto (mesmo produtor + mesmo vinho) |
| ERRADO | 75 | Match com vinho errado |
| NAO-VINHO MATCHOU | 31 | Produto nao-vinho matchou com vinho (mel, perfume, sapato, etc.) |
| SEM MATCH OK | 30 | Correto nao matchear (nao e vinho) |
| SEM MATCH PERDEU | 9 | Vinho real que nao encontrou match |

### 3 tipos de erro encontrados

**Tipo A — Nao-vinho na base (31 casos).** Exemplos:
- "bitter 820g" → matchou com "bitter creek cabernet" (0.51)
- "manta lana mohair" → matchou com "lana malbec" (0.45)
- "shoes bags" → matchou com "no shoes pinot noir" (0.50)
- "pantene hair spray no3" → sem match (correto)
- "mini refrigerador portatil" → sem match (correto)

**Tipo B — Mesmo produtor, vinho errado (18 casos).** Exemplos:
- "rutini cab sauvignon malbec" → "rutini malbec" (blend vs puro)
- "tommasi ripasso valpolicella" → "tommasi amarone" (Ripasso vs Amarone)
- "mucho mas rose" → "mucho mas merlot" (rose vs tinto)
- "fieldhouse 301 merlot" → "fieldhouse 301 white zinfandel"

**Tipo C — Produtor errado (57 casos).** Exemplos:
- "chateau pontet canet pauillac" → "chateau pauillac" (produtores diferentes)
- "champagne krug clos de mesnil" → "philibert de manneville" (totalmente errado)
- "chateau d'yquem Y bordeaux" → "ug bordeaux padovet" (absurdo)

---

## PROXIMOS PASSOS SOLICITADOS

### 1. RODAR TESTE COM 2000 VINHOS — POR ORDEM ALFABETICA

200 e pouco pra ter confianca estatistica. Precisamos de 2000 vinhos, mas NAO aleatorios. Pegar 100 vinhos de cada uma das 20 primeiras letras do alfabeto (A-T), em ordem alfabetica. Assim garantimos diversidade e nao ficamos presos numa letra so.

```
A: 100 vinhos | B: 100 | C: 100 | ... | T: 100 = 2000 total
ORDER BY nome_normalizado, pegar os primeiros 100 de cada letra
```

Objetivo:
- Confirmar as precisoes por faixa com amostra maior
- Mapear proporcao real de nao-vinhos na base
- Ter diversidade de nomes/produtores

### 2. VALIDACAO POR ORDEM ALFABETICA (IDEIA NOVA)

Quando o match e duvidoso (mesmo produtor, nome similar mas nao identico), verificar se existe mais de 1 vinho daquele produtor no Vivino:

```
Exemplo: "conejo negro gran malbec" matchou com "conejo negro malbec"
→ Checar: quantos Malbec do Conejo Negro existem no Vivino?
→ Se so tem 1: sao o mesmo vinho (Gran e so o nome completo). CERTO.
→ Se tem 2+ (Malbec e Gran Malbec separados): sao diferentes. ERRADO.
```

Isso resolve o erro Tipo B (mesmo produtor, vinho errado). Implementar como pos-processamento:
- Pra cada match com score 0.55-0.80, contar quantos vinhos do mesmo produtor existem no Vivino
- Se produtor tem 1 so vinho daquele tipo: confirmar match
- Se produtor tem varios: exigir match mais preciso no nome

### 3. FILTROS PRA IDENTIFICAR NAO-VINHOS (antes do match)

A wines_unique ainda tem ~15-20% de produtos que nao sao vinho. Ideias de filtros:

| Criterio | Logica | O que pega |
|---|---|---|
| Sem uva | Se nao tem tipo (tinto/branco/rose/espumante) E nao tem uva | Mel, perfume, sapato |
| Palavras-chave nao-vinho | Nome contem: spray, cream, shampoo, shoes, bag, refrigerator, deodorant, candle, chocolate, coffee, tea, biscuit, pouf, strainer, folder, shin guard, cotton pad, jackfruit, oat cake, hair, perfume, edp | Cosmeticos, comida, eletronicos |
| **Bebidas alcoolicas que NAO sao vinho** | Nome contem: bitter, bitters, gin, rum, rhum, whisky, whiskey, bourbon, vodka, sake, soju, tequila, mezcal, cognac, armagnac, cachaca, aguardente, grappa, pisco, absinthe, limoncello, amaretto, sambuca, ouzo, raki, slivovitz, pastis, fernet, chartreuse, jagermeister, baileys, kahlua, cointreau, grand marnier, drambuie, martini can, espresso martini | Destilados, licores, cocktails prontos |
| Sem produtor + nome curto | produtor_extraido = NULL E LENGTH(nome_normalizado) < 10 | Fragmentos inuteis |
| Preco absurdo | preco < 1.00 (em qualquer moeda) | Produtos de centavos |

**IMPORTANTE:** Essa lista de bebidas alcoolicas nao-vinho tambem deve ser rodada na wines_unique (retrolimpeza). A fase W e X nao pegaram tudo. Ao limpar a base ANTES do match, a precisao sobe automaticamente sem mexer no threshold.

Sugestao: rodar esses filtros na wines_unique ANTES do match. Marcar como `is_wine = false` e excluir do matching. Depois considerar rodar essa mesma limpeza retroativamente no wines_clean e wines_unique (refazer contagem).

### 4. SOBRE THRESHOLDS — NAO SUBIR PRA 0.75

Na verificacao manual vimos que muitos matches com score 0.55-0.70 ESTAO CORRETOS. O problema nao e o threshold — e o lixo na base (nao-vinhos) e a falta de validacao de tipo.

Sugestao: MANTER threshold atual, mas aplicar os filtros (nao-vinho + tipo + ordem alfabetica). Depois rodar os 2000 e medir a precisao nova. Ai sim decidimos threshold com dados reais.

### 5. VALIDACAO DE TIPO (RAPIDA)

Se loja diz "rose" e Vivino diz "tinto" → rejeitar match. Isso eliminaria erros como:
- "mucho mas rose" → "mucho mas merlot" (tipo diferente)
- "fieldhouse 301 merlot" → "fieldhouse 301 white zinfandel"

Implementar: `IF loja.tipo != vivino.tipo AND ambos nao sao NULL → score = 0`

---

## RESUMO DO QUE PEDIMOS

1. **Rodar teste com 2000 vinhos** (mesmo formato da lista de 200)
2. **Implementar validacao por ordem alfabetica** (1 vinho do produtor = confirmar match)
3. **Filtrar nao-vinhos** antes do match (palavras-chave + sem tipo/uva)
4. **Subir threshold** pra >= 0.75 (HIGH) e 0.55-0.75 (quarentena)
5. **Validar tipo** (rose != tinto = rejeitar)
6. **Re-rodar analise** com as melhorias e reportar nova precisao

Nao tem pressa. O trabalho base ja esta excelente. Estamos refinando.
