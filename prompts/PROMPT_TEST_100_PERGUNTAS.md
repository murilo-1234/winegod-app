INSTRUCAO: Gere exatamente 100 perguntas que usuarios reais fariam a uma IA sommelier de vinhos. As perguntas devem ser REALISTAS — como se fossem digitadas por pessoas comuns no Google, em foruns de vinho, ou em apps como Vivino.

# CONTEXTO

Voce esta gerando perguntas de teste para o WineGod.ai, uma IA sommelier global chamada "Baco". O sistema tem:
- 1.72M vinhos com notas, precos e lojas
- Busca por nome, produtor, regiao, uva, tipo
- Comparacao entre vinhos
- Recomendacao por filtros (tipo, pais, preco, nota)
- OCR de fotos de rotulos
- Estatisticas (quantos vinhos, vinicolas, medias, rankings)
- Precos em lojas de 50 paises

# DISTRIBUA AS 100 PERGUNTAS ASSIM:

## BLOCO A — Por Persona (25 perguntas)
Gere perguntas como se fossem feitas por estas 7 personas:

1. **Iniciante total** (4 perguntas) — nunca entendeu vinho, tem vergonha de perguntar
   Ex: "qual a diferenca entre vinho seco e suave?", "tinto vai na geladeira?"

2. **Entusiasta casual** (4 perguntas) — bebe vinho nos fins de semana, quer aprender mais
   Ex: "malbec argentino bom ate 80 reais?", "por que Pinot Noir e mais caro?"

3. **Colecionador/expert** (4 perguntas) — conhece bastante, quer dados precisos
   Ex: "comparar safras 2015 vs 2018 de Barolo", "qual a nota do Opus One 2019?"

4. **Presenteador** (3 perguntas) — comprando pra outra pessoa
   Ex: "vinho pra dar de presente de aniversario ate 200 reais", "garrafa elegante pra sogra"

5. **Restaurante/sommelier** (3 perguntas) — profissional buscando opcoes
   Ex: "tintos italianos pra carta de 80-150 reais", "espumante brasileiro bom pra evento"

6. **Viajante** (3 perguntas) — planejando viagem ou voltou de uma
   Ex: "trouxe um vinho da Toscana chamado X, e bom?", "o que beber em Mendoza?"

7. **Curioso/random** (4 perguntas) — pergunta aleatoria, as vezes nem sobre vinho
   Ex: "qual o vinho mais caro do mundo?", "vinho faz bem pra saude?", "baco existiu mesmo?"

## BLOCO B — Por Cenario Real (25 perguntas)
Gere perguntas que surgem em situacoes reais:

1. **No supermercado** (5) — olhando prateleira, precisa decidir rapido
2. **No restaurante** (5) — com o cardapio na mao, quer acertar
3. **Churrasco/jantar em casa** (5) — qual vinho pra acompanhar
4. **Comprando online** (5) — comparando opcoes em loja virtual
5. **Viu nas redes sociais** (5) — alguem postou, quer saber mais

## BLOCO C — Por Intencao de Busca (25 perguntas)
Gere perguntas baseadas em como as pessoas buscam no Google:

1. **Melhor X ate Y reais** (5) — buscas de custo-beneficio
2. **X vs Y** (5) — comparacoes diretas entre vinhos, uvas, regioes
3. **Vinho pra Z** (5) — harmonizacao com comida ou ocasiao
4. **O que e/significa X** (5) — duvidas sobre termos, uvas, regioes
5. **Ranking/lista** (5) — top 10, melhores de, etc.

## BLOCO D — Por Dados Reais de Foruns (25 perguntas)
Gere perguntas como as que aparecem em:

1. **Reddit r/wine** (5) — discussoes entre entusiastas
2. **Vivino comments** (5) — duvidas de quem usa app de vinho
3. **Google "People Also Ask"** (5) — perguntas frequentes sobre vinho
4. **Wine forums** (5) — CellarTracker, WineBerserkers, etc.
5. **WhatsApp/amigos** (5) — perguntas informais que as pessoas mandam

# REGRAS

1. As perguntas devem ser em **portugues** (foco mercado BR inicialmente)
2. Variar entre perguntas **curtas** ("malbec bom e barato?") e **longas** ("estou procurando um vinho tinto encorpado pra harmonizar com costela no bafo, orcamento de 60 a 100 reais, o que recomenda?")
3. Incluir pelo menos 10 perguntas que mencionem **vinhos especificos** pelo nome (ex: "o que acha do Casillero del Diablo?")
4. Incluir pelo menos 5 perguntas sobre **fotos** (ex: "tirei foto desse rotulo, que vinho e?")
5. Incluir pelo menos 5 perguntas que testem **limites** (ex: pergunta fora do tema, pergunta sem resposta possivel)
6. Incluir pelo menos 5 perguntas sobre **estatisticas** (ex: "quantos vinhos argentinos tem?", "qual pais tem mais vinicolas?")
7. As perguntas devem parecer **digitadas por humanos** — com erros de digitacao ocasionais, gírias, abreviacoes
8. NAO repetir perguntas. Cada uma deve ser unica.
9. Numerar de 1 a 100

# FORMATO DE SAIDA

Retorne APENAS as 100 perguntas numeradas, sem explicacao, sem categorias, sem comentarios. Apenas:

1. pergunta aqui
2. pergunta aqui
...
100. pergunta aqui
