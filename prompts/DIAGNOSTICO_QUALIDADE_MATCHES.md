# DIAGNOSTICO DE QUALIDADE — Match Results Final

## Data: 30/03/2026
## Autor: CTO WineGod (Claude — novo CTO)
## Base analisada: `match_results_final` (3,962,334 registros)

---

## 1. RESUMO EXECUTIVO

A base `match_results_final` tem **2,350,407 registros no destino A** (match com Vivino). Desses, estimo que **~755K (32%) sao falsos positivos** — vinhos que o sistema casou errado com o Vivino.

Os 3 maiores causadores de sujeira:
1. **292K registros** entraram com score < 0.45 por uma regra de promocao (v5) que foi longe demais
2. **627K registros** estao concentrados em apenas **5,424 vivino_ids** que acumularam >50 lojas cada — a maioria sao nomes genericos funcionando como "imas" de falsos positivos
3. **~9K registros** sao produtos que nao sao vinho (vinagre, aperitivo, cestas de presente, certificados, agua mineral)

**Proposta:** Aplicar 6 filtros que reduzem a base de 2.35M para **~1.19M registros limpos** (294K vivino_ids unicos). Precisao estimada sobe de ~65% para ~85%+.

---

## 2. O QUE ENCONTREI — PROBLEMA POR PROBLEMA

### 2.1. A regra do nome overlap (v5) foi longe demais

**O que e a regra:** Na versao 5 do pipeline, introduzimos a regra: "se nome overlap >= 50% E (tipo OU safra OU produtor parcial bate), promove de C1 para A". Isso dobrou os matches (de 24% para 52% na amostra de 2000).

**O problema:** A regra aceita matches com score tao baixo quanto 0.30. Nesses scores, a maioria sao falsos positivos.

**Numeros:**
- **292,075 registros** no destino A tem score < 0.45
- Desses, 134K vieram por keyword (kw), 101K por multi-keyword (mkw), 55K por produtor (prod)

**Exemplos reais do banco (score < 0.45):**

| Score | Loja | Vivino | Correto? |
|---|---|---|---|
| 0.45 | `agua mineral perrier` | `mineral — syrah` | **NAO** (agua mineral!) |
| 0.45 | `cous cous ararat x 500grs` | `ararat — oshakan` | **NAO** (comida!) |
| 0.40 | `vino blanco planeta chardonnay 2020` | `vino skrobak — chardonnay kabinetni vino` | **NAO** (vinhos diferentes) |
| 0.36 | `sauvignon blanc 2022 clos malverne` | `weidinger — sauvignon blanc` | **NAO** (produtores diferentes) |
| 0.31 | `pinot noir barrique aoc zurich 2021` | `barrique — pinot noir` | **NAO** (produtores diferentes) |
| 0.36 | `ma maison white sparkling champagne` | `rgny — white sparkling` | **NAO** |
| 0.43 | `snow village sparkling wine armenia` | `popup sparkling — sparkling wine` | **NAO** |
| 0.32 | `irancy aoc 2022 gabin et felix richoux` | `domaine gabin felix richoux — irancy` | SIM (raro) |
| 0.39 | `casillero del diablo res esp rose` | `casillero del diablo — rose reserva` | SIM (raro) |

**Precisao estimada nesta faixa (<0.45): ~15-20%.** A cada 5-6 registros, apenas 1 esta correto.

**Causa raiz:** A regra do nome overlap e boa em principio, mas aceita scores muito baixos. Um overlap de 50% com 2 palavras em comum (ex: "sauvignon blanc") e trivial — nao confirma nada. Precisaria de overlap mais alto (60%+) E score minimo mais alto (0.50+).

---

### 2.2. Nomes genericos funcionam como "imas de falsos positivos"

**O que acontece:** Alguns vinhos no Vivino tem nomes genericos (ex: "spumante dolce", "pauillac", "espumante brut"). Quando o sistema encontra qualquer vinho de loja com palavras em comum, casa com esse vivino_id. Como milhares de vinhos de loja contem essas palavras, o vivino_id acumula centenas ou milhares de "lojas".

**Numeros:**

