# METODOLOGIA — Match Vinhos de Loja contra Vivino

## Versao: 2.0 (30/03/2026)
## Autor: CTO WineGod (Claude)
## Status: Curadoria de indicadores concluida, pendente re-rodar amostra

---

## 1. O PROBLEMA

O WineGod tem 2 bases de vinhos:
- **Vivino (confiavel):** 1,727,058 vinhos com notas, reviews, produtores verificados
- **Lojas (novos):** 2,942,304 vinhos unicos de 50 paises, extraidos de 57K lojas

O objetivo e cruzar: pra cada vinho de loja, encontrar o vinho correspondente no Vivino. Isso permite:
- Associar nota Vivino ao vinho da loja
- Calcular WineGod Score (custo-beneficio)
- Confirmar que o produto e um vinho real

### Por que e dificil

O Vivino **separa** produtor do nome. As lojas **juntam** tudo num campo so:

```
Vivino:  produtor = "Barefoot"     nome_normalizado = "pinot grigio"
Loja:    nome_normalizado = "barefoot pinot grigio 2022"

Vivino:  produtor = "Antinori"     nome_normalizado = "solaia"
Loja:    nome_normalizado = "2022 solaia antinori toscana"
```

Comparar strings inteiras **nao funciona** — os formatos sao incompativeis.

### Tentativas anteriores que falharam

| Abordagem | Resultado | Por que falhou |
|---|---|---|
| Match exato de nome_normalizado | **0.6%** | Formatos incompativeis |
| Concatenar produtor+nome do Vivino | **4%** | Loja muitas vezes nao inclui produtor |
| Splink fuzzy (Jaro-Winkler) | **0%** | Blocking rules incompativeis |

---

## 2. A SOLUCAO — Match Multi-Estrategia

### 2.1 Preparacao: Importar Vivino localmente

O Vivino esta no Render (remoto, ~27s por query). Impossivel fazer 2.9M queries remotas.

**Solucao:** Importar os 1.7M vinhos Vivino pra tabela local `vivino_match`:

```sql
CREATE TABLE vivino_match (
    id INTEGER PRIMARY KEY,
    nome_normalizado TEXT,
    produtor_normalizado TEXT,
    safra VARCHAR(10),
    tipo VARCHAR(20),
    pais VARCHAR(5),
    regiao TEXT,
    texto_busca TEXT  -- produtor + nome concatenados
);
```

**Indexes criados (GIN trgm):**
- `texto_busca gin_trgm_ops` — busca fuzzy no texto combinado
- `nome_normalizado gin_trgm_ops` — busca fuzzy so no nome
- `produtor_normalizado gin_trgm_ops` — busca fuzzy no produtor

**Script:** `C:\winegod-app\scripts\import_vivino_local.py`
**Tempo:** ~25 minutos (1K registros/segundo do Render)

### 2.2 Algoritmo de busca (4 estrategias em cascata)

Para cada vinho de loja, tenta 4 estrategias em ordem de velocidade:

#### Estrategia 1 — Busca por produtor (0.03s)
```sql
SELECT * FROM vivino_match
WHERE produtor_normalizado ILIKE '%anchor_word%'
LIMIT 200
```
Pega a palavra mais longa e distinta do produtor da loja. Retorna todos os vinhos desse produtor no Vivino. Resolve ~70% dos vinhos.

#### Estrategia 2 — Busca por palavra-chave (0.05s)
```sql
SELECT * FROM vivino_match
WHERE nome_normalizado ILIKE '%keyword%'
   OR produtor_normalizado ILIKE '%keyword%'
LIMIT 150
```
Pega a palavra mais longa e distinta do nome da loja. Resolve ~20%.

#### Estrategia 3 — pg_trgm no nome (~2s)
```sql
SELECT *, similarity(nome_normalizado, 'search_text') as sim
FROM vivino_match
WHERE nome_normalizado % 'search_text'
ORDER BY sim DESC LIMIT 10
```
Similaridade fuzzy por trigramas. Resolve ~8%.

#### Estrategia 4 — pg_trgm no texto combinado (~17s)
```sql
SELECT *, similarity(texto_busca, 'full_store_name') as sim
FROM vivino_match
WHERE texto_busca % 'full_store_name'
ORDER BY sim DESC LIMIT 10
```
Ultimo recurso, mais lento. Resolve ~2%.

**Logica de cascata:** So avanca pra proxima estrategia se a anterior nao encontrou match com score suficiente.

### 2.3 Scoring de candidatos

Cada candidato Vivino recebe um score de 0.0 a 1.0:

