# WineGod — Schema Atual do Banco de Dados

**Data:** 2026-03-27
**Banco:** PostgreSQL 16 no Render
**Tamanho total:** 911 MB
**Total de tabelas:** 8

---

## Resumo de Volumes

| Tabela | Registros | Tamanho |
|--------|-----------|---------|
| wines | 1,727,058 | 903 MB |
| wine_sources | 0 | 48 kB |
| stores | 0 | 48 kB |
| wine_scores | 0 | 40 kB |
| executions | 0 | 40 kB |
| store_recipes | 0 | 24 kB |
| country_summary | 0 | — |
| platform_summary | 0 | — |

---

## Tabela: `wines`

Principal tabela do sistema. Contém 1,727,058 vinhos importados do Vivino.

| Coluna | Tipo | Nullable | Default |
|--------|------|----------|---------|
| id | integer | NO | nextval('wines_id_seq') |
| hash_dedup | varchar(32) | NO | — |
| nome | text | NO | — |
| nome_normalizado | text | NO | — |
| produtor | text | YES | — |
| produtor_normalizado | text | YES | — |
| safra | varchar(4) | YES | — |
| tipo | varchar(50) | YES | — |
| pais | varchar(2) | YES | — | CANONICO (ISO 3166-1 alpha-2). Usado em busca, filtro, score, trigger. |
| pais_nome | varchar(100) | YES | — | DISPLAY ONLY. Preenchido via dicionario ISO->PT-BR. Nao usar em logica. |
| regiao | text | YES | — |
| sub_regiao | text | YES | — |
| uvas | jsonb | YES | — |
| teor_alcoolico | numeric(4,1) | YES | — |
| volume_ml | integer | YES | — |
| ean_gtin | varchar(20) | YES | — |
| imagem_url | text | YES | — |
| descricao | text | YES | — |
| harmonizacao | text | YES | — |
| vivino_id | bigint | YES | — |
| vivino_rating | numeric(3,2) | YES | — |
| vivino_reviews | integer | YES | — |
| vivino_url | text | YES | — |
| preco_min | numeric(10,2) | YES | — |
| preco_max | numeric(10,2) | YES | — |
| moeda | varchar(3) | YES | — |
| total_fontes | integer | YES | 0 |
| fontes | jsonb | YES | '[]' |
| descoberto_em | timestamptz | YES | now() |
| atualizado_em | timestamptz | YES | now() |

**Constraints:**
- PK: `wines_pkey` (id)
- UNIQUE: `wines_hash_dedup_key` (hash_dedup)

**Indices:**
- `idx_wines_atualizado` — btree (atualizado_em)
- `idx_wines_nome_norm` — btree (nome_normalizado)
- `idx_wines_pais` — btree (pais)
- `idx_wines_produtor_norm` — btree (produtor_normalizado)
- `idx_wines_tipo` — btree (tipo)
- `idx_wines_vivino_id` — btree (vivino_id)

---

## Tabela: `wine_sources`

Fontes/lojas onde cada vinho foi encontrado, com precos.

| Coluna | Tipo | Nullable | Default |
|--------|------|----------|---------|
| id | integer | NO | nextval('wine_sources_id_seq') |
| wine_id | integer | YES | — |
| store_id | integer | YES | — |
| url | text | NO | — |
| preco | numeric(10,2) | YES | — |
| preco_anterior | numeric(10,2) | YES | — |
| moeda | varchar(3) | YES | — |
| disponivel | boolean | YES | true |
| em_promocao | boolean | YES | false |
| descoberto_em | timestamptz | YES | now() |
| atualizado_em | timestamptz | YES | now() |

**Constraints:**
- PK: `wine_sources_pkey` (id)
- UNIQUE: `wine_sources_wine_id_store_id_url_key` (wine_id, store_id, url)
- FK: `wine_sources_wine_id_fkey` → wines(id)
- FK: `wine_sources_store_id_fkey` → stores(id)

**Indices:**
- `idx_sources_disponivel` — btree (disponivel)
- `idx_sources_store` — btree (store_id)
- `idx_sources_wine` — btree (wine_id)

---

## Tabela: `wine_scores`

Notas/scores de diversas fontes para cada vinho.

| Coluna | Tipo | Nullable | Default |
|--------|------|----------|---------|
| id | integer | NO | nextval('wine_scores_id_seq') |
| wine_id | integer | YES | — |
| fonte | varchar(50) | NO | — |
| score | numeric(4,2) | YES | — |
| score_raw | text | YES | — |
| confianca | numeric(3,2) | YES | — |
| dados_extra | jsonb | YES | — |
| criado_em | timestamptz | YES | now() |

**Constraints:**
- PK: `wine_scores_pkey` (id)
- UNIQUE: `wine_scores_wine_id_fonte_key` (wine_id, fonte)
- FK: `wine_scores_wine_id_fkey` → wines(id)

**Indices:**
- `idx_scores_fonte` — btree (fonte)
- `idx_scores_wine` — btree (wine_id)

---

## Tabela: `stores`

Lojas/e-commerces de vinhos cadastradas.