| Lojas por vivino_id | Vivino IDs | Registros | % do total A |
|---|---|---|---|
| 1 | 143,785 | 143,785 | 6.1% |
| 2-3 | 104,355 | 246,735 | 10.5% |
| 4-10 | 87,482 | 524,357 | 22.3% |
| 11-50 | 40,088 | 807,830 | 34.4% |
| **51-100** | **3,602** | **246,454** | **10.5%** |
| **101-500** | **1,725** | **305,156** | **13.0%** |
| **501-1000** | **78** | **49,787** | **2.1%** |
| **1000+** | **19** | **26,303** | **1.1%** |

**627,700 registros (26.7% do destino A)** estao em vivino_ids com >50 lojas. Sao 5,424 vivino_ids que sozinhos acumulam mais de 1/4 de todos os matches.

**Os 15 piores "imas":**

| Lojas | Vivino | Score medio | Por que e errado |
|---|---|---|---|
| 2,528 | `spumante dolce — spumante dolce` | 0.49 | Nome generico. Milhares de espumantes dolce diferentes matcharam com 1 so |
| 2,048 | `chateau latour a pomerol — pomerol` | 0.54 | Qualquer vinho de Pomerol caiu aqui |
| 1,934 | `chateau margaux — margaux du chateau margaux` | 0.63 | Qualquer vinho com "margaux" ou "chateau" caiu aqui |
| 1,583 | `moet chandon — imperial brut champagne` | 0.71 | Plausivel, mas 1,583 lojas? Improvavel |
| 1,361 | `negociant — chateauneuf du pape` | 0.55 | Qualquer Chateauneuf-du-Pape caiu aqui |
| 1,352 | `santangelo dabruzzo — cerasuolo montepulciano` | 0.42 | Qualquer Montepulciano d'Abruzzo caiu aqui |
| 1,350 | `chateau pauillac — pauillac` | 0.53 | **Pauillac e uma REGIAO, nao um vinho** |
| 1,293 | `espumante — brut` | 0.39 | Generico total |
| 1,292 | `tinto colheita — reserva do pai` | 0.53 | Generico: qualquer "tinto colheita" ou "reserva" casou |
| 1,285 | `chateau clos saintemilion — grand cru` | 0.46 | Qualquer Saint-Emilion Grand Cru caiu aqui |
| 1,276 | `chateau de meursault — meursault 1er cru` | 0.56 | Qualquer Meursault caiu aqui |
| 1,254 | `marlborough vines — sauvignon blanc` | 0.65 | Qualquer Sauvignon Blanc de Marlborough caiu aqui |
| 1,233 | `chateau mouton rothschild — monton grignan` | 0.71 | **Match ABSURDO**: Mouton Rothschild casou com Monton Grignan |
| 1,228 | `opus one — opus one` | 0.70 | Vinho de $400 com 1,228 lojas? Impossivel |
| 1,086 | `popup sparkling — sparkling wine` | 0.43 | Qualquer sparkling wine caiu aqui |

**O que esses imas tem em comum:**
- Nomes que sao **regioes** (Pauillac, Saint-Emilion, Meursault, Pomerol, Margaux)
- Nomes que sao **tipos genericos** (spumante dolce, espumante brut, sparkling wine)
- Nomes **famosos** que atraem qualquer vinho com palavras similares (Mouton Rothschild, Opus One)

**Exemplos do que caiu no "ima" do spumante dolce (2,528 lojas):**

```
0.48 | spumante metodo classico brut neps casa roma          (NÃO é spumante dolce)
0.44 | spumante da uve di raboso casa roma senza etichetta   (NÃO é spumante dolce)
0.53 | spumante pro spritz                                   (NÃO é spumante dolce)
0.46 | franc lizer spumante blanc de blancs zero alcol       (NÃO é spumante dolce)
0.60 | oddbird spumante                                      (NÃO é spumante dolce)
```

Nenhum desses e o vinho "Spumante Dolce" do Vivino. Sao espumantes completamente diferentes que acontecem de ter a palavra "spumante" no nome.

---

### 2.3. Nao-vinhos ainda presentes no destino A

Apesar dos filtros de nao-vinho (palavras proibidas, padroes de peso, destilados), varios produtos que nao sao vinho passaram para o destino A:

