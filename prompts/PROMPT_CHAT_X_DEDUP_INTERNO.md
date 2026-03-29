INSTRUCAO: Execute tudo diretamente. NAO pergunte se pode comecar. NAO peca confirmacao. Leia este prompt e implemente imediatamente.

# CHAT X — Fase 2: Deduplicacao Interna dos ~3.96M Vinhos

## CONTEXTO

A Fase 1 (Chat W) limpou e filtrou vinhos de lojas: corrigiu encoding, removeu HTML/volume/preco do nome, extraiu produtor, eliminou ~211K registros de lixo (spirits, grappa, acessorios, fragmentos). Resultado: **3,955,624 vinhos limpos** na tabela `wines_clean` no banco local. Muitos desses vinhos sao o MESMO vinho vendido em lojas/paises diferentes. Precisamos encontrar os vinhos UNICOS.

## SUA TAREFA

Criar um script que:
1. Le a tabela `wines_clean`
2. Agrupa vinhos que sao o mesmo produto (mesmo vinho, lojas diferentes)
3. Salva numa tabela `wines_unique` com vinhos unicos + referencia as fontes

## CREDENCIAIS

```
WINEGOD_LOCAL_URL=postgresql://postgres:XXXXXXXXX@localhost:5432/winegod_db
```

## TABELA DE ORIGEM

`wines_clean` — criada pela Fase 1, com colunas:
- `id`, `pais_tabela`, `id_original`
- `nome_limpo`, `nome_normalizado`
- `produtor_extraido`, `produtor_normalizado`
- `safra`, `tipo`, `pais`, `regiao`, `sub_regiao`, `uvas`
- `rating`, `total_ratings`
- `preco`, `moeda`, `preco_min`, `preco_max`
- `url_imagem`, `hash_dedup`, `ean_gtin`
- `fontes`, `total_fontes`

## TABELA DE DESTINO

```sql
CREATE TABLE IF NOT EXISTS wines_unique (
    id SERIAL PRIMARY KEY,
    nome_limpo TEXT NOT NULL,
    nome_normalizado TEXT NOT NULL,
    produtor TEXT,
    produtor_normalizado TEXT,
    safra INTEGER,
    tipo TEXT,
    pais TEXT,
    regiao TEXT,
    sub_regiao TEXT,
    uvas TEXT,
    rating_melhor REAL,              -- melhor rating entre as copias
    total_ratings_max INTEGER,       -- maior total_ratings entre as copias
    preco_min_global REAL,           -- menor preco entre todas as fontes
    preco_max_global REAL,           -- maior preco
    moeda_referencia VARCHAR(10),    -- moeda do preco_min_global
    url_imagem TEXT,                 -- melhor imagem disponivel
    hash_dedup VARCHAR(64),
    ean_gtin VARCHAR(50),
    total_copias INTEGER,            -- em quantas lojas/paises aparece
    clean_ids INTEGER[],             -- array de IDs na wines_clean
    UNIQUE(nome_normalizado, safra, pais)
);

CREATE INDEX idx_wu_nome ON wines_unique (nome_normalizado);
CREATE INDEX idx_wu_produtor ON wines_unique (produtor_normalizado);
CREATE INDEX idx_wu_hash ON wines_unique (hash_dedup) WHERE hash_dedup IS NOT NULL;
CREATE INDEX idx_wu_pais ON wines_unique (pais);
CREATE INDEX idx_wu_ean ON wines_unique (ean_gtin) WHERE ean_gtin IS NOT NULL;
```

## ALGORITMO DE DEDUPLICACAO (Cascading Rules)

Processar por pais. Para cada par de vinhos, considerar DUPLICATA se:

### Nivel 1 — Match exato por hash_dedup
Se `hash_dedup` e igual e nao NULL → mesmo vinho (100% certeza)

### Nivel 2 — Match exato por EAN/GTIN
Se `ean_gtin` e igual e nao NULL → mesmo vinho (100% certeza)

### Nivel 3 — Match exato por nome_normalizado + safra
Se `nome_normalizado` identico E `safra` identica (ou ambas NULL) → mesmo vinho (99% certeza)

### Nivel 4 — Match fuzzy por nome (mesmo pais)
Se no mesmo pais:
- `nome_normalizado` com similarity > 0.85 (Jaccard ou SequenceMatcher)
- E safra igual (ou ambas NULL)
→ provavel mesmo vinho (90% certeza)

### Estrategia de implementacao:

```python
# 1. Criar dict de grupos por hash_dedup
# 2. Para vinhos sem hash, agrupar por (nome_normalizado, safra, pais)
# 3. Para vinhos que sobraram, fuzzy match dentro do mesmo pais

from collections import defaultdict

# Grupo por hash
hash_groups = defaultdict(list)
nome_groups = defaultdict(list)
ungrouped = []

for wine in wines_clean:
    if wine.hash_dedup:
        hash_groups[wine.hash_dedup].append(wine)
    else:
        key = (wine.nome_normalizado, wine.safra, wine.pais)
        nome_groups[key].append(wine)

# Cada grupo = 1 vinho unico
for group in hash_groups.values():
    wine_unico = merge_group(group)
    insert_wines_unique(wine_unico)

for group in nome_groups.values():
    wine_unico = merge_group(group)
    insert_wines_unique(wine_unico)
```

### Funcao merge_group:
Quando um vinho aparece em multiplas copias, o vinho unico pega:
- `nome_limpo` — da copia com nome mais longo (mais completo)
- `rating_melhor` — MAX de todos os ratings
- `total_ratings_max` — MAX de todos os total_ratings
- `preco_min_global` — MIN de todos os precos
- `preco_max_global` — MAX de todos os precos
- `url_imagem` — primeira imagem nao NULL
- `total_copias` — COUNT do grupo
- `clean_ids` — array com todos os IDs da wines_clean

## PERFORMANCE

- Carregar vinhos em memoria por pais (nao todos de uma vez)
- Usar dicts para O(1) lookup por hash e nome
- Nao usar pg_trgm (tudo em memoria com Python)
- INSERT em batches de 5000
- Progresso: `[Fase 2] 500000/3955624 processados — 127000 unicos ate agora`
- Tempo estimado: 1-2h

## ARQUIVO A CRIAR

### scripts/dedup_internal.py (NOVO)

## O QUE NAO FAZER

- **NAO modificar wines_clean** — so ler
- **NAO conectar ao banco Render** — tudo local
- **NAO fazer git commit/push** — avisar quando terminar
- **NAO usar fuzzy match cross-pais** — so dentro do mesmo pais (senao explode em complexidade)

## COMO TESTAR

```bash
cd scripts && python dedup_internal.py
# Verificar:
psql -h localhost -U postgres -d winegod_db -c "SELECT COUNT(*) FROM wines_unique;"
psql -h localhost -U postgres -d winegod_db -c "SELECT total_copias, COUNT(*) FROM wines_unique GROUP BY total_copias ORDER BY total_copias DESC LIMIT 10;"
```

## ENTREGAVEL

- `scripts/dedup_internal.py`
- Tabela `wines_unique` populada (estimativa: 800K-1.5M vinhos unicos)
- Relatorio: quantos duplicatas encontrados, distribuicao de copias

## REGRA DE COMMIT

Commitar APENAS os arquivos que VOCE criou/modificou nesta sessao. NUNCA incluir arquivos de outros chats. Fazer `git pull` antes de `git push`.
