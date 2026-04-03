## CONTEXTO

Temos 2 bases de vinhos:
- **Vivino:** 1.7M vinhos com campos separados: `produtor_normalizado` e `nome_normalizado`
- **Lojas:** 3.96M vinhos com tudo num campo so: `nome_normalizado`

Estamos tentando casar vinhos de lojas com o Vivino. O algoritmo atual funciona assim:

### Algoritmo de match (4 estrategias em cascata):
1. **Busca por produtor** — pega a palavra mais longa do produtor da loja e busca com ILIKE no Vivino
2. **Busca por keyword** — pega a palavra mais distinta do nome e busca no Vivino
3. **pg_trgm similarity no nome** — fuzzy match por trigramas
4. **pg_trgm no texto combinado** — fuzzy match no produtor+nome concatenado

### Scoring (0.0 a 1.0):
- Token overlap distintivo loja→Vivino: 0.35
- Token overlap geral: 0.10
- Token overlap reverso: 0.10
- Match de produtor: 0.25 (penalidade -0.10 se nao bate)
- Safra identica: 0.12
- Tipo identico: 0.08

### Threshold:
- Produtor bate + score >= 0.45 → aceita (destino A)
- Produtor NAO bate + score >= 0.70 → aceita (destino A)
- Score entre 0.30-0.45 ou produtor nao bate → C1 (quarentena — sabe que e vinho mas match duvidoso)

## O PROBLEMA

Temos ~400 vinhos na amostra de 2000 (20%) classificados como C1 — o sistema sabe que sao vinhos reais mas NAO conseguiu casar com confianca com o Vivino. Muitos desses vinhos ESTAO no Vivino mas o match falhou.

### Exemplos de falha (o vinho ESTA no Vivino mas nao casou):

```
LOJA: "d arenberg the dead arm shiraz"
VIVINO: "darenberg — the dead arm shiraz"
PROBLEMA: "d arenberg" (com espaco) vs "darenberg" (junto). Produtor nao bate.

LOJA: "b moreau chassagne montrachet morgeot 1er cru"
VIVINO: "bernard moreau — chassagne montrachet 1er cru morgeot"
PROBLEMA: "b moreau" (inicial) vs "bernard moreau" (nome completo). Produtor nao bate.

LOJA: "b by fonbadet bordeaux"
VIVINO: "chateau fonbadet — b de fonbadet bordeaux"
PROBLEMA: nome da linha e diferente ("b by" vs "b de"). Produtor nao bate.

LOJA: "b herzog jeunesse pinot noir"
VIVINO: "herzog — jeunesse pinot noir"
PROBLEMA: "b herzog" (com inicial) vs "herzog" (sem inicial). Produtor nao bate.

LOJA: "b cabernet sauvignon beckstoffer to kalon 2019"
VIVINO: "schrader — cabernet sauvignon rbs beckstoffer to kalon vineyard"
PROBLEMA: produtor da loja nao aparece. Nome do vinhedo "beckstoffer to kalon" e o link.

LOJA: "r de ruinart brut magnum"
VIVINO: "ruinart — r de ruinart brut"
PROBLEMA: "r de ruinart" funciona como nome, mas o produtor e "ruinart".

LOJA: "m chapoutier belleruche cotes du rhone"
VIVINO: "m chapoutier — belleruche cotes du rhone"
PROBLEMA: este DEVERIA casar mas o score ficou baixo por alguma razao de tokens.
```

### Padroes de falha identificados:

1. **Inicial + sobrenome** — "b moreau" vs "bernard moreau", "m chapoutier" vs "michel chapoutier"
2. **Nome com espaco vs junto** — "d arenberg" vs "darenberg", "d auvenay" vs "dauvenay"
3. **Prefixos de linha** — "b by fonbadet" vs "b de fonbadet", "r de ruinart" vs "ruinart"
4. **Produtor diferente, vinhedo em comum** — "beckstoffer to kalon" aparece em Schrader, Bond, Tor
5. **Produtor ausente** — loja so tem nome do vinho sem produtor

