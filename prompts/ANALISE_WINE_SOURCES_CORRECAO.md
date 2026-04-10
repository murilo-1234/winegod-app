# Analise Completa: Wine Sources — Problema e Plano de Correcao

Data: 2026-04-06

---

## 1. CONTEXTO — O que foi feito

O script `scripts/import_render_z.py` (Chat Z) importou dados do banco LOCAL para o Render:

- **Fase 1**: Criou wine_sources para 1.05M vinhos matched (score >= 0.5)
- **Fase 2**: Inseriu ~60K wines novos + wine_sources
- **Fase 3**: Enriqueceu 330K wines existentes (campos NULL preenchidos com COALESCE)

### Resultado no Render AGORA

| Metrica | Antes (pre-import) | Depois (atual) |
|---|---|---|
| wines | 1,727,058 | 2,506,440 |
| wine_sources | 66,216 | 2,425,587 |
| stores | 12,776 | 12,776 |
| wines com >= 1 source | ~50K | 262,277 |

---

## 2. PROBLEMA CRITICO — Wine Sources com Mapeamento ERRADO

### O que aconteceu

O script carregava fontes (URLs de lojas) usando o mapeamento:

```
fontes_map[vinho_id] = [(url, preco, moeda)]
```

Onde `vinho_id` vinha direto de `vinhos_XX_fontes.vinho_id`.

Depois buscava fontes usando:

```python
fontes = fontes_map.get(clean_id)  # clean_id = wines_clean.id
```

**O ERRO**: `vinhos_br_fontes.vinho_id` aponta para `vinhos_br.id`, que e DIFERENTE de `wines_clean.id`. Os IDs se sobrepoe por acidente (ambos sao sequenciais), mas representam vinhos completamente diferentes.

### Prova do erro

```
vinhos_br.id = 1     → "Catena Zapata Adrianna River Stones 2018"
wines_clean.id = 1   → "Spring Sunshine 80"
```

### Exemplo de wine_source ERRADO no Render

```
wine_source.wine_id = 648239 → wine "Rich Red Blend"
wine_source.url = "https://vinogrande.pt/products/kopke-fine-tawny"  ← URL de OUTRO vinho
```

### Escala do problema

- **1,269,433 wine_sources criados por nos** (descoberto_em >= 2026-04-05) — MAIORIA ERRADOS
- **1,156,154 wine_sources originais** (pre-existentes) — estes estao CORRETOS
- Total: 2,425,587

---

## 3. MAPEAMENTO CORRETO — Como funciona

### Cadeia de IDs no banco LOCAL

```
lojas_scraping          → 86,089 lojas (84,631 importadas)
    ↓ scraping
vinhos_XX               → 50 tabelas por pais (vinhos_br, vinhos_us, etc.)
    ↓ cada vinho tem fontes
vinhos_XX_fontes        → 4,849,614 registros com URL, preco, moeda
    ↓ deduplicacao
wines_clean             → 3,962,334 vinhos unicos
    ↓ classificacao IA (Chat Y)
y2_results              → 3,961,222 classificados
    ↓ matching
vivino_match            → 1,727,058 vinhos Vivino (espelho do Render)
```

### Chave do mapeamento

`wines_clean` tem dois campos criticos:

| Campo | Significado |
|---|---|
| `wines_clean.id` | ID PROPRIO sequencial (1 a 4,097,727) |
| `wines_clean.pais_tabela` | Pais de origem: 'br', 'us', 'de', etc. |
| `wines_clean.id_original` | ID na tabela vinhos_XX de origem |

**Mapeamento CORRETO:**

```
wines_clean.id = 496154
wines_clean.pais_tabela = 'br'
wines_clean.id_original = 572556
    → vinhos_br_fontes WHERE vinho_id = 572556
    → URL: https://www.vinatobr.com/vinho-brasileiro-50
    → Preco: R$ 59.00
```

**Mapeamento ERRADO (o que o script usava):**