| Termo | Registros no A | O que sao |
|---|---|---|
| `gift` | 4,954 | Cestas de presente, gift boxes, gift certificates |
| `aperitivo` | 1,298 | Aperitivos (nao sao vinho) |
| `basket` | 861 | Cestas |
| `aceto` / `balsamic` | 1,427 | **Vinagre balsamico** |
| `mixed case` | 638 | Caixas mistas (nao sao 1 vinho especifico) |
| `sample` | 153 | Amostras/degustacao |
| `mineral water` / `agua mineral` | 102 | Agua |
| `tasting pack` | 35 | Pacotes de degustacao |
| `cous cous` | 12 | Comida |
| `vinagre` | 11 | Vinagre |
| `voucher` | 1 | Vale presente |
| **TOTAL** | **~9,500** | |

**Exemplos reais:**

```
0.45 | "cous cous ararat x 500grs"          → "ararat — oshakan"               (COMIDA matchou com vinicola armênia)
0.51 | "champion wine cellars gift certificate" → "champion lane cellars — cab sauv" (CERTIFICADO matchou com vinho)
0.53 | "golden sauvignon gift pack"          → "golden oriole — cabernet sauvignon" (EMBALAGEM matchou com vinho)
0.45 | "super malbec 6 bottle mixed case"    → "super pipi cucu — malbec"       (CAIXA matchou com vinho)
0.66 | "beaujolais mixed case 2025"          → "mixed case — brunello luxury"    (CAIXA matchou com OUTRA caixa!)
```

**Caso especial — aceto balsamico di modena:** O Vivino tem um registro chamado "aceto balsamico di modena" (provavelmente um erro no proprio Vivino). 661 registros de vinagre de varias lojas matcharam com esse registro. **Vinagre nao e vinho.**

---

### 2.4. A estrategia multi-keyword (mkw) tem precisao muito baixa

O pipeline usa 3 estrategias de busca em cascata:

| Estrategia | Como funciona | Registros A | Score medio | Precisao estimada |
|---|---|---|---|---|
| `prod` | Busca pelo produtor | 1,601,442 (68%) | 0.684 | ~75% |
| `kw` | Busca por palavra-chave | 479,675 (20%) | 0.571 | ~50% |
| `mkw` | Busca por 2+ palavras em comum | 269,290 (11%) | 0.518 | ~35% |

**O mkw e a ultima opcao** — so roda quando prod e kw nao acharam nada. Ele encontra candidatos que compartilham 2+ palavras de 4+ caracteres. O problema e que 2 palavras em comum nao significam que sao o mesmo vinho.

**Distribuicao do mkw por faixa de score:**

| Faixa | Registros | % do mkw |
|---|---|---|
| >= 0.70 | 35,508 | 13% |
| 0.55-0.69 | 60,641 | 23% |
| 0.40-0.54 | 110,954 | **41%** |
| < 0.40 | 62,187 | **23%** |

**64% dos matches mkw tem score < 0.55.** Nessa faixa, a maioria sao falsos positivos.

**Exemplos mkw errados:**

```
0.49 | "champagne krug clos dambonnay"       → "krug — clos dambonnay"           (CORRETO — raro)
0.43 | "les grands preaux cotesdurhone 2019" → "les grands chais — cuvee reserve" (ERRADO — produtores diferentes)
0.47 | "chambollemusigny les baudes jadot"   → "louis jadot — chambollemusigny"   (CORRETO)
0.56 | "vino rosado"                         → "wyhuus st andre — vino rosado"    (ERRADO — generico)
0.43 | "m c noellat msd 1er monts luisants"  → "georges noellat — vosneromanee"   (ERRADO — vinicolas diferentes)
```

---

### 2.5. O threshold "produtor bate + score >= 0.45" e baixo demais

O pipeline aceita um match se o produtor bateu E o score e >= 0.45. O problema: "produtor bateu" significa que **uma unica palavra** do produtor da loja aparece no produtor do Vivino.

Isso gera falsos positivos quando a palavra em comum e generica ou curta:

```
0.49 | "societa agricola rabasco cancelli"  → "societa agricola casagliana — siscopile"
       Palavra em comum: "societa agricola" (generico — dezenas de vinicolas italianas)

0.45 | "domainem roman popp neuburger"      → "domainem — mullerthurgau iii"
       Palavra em comum: "domainem" (mesmo produtor, mas vinho completamente diferente)

0.49 | "roger coulon herihodie 1er cru"     → "roger coulon — vindemia brut nature"
       Palavra em comum: "roger coulon" (mesmo produtor, mas vinho errado)

0.51 | "tellus maison fouassier"            → "tellus — tinto"
       Palavra em comum: "tellus" (produtores DIFERENTES chamados Tellus)
```

