INSTRUCAO: Execute tudo diretamente. NAO pergunte se pode comecar. NAO peca confirmacao. Leia este prompt e implemente imediatamente.

# CHAT X6 — Deduplicacao de Vinhos (Grupo 6 de 10)

## CONTEXTO

WineGod.ai e uma IA sommelier com 1.72M vinhos Vivino + ~4M vinhos de lojas (50 paises). A Fase 1 (Chat W) limpou os vinhos de lojas e salvou 3,955,624 registros na tabela `wines_clean` no banco local.

Este chat e 1 de 10 que rodam EM PARALELO. Cada um processa um grupo de paises. Voce processa APENAS os paises listados abaixo. Os outros 9 chats processam os outros paises. No final, um prompt de merge junta tudo.

## SEUS PAISES

```
PT, FR, NZ, ES
```

Filtrar SEMPRE: `WHERE pais_tabela IN ('pt', 'fr', 'nz', 'es')`

## CREDENCIAIS

```
WINEGOD_LOCAL_URL=postgresql://postgres:XXXXXXXXX@localhost:5432/winegod_db
```

## O QUE FAZER

Criar um script `scripts/dedup_group_6.py` que:
1. Le vinhos do seu grupo da tabela `wines_clean`
2. Deduplica em 3 niveis (deterministico + probabilistico + quarentena)
3. Salva resultado em `wines_unique_g6` e `dedup_quarantine_g6`

## TABELA DE ORIGEM

`wines_clean` — colunas relevantes para dedup:
- `id` (PK), `pais_tabela`, `id_original`
- `nome_limpo`, `nome_normalizado` (lowercase sem acentos)
- `produtor_extraido`, `produtor_normalizado`
- `safra` (integer, pode ser NULL)
- `tipo` (tinto/branco/rose/espumante, pode ser NULL)
- `pais` (nome do pais, pode ser NULL)
- `regiao`, `sub_regiao` (podem ser NULL)
- `uvas` (pode ser NULL)
- `rating`, `total_ratings`
- `preco`, `moeda`, `preco_min`, `preco_max`
- `url_imagem`, `hash_dedup`, `ean_gtin`
- `fontes`, `total_fontes`

## TABELAS DE DESTINO

```sql
CREATE TABLE IF NOT EXISTS wines_unique_g6 (
    id SERIAL PRIMARY KEY,
    nome_limpo TEXT NOT NULL,
    nome_normalizado TEXT NOT NULL,
    produtor TEXT,
    produtor_normalizado TEXT,
    safra INTEGER,
    tipo TEXT,
    pais TEXT,
    pais_tabela VARCHAR(5),
    regiao TEXT,
    sub_regiao TEXT,
    uvas TEXT,
    rating_melhor REAL,
    total_ratings_max INTEGER,
    preco_min_global REAL,
    preco_max_global REAL,
    moeda_referencia VARCHAR(10),
    url_imagem TEXT,
    hash_dedup VARCHAR(64),
    ean_gtin VARCHAR(50),
    match_type VARCHAR(20) NOT NULL,
    match_probability REAL,
    total_copias INTEGER,
    clean_ids INTEGER[]
);

CREATE TABLE IF NOT EXISTS dedup_quarantine_g6 (
    id SERIAL PRIMARY KEY,
    clean_id_a INTEGER NOT NULL,
    clean_id_b INTEGER NOT NULL,
    nome_a TEXT,
    nome_b TEXT,
    match_probability REAL,
    motivo TEXT
);
```

## ALGORITMO — 3 NIVEIS (abordagem hibrida NHS England / Censo UK)

### NIVEL 1 — Deterministico (100% certeza)

Agrupar vinhos que sao CERTAMENTE o mesmo produto:

**1a. hash_dedup identico** (quando nao NULL):
```python
# Agrupar por hash_dedup dentro do mesmo pais_tabela
# Se 5 vinhos tem o mesmo hash → 1 grupo de 5 copias
groups_hash = df.groupby(['pais_tabela', 'hash_dedup']).agg(...)
```

**1b. ean_gtin identico** (quando nao NULL):
```python
# EAN/GTIN e codigo de barras — se bate, e o mesmo produto
groups_ean = df.groupby(['pais_tabela', 'ean_gtin']).agg(...)
```

**1c. nome_normalizado + safra identicos** (dentro do mesmo pais_tabela):
```python
# "chateau margaux 2015" aparece 12 vezes = 1 vinho, 12 copias
groups_exact = df.groupby(['pais_tabela', 'nome_normalizado', 'safra']).agg(...)
```

Marcar todos como `match_type = 'deterministic'`, `match_probability = 1.0`.

**IMPORTANTE**: Ao agrupar no nivel 1, juntar os IDs. Se um vinho ja foi agrupado por hash, NAO processar de novo por nome. Manter um set de IDs ja processados.