```
wines_clean.id = 496154
    → vinhos_XX_fontes WHERE vinho_id = 496154  ← VINHO DIFERENTE!
    → URL de outro vinho completamente diferente
```

### Cobertura com mapeamento correto

```
vinhos_XX_fontes totais:     4,849,614 registros (99.9% dos vinhos_XX)
Mapeaveis para wines_clean:  3,953,913 (81.6%)
```

---

## 4. PROBLEMA SECUNDARIO — Lojas faltando no Render

### Stores no Render vs Lojas no Local

| Fonte | Quantidade |
|---|---|
| lojas_scraping (local) | 86,089 total |
| Tier 1 (tier_usado=1) | 11,585 (11,572 com vinhos extraidos) |
| Tier 2 (tier_usado=2) | 8,180 (6,454 com vinhos extraidos) |
| Tier 2 elegivel (dashboard) | 27,313 (14,392 finalizadas = 52.7%) |
| Tier 3 | 87 |
| **Lojas com vinhos reais** | **18,026** (T1 + T2 com vinhos) |
| stores no Render | 12,776 |

NOTA: O dashboard mostra numeros diferentes porque calcula "elegivel" e "finalizado" com criterios proprios. O campo `tier_usado` na tabela indica qual tier FOI USADO no scraping. O dashboard conta tambem lojas que PODERIAM ser tier 2 mas ainda nao rodaram.

### Gap de dominios

```
Dominios unicos nas fontes (vinhos_XX_fontes): 17,525
Dominios ja no Render (stores):                12,776  (72.9%)
Dominios FALTANDO no Render:                    6,001  (27.1%)
```

Especificamente das lojas Tier 1+2:
```
Dominios Tier 1+2:     19,509
Ja no Render:          12,701
FALTANDO:               6,808
```

**Impacto**: Quando o script tenta criar um wine_source mas o dominio da URL nao tem loja correspondente no Render, o wine_source NAO e criado. Na Fase 1 original, 453,014 fontes foram perdidas por "sem loja".

---

## 5. CADEIA COMPLETA: Vinho na Loja → wine_source no Render

Para um wine_source existir no Render, TODA esta cadeia precisa funcionar:

```
1. Loja existe em lojas_scraping             ✅ 86K lojas
2. Loja foi importada para stores no Render  ⚠️  So 12.7K de 19.5K tier 1+2
3. Vinho foi scraped (vinhos_XX)             ✅ 4.85M vinhos
4. URL salva em vinhos_XX_fontes             ✅ 99.9% cobertura
5. Vinho esta em wines_clean                 ✅ 3.96M
6. Vinho classificado em y2_results          ✅ matched ou new
7. Mapeamento clean_id → id_original correto ✅ CORRIGIDO no script
8. Dominio da URL existe em stores           ⚠️  6.8K dominios faltando
9. y2_results.vivino_id correto (= wines.id) ✅ CORRIGIDO no script
```

**Pontos de falha**: passos 2 e 8 (lojas faltando no Render).

---

## 6. NUMEROS DO DASHBOARD (Winegod Codex)

```
Discovery:          84,633 lojas descobertas
Importadas:         84,631 / 84,633 (100%)
Classificadas:      86,089 / 86,089 (100%)
Tier 1 finalizado:  11,539 / 11,539 (100%)
Tier 2 finalizado:  14,392 / 27,313 (52.7%)
Tier 2 pendente:    12,899

Vinhos bruto:       4,863,891
wines_clean:        3,962,334
Vinhos novos:       901,557 (ainda nao na wines_clean)

y2_results:
  matched:      1,465,480 (55%) — casaram com Vivino
  new:            827,593 (31%) — vinhos novos (nao existem no Vivino)
  not_wine:     1,039,952 (26%) — nao sao vinhos
  duplicate:      350,281 (13%) — duplicatas
  spirit:         108,780 (3%)  — destilados
  error:          169,136 (4%)  — erros de classificacao
```

### Vinhos que DEVEM ter link de loja

**2,293,073** vinhos (matched + new) foram scraped de lojas reais. Cada um DEVE ter pelo menos 1 wine_source no Render conectando-o a loja de onde foi extraido.

