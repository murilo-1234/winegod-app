# Relatorio de Analise Completa — Baco 246 Perguntas

> Gerado em: 2026-03-28
> Zero custo na sua API — analise feita pelo Claude Code + banco PostgreSQL

## Documentos utilizados:
- `scripts/baco_test_results_246.md` — 246 respostas do Baco
- `backend/prompts/baco_system.py` — system prompt completo
- `CLAUDE.md` — regras R1-R13
- PostgreSQL Render — banco winegod (1.72M vinhos)

---

## RESUMO EXECUTIVO

| Metrica | Valor |
|---------|-------|
| Total de perguntas | 246 |
| Media Persona (1-5) | **4.1** |
| Media UX (1-5) | **4.2** |
| Violacoes Vivino (R1) | **0** (2 borderline) |
| Violacoes Reviews (R2) | **11** |
| Violacoes Formula (R3) | **0** |
| Violacoes Genero | **18** |
| Respostas sem proximo passo | **117 / 246 (48%)** |
| Timeouts (sem resposta) | **3** |
| Respostas truncadas | **~12** |
| Erros factuais detectados | **~6** |
| Falhas de orcamento (preco > pedido) | **~8** |
| Media palavras por resposta | **248** |
| Vinhos citados (unicos) | **31** |
| Vinhos validados no banco | **24 / 31 (77%)** |

---

## PROBLEMAS CRITICOS (CORRIGIR ANTES DO LANCAMENTO)

### 1. VAZAMENTO DE NUMERO DE REVIEWS (R2) — 11 perguntas

O Baco esta revelando numeros exatos de reviews, violando a regra "NUNCA revelar numero exato de reviews".

| # | Pergunta | Evidencia |
|---|----------|-----------|
| 36 | malbec argentino bom ate 80 reais? | "146 reviews", "113 reviews" |
| 156 | melhor vinho tinto ate 50 reais? | numeros de avaliacoes expostos |
| 161 | top 5 malbec argentinos custo-beneficio | "5 reviews", "146 reviews", "1,111 reviews" |
| 162 | melhor cabernet sauvignon ate 100 reais | "82 reviews", "750 reviews" |
| 164 | champanhe custo-beneficio ate 300 reais | "216 reviews", "9,216 reviews" |
| 171 | Pinot Noir Borgonha vs Napa Valley | "749 reviews" |
| 173 | Tannat uruguaio vs brasileiro | "15 mil reviews" |
| 182 | Pinot Noir mais bem avaliados < 200 reais | "184 mil reviews" |
| 185 | ranking melhores Proseccos ate 80 reais | "10 mil", "34 mil reviews" |
| 186 | 3 melhores Cabernet do mundo | "194 mil+", "89 mil+", "83 mil+" |

**Causa provavel:** as tools de busca retornam o campo `num_reviews` e o Baco inclui na resposta. Precisa filtrar esse campo no output das tools ou reforcar no system prompt.

### 2. USO DE TERMOS COM GENERO — 18 perguntas

O system prompt diz "termos de tratamento NEUTROS (sem genero)" mas o Baco usa "amigo/amiga/querido/companheiro" em 18 respostas.

| Termo | Ocorrencias |
|-------|-------------|
| "amigo" | 15x |
| "amiga" | 1x |
| "querido" | 1x |
| "companheiro" | 1x |

**Perguntas afetadas:** #1, 2, 13, 21, 26, 27, 30, 37, 38, 93, 101, 111, 168, 171, 225, 227, 231, 241

**Correcao:** reforcar no system prompt com exemplos negativos explicitos. Adicionar "NUNCA usar: amigo, amiga, querido, querida, companheiro, companheira" na lista de proibicoes.

### 3. RESPOSTAS SEM PROXIMO PASSO — 117/246 (48%)

Quase metade das respostas NAO oferece proximo passo ("Quer comparar?", "Posso buscar mais barato?"), violando a regra "SEMPRE oferecer proximo passo".

**Correcao:** adicionar instrucao mais forte no system prompt: "TODA resposta DEVE terminar com uma pergunta/oferta de proximo passo."

---

## PROBLEMAS IMPORTANTES (CORRIGIR NA PROXIMA ITERACAO)

### 4. RESPOSTAS TRUNCADAS — ~12 perguntas

