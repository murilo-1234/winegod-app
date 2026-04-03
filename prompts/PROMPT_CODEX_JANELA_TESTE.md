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

## FACA EM BLOCOS

Bloco 1: escreva linhas 1-250 no arquivo (modo escrita)
Bloco 2: adicione linhas 251-500 (modo append)
Bloco 3: adicione linhas 501-750 (modo append)
Bloco 4: adicione linhas 751-1000 (modo append)

Depois faca o mesmo para:
- lote_z_008.txt -> resposta_z_008.txt
- lote_z_009.txt -> resposta_z_009.txt
- lote_z_010.txt -> resposta_z_010.txt
- lote_z_011.txt -> resposta_z_011.txt

COMECE AGORA. NAO PARE ENTRE LOTES.