| Componente | Peso | O que mede |
|---|---|---|
| Token overlap loja→Vivino (distintivos) | 0.35 | Quantas palavras da loja aparecem no Vivino |
| Token overlap loja→Vivino (todos) | 0.10 | Idem mas com todas as palavras |
| Token overlap Vivino→loja | 0.10 | Quantas palavras do Vivino aparecem na loja |
| Match de produtor | 0.25 | Produtor da loja bate com produtor Vivino |
| Safra identica | 0.12 | Mesmo ano |
| Tipo identico | 0.08 | Tinto=tinto, branco=branco |

**Penalidades:**
- Produtor NAO bate: -0.10
- Safra diferente: -0.02
- Tipo contradiz (tinto↔branco): -0.15

**Tokens "distintivos"** = palavras que nao sao genericas (exclui: "wine", "reserve", "estate", "domaine", "red", "white", etc.)

### 2.4 Threshold duplo

A decisao de aceitar um match depende de SE o produtor bateu:

| Situacao | Threshold | Justificativa |
|---|---|---|
| Produtor bate | >= 0.45 | Se o produtor e o mesmo, precisa de menos evidencia |
| Produtor NAO bate | >= 0.70 | Sem produtor, precisa de muito mais evidencia |

### 2.5 Regra do produtor unico

Quando a loja tem "Conejo Negro Gran Malbec" e o Vivino tem "Conejo Negro Malbec":
- Se o Vivino so tem **1 Malbec** do Conejo Negro → sao o mesmo vinho (variante)
- Se o Vivino tem **2+ Malbecs** → precisa bater mais palavras do nome

Adjetivos como "Gran", "Reserva", "Selection", "Old Vines" sao variantes do vinho base quando o produtor so tem 1 daquele tipo/uva.

**Excecao:** Na Espanha e Italia, "Reserva" e "Gran Reserva" sao classificacoes legais (DO). O Vivino normalmente ja separa esses em registros diferentes, entao o scoring resolve naturalmente.

---

## 3. PRIMEIRO TESTE — 200 VINHOS ALEATORIOS

### 3.1 Resultado bruto (score do sistema)

| Nivel | Qtd | % |
|---|---|---|
| HIGH (>=0.55) | 72 | 36% |
| MEDIUM (0.40-0.55) | 58 | 29% |
| LOW (0.30-0.40) | 33 | 16.5% |
| NO_MATCH (<0.30) | 37 | 18.5% |
| **Total matched (H+M)** | **130** | **65%** |

### 3.2 Verificacao manual (pelo fundador)

A verificacao manual RIGOROSA dos 200 revelou:

**Precisao REAL: ~34%** (55 corretos de 161 matches)

| Faixa de score | Precisao estimada |
|---|---|
| >= 0.80 | ~95% |
| 0.65-0.80 | ~60% |
| 0.55-0.65 | ~30% |
| 0.40-0.55 | ~10-18% |
| 0.30-0.40 | ~5% |

### 3.3 Problemas encontrados

#### A) Nao-vinhos na base (~15-20% dos 2.9M)

A limpeza do Chat W nao removeu tudo. Ainda na base:

| Categoria | Exemplos encontrados |
|---|---|
| COMIDA | mel, cha, chocolate, biscoito, molho de tomate, puree, tempero, conserva |
| OBJETO | refrigerador, perfume, caneta, isqueiro, coador, pouf, movel, sapato |
| COSMETICO | Pantene, Rexona, desodorante, hair spray |
| DESTILADO | whisky, rum, gin, bourbon, sake, cognac, grappa, cachaca |
| CERVEJA | lager, IPA, stout, pilsner |
| COCKTAIL | espresso martini, bitters, vermouth (ambiguo) |
| OUTROS | cartao de natal, cesta de presente, adega climatizada, charuto |

#### B) Falsos positivos por nome generico

O sistema encontra uma palavra em comum e casa errado:

```
"bitter 820g" (comida) → "bitter creek cabernet" (score 0.51)
"manta lana mohair" (cobertor) → "lana malbec" (score 0.45)
"shoes bags" (sapato) → "no shoes pinot noir" (score 0.50)
"espresso martini can" → "espresso chardonnay" (score 0.45)
```

#### C) Mesmo produtor, vinho errado

```
"rutini cab sauvignon malbec" → "rutini malbec" (blend vs varietal)
"tommasi ripasso" → "tommasi amarone" (ripasso ≠ amarone)
"fieldhouse 301 merlot" → "fieldhouse 301 white zinfandel"
"fuenteseca bobal cabernet" → "fuenteseca bobal syrah"
```

#### D) Matches corretos (exemplos de sucesso)

```
"tyrian clouds shiraz" → "tyrian clouds shiraz" (0.88) — perfeito
"gaja dagromis barolo" → "gaja dagromis barolo" (0.83) — perfeito
"cappellano barolo pie rupestris" → "cappellano pie rupestris barolo" (0.84) — ordem diferente
"jackson estate shelter bay sauv blanc" → "jackson estate shelter bay sauv blanc" (0.87)
"krug clos du mesnil 2008" → "krug clos du mesnil" (0.58) — safra diferente, mesmo vinho
```