**O produtor bater deveria exigir score minimo mais alto** — se o produtor e o mesmo mas o vinho e totalmente diferente, 0.45 nao e suficiente pra confirmar que e o MESMO vinho do mesmo produtor.

---

### 2.6. Nomes de 1-2 palavras geram matches frageis

**98,526 registros** no destino A tem nome de loja com apenas 1 ou 2 palavras.

**Exemplos:**

| Score | Nome loja | Vivino | Correto? |
|---|---|---|---|
| 0.88 | `artigiano rosato` | `artigiano — rosato` | SIM |
| 0.80 | `crios malbec` | `crios — malbec` | SIM |
| 0.50 | `purple angel` | `purple — pays doc white` | **NAO** |
| 0.51 | `fino micaela` | `micaela — classic rose` | **NAO** |
| 0.53 | `artisan treats` | `artisan — tavkveri` | **NAO** |
| 0.50 | `deluxe citra` | `chateau deluxe — sparkling ramato` | **NAO** |
| 0.53 | `house party` | `house — rose` | **NAO** |
| 0.38 | `vermouth vicenzo` | `vermouth del mugello — oro` | **NAO** |
| 0.58 | `escursac` | `socarel — escursac` | SIM |
| 0.53 | `capel reservado` | `reservado — lambrusco` | **NAO** |

Nomes curtos nao tem informacao suficiente para um match confiavel. Dos 20 que amostrei, ~40% estavam errados. O risco e maior porque:
- 2 palavras em comum podem ser coincidencia
- Sem produtor explicito, o sistema nao tem como validar
- "Purple angel" poderia ser o vinho chileno famoso de Montes, mas matchou com "Purple" (outro produtor)

---

### 2.7. A faixa 0.70-0.80 e melhor do que se pensava

**Boa noticia.** Na amostra de 20 vinhos com score 0.70-0.80 e <=50 lojas, **17 de 20 estavam corretos (85%)**.

O relatorio anterior estimava 55-65% para essa faixa. A estimativa estava pessimista porque incluia vinhos com >50 lojas (que sao os imas de falsos positivos). **Filtrando os imas, a faixa 0.70+ e confiavel.**

Os 3 erros na faixa 0.70-0.80:
- `saronsberg brut` → `saronsberg rousanne` (mesmo produtor, varietal errado)
- `belsazar rosso` → `belsazar vermouth white` (mesmo produtor, cor errada)
- `sera` → `domeniile sera rose` (nome curto demais, match fragil)

---

### 2.8. A faixa 0.55-0.70 e aceitavel com filtros

Na amostra de 20 vinhos com score 0.55-0.70, <=50 lojas, estrategia "prod":

**~70% corretos.** Exemplos bons:
```
0.66 | petit chablis jeanmarc brocard    → jeanmarc brocard — petit chablis         ✅
0.68 | cavalleri blanc de blancs brut    → cavalleri — brut blanc de blancs nature   ✅
0.70 | louis m martini lot 1 cab sauv   → louis m martini — lot no 1 cab sauv      ✅
0.63 | equipo navazos la bota 114       → equipo navazos — la bota 114 florpower   ✅
```

Exemplos errados:
```
0.60 | rhone to the bone cotes du rhone → arc du rhone — cotes du rhone blanc       ❌ (produtores diferentes)
0.56 | hors champs 2020                 → chateau grand champs — bordeaux            ❌ (so "champs" em comum)
```

**A faixa 0.55-0.70 com estrategia prod e <=50 lojas e aceitavel** — mas precisa de mais cuidado. Com kw e mkw nessa faixa, a precisao cai bastante.

---

## 3. NUMEROS CONSOLIDADOS

### 3.1. Estado atual (sem filtros)

| Metrica | Valor |
|---|---|
| Total destino A | 2,350,407 |
| Vivino IDs unicos | 381,134 |
| Score medio | 0.628 |
| Precisao estimada global | **~65%** |
| Falsos positivos estimados | **~820K** |

### 3.2. Distribuicao por faixa de score