## A LISTA C1 (50 exemplos reais)

Esses vinhos sao CONFIRMADOS como vinhos (wine-likeness >= 3) mas nao casaram com confianca no Vivino:

```
"b block chardonnay 2025" → match fraco com "delamere block 3 chardonnay"
"b by fonbadet bordeaux" → match fraco com "chateau fonbadet b de fonbadet bordeaux"
"b cabernet franc beckstoffer dr crane 2021" → match fraco com "waypoint beckstoffer dr crane cabernet franc"
"b cabernet sauvignon beckstoffer to kalon 2019" → match fraco com "schrader cabernet sauvignon beckstoffer to kalon"
"b cellars 2007 napa cabernet sauvignon georges iii" → match fraco com "purlieu georges iii cabernet sauvignon"
"b de basilio blanco 2014" → match fraco com "basilio izquierdo b de basilio blanco"
"b desaunaybissey bourgogne blanc 2022" → match fraco com "louis latour bourgogne blanc"
"b g barton guestier cotes de provence rose tourmaline" → match fraco com "barton guestier tourmaline cotes de provence"
"b herzog jeunesse pinot noir" → match fraco com "herzog jeunesse pinot noir"
"b moreau chassagne montrachet morgeot 1er cru" → match fraco com "prieurbrunet chassagne montrachet 1er cru"
"b moreau bourgogne blanc" → match fraco com "jeanmichel moreau bourgogne blanc"
"d arenberg the dead arm shiraz" → match fraco com "darenberg the dead arm shiraz"
"d arenberg the footbolt shiraz 2022" → match fraco com "darenberg the footbolt shiraz"
"d arenberg the hermit crab viognier marsanne" → match fraco com "darenberg the hermit crab viognier marsanne"
"d arenberg laughing magpie shiraz viognier" → match fraco com "darenberg the laughing magpie shiraz viognier"
"d alamel reserva cabernet sauvignon" → match fraco com "vines 79 rescue red cabernet sauvignon"
"j bookwalter winery chapter cuvee columbia valley 2021" → match fraco com produtor
"m chapoutier belleruche cotes du rhone" → match fraco com "m chapoutier belleruche cotes du rhone"
"m c noellat gevrey chambertin" → match fraco com produtor
"p minot vosne romanee" → match fraco com produtor
"r de ruinart brut magnum" → match fraco com "ruinart r de ruinart brut"
"r chevillon nuits st georges vieilles vignes" → match fraco com produtor
"t cuvee rot igt 2023 kellerei tramin" → match fraco com "kellerei tramin"
```

## O QUE PRECISO DE VOCE

1. **Analise os padroes de falha** — por que o algoritmo nao consegue casar esses vinhos?

2. **Sugira melhorias ao algoritmo** que resolveriam esses casos sem criar falsos positivos. Ideias que estou considerando:
   - Normalizar "d arenberg" → "darenberg" (juntar iniciais coladas)
   - Buscar por sobrenome do produtor ignorando iniciais ("b moreau" → buscar "moreau")
   - Buscar pelo nome da linha/vinho ignorando o produtor
   - Usar o nome do vinhedo como chave secundaria ("beckstoffer to kalon")

3. **Identifique quais desses 50 vinhos provavelmente NAO estao no Vivino** (vinhos muito raros, regionais, ou producao limitada que o Vivino pode nao cobrir).

4. **Sugira metricas de confianca** — como saber se um match fraco e correto ou errado sem fazer busca externa?

## REGRAS
- NAO sugira scraping ou busca em APIs externas
- As solucoes devem funcionar com os dados que ja temos (texto do nome + campos da tabela)
- Priorize solucoes que funcionem em escala (800K vinhos, nao 1 por 1)
- Foque em mudancas no algoritmo de match, nao na classificacao de vinho