---

## 7. PLANO DE CORRECAO (5 passos)

### Passo 1 — Deletar wine_sources ERRADOS

```sql
-- ANTES de deletar: confirmar amostra (10 segundos)
SELECT ws.id, ws.wine_id, ws.url, w.nome
FROM wine_sources ws JOIN wines w ON w.id = ws.wine_id
WHERE ws.descoberto_em >= '2026-04-05'
ORDER BY RANDOM() LIMIT 20;
-- Conferir: as URLs batem com os nomes dos vinhos? Se NAO batem → confirma que sao errados.

-- Deletar
DELETE FROM wine_sources WHERE descoberto_em >= '2026-04-05';
-- Esperado: ~1,269,433 deletados
-- Manter: ~1,156,154 originais
```

### Passo 2 — Importar lojas faltantes pro Render

**ANTES: verificar schema da tabela stores no Render:**
```sql
SELECT column_name, data_type, is_nullable, character_maximum_length
FROM information_schema.columns
WHERE table_name = 'stores' ORDER BY ordinal_position;
-- Verificar: quais campos sao NOT NULL? Tem UNIQUE em dominio?
```

Criar script que:
1. Le `lojas_scraping` do LOCAL (tier 1 e tier 2 com vinhos extraidos)
2. Extrai dominio de `url_normalizada`
3. Verifica se dominio ja existe em `stores` do Render
4. INSERT das lojas faltantes (~5-6K lojas) com ON CONFLICT DO NOTHING

Campos a mapear: `lojas_scraping.nome` → `stores.nome`, `url_normalizada` → `stores.url`, dominio extraido → `stores.dominio`, `pais_codigo` → `stores.pais`

### Passo 3 — Re-rodar Fase 1 (matched → wine_sources)

Com o mapeamento CORRETO (`pais_tabela` + `id_original`):
- Input: 1,465,480 matched (score >= 0.5)
- Para cada: buscar fontes via `wines_clean.id_original` → `vinhos_XX_fontes`
- Criar wine_sources com `wine_id = y2_results.vivino_id` (= wines.id no Render)
- Estimativa: ~30-60 minutos

### Passo 4 — Re-rodar Fase 2 (new → wine_sources)

Wines novos ja estao inseridos (ON CONFLICT pega). So cria wine_sources faltantes.
- Input: 827,593 new
- Estimativa: ~30 minutos com 4 workers

### Passo 5 — Verificar (quantidade + qualidade)

```sql
-- 5a. Contagem
SELECT COUNT(DISTINCT wine_id) FROM wine_sources;
-- Esperado: ~1.5M - 2M (vs 262K atual)

-- 5b. Verificacao qualitativa: 10 amostras aleatorias
-- Conferir se URL bate com o vinho (abrir URL no browser)
SELECT w.nome, w.produtor, ws.url, s.nome as loja, ws.preco, ws.moeda
FROM wine_sources ws
JOIN wines w ON w.id = ws.wine_id
JOIN stores s ON s.id = ws.store_id
WHERE ws.descoberto_em >= '2026-04-06'
ORDER BY RANDOM() LIMIT 10;

-- 5c. Cobertura por pais
SELECT w.pais, COUNT(DISTINCT ws.wine_id) as wines_com_link
FROM wine_sources ws
JOIN wines w ON w.id = ws.wine_id
GROUP BY w.pais ORDER BY COUNT(*) DESC LIMIT 20;
```

NOTA sobre numeros: 1.05M (Fase 1) = matched com score >= 0.5. O total matched e 1.46M mas a Fase 1 filtra por score. A Fase 3 usa score >= 0.7 (648K).

---

## 8. ONDE ENCONTRAR OS DADOS (referencia)

### Banco LOCAL (PostgreSQL localhost:5432, winegod_db)