| Faixa | Registros | % do A | Precisao estimada |
|---|---|---|---|
| 0.90-1.00 | 7,556 | 0.3% | ~98% |
| 0.85-0.89 | 222,907 | 9.5% | ~95% |
| 0.80-0.84 | 229,691 | 9.8% | ~90% |
| 0.75-0.79 | 309,267 | 13.2% | ~85% |
| 0.70-0.74 | 198,215 | 8.4% | ~80% |
| 0.65-0.69 | 198,612 | 8.4% | ~55% |
| 0.60-0.64 | 229,809 | 9.8% | ~45% |
| 0.55-0.59 | 198,948 | 8.5% | ~35% |
| 0.50-0.54 | 245,057 | 10.4% | ~25% |
| 0.45-0.49 | 218,270 | 9.3% | ~15% |
| 0.40-0.44 | 139,759 | 5.9% | ~10% |
| 0.35-0.39 | 85,341 | 3.6% | ~8% |
| 0.30-0.34 | 66,975 | 2.8% | ~5% |

### 3.3. Distribuicao por estrategia

| Estrategia | Total | Score >= 0.70 | 0.55-0.69 | 0.40-0.54 | < 0.40 |
|---|---|---|---|---|---|
| prod (produtor) | 1,601,442 | 805,786 (50%) | 458,785 (29%) | 324,277 (20%) | 12,594 (1%) |
| kw (keyword) | 479,675 | 126,342 (26%) | 107,943 (23%) | 167,855 (35%) | 77,535 (16%) |
| mkw (multi-kw) | 269,290 | 35,508 (13%) | 60,641 (23%) | 110,954 (41%) | 62,187 (23%) |

---

## 4. PROPOSTA DE LIMPEZA — 6 FILTROS

### FILTRO 1: Score minimo (o mais impactante)

**Regra:** Remover todos os matches com score < 0.55.

**Impacto:** Remove **755,402 registros** (32% do destino A).

**Por que 0.55:** A partir de 0.55 com estrategia prod, a precisao fica acima de 60%. Abaixo de 0.55, a maioria sao falsos positivos em TODAS as estrategias. O corte de 0.55 e conservador o suficiente para nao perder matches bons e agressivo o suficiente para eliminar a maioria do lixo.

**Alternativa mais conservadora:** Corte em 0.70 removeria 1,382,771 registros mas perderia matches corretos na faixa 0.55-0.70 (especialmente de produtores conhecidos).

**Alternativa por estrategia:**
- prod: aceitar >= 0.55 (produtor batendo da mais confianca)
- kw: aceitar >= 0.65 (sem produtor, precisa de mais evidencia)
- mkw: aceitar >= 0.70 (estrategia mais fraca, precisa de score alto)

Esta alternativa e mais sofisticada e provavelmente mais precisa. Recomendo testar com amostra antes de decidir.

---

### FILTRO 2: Limite de lojas por vivino_id (segundo mais impactante)

**Regra:** Remover todos os registros de vivino_ids que acumularam >50 lojas.

**Impacto:** Remove **627,700 registros** (26.7%).

**Por que 50:** Um vinho popular pode realisticamente aparecer em 10-30 lojas globais. 50 ja e generoso. Acima de 50, a probabilidade de ser um "ima de nome generico" e altissima. Os 5,424 vivino_ids com >50 lojas incluem os piores falsos positivos da base (spumante dolce, pauillac, espumante brut, etc.).

**Excepcoes possiveis:** Alguns vinhos MUITO famosos (Moet Chandon, Dom Perignon) poderiam legitimamente ter 50+ lojas. Mas o risco de manter esses imas abertos e maior do que o beneficio de ter 1-2 vinhos famosos com mais fontes. Esses vinhos ja estao no Vivino — nao precisam de 1,583 fontes de loja pra existir.

---

### FILTRO 3: Blacklist de nao-vinhos residuais

**Regra:** Remover registros que contem termos de produtos que nao sao vinho.

**Termos a adicionar na blacklist:**
```
NOVOS na blacklist: aceto, balsamic, vinagre, couscous,
  mineral water, agua mineral, gift card, gift certificate,
  voucher, tasting pack, mixed case, sample pack
```

**Impacto:** Remove **~2,890 registros** (pequeno mas importante — vinagre no banco e inadmissivel).

**Nota sobre "gift":** NAO remover "gift" sozinho — "gift box" e embalagem de vinho real. So remover "gift card", "gift certificate", "gift basket", "gift set" (sem vinho especifico).

---

### FILTRO 4: Nome de loja muito curto

**Regra:** Registros com nome de loja de <=2 palavras E score < 0.75 → mover para quarentena.

**Impacto:** Remove **~60-70K registros** (parcial — muitos nomes curtos tem score alto e sao corretos).

