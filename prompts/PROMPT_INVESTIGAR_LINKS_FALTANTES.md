# Investigacao: Por que vinhos de scraping nao tem links de loja no Render?

## INSTRUCAO

Voce vai INVESTIGAR e DIAGNOSTICAR um problema. NAO execute correcoes. Seu trabalho e:
1. Entender todo o contexto abaixo
2. Investigar no banco de dados onde os links se perdem
3. Propor solucoes detalhadas para outro chat/IA executar

---

## 1. COMO FUNCIONA O PIPELINE DE DADOS DO WINEGOD

### Fase 1 — Discovery (descoberta de lojas)

Uma IA descobriu **84,633 lojas de vinho** em 50 paises. Cada loja e um e-commerce real (ex: evino.com.br, wine.com, etc.). Essas lojas estao na tabela `lojas_scraping` no banco LOCAL.

### Fase 2 — Scraping (extracao de vinhos)

Pra cada loja, um scraper extraiu todos os vinhos que ela vende. Cada vinho extraido tem:
- Nome do vinho
- Preco
- Moeda
- **URL da pagina do produto na loja** (ex: https://www.evino.com.br/vinho-malbec-catena-123)

Os vinhos ficam nas tabelas `vinhos_XX` (por pais: `vinhos_br`, `vinhos_us`, etc. — 50 tabelas).
As **URLs de cada vinho em cada loja** ficam nas tabelas `vinhos_XX_fontes` (50 tabelas).

Resultado:
- **4,907,368 vinhos brutos** extraidos de lojas
- **~5.6M registros** em vinhos_XX_fontes (URLs com preco)
- Cobertura de 99.9% — praticamente todo vinho tem pelo menos 1 URL

**PRINCIPIO FUNDAMENTAL: Todo vinho neste pipeline veio de uma URL de uma loja. Se o vinho existe, a URL existe.**

### Fase 3 — Limpeza e deduplicacao

Os 4.9M vinhos brutos foram limpos e deduplicados:
- Remocao de nao-vinhos (agua, molho, etc.)
- Normalizacao de nomes
- Agrupamento de duplicatas

Resultado: **3,962,334 vinhos unicos** na tabela `wines_clean`.

**IMPORTANTE**: `wines_clean` tem dois campos criticos:
- `wines_clean.id` = ID PROPRIO (sequencial, 1 a 4,097,727)
- `wines_clean.pais_tabela` = pais de origem (ex: 'br', 'us')
- `wines_clean.id_original` = ID na tabela vinhos_XX de origem

A ponte entre `wines_clean` e as URLs originais e:
```
wines_clean.pais_tabela = 'br' AND wines_clean.id_original = 572556
    → vinhos_br_fontes WHERE vinho_id = 572556
    → URL: https://www.vinatobr.com/vinho-brasileiro-50, preco R$59
```

**ATENCAO**: `wines_clean.id` NAO e igual a `vinhos_XX.id`. Sao IDs de tabelas diferentes que se sobrepoe por acidente. SEMPRE usar `id_original` + `pais_tabela`.

### Fase 4 — Classificacao IA (Chat Y)

Cada vinho em `wines_clean` foi classificado por 7 IAs:
- **matched** (1,465,480): "esse vinho de loja e o MESMO que um vinho no Vivino"
- **new** (827,593): "esse vinho nao existe no Vivino, e um vinho novo"
- **not_wine** (1,039,952): nao e vinho (agua, destilado, acessorio)
- **duplicate** (350,281): duplicata de outro registro
- **spirit** (108,780): destilado
- **error** (169,136): erro de classificacao

Os resultados estao na tabela `y2_results`.

**DETALHE CRITICO sobre matched**: `y2_results.vivino_id` armazena o `wines.id` do Render (chave primaria), NAO o vivino_id real. Isso porque o matching foi feito contra `vivino_match`, onde `vivino_match.id = wines.id` do Render.

### Fase 5 — Import pro Render (Chat Z — o que fizemos)

Subimos os dados pro banco de producao (Render PostgreSQL):

**Fase 1 do import**: Para cada matched, criar `wine_source` (link vinho↔loja).
- O vinho Vivino JA existe no Render
- So criamos a conexao: "esse vinho Vivino e vendido nesta loja, por este preco, nesta URL"
- 1.46M matched = so 305K vivino_ids unicos (muitos vinhos de lojas diferentes casam com o mesmo Vivino)

**Fase 2 do import**: Para cada new, INSERT do vinho + wine_sources.
- Vinho novo nao existe no Render → inserir
- Depois criar wine_sources (links com lojas)
- 827K processados → ~779K wines inseridos

**Fase 3 do import**: Enriquecer vinhos existentes (preencher campos NULL).
- COALESCE: so preenche campos NULL, nunca sobrescreve

---

## 2. ESTADO ATUAL DO RENDER

```
Wines total:        2,506,441
  Vivino originais: 1,727,058
  Novos (scraping): 779,383

Stores:             19,881
Wine sources:       3,659,501
Wines com link:     1,009,261 (40%)
Wines SEM link:     1,497,180 (60%)
```

### Breakdown dos sem link

- **~1,422,000 Vivino puro**: Vinhos que vieram do Vivino e que NENHUMA loja scraped vende. Esses nao tem link e e esperado — nao foram scrapeados.
- **~88,000 novos (scraping)**: Vieram de lojas, TEM URL na base original, mas NAO tem wine_source no Render. **ESTE E O BUG.**
- **~305K matched**: 99.8% ja tem link. So ~500 faltam (edge cases).

---

## 3. O PROBLEMA: 88K vinhos de scraping SEM link

Esses 88K vinhos:
- Foram extraidos de uma loja real (TEM URL no vinhos_XX_fontes)
- Passaram pela limpeza (estao no wines_clean)
- Foram classificados como "new" (estao no y2_results)
- Foram inseridos no Render (existem na tabela wines)
- **MAS** nao tem nenhum wine_source (link com loja)

O link se perde em algum lugar entre o `vinhos_XX_fontes` e o `wine_sources` do Render.

---

## 4. O QUE VOCE PRECISA INVESTIGAR

### Investigacao 1: Rastrear 50 vinhos novos SEM link

Pegar 50 wines do Render que:
- NAO tem vivino_id (sao novos, de scraping)
- NAO tem nenhum wine_source

Pra cada um:
1. Buscar no Render: `wines.hash_dedup`
2. Buscar no LOCAL: `wines_clean WHERE hash_dedup = X` → pegar `id`, `pais_tabela`, `id_original`
3. Buscar no LOCAL: `vinhos_XX_fontes WHERE vinho_id = id_original` → a URL DEVE existir
4. Se a URL existe: por que nao foi criada como wine_source?
   - O dominio existe em `stores`?
   - O wine_id no Render bate com o esperado?
5. Se a URL NAO existe: por que? O vinho deveria ter vindo de uma loja.

### Investigacao 2: Verificar o script import_render_z.py

O script `C:\winegod-app\scripts\import_render_z.py` (Fase 2) processa os vinhos novos. Verificar:
1. A funcao `carregar_fontes_locais` carrega TODAS as fontes? Quantas?
2. Na Fase 2, quando um wine novo e inserido, o script busca fontes pro `clean_id` correto?
3. O `hash_to_fontes` mapeia corretamente o hash do wine inserido → fontes?
4. Se o INSERT do wine deu ON CONFLICT (hash duplicado), o wine_source NAO e criado? (isso seria o bug)

### Investigacao 3: Quantificar as categorias

Dos 88K novos sem link, classificar em:
- A) Tem fonte na base local, dominio tem loja no Render → **BUG no script** (deveria ter criado)
- B) Tem fonte na base local, dominio NAO tem loja → **Loja faltante** (precisa importar)
- C) NAO tem fonte na base local → **Bug no scraping** (deveria ter)
- D) NAO encontrado no wines_clean via hash_dedup → **Bug na insercao** (hash diferente)