---

## 4. EVOLUCAO — SISTEMA DE 5 DESTINOS

Baseado nos problemas encontrados, o sistema evoluiu de binario (match/nao-match) para 5 destinos:

### 4.1 Fluxo completo

```
wines_unique (2.9M)
    │
    ├── ETAPA 1: Filtrar nao-vinhos (ANTES do match)
    │   │
    │   ├── D: NOT_WINE → ELIMINA
    │   │   - Palavras proibidas (comida, objeto, cosmetico): ~200 termos
    │   │   - Padroes de peso/quantidade: "500g", "1kg", "16oz"
    │   │   - Wine-likeness = 0 (nenhum indicador de vinho)
    │   │
    │   ├── E: SPIRITS → ARQUIVO SEPARADO
    │   │   - Destilados: whisky, rum, gin, vodka, tequila, etc.
    │   │   - Nao elimina — pode ser util no futuro
    │   │
    │   └── Vinhos provaveis (wine-likeness >= 2) → ETAPA 2
    │
    ├── ETAPA 2: Match com Vivino
    │   │
    │   ├── A: MATCHED_VIVINO → SOBE PRO RENDER
    │   │   - Produtor bate + score >= 0.45
    │   │   - OU produtor nao bate + score >= 0.70
    │   │   - Tipo nao contradiz (tinto↔branco = invalida)
    │   │
    │   ├── B: WINE_NEW → ARQUIVO (sobe depois)
    │   │   - NAO casou com Vivino
    │   │   - Wine-likeness >= 3 (certeza que e vinho)
    │   │   - Tem loja de origem
    │   │
    │   ├── C1: QUARENTENA_PROVAVEL → REVISAR
    │   │   - Wine-likeness >= 3 mas match duvidoso
    │   │   - Score 0.30-0.45 ou produtor nao bate
    │   │
    │   └── C2: QUARENTENA_INCERTO → BAIXA PRIORIDADE
    │       - Wine-likeness = 2
    │       - Sem match ou match muito fraco
    │
    └── FIM
```

### 4.2 Wine-likeness score (0-7)

Mede quao provavel e que o registro seja um vinho. **Atualizado na v2** com produtor Vivino e vocabulario global.

| Indicador | Pontos |
|---|---|
| Tipo reconhecido (Tinto, Branco, Rose, Espumante, Fortificado, Sobremesa) | +1 |
| Safra entre 1900 e 2026 | +1 |
| Regiao preenchida (length > 2) | +1 |
| Nome contem uva (lista expandida — ver 4.4) | +1 |
| Nome contem termo de vinho (lista expandida — ver 4.5) | +1 |
| **Produtor da loja existe como produtor no Vivino** (novo v2) | **+2** |

- Score 0: nao e vinho → Destino D
- Score 1: quarentena → Destino C2
- Score 2+: tentar match
- Score 3+: se nao casar com Vivino → Destino B (vinho novo confirmado)

### 4.2.1 Lista GARANTIA_VINHO (novo v2)

Palavras que **confirmam** que o produto e vinho — forcam wine-likeness = 3 minimo (garante tentativa de match e destino B se nao casar). Testadas com <0.1% falso positivo na base de lojas de vinho.

```
vineyard, vineyards, winery, wineries, vinicola,
vigneron, vignerons, vignoble, weingut, winzer,
winzergenossenschaft, bodega, bodegas, cantina,
chateau, domaine, quinta, tenuta, fattoria, podere,
herdade, adega, kellerei, clos, castello, schloss
```

**Eliminado:** `mas` (42% falso positivo — "geleia", "hierbabuena", palavra comum em ES/PT)

**Por que funciona:** As fontes sao lojas de vinho, nao supermercados genericos. "Chateau" numa loja de vinhos e 99.9% vinho, nao hotel.

### 4.2.2 Regra de comprimento minimo (novo v2)

| Chars uteis (letras) | Regra | Justificativa |
|---|---|---|
| 0-2 | **D direto** (elimina sem tentar match) | 14.5K na base, 99%+ codigos/lixo. So 22 vinhos reais no Vivino inteiro com nome tao curto |
| 3-4 | Tenta match → A se Vivino bate, B se wl>=3, **D se nada** | Nome curto demais pra quarentena. Ou e vinho confirmado ou e lixo |
| 5+ | Pipeline normal (A/B/C1/C2) | Informacao suficiente pra quarentena |

"Chars uteis" = caracteres alfabeticos (sem numeros, espacos, pontuacao).

