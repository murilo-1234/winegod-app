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
- produtor = quem FAZ o vinho (vinicola/bodega/domaine/chateau), NAO o nome do vinho. NUNCA deixe ??.
  Exemplos do nosso banco:
    "chateau levangile" → produtor: chateau levangile, vinho: pomerol
    "campo viejo reserva rioja" → produtor: campo viejo, vinho: reserva rioja
    "penfolds grange shiraz" → produtor: penfolds, vinho: grange shiraz
    "norton barrel select malbec" → produtor: norton, vinho: barrel select malbec
    "larentis malbec" → produtor: larentis, vinho: malbec
  Se produtor e vinho sao o mesmo nome, repita:
    "chateau montrose" → produtor: chateau montrose, vinho: montrose
    "quinta do noval" → produtor: quinta do noval, vinho: noval
    "dom perignon" → produtor: dom perignon, vinho: dom perignon
  O produtor e CRITICO — sem ele nao conseguimos fazer match no banco. Sempre extraia.
- vinho = nome do vinho SEM o produtor. NUNCA deixe ??.
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

FORTIFICADOS — sao VINHOS (W, cor f), NAO destilados:
  Sherry, porto, madeira, marsala, manzanilla, fino, oloroso, amontillado, palo cortado = W (cor f)
  Exemplos:
    "manzanilla en rama" → W|??|manzanilla en rama|es|f|palomino|andalucia|sanlucar de barrameda|...
    "porto tawny 10 years" → W|??|tawny 10 years|pt|f|??|douro|...|doce
  NAO classificar fortificados como S. Calvados, brandy, grappa = S.

Se 2 itens sao IDENTICOS (mesmo nome, mesma safra, mesmo produtor), o segundo pode ser =N (N = numero do primeiro).
Safra diferente = NAO e duplicata, classifique os dois normalmente.
Na duvida, classifique com W|... em vez de =N.

## FACA EM BLOCOS DE 250

### LOTE 1 (lote_t_590)
1. Leia C:/winegod-app/lotes_codex/lote_t_590.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_t_590.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 2 (lote_t_591)
1. Leia C:/winegod-app/lotes_codex/lote_t_591.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_t_591.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 3 (lote_t_592)
1. Leia C:/winegod-app/lotes_codex/lote_t_592.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_t_592.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 4 (lote_t_593)
1. Leia C:/winegod-app/lotes_codex/lote_t_593.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_t_593.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 5 (lote_t_594)
1. Leia C:/winegod-app/lotes_codex/lote_t_594.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_t_594.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 6 (lote_t_595)
1. Leia C:/winegod-app/lotes_codex/lote_t_595.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_t_595.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

### LOTE 7 (lote_t_596)
1. Leia C:/winegod-app/lotes_codex/lote_t_596.txt (os itens numerados)
2. Classifique em blocos de 250, salve em C:/winegod-app/lotes_codex/resposta_t_596.txt
3. NAO copie de outros arquivos. Classifique do ZERO.

## COMECE AGORA. NAO PARE ATE TERMINAR TODOS OS LOTES.