| Tabela | Descricao | Registros |
|---|---|---|
| `wines_clean` | Vinhos deduplicados de todas as lojas | 3,962,334 |
| `y2_results` | Classificacao IA de cada vinho | 3,961,222 |
| `vivino_match` | Espelho dos vinhos Vivino (= wines.id do Render) | 1,727,058 |
| `vinhos_XX` | Vinhos por pais (50 tabelas) | ~4.85M total |
| `vinhos_XX_fontes` | URLs de lojas por pais (50 tabelas) | ~5.6M registros |
| `lojas_scraping` | Todas as lojas descobertas | 86,089 |
| `wines_unique` | Vinhos unicos (agrupados por hash) | ~900K |

### Banco RENDER (PostgreSQL Render, Oregon)

| Tabela | Descricao | Registros |
|---|---|---|
| `wines` | Todos os vinhos (Vivino + novos) | 2,506,440 |
| `stores` | Lojas cadastradas | 12,776 |
| `wine_sources` | Links vinho ↔ loja (com preco) | 2,425,587 (1.27M ERRADOS) |

### Conexoes

```
LOCAL:  host=localhost port=5432 dbname=winegod_db user=postgres password=postgres123
RENDER: <DATABASE_URL_FROM_ENV>
```

### Scripts relevantes

```
C:\winegod-app\scripts\import_render_z.py   — Script de import (JA CORRIGIDO o mapeamento)
C:\winegod-app\prompts\PROMPT_CHAT_Z_IMPORT_RENDER_V2.md — Prompt original
```

### Como verificar o mapeamento CORRETO

```sql
-- No banco LOCAL: confirmar que wines_clean.id_original mapeia corretamente
SELECT wc.id as clean_id, wc.pais_tabela, wc.id_original,
       wc.nome_normalizado as nome_clean,
       v.nome_normalizado as nome_vinhos_br
FROM wines_clean wc
JOIN vinhos_br v ON v.id = wc.id_original
WHERE wc.pais_tabela = 'br'
LIMIT 5;
-- Os nomes devem ser iguais ou muito similares

-- Buscar fontes de um vinho especifico
SELECT f.url_original, f.preco, f.moeda
FROM vinhos_br_fontes f
WHERE f.vinho_id = (SELECT id_original FROM wines_clean WHERE id = 496154 AND pais_tabela = 'br');
```

### Como a funcao carregar_fontes_locais CORRIGIDA funciona

```python
# 1. Carrega mapa: (pais, id_original) → clean_id
SELECT id, pais_tabela, id_original FROM wines_clean

# 2. Para cada tabela vinhos_XX_fontes:
#    - Extrai pais do nome da tabela (vinhos_br_fontes → 'br')
#    - Para cada fonte: busca clean_id via orig_to_clean[(pais, vinho_id)]
#    - Resultado: fontes_map[clean_id] = [(url, preco, moeda)]
```

---

## 9. WINES NOVOS — Estao corretos?

Os ~60K wines novos inseridos na Fase 2 vieram de `wines_clean` e usaram os campos corretos:
- `nome_limpo`, `nome_normalizado`, `produtor_extraido` → do wines_clean (correto)
- `pais`, `cor`, `safra`, etc. → do y2_results (classificacao IA, correto)
- `hash_dedup` → do wines_clean (correto)
- O vinho em si esta CORRETO

O problema e APENAS nos wine_sources (URLs) que foram associados a eles com o mapeamento errado.

---

## 10. RESUMO EXECUTIVO

**Situacao**: Importamos 2.5M wines pro Render, mas os links vinho↔loja (wine_sources) estao majoritariamente ERRADOS por um bug no mapeamento de IDs.

**Causa raiz**: `wines_clean.id` ≠ `vinhos_XX.id`. O campo correto e `wines_clean.id_original` + `wines_clean.pais_tabela`.

**Impacto**: Baco mostraria precos/links de lojas ERRADOS para os usuarios.

**Correcao**: 5 passos — deletar sources errados, importar lojas faltantes, re-rodar com mapeamento correto.

**Tempo estimado**: ~2 horas de execucao total.