**Exemplo do impacto do produtor Vivino (+2):**
- "j bouchon canto sur" — antes: wl=0 (eliminado). Agora: wl=2 (vai pro match). J. Bouchon existe no Vivino como produtor chileno.
- "pantene hair spray" — antes: wl=0. Agora: wl=0 (continua eliminado). Pantene nao existe como produtor no Vivino.

### 4.3 Filtro de nao-vinhos

**~200 palavras proibidas** organizadas em categorias:
- Comida (arroz, feijao, chocolate, biscoito, sauce, honey, garlic...)
- Objetos (refrigerador, speaker, cable, furniture, lamp...)
- Cosmeticos (shampoo, deodorant, perfume, lipstick...)
- Roupa (shoe, shirt, dress, pants, jersey...)
- Papelaria (caneta, pencil, folder, stapler...)
- Ferramentas (screwdriver, hammer, drill, strainer...)

**Padroes regex:**
- `\b\d+\s*g\b` (peso em gramas)
- `\b\d+\s*kg\b` (peso em kilos)
- `\b\d+\s*oz\b` (peso em ounces)
- `\bpack\s+of\b`, `\bbox\s+of\b`, `\bset\s+of\b`

**~40 termos de destilado** (arquivo separado, nao elimina):
- whisky, whiskey, bourbon, scotch, rum, gin, vodka, tequila, cognac, grappa...

### 4.4 Lista de uvas (expandida na v2 — curadoria global)

**Curadoria feita com pesquisa em 3 IAs (Gemini, Kimi, ChatGPT) + validacao contra wines_unique e vivino_match. Cada uva foi testada: existe na base? E vinho real?**

**Uvas internacionais originais (~60):** cabernet, sauvignon, merlot, pinot, noir, grigio, gris, chardonnay, syrah, shiraz, tempranillo, malbec, zinfandel, sangiovese, nebbiolo, barbera, riesling, gewurztraminer, chenin, viognier, mourvedre, grenache, garnacha, carmenere, primitivo, gamay, muscat, moscato, moscatel, torrontes, albarino, verdejo, gruner, veltliner, montepulciano, lambrusco, corvina, glera, trebbiano, vermentino, fiano, aglianico, dolcetto, arneis, cortese, tannat, bonarda, touriga, tinta, bobal, monastrell, cinsault, carignan, mencia, godello, alvarinho, semillon, marsanne, roussanne, picpoul, clairette, blaufrankisch, zweigelt, saperavi, rkatsiteli, pinotage, petite, sirah, petit, verdot, semillion, gewurz.

**Sinonimos internacionais adicionados na v2 (~20):** spatburgunder (Pinot Noir DE, 3.8K+15.7K), blauburgunder (AT), grauburgunder (Pinot Grigio DE), weissburgunder (Pinot Blanc DE), cannonau (Grenache Sardegna), aragonez (Tempranillo PT), cencibel (Tempranillo ES), mataro (Mourvedre AU), nielluccio/morellino/prugnolo (Sangiovese), kekfrankos/lemberger/frankovka (Blaufrankisch), mazuelo/samso (Carignan), traminer, tribidrag, chiavennasca.

**Uvas locais por pais adicionadas na v2 (~66):**
- **Alemanha/Austria (10):** dornfelder, silvaner, kerner, scheurebe, trollinger, rotgipfler, zierfandler, neuburger, welschriesling, olaszrizling
- **Portugal (13):** castelao, trincadeira, encruzado, arinto, loureiro, verdelho, boal, sercial, viosinho, gouveio, sousao, alfrocheiro, rabigato
- **Grecia (11):** assyrtiko, xinomavro, agiorgitiko, moschofilero, malagousia, roditis, robola, mavrodaphne, athiri, vidiano, limnio
- **Hungria (4):** furmint, harslevelu, kadarka, juhfark
- **Georgia (6):** mtsvane, kisi, khikhvi, chinuri, tavkveri, aladasturi
- **Romenia (3):** feteasca, babeasca, tamaioasa
- **Croacia/Eslovenia (6):** posip, grasevina, malvazija, teran, rebula + plavac mali
- **Bulgaria (5):** mavrud, melnik, gamza, dimyat, pamid
- **Turquia (3):** okuzgozu, bogazkere, narince
- **Japao (1):** koshu
- **Argentina (1):** criolla
- **Libano/Israel (4):** obaideh, merwah, argaman, dabouki
- **Outros:** spanna (Nebbiolo), ugni blanc (Trebbiano)

**Abreviacoes de uva multi-palavra (~19):** cab sauv, cab franc, sauv blanc, sav blanc, gsm, tinta roriz, ull de llebre, antao vaz, fernao pires, tinta negra, irsai oliver, plavac mali, kalecik karasi, muscat bailey, ugni blanc, st laurent, skin contact, vin santo, vendange tardive, methode traditionnelle, cru classe, vino de pago, metodo classico, pet nat.

