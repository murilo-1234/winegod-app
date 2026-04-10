INSTRUCAO: Execute tudo diretamente. NAO pergunte se pode comecar. NAO peca confirmacao. Leia este prompt e implemente imediatamente.

# CHAT Y9 — Match Vinhos de Loja contra Vivino (Grupo 9 de 15)

## CONTEXTO

WineGod.ai tem 2 bases de vinhos:
- **Vivino (confiavel):** 1,727,058 vinhos no banco Render com notas, reviews, produtores verificados
- **Lojas (novos):** 2,942,304 vinhos unicos na tabela `wines_unique` no banco local, deduplicados na Fase X

Este chat e 1 de 15 que rodam EM PARALELO. Cada um processa uma faixa de IDs da wines_unique. Voce processa APENAS os IDs abaixo.

## SUA FAIXA DE IDs

```
wines_unique WHERE id >= 1569225 AND id <= 1765377
```
Estimativa: ~196,153 vinhos.

## CREDENCIAIS

```
# Banco LOCAL (wines_unique — leitura)
LOCAL_URL=postgresql://postgres:postgres123@localhost:5432/winegod_db

# Banco RENDER (wines Vivino — leitura)
RENDER_URL=<DATABASE_URL_FROM_ENV>
```

## O QUE FAZER

Criar script `scripts/match_vivino_9.py` que:
1. Le sua faixa de wines_unique (banco local)
2. Le TODOS os 1.72M vinhos do Vivino (banco Render) — sim, a tabela inteira
3. Tenta match de cada vinho de loja contra o Vivino (3 niveis)
4. Salva resultado em `match_results_g9` (banco local)

## SCHEMA DAS TABELAS

### wines_unique (local) — campos pra match:
- `id`, `nome_normalizado`, `produtor_normalizado`, `safra` (integer)
- `tipo`, `pais` (nome do pais), `pais_tabela` (codigo 2 letras), `regiao`
- `hash_dedup`, `ean_gtin`
- `nome_limpo`, `rating_melhor`, `preco_min_global`, `preco_max_global`, `moeda_referencia`
- `url_imagem`, `total_copias`, `clean_ids` (array), `match_type`

### wines (Render/Vivino) — campos pra match:
- `id`, `nome_normalizado`, `produtor_normalizado`, `safra` (varchar!)
- `tipo`, `pais_nome` (nome do pais), `pais` (codigo 2 letras), `regiao`
- `hash_dedup`, `ean_gtin`
- `nome`, `vivino_rating`, `vivino_reviews`, `vivino_id`
- `imagem_url`, `nota_wcf`, `winegod_score`

**ATENCAO:** `safra` no Vivino e VARCHAR, na wines_unique e INTEGER. Converter ao comparar.

### Mapeamento de campos pra comparacao:

| Campo | wines_unique (loja) | wines (Vivino) |
|---|---|---|
| Nome | nome_normalizado | nome_normalizado |
| Produtor | produtor_normalizado | produtor_normalizado |
| Safra | safra (int) | safra (varchar) |
| Tipo | tipo | tipo |
| Pais | pais_tabela | pais |
| Regiao | regiao | regiao |
| Hash | hash_dedup | hash_dedup |
| EAN | ean_gtin | ean_gtin |

## TABELA DE RESULTADO

```sql
CREATE TABLE IF NOT EXISTS match_results_g9 (
    id SERIAL PRIMARY KEY,
    unique_id INTEGER NOT NULL,          -- ID na wines_unique
    vivino_id INTEGER,                   -- ID na wines (Render). NULL = sem match
    match_level VARCHAR(20) NOT NULL,    -- 'hash', 'ean', 'exact_name', 'splink_high', 'no_match'
    match_probability REAL,              -- 0.0 a 1.0 (1.0 pra deterministicos)
    vivino_nome TEXT,                    -- pra conferencia visual
    loja_nome TEXT                       -- pra conferencia visual
);

CREATE INDEX idx_mr9_uid ON match_results_g9 (unique_id);
CREATE INDEX idx_mr9_vid ON match_results_g9 (vivino_id) WHERE vivino_id IS NOT NULL;
CREATE INDEX idx_mr9_level ON match_results_g9 (match_level);
```

## ALGORITMO — 3 NIVEIS

### PASSO 0 — Carregar dados

```python
import psycopg2
import pandas as pd

# Carregar SUA FAIXA de wines_unique (local)
conn_local = psycopg2.connect(LOCAL_URL)
df_loja = pd.read_sql("""
    SELECT id, nome_normalizado, produtor_normalizado, safra,
           tipo, pais_tabela, regiao, hash_dedup, ean_gtin, nome_limpo
    FROM wines_unique
    WHERE id >= 1569225 AND id <= 1765377
""", conn_local)

# Carregar TODOS os vinhos Vivino (Render)
conn_render = psycopg2.connect(RENDER_URL)
df_vivino = pd.read_sql("""
    SELECT id as vivino_id, nome_normalizado, produtor_normalizado, safra,
           tipo, pais as pais_code, regiao, hash_dedup, ean_gtin, nome
    FROM wines
""", conn_render)
conn_render.close()

# Converter safra do Vivino pra int
df_vivino['safra'] = pd.to_numeric(df_vivino['safra'], errors='coerce').astype('Int64')

print(f"Loja: {len(df_loja):,} | Vivino: {len(df_vivino):,}")
```