---

## 5. HIPOTESES PROVAVEIS

### Hipotese 1: ON CONFLICT na Fase 2 pula wine_sources

Na Fase 2, o script faz:
```python
INSERT INTO wines ... ON CONFLICT (hash_dedup) DO NOTHING RETURNING id
```

Se o wine JA existe (hash duplicado), `RETURNING id` retorna NULL. O script so cria wine_sources quando recebe o id de volta. Se retornou NULL → nao cria wine_sources.

Isso significa: wines que foram inseridos na PRIMEIRA rodada (quando o mapeamento estava ERRADO) ja existem. Na segunda rodada (mapeamento correto), ON CONFLICT pula → nao cria sources.

**Se essa hipotese estiver correta**: Os 88K sao wines que foram inseridos na primeira rodada com fontes_map errado, e na segunda rodada o ON CONFLICT impediu a criacao dos sources corretos.

### Hipotese 2: check_exists_in_render absorve sem criar sources

Na Fase 2, antes de inserir, o script verifica se o vinho ja existe no Render por `produtor + nome`. Se encontra, incrementa `encontrados_render` e tenta criar wine_sources. Mas se o `fontes_map` nao tem fontes pro clean_id, nao cria nada.

### Hipotese 3: Erros de batch silenciosos

Na Fase 2 com workers, se um batch inteiro falha (ex: numeric overflow), TODOS os wines desse batch perdem seus sources. Os 33K erros da primeira rodada + 2.7K da segunda podem ter causado isso.