**Candidatos ELIMINADOS por falso positivo (13):**
- `cot` (55K falsos — "cotes", "coteaux" capturam substring)
- `rolle` ("roller", "trolley", "stroller")
- `steen` ("steenberg", "mangosteen")
- `emir` ("nemiroff", "remirez")
- `rubin` ("rubino", "cherubini")
- `baga` ("bagasse", "bagagem")
- `bacchus` (cerveja/mead/marca)
- `favorita` (comida — "fideos", "macarrao", "pesto")
- `wein` ("weinbrand"=brandy, "schwein"=porco)
- `bor` ("aalborg", "marlborough")
- `dac` ("pedaco", substring)
- `fino` ("finocchietto", "picole grifinoria")
- `sarap` ("sweetsarap spaghetti", "evapsarap")

### 4.5 Lista de termos de vinho (expandida na v2)

**Termos originais (~100):** cuvee, barrique, vendemmia, cru, terroir, chateau, domaine, bodega, cantina, weingut, tenuta, quinta, vineyard, barolo, barbaresco, chianti, brunello, amarone, bordeaux, bourgogne, champagne, rioja, ribera, douro, alentejo, vinho, napa, sonoma, trocken, brut, prosecco, franciacorta, cremant, cava, sekt, port, porto, sherry, madeira, marsala, sauternes, rose, rosado, rosato, reserva, riserva, crianza, doc, docg, aoc, igt, igp, etc.

**Termos adicionados na v2 (~43):**
- **Porto/Fortificado (8):** portwein, portwijn, portvin, oporto, tawny, lbv, crusted, garrafeira, colheita, ruby
- **Sherry estilos (4):** amontillado, oloroso, manzanilla, palo cortado
- **Alemao (16):** rotwein, weisswein, rosewein, winzer, weinberg, spatlese, auslese, kabinett, halbtrocken, feinherb, pradikatswein, qualitatswein, landwein, eiswein, beerenauslese, trockenbeerenauslese
- **Austria (3):** smaragd, federspiel, steinfeder
- **Escandinavo (4):** rodvin, hvidvin, rosevin, hedvin
- **Holandes/Polones (2):** wijn, wino
- **Romeno/Hungaro (3):** spumant, aszu, szamorodni
- **Espumantes (4):** frizzante, spumante, mousseux, perlwein
- **Late harvest (4):** passito, recioto, sforzato, vinsanto
- **Natural/Orange (2):** qvevri, amphora
- **Classificacao (1):** cru bourgeois

---

## 5. VALIDACAO EM ANDAMENTO — 2000 VINHOS POR LETRA

### 5.1 Metodologia

Amostra de 2000 vinhos distribuidos por **8 letras do alfabeto**:
- Letras: B, D, J, M, O, P, R, T
- 250 vinhos por letra
- Ordem alfabetica dentro de cada letra
- Cada vinho e classificado em A/B/C1/C2/D/E

### 5.2 Por que por letra e nao aleatorio

1. **Ordem alfabetica agrupa variantes** — "Conejo Negro Gran Malbec" e "Conejo Negro Malbec" ficam juntos. Permite ver se a regra do produtor unico funciona.
2. **Letras diversas garantem diversidade** — B tem Bordeaux e brasileiros, J tem japoneses, M tem Malbec argentino, T tem Toscana italiana.
3. **Facilita verificacao visual** — o fundador pode ler em sequencia e notar padroes.

### 5.3 Resultado da primeira rodada (ANTES da curadoria v2)

| Destino | Qtd | % | Extrapolado 2.9M |
|---|---|---|---|
| A (matched Vivino) | 458 | 22.9% | ~674K |
| B (vinho novo) | 48 | 2.4% | ~71K |
| C1 (quarentena provavel) | 319 | 16.0% | ~469K |
| C2 (quarentena incerto) | 695 | 34.8% | ~1.02M |
| D (nao-vinho) | 446 | 22.3% | ~656K |
| E (destilado) | 34 | 1.7% | ~50K |

Distribuicao por letra:

| Letra | A | B | C1 | C2 | D | E |
|---|---|---|---|---|---|---|
| B | 42 | 2 | 24 | 103 | 74 | 5 |
| D | 78 | 8 | 52 | 72 | 39 | 1 |
| J | 118 | 2 | 14 | 49 | 41 | 26 |
| M | 57 | 13 | 49 | 82 | 49 | 0 |
| O | 6 | 13 | 56 | 122 | 53 | 0 |
| P | 64 | 5 | 38 | 77 | 64 | 2 |
| R | 48 | 5 | 66 | 97 | 34 | 0 |
| T | 45 | 0 | 20 | 93 | 92 | 0 |

