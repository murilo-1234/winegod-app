# WineGod — Schema Completo do Banco de Dados

**Data:** 2026-03-27 (apos migracoes)
**Banco:** PostgreSQL 16 no Render
**Tamanho total:** 1,205 MB (antes: 911 MB)
**Total de tabelas:** 8
**Extensoes:** plpgsql 1.0, pg_trgm 1.6

---

## Resumo de Volumes

| Tabela | Registros | Tamanho |
|--------|-----------|---------|
| wines | 1,727,058 | 1,197 MB |
| wine_sources | 0 | 48 kB |
| stores | 0 | 48 kB |
| wine_scores | 0 | 40 kB |
| executions | 0 | 40 kB |
| store_recipes | 0 | 24 kB |
| country_summary | 0 | — |
| platform_summary | 0 | — |

---

## Tabela: `wines` (35 colunas)

Principal tabela do sistema. Contém 1,727,058 vinhos importados do Vivino.

| # | Coluna | Tipo | Nullable | Default | Notas |
|---|--------|------|----------|---------|-------|
| 1 | id | integer | NO | nextval('wines_id_seq') | PK |
| 2 | hash_dedup | varchar(32) | NO | — | UNIQUE, hash para deduplicacao |
| 3 | nome | text | NO | — | Nome original do vinho |
| 4 | nome_normalizado | text | NO | — | Lowercase, sem acentos (busca fuzzy) |
| 5 | produtor | text | YES | — | Nome do produtor/vinicola |
| 6 | produtor_normalizado | text | YES | — | Produtor normalizado |
| 7 | safra | varchar(4) | YES | — | Ano da safra (ex: 2020) |
| 8 | tipo | varchar(50) | YES | — | tinto, branco, rose, espumante, etc |
| 9 | pais | varchar(2) | YES | — | CANONICO. Codigo ISO 3166-1 alpha-2 (br, us, it, etc). Usado em busca, filtro, score, trigger. |
| 10 | pais_nome | varchar(100) | YES | — | DISPLAY ONLY. Nome PT-BR derivado de pais via dicionario. Nao usar em logica funcional. |
| 11 | regiao | text | YES | — | Regiao vinicola |
| 12 | sub_regiao | text | YES | — | Sub-regiao (quando disponivel) |
| 13 | uvas | jsonb | YES | — | Lista de uvas/castas |
| 14 | teor_alcoolico | numeric(4,1) | YES | — | Teor alcoolico (%) |
| 15 | volume_ml | integer | YES | — | Volume da garrafa em ml |
| 16 | ean_gtin | varchar(20) | YES | — | Codigo de barras |
| 17 | imagem_url | text | YES | — | URL da imagem do rotulo |
| 18 | descricao | text | YES | — | Descricao do vinho |
| 19 | harmonizacao | text | YES | — | Sugestoes de harmonizacao |
| 20 | vivino_id | bigint | YES | — | ID do vinho no Vivino |
| 21 | vivino_rating | numeric(3,2) | YES | — | Nota media no Vivino (0-5) |
| 22 | vivino_reviews | integer | YES | — | Numero de avaliacoes no Vivino |
| 23 | vivino_url | text | YES | — | URL do vinho no Vivino |
| 24 | preco_min | numeric(10,2) | YES | — | Menor preco encontrado |
| 25 | preco_max | numeric(10,2) | YES | — | Maior preco encontrado |
| 26 | moeda | varchar(3) | YES | — | Moeda do preco (USD, BRL, EUR) |
| 27 | total_fontes | integer | YES | 0 | Quantas lojas vendem este vinho |
| 28 | fontes | jsonb | YES | '[]' | Lista de fontes (ex: ["vivino"]) |
| 29 | descoberto_em | timestamptz | YES | now() | Data de descoberta |
| 30 | atualizado_em | timestamptz | YES | now() | Ultima atualizacao |
| 31 | **winegod_score** | **numeric(3,2)** | YES | — | **NOVO** WineGod Score: custo-beneficio, escala 0-5 |
| 32 | **winegod_score_type** | **varchar(20)** | YES | 'none' | **NOVO** verified/estimated/none |
| 33 | **winegod_score_components** | **jsonb** | YES | '{}' | **NOVO** Termos proprietarios ativados |
| 34 | **nota_wcf** | **numeric(3,2)** | YES | — | **NOVO** Nota WCF: qualidade pura, escala 0-5 |
| 35 | **confianca_nota** | **numeric(3,2)** | YES | — | **NOVO** Confianca: 0.0 a 1.0 |

### Constraints

| Tipo | Nome | Colunas |
|------|------|---------|
| PRIMARY KEY | wines_pkey | id |
| UNIQUE | wines_hash_dedup_key | hash_dedup |

### Indices (17 total)

| Indice | Tipo | Colunas/Expressao |
|--------|------|-------------------|
| wines_pkey | btree | id |
| wines_hash_dedup_key | btree UNIQUE | hash_dedup |
| idx_wines_atualizado | btree | atualizado_em |
| idx_wines_nome_norm | btree | nome_normalizado |
| idx_wines_pais | btree | pais |
| idx_wines_produtor_norm | btree | produtor_normalizado |
| idx_wines_tipo | btree | tipo |
| idx_wines_vivino_id | btree | vivino_id |
| **idx_wines_nome_trgm** | **GIN** | **nome_normalizado gin_trgm_ops** |
| **idx_wines_nome_original_trgm** | **GIN** | **nome gin_trgm_ops** |
| **idx_wines_pais_rating** | **btree** | **pais, vivino_rating DESC NULLS LAST** |
| **idx_wines_tipo_rating** | **btree** | **tipo, vivino_rating DESC NULLS LAST** |
| **idx_wines_regiao** | **btree** | **regiao WHERE regiao IS NOT NULL** |
| **idx_wines_preco_min** | **btree** | **preco_min WHERE preco_min IS NOT NULL** |
| **idx_wines_wg_score** | **btree** | **winegod_score DESC NULLS LAST WHERE IS NOT NULL** |
| **idx_wines_score_type** | **btree** | **winegod_score_type WHERE != 'none'** |
| **idx_wines_pais_wgscore** | **btree** | **pais, winegod_score DESC NULLS LAST WHERE IS NOT NULL** |

