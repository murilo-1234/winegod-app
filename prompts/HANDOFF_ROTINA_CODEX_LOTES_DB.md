# Handoff - Rotina de Classificacao Codex por Lotes

Este documento registra a rotina operacional que funcionou para classificar lotes `lote_r_####.txt` e gerar `resposta_r_####.txt` sem depender de script novo.

## Objetivo

Gerar, para cada lote de 1000 itens:
- um arquivo de resposta com exatamente 1000 linhas numeradas
- uma classificacao por item seguindo o formato exigido
- sem criar arquivos de script
- sem copiar respostas prontas de outros arquivos
- sem interromper o fluxo entre lotes

## Regras Nao Negociaveis

- Nao criar arquivos `.py`, `.ps1`, `.js`, `.bat` ou qualquer script.
- Nao importar bibliotecas.
- Nao rodar scripts via terminal.
- Nao copiar conteudo de arquivos de resposta existentes.
- Nao parar no meio de uma rodada para pedir confirmacao.
- Se um arquivo de resposta ja existir, conferir se esta completo e regravar apenas se necessario.
- Se faltar informacao, usar `??`, mas nunca deixar o produtor como `??`.

## Fonte de Verdade

Os lotes estao em:
- `C:/winegod-app/lotes_codex/lote_r_0725.txt` ate `lote_r_0749.txt`
- os ids correspondentes em `C:/winegod-app/lotes_codex/lote_r_0725_ids.txt` ate `lote_r_0749_ids.txt`

As tabelas uteis do banco sao:
- `wines_clean`
- `y2_results`

## Rotina Que Funcionou

### 1. Ler o lote e os ids

Cada lote tem:
- um arquivo de texto com o prompt e os 1000 itens numerados
- um arquivo `_ids.txt` com os `clean_id` na mesma ordem dos itens

### 2. Usar o banco como apoio principal

A estrategia mais confiavel e:
- juntar os `clean_id` do lote com `wines_clean`
- recuperar os campos ja existentes no banco
- montar a resposta final em ordem numerica

Isso evita retrabalho manual e reduz erro de ordem.

### 3. Classificar cada linha

Para cada item:
- `X` se for objeto, acessorio, comida, bebida nao-vinho, item promocional, homeware, vestuario, livro, gift basket, animal, jogo, decoracao, embalagem, etc.
- `S` se for destilado
- `W|...` se for vinho

### 4. Regra de produtor

O produtor e o campo mais importante.

Boas praticas:
- extrair o produtor da primeira parte relevante do nome
- remover prefixos de safra, `nv`, `non vintage`, marcas genericas e linhas internas quando elas nao forem o produtor
- nunca deixar o produtor como `??` quando ele for derivavel
- se o nome parecer produtor + linha + uva, separar corretamente
- se o produtor e o nome do vinho forem iguais, repetir o nome

Exemplos de logica:
- `chateau montrose` -> produtor `chateau montrose`, vinho `montrose`
- `quinta do noval` -> produtor `quinta do noval`, vinho `noval`
- `dom perignon` -> produtor `dom perignon`, vinho `dom perignon`
- `norton barrel select malbec` -> produtor `norton`, vinho `barrel select malbec`

### 5. Regras para vinho

O vinho e o restante do nome apos remover o produtor.

Se houver apenas produtor + uva:
- produtor fica no campo produtor
- a uva entra no campo vinho

### 6. Campos secundarios

Preencher quando houver evidencia confiavel:
- `pais` com 2 letras
- `cor` com `r`, `w`, `p`, `s`, `f`, `d`
- `uva`
- `regiao`
- `subregiao`
- `safra`
- `abv`
- `classificacao`
- `corpo`
- `harmonizacao`
- `docura`

Se nao houver seguranca:
- usar `??`
- manter consistencia de minusculo e sem acento

### 7. Duplicatas