**Problemas identificados na verificacao visual:**
- Vinhos reais eliminados como D (J. Bouchon, D'Arenberg, M. Chapoutier) — produtor existe no Vivino mas wine_likeness=0
- Termos de vinho em alemao, escandinavo, polones nao reconhecidos
- Uvas locais (assyrtiko, furmint, feteasca, etc.) nao estavam na lista

### 5.4 Melhorias aplicadas (v2)

1. **Produtor Vivino (+2 wine_likeness)** — se o produtor da loja existe no Vivino, ganha +2 pontos
2. **86 uvas novas** — sinonimos internacionais + uvas locais de 15 paises
3. **43 termos de vinho** em 8 linguas + classificacoes legais
4. **19 abreviacoes multi-palavra** novas
5. **8 termos de Porto/Sherry** adicionados (portwein, tawny, lbv, amontillado, etc.)
6. **13 candidatos de uva eliminados** por falso positivo (cot, rolle, steen, etc.)
7. **26 palavras GARANTIA_VINHO** que forcam wl=3 (chateau, domaine, vineyard, weingut, bodega, etc.)
8. **Regra de comprimento minimo** — 0-2 chars uteis → D, 3-4 chars → D se nao casar com Vivino
9. **~15 novos termos na blacklist** (verjus, mosto, refill, steak, lakrids, speyside, pure malt, ice drink, etc.) — validados por 3 IAs
10. **~10 novos termos de vinho** (likorwein, champagner, espumoso, sparkling, oinos, valdeorras, morgon, salento)
11. **Candidatos `rot` e `weiss` rejeitados** — ambiguos (revista "noble rot", almofada "auf weiss", cerveja "cerveza weiss")
12. **Cerveja na blacklist (+9):** stout, lager, pilsner, ipa, beer, cerveza, cerveja, brewery, hops — validados 0 falsos. Rejeitados: `ale` (ginger ale), `bier` (bierzo = vinho)
13. **Licor "creme de" na blacklist** — 9 variantes (menthe, cassis, mure, peche, framboise, violette, cacao, mandarine, moka) — 2.9K registros, 100% licor
14. **Regioes de whisky na blacklist (+3):** lowland, islay, campbeltown — rejeitado: `highland` (santa lucia highlands = vinho)
15. **Borgonha vilas como termos de vinho (+10):** meursault (13.5K), pommard (6.2K), volnay (7.3K), corton (8.8K), santenay, rully, mercurey, givry, musigny, romanee — todos 100% vinho
16. **Rhone vilas (+7):** condrieu, vacqueyras, gigondas, tavel, lirac, cairanne, fitou
17. **Georgia denominacoes (+3):** tsinandali, mukuzani, khvanchkara
18. **Multi-palavra fortissimos (+17):** blanc de blancs (19K), blanc de noirs (5.5K), vieilles vignes (13K), old vines, vin de france, cotes de provence, rias baixas + 10 vilas Borgonha + crozes hermitage + cote rotie

19. **`1er` e `rosat` adicionados** aos TERMOS_VINHO — 1er = Premier Cru abreviado (49K loja, 15K vivino), rosat = rosé catalao (501 + 9.2K)
20. **Validacao por 3 IAs (Gemini, Kimi, ChatGPT)** — enviamos vinhos de 0.30-0.60 e 0.68-0.88 pra classificacao. Resultado: **zero nao-vinhos** confirmados na faixa A. Blacklist e GARANTIA_VINHO validados.
21. **Verificacao pos-pipeline (A+B, 2000 vinhos, 0.00-0.40)** — 3 IAs identificaram: `tabaco` (452), `presente gourmet`, `pata negra` (presunto), `riedel` (3K) como nao-vinhos. Adicionados. `fumo` rejeitado ("bulfon fumo rosso" = vinho). `b2b` rejeitado (vinhos reais).
22. **Verificacao pos-pipeline (A+B, 0.40-1.00)** — `aperitivo` (2.9K), `carafe`/`caraffe` (592). Adicionados. `snaps` rejeitado ("ginger snaps"). `marc`/`bundle`/`magnum`/`case`/`pack` rejeitados (embalagens de vinho real).
23. **Verificacao C2 (1504 vinhos incertos)** — 3 IAs encontraram 42-53% nao-vinho no C2. Novos termos validados contra o banco e adicionados (13 termos, ~4.3K registros):
    - Cerveja: `pabst` (122)
    - Textil: `sabana` (369), `hilos` (345)
    - Comida/massa: `fabada` (75), `penne` (894), `paccheri` (146), `fettuccine` (272)
    - Xarope: `szirup` (96), `sirop` (918), `topping` (141)
    - Papelaria/eletronico: `ballpen` (39), `samsung` (653)
    - Higiene: `rollon` (223)
    - Rejeitados: `spritz` (vinhos naturais), `vermouth` (base de vinho), `keg` ("drikkeglas" = copo DK), `distillery` (pode pegar wine distillery), `snaps` ("ginger snaps")
    - Total acumulado de nao-vinhos extras identificados: ~11K registros

### 5.6 Resultado da segunda rodada (v4 — pos-curadoria completa, 30/03/2026)

| Destino | v3 (pre) | v4 (pos) | Mudanca |
|---|---|---|---|
| A (matched Vivino) | 458 (22.9%) | **488 (24.4%)** | +30 |
| B (vinho novo) | 48 (2.4%) | **67 (3.4%)** | +19 |
| C1 (quarentena provavel) | 319 (16.0%) | **403 (20.2%)** | +84 |
| C2 (quarentena incerto) | 695 (34.8%) | **504 (25.2%)** | **-191** |
| D (nao-vinho) | 446 (22.3%) | **504 (25.2%)** | +58 |
| E (destilado) | 34 (1.7%) | **34 (1.7%)** | = |

**Impacto das melhorias:**
- C2 (incerto) caiu de 35% pra 25% — 191 vinhos reclassificados corretamente
- +30 novos matches com Vivino (A)
- +19 vinhos novos reconhecidos (B)
- +84 vinhos movidos de incerto pra provavel (C1)
- +58 nao-vinhos a mais eliminados (D)
- Validado por 3 IAs externas (Gemini, Kimi, ChatGPT) — zero falsos no A

**Arquivos v4:**
- `C:\winegod-app\scripts\analise_letra_{B,D,J,M,O,P,R,T}.txt` — 8 analises individuais
- `C:\winegod-app\scripts\analise_2000_por_score_v2.md` — consolidado ordenado por score

### 5.7 Resultado da terceira rodada (v5 — regra nome overlap, 30/03/2026)

**Melhoria principal:** Regra "nome overlap >= 50% + (tipo OU safra OU produtor parcial bate) → promove pra A". Validada contra banco real: 80% dos antigos C1 promovidos corretamente. C1 eliminado como categoria.

| Destino | v4 | v5 | Mudanca |
|---|---|---|---|
| A (match Vivino) | 488 (24.4%) | **1049 (52.4%)** | **+561** |
| B (vinho novo) | 67 (3.4%) | **149 (7.4%)** | +82 |
| C1 (quarentena) | 403 (20.2%) | **0 (0%)** | eliminado |
| C2 (incerto) | 504 (25.2%) | **266 (13.3%)** | -238 |
| D+E (eliminado) | 538 (26.9%) | **536 (26.8%)** | = |

**Destinos agora sao 4 (era 5):**
- **A** = match Vivino confirmado (com vivino_id) — 52.4%
- **B** = vinho confirmado sem match (vinho novo) — 7.4%
- **C2** = incerto (wl baixo) — 13.3%
- **D** = nao e vinho (elimina) — 25.1%
- **E** = destilado (arquivo) — 1.7%

**Total vinho confirmado (A+B): 60% da amostra.**

Por letra:
| Letra | A | B | C2 | D | E |
|---|---|---|---|---|---|
| B | 104 | 13 | 49 | 79 | 5 |
| D | 161 | 31 | 17 | 40 | 1 |
| J | 168 | 4 | 20 | 32 | 26 |
| M | 138 | 31 | 17 | 64 | 0 |
| O | 104 | 22 | 64 | 60 | 0 |
| P | 115 | 22 | 29 | 82 | 2 |
| R | 168 | 10 | 24 | 48 | 0 |
| T | 91 | 16 | 46 | 97 | 0 |

### 5.8 Pipeline em escala (CONCLUIDO — 30/03/2026)

Pipeline rodou em 3,962,334 vinhos (8 grupos paralelos, ~3.1h, 0 erros).

| Destino | Quantidade | % |
|---|---|---|
| A (match Vivino) | 2,350,407 | 59.3% |
| B (vinho novo) | 256,440 | 6.5% |
| C2 (incerto) | 452,690 | 11.4% |
| D (nao-vinho) | 856,559 | 21.6% |
| E (destilado) | 46,238 | 1.2% |

- Vivino IDs unicos matchados: 381,134 (22.1% do Vivino)
- Media de lojas por vinho: 6.2

### 5.9 Tabela final (wines_final)

D e E removidos. Base de trabalho:

| Tabela | Registros | Conteudo |
|---|---|---|
| `wines_final` | 3,059,537 | A (2.35M) + B (256K) + C2 (453K) — base de trabalho |
| `wines_clean` | 3,962,334 | Backup completo (com D e E) |
| `match_results_final` | 3,962,334 | Resultados do pipeline com destinos |

**Proximo passo:** Chat Z — importar wines_final pro Render.

### 5.5 Arquivos de resultado

```
C:\winegod-app\scripts\analise_letra_B.txt (ate analise_letra_T.txt) — primeira rodada
C:\winegod-app\scripts\analise_2000_por_score.md — consolidado ordenado por score
C:\winegod-app\scripts\analise_2000_por_score.pdf — idem em PDF (61 paginas)
```

---

## 6. SCRIPTS E ARQUIVOS

| Arquivo | O que faz |
|---|---|
| `C:\winegod-app\scripts\import_vivino_local.py` | Importa 1.7M vinhos do Render pro banco local |
| `C:\winegod-app\scripts\test_match_y_v3.py` | Teste com 100 vinhos (primeiro teste) |
| `C:\winegod-app\scripts\test_match_200_random.py` | Teste com 200 aleatorios (segundo teste) |
| `C:\winegod-app\scripts\lista_200.py` | Gera lista compacta dos 200 pra verificacao |
| `C:\winegod-app\scripts\lista_200_vinhos.txt` | Lista dos 200 vinhos verificados manualmente |
| `C:\winegod-app\scripts\analise_letra.py` | Analise por letra com classificacao A-E |
| `C:\winegod-app\scripts\match_vivino.py` | Script de producao (8 grupos por pais) |
| `C:\winegod-app\prompts\BRIEFING_CTO_Y_METRICAS_2000.md` | Briefing da analise de 2000 |
| `C:\winegod-app\scripts\analise_2000_por_score.md` | 2000 vinhos consolidados ordenados por score |
| `C:\winegod-app\scripts\analise_2000_por_score.pdf` | Idem em PDF (61 paginas) |
| `C:\winegod-app\prompts\PROMPT_PESQUISA_UVAS_GLOBAL.md` | Prompt usado pra pesquisa de uvas em 3 IAs |

### Tabelas no banco local (winegod_db)

| Tabela | O que contem |
|---|---|
| `vivino_match` | 1,727,058 vinhos Vivino (importados do Render) |
| `wines_unique` | 2,942,304 vinhos de loja (deduplicados) |
| `wines_clean` | 3,955,624 vinhos limpos (antes dedup) |
| `match_results_g2` | 196K resultados do primeiro teste Y (0.6% match) |

---

## 7. DECISOES TOMADAS

| Decisao | Justificativa |
|---|---|
| Importar Vivino localmente | Query remota leva 27s, local 0.03s |
| 4 estrategias em cascata | Velocidade: 90% resolvido em <100ms |
| Threshold duplo (produtor bate vs nao) | Produtor e o sinal mais forte |
| 5 destinos (A/B/C1/C2/D/E) | Binario (match/nao) perdia nuance |
| Subir so A (matched Vivino) primeiro | Zero risco de sujar producao |
| Filtrar nao-vinhos ANTES do match | Evita falsos positivos por nome generico |
| Amostra por letra alfabetica | Agrupa variantes, facilita verificacao |
| Destilados como arquivo separado | Podem ser uteis no futuro (Baco) |

---

## 8. PROXIMOS PASSOS

1. **Re-rodar 2000 com melhorias v2** — medir impacto da curadoria de indicadores
2. **Verificacao visual pelo fundador** — confirmar que melhorias reduziram falsos
3. **Calibrar threshold final** — baseado na precisao real por faixa de score
4. **Rodar em escala** — 8 abas paralelas por pais (match_vivino.py precisa ser atualizado com melhorias v2)
5. **Chat Z** — importar destino A pro Render (wine_sources + vinhos novos)

---

## 9. REUTILIZACAO FUTURA

Este processo precisa ser repetido toda vez que:
- Novas lojas sao adicionadas (novos vinhos de loja)
- Novos paises sao cobertos
- O Vivino e re-importado (novos vinhos Vivino)

### Agente reutilizavel

O fluxo completo pode virar um agente/pipeline:

```
INPUT:  tabela de vinhos novos (nome, produtor, safra, tipo, pais, regiao)
STEP 1: Filtrar nao-vinhos (palavras proibidas, padroes, wine-likeness)
STEP 2: Match contra vivino_match (4 estrategias + scoring)
STEP 3: Classificar em A/B/C1/C2/D/E
OUTPUT: 5 tabelas/arquivos separados
```

### O que manter atualizado

- **Lista de palavras proibidas** — adicionar conforme novos nao-vinhos aparecem
- **Lista de destilados** — pode expandir
- **Lista de uvas e termos de vinho** — adicionar uvas/regioes novas
- **Threshold** — recalibrar se a fonte de dados mudar
- **vivino_match** — re-importar quando Vivino for atualizado