---

## 6. CONEXOES E TABELAS

### Banco LOCAL
```
host=localhost port=5432 dbname=winegod_db user=postgres password=postgres123
```

| Tabela | O que contem | Registros |
|---|---|---|
| `wines_clean` | Vinhos deduplicados | 3,962,334 |
| `y2_results` | Classificacao IA | 3,961,222 |
| `vivino_match` | Espelho Vivino (id = wines.id Render) | 1,727,058 |
| `vinhos_XX` | Vinhos por pais (50 tabelas) | ~4.85M |
| `vinhos_XX_fontes` | URLs+preco por pais (50 tabelas) | ~5.6M |
| `lojas_scraping` | Lojas descobertas | 86,089 |

### Banco RENDER
```
<DATABASE_URL_FROM_ENV>
```

| Tabela | O que contem | Registros |
|---|---|---|
| `wines` | Todos os vinhos | 2,506,441 |
| `stores` | Lojas | 19,881 |
| `wine_sources` | Links vinho↔loja | 3,659,501 |

### Script
```
C:\winegod-app\scripts\import_render_z.py
```

---

## 7. COMO VERIFICAR O MAPEAMENTO CORRETO

```sql
-- No LOCAL: confirmar wines_clean → vinhos_XX_fontes
SELECT wc.id as clean_id, wc.pais_tabela, wc.id_original,
       f.url_original, f.preco, f.moeda
FROM wines_clean wc
JOIN vinhos_br_fontes f ON f.vinho_id = wc.id_original
WHERE wc.pais_tabela = 'br'
LIMIT 5;

-- No RENDER: wines sem link que sao novos (scraping)
SELECT w.id, w.nome, w.hash_dedup
FROM wines w
LEFT JOIN wine_sources ws ON ws.wine_id = w.id
WHERE ws.id IS NULL AND w.vivino_id IS NULL
LIMIT 20;
```

---

## 8. EVIDENCIA OPERACIONAL (dados reais coletados)

### 8a. Estado atual do Render (06/abril/2026)

```
wines total:        2,506,441
wines vivino:       1,727,058
wines novos:        779,383
stores:             19,881
wine_sources:       3,659,501
wines com link:     1,008,941
wines SEM link:     1,497,500
```

### 8b. Historico de execucoes do script

**Rodada 1 (05/abril — versao com mapeamento ERRADO):**
- Fase 1: 1,059,055 processados | 52,829 sources | 731,176 sem fontes | 453,014 sem loja
- Fase 2 (versao lenta, 2/seg): cancelada em 3,000 | 2,747 criados
- Fase 2 (versao batch, 4 workers): 827,593 processados | 58,595 criados | 29,370 existentes | 705,730 dup_hash | 40,585 sources | 33,898 erros
- Fase 3: 618,738 processados | 330,478 atualizados

**Rodada 2 (05/abril — correcao sanitizacao):**
- Fase 2: 827,593 processados | 1,940 criados | 547,843 existentes | 275,034 dup_hash | 4,461 sources | 2,776 erros

**Rodada 3 (06/abril — DELETE dos errados + mapeamento corrigido + lojas importadas):**
- DELETE: 1,269,433 wine_sources deletados (descoberto_em >= '2026-04-05')
- Lojas importadas: 7,101 novas (4 Amazon)
- Fase 1 (score >= 0.0): 1,465,480 processados | sem_vivino=0 | sem_fontes=1,933 | sem_loja=0 | sources reportados=27,763 (rowcount nao confiavel com ON CONFLICT)
- Fase 2 (4 workers): completada | erros de encoding + varchar

### 8c. Versao atual do script (a que rodou na Rodada 3)

O script `C:\winegod-app\scripts\import_render_z.py` usa:
- **Fase 2 batch**: `_processar_batch_fase2()` com workers paralelos
- **INSERT wines**: `execute_values` com ON CONFLICT (hash_dedup) DO NOTHING
- **Busca IDs**: Depois do INSERT, busca wines por hash_dedup com `WHERE hash_dedup = ANY(%s)`
- **Cria sources**: So pra wines encontrados no lookup de hash