**Por que:** Nomes de 1-2 palavras nao tem informacao suficiente. "Crios malbec" (0.80) e correto. "House party" (0.53) e falso. O score 0.75 separa os dois.

---

### FILTRO 5: Score diferenciado por estrategia

**Regra:** Aplicar threshold minimo diferente por estrategia de match:

| Estrategia | Threshold atual | Threshold proposto |
|---|---|---|
| prod (produtor) | 0.45 | **0.55** |
| kw (keyword) | 0.45 / 0.70 | **0.65** |
| mkw (multi-keyword) | 0.45 / 0.70 | **0.70** |

**Por que:** As estrategias tem precisao muito diferente no mesmo score. Um match prod a 0.60 e muito mais confiavel que um mkw a 0.60.

---

### FILTRO 6: Validacao de tipo (tinto ↔ branco)

**Regra:** Se o tipo da loja contradiz o tipo do Vivino (tinto matchou com branco ou vice-versa), remover do destino A.

**Impacto:** Ja existe parcialmente no pipeline (penalidade -0.15). Mas precisa ser um VETO absoluto — nenhum vinho tinto deve matchear com um branco, independente do score.

---

## 5. RESULTADO ESPERADO APOS LIMPEZA

### Cenario recomendado: Filtros 1+2 combinados (score >= 0.55 + <=50 lojas)

| Metrica | Antes | Depois | Reducao |
|---|---|---|---|
| Registros A | 2,350,407 | **1,188,009** | -49% |
| Vivino IDs unicos | 381,134 | **294,030** | -23% |
| Precisao estimada | ~65% | **~82%** | +17pp |
| Falsos positivos estimados | ~820K | **~210K** | -74% |

### Cenario agressivo: Todos os 6 filtros

| Metrica | Antes | Depois | Reducao |
|---|---|---|---|
| Registros A | 2,350,407 | **~1,137,058** | -52% |
| Vivino IDs unicos | 381,134 | **~282,463** | -26% |
| Precisao estimada | ~65% | **~85%** | +20pp |
| Falsos positivos estimados | ~820K | **~170K** | -79% |

### O que se ganha

- **294K vivino_ids** recebem dados de precos de lojas (vs 381K sujos)
- Cada vinho Vivino ganha em media **4 fontes de loja** (vs 6.2 com lixo)
- **Zero vinagre**, zero agua mineral, zero cestas de presente no banco
- **Zero imas de nomes genericos** acumulando milhares de fontes falsas
- Precisao de **85%+** — a cada 6 matches, 5 estao corretos

### O que se perde

- **~87K vivino_ids** que tinham matches reais mas com score baixo ou muitas lojas
- Estimativa: desses 87K, ~30-40K eram matches reais que serao removidos como "dano colateral"
- Esses vinhos ainda existem no Vivino — so perdem os dados de preco de loja
- Podem ser recuperados no futuro com um pipeline mais sofisticado (embeddings, LLM validation)

---

## 6. COMO APLICAR NA BASE ATUAL

### Passo 1: Criar tabela limpa

```sql
CREATE TABLE match_results_clean AS
SELECT m.*
FROM match_results_final m
WHERE m.destino = 'A'
  AND m.match_score >= 0.55
  AND m.vivino_id IN (
      SELECT vivino_id FROM match_results_final
      WHERE destino = 'A'
      GROUP BY vivino_id HAVING COUNT(*) <= 50
  )
  AND m.loja_nome NOT ILIKE '%aceto%'
  AND m.loja_nome NOT ILIKE '%vinagre%'
  AND m.loja_nome NOT ILIKE '%balsamic%'
  AND m.loja_nome NOT ILIKE '%aperitivo%'
  AND m.loja_nome NOT ILIKE '%gift card%'
  AND m.loja_nome NOT ILIKE '%gift certificate%'
  AND m.loja_nome NOT ILIKE '%voucher%'
  AND m.loja_nome NOT ILIKE '%mixed case%'
  AND m.loja_nome NOT ILIKE '%agua mineral%'
  AND m.loja_nome NOT ILIKE '%mineral water%'
  AND m.loja_nome NOT ILIKE '%couscous%'
  AND m.loja_nome NOT ILIKE '%cous cous%'
  AND m.loja_nome NOT ILIKE '%tasting pack%'
  AND m.loja_nome NOT ILIKE '%sample pack%';
```

