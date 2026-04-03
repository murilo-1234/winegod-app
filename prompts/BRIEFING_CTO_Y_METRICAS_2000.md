# BRIEFING — Analise de 2000 vinhos por faixa de score

## SITUACAO ATUAL — PRECISAO REAL NAO E 96%, E NO MAXIMO 34%

O sistema reportou 96% de match e depois 64% no teste de 200. A verificacao manual RIGOROSA (vinho a vinho, olhando produtor + nome da linha) mostrou que a **precisao REAL e 34%** (55 certos de 161 matches). A maioria dos "matches" sao falsos positivos — produtor errado, vinho errado do mesmo produtor, ou produto que nem vinho e.

Isso significa que dos ~1.9M vinhos que o sistema diz ter match, so ~640K sao matches corretos. O restante e lixo.

**Nosso objetivo: melhorar essa taxa pra pelo menos 50-60% com as metricas abaixo, e saber exatamente onde esta o corte de confianca.**

Problemas encontrados:
- ~15-20% da base wines_unique NAO e vinho (comida, destilado, perfume, eletronico)
- Matches abaixo de score 0.55 tem precisao de 6-18%
- Mesmo produtor mas vinho errado (Rutini Malbec vs Rutini Cab+Malbec)
- Score >= 0.80 tem 95% precisao, mas e so 10% do volume

Precisamos de uma analise MAIOR e MAIS DETALHADA pra tomar decisoes com confianca.

## O QUE QUEREMOS FAZER

Pegar 2000 registros da match_results_y (ou rodar match novo em 2000) distribuidos por faixa de score, 1% em 1%. Cada faixa de 50-51%, 51-52%, ... 99-100% tera ~20 registros. Analisar CADA UM dos 2000 manualmente.

### Distribuicao sugerida:

```
Score 0.30-0.39:  200 registros (20 por ponto percentual)
Score 0.40-0.49:  200 registros
Score 0.50-0.59:  200 registros
Score 0.60-0.69:  200 registros
Score 0.70-0.79:  200 registros
Score 0.80-0.89:  200 registros
Score 0.90-1.00:  200 registros
+ 600 registros SEM MATCH (no_match) distribuidos por ordem alfabetica
= 2000 total
```

Pegar por ORDEM ALFABETICA dentro de cada faixa (nao aleatorio). Assim garantimos diversidade de nomes.

## 7 METRICAS PRA ANALISAR EM CADA REGISTRO

### 1. Distribuicao de acerto por faixa de score (1% em 1%)

Pra cada faixa (ex: 0.63-0.64), classificar os ~20 registros como:
- **VINHO_CERTO** — match correto (mesmo produtor + mesmo vinho)
- **VINHO_ERRADO** — e vinho mas matchou com vinho errado
- **NAO_VINHO** — produto nao e vinho (comida, destilado, objeto)

Resultado esperado: uma tabela tipo:

| Faixa | Total | Vinho certo | Vinho errado | Nao-vinho | % acerto |
|---|---|---|---|---|---|
| 0.95-1.00 | 20 | 19 | 1 | 0 | 95% |
| 0.94-0.95 | 20 | 18 | 2 | 0 | 90% |
| ... | ... | ... | ... | ... | ... |
| 0.50-0.51 | 20 | 3 | 10 | 7 | 15% |

Isso nos da o CORTE EXATO de onde confiar.

### 2. Classificacao de nao-vinhos por categoria

Pra cada produto que NAO e vinho, classificar em:
- **DESTILADO** — gin, rum, whisky, vodka, tequila, cognac, grappa, cachaca, sake, etc.
- **COMIDA** — mel, cha, chocolate, cream, biscoito, conserva, tempero
- **OBJETO** — perfume, sapato, movel, eletronico, roupa, ferramenta
- **CERVEJA** — beer, lager, IPA, stout
- **COCKTAIL** — espresso martini, bitters, ready-to-drink

E listar as PALAVRAS-CHAVE que identificam cada categoria. Essas palavras viram filtro pra limpar a base.

### 3. Validacao por ordem alfabetica (produtor unico)

Quando match e duvidoso (score 0.50-0.80, mesmo produtor, nome levemente diferente):
- Buscar no Vivino quantos vinhos do MESMO PRODUTOR existem
- Se produtor tem 1 so vinho daquele tipo/uva → match CERTO (nao tem outro, e esse mesmo)
- Se produtor tem 5+ vinhos → precisa bater o nome da LINHA tambem