### NIVEL 1 — Deterministico (100% certeza)

**1a. Match por hash_dedup:**
```python
# Inner join por hash_dedup (quando ambos nao sao NULL)
matches_hash = df_loja[df_loja['hash_dedup'].notna()].merge(
    df_vivino[df_vivino['hash_dedup'].notna()][['vivino_id', 'hash_dedup', 'nome']],
    on='hash_dedup', how='inner'
)
# Registrar: match_level='hash', match_probability=1.0
matched_ids = set(matches_hash['id'])
```

**1b. Match por ean_gtin:**
```python
remaining = df_loja[~df_loja['id'].isin(matched_ids)]
matches_ean = remaining[remaining['ean_gtin'].notna()].merge(
    df_vivino[df_vivino['ean_gtin'].notna()][['vivino_id', 'ean_gtin', 'nome']],
    on='ean_gtin', how='inner'
)
matched_ids.update(matches_ean['id'])
```

**1c. Match por nome_normalizado + safra exato:**
```python
remaining = df_loja[~df_loja['id'].isin(matched_ids)]
matches_exact = remaining.merge(
    df_vivino[['vivino_id', 'nome_normalizado', 'safra', 'nome']],
    on=['nome_normalizado', 'safra'], how='inner'
)
# Se multiplos matches, pegar o com mais reviews (ou primeiro)
matches_exact = matches_exact.drop_duplicates(subset='id', keep='first')
matched_ids.update(matches_exact['id'])
```

**1d. Match por nome_normalizado sem safra (quando ambas safras sao NULL):**
```python
remaining = df_loja[~df_loja['id'].isin(matched_ids)]
remaining_no_safra = remaining[remaining['safra'].isna()]
vivino_no_safra = df_vivino[df_vivino['safra'].isna()]
matches_no_safra = remaining_no_safra.merge(
    vivino_no_safra[['vivino_id', 'nome_normalizado', 'nome']],
    on='nome_normalizado', how='inner'
)
matches_no_safra = matches_no_safra.drop_duplicates(subset='id', keep='first')
matched_ids.update(matches_no_safra['id'])
```

Todos os matches nivel 1: `match_level='exact_name'` ou `'hash'`/`'ean'`, `match_probability=1.0`.

### NIVEL 2 — Probabilistico com Splink

Para os vinhos que sobraram, usar Splink em modo LINKAGE (2 tabelas):

```bash
pip install splink[duckdb]
```

```python
import splink.comparison_library as cl
import splink.blocking_rule_library as brl
from splink import DuckDBAPI, Linker, SettingsCreator, block_on

# Preparar DataFrames pro Splink
df_loja_remaining = df_loja[~df_loja['id'].isin(matched_ids)].copy()
df_loja_remaining = df_loja_remaining.rename(columns={'id': 'unique_id'})

# Adicionar source_dataset pro Splink saber qual e qual
df_loja_remaining['source_dataset'] = 'loja'
df_vivino_splink = df_vivino.copy()
df_vivino_splink['source_dataset'] = 'vivino'
df_vivino_splink = df_vivino_splink.rename(columns={'vivino_id': 'unique_id'})

# Alinhar colunas (ambos precisam ter as mesmas colunas)
cols = ['unique_id', 'nome_normalizado', 'produtor_normalizado',
        'safra', 'tipo', 'pais_code', 'regiao', 'source_dataset']

# Ajustar nome de coluna de pais
df_loja_remaining = df_loja_remaining.rename(columns={'pais_tabela': 'pais_code'})

# Selecionar colunas
df_left = df_loja_remaining[cols].copy()
df_right = df_vivino_splink[cols].copy()

# Converter safra pra string pro Splink
df_left['safra'] = df_left['safra'].astype(str).replace('<NA>', None).replace('nan', None)
df_right['safra'] = df_right['safra'].astype(str).replace('<NA>', None).replace('nan', None)

# Configurar Splink em modo LINKAGE (2 tabelas)
settings = SettingsCreator(
    link_type="link_only",                    # LINKAGE, nao dedup
    unique_id_column_name="unique_id",

    comparisons=[
        cl.JaroWinklerAtThresholds(
            col_name="nome_normalizado",
            score_threshold_or_thresholds=[0.92, 0.80],
        ),
        cl.JaroWinklerAtThresholds(
            col_name="produtor_normalizado",
            score_threshold_or_thresholds=[0.92, 0.80],
        ),
        cl.ExactMatch("safra"),
        cl.ExactMatch("tipo"),
        cl.ExactMatch("pais_code"),
        cl.JaroWinklerAtThresholds(
            col_name="regiao",
            score_threshold_or_thresholds=[0.88],
        ),
    ],

    blocking_rules_to_generate_predictions=[
        block_on("nome_normalizado"),
        block_on("produtor_normalizado", "pais_code"),
        brl.CustomRule(
            "SUBSTR(l.nome_normalizado,1,10) = SUBSTR(r.nome_normalizado,1,10) "
            "AND l.pais_code = r.pais_code"
        ),
    ],

    retain_matching_columns=True,
)

db_api = DuckDBAPI()
linker = Linker([df_left, df_right], settings, db_api)

# Treinar
training_block_nome = block_on("nome_normalizado")
training_block_produtor = block_on("produtor_normalizado")

linker.training.estimate_probability_two_random_records_match(
    training_block_nome, recall=0.7,
)
linker.training.estimate_u_using_random_sampling(max_pairs=5_000_000)
linker.training.estimate_parameters_using_expectation_maximisation(
    training_block_nome, fix_u_probabilities=True,
)
linker.training.estimate_parameters_using_expectation_maximisation(
    training_block_produtor, fix_u_probabilities=True,
)

# Predizer
results = linker.inference.predict(threshold_match_probability=0.50)
df_predictions = results.as_pandas_dataframe()

# Separar: match alto (>= 0.80) vs quarentena (0.50-0.80)
df_high = df_predictions[df_predictions['match_probability'] >= 0.80].copy()
df_quarantine = df_predictions[
    (df_predictions['match_probability'] >= 0.50) &
    (df_predictions['match_probability'] < 0.80)
].copy()

# Pra cada vinho de loja, pegar o MELHOR match do Vivino (maior probabilidade)
# Identificar qual lado e loja e qual e vivino pelo source_dataset
# df_predictions tem unique_id_l e unique_id_r
# Precisamos saber qual e loja e qual e vivino
```