### NIVEL 2 — Probabilistico com Splink (~85-99% certeza)

Para os vinhos que sobraram (sem match no nivel 1), usar Splink:

```bash
pip install splink duckdb
```

```python
# ── Instalar dependencias ──
# pip install splink[duckdb] psycopg2-binary pandas

import splink.comparison_library as cl
import splink.blocking_rule_library as brl
from splink import DuckDBAPI, Linker, SettingsCreator, block_on

# ── Configurar o modelo Splink ──

# Blocking rules pra TREINO (EM) — uma por passada
training_block_nome = block_on("nome_normalizado")
training_block_produtor = block_on("produtor_normalizado")

# Blocking rules pra PREDICAO — pares que serao avaliados
# Um par e avaliado se bater em QUALQUER uma dessas regras (OR)
prediction_blocking_rules = [
    block_on("nome_normalizado"),                          # nome exato
    block_on("produtor_normalizado", "pais_tabela"),       # produtor + pais
    brl.CustomRule(
        "SUBSTR(l.nome_normalizado,1,10) = SUBSTR(r.nome_normalizado,1,10) "
        "AND l.pais_tabela = r.pais_tabela"
    ),                                                     # primeiros 10 chars + pais
]

# Comparacoes — cada campo com tipo de similaridade e thresholds
settings = SettingsCreator(
    link_type="dedupe_only",
    unique_id_column_name="id",
    comparisons=[
        # Nome: campo principal — Jaro-Winkler com 2 thresholds
        cl.JaroWinklerAtThresholds(
            col_name="nome_normalizado",
            score_threshold_or_thresholds=[0.92, 0.80],
        ),
        # Produtor: fuzzy (pode ter variantes)
        cl.JaroWinklerAtThresholds(
            col_name="produtor_normalizado",
            score_threshold_or_thresholds=[0.92, 0.80],
        ),
        # Safra: match exato
        cl.ExactMatch("safra"),
        # Tipo: match exato (tinto != branco)
        cl.ExactMatch("tipo"),
        # Pais: match exato
        cl.ExactMatch("pais_tabela"),
        # Regiao: fuzzy (variantes de grafia)
        cl.JaroWinklerAtThresholds(
            col_name="regiao",
            score_threshold_or_thresholds=[0.88],
        ),
        # Uvas: fuzzy (blends em ordens diferentes)
        cl.JaroWinklerAtThresholds(
            col_name="uvas",
            score_threshold_or_thresholds=[0.88],
        ),
    ],
    blocking_rules_to_generate_predictions=prediction_blocking_rules,
    retain_matching_columns=True,
)

# ── Rodar o pipeline Splink ──

def run_splink_dedup(df_remaining, match_threshold=0.80, review_threshold=0.50):
    """
    Recebe DataFrame com vinhos que NAO foram agrupados no nivel 1.
    Retorna: (df_clusters, df_review_pairs)
    - df_clusters: DataFrame com colunas (id, cluster_id) — mesmo cluster = mesmo vinho
    - df_review_pairs: DataFrame com pares incertos pra quarentena
    """
    if len(df_remaining) < 10:
        return pd.DataFrame(columns=["id", "cluster_id"]), pd.DataFrame()

    db_api = DuckDBAPI()
    linker = Linker(df_remaining, settings, db_api)

    # Estimar probabilidade prior (2 registros aleatorios serem match)
    linker.training.estimate_probability_two_random_records_match(
        training_block_nome, recall=0.7,
    )

    # Estimar u-probabilities (P(campo bate | NAO e match))
    linker.training.estimate_u_using_random_sampling(max_pairs=5_000_000)

    # Estimar m-probabilities via EM (P(campo bate | E match))
    linker.training.estimate_parameters_using_expectation_maximisation(
        training_block_nome, fix_u_probabilities=True,
    )
    linker.training.estimate_parameters_using_expectation_maximisation(
        training_block_produtor, fix_u_probabilities=True,
    )

    # Predizer — gerar pares com probabilidade >= review_threshold
    results = linker.inference.predict(threshold_match_probability=review_threshold)
    df_predictions = results.as_pandas_dataframe()

    if len(df_predictions) == 0:
        return pd.DataFrame(columns=["id", "cluster_id"]), pd.DataFrame()

    # Pares pra quarentena (review_threshold <= prob < match_threshold)
    df_review = df_predictions[
        (df_predictions["match_probability"] >= review_threshold) &
        (df_predictions["match_probability"] < match_threshold)
    ][["id_l", "id_r", "match_probability"]].copy()

    # Clusterizar — agrupar pares acima do match_threshold
    clusters = linker.clustering.cluster_pairwise_predictions_at_threshold(
        results, threshold_match_probability=match_threshold,
    )
    df_clusters = clusters.as_pandas_dataframe()

    return df_clusters, df_review
```