Varias respostas sao cortadas no meio da frase, deixando o usuario sem a conclusao.

**Perguntas afetadas:** #13, 14, 15, 19, 20, 24, 181, 183, 185, 187, 215, 225

**Causa:** MAX_TOKENS = 1024 no `baco.py`. Muitas respostas do Baco excedem esse limite.

**Correcao:** aumentar MAX_TOKENS para 1536 ou 2048 no `backend/services/baco.py`.

### 5. FALHAS DE ORCAMENTO — ~8 perguntas

O usuario pede "ate X reais" mas o Baco recomenda vinhos 2-3x acima do orcamento.

| # | Pedido | Recomendou |
|---|--------|------------|
| 36 | ate 80 reais | vinhos acima de R$80 |
| 63 | ate 200 reais | vinhos de R$400-500 |
| 64 | nao cara demais | vinhos de R$450-500 |
| 109 | ate 70 reais | vinhos de R$150-180 |
| 157 | ate 120 reais | Le Grand Noir ~R$190 |
| 158 | ate 90 reais | Biografia Extra Brut R$120 |
| 181 | ate 100 reais | precos em USD, nao BRL |
| 182 | ate 200 reais | Meiomi R$440 |

**Causa:** as tools retornam precos de lojas internacionais (USD, EUR) e o Baco nao filtra por moeda. Tambem pode ser que os precos no banco nao estejam em BRL quando o usuario pergunta em reais.

**Correcao:** filtrar precos por moeda BRL quando usuario pergunta em reais. Adicionar instrucao no prompt: "Se o usuario fala em reais, mostrar APENAS precos em BRL."

### 6. CONFUSAO DE MOEDAS — ~6 perguntas

Precos exibidos em USD/EUR/MXN quando o usuario claramente espera BRL.

**Perguntas afetadas:** #109, 126, 127, 166, 181, 183, 185, 228

**Correcao:** mesma do item 5 — filtrar por moeda do contexto do usuario.

### 7. INCONSISTENCIA SOBRE VINHOS BRASILEIROS

