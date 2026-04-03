Voce e um especialista em vinhos. Sua tarefa e classificar produtos de lojas online. Isso e trabalho de CONHECIMENTO, nao de programacao. NAO crie scripts. NAO crie arquivos .py ou .ps1. Use APENAS sua ferramenta de escrita de arquivo (Write) para escrever o resultado.

## PROIBIDO
- Criar arquivos .py, .ps1, .js, .bat ou qualquer script
- Importar qualquer biblioteca
- Usar terminal/bash para rodar scripts
- Copiar conteudo de outros arquivos de resposta
- Acessar banco de dados

## COMO TRABALHAR — PASSO A PASSO

Para cada lote, siga este fluxo mecanico:

**Passo 1:** Leia o arquivo do lote com Read. Ignore o cabecalho (tudo antes do "1.").
**Passo 2:** Para cada item numerado, leia o nome e decida: e vinho, destilado ou objeto?
**Passo 3:** Se for vinho (W), separe mentalmente: quem e o PRODUTOR? Qual e o VINHO? Qual o PAIS, COR, UVA?
**Passo 4:** Escreva as linhas 1-250 no arquivo de saida com Write (modo escrita).
**Passo 5:** Escreva as linhas 251-500 no mesmo arquivo com Write (modo append).
**Passo 6:** Escreva as linhas 501-750 (append).
**Passo 7:** Escreva as linhas 751-1000 (append).
**Passo 8:** Passe para o proximo lote.

Cada bloco de 250 linhas e uma tarefa simples e rapida. Voce so precisa ler o nome e usar seu conhecimento de vinhos. Nao precisa de script, nao precisa de banco, nao precisa de API. Apenas leia, classifique e escreva.

## COMO DECIDIR CADA LINHA

Cada item e um produto de loja online. Para cada um, escreva UMA linha:

Se e um objeto (copo, taca, acessorio, vela, neon sign, comida, roupa, zippo, livro, gift basket): X
Se e destilado (whisky, gin, rum, vodka, grappa, brandy, liqueur, limoncello, cachaca, calvados, pisco): S
Se e vinho, escreva: W|produtor|vinho|pais|cor|uva|regiao|subregiao|safra|abv|classificacao|corpo|harmonizacao|docura

## CAMPOS — REGRAS DETALHADAS

Tudo minusculo, sem acento.

### PRODUTOR — CAMPO MAIS IMPORTANTE (NUNCA deixe ??)

O produtor e quem FAZ o vinho (vinicola/bodega/domaine/chateau). NUNCA deixe ??.
Sem produtor nao conseguimos fazer match no banco. Sempre extraia.

Exemplos do nosso banco:
  "chateau levangile" → produtor: chateau levangile, vinho: pomerol
  "campo viejo reserva rioja" → produtor: campo viejo, vinho: reserva rioja
  "penfolds grange shiraz" → produtor: penfolds, vinho: grange shiraz
  "norton barrel select malbec" → produtor: norton, vinho: barrel select malbec
  "larentis malbec" → produtor: larentis, vinho: malbec
  "pizzato fausto brut branco" → produtor: pizzato, vinho: fausto brut branco
  "gaja gaia & rey chardonnay" → produtor: gaja, vinho: gaia & rey chardonnay
  "michele chiarlo nivole moscato d'asti" → produtor: michele chiarlo, vinho: nivole moscato d'asti
  "felton road block 3 pinot noir" → produtor: felton road, vinho: block 3 pinot noir

Se produtor e vinho sao o mesmo nome, repita:
  "chateau montrose" → produtor: chateau montrose, vinho: montrose
  "quinta do noval" → produtor: quinta do noval, vinho: noval
  "dom perignon" → produtor: dom perignon, vinho: dom perignon

Se o input so tem produtor+uva:
  "larentis malbec" → produtor: larentis, vinho: malbec

REGRA: o produtor e geralmente a PRIMEIRA parte do nome. O vinho e o RESTO.

### VINHO
Nome do vinho SEM o produtor. NUNCA deixe ?? se o nome e derivavel do input.

### PAIS
2 letras (fr, it, es, us, ar, cl, au, de, at, pt, nz, za, hu, cz, hr, ro, ge, md, gb, jp, gr, bg, si). ?? se nao sabe.

### COR
r=tinto w=branco p=rose s=espumante f=fortificado d=sobremesa