**Novos indices marcados em negrito.**

---

## Tabela: `wine_sources` (0 registros)

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

**Constraints:** PK(id), UNIQUE(wine_id, store_id, url), FK(wine_id→wines), FK(store_id→stores)
**Indices:** idx_sources_disponivel, idx_sources_store, idx_sources_wine

---

## Tabela: `wine_scores` (0 registros)

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

**Constraints:** PK(id), UNIQUE(wine_id, fonte), FK(wine_id→wines)
**Indices:** idx_scores_fonte, idx_scores_wine

---

## Tabela: `stores` (0 registros)

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

**Constraints:** PK(id), UNIQUE(dominio)
**Indices:** idx_stores_ativa, idx_stores_pais, idx_stores_plataforma

---

## Tabela: `store_recipes` (0 registros)

Receitas de scraping para cada loja.

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

**Constraints:** PK(id), UNIQUE(store_id), FK(store_id→stores)

---

## Tabela: `executions` (0 registros)

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

**Constraints:** PK(id), FK(store_id→stores)
**Indices:** idx_exec_iniciado, idx_exec_pais, idx_exec_status

---

## Tabela: `country_summary` (0 registros)

Resumo agregado por pais.

| Coluna | Tipo | Nullable |
|--------|------|----------|
| pais | varchar(2) | YES |
| total_lojas | bigint | YES |
| lojas_ativas | bigint | YES |
| vinhos_com_fonte | bigint | YES |
| total_vinhos_lojas | bigint | YES |

**Constraints:** Nenhuma

---

## Tabela: `platform_summary` (0 registros)

Resumo agregado por plataforma e pais.

| Coluna | Tipo | Nullable |
|--------|------|----------|
| plataforma | varchar(50) | YES |
| pais | varchar(2) | YES |
| total_lojas | bigint | YES |
| total_vinhos | bigint | YES |

**Constraints:** Nenhuma

---

## Extensoes

| Extensao | Versao | Descricao |
|----------|--------|-----------|
| plpgsql | 1.0 | PL/pgSQL procedural language |
| pg_trgm | 1.6 | Busca fuzzy por similaridade de trigrams |

**Configuracao:** `pg_trgm.similarity_threshold = 0.3`

---

## Diagrama de Relacionamentos

```
wines (1,727,058)
  ├── wine_sources (FK: wine_id → wines.id)
  │     └── stores (FK: store_id → stores.id)
  ├── wine_scores (FK: wine_id → wines.id)
  └── [campos WineGod Score: winegod_score, winegod_score_type, winegod_score_components, nota_wcf, confianca_nota]

stores (0)
  ├── store_recipes (FK: store_id → stores.id, 1:1)
  ├── wine_sources (FK: store_id → stores.id)
  └── executions (FK: store_id → stores.id)

country_summary (sem FK, tabela auxiliar)
platform_summary (sem FK, tabela auxiliar)
```

---

## Exemplo de 3 Registros (wines)

```
id=1  | Brut Rosé Metodo Classico       | Scacciadiavoli | espumante | IT | Umbria      | rating=3.90 | reviews=1032 | vivino_id=10
id=2  | Twisted Sisters-Paso Chardonnay | Calcareous     | branco    | US | Paso Robles | rating=3.70 | reviews=133  | vivino_id=17
id=3  | Trés Violet                     | Calcareous     | tinto     | US | Paso Robles | rating=4.30 | reviews=1083 | vivino_id=19
```

---

## Migracoes Aplicadas

| Migracao | Descricao | Status |
|----------|-----------|--------|
| 001_add_winegod_score.sql | 5 colunas novas (winegod_score, winegod_score_type, winegod_score_components, nota_wcf, confianca_nota) | OK |
| 002_add_trgm_index.sql | pg_trgm + 2 indices GIN trigram | OK |
| 003_add_performance_indexes.sql | 7 indices btree para queries frequentes | OK |

**Impacto em disco:** 911 MB → 1,205 MB (+294 MB, maioria indices)

---

## Queries Uteis

```sql
-- Busca fuzzy por nome do vinho
SELECT nome, similarity(nome_normalizado, 'cabernet sauvignon') as sim
FROM wines
WHERE nome_normalizado % 'cabernet sauvignon'
ORDER BY sim DESC LIMIT 10;

-- Top vinhos por custo-beneficio em um pais (quando winegod_score estiver populado)
SELECT nome, winegod_score, vivino_rating, preco_min
FROM wines
WHERE pais = 'br' AND winegod_score IS NOT NULL
ORDER BY winegod_score DESC LIMIT 20;

-- Vinhos por tipo e rating
SELECT nome, vivino_rating, pais
FROM wines
WHERE tipo = 'tinto' AND vivino_rating >= 4.0
ORDER BY vivino_rating DESC LIMIT 20;
```