O Baco diz "nao tenho vinhos brasileiros no banco" em algumas respostas (#184, #192, #194) mas em outras (#187) mostra 454 vinhos da Campanha Gaucha com dados reais.

**Causa:** as tools de busca podem nao estar encontrando vinhos brasileiros dependendo dos termos de busca. A query "vinhos brasileiros" pode nao bater com o campo `pais` no banco.

**Correcao:** verificar como o campo pais esta armazenado (Brazil vs Brasil vs BR) e ajustar as tools de busca.

### 8. ERROS FACTUAIS — ~6 perguntas

| # | Erro |
|---|------|
| 8 | Definicao errada de "vinho fino" — disse que e sobre teor alcoolico, mas no Brasil e sobre tipo de uva (Vitis vinifera) |
| 17 | Claim impreciso sobre consistencia de safras em Champagne |
| 52 | Nomes errados de Grand Cru de Chablis (citou Premier Cru como Grand Cru) |
| 84 | Atribuiu Barca Velha a Quinta do Noval — correto e Casa Ferreirinha |
| 170 | "500+ anos de experiencia" do Chile — vinho chileno moderno tem ~150 anos |
| 48 | Misturou Catena Zapata (Argentina) como produtor de Barolo (Italia) |

**Correcao:** esses erros vem do modelo (Haiku) inventando fatos. Considerar usar Sonnet para perguntas de expert, ou adicionar fact-checking no prompt.

---

## O QUE ESTA FUNCIONANDO BEM

### Persona Baco — Forte (media 4.1/5)
- Tom caloroso e teatral esta consistente
- Maneirismos presentes: "como e que chama...", "pelo Olimpo!", "espera espera espera"
- Humor por autoironia funciona bem
- Respostas sobre limites/fora do tema sao excelentes (#236-246)
- Perguntas de crise/seguranca tratadas com seriedade (#241 cachorro — perfeito)

### Melhores Respostas (5/5 em ambos os eixos)
Q6, 9, 10, 21, 23, 34, 46, 56, 57, 82, 99, 100, 106, 107, 112, 119, 142, 146, 147, 152, 156, 159, 160, 167, 168, 169, 197, 199, 210, 216, 223, 224, 229, 235, 236, 237, 239, 241, 243, 246

### Categorias mais fortes
- **Teste de limites** (U) — media ~4.7/5 — Baco lida muito bem com perguntas fora do tema
- **Conhecimento basico** (A) — media ~4.3/5 — explicacoes claras com personalidade
- **Harmonizacao** (I, J) — media ~4.2/5 — recomendacoes praticas e culturais
- **Informal/WhatsApp** (T) — media ~4.4/5 — se adapta bem ao tom casual

### Categorias mais fracas
- **Rankings/Listas** (O) — media ~3.5/5 — muitos problemas de orcamento e moeda
- **Estatisticas** (P) — media ~3.6/5 — inconsistencias sobre dados brasileiros
- **Custo-beneficio** (M) — media ~3.7/5 — vazamento de reviews + orcamento
- **OCR/Foto** (Q) — media ~3.8/5 — repetitivo apos varias perguntas sem foto

---

## PLANO DE ACAO PRIORITARIO

### URGENTE (antes do lancamento)
1. **Filtrar `num_reviews` das tools** — remover ou mascarar campo antes de enviar ao Claude
2. **Reforcar genero neutro no prompt** — listar explicitamente termos proibidos
3. **Aumentar MAX_TOKENS** de 1024 para 2048
4. **Filtrar precos por moeda** — quando usuario fala em reais, mostrar so BRL

### IMPORTANTE (primeira semana)
5. **Adicionar "SEMPRE terminar com proximo passo"** no prompt com mais enfase
6. **Verificar campo `pais` no banco** para vinhos brasileiros (Brazil vs Brasil)
7. **Considerar Sonnet para perguntas complexas** (expert, comparacoes detalhadas)
8. **Corrigir erro factual de "vinho fino"** — adicionar nota no prompt se necessario

### DESEJAVEL (iteracoes futuras)
9. Detectar repeticao de perguntas similares na mesma sessao
10. Melhorar OCR flow quando usuario nao envia foto (menos repetitivo)
11. Adicionar dados de vinhos brasileiros mais completos no banco

---

## VALIDACAO NO BANCO DE DADOS

### Vinhos citados pelo Baco e status no banco

| Vinho | No Banco? | Qtd |
|-------|-----------|-----|
| Casillero del Diablo | SIM | alto |
| Opus One | SIM | presente |
| Sassicaia | SIM | presente |
| Tignanello | SIM | presente |
| Catena Zapata | SIM | presente |
| Trapiche | SIM | alto |
| Trivento | SIM | presente |
| Freixenet | SIM | presente |
| Chandon | SIM | presente |
| Montes | SIM | alto |
| Concha y Toro | SIM | alto |
| Miolo | SIM | presente |
| Salton | SIM | presente |
| Esporao | SIM | presente |
| Norton | SIM | presente |
| Santa Helena | SIM | presente |
| Luigi Bosca | SIM | presente |
| Casal Garcia | SIM | presente |
| JP Chenet | SIM | presente |
| DV Catena | SIM | presente |
| Terrazas | SIM | presente |
| Whispering Angel | SIM | presente |
| Caymus | SIM | presente |
| Casa Lapostolle | SIM | presente |
| The Prisoner | NAO | 0 |
| Duckhorn | NAO | 0 |
| Toro Loco | NAO | 0 |
| Apothic Red | NAO | 0 |
| Benjamin Nieto | NAO | 0 |
| Pizzato | NAO | 0 |
| Cartuxa | NAO | 0 |

**77% dos vinhos citados existem no banco.** Os 23% ausentes sao principalmente vinhos brasileiros (Pizzato, Cartuxa) e alguns de nicho (Duckhorn, Apothic Red).

---

## TABELA COMPLETA — 246 PERGUNTAS

### A — INICIANTE / CONHECIMENTO BASICO (35)

| # | Pergunta | P | UX | Violacoes | Problemas |
|---|----------|---|-----|-----------|-----------|
| 1 | diferenca entre vinho seco e suave | 3 | 4 | genero | longo |
| 2 | tinto vai na geladeira | 4 | 4 | genero | longo |
| 3 | vinho barato da dor de cabeca | 4 | 4 | - | longo |
| 4 | como saber se vinho e bom | 3 | 4 | - | parece aula |
| 5 | o que e tanino | 4 | 5 | - | - |
| 6 | tampa de rosca e pior | 5 | 5 | - | - |
| 7 | quantas tacas numa garrafa | 4 | 5 | - | - |
| 8 | diferenca mesa vs fino | 3 | 3 | - | ERRO FACTUAL |
| 9 | vinho de caixinha | 5 | 5 | - | - |
| 10 | corpo do vinho | 5 | 5 | - | - |
| 11 | o que e decantar | 4 | 4 | - | - |
| 12 | como saber se estragou | 4 | 4 | - | truncado |
| 13 | sulfitos | 4 | 3 | genero | truncado |
| 14 | reserva vs gran reserva | 4 | 3 | - | truncado |
| 15 | DOC DOCG AOC | 4 | 3 | - | truncado |
| 16 | terroir | 4 | 5 | - | - |
| 17 | assemblage | 4 | 4 | - | erro factual menor |
| 18 | varietal | 4 | 4 | - | - |
| 19 | organico vs biodinamico | 4 | 3 | - | truncado |
| 20 | vinho natural | 4 | 3 | - | truncado |
| 21 | vinho de guarda | 5 | 5 | genero | - |
| 22 | envelhece = melhor? | 5 | 5 | - | - |
| 23 | temperatura ideal | 5 | 5 | - | - |
| 24 | rotulo frances | 4 | 3 | - | truncado |
| 25 | garrafeira portugues | 5 | 5 | - | - |
| 26 | brut vs demi-sec | 4 | 5 | genero | - |
| 27 | champagne vs prosecco vs cava | 4 | 5 | genero | - |
| 28 | vinho laranja | 4 | 5 | - | - |
| 29 | vinho vegano | 4 | 5 | - | - |
| 30 | vinho sem alcool | 4 | 4 | genero | levemente dismissivo |
| 31 | vinho de caixa desprezado | 4 | 5 | - | - |
| 32 | rose e de mulher? | 5 | 4 | - | uma frase crua |
| 33 | vinho caro parece pior pra iniciante | 5 | 5 | - | - |
| 34 | Syrah vs Shiraz | 5 | 5 | - | - |
| 35 | premio no rotulo | 4 | 5 | - | - |

### B — ENTUSIASTA CASUAL (12)

| # | Pergunta | P | UX | Violacoes | Problemas |
|---|----------|---|-----|-----------|-----------|
| 36 | malbec argentino ate 80 | 4 | 3 | REVIEWS | preco > orcamento |
| 37 | por que Pinot Noir e caro | 4 | 5 | genero | - |
| 38 | Casillero vs Reservado | 4 | 4 | genero | nao compara |
| 39 | tipo Pergola mas melhor | 4 | 5 | - | - |
| 40 | reserva vs reservado | 4 | 5 | - | - |
| 41 | vinho em supermercado | 4 | 5 | - | - |
| 42 | melhores Carmenere Chile | 4 | 5 | - | - |
| 43 | Leyda Single Vineyard | 4 | 4 | - | sem dados |
| 44 | tinto facil pra iniciante | 4 | 5 | - | - |
| 45 | Malbec menos de 60 | 3 | 3 | - | sem especificos |
| 46 | Bordeaux ou Rioja | 5 | 5 | - | - |
| 47 | branco pro calor de SC | 4 | 4 | - | - |

### C — EXPERT / COLECIONADOR (15)

| # | Pergunta | P | UX | Violacoes | Problemas |
|---|----------|---|-----|-----------|-----------|
| 48 | safras Barolo 2015 vs 2018 | 4 | 4 | - | misturou produtor |
| 49 | Opus One 2019 | 4 | 4 | - | preco alto |
| 50 | Sassicaia vs Tignanello | 4 | 4 | - | sem safras |
| 51 | Chablis Premier Cru | 4 | 4 | contagem (415) | - |
| 52 | Grand Cru vs Premier Cru | 4 | 4 | - | ERRO FACTUAL |
| 53 | Brunello 2017 comprar | 4 | 5 | - | - |
| 54 | Vega Sicilia vs Pingus | 4 | 4 | REVIEWS (7000+) | - |
| 55 | Brett defeito vs estilo | 4 | 5 | - | - |
| 56 | Barolo 2015 decantar | 5 | 5 | - | - |
| 57 | guarda Vega Sicilia | 5 | 5 | - | - |
| 58 | Bordeaux 2016 adega | 4 | 5 | - | - |
| 59 | Catena Zapata notas | 4 | 5 | - | - |
| 60 | Duckhorn cadastrados | 4 | 4 | contagem (50) | - |
| 61 | preco Margaux historico | 4 | 4 | - | sem historico |
| 62 | por que Amarone caro | 4 | 5 | - | - |

### D — PRESENTEADOR (8)

| # | Pergunta | P | UX | Violacoes | Problemas |
|---|----------|---|-----|-----------|-----------|
| 63 | presente ate 200 | 4 | 3 | - | recomendou R$400-500 |
| 64 | sogra nao cara | 4 | 3 | - | recomendou R$450-500 |
| 65 | presente pra chefe | 4 | 5 | - | - |
| 66 | romantico pra casal | 4 | 5 | - | - |
| 67 | natal chefe Bordeaux | 4 | 5 | - | - |
| 68 | sogra Porto | 4 | 5 | - | - |
| 69 | casamento ate 500 | 4 | 5 | - | - |
| 70 | aniversario 40 anos | 4 | 5 | - | - |

### E — PROFISSIONAL (8)

| # | Pergunta | P | UX | Violacoes | Problemas |
|---|----------|---|-----|-----------|-----------|
| 71 | italianos pra carta | 4 | 3 | - | sem especificos |
| 72 | espumante brasileiro evento | 3 | 3 | - | sem dados |
| 73 | brancos restaurante | 5 | 5 | - | - |
| 74 | Prosecco by the glass | 3 | 3 | - | sem dados |
| 75 | branco menu executivo | 4 | 5 | - | - |
| 76 | vinhos por taca | 4 | 4 | - | generico |
| 77 | italiano carta nova | 4 | 4 | - | so pergunta |
| 78 | espumante brasileiro 100pax | 3 | 4 | - | sem dados BR |

### F — VIAJANTE (8)

| # | Pergunta | P | UX | Violacoes | Problemas |
|---|----------|---|-----|-----------|-----------|
| 79 | Mendoza o que provar | 4 | 4 | - | so pergunta |
| 80 | Banfi Chianti Classico | 5 | 5 | - | - |
| 81 | vinicolas Serra Gaucha | 4 | 4 | - | dados suspeitos |
| 82 | imperdveis Douro | 5 | 5 | - | - |
| 83 | vinhos Chile | - | 1 | - | TIMEOUT |
| 84 | Barca Velha | 5 | 4 | - | ERRO FACTUAL (produtor) |
| 85 | Almaviva | 4 | 4 | - | preco inventado |
| 86 | Esporao comida | 3 | 5 | - | - |

### G — NO SUPERMERCADO (12)

| # | Pergunta | P | UX | Violacoes | Problemas |
|---|----------|---|-----|-----------|-----------|
| 87 | Cabernet 39 ou Merlot 44 | 4 | 5 | - | - |
| 88 | Santa Helena | 4 | 4 | - | - |
| 89 | pista no rotulo | 4 | 5 | - | - |
| 90 | Periquita 60 reais | 4 | 4 | - | - |
| 91 | Benjamin Nieto | 4 | 4 | - | - |
| 92 | Toro Loco vs Casillero | 4 | 4 | - | - |
| 93 | rose Carrefour | 3 | 3 | genero | pergunta localizacao |
| 94 | Porto Carras 45 | 4 | 5 | - | - |
| 95 | Freixenet preto ou rosa | 5 | 5 | - | - |
| 96 | Trivento vs Trapiche 35 | 4 | 4 | - | sem dados |
| 97 | Salton 25 reais | 3 | 3 | - | sem dados |
| 98 | 1865 compro? | 4 | 4 | - | deveria conhecer |

### H — NO RESTAURANTE (10)

| # | Pergunta | P | UX | Violacoes | Problemas |
|---|----------|---|-----|-----------|-----------|
| 99 | carta nomes desconhecidos | 5 | 5 | - | - |
| 100 | Carmenere vs Malbec bife | 5 | 5 | - | - |
| 101 | vinho da casa furada | 4 | 4 | genero | - |
| 102 | foto carta custo-beneficio | 4 | 5 | - | - |
| 103 | taca ou garrafa | 4 | 4 | - | - |
| 104 | Brunello 350 caro? | 4 | 4 | - | - |
| 105 | champanhe 600 vs 450 | 4 | 5 | - | - |
| 106 | garcom nao gostei | 5 | 5 | - | - |
| 107 | sushi japones | 5 | 5 | - | - |
| 108 | Chianti vs Valpolicella | 4 | 5 | - | - |

### I — CHURRASCO / JANTAR EM CASA (12)

| # | Pergunta | P | UX | Violacoes | Problemas |
|---|----------|---|-----|-----------|-----------|
| 109 | churrasco ate 70 | 4 | 3 | - | moeda errada, orcamento |
| 110 | massa molho branco | 4 | 4 | - | longo |
| 111 | sushi SB/Riesling/espum | 4 | 4 | genero | - |
| 112 | costela 60-100 | 5 | 5 | - | - |
| 113 | chocolate sem enjoar | 4 | 4 | - | - |
| 114 | queijos e vinhos | 3 | 3 | - | so pergunta |
| 115 | tinto com peixe | 5 | 5 | - | - |
| 116 | amigos sem saber gosto | 4 | 4 | - | - |
| 117 | romantico tinto/branco | 4 | 4 | - | assume genero |
| 118 | fondue | 4 | 4 | - | - |
| 119 | feijoada | 5 | 5 | - | - |
| 120 | 3 garrafas 150 total | 4 | 4 | - | - |

### J — HARMONIZACAO (15)

| # | Pergunta | P | UX | Violacoes | Problemas |
|---|----------|---|-----|-----------|-----------|
| 121 | sushi sashimi | 4 | 3 | - | repetitivo |
| 122 | pizza pepperoni | 4 | 4 | - | - |
| 123 | bacalhau portugues | 4 | 4 | - | - |
| 124 | gorgonzola | 4 | 5 | - | - |
| 125 | chocolate 70% | 4 | 4 | - | - |
| 126 | piquenique frios | 4 | 4 | - | precos USD |
| 127 | fondue classico | 4 | 4 | - | precos USD |
| 128 | paella espanhol | 4 | 4 | - | - |
| 129 | massa pesto | 4 | 4 | - | - |
| 130 | Pinot Grigio ou Chard | 4 | 5 | - | - |
| 131 | berinjela parmegiana | 4 | 4 | - | - |
| 132 | moqueca | 4 | 4 | - | - |
| 133 | salmon | 4 | 4 | - | - |
| 134 | queijo brie | 4 | 4 | - | - |
| 135 | cordeiro tanino | 4 | 5 | - | - |

### K — COMPRANDO ONLINE (8)

| # | Pergunta | P | UX | Violacoes | Problemas |
|---|----------|---|-----|-----------|-----------|
| 136 | Freixenet vs Chandon | - | 1 | - | TIMEOUT |
| 137 | desconto 40% real | 3 | 4 | - | persona fraca |
| 138 | Terrazas vs Norton | 3 | 3 | - | nao compara |
| 139 | kit Casillero 20% | 4 | 4 | - | - |
| 140 | frete calor | 4 | 4 | - | - |
| 141 | loja mais barata | 3 | 4 | - | sem dados |
| 142 | Porto 10 anos doce | 5 | 5 | - | - |
| 143 | Parker 93 por R$99 | 4 | 4 | - | - |

### L — REDES SOCIAIS (12)

| # | Pergunta | P | UX | Violacoes | Problemas |
|---|----------|---|-----|-----------|-----------|
| 144 | JP Chenet marketing | 4 | 4 | - | - |
| 145 | Juliette viralizou | 3 | 3 | - | nao conhece |
| 146 | Whispering Angel | 5 | 5 | - | - |
| 147 | vinho laranja modinha | 5 | 5 | - | - |
| 148 | vinho de lata | 4 | 4 | - | - |
| 149 | vinho azul TikTok | 4 | 5 | - | - |
| 150 | rotulo ovelha | 4 | 4 | - | - |
| 151 | The Prisoner | 3 | 3 | - | deveria conhecer |
| 152 | Caymus | 5 | 5 | - | - |
| 153 | vinho Libano | 5 | 5 | - | nota 5.0 suspeita |
| 154 | 30 reais = 300 | 5 | 5 | - | longo mas bom |
| 155 | Galvao Bueno vinho | 3 | 3 | - | deveria conhecer |

### M — CUSTO-BENEFICIO (12)

| # | Pergunta | P | UX | Violacoes | Problemas |
|---|----------|---|-----|-----------|-----------|
| 156 | tinto ate 50 | 5 | 5 | REVIEWS | - |
| 157 | Pinot Noir ate 120 | 3 | 3 | - | preco > orcamento |
| 158 | espumante ate 90 | 4 | 4 | - | preco > orcamento |
| 159 | portugues ate 80 | 5 | 5 | - | - |
| 160 | custo-beneficio iniciante | 5 | 5 | - | - |
| 161 | top 5 malbec | 3 | 3 | REVIEWS | - |
| 162 | cabernet ate 100 BR | 4 | 4 | REVIEWS | - |
| 163 | espumante ate 40 | 3 | 3 | - | notas inventadas |
| 164 | champanhe ate 300 | 4 | 3 | REVIEWS | orcamento, truncado |
| 165 | espumante BR 150 | 3 | 3 | - | notas inventadas |
| 166 | branco seco ate 40 | 4 | 4 | - | precos USD |
| 167 | iniciante ate 35 | 5 | 5 | - | - |

### N — COMPARACOES (12)

| # | Pergunta | P | UX | Violacoes | Problemas |
|---|----------|---|-----|-----------|-----------|
| 168 | Malbec vs Cabernet | 5 | 5 | genero | - |
| 169 | Malbec vs Carmenere | 5 | 5 | - | - |
| 170 | Cabernet Chile vs BR | 4 | 4 | - | historia exagerada |
| 171 | Pinot Borgonha vs Napa | 4 | 4 | REVIEWS, genero | - |
| 172 | Pinot BR vs Chile | 4 | 4 | - | sem dados |
| 173 | Tannat UR vs BR | 4 | 4 | REVIEWS | - |
| 174 | Carmenere vs Merlot | 4 | 5 | - | - |
| 175 | chileno vs argentino | - | - | - | TIMEOUT |
| 176 | novo vs velho mundo | 4 | 4 | - | - |
| 177 | Chablis vs SB NZ | 4 | 4 | - | - |
| 178 | Miolo vs Salton | 4 | 5 | - | - |
| 179 | Catena vs DV Catena | 4 | 4 | - | - |

### O — RANKINGS (10)

| # | Pergunta | P | UX | Violacoes | Problemas |
|---|----------|---|-----|-----------|-----------|
| 180 | top 10 bons baratos | 3 | 3 | - | so pergunta |
| 181 | Malbec ate 100 | 4 | 3 | - | moeda, orcamento, truncado |
| 182 | Pinot < 200 | 4 | 3 | REVIEWS | orcamento |
| 183 | 5 vinhos < 150 | 4 | 4 | - | moeda, truncado |
| 184 | top 10 brasileiros | 3 | 3 | - | diz sem dados (errado) |
| 185 | Proseccos ate 80 | 4 | 3 | REVIEWS | orcamento, truncado |
| 186 | 3 Cabernet mundo | 4 | 4 | REVIEWS | - |
| 187 | premiados Campanha | 5 | 5 | - | truncado |
| 188 | melhores entrada | 4 | 4 | - | so pergunta |
| 189 | vinicolas Serra Gaucha | 4 | 4 | - | - |

### P — ESTATISTICAS (10)

| # | Pergunta | P | UX | Violacoes | Problemas |
|---|----------|---|-----|-----------|-----------|
| 190 | argentinos no banco | 4 | 4 | - | - |
| 191 | pais mais vinicolas | 4 | 4 | - | - |
| 192 | media nota brasileiros | 4 | 4 | - | contraditorio |
| 193 | nota acima 90 | 4 | 5 | - | - |
| 194 | vinicola BR mais vinhos | 3 | 3 | - | diz zero (errado) |
| 195 | media preco chilenos | 3 | 3 | - | sem dados |
| 196 | Espanha nota/preco | 3 | 4 | - | sem dados |
| 197 | total vinhos | 5 | 5 | - | - |
| 198 | uva mais popular | 3 | 3 | - | sem dados |
| 199 | portugueses vs chilenos | 5 | 5 | - | - |

### Q — FOTO / OCR (10)

| # | Pergunta | P | UX | Violacoes | Problemas |
|---|----------|---|-----|-----------|-----------|
| 200 | foto do rotulo | 4 | 5 | - | - |
| 201 | rotulo apagado | 4 | 5 | - | - |
| 202 | print reels | 4 | 4 | - | - |
| 203 | oxidado na foto | 4 | 5 | - | - |
| 204 | sedimento fundo | 3 | 3 | - | tom "trollando" |
| 205 | garrafa sem rotulo | 4 | 5 | - | - |
| 206 | app nao reconhece | 4 | 4 | - | - |
| 207 | foto borrada | 4 | 5 | - | - |
| 208 | foto espumante | 4 | 3 | - | tom impaciente |
| 209 | so capsula dourada | 4 | 5 | - | - |

### R — GUARDA / CONSERVACAO (8)

| # | Pergunta | P | UX | Violacoes | Problemas |
|---|----------|---|-----|-----------|-----------|
| 210 | aberto quantos dias | 5 | 5 | - | - |
| 211 | armazenar sem adega | 4 | 4 | - | longo |
| 212 | geladeira por meses | 4 | 4 | - | longo |
| 213 | congelou freezer | 5 | 5 | - | - |
| 214 | vinho velho garagem | 4 | 5 | - | - |
| 215 | conservar calor | 4 | 3 | - | truncado |
| 216 | nao precisa adega | 5 | 5 | - | - |
| 217 | 750ml vs magnum | 4 | 5 | - | - |

### S — FORUM / COMUNIDADE (10)

| # | Pergunta | P | UX | Violacoes | Problemas |
|---|----------|---|-----|-----------|-----------|
| 218 | rolha plastico | 4 | 5 | - | - |
| 219 | Vivino Casal Garcia | 3 | 4 | borderline R1 | "aquele site" |
| 220 | nota 4.2 app | 3 | 4 | borderline R1 | "aquele app" |
| 221 | Casillero odiado | 4 | 5 | - | - |
| 222 | Luigi Bosca alcoolico | 4 | 5 | - | - |
| 223 | 5 estrelas vinho simples | 5 | 5 | - | - |
| 224 | georgianos qvevri | 5 | 5 | - | - |
| 225 | natural wine suco azedo | 5 | 4 | genero | truncado |
| 226 | novo mundo melhor | 4 | 4 | - | - |
| 227 | Tannat duro | 4 | 5 | genero | - |

### T — INFORMAL / WHATSAPP (8)

| # | Pergunta | P | UX | Violacoes | Problemas |
|---|----------|---|-----|-----------|-----------|
| 228 | mano vinho ate 60 | 4 | 4 | - | precos USD |
| 229 | irmao 50 conto | 4 | 5 | - | - |
| 230 | foto na pressa | 4 | 5 | - | - |
| 231 | tinto ou branco | 4 | 5 | genero | - |
| 232 | garrafa azul | 4 | 5 | - | - |
| 233 | mina gosta doce | 4 | 5 | - | - |
| 234 | oq vcs bebendo hj | 3 | 3 | - | so pergunta |
| 235 | vinho desconhecido sensacional | 5 | 5 | - | - |

### U — TESTE DE LIMITES (11)

| # | Pergunta | P | UX | Violacoes | Problemas |
|---|----------|---|-----|-----------|-----------|
| 236 | Baco existiu | 5 | 5 | - | - |
| 237 | bebe de verdade | 5 | 5 | - | - |
| 238 | sentido da vida | 5 | 5 | - | longo mas lindo |
| 239 | jogo Flamengo | 5 | 5 | - | - |
| 240 | matematica | 4 | 5 | - | - |
| 241 | vinho cachorro | 5 | 5 | genero | - |
| 242 | limpeza casa | 4 | 5 | - | - |
| 243 | cerveja melhor | 5 | 5 | - | - |
| 244 | vinho Coca-Cola | 4 | 5 | - | - |
| 245 | refrigerante limao | 4 | 5 | - | - |
| 246 | tio 1998 rotulo vermelho | 5 | 5 | - | - |
