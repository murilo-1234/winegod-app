INSTRUCAO: Execute tudo diretamente. NAO pergunte se pode comecar. NAO pare entre blocos. NAO pare entre lotes. NAO peca confirmacao. Faca TUDO de uma vez: 5 lotes, 4 blocos cada. So pare quando os 5 lotes estiverem prontos.

# TAREFA: Classificar vinhos em lotes de 250

## REGRAS CRITICAS

1. NUNCA use API, NUNCA importe openai, NUNCA escreva scripts de classificacao
2. VOCE MESMO classifica cada item com seu conhecimento de vinhos
3. NUNCA COPIE respostas de outros arquivos. Cada lote tem itens DIFERENTES
4. Leia os itens numerados dentro do arquivo lote_z_NNN.txt e classifique ESSES itens

## COMO FUNCIONA

5 lotes de 1000 itens. Para cada lote:
1. Leia o arquivo do lote
2. Classifique em 4 blocos de 250 (1-250, 251-500, 501-750, 751-1000)
3. Apos cada bloco, APPEND as 250 linhas no arquivo de resposta
4. Passe pro proximo lote SEM PARAR

## FORMATO (uma linha por item, sem numero)

- NAO e vinho (cerveja, agua, acessorio, neon sign, comida, gift basket, roupa, zippo, vela, copo, taca): X
- Destilado (whisky, gin, rum, vodka, grappa, brandy, cachaca, liqueur, liquore, limoncello, mirto, filu ferru): S
- Vinho: W|produtor|vinho|pais|cor|uva|regiao|subregiao|safra|abv|classificacao|corpo|harmonizacao|docura

## CAMPOS DO W

- produtor = vinicola/bodega/chateau, minusculo, sem acento. Quem FAZ o vinho
- vinho = nome do vinho SEM produtor, minusculo, sem acento
- pais = 2 letras (fr, it, ar, us, au, br, es, cl, pt, de, za, nz, at, hu, cz, hr, gb, ro, ge, md, am, etc). ?? se nao sabe
- cor: r=tinto w=branco p=rose s=espumante f=fortificado d=sobremesa
- uva, regiao, subregiao, safra, abv, classificacao, corpo, harmonizacao, docura (?? se nao sabe)

## COR — REGRAS ESPECIFICAS (MUITA ATENCAO)

- pinot gris, pinot grigio, chardonnay, sauvignon blanc, riesling, gewurztraminer, gruner veltliner, vermentino, fiano, trebbiano, garganega, pecorino, cortese, albarino, verdejo, viognier, chenin blanc, semillon, muscat blanc, furmint, feteasca alba, passerina = cor w (BRANCO)
- pinot noir, cabernet sauvignon, merlot, syrah, shiraz, malbec, tempranillo, sangiovese, nebbiolo, barbera, primitivo, zinfandel, zweigelt, blaufrankisch, nero d avola, carmenere, gamay, grenache, mourvedre, touriga, aglianico, dolcetto, corvina, montepulciano, cannonau, carignano = cor r (TINTO)
- champagne, prosecco, cava, cremant, spumante, sekt, brut, frizzante, pet-nat = cor s (ESPUMANTE)
- rose, rosato, rosado = cor p (ROSE)
- porto, sherry, madeira, marsala, manzanilla, fino, oloroso, amontillado = cor f (FORTIFICADO)
- passito, icewine, late harvest, auslese, beerenauslese, trockenbeerenauslese, recioto, vin santo, sauternes = cor d (SOBREMESA)

## DUPLICATAS — REGRA MUITO RIGOROSA

SAFRA DIFERENTE = NAO E DUPLICATA. NUNCA marque =N se a safra for diferente.

Exemplos de NAO duplicata:
- "zephyr pinot gris 2025" e "zephyr pinot gris 2023" = safras diferentes = classificar os dois com W|...
- "zephyr gewurztraminer 2024" e "zephyr gewurztraminer 2022" = safras diferentes = classificar os dois
- "zensa primitivo" e "zensa primitivo 135 abv" = mesmo vinho, so ABV no nome = marcar =N

SO marque =N quando:
- Nome IDENTICO ou quase identico (variacao de escrita, lixo do site)
- Mesmo produtor E mesma uva E mesma safra (ou ambos sem safra)

Na DUVIDA: classifique com W|... normalmente. Preferimos dados repetidos do que dados perdidos.

## EXECUCAO

### LOTE 1 (z_012)
1. Leia C:/winegod-app/lotes_codex/lote_z_012.txt (os itens numerados DENTRO deste arquivo)
2. Classifique ESSES itens do ZERO em 4 blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_z_012.txt

### LOTE 2 (z_013)
1. Leia C:/winegod-app/lotes_codex/lote_z_013.txt (os itens numerados DENTRO deste arquivo)
2. Classifique ESSES itens do ZERO em 4 blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_z_013.txt

### LOTE 3 (z_014)
1. Leia C:/winegod-app/lotes_codex/lote_z_014.txt (os itens numerados DENTRO deste arquivo)
2. Classifique ESSES itens do ZERO em 4 blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_z_014.txt

### LOTE 4 (z_015)
1. Leia C:/winegod-app/lotes_codex/lote_z_015.txt (os itens numerados DENTRO deste arquivo)
2. Classifique ESSES itens do ZERO em 4 blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_z_015.txt

### LOTE 5 (z_016)
1. Leia C:/winegod-app/lotes_codex/lote_z_016.txt (os itens numerados DENTRO deste arquivo)
2. Classifique ESSES itens do ZERO em 4 blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_z_016.txt

## COMECE AGORA. NAO PARE ATE TERMINAR OS 5 LOTES.