**IMPORTANTE sobre Splink linkage com 2 tabelas:**
- Passar como lista: `Linker([df_left, df_right], settings, db_api)`
- `link_type="link_only"` — so compara entre tabelas, nao dentro
- Os resultados tem `unique_id_l` (da primeira tabela) e `unique_id_r` (da segunda)
- Se df_left e loja e df_right e vivino: `unique_id_l` = ID loja, `unique_id_r` = ID vivino
- Pegar o match com maior probabilidade quando um vinho de loja bate com multiplos Vivino

Marcar como `match_level='splink_high'` (prob >= 0.80).

### NIVEL 3 — Sem match

Vinhos que nao matcharam em nenhum nivel:
```python
# Registrar com match_level='no_match', vivino_id=NULL
```

## VALIDACOES

1. **Um vinho de loja so pode ter 1 match Vivino.** Se multiplos, pegar o de maior probabilidade.
2. **Tipo deve bater.** Se loja diz "tinto" e Vivino diz "branco", descartar o match.
3. **Nao forcar match.** Se nenhum Vivino bate, e no_match — nao inventar.

## PERFORMANCE

- Carregar Vivino inteiro em memoria uma vez (~1.72M records, ~500MB em pandas)
- Nivel 1 e puro pandas merge — segundos
- Nivel 2 Splink — minutos (DuckDB paralleliza)
- INSERT em batches de 5000
- Progresso: `[Y9] Nivel 1: X matches | Nivel 2: processando... | Sem match: X`

## O QUE NAO FAZER

- **NAO processar IDs fora da sua faixa**
- **NAO modificar wines_unique nem wines (Render)** — so ler
- **NAO criar tabela match_results** (sem sufixo) — so match_results_g9
- **NAO fazer git commit/push**
- **NAO escrever no banco Render** — so ler. Escrever so no local.

## COMO TESTAR

```bash
cd C:\winegod-app && python scripts/match_vivino_9.py
```

Verificar:
```sql
SELECT match_level, COUNT(*), ROUND(AVG(match_probability)::numeric, 2) as prob_media
FROM match_results_g9 GROUP BY match_level ORDER BY COUNT(*) DESC;

SELECT COUNT(*) as total FROM match_results_g9;
SELECT COUNT(*) FILTER (WHERE vivino_id IS NOT NULL) as com_match FROM match_results_g9;
SELECT COUNT(*) FILTER (WHERE vivino_id IS NULL) as sem_match FROM match_results_g9;
```

## ENTREGAVEL

Ao terminar, imprimir:
```
=== GRUPO Y9 CONCLUIDO ===
Input: X vinhos de wines_unique (IDs 1569225 a 1765377)
Vivino carregado: 1,727,058 vinhos

Nivel 1 (hash):       X matches
Nivel 1 (ean):        X matches
Nivel 1 (nome exato): X matches
Nivel 2 (Splink):     X matches
Sem match:            X vinhos

Taxa de match: X% encontraram par no Vivino
Tabela: match_results_g9 populada com X registros
```

E mostrar 10 exemplos de matches nivel 1 e 10 do nivel 2 (Splink) pra conferencia visual:
```
[HASH]  "catena malbec 2021" (loja) → "catena malbec 2021" (vivino) | prob=1.0
[SPLINK] "ch margaux grand vin 2015" (loja) → "chateau margaux 2015" (vivino) | prob=0.93
```