Exemplo:
```
"Conejo Negro Gran Malbec" → "Conejo Negro Malbec"
Se Conejo Negro so tem 1 Malbec no Vivino → sao o mesmo. CERTO.

"Rutini Cab Sauv Malbec" → "Rutini Malbec"
Se Rutini tem 15 vinhos no Vivino → sao diferentes. ERRADO.
```

Medir: quantos matches "duvidosos" sao resolvidos por essa regra?

### 4. Tipo cruzado (validacao simples)

Pra cada match, checar se o tipo bate:
- Loja diz "tinto", Vivino diz "branco" → ERRADO automatico
- Loja diz "rose", Vivino diz "tinto" → ERRADO automatico
- Loja diz "espumante", Vivino diz "tinto" → ERRADO automatico
- Ambos NULL → neutro

Medir: quantos erros seriam eliminados so com essa validacao?

### 5. Campos vazios como indicador de nao-vinho

Hipotese: produtos que NAO sao vinho tem mais campos NULL. Verificar:

| Campo | % NULL em vinhos reais | % NULL em nao-vinhos |
|---|---|---|
| tipo (tinto/branco) | ? | ? |
| uvas | ? | ? |
| safra | ? | ? |
| produtor_extraido | ? | ? |

Se nao-vinhos tem 90%+ de tipo=NULL E uva=NULL, isso vira um filtro automatico.

### 6. Score quando produtor bate vs nao bate

Separar os matches em:
- **Produtor bateu** (mesmo produtor nos dois lados)
- **Produtor nao bateu** (produtores diferentes)

Medir precisao de cada grupo. Hipotese: quando produtor bate, precisao e MUITO maior.

### 7. Analise dos SEM MATCH (600 registros)

Dos 600 sem match:
- Quantos sao vinhos reais que DEVERIAM ter match no Vivino? (buscar manualmente)
- Quantos sao nao-vinhos? (correto nao matchear)
- Quantos sao vinhos que o Vivino realmente nao tem? (vinhos de nicho/regionais)

Isso nos diz o RECALL real do sistema (quantos vinhos existentes no Vivino estamos perdendo).

## O QUE QUEREMOS DECIDIR COM ESSA ANALISE

1. **Qual o score de corte ideal?** (talvez 0.65, talvez 0.70, talvez 0.55 — depende dos dados)
2. **Quais filtros de nao-vinho implementar?** (lista de palavras + campos NULL)
3. **A validacao de tipo elimina quantos erros?** (se elimina muitos, implementar)
4. **A regra do produtor unico resolve quantos duvidosos?** (se resolve muitos, implementar)
5. **Devemos retrolimpar a wines_unique antes de rodar o Y em escala?** (provavelmente sim)
6. **Qual o recall real?** (quantos vinhos existentes estamos perdendo)

## COMO APRESENTAR OS RESULTADOS

Queremos ver:
1. A tabela de acerto por faixa de 1% (metrica 1)
2. A lista de palavras-chave de nao-vinho por categoria (metrica 2)
3. Quantos matches a regra do produtor unico resolve (metrica 3)
4. Quantos erros a validacao de tipo elimina (metrica 4)
5. A tabela de campos NULL em vinhos vs nao-vinhos (metrica 5)
6. Precisao com produtor batendo vs nao batendo (metrica 6)
7. Proporcao de vinhos reais nos sem-match (metrica 7)

Com esses dados, tomamos a decisao final de como proceder.

## REFERENCIA — ANALISE MANUAL DE 200 VINHOS (JA FEITA)

Leia o arquivo `C:\winegod-app\scripts\lista_200_vinhos.txt` — sao 200 matches ja verificados um a um pelo CTO anterior. Cada registro tem:
- Score, nome da loja, nome do Vivino, classificacao (OK/??/~~/XX)

E a analise detalhada de cada um dos 200 esta neste resultado:

### Exemplos de NAO-VINHO encontrados na base:
```
"bitter 820g" — comida (matched com bitter creek cabernet, score 0.51)
"manta lana mohair" — cobertor (matched com lana malbec, 0.45)
"shoes bags" — sapato (matched com no shoes pinot noir, 0.50)
"pantene hair spray no3" — cosmetico (sem match, correto)
"mini refrigerador portatil" — eletrodomestico (sem match, correto)
"spicchi di sole mulino bianco" — biscoito Barilla (matched com spicchi di luna falanghina, 0.54)
"espresso martini can" — cocktail pronto (matched com espresso chardonnay, 0.45)
"glen grant 18yo" — whisky (matched com bodegas grant fino, 0.42)
"rhum stroh" — rum (matched com theisen stroh, 0.38)
"cigar cao flathead camshaft" — charuto (matched com cigar box malbec, 0.31)
"le creme crema ai pomodorini 130g" — molho de tomate (matched com creme sel chardonnay, 0.37)
"philippine brand puree sweetened lemonsito 1kg" — polpa de fruta (matched com vm brand pinot franc, 0.34)
"miel de abeja medalla de oro 520g" — mel (matched com le miel pinot noir, 0.36)
"water biscuit stag" — biscoito (matched com water 2 wine stella, 0.42)
"birmingham cylinder pouf" — movel (matched com karen birmingham merlot, 0.31)
"grifo adaptable de lujo" — torneira (matched com el grifo rosado, 0.42)
"chilli addict korean chilli garlic" — molho (matched com chilli wine rose, 0.39)
"dupont minijet 261071" — isqueiro (matched com fernando dupont cabernet, 0.30)
"strainer baron hawthorne stainless steel" — coador (matched com hawthorne rose, 0.39)
"range tasmania tasmanian scottish oat cakes" — biscoito (matched com cuvee tasmania, 0.34)
"lapicero stitch 3d" — caneta (matched com red stitch cabernet, 0.48)
"pure small single temperature wine cabinet" — adega climatizada (matched com small malbec, 0.40)
"10 years single cask im geschenkkarton" — whisky (matched com years red, 0.43)
"chairman's reserve original" — rum (matched com chairman's reserve shiraz, 0.53)
"abanico de papel" — leque de papel (matched com abanico branco, 0.51)
"cestas gourmet el corte ingles" — cesta de presente (matched com el gourmet rosalina, 0.44)
"cha verde yai limao siciliano" — cha verde (matched com casa verde blanco, 0.36)
"bitters scrappys lime" — bitters pra cocktail (matched com lime berry, 0.31)
```

### Exemplos de MATCH ERRADO (mesmo produtor, vinho diferente):
```
"rutini cab sauvignon malbec" → "rutini malbec" (blend vs puro, 0.57)
"tommasi ripasso valpolicella" → "tommasi amarone" (Ripasso vs Amarone, 0.64)
"mucho mas rose" → "mucho mas merlot" (rose vs tinto, 0.48)
"fieldhouse 301 merlot" → "fieldhouse 301 white zinfandel" (merlot vs zinfandel, 0.52)
"lofi chardonnay" → "lofi sauvignon blanc chardonnay" (varietal vs blend, 0.83)
"kompassus espumante" → "kompassus espumante rose" (branco vs rose, 0.45)
"conejo negro gran malbec" → "conejo negro malbec" (gran vs regular, 0.78)
"fuenteseca bobal cabernet" → "fuenteseca bobal syrah" (cab vs syrah, 0.70)
"santa carolina vinho tinto suave" → "santa carolina coupage tinto" (suave vs coupage, 0.64)
"berton vineyards petite sirah" → "berton vineyard shiraz" (petite sirah vs shiraz, 0.42)
"cadus single vineyard vina vida malbec" → "cadus malbec" (single vineyard vs basic, 0.55)
"buil gine priorat" → "buil gine priorat natur vermut" (vinho vs vermute, 0.76)
```

### Exemplos de MATCH CORRETO:
```
"tyrian clouds shiraz" → "tyrian clouds shiraz" (0.88) — identico
"gaja dagromis barolo" → "gaja dagromis barolo" (0.83) — identico
"stags leap wine cellars cask 23" → "stags leap wine cellars cask 23" (0.77) — identico
"cappellano barolo pie rupestris" → "cappellano pie rupestris barolo" (0.84) — ordem diferente
"philipponnat clos des goisses juste rose" → identico (0.79)
"jackson estate shelter bay sauvignon blanc" → identico (0.87)
"krug clos du mesnil 2008" → "krug clos du mesnil" (0.58) — safra diferente mas mesmo vinho
"chateau quintus saint-emilion" → "chateau quintus le saint-emilion" (0.52) — mesmo vinho
"grancollina barbera d'asti" → "grancollina barbera d'asti" (0.42) — score baixo mas correto
```

Use esses exemplos como referencia pra classificar os 2000.

## NOTA IMPORTANTE

Nao estamos pedindo pra executar nada agora. Queremos sua opiniao sobre essa abordagem ANTES de rodar. Se voce tem sugestoes de metricas adicionais ou acha que alguma dessas nao faz sentido, fala. O objetivo e chegar na melhor decisao possivel com dados reais.