**PONTO CRITICO no codigo (linhas 451-467):**
```python
# Buscar IDs dos wines recem-inseridos
if hash_to_fontes or hash_to_prod:
    all_hashes = list(set(list(hash_to_fontes.keys()) + list(hash_to_prod.keys())))
    for i in range(0, len(all_hashes), 1000):
        chunk = all_hashes[i:i+1000]
        r_cur.execute(
            "SELECT id, hash_dedup FROM wines WHERE hash_dedup = ANY(%s)",
            (chunk,)
        )
        for wid, hd in r_cur.fetchall():
            fontes_for_wine = hash_to_fontes.get(hd, [])
            # SÓ CRIA SOURCE SE O HASH ESTIVER NO hash_to_fontes
```

O `hash_to_fontes` so contem hashes de wines que o script TENTOU inserir (nao os que foram encontrados por `check_exists_in_render`). Se o wine foi encontrado como "ja existente" por produtor+nome, ele vai pra `existing_sources` via a funcao `add_wine_sources`. MAS `existing_sources` tambem depende de `fontes_map.get(clean_id)` retornar fontes.

### 8d. PROVA DO BUG — 10 vinhos sem link rastreados

Todos os 10 vinhos abaixo estao no Render SEM wine_source, mas TEM URL e TEM loja:

```
wine_id=1803635 | Georges Descombes Regnie Vieilles Vignes
  LOCAL: clean_id=178588 pais=us id_orig=899674
  FONTE: https://www.sommselect.com/products/somm2309-... preco=39.0 USD
  LOJA: sommselect.com → EXISTE no Render ✅
  WINE_SOURCE: NAO EXISTE ❌

wine_id=2336968 | Super Τροφές Σπιρουλίνα
  LOCAL: clean_id=3459999 pais=gr id_orig=11642
  FONTE: https://polykarpos-bio.gr/... preco=10.9 EUR
  LOJA: polykarpos-bio.gr → EXISTE no Render ✅
  WINE_SOURCE: NAO EXISTE ❌

wine_id=1921444 | Chateau Haut Condissas Prestige Medoc 2009
  LOCAL: clean_id=3045641 pais=ru id_orig=41744
  FONTE: https://vincart.ru/product/... preco=None RUB
  LOJA: vincart.ru → EXISTE no Render ✅
  WINE_SOURCE: NAO EXISTE ❌

wine_id=1956490 | Starward Old Fashioned
  LOCAL: clean_id=4008419 pais=nl id_orig=180894
  FONTE: https://bottlebusiness.nl/winkel/... preco=18.23 EUR
  LOJA: bottlebusiness.nl → EXISTE no Render ✅
  WINE_SOURCE: NAO EXISTE ❌

wine_id=2314948 | Yamadaichi One
  LOCAL: clean_id=3998346 pais=nl id_orig=183139
  FONTE: https://daansdrinks.com/products/... preco=40.0 EUR
  LOJA: daansdrinks.com → EXISTE no Render ✅
  WINE_SOURCE: NAO EXISTE ❌

wine_id=2491852 | Ron de Viejo de Caldas Gran Reserva 15 Anos
  LOCAL: clean_id=1623583 pais=co id_orig=45177
  FONTE: https://verbenalicores.com/producto/... preco=127900.0 COP
  LOJA: verbenalicores.com → EXISTE no Render ✅
  WINE_SOURCE: NAO EXISTE ❌

wine_id=2064219 | Familia Geisse Cave Amadeu Brut NV
  LOCAL: clean_id=3143673 pais=us id_orig=161872
  FONTE: https://accent.wine/products/... preco=27.0 USD
  LOJA: accent.wine → EXISTE no Render ✅
  WINE_SOURCE: NAO EXISTE ❌

wine_id=1956172 | St. Laurent
  LOCAL: clean_id=80920 pais=at id_orig=72596
  FONTE: https://www.selektion-burgenland.at/... preco=10.9 EUR
  LOJA: selektion-burgenland.at → EXISTE no Render ✅
  WINE_SOURCE: NAO EXISTE ❌

wine_id=2162969 | Growers Gate Chardonnay 2022
  LOCAL: clean_id=2732007 pais=ph id_orig=15970
  FONTE: https://barrelsandbeyondph.com/... preco=320.0 PHP
  LOJA: barrelsandbeyondph.com → EXISTE no Render ✅
  WINE_SOURCE: NAO EXISTE ❌

wine_id=2167518 | Guado al Tasso 2008
  LOCAL: clean_id=1727544 pais=us id_orig=405397
  FONTE: https://www.cellaraiders.com/... preco=139.0 USD
  LOJA: cellaraiders.com → EXISTE no Render ✅
  WINE_SOURCE: NAO EXISTE ❌
```

**10 de 10 tem fonte + loja → bug confirmado no script, nao nos dados.**

