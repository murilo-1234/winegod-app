INSTRUCAO: Execute tudo diretamente. NAO pergunte se pode comecar. NAO peca confirmacao. Leia este prompt E o documento V2 referenciado abaixo, e comece a trabalhar imediatamente na solucao.

# PRIORIDADE IMEDIATA — RESOLVER O CHAT Y (MATCH VIVINO)

Voce e o novo CTO do projeto WineGod.ai. Primeiro leia o documento completo do projeto em `C:\winegod-app\prompts\PROMPT_CTO_WINEGOD_V2.md`. Depois volte aqui. Sua **PRIORIDADE UNICA E IMEDIATA** e resolver o problema do Chat Y.

Comece pesquisando abordagens, teste com 100 vinhos que falharam (tabela match_results_g2 WHERE match_level='no_match'), e apresente resultados. NAO espere aprovacao pra comecar.

## O QUE ACONTECEU

As fases W (limpeza) e X (dedup) foram concluidas com sucesso:
- 4.17M vinhos de lojas → limpos → 3,955,624 em wines_clean
- 3.96M deduplicados → 2,942,304 unicos em wines_unique (Splink + deterministico)

O Chat Y (match vinhos de loja contra 1.72M vinhos Vivino) **FALHOU** com taxa de match de **0.6%** — deveria ser 40-60%.

## POR QUE FALHOU

O Vivino SEPARA produtor do nome. As lojas JUNTAM tudo:

```
Vivino:  produtor="Barefoot"    nome_normalizado="pinot grigio"
Loja:    nome_normalizado="barefoot pinot grigio"

Vivino:  produtor="Antinori"    nome_normalizado="solaia"
Loja:    nome_normalizado="2022 solaia"
```

Tentativas feitas e resultados:
1. Match exato nome_normalizado: **0.6%** (formatos incompativeis)
2. Concatenar produtor+nome do Vivino: **4%** (loja muitas vezes nao inclui produtor)
3. Splink fuzzy: **0%** (blocking rules incompativeis, nomes muito diferentes)

## O QUE VOCE PRECISA FAZER

1. **Pesquisar e avaliar** abordagens de entity resolution para dados desestruturados vs estruturados
2. **Testar com 100 vinhos** antes de rodar em escala (pegar da tabela match_results_g2 WHERE match_level='no_match')
3. **Atingir no minimo 30% de match** (idealmente 50%+)
4. **Gerar prompts paralelos** (8 abas) quando a solucao estiver validada

Abordagens sugeridas pelo CTO anterior (nenhuma foi testada ainda):
- Busca por palavras-chave (LIKE '%solaia%' + safra=2022)
- TF-IDF + cosine similarity
- pg_trgm similarity() no PostgreSQL
- Embeddings (sentence transformers)
- Combinar TODOS os campos do Vivino num texto unico pra comparar

Voce NAO esta limitado a essas sugestoes. Pesquise, teste, e encontre a melhor solucao. O fundador NAO e programador — explique simples, teste antes, e so escale quando funcionar.

## DADOS DISPONIVEIS

**Banco local (winegod_db):**
- `wines_unique`: 2,942,304 vinhos de loja (deduplicados)
  - Campos: id, nome_normalizado, nome_limpo, produtor_normalizado, safra, tipo, pais_tabela, regiao, hash_dedup, ean_gtin
- `wines_clean`: 3,955,624 vinhos limpos (antes do dedup)
- `match_results_g2`: 196K resultados do teste Y2 (99.4% no_match) — usar pra testar

**Banco Render (winegod):**
- `wines`: 1,727,058 vinhos Vivino
  - Campos: id, nome, nome_normalizado, produtor, produtor_normalizado, safra (VARCHAR), tipo, pais (codigo), pais_nome, regiao, uvas (JSONB), vivino_id, vivino_rating, vivino_reviews, hash_dedup, ean_gtin
  - IMPORTANTE: nome_normalizado do Vivino NAO inclui o produtor (sao campos separados)

**Credenciais: ver .env no projeto ou a secao CREDENCIAIS do documento abaixo.**

## REGRAS

- Testar com amostra pequena (100-1000) ANTES de rodar em escala
- Medir taxa de match e mostrar exemplos pro fundador validar
- Se a abordagem nao funcionar, tentar outra — nao insistir
- Quando funcionar, dividir em 8 abas paralelas (regra de paralelizacao do projeto)
- NAO modificar tabelas existentes — criar tabelas novas pra resultados
- NAO fazer commit/push sem pedir ao fundador

---

# DOCUMENTO COMPLETO DO PROJETO (CTO V2)

Leia o arquivo completo do projeto aqui:

```
Leia o arquivo: C:\winegod-app\prompts\PROMPT_CTO_WINEGOD_V2.md
```
