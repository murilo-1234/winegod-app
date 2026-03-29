INSTRUCAO: Execute tudo diretamente. NAO pergunte se pode comecar. NAO peca confirmacao. Leia este prompt e implemente imediatamente.

# CHAT Y — Fase 3: Match Vinhos de Lojas x Vivino (1.72M)

## CONTEXTO

A Fase 2 (Chat X) deduplicou 4.17M vinhos de lojas e salvou os vinhos unicos na tabela `wines_unique` no banco local (~800K-1.5M vinhos unicos). Agora precisamos cruzar esses vinhos com os 1.72M vinhos do Vivino que estao no banco Render.

O objetivo e descobrir:
- **Match garantido**: mesmo vinho, linkar ao wine_id do Vivino
- **Match provavel**: provavelmente o mesmo, aceitar com validacao
- **Sem match**: vinho novo que o Vivino nao tem

## SUA TAREFA

Criar um script que:
1. Le `wines_unique` do banco local
2. Compara com a tabela `wines` do banco Render (1.72M vinhos Vivino)
3. Salva resultados na tabela `wines_matched` no banco local

## CREDENCIAIS

```
# Banco local (wines_unique)
WINEGOD_LOCAL_URL=postgresql://postgres:XXXXXXXXX@localhost:5432/winegod_db

# Banco Render (wines do Vivino)
DATABASE_URL=postgresql://winegod_user:XXXXXXXXX@dpg-XXXXXXXXX.oregon-postgres.render.com/winegod
```

## TABELA DE ORIGEM

`wines_unique` (banco local) — criada pela Fase 2:
- `id`, `nome_limpo`, `nome_normalizado`
- `produtor`, `produtor_normalizado`
- `safra`, `tipo`, `pais`, `regiao`
- `rating_melhor`, `total_ratings_max`
- `preco_min_global`, `preco_max_global`, `moeda_referencia`
- `url_imagem`, `hash_dedup`, `ean_gtin`
- `total_copias`, `clean_ids`

`wines` (banco Render) — 1.72M vinhos Vivino:
- `id`, `nome`, `produtor`, `safra`, `tipo`
- `pais_nome`, `regiao`, `sub_regiao`
- `vivino_rating`, `vivino_reviews`
- `nome_normalizado` (com indice pg_trgm)
- `nota_wcf`, `winegod_score`

## TABELA DE DESTINO

```sql
CREATE TABLE IF NOT EXISTS wines_matched (
    id SERIAL PRIMARY KEY,
    unique_id INTEGER NOT NULL REFERENCES wines_unique(id),
    match_type VARCHAR(20) NOT NULL,      -- 'exact_hash', 'exact_name', 'fuzzy_name', 'producer_vintage', 'no_match'
    vivino_wine_id INTEGER,               -- ID na tabela wines do Render (NULL se no_match)
    confidence REAL,                       -- 0.0 a 1.0
    match_details JSONB,                   -- detalhes do match (similarity score, campos que bateram)
    UNIQUE(unique_id)
);

CREATE INDEX idx_wm_type ON wines_matched (match_type);
CREATE INDEX idx_wm_vivino ON wines_matched (vivino_wine_id) WHERE vivino_wine_id IS NOT NULL;
CREATE INDEX idx_wm_confidence ON wines_matched (confidence);
```

## ALGORITMO DE MATCHING (Cascading Rules)

Processar por pais para limitar o espaco de busca.

### Pre-carga: Baixar dados do Render para memoria

Para cada pais, baixar do Render:
```sql
SELECT id, nome, nome_normalizado, produtor, safra, tipo
FROM wines
WHERE pais_nome = %s
```
Montar dicts em memoria para busca rapida:
- `render_by_name[nome_normalizado]` = list of wines
- `render_by_producer_vintage[(produtor_lower, safra)]` = list of wines

### Nivel 1 — Match exato por nome_normalizado + safra (100% confianca)
```python
key = (wine_unique.nome_normalizado, wine_unique.safra)
# Buscar no dict render_by_name
candidates = render_by_name.get(wine_unique.nome_normalizado, [])
for c in candidates:
    if c.safra == wine_unique.safra or (c.safra is None and wine_unique.safra is None):
        match(wine_unique, c, type='exact_name', confidence=1.0)
```

### Nivel 2 — Match por produtor + safra + tipo (95% confianca)
```python
if wine_unique.produtor_normalizado:
    candidates = render_by_producer_vintage.get(
        (wine_unique.produtor_normalizado, wine_unique.safra), []
    )
    for c in candidates:
        if c.tipo == wine_unique.tipo:
            match(wine_unique, c, type='producer_vintage', confidence=0.95)
```

### Nivel 3 — Match fuzzy por nome (via pg_trgm no Render, 80%+ confianca)
APENAS para vinhos que NAO bateram nos niveis 1-2. Usar pg_trgm do Render:
```sql
SELECT id, nome, nome_normalizado, safra,
       similarity(nome_normalizado, %s) as sim
FROM wines
WHERE pais_nome = %s
  AND nome_normalizado %% %s
  AND similarity(nome_normalizado, %s) > 0.7
ORDER BY sim DESC
LIMIT 3
```
- Similarity > 0.85 + mesma safra → confidence 0.90
- Similarity > 0.85 sem safra → confidence 0.80
- Similarity 0.7-0.85 + mesma safra → confidence 0.70

**CUIDADO com performance**: NAO rodar fuzzy para todos os vinhos. So para os que nao bateram nos niveis 1-2. Limitar a 1000 queries fuzzy por pais (pegar os mais importantes por total_ratings).

### Nivel 4 — Sem match
Vinhos que nao bateram em nenhum nivel → `match_type = 'no_match'`, `confidence = 0.0`

## PERFORMANCE

- Processar por pais (reduz espaco de busca drasticamente)
- Pre-carregar dados do Render por pais em memoria (evitar queries individuais)
- Niveis 1-2 sao in-memory (rapido)
- Nivel 3 (fuzzy) so para vinhos restantes, limitado
- INSERT resultados em batches de 1000
- Progresso: `[AR] 12000 exact, 3400 producer, 890 fuzzy, 98000 no_match`
- Tempo estimado: 2-3h (maior parte e o fuzzy no Render)

## ARQUIVO A CRIAR

### scripts/match_vivino.py (NOVO)

## O QUE NAO FAZER

- **NAO modificar nenhuma tabela no Render** — so ler
- **NAO modificar wines_unique** — so ler
- **NAO fazer git commit/push** — avisar quando terminar
- **NAO rodar fuzzy pra todos os vinhos** — so pros que nao bateram em nivel 1-2
- **NAO confiar no campo vinicola_nome** — e dominio da loja

## COMO TESTAR

```bash
cd scripts && python match_vivino.py --pais ar
# Verificar:
psql -h localhost -U postgres -d winegod_db -c "
SELECT match_type, COUNT(*), ROUND(AVG(confidence)::numeric, 2) as avg_conf
FROM wines_matched
GROUP BY match_type
ORDER BY COUNT(*) DESC;
"
```

## ENTREGAVEL

- `scripts/match_vivino.py`
- Tabela `wines_matched` populada
- Relatorio: quantos em cada categoria (exact, producer, fuzzy, no_match)
- Estatisticas de confianca

## REGRA DE COMMIT

Commitar APENAS os arquivos que VOCE criou/modificou nesta sessao. NUNCA incluir arquivos de outros chats. Fazer `git pull` antes de `git push`.