**Resultado esperado**: ~1.5-2M wines com link correto de loja (vs 262K hoje, dos quais a maioria esta errada).

---

## 11. ARMADILHAS — Erros que cometemos e que voce NAO deve repetir

Estas sao licoes aprendidas ao longo de ~12 horas de trabalho. Leia ANTES de escrever qualquer codigo.

### Armadilha 1: y2_results.vivino_id NAO e o vivino_id real

`y2_results.vivino_id` armazena o `wines.id` do Render (chave primaria sequencial), NAO o vivino_id real do Vivino. Isso acontece porque o matching foi feito contra a tabela `vivino_match`, onde `vivino_match.id = wines.id` do Render.

**ERRADO**: `SELECT id FROM wines WHERE vivino_id = y2_results.vivino_id`
**CORRETO**: `y2_results.vivino_id` JA E o `wines.id` do Render. Usar direto.

**Como confirmar**: 
```sql
-- No LOCAL: vivino_match.id = 9414
SELECT nome_normalizado FROM vivino_match WHERE id = 9414;
-- Resultado: "brunello di montalcino"

-- No RENDER: wines.id = 9414
SELECT nome_normalizado FROM wines WHERE id = 9414;
-- Resultado: "brunello di montalcino"  ← MESMO VINHO
```

### Armadilha 2: wines_clean.id ≠ vinhos_XX.id (A MAIOR armadilha)

Os IDs sao sequenciais independentes e SE SOBREPOE:
- `vinhos_br.id` vai de 1 a 606,201
- `vinhos_us.id` vai de 1 a 2,494,876
- `wines_clean.id` vai de 1 a 4,097,727

ID 100000 em `vinhos_br` e um vinho italiano vendido no Brasil.
ID 100000 em `wines_clean` e um sauvignon blanc culto de 2019.
SAO VINHOS COMPLETAMENTE DIFERENTES.

**ERRADO**: `vinhos_br_fontes WHERE vinho_id = wines_clean.id`
**CORRETO**: `vinhos_br_fontes WHERE vinho_id = wines_clean.id_original` (quando `wines_clean.pais_tabela = 'br'`)

**Como confirmar**:
```sql
SELECT wc.id, wc.pais_tabela, wc.id_original, wc.nome_normalizado,
       vb.nome_normalizado
FROM wines_clean wc
JOIN vinhos_br vb ON vb.id = wc.id_original
WHERE wc.pais_tabela = 'br'
LIMIT 3;
-- Os nomes devem ser iguais (ou muito proximos)
```

### Armadilha 3: wines_clean.fontes esta VAZIO pra 96% dos vinhos

O campo `wines_clean.fontes` contem `'[]'` ou nomes de plataforma (`'["vtex_io"]'`), NAO URLs.
As URLs reais estao APENAS nas tabelas `vinhos_XX_fontes`.

```
wines_clean com fontes preenchidas:   149,204 (3.8%)
wines_clean sem fontes:             3,813,130 (96.2%)
vinhos_XX_fontes com URL:           4,849,614 (99.9% dos vinhos_XX)
```

NAO use `wines_clean.fontes`. Use SEMPRE `vinhos_XX_fontes` via `id_original`.

### Armadilha 4: Render tem NOT NULL em hash_dedup

A tabela `wines` no Render tem constraint NOT NULL na coluna `hash_dedup`. Se `wines_clean.hash_dedup` for NULL, o INSERT falha. Solucao: gerar um hash MD5 de `produtor + nome + safra` como fallback.

```python
import hashlib
def gerar_hash_dedup(nome_normalizado, produtor_normalizado, safra):
    chave = f"{produtor_normalizado or ''}|{nome_normalizado or ''}|{safra or ''}"
    return hashlib.md5(chave.encode()).hexdigest()
```

### Armadilha 5: Campos com overflow numerico/varchar

Dados do scraping podem ter valores fora dos limites das colunas do Render:
- `pais` e VARCHAR(2) — alguns vinhos tem pais com 3+ chars
- `teor_alcoolico` e NUMERIC(4,1) — max 999.9, alguns tem 1234
- `preco_min/preco_max` e NUMERIC(10,2) — max 99999999.99
- `safra` e VARCHAR(20) — alguns tem texto longo

