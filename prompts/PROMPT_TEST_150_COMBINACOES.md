# GERADOR DE 150 PERGUNTAS DIFICEIS PARA TESTAR IA SOMMELIER

## O QUE E O SISTEMA

WineGod.ai e uma IA sommelier chamada "Baco" (deus grego do vinho). O usuario conversa por chat. Baco tem acesso a:

- 1.72 MILHOES de vinhos com notas de avaliadores reais (0-5 estrelas)
- 57.000 lojas em 50 paises com precos em moedas locais
- Dados: nome do vinho, produtor, safra (ano), tipo (tinto/branco/rose/espumante), pais, regiao, uva, nota, preco, loja
- Funcoes: buscar vinho, comparar vinhos, ver precos, recomendar, ler foto de rotulo (OCR)
- Score proprietario de custo-beneficio (nota / preco)

O sistema NAO tem: historico de precos, estoque em tempo real, reserva em restaurante, venda direta.

## SUA TAREFA

Gere exatamente 150 perguntas que um usuario REAL faria ao Baco. As perguntas devem ser DIFICEIS mas LEGITIMAS — coisas que o sistema TEM obrigacao de responder bem.

## OS 14 EIXOS DE VARIACAO

Cada pergunta do usuario combina 2 a 5 destes eixos. Quanto mais eixos combinados, mais dificil a pergunta.

| # | Eixo | Variacoes possiveis |
|---|---|---|
| 1 | **O que busca** | Vinho especifico, tipo (tinto/branco/rose/espumante), uva (Malbec, Cabernet, Chardonnay...), regiao (Bordeaux, Mendoza, Douro...), produtor (Catena, Antinori...), estilo (encorpado, leve, frutado, seco, doce) |
| 2 | **Filtro de preco** | "ate X", "entre X e Y", "mais barato possivel", "custo-beneficio", "nao caro", "sem limite" |
| 3 | **Filtro de nota** | "acima de 4.0", "bem avaliado", "nota minima 3.5", "melhor avaliado", "top rated" |
| 4 | **Moeda** | BRL, USD, EUR, GBP, ARS, CLP, MXN, moeda local do pais, conversao entre moedas |
| 5 | **Geografia do vinho** | Pais de origem, regiao especifica, sub-regiao, comparacao entre paises |
| 6 | **Geografia do usuario** | "estou no Brasil", "vou viajar pra X", "moro em Londres", "comprando online dos EUA" |
| 7 | **Quantidade** | "me da 1", "top 5", "lista de 10", "ranking completo", "quantos tem?" |
| 8 | **Ocasiao** | Churrasco, jantar romantico, presente, casamento, degustacao, piquenique, ano novo, formatura |
| 9 | **Harmonizacao** | Carne, peixe, queijo, massa, sushi, sobremesa, comida picante, vegetariano, vegano |
| 10 | **Comparacao** | Vinho A vs B, pais vs pais, uva vs uva, safra vs safra, regiao vs regiao |
| 11 | **Tempo** | Safra especifica, vinho pra guardar, beber agora, envelhecimento, "quando abrir?" |
| 12 | **Contexto** | Supermercado, restaurante (carta), loja online, viagem/vinicola, duty free, importadora |
| 13 | **Nivel do usuario** | Iniciante total, entusiasta, expert/sommelier, profissional (dono de restaurante) |
| 14 | **Acao pedida** | Buscar, comparar, recomendar, explicar, calcular, contar/estatistica, validar escolha |

## REGRAS PARA GERAR AS PERGUNTAS

### Distribuicao obrigatoria:
- **30 perguntas faceis** (2 eixos combinados) — ex: "me recomenda um tinto ate 50 reais"
- **50 perguntas medias** (3 eixos) — ex: "top 5 Malbec argentinos ate R$100 com nota acima de 4"
- **50 perguntas dificeis** (4 eixos) — ex: "vou pra Colombia, quero vinhos locais bons e baratos, nota minima 3.5, me da preco em reais"
- **20 perguntas muito dificeis** (5+ eixos) — ex: "vou visitar vinicolas em Mendoza semana que vem, quero saber quais tem os vinhos com melhor custo-beneficio, nota acima de 4, e que eu consiga comprar no Brasil depois por menos de R$150"

