INSTRUCAO: Execute tudo diretamente. NAO pergunte se pode comecar. NAO peca confirmacao. Leia este prompt e implemente imediatamente.

# CHAT Z — Fase 4: Importar Vinhos Matchados e Novos pro Render

## CONTEXTO

A Fase 3 (Chat Y) cruzou vinhos de lojas com os 1.72M vinhos Vivino no Render. Os resultados estao na tabela `wines_matched` no banco local. Agora precisamos:

1. **Vinhos COM match** (exact/producer/fuzzy) → criar `wine_sources` no Render (loja + preco + URL)
2. **Vinhos SEM match** → inserir como vinhos NOVOS na tabela `wines` do Render

## SUA TAREFA

Criar um script que:
1. Le `wines_matched` + `wines_unique` + `wines_clean` do banco local
2. Para vinhos com match: cria registros em `wine_sources` e atualiza precos em `wines` no Render
3. Para vinhos sem match: insere como vinhos novos em `wines` no Render + cria `wine_sources`

## CREDENCIAIS

```
# Banco local
WINEGOD_LOCAL_URL=postgresql://postgres:XXXXXXXXX@localhost:5432/winegod_db

# Banco Render
DATABASE_URL=postgresql://winegod_user:XXXXXXXXX@dpg-XXXXXXXXX.oregon-postgres.render.com/winegod
```

## TABELAS DE ORIGEM (banco local)

`wines_matched`:
- `unique_id` → referencia wines_unique
- `match_type` — 'exact_hash', 'exact_name', 'fuzzy_name', 'producer_vintage', 'no_match'
- `vivino_wine_id` — ID na tabela wines do Render (NULL se no_match)
- `confidence` — 0.0 a 1.0

`wines_unique`:
- `id`, `nome_limpo`, `nome_normalizado`
- `produtor`, `produtor_normalizado`
- `safra`, `tipo`, `pais`, `regiao`, `sub_regiao`, `uvas`
- `rating_melhor`, `total_ratings_max`
- `preco_min_global`, `preco_max_global`, `moeda_referencia`
- `url_imagem`, `hash_dedup`, `ean_gtin`
- `total_copias`, `clean_ids`

`wines_clean`:
- Dados individuais de cada copia do vinho (cada loja)
- `fontes` — JSON com dados das lojas

`lojas_scraping` (tabela existente no banco local):
- `id`, `nome`, `dominio`, `pais`, `plataforma`, `url`
- Ja foi importada pro Render como `stores` na Fase I

## TABELAS DE DESTINO (banco Render)

### Para vinhos COM match — criar wine_sources

```sql
INSERT INTO wine_sources (wine_id, store_id, preco, moeda, url, nome_na_loja, atualizado_em)
VALUES (%s, %s, %s, %s, %s, %s, NOW())
ON CONFLICT DO NOTHING;
```

E atualizar precos no wines:
```sql
UPDATE wines SET
    preco_min = LEAST(preco_min, %s),
    preco_max = GREATEST(preco_max, %s)
WHERE id = %s AND (%s < preco_min OR preco_min IS NULL);
```

### Para vinhos SEM match — inserir vinho novo + wine_sources

```sql
INSERT INTO wines (
    nome, produtor, safra, tipo, pais_nome, regiao, sub_regiao,
    vivino_rating, vivino_reviews,
    preco_min, preco_max, moeda,
    nome_normalizado,
    nota_wcf, confianca_nota, winegod_score_type
)
VALUES (
    %s, %s, %s, %s, %s, %s, %s,
    %s, %s,          -- rating e total_ratings da loja (nao e Vivino)
    %s, %s, %s,
    %s,
    NULL, 'estimated', 'estimated'  -- sem nota WCF (nao tem reviews Vivino)
)
RETURNING id;
```

Depois criar wine_sources para o novo vinho.

### Threshold de confianca para importar

- `confidence >= 0.80` → importar match (criar wine_sources)
- `confidence >= 0.70 AND < 0.80` → importar mas marcar como `match_type = 'uncertain'` no wine_sources
- `confidence < 0.70` → tratar como no_match (inserir vinho novo)
- `match_type = 'no_match'` → inserir vinho novo

### Vinhos novos — campos especiais

Para vinhos novos (sem match no Vivino):
- `vivino_rating` = rating da loja (se existir), senao NULL
- `vivino_reviews` = total_ratings da loja (se existir), senao 0
- `nota_wcf` = NULL (sera calculado depois se tiver reviews)
- `confianca_nota` = 'estimated'
- `winegod_score_type` = 'estimated'
- `winegod_score` = NULL (sera calculado depois)
- `nome_normalizado` = ja normalizado na Fase 1

### Mapear lojas (store_id)

As lojas ja foram importadas pro Render na tabela `stores` (Chat I — 12,776 lojas). Para encontrar o store_id:
```sql
SELECT id FROM stores WHERE dominio = %s LIMIT 1;
```

Se a loja nao existir no Render, inserir:
```sql
INSERT INTO stores (nome, dominio, pais) VALUES (%s, %s, %s)
ON CONFLICT (dominio) DO NOTHING
RETURNING id;
```

## PERFORMANCE

- Processar em batches de 1000
- Usar executemany para INSERTs
- Para vinhos novos: INSERT retornando ID, depois criar wine_sources
- Progresso: `[IMPORT] 50000/800000 — 30000 sources criados, 20000 vinhos novos`
- Tempo estimado: 1-2h

## ARQUIVO A CRIAR

### scripts/import_to_render.py (NOVO)

## O QUE NAO FAZER

- **NAO deletar dados existentes no Render** — so adicionar
- **NAO modificar nota_wcf ou winegod_score de vinhos existentes**
- **NAO importar vinhos com confidence < 0.70 como match** — tratar como novos
- **NAO fazer git commit/push** — avisar quando terminar
- **NAO importar duplicatas** — usar ON CONFLICT DO NOTHING

## COMO TESTAR

1. Testar com 1 pais:
```bash
cd scripts && python import_to_render.py --pais ar --dry-run
```
(dry-run: mostra o que faria sem executar)

2. Verificar no Render apos importacao:
```sql
SELECT COUNT(*) FROM wines;                    -- deve ter aumentado
SELECT COUNT(*) FROM wine_sources;             -- deve ter aumentado muito
SELECT COUNT(*) FROM stores;                   -- pode ter aumentado um pouco
SELECT pais_nome, COUNT(*) FROM wines WHERE nota_wcf IS NULL GROUP BY pais_nome LIMIT 10;  -- vinhos novos
```

3. Rodar completo:
```bash
cd scripts && python import_to_render.py
```

## ENTREGAVEL

- `scripts/import_to_render.py`
- Relatorio final:
  - Quantos vinhos com match → wine_sources criados
  - Quantos vinhos novos inseridos
  - Quantos stores novos criados
  - Total de wine_sources no Render antes/depois
  - Total de wines no Render antes/depois

## REGRA DE COMMIT

Commitar APENAS os arquivos que VOCE criou/modificado nesta sessao. NUNCA incluir arquivos de outros chats. Fazer `git pull` antes de `git push`.