**Sempre sanitizar antes de INSERT:**
```python
pais_safe = pais[:2] if pais and len(pais) > 2 else pais
abv_float = None if abv_float and (abv_float > 100 or abv_float < 0) else abv_float
preco_safe = preco if preco and preco < 99999999 else None
```

### Armadilha 6: Conexao Render cai com operacoes longas

O Render (plano Basic) derruba conexoes ociosas ou muito longas. Solucao:
- Usar `keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=5`
- Implementar retry com reconexao automatica (3 tentativas)
- Commit a cada batch, NAO acumular transacao gigante

### Armadilha 7: INSERT individual no Render e extremamente lento

Latencia Brasil→Oregon ~100ms. INSERT individual = ~2/seg = 115 horas pra 827K vinhos.
Solucao: usar `execute_values` do psycopg2 (batch de 1000) + workers paralelos (4 threads).
Resultado: ~86/seg = ~2.5 horas.

### Armadilha 8: Stores faltantes = wine_sources perdidos silenciosamente

Se o dominio da URL nao existe na tabela `stores` do Render, o wine_source NAO e criado (precisa de FK `store_id`). Nao da erro — simplesmente pula. Na Fase 1 original, 453,014 fontes foram perdidas assim.

**IMPORTANTE**: Importar lojas faltantes ANTES de rodar as Fases 1 e 2.

---

## NOTA IMPORTANTE: O Passo 1 (DELETE) nao esta no script

O script `import_render_z.py` so tem `--check`, `--fase 1/2/3/all`. NAO tem flag de cleanup.
O DELETE precisa ser rodado **MANUALMENTE** via SQL direto no Render, ANTES de rodar o script.

Ordem de execucao:
1. Rodar SELECT amostra (confirmar que sources sao errados)
2. Rodar DELETE via SQL direto
3. Rodar script Passo 2 (importar lojas — script separado a criar)
4. Rodar `python scripts/import_render_z.py --fase 1 --dry-run --limite 10000` (validar numeros)
5. Rodar `python scripts/import_render_z.py --fase 1`
6. Rodar `python scripts/import_render_z.py --fase 2 --workers 4`
7. Verificacao (Passo 5)

---

## 12. PERGUNTAS QUE O NOVO CHAT DEVE RESPONDER ANTES DE EXECUTAR

1. **Os 1,156,154 wine_sources originais (pre-2026-04-05) estao corretos?** Verificar amostra.
2. **Os ~779K wines novos (Fase 2) tem os dados corretos?** Nome, produtor, pais vem de wines_clean (correto), mas confirmar com amostra.
3. **Quantos wine_sources o mapeamento correto REALMENTE gera?** Rodar Fase 1 com --dry-run --limite 10000 e ver o ratio.
4. **As 6,808 lojas faltantes — todas precisam ser importadas?** Ou algumas sao lixo (dominios invalidos)?
5. **Depois de corrigir, qual a cobertura esperada?** Meta: ~2.3M wines com pelo menos 1 link.

---

## 13. COMANDO PARA O NOVO CHAT

```
Leia C:\winegod-app\prompts\ANALISE_WINE_SOURCES_CORRECAO.md

Este documento descreve um problema critico no import de wine_sources para o Render.
O script C:\winegod-app\scripts\import_render_z.py ja foi CORRIGIDO (funcao carregar_fontes_locais).

Antes de executar qualquer coisa:
1. Leia a secao 11 (ARMADILHAS) inteira
2. Responda as 5 perguntas da secao 12
3. Valide o plano da secao 7 ou proponha alternativas
4. So execute depois de alinhar comigo

O banco LOCAL roda em localhost:5432 (winegod_db).
O banco RENDER roda na connection string do documento.
O dashboard esta em http://localhost:5568/ (Dash/Plotly, nao acessivel via fetch).
```