| Coluna | Tipo | Nullable | Default |
|--------|------|----------|---------|
| id | integer | NO | nextval('stores_id_seq') |
| nome | varchar(200) | NO | — |
| url | text | NO | — |
| dominio | varchar(200) | NO | — |
| pais | varchar(2) | NO | — |
| tipo | varchar(50) | YES | — |
| plataforma | varchar(50) | YES | — |
| regiao | varchar(100) | YES | — |
| cidade | varchar(100) | YES | — |
| abrangencia | varchar(20) | YES | — |
| total_vinhos | integer | YES | 0 |
| ativa | boolean | YES | true |
| como_descobriu | varchar(50) | YES | — |
| observacoes | text | YES | — |
| descoberta_em | timestamptz | YES | now() |
| atualizada_em | timestamptz | YES | now() |

**Constraints:**
- PK: `stores_pkey` (id)
- UNIQUE: `stores_dominio_key` (dominio)

**Indices:**
- `idx_stores_ativa` — btree (ativa)
- `idx_stores_pais` — btree (pais)
- `idx_stores_plataforma` — btree (plataforma)

---

## Tabela: `store_recipes`

Receitas de scraping para cada loja (como extrair dados).

| Coluna | Tipo | Nullable | Default |
|--------|------|----------|---------|
| id | integer | NO | nextval('store_recipes_id_seq') |
| store_id | integer | YES | — |
| plataforma | varchar(50) | NO | — |
| metodo_listagem | varchar(20) | NO | — |
| url_sitemap | text | YES | — |
| url_api | text | YES | — |
| filtro_urls | text | YES | — |
| metodo_extracao | varchar(20) | YES | — |
| campos_mapeados | jsonb | YES | — |
| anti_bot | varchar(20) | YES | 'none' |
| usa_curl_cffi | boolean | YES | false |
| usa_playwright | boolean | YES | false |
| headers_custom | jsonb | YES | — |
| sitemap_hash | varchar(32) | YES | — |
| total_produtos | integer | YES | — |
| tempo_medio_seg | integer | YES | — |
| ultima_extracao | timestamptz | YES | — |
| ultima_falha | timestamptz | YES | — |
| falhas_consecutivas | integer | YES | 0 |
| sucesso | boolean | YES | true |
| criado_por | varchar(20) | YES | 'auto' |
| notas | text | YES | — |
| criado_em | timestamptz | YES | now() |
| atualizado_em | timestamptz | YES | now() |

**Constraints:**
- PK: `store_recipes_pkey` (id)
- UNIQUE: `store_recipes_store_id_key` (store_id)
- FK: `store_recipes_store_id_fkey` → stores(id)

---

## Tabela: `executions`

Log de execucoes de scraping/importacao.

| Coluna | Tipo | Nullable | Default |
|--------|------|----------|---------|
| id | integer | NO | nextval('executions_id_seq') |
| pais | varchar(2) | YES | — |
| fonte | varchar(100) | YES | — |
| store_id | integer | YES | — |
| tipo | varchar(20) | YES | — |
| status | varchar(20) | YES | 'running' |
| vinhos_encontrados | integer | YES | 0 |
| vinhos_novos | integer | YES | 0 |
| vinhos_atualizados | integer | YES | 0 |
| precos_alterados | integer | YES | 0 |
| erros | integer | YES | 0 |
| memoria_max_mb | integer | YES | — |
| tempo_seg | integer | YES | — |
| checkpoint | jsonb | YES | — |
| iniciado_em | timestamptz | YES | now() |
| finalizado_em | timestamptz | YES | — |

**Constraints:**
- PK: `executions_pkey` (id)
- FK: `executions_store_id_fkey` → stores(id)

**Indices:**
- `idx_exec_iniciado` — btree (iniciado_em)
- `idx_exec_pais` — btree (pais)
- `idx_exec_status` — btree (status)

---

## Tabela: `country_summary`

Resumo agregado por pais (view materializada ou tabela auxiliar).

| Coluna | Tipo | Nullable | Default |
|--------|------|----------|---------|
| pais | varchar(2) | YES | — |
| total_lojas | bigint | YES | — |
| lojas_ativas | bigint | YES | — |
| vinhos_com_fonte | bigint | YES | — |
| total_vinhos_lojas | bigint | YES | — |

**Constraints:** Nenhuma (sem PK)

---

## Tabela: `platform_summary`

Resumo agregado por plataforma e pais.

| Coluna | Tipo | Nullable | Default |
|--------|------|----------|---------|
| plataforma | varchar(50) | YES | — |
| pais | varchar(2) | YES | — |
| total_lojas | bigint | YES | — |
| total_vinhos | bigint | YES | — |

**Constraints:** Nenhuma (sem PK)

---

## Extensoes Instaladas

| Extensao | Versao |
|----------|--------|
| plpgsql | 1.0 |

---

## Exemplo de 3 Registros (wines)

```
id=1  | Brut Rosé Metodo Classico      | Scacciadiavoli | espumante | IT | Umbria      | vivino_rating=3.90 | reviews=1032
id=2  | Twisted Sisters-Paso Chardonnay | Calcareous     | branco    | US | Paso Robles | vivino_rating=3.70 | reviews=133
id=3  | Trés Violet                     | Calcareous     | tinto     | US | Paso Robles | vivino_rating=4.30 | reviews=1083
```