### 8e. Simulacao de cobertura (10K matched)

Rodamos uma simulacao buscando fontes DIRETO no banco (sem o script):
- 10,000 matched testados
- 9,633 (96.3%) tem wine + fonte + loja
- 12 sem fonte (0.1%)
- 355 sem loja (3.5%)

Isso prova que os dados estao corretos — o problema e o script que nao cria os wine_sources.

---

## 8f. CLASSIFICACAO A/B/C/D DOS 76,812 WINES NOVOS SEM LINK (amostra 2000)

```
A (fonte+loja OK, bug script):  1,920 (96.0%)  → ~73,739 wines
B (fonte OK, loja faltando):       19 (0.9%)   → ~729 wines
C (sem fonte):                     56 (2.8%)   → ~2,150 wines
D (hash nao encontrado):            5 (0.2%)   → ~192 wines
```

**96% sao categoria A** — a fonte existe, a loja existe no Render, mas o script NAO criou o wine_source.

Isso confirma que o bug e 100% na logica da Fase 2, nao nos dados.

### 8g. LOGS DAS EXECUCOES DA FASE 2

**Rodada 1 (05/abril, versao batch com 4 workers):**
```
Total a processar: 827,593
Erros: 33,898 (numeric overflow, varchar too long)
  [W2] ERRO batch: numeric field overflow (precision 10, scale 2)
  [W3] ERRO batch: value too long for type character varying(20)
  [W3] ERRO batch: numeric field overflow (precision 4, scale 1)
  [W0] ERRO batch: numeric field overflow (precision 4, scale 1)
  ... (dezenas de erros distribuidos nos batches)
Resultado: 58,595 criados | 29,370 existentes | 705,730 dup_hash | 40,585 sources | 33,898 erros
```

**Rodada 2 (05/abril, com sanitizacao):**
```
Total a processar: 827,593
  [W3] ERRO batch: value too long for type character varying(20) (3x)
Resultado: 1,940 criados | 547,843 existentes | 275,034 dup_hash | 4,461 sources | 2,776 erros
```

**Rodada 3 (06/abril, com lojas importadas + score >= 0.0):**
```
Fase 2 concluida (detalhes no output do outro chat — erros de encoding + varchar)
```

**NOTA CRITICA**: Quando um worker da erro em um batch, o batch INTEIRO e perdido. Nenhum wine desse batch recebe wine_source. Com batches de 1000, cada erro perde potencialmente 1000 wines. 33,898 erros na Rodada 1 podem ter afetado ~34 batches = ~34,000 wines sem sources.

Mas isso explica so ~34K dos 76K. Os outros ~40K provavelmente se perdem por:
- fontes_map.get(clean_id) retornando vazio (fontes nao carregadas pra esse clean_id)
- hash_to_fontes sendo sobrescrito por outro clean_id com mesmo hash no batch
- check_exists_in_render encontrando o wine mas fontes estando vazio

---

## 9. O QUE NAO FAZER

- NAO deletar nenhum dado
- NAO rodar INSERT/UPDATE
- NAO alterar o script
- NAO executar correcoes
- APENAS investigar, diagnosticar e propor solucoes

---

## 9. ENTREGAVEL ESPERADO

1. **Diagnostico**: Dos 88K novos sem link, quantos caem em cada categoria (A, B, C, D da secao 4)
2. **Causa raiz**: Qual etapa do pipeline perde o link e por que
3. **Proposta de correcao**: Passos detalhados para outro chat executar
4. **Estimativa**: Quantos wines passarao a ter link apos a correcao
5. **Validacao**: Queries pra confirmar que a correcao funcionou

---

## 10. ARMADILHAS CONHECIDAS (NAO REPITA ESTES ERROS)

1. `wines_clean.id` ≠ `vinhos_XX.id` — SEMPRE usar `id_original` + `pais_tabela`
2. `y2_results.vivino_id` = `wines.id` do Render, NAO o vivino_id real
3. `wines_clean.fontes` esta vazio pra 96% dos vinhos — usar `vinhos_XX_fontes`
4. IDs de paises diferentes se sobrepoe (vinhos_br.id=1 ≠ vinhos_us.id=1 ≠ wines_clean.id=1)
5. ON CONFLICT (hash_dedup) DO NOTHING + RETURNING id → retorna NULL se ja existe → wine_sources nao sao criados
6. Render tem NOT NULL em hash_dedup, VARCHAR(2) em pais, NUMERIC(4,1) em teor_alcoolico
7. Conexao Render cai com operacoes longas — usar keepalives
8. `execute_values` rowcount nao e confiavel com ON CONFLICT DO NOTHING
