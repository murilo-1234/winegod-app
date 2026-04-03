Voce vai ler um arquivo de texto e gerar um arquivo de saida. NAO crie scripts. NAO crie arquivos .py ou .ps1. Use APENAS sua ferramenta de escrita de arquivo (Write) para escrever o resultado.

## PROIBIDO
- Criar arquivos .py, .ps1, .js, .bat ou qualquer script
- Importar qualquer biblioteca
- Usar terminal/bash para rodar scripts
- Copiar conteudo de outros arquivos de resposta

## O QUE FAZER

Passo 1: Leia o arquivo do lote indicado abaixo
Passo 2: Ignore o cabecalho (tudo antes do "1.")
Passo 3: Para cada item numerado (1 a 1000), decida uma linha de resposta
Passo 4: Escreva TODAS as 1000 linhas de resposta no arquivo de saida indicado

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

### LOTE 1 (lote_r_1275)
1. Leia C:/winegod-app/lotes_codex/lote_r_1275.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_1275.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 2 (lote_r_1276)
1. Leia C:/winegod-app/lotes_codex/lote_r_1276.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_1276.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 3 (lote_r_1277)
1. Leia C:/winegod-app/lotes_codex/lote_r_1277.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_1277.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 4 (lote_r_1278)
1. Leia C:/winegod-app/lotes_codex/lote_r_1278.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_1278.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 5 (lote_r_1279)
1. Leia C:/winegod-app/lotes_codex/lote_r_1279.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_1279.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 6 (lote_r_1280)
1. Leia C:/winegod-app/lotes_codex/lote_r_1280.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_1280.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 7 (lote_r_1281)
1. Leia C:/winegod-app/lotes_codex/lote_r_1281.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_1281.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 8 (lote_r_1282)
1. Leia C:/winegod-app/lotes_codex/lote_r_1282.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_1282.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 9 (lote_r_1283)
1. Leia C:/winegod-app/lotes_codex/lote_r_1283.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_1283.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 10 (lote_r_1284)
1. Leia C:/winegod-app/lotes_codex/lote_r_1284.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_1284.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 11 (lote_r_1285)
1. Leia C:/winegod-app/lotes_codex/lote_r_1285.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_1285.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 12 (lote_r_1286)
1. Leia C:/winegod-app/lotes_codex/lote_r_1286.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_1286.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 13 (lote_r_1287)
1. Leia C:/winegod-app/lotes_codex/lote_r_1287.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_1287.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 14 (lote_r_1288)
1. Leia C:/winegod-app/lotes_codex/lote_r_1288.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_1288.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 15 (lote_r_1289)
1. Leia C:/winegod-app/lotes_codex/lote_r_1289.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_1289.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 16 (lote_r_1290)
1. Leia C:/winegod-app/lotes_codex/lote_r_1290.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_1290.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 17 (lote_r_1291)
1. Leia C:/winegod-app/lotes_codex/lote_r_1291.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_1291.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 18 (lote_r_1292)
1. Leia C:/winegod-app/lotes_codex/lote_r_1292.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_1292.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 19 (lote_r_1293)
1. Leia C:/winegod-app/lotes_codex/lote_r_1293.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_1293.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 20 (lote_r_1294)
1. Leia C:/winegod-app/lotes_codex/lote_r_1294.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_1294.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 21 (lote_r_1295)
1. Leia C:/winegod-app/lotes_codex/lote_r_1295.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_1295.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 22 (lote_r_1296)
1. Leia C:/winegod-app/lotes_codex/lote_r_1296.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_1296.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 23 (lote_r_1297)
1. Leia C:/winegod-app/lotes_codex/lote_r_1297.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_1297.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 24 (lote_r_1298)
1. Leia C:/winegod-app/lotes_codex/lote_r_1298.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_1298.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 25 (lote_r_1299)
1. Leia C:/winegod-app/lotes_codex/lote_r_1299.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_r_1299.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

## COMECE AGORA. NAO PARE ATE TERMINAR TODOS OS 25 LOTES.