### O que torna uma pergunta DIFICIL:
- Combinar preco + moeda + geografia diferente (usuario no Brasil quer preco de vinho na Colombia)
- Pedir estatisticas filtradas ("quantos vinhos italianos acima de 4.5 existem por menos de EUR 20?")
- Comparacoes complexas ("top 3 Cabernet de cada continente por custo-beneficio")
- Contexto de viagem ("estou no duty free de Lisboa, tenho EUR 30, qual vinho portugues levo?")
- Pedidos com restricoes multiplas ("branco seco, organico, nota >4.0, ate R$60, que harmonize com sushi")
- Perguntas sobre vinicolas pra visitar com criterios de preco/nota
- Conversao de moeda implicita ("esse vinho custa $15 nos EUA, quanto sairia no Brasil?")
- Listas com criterios compostos ("5 vinhos de paises diferentes, todos acima de 4.0, todos abaixo de US$20")

### O que NAO gerar:
- Perguntas sobre cerveja, destilados, comida sem relacao com vinho
- Perguntas sobre a vida pessoal do Baco ou mitologia (isso ja foi testado)
- Perguntas genericas demais ("me recomenda um vinho" sem nenhum filtro)
- Perguntas identicas com palavras diferentes
- Perguntas que o sistema claramente nao consegue responder (ex: "compra pra mim", "reserva mesa")

### Linguagem:
- 70% em portugues BR (informal, como WhatsApp)
- 15% em ingles
- 10% em espanhol
- 5% em portugues formal

### Exemplos de perguntas BEM feitas (pra voce entender o nivel):

**Facil (2 eixos):**
1. "Qual espumante ate R$60 voce recomenda?" [preco + tipo]
2. "Malbec ou Cabernet pra churrasco?" [comparacao + harmonizacao]

**Media (3 eixos):**
3. "Top 5 vinhos portugueses com nota acima de 4.0 ate EUR 15" [geografia + nota + preco]
4. "Estou no supermercado, tem um Casillero del Diablo por R$35, vale a pena?" [contexto + vinho especifico + validacao]

**Dificil (4 eixos):**
5. "Vou pra Argentina, quero visitar vinicolas em Mendoza com vinhos nota 4+ que custem menos de US$10 la" [viagem + vinicola + nota + preco + moeda]
6. "Me da 3 tintos e 2 brancos, todos de paises diferentes, nota minima 3.8, nenhum acima de R$80" [quantidade + tipo + geografia + nota + preco]

**Muito dificil (5+ eixos):**
7. "Meu sogro coleciona Bordeaux mas eu quero surpreender com algo de outro pais que tenha mesmo nivel, ate R$300, safra 2015-2018, pra guardar mais 5 anos, e que eu ache pra comprar no Brasil" [presente + comparacao + preco + safra + guarda + geografia loja]
8. "Quantos vinhos no seu banco tem nota acima de 4.5, custam menos de EUR 20, sao italianos, e sao tintos? Me lista os top 10 por custo-beneficio" [estatistica + nota + preco + moeda + geografia + tipo + ranking + score]

## FORMATO DE SAIDA

Gere as 150 perguntas neste formato:

```
### FACEIS (30)
1. [pergunta aqui]
2. [pergunta aqui]
...

### MEDIAS (50)
31. [pergunta aqui]
32. [pergunta aqui]
...

### DIFICEIS (50)
81. [pergunta aqui]
82. [pergunta aqui]
...

### MUITO DIFICEIS (20)
131. [pergunta aqui]
132. [pergunta aqui]
...
```

Cada pergunta deve ser unica, realista, e testar uma combinacao diferente de eixos. O objetivo e encontrar os LIMITES do sistema — onde ele falha, onde confunde moeda, onde nao filtra direito, onde inventa dados.

COMECE AGORA. Gere as 150 perguntas.
