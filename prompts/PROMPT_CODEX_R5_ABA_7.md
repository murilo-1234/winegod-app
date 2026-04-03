Voce vai ler um arquivo de texto e gerar um arquivo de saida. NAO crie scripts. NAO crie arquivos .py ou .ps1. Use APENAS sua ferramenta de escrita de arquivo (Write) para escrever o resultado.

## PROIBIDO
- Criar arquivos .py, .ps1, .js, .bat ou qualquer script
- Importar qualquer biblioteca
- Usar terminal/bash para rodar scripts
- Copiar conteudo de outros arquivos de resposta

## O QUE FAZER

Passo 1: Leia C:/winegod-app/lotes_codex/lote_z_007.txt
Passo 2: Ignore o cabecalho (tudo antes do "1.")
Passo 3: Para cada item numerado (1 a 1000), decida uma linha de resposta
Passo 4: Escreva TODAS as 1000 linhas de resposta em C:/winegod-app/lotes_codex/resposta_z_007.txt

## COMO DECIDIR CADA LINHA

Cada item e um produto de loja online. Para cada um, escreva UMA linha:

Se e um objeto (copo, taca, acessorio, vela, neon sign, comida, roupa, zippo, livro, gift basket): X
Se e destilado (whisky, gin, rum, vodka, grappa, brandy, liqueur, limoncello): S
Se e vinho, escreva: W|produtor|vinho|pais|cor|uva|regiao|subregiao|safra|abv|classificacao|corpo|harmonizacao|docura

Regras dos campos:
- Tudo minusculo, sem acento
- produtor = quem faz o vinho (vinicola). ?? se nao sabe
- vinho = nome do vinho sem o produtor. ?? se nao sabe
- pais = 2 letras (fr, it, es, us, ar, cl, au, de, at, pt, nz, za, hu, cz, hr, ro, ge, md, gb). ?? se nao sabe
- cor = r(tinto) w(branco) p(rose) s(espumante) f(fortificado) d(sobremesa)
  - BRANCO: pinot gris, pinot grigio, chardonnay, sauvignon blanc, riesling, gewurztraminer, gruner veltliner, vermentino, fiano, albarino
  - TINTO: pinot noir, cabernet sauvignon, merlot, syrah, malbec, tempranillo, sangiovese, nebbiolo, zweigelt, primitivo, zinfandel
  - ESPUMANTE: champagne, prosecco, cava, cremant, spumante, sekt, brut, frizzante
  - ROSE: rose, rosato, rosado
  - FORTIFICADO: porto, sherry, madeira, marsala, manzanilla
  - SOBREMESA: passito, icewine, late harvest, recioto, vin santo
- uva, regiao, subregiao = ?? se nao sabe
- safra = ano. NV se nao tem. ?? se nao sabe
- abv = estimar pelo tipo (champagne ~12, bordeaux ~13.5, amarone ~15, porto ~20). ?? se impossivel
- classificacao = DOC, DOCG, AOC, IGT, IGP, etc. ?? se nao tem
- corpo = leve, medio, encorpado. ?? se nao sabe
- harmonizacao = 1-3 pratos. ?? se nao sabe
- docura = seco, demi-sec, doce, brut, etc. ?? se nao sabe

Se 2 itens sao IDENTICOS (mesmo nome, mesma safra, mesmo produtor), o segundo pode ser =N (N = numero do primeiro).
Safra diferente = NAO e duplicata, classifique os dois normalmente.
Na duvida, classifique com W|... em vez de =N.

## FACA EM BLOCOS DE 250

### LOTE 1 (lote_t_560)
1. Leia C:/winegod-app/lotes_codex/lote_t_560.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_t_560.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 2 (lote_t_561)
1. Leia C:/winegod-app/lotes_codex/lote_t_561.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_t_561.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 3 (lote_t_562)
1. Leia C:/winegod-app/lotes_codex/lote_t_562.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_t_562.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 4 (lote_t_563)
1. Leia C:/winegod-app/lotes_codex/lote_t_563.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_t_563.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 5 (lote_t_564)
1. Leia C:/winegod-app/lotes_codex/lote_t_564.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_t_564.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 6 (lote_t_565)
1. Leia C:/winegod-app/lotes_codex/lote_t_565.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_t_565.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 7 (lote_t_566)
1. Leia C:/winegod-app/lotes_codex/lote_t_566.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_t_566.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 8 (lote_t_567)
1. Leia C:/winegod-app/lotes_codex/lote_t_567.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_t_567.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 9 (lote_t_568)
1. Leia C:/winegod-app/lotes_codex/lote_t_568.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_t_568.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 10 (lote_t_569)
1. Leia C:/winegod-app/lotes_codex/lote_t_569.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_t_569.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

## COMECE AGORA. NAO PARE ATE TERMINAR TODOS OS LOTES.