**IMPORTANTE sobre Splink:**
- `pip install splink[duckdb]` — instalar ANTES de rodar
- O Splink usa DuckDB internamente (rapido, in-process, sem servidor)
- Se o grupo tiver poucos vinhos restantes apos nivel 1 (<100), pular nivel 2
- Se der erro de memoria, processar por pais_tabela individualmente dentro do grupo
- O pipeline Splink treina um modelo estatistico nos SEUS dados — nao usa modelo pre-treinado

Marcar como `match_type = 'splink_high'` se probabilidade >= 0.80.

### NIVEL 3 — Quarentena (50-80% certeza)

Pares com match_probability entre 0.50 e 0.80 vao pra `dedup_quarantine_g6`:
- Nao sao agrupados (ficam separados em wines_unique)
- Sao registrados pra revisao futura
- Motivo: "splink_uncertain" + detalhes

### FUNCAO DE MERGE DE GRUPO

Quando um vinho aparece em multiplas copias, o vinho unico pega:
```python
def merge_group(group_df):
    return {
        'nome_limpo': group_df.loc[group_df['nome_limpo'].str.len().idxmax(), 'nome_limpo'],  # nome mais longo
        'nome_normalizado': group_df.iloc[0]['nome_normalizado'],
        'produtor': first_non_null(group_df, 'produtor_extraido'),
        'produtor_normalizado': first_non_null(group_df, 'produtor_normalizado'),
        'safra': first_non_null(group_df, 'safra'),
        'tipo': most_common(group_df, 'tipo'),
        'pais': first_non_null(group_df, 'pais'),
        'pais_tabela': group_df.iloc[0]['pais_tabela'],
        'regiao': first_non_null(group_df, 'regiao'),
        'sub_regiao': first_non_null(group_df, 'sub_regiao'),
        'uvas': first_non_null(group_df, 'uvas'),
        'rating_melhor': group_df['rating'].max(),
        'total_ratings_max': group_df['total_ratings'].max(),
        'preco_min_global': group_df['preco'].min(),  # ignorar NULL e 0
        'preco_max_global': group_df['preco'].max(),
        'moeda_referencia': most_common(group_df, 'moeda'),
        'url_imagem': first_non_null(group_df, 'url_imagem'),
        'hash_dedup': first_non_null(group_df, 'hash_dedup'),
        'ean_gtin': first_non_null(group_df, 'ean_gtin'),
        'total_copias': len(group_df),
        'clean_ids': list(group_df['id']),
    }
```

### VALIDACOES DE SEGURANCA (aplicar antes de confirmar merge)

1. **Tipo deve bater**: se um grupo tem tinto E branco, SEPARAR (nao e o mesmo vinho)
2. **Preco nao pode variar >10x**: se min=5 e max=500 no grupo, colocar em quarentena
3. **Grupos gigantes (>100 copias)**: verificar se faz sentido, pode ser lixo generico

## PERFORMANCE

- Carregar vinhos em memoria com pandas (por pais)
- Nivel 1 e puro pandas groupby — rapido
- Nivel 2 (Splink) usar DuckDB backend — benchmark: 7M em 2 minutos
- INSERT em batches de 5000
- Progresso: `[X6] pais US: 784,300 vinhos | nivel 1: 520K agrupados | nivel 2: processando...`

## O QUE NAO FAZER

- **NAO processar paises que NAO sao seus** — so os listados acima
- **NAO modificar wines_clean** — so ler
- **NAO criar tabela wines_unique** (sem sufixo) — so wines_unique_g6
- **NAO conectar ao banco Render** — tudo local
- **NAO fazer git commit/push**
- **NAO instalar pacotes grandes (torch, tensorflow)** — so splink e duckdb

## COMO TESTAR

```bash
cd C:\winegod-app && python scripts/dedup_group_6.py
```

Verificar:
```sql
SELECT COUNT(*) FROM wines_unique_g6;
SELECT match_type, COUNT(*) FROM wines_unique_g6 GROUP BY match_type;
SELECT total_copias, COUNT(*) FROM wines_unique_g6 GROUP BY total_copias ORDER BY total_copias DESC LIMIT 10;
SELECT COUNT(*) FROM dedup_quarantine_g6;
```

## ENTREGAVEL

Ao terminar, imprimir relatorio:
```
=== GRUPO 6 CONCLUIDO ===
Paises: PT, FR, NZ, ES
Input: X vinhos de wines_clean
Nivel 1 (deterministico): X grupos
Nivel 2 (Splink): X grupos adicionais
Nivel 3 (quarentena): X pares incertos
Output: X vinhos unicos em wines_unique_g6
Taxa de dedup: X% (de N para M)
```

E mostrar 10 exemplos de merges do nivel 1 e 10 do nivel 2 para conferencia visual.