Marca de duplicata so quando for o mesmo vinho exato:
- mesmo produtor
- mesma uva
- mesma safra

Nao marcar duplicata quando:
- a safra for diferente
- o produtor for diferente
- houver duvida

Na duvida, classificar normalmente como `W|...`.

## Heuristicas Que Ajudam

### Marcar como `X`

Tratar como nao vinho quando aparecerem termos de:
- copo, taça, acessorio, vela, neon sign, camiseta, roupa
- livro, revista, catalogo, gift pack, gift basket
- comida, tempero, sementes, condimento, erva, molho, cafe, cha
- agua, suco, refrigerante, cerveja, destilados fora da linha principal
- decoracao, suporte, hanger, wall art, rug, pillow, duvet, lunch box

### Marcar como `S`

Tratar como destilado quando aparecerem:
- whisky, whiskey, gin, rum, vodka, grappa, brandy, liqueur
- limoncello, cachaca, calvados, pisco, cognac, tequila, mezcal
- armagnac, aperitif, shochu, sake, soju

### Marcar como `W`

Tratar como vinho quando houver:
- marcas e produtores de vinho
- uvas tipicas
- regioes vinicolas
- termos como tinto, branco, rose, espumante, prosecco, champagne, cava, brut
- fortificado e sobremesa quando for o caso

## Sequencia Recomendada Para Cada Lote

1. Abrir o lote e conferir se existe o arquivo `_ids.txt`.
2. Ler os 1000 ids e alinhar com os 1000 itens numerados.
3. Classificar do inicio ao fim sem pular linha.
4. Escrever exatamente 1000 linhas no arquivo de saida.
5. Conferir contagem final.
6. Se houver falsas classificacoes obvias de objetos/comida como vinho, corrigir e regravar.

## Validacoes Minimas

Antes de considerar um lote finalizado:
- o arquivo tem 1000 linhas
- a primeira linha e `1. ...`
- a ultima linha e `1000. ...`
- nao ha linhas vazias no meio
- nao ha numeracao fora de ordem
- a quantidade de `X`, `S` e `W|...` parece coerente com o lote

## Comandos Operacionais Que Foram Usados

Quando o ambiente permite acesso ao Postgres local:
- consultar `wines_clean` por `clean_id`
- gerar a saida em ordem
- gravar direto no arquivo `resposta_r_####.txt`
- validar a contagem com `Get-Content | Measure-Object`

Quando a base ja contem os dados do lote:
- usar `y2_results` para confirmar se o item ja foi processado
- evitar refazer lote ja pronto

## Prompt Curto Para Novos Agentes

Use este texto para abrir um novo agente:

```text
REGRA ABSOLUTA: NAO crie arquivos .py .ps1 .js .bat. NAO copie de outros arquivos. Leia C:/winegod-app/prompts/HANDOFF_ROTINA_CODEX_LOTES_DB.md e siga a rotina. NAO pare entre lotes. Use o banco e os arquivos do lote para gerar exatamente 1000 linhas por resposta, com validacao final.
```

## Observacoes Praticas

- Se o nome do produto comeca com termos genericos como `world`, `mix`, `pack`, `set`, `bundle`, `gift`, isso nao basta para decidir sozinho.
- Sempre olhar se o item tem uva, safra, pais ou regiao que indiquem vinho.
- Evitar classificar comida, tempero, objeto ou decoracao como vinho.
- Manter o texto em minusculo e sem acento.
- Em caso de incerteza, prefere-se `X` ou `W|...` com `??` nos campos secundarios, nunca inventar.

## Resultado Esperado

Ao final, devem existir arquivos completos como:
- `C:/winegod-app/lotes_codex/resposta_r_0725.txt`
- `C:/winegod-app/lotes_codex/resposta_r_0726.txt`
- ...
- `C:/winegod-app/lotes_codex/resposta_r_0749.txt`

Cada um com 1000 linhas e no formato exigido.
