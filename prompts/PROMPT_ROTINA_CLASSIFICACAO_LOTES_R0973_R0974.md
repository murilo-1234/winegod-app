ROUTINA OPERACIONAL PARA CLASSIFICACAO DE LOTES CODEX

Objetivo:
Criar uma rotina reutilizavel para classificar lotes de produtos de loja online e gerar arquivos de resposta com 1000 linhas, sem criar scripts novos, sem usar APIs externas e sem copiar conteudo de outros arquivos como atalho.

Contexto pratico:
Neste fluxo, os arquivos de entrada ficam em `C:/winegod-app/lotes_codex/`.
Cada lote contem um cabecalho de prompt e depois 1000 itens numerados.
A saida deve ser escrita em `C:/winegod-app/lotes_codex/resposta_r_NNNN.txt`.

REGRA CENTRAL:
O agente deve classificar do zero, usando o proprio criterio e conhecimento, mas seguindo um processo mecanico e consistente.
Se o item nao puder ser determinado com confianca, usar `??` nos campos permitidos.
O campo `produtor` nunca deve ficar `??` quando o item for vinho e o nome permitir inferencia razoavel.

Fluxo de trabalho recomendado:
1. Abrir o arquivo do lote.
2. Ignorar tudo antes do primeiro item numerado real.
3. Extrair apenas as 1000 linhas numeradas.
4. Para cada item, decidir entre `X`, `S` ou `W`.
5. Se for `W`, preencher todos os campos no formato:
   `W|produtor|vinho|pais|cor|uva|regiao|subregiao|safra|abv|classificacao|corpo|harmonizacao|docura`
6. Se houver duplicata exata, marcar com `=N` somente quando o vinho for o mesmo vinho exato segundo a regra do lote.
7. Escrever a saida final em um arquivo unico, com 1000 linhas, uma por item.

Regras de classificacao:
`X`
- Nao e vinho.
- Use para acessorios, caixas, gift basket, UI de site, comida, roupa, agua, cerveja, sidra, seltzer, itens de loja, texto promocional e outros nao-vinhos.

`S`
- Destilado.
- Use para whisky, gin, rum, vodka, tequila, grappa, cachaca, brandy, calvados, pisco, soju, baijiu e shochu.

`W`
- Vinho.
- Inclui tinto, branco, rose, espumante, champagne, prosecco, cava, cremant, pet-nat, fortificados e vinhos doces.

Regras de extracao de campos para `W`:
- `produtor`: quem produz o vinho. Normalmente a primeira parte do nome, mas pode ser uma casa produtora conhecida.
- `vinho`: o restante do nome apos remover o produtor.
- `pais`: codigo de 2 letras.
- `cor`: `r`, `w`, `p`, `s`, `f` ou `d`.
- `uva`: uva principal ou blend principal.
- `regiao`: regiao vinicola principal.
- `subregiao`: sub-regiao mais especifica, se houver.
- `safra`: ano em 4 digitos ou `NV`.
- `abv`: teor alcoolico estimado quando o valor exato nao estiver evidente.
- `classificacao`: DOC, DOCG, AOC, DO, DOCa, IGT, IGP, AVA, Reserva, Gran Reserva, Icewine e equivalentes.
- `corpo`: leve, medio ou encorpado.
- `harmonizacao`: 1 a 3 sugestoes de pratos.
- `docura`: seco, demi-sec, doce, brut, extra brut ou brut nature.

Regra forte para produtor:
Se o item parecer do tipo `marca + linha + uva`, manter a marca como produtor e a linha como parte do vinho.
Exemplo conceitual:
- `norton barrel select malbec` -> produtor `norton`, vinho `barrel select malbec`
- `chateau montrose` -> produtor `chateau montrose`, vinho `montrose`
- `quinta do noval` -> produtor `quinta do noval`, vinho `noval`

Regras para itens ambigios:
- Se o item tiver safra, ela deve ser mantida no campo `safra`.
- Se o item tiver tamanho, embalagem, caixa, etiqueta, gift box, numero de garrafas ou texto de loja, isso normalmente nao muda o vinho principal.
- Itens com o mesmo vinho mas safras diferentes nao sao duplicata.
- Itens com uvas diferentes nao sao duplicata.
- Na duvida, prefira classificar como `W` com campos incompletos em vez de transformar em duplicata.

Heuristicas uteis para cor:
- `s`: champagne, brut, prosecco, cava, cremant, frizzante, espumante, pet-nat.
- `p`: rose, rosato, rosado.
- `f`: porto, sherry, madeira, marsala, manzanilla, fino, oloroso, amontillado, palo cortado.
- `d`: passito, icewine, late harvest, auslese, beerenauslese, trockenbeerenauslese, recioto, vin santo, sauternes.
- `w`: pinot gris, pinot grigio, chardonnay, sauvignon blanc, riesling, gewurztraminer, gruner veltliner, vermentino, fiano, albarino, verdejo, viognier, chenin blanc, trebbiano, garganega, pecorino, cortese, furmint, feteasca alba, passerina.
- `r`: tintos em geral quando nao houver sinal claro dos demais.

Heuristicas uteis para pais e regiao:
- Reconhecer produtores e regioes muito frequentes no lote.
- Quando o nome for suficientemente especifico, inferir o pais a partir do produtor, da regiao ou da linguagem do nome.
- Se nao houver base minima, usar `??`.

Heuristicas uteis para safra:
- Procurar ano de 4 digitos.
- Se nao houver ano, usar `NV` em vez de `??` quando o item for claramente vinho sem safra aparente.

Heuristicas uteis para ABV:
- Champagne e espumantes secos: aproximadamente 12.
- Vinho tinto seco comum: aproximadamente 13.5.
- Vinhos mais encorpados, reserva ou premium: pode subir para 14 ou mais.
- Fortificados: aproximadamente 19.5 a 20.
- Doces e colheita tardia: aproximadamente 8.5 a 10.

Heuristicas uteis para corpo:
- `leve`: espumantes e brancos aromaticos mais leves.
- `medio`: brancos e tintos sem forte indicio de estrutura.
- `encorpado`: tintos estruturados, fortificados e doces.

Heuristicas uteis para harmonizacao:
- `leve`: peixes, frutos do mar, saladas, aves.
- `medio`: massas, queijos, carnes brancas.
- `encorpado`: carne vermelha, churrasco, pratos intensos.
- `s`: aperitivos, frutos do mar, sobremesas.
- `f` e `d`: foie gras, queijos azuis, sobremesas.

Rotina de processamento em lote:
1. Ler o arquivo do lote.
2. Localizar o primeiro item real numerado.
3. Ignorar o cabecalho inteiro.
4. Verificar se existem exatamente 1000 itens.
5. Classificar item por item.
6. Registrar duplicatas somente quando o item novo corresponder de forma muito direta ao vinho anterior.
7. Gerar o arquivo de saida com exatamente 1000 linhas.
8. Conferir contagem, inicio e fim do arquivo.

Checklist final:
- O arquivo de saida existe.
- O arquivo de saida tem 1000 linhas.
- O formato de cada linha bate com `X`, `S`, `=N` ou `W|...`.
- `produtor` nunca ficou vazio quando o item e vinho.
- Campos desconhecidos usam `??` ou `NV` conforme o caso.
- Nao foram criados scripts novos.

Observacao operacional:
Este documento foi pensado para orientar agentes futuros no mesmo workspace.
Ele descreve o processo, as heuristicas e os cuidados de validação que permitiram concluir os lotes `0973` e `0974` com saida consistente.