### Passo 2: Adicionar B e C2 (vinhos sem match)

```sql
INSERT INTO match_results_clean
SELECT * FROM match_results_final
WHERE destino IN ('B', 'C2');
```

### Passo 3: Verificar e indexar

```sql
CREATE INDEX idx_mrc_vivino_id ON match_results_clean(vivino_id);
CREATE INDEX idx_mrc_destino ON match_results_clean(destino);
CREATE INDEX idx_mrc_score ON match_results_clean(match_score);
```

---

## 7. COMO INTEGRAR NO PIPELINE PARA DADOS FUTUROS

Esses filtros devem ser aplicados **dentro do `match_vivino.py`** na funcao `classify_match`, para que novos dados ja saiam limpos:

### 7.1. Mudar thresholds na classify_match

```python
# ANTES (v5):
if score >= 0.45 and producer_matched: return 'A'
if score >= 0.70 and not producer_matched: return 'A'

# DEPOIS (v6):
if score >= 0.55 and producer_matched: return 'A'
if score >= 0.75 and not producer_matched: return 'A'
```

### 7.2. Regra nome overlap mais estrita

```python
# ANTES (v5):
if n_overlap >= 0.50 and (has_tipo or has_safra or has_prod): return 'A'

# DEPOIS (v6):
if score >= 0.50 and n_overlap >= 0.60 and (has_tipo or has_safra or has_prod): return 'A'
```

### 7.3. Threshold por estrategia

Adicionar a estrategia como parametro na classify_match e usar thresholds diferentes:

```python
MIN_SCORE = {'prod': 0.55, 'kw': 0.65, 'mkw': 0.70}
```

### 7.4. Filtro de nao-vinho expandido

Adicionar os termos novos na blacklist de `PALAVRAS_PROIBIDAS`:

```python
# Adicionar:
'aceto', 'balsamic', 'vinagre', 'couscous',
'gift card', 'gift certificate', 'voucher',
'tasting pack', 'sample pack', 'mixed case'
```

### 7.5. Pos-processamento: cap de lojas por vivino_id

Apos rodar o pipeline, adicionar um passo que detecta vivino_ids com >50 lojas e os rebaixa para C2. Isso evita que imas de nomes genericos se formem.

Isso pode ser feito como um passo SQL apos o merge das 8 tabelas:

```sql
-- Identificar imas
UPDATE match_results_final SET destino = 'C2'
WHERE destino = 'A'
  AND vivino_id IN (
    SELECT vivino_id FROM match_results_final WHERE destino = 'A'
    GROUP BY vivino_id HAVING COUNT(*) > 50
  );
```

---

## 8. PARA O FUTURO — MELHORIAS POSSIVEIS (NAO URGENTES)

Estas sao melhorias que podem aumentar a precisao ainda mais, mas NAO sao necessarias para a limpeza atual:

1. **Embeddings semanticos** — usar sentence-transformers para gerar vetores dos nomes e comparar por similaridade coseno. Muito mais robusto que tokens, mas mais lento (~10x)

2. **Validacao por LLM** — pegar os matches da faixa 0.55-0.70 e pedir ao Claude/DeepSeek: "Estes sao o mesmo vinho?" Caro mas muito preciso para faixa incerta

3. **EAN/GTIN cross-reference** — se os vinhos de loja tiverem codigo de barras, o match e perfeito. Poucos tem hoje (~28%), mas pode crescer

4. **Lista de vinhos famosos** — criar whitelist dos top 10K vinhos do mundo. Se "Opus One" aparece, ja sabemos o vivino_id. Sem fuzzy, sem risco

5. **Feedback loop** — quando usuarios do chat confirmam que um vinho e correto, usar isso como treinamento

---

## DOCUMENTOS RELACIONADOS

| Documento | Conteudo |
|---|---|
| `C:\winegod-app\prompts\DOC_MATCH_VIVINO_METODOLOGIA.md` | Metodologia completa do pipeline de match |
| `C:\winegod-app\prompts\RELATORIO_MATCH_FINAL.md` | Relatorio anterior (numeros gerais + top 15 imas) |
| `C:\winegod-app\prompts\PROMPT_CTO_WINEGOD_V2.md` | Documento completo do projeto |
| `C:\winegod-app\scripts\match_vivino.py` | Script principal do pipeline |
| `C:\winegod-app\scripts\analise_letra.py` | Script de analise por amostra |