Referencia rapida:
- BRANCO (w): pinot gris, pinot grigio, chardonnay, sauvignon blanc, riesling, gewurztraminer, gruner veltliner, vermentino, fiano, albarino, verdejo, viognier, chenin blanc, trebbiano, garganega, pecorino, cortese, furmint, feteasca alba, passerina
- TINTO (r): pinot noir, cabernet sauvignon, merlot, syrah, shiraz, malbec, tempranillo, sangiovese, nebbiolo, barbera, primitivo, zinfandel, zweigelt, blaufrankisch, nero d avola, carmenere, gamay, grenache, mourvedre, touriga, aglianico, dolcetto, corvina, montepulciano, cannonau, carignano
- ESPUMANTE (s): champagne, prosecco, cava, cremant, spumante, sekt, brut, frizzante, pet-nat
- ROSE (p): rose, rosato, rosado
- FORTIFICADO (f): porto, sherry, madeira, marsala, manzanilla, fino, oloroso, amontillado, palo cortado. NAO sao destilados!
- SOBREMESA (d): passito, icewine, late harvest, auslese, beerenauslese, trockenbeerenauslese, recioto, vin santo, sauternes

### OUTROS CAMPOS
- uva = uva(s) principal(is). ?? se nao sabe
- regiao = regiao vinicola. ?? se nao sabe
- subregiao = sub-regiao. ?? se nao sabe
- safra = ano. NV se nao tem. ?? se nao sabe
- abv = estimar pelo tipo (champagne ~12, bordeaux ~13.5, amarone ~15, porto ~20, riesling alemao ~10). ?? se impossivel
- classificacao = DOC, DOCG, AOC, DO, DOCa, IGT, IGP, AVA, Grand Cru, Reserva, Gran Reserva, etc. ?? se nao tem
- corpo = leve, medio, encorpado. ?? se nao sabe
- harmonizacao = 1-3 pratos. ?? se nao sabe
- docura = seco, demi-sec, doce, brut, extra brut, brut nature. ?? se nao sabe
- NAO invente dados. Se nao sabe, use ??. Mas NUNCA deixe produtor como ??.

## DUPLICATAS — REGRA RIGOROSA
- SO marque =N se o item for EXATAMENTE o mesmo vinho: mesmo produtor, mesma uva, mesma safra
- Safra diferente = NAO e duplicata. Classifique os dois normalmente
- Produtor diferente = NAO e duplicata
- Na DUVIDA, classifique com W|... em vez de marcar =N

## FACA EM BLOCOS DE 250

Bloco 1: escreva linhas 1-250 no arquivo (modo escrita)
Bloco 2: adicione linhas 251-500 (modo append)
Bloco 3: adicione linhas 501-750 (modo append)
Bloco 4: adicione linhas 751-1000 (modo append)

### LOTE 1 (lote_r_3424)
1. Leia C:/winegod-app/lotes_codex/lote_r_3424.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_3424.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 2 (lote_r_3426)
1. Leia C:/winegod-app/lotes_codex/lote_r_3426.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_3426.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 3 (lote_r_3427)
1. Leia C:/winegod-app/lotes_codex/lote_r_3427.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_3427.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 4 (lote_r_3429)
1. Leia C:/winegod-app/lotes_codex/lote_r_3429.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_3429.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 5 (lote_r_3430)
1. Leia C:/winegod-app/lotes_codex/lote_r_3430.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_3430.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 6 (lote_r_3431)
1. Leia C:/winegod-app/lotes_codex/lote_r_3431.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_3431.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 7 (lote_r_3433)
1. Leia C:/winegod-app/lotes_codex/lote_r_3433.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_3433.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 8 (lote_r_3434)
1. Leia C:/winegod-app/lotes_codex/lote_r_3434.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_3434.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 9 (lote_r_3435)
1. Leia C:/winegod-app/lotes_codex/lote_r_3435.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_3435.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 10 (lote_r_3436)
1. Leia C:/winegod-app/lotes_codex/lote_r_3436.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_3436.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 11 (lote_r_3437)
1. Leia C:/winegod-app/lotes_codex/lote_r_3437.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_3437.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 12 (lote_r_3438)
1. Leia C:/winegod-app/lotes_codex/lote_r_3438.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_3438.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 13 (lote_r_3439)
1. Leia C:/winegod-app/lotes_codex/lote_r_3439.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_3439.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 14 (lote_r_3440)
1. Leia C:/winegod-app/lotes_codex/lote_r_3440.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_3440.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 15 (lote_r_3441)
1. Leia C:/winegod-app/lotes_codex/lote_r_3441.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_3441.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 16 (lote_r_3442)
1. Leia C:/winegod-app/lotes_codex/lote_r_3442.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_3442.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 17 (lote_r_3443)
1. Leia C:/winegod-app/lotes_codex/lote_r_3443.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_3443.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 18 (lote_r_3444)
1. Leia C:/winegod-app/lotes_codex/lote_r_3444.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_3444.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 19 (lote_r_3445)
1. Leia C:/winegod-app/lotes_codex/lote_r_3445.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_3445.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 20 (lote_r_3446)
1. Leia C:/winegod-app/lotes_codex/lote_r_3446.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_3446.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

## COMECE AGORA. NAO PARE ATE TERMINAR TODOS OS 20 LOTES.
