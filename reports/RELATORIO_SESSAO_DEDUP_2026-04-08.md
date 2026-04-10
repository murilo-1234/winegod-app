# Relatorio de Sessao -- Correcao Dedup/Matching

Data: 2026-04-08 (atualizado 2026-04-09 pos prova operacional v2)

## Resumo

Prova operacional executada contra o banco Render (2.5M wines).
Regressao da busca (v1) foi corrigida com complemento por tokens.
Fase 0: **APROVADA.** Busca, cache e UX aprovados. Deploy autorizado.
Fase 1 parcialmente preparada. Fase 2 com runbook.

---

## FASE 0 -- Status: APROVADA E DEPLOYADA.

### 0.1 Pipeline Y2/Z ativo?

O repositorio nao mostra scheduler integrado (sem Procfile, render.yaml, Celery, APScheduler instanciado, cron configurado). Os scripts de import (import_render_z.py, pipeline_y2.py) sao arquivos locais nao commitados, executados manualmente.

**Limitacao**: esta verificacao cobre apenas o que esta nos repos. Nao ha como confirmar daqui se existem jobs externos (ex: task agendada no Render dashboard, cron em outra maquina, ou execucao manual em andamento). Recomenda-se verificar o dashboard do Render e confirmar que nenhum job manual esta rodando antes de proceder.

### 0.2 Baseline capturado?

Script criado: `C:\winegod-app\scripts\baseline_fase0.py`

Importa e executa `search_wine()` diretamente de `backend/tools/search.py` -- mesma funcao que o app usa em producao. Nao usa query paralela propria.

Para executar:
```bash
cd C:\winegod-app
python scripts/baseline_fase0.py               # pre-hotfix
python scripts/baseline_fase0.py --pos          # pos-hotfix
python scripts/baseline_fase0.py --skip-local   # sem banco local
```

**Nao foi executado ainda.** Requer .env com DATABASE_URL configurada.

### 0.3 Bug do importador corrigido?

Arquivo: `C:\winegod-app\scripts\import_render_z.py`

Mudanca: linhas 336 e 361 (aproximadas), `match_score >= 0.0` corrigido para `match_score >= 0.5`.

O comentario da funcao ja dizia "FASE 1 -- Wine Sources dos Matched (score >= 0.5)" mas o SQL real usava `>= 0.0`. Agora codigo e comentario estao consistentes.

Verificado: as fases 3 (linhas 694, 722 aprox.) ja usavam `>= 0.7` corretamente.

Tambem adicionadas constantes no topo do script:
```python
THRESHOLD_AUTO = 0.7      # auto-match confiavel
THRESHOLD_SOURCES = 0.5   # wine_sources aceito
THRESHOLD_QUARANTINE = 0.5  # abaixo = quarentena
```

### 0.4 Busca corrigida?

Arquivo: `C:\winegod-app\backend\tools\search.py`

O search.py atual usa busca em 4 camadas (exact -> prefix -> producer -> fuzzy). Cada camada usa um ORDER BY para rankear resultados dentro daquela camada.

**O que foi implementado:**

Adicionada expressao `_CANONICAL_RANK` -- uma soma de 0 a 4, onde cada campo canonico nao-nulo (vivino_rating, nota_wcf, winegod_score, vivino_id) soma 1 ponto.

A `_ORDER_CLAUSE` usada pelas camadas 1-3 mudou de:
```sql
ORDER BY vivino_reviews DESC NULLS LAST, vivino_rating DESC NULLS LAST
```
para:
```sql
ORDER BY (soma_canonico) DESC, vivino_reviews DESC NULLS LAST, vivino_rating DESC NULLS LAST
```

A camada 4 (fuzzy) mudou de:
```sql
ORDER BY sim DESC, vivino_reviews DESC NULLS LAST
```
para:
```sql
ORDER BY sim DESC, (soma_canonico) DESC, vivino_reviews DESC NULLS LAST
```

**Efeito**: nas camadas 1-3, o primeiro criterio de ordenacao agora e a soma de sinais canonicos. Vinhos com mais dados (rating, score, vivino_id) aparecem antes de vinhos sem esses dados. Na camada fuzzy, similaridade textual continua como primeiro criterio, mas entre vinhos com mesma similaridade, o canonico aparece primeiro.

**Dependencia**: search.py importa `from tools.normalize import normalizar`. O arquivo `backend/tools/normalize.py` existe no disco mas **nao esta commitado no Git**. Precisa ser incluido no deploy.

### 0.5 Cache invalidado?

Arquivo: `C:\winegod-app\backend\services\cache.py`

Adicionada constante `CACHE_VERSION = 2`. A funcao `cache_key()` mudou de `wg:{prefix}:{hash}` para `wg:v{CACHE_VERSION}:{prefix}:{hash}`.

Chaves antigas com prefixo `wg:search:` ou `wg:details:` ficam orfas e expiram naturalmente pelo TTL (max 1h).

Para invalidar novamente no futuro: incrementar CACHE_VERSION.

**Nota**: o search.py refatorado ja usa cache key `"search_v2"` em vez de `"search"`, o que por si so ja invalida o cache antigo da busca. O CACHE_VERSION e uma camada adicional de seguranca.

### 0.6 UX fallback para vinho sem nota

Arquivo: `C:\winegod-app\backend\prompts\baco_system.py`

Adicionada instrucao na secao "NOTAS E SCORES":
- Vinho encontrado SEM nota (vivino_rating e nota_wcf ambos nulos): Baco diz que encontrou o vinho mas ainda nao tem nota verificada
- Nao inventa nota, nao pede desculpa

### 0.7 Revalidacao pos-hotfix

O script baseline_fase0.py suporta `--pos` para gerar relatorio pos-hotfix. Comparacao manual dos dois arquivos (`baseline_fase0.txt` vs `pos_hotfix_fase0.txt`).

Executado em 2026-04-09. Resultados salvos em:
- `reports/baseline_fase0.txt` (pre-hotfix)
- `reports/pos_hotfix_fase0.txt` (pos-hotfix)

---

## EVIDENCIA OPERACIONAL — Comparacao antes/depois

Fonte: dados extraidos dos arquivos salvos, nao de memoria.
- Pre-hotfix: `reports/baseline_fase0.txt`
- Pos-hotfix: `reports/pos_hotfix_fase0.txt`

### Ambiente
- Banco: Render PostgreSQL, 2,506,441 wines
- Pre-hotfix: search.py de origin/main (fuzzy pg_trgm, camada unica, ORDER BY sim DESC, reviews DESC)
- Pos-hotfix: search.py de HEAD (4 camadas exact/prefix/producer/fuzzy + _CANONICAL_RANK)

### Resultados por caso (exatamente como nos arquivos)

#### Dom Perignon

| | Pre (baseline_fase0.txt:10-32) | Pos (pos_hotfix_fase0.txt:7-12) |
|---|---|---|
| Resultados | 5 | 2 |
| Com rating | 0 de 5 | 0 de 2 |
| #1 | id=1844319 rating=None, 599.99 CAD | id=1800714 rating=None, 279.99 EUR |

Nenhuma versao canonica Vivino existe no banco para Dom Perignon.
Pre-hotfix retorna mais resultados (fuzzy mais permissivo) mas nenhum tem nota.
Sem regressao funcional — ambos retornam sem nota.

#### Finca Las Moras Cabernet Sauvignon

| | Pre (baseline_fase0.txt:34-56) | Pos (pos_hotfix_fase0.txt:14-17) |
|---|---|---|
| Resultados | 5 | 1 |
| Com rating | 3 de 5 | 0 de 1 |
| #1 | id=1803853 rating=None (loja) | id=1803853 rating=None (loja) |
| #3 | id=40743 **rating=3.4 wcf=3.46** "Las Moras Cabernet Sauvignon" (Bodega Finca Las Moras) | nao existe |

**REGRESSAO**: o pre-hotfix (fuzzy) encontra o canonico "Las Moras Cabernet Sauvignon" como #3 com rating=3.4. O pos-hotfix (exact) encontra apenas a versao loja e para, nunca chegando ao fuzzy onde o canonico apareceria.

#### Chaski Petit Verdot

| | Pre (baseline_fase0.txt:58-80) | Pos (pos_hotfix_fase0.txt:19-22) |
|---|---|---|
| Resultados | 5 | 1 |
| Com rating | 4 de 5 | 0 de 1 |
| #1 | id=94874 **rating=4.1 wcf=4.26 score=5.0** "Petit Verdot Chaski" (Perez Cruz) | id=1796520 rating=None "Chaski Petit Verdot 2019" (loja) |

**REGRESSAO**: o pre-hotfix (fuzzy) encontra o canonico Vivino como #1 com rating=4.1. O pos-hotfix (prefix) encontra apenas a versao loja (nome invertido: "Chaski Petit Verdot" vs "Petit Verdot Chaski") e para antes do fuzzy.

#### Luigi Bosca De Sangre Malbec

| | Pre (baseline_fase0.txt:82-104) | Pos (pos_hotfix_fase0.txt:24-27) |
|---|---|---|
| Resultados | 5 | 1 |
| Com rating | 0 de 5 | 0 de 1 |
| #1 | id=1814050 rating=None (loja) | id=1814050 rating=None (loja) |

Nenhuma versao canonica Vivino existe para o Malbec argentino.
Pre-hotfix retorna mais resultados mas nenhum com nota.
Sem regressao funcional — ambos retornam sem nota.

#### Perez Cruz Piedra Seca

| | Pre (baseline_fase0.txt:106-128) | Pos (pos_hotfix_fase0.txt:29-30) |
|---|---|---|
| Resultados | 5 | SSL error |
| Com rating | 2 de 5 (mas vinhos errados) | N/A |
| #2 | id=1433433 "Pedra Seca" rating=4.2 (Albet i Noya — vinho espanhol, nao o chileno) | N/A |

Pre-hotfix retorna resultados por fuzzy mas nenhum e o vinho correto.
Pos-hotfix falhou por SSL. Inconcluso.

### Analise: regressao confirmada em 2 de 5 casos

A busca em 4 camadas (exact/prefix/producer/fuzzy) para na primeira camada que retorna resultados. Isso causa regressao em pelo menos 2 casos onde o fuzzy antigo encontrava o canonico:

1. **Chaski**: fuzzy antigo encontrava "Petit Verdot Chaski" (canonico, rating=4.1) como #1. A busca nova para no prefix com "Chaski Petit Verdot 2019" (loja, sem nota).
2. **Finca Las Moras**: fuzzy antigo encontrava "Las Moras Cabernet Sauvignon" (canonico, rating=3.4) como #3. A busca nova para no exact com "FINCA LAS MORAS CABERNET SAUVIGNON" (loja, sem nota).

O _CANONICAL_RANK nao resolve isso porque opera dentro de cada camada, nao entre camadas. E a camada exact/prefix retorna antes de chegar ao fuzzy.

### Veredito Fase 0

| Criterio | Status |
|----------|--------|
| Pipeline de contaminacao parado | SIM (repo nao mostra scheduler; falta verificar dashboard Render) |
| Regra de auto-import fraco removida | SIM (>= 0.0 corrigido para >= 0.5) |
| Busca priorizando canonico com rating | NAO APROVADA — regressao em Chaski e Finca |
| Cache nao mascarando resultado | SIM (CACHE_VERSION=2) |
| Evidencia antes/depois coerente | SIM (arquivos salvos, referencias com numero de linha) |

### Decisao sobre search.py — historico

**v1 (Caminho B, 2026-04-09)**: search.py fora do deploy por regressao em Chaski e Finca.
A busca em 4 camadas parava no exact/prefix antes de encontrar canonicos com nome diferente.

**v2 (Caminho A executado, 2026-04-09)**: implementado complemento por tokens.
Quando exact/prefix retorna resultados mas nenhum tem sinal canonico, executa busca
adicional por LIKE com tokens individuais (cada palavra da query vira AND LIKE '%token%').
Se all-tokens nao acha canonico, tenta subsets com N-1 tokens.
Canonicos encontrados no complemento sobem ao topo do resultado final.
Protecao com statement_timeout de 5s para tokens comuns.

### Prova operacional v2 — resultados

Fonte: `reports/pos_hotfix_fase0_v2.txt`
Comparacao com: `reports/baseline_fase0.txt` (pre-hotfix) e `reports/pos_hotfix_fase0.txt` (v1)

| Caso | Baseline (pre) | v1 (regressao) | v2 (corrigido) | Veredito |
|------|----------------|----------------|----------------|----------|
| Chaski | #1 rating=4.1 (5 res) | #1 sem nota (1 res) | #1 rating=4.1 (2 res) | CORRIGIDO - igual ou melhor que baseline |
| Finca Las Moras | #3 rating=3.4 (5 res) | #1 sem nota (1 res) | #1 rating=3.4 (5 res, 3 com nota) | CORRIGIDO - MELHOR que baseline (canonico subiu de #3 para #1) |
| Dom Perignon | todos sem nota (5 res) | todos sem nota (2 res) | todos sem nota (5 res) | SEM REGRESSAO - lacuna de dados |
| Luigi Bosca | todos sem nota (5 res) | todos sem nota (1 res) | todos sem nota (5 res) | SEM REGRESSAO - lacuna de dados |
| Perez Cruz | nenhum correto (5 res) | SSL error | 0 resultados canonicos | SEM REGRESSAO - lacuna de dados confirmada |

### Veredito v2

| Criterio | Status |
|----------|--------|
| Chaski volta a mostrar canonico com rating | SIM — #1 com rating=4.1 |
| Finca volta a mostrar canonico com rating | SIM — #1 com rating=3.4 (melhor que baseline) |
| Dom Perignon nao piorou | SIM — mesma quantidade de resultados |
| Luigi Bosca nao piorou | SIM — mesma quantidade de resultados |
| Perez Cruz documentado | SIM — lacuna de dados, zero canonicos no banco |

**search.py v2: APROVADO para deploy.** Auditoria externa aprovou em 2026-04-09.
Base de prova: `reports/pos_hotfix_fase0_v2.txt`.

### Deploy aprovado — conjunto minimo (5 arquivos)

| # | Arquivo | Tipo | Mudanca |
|---|---------|------|---------|
| 1 | `backend/tools/search.py` | Modified | 4 camadas + _CANONICAL_RANK + complemento tokens |
| 2 | `backend/tools/normalize.py` | Novo (untracked) | Dependencia de search.py |
| 3 | `backend/services/display.py` | Novo (untracked) | Dependencia de search.py |
| 4 | `backend/services/cache.py` | Modified | CACHE_VERSION=2 |
| 5 | `backend/prompts/baco_system.py` | Modified | UX fallback vinho sem nota + regras display_note |

### Fora do deploy (scripts locais/manuais)

- `scripts/import_render_z.py` — threshold 0.0 -> 0.5 (corrigido localmente)

### Confirmacao de deploy (2026-04-09)

Os 5 arquivos estao commitados e pushados para origin/main.
Commits relevantes: 1b52f465, 9452fa17, 913be468.
Branch local sincronizado com remoto (nada ahead, nada behind).
Conteudo critico verificado no HEAD:
- _CANONICAL_RANK presente em search.py (linhas 22, 28, 220)
- _has_canonical, _search_tokens, _merge_results presentes
- Complemento por tokens ativo (linhas 94-104)
- CACHE_VERSION=2 em cache.py (linhas 20, 47)
Render auto-deploy a partir de origin/main.

### Validacao pos-deploy em producao (2026-04-09 16:03-16:05)

Codigo local = origin/main (commit a4801d99). DB = Render (2.5M wines).

| Caso | Camada | #1 | Resultado |
|------|--------|----| ---------|
| Chaski Petit Verdot | fuzzy+tokens | **rating=4.1 wcf=4.26 score=5.0** "Petit Verdot Chaski" (Perez Cruz) | VALIDADO |
| Finca Las Moras CS | exact+tokens | **rating=3.4 wcf=3.46 score=3.46** "Las Moras Cabernet Sauvignon" (Bodega Finca Las Moras) | VALIDADO |
| Dom Perignon | exact+tokens | sem nota (lacuna de dados — zero canonicos no banco) | SEM REGRESSAO |
| Luigi Bosca De Sangre | exact+tokens | sem nota (lacuna de dados — zero canonicos no banco) | SEM REGRESSAO |
| Perez Cruz Piedra Seca | none | 0 resultados (lacuna de dados + timeouts no DB Basic-256mb) | SEM REGRESSAO |

Commits adicionais de estabilizacao durante validacao:
- `56ef0af7`: _try_layer com rollback para evitar cascata de InFailedSqlTransaction
- `a4801d99`: token fallback roda em resultados vazios + rollback preventivo

**STATUS: VALIDADO EM PRODUCAO.**

---

## FASE 1 -- Status: ARTEFATOS PARCIALMENTE PREPARADOS

### 1.1 Matching com 3 estados

**Implementado no codigo**: constantes `THRESHOLD_AUTO`, `THRESHOLD_SOURCES`, `THRESHOLD_QUARANTINE` adicionadas ao `import_render_z.py`. Funcao `check()` atualizada para mostrar distribuicao nos 3 estados.

**Limitacao**: a logica de quarentena e apenas documental -- o script nao grava status 'quarantine' no y2_results. A classificacao em 3 estados depende do threshold no SELECT da Fase 1 (`match_score >= 0.5`), que agora esta correto.

### 1.2 Guardrails de owner

**Script criado**: `C:\winegod-app\scripts\guardrails_owner.py`

Contem:
- `is_producer_valid()` -- valida produtor (vazio, curto, generico)
- `has_type_conflict()` -- detecta conflito tinto/branco
- `validate_match_row()` -- validacao combinada
- Blocklist de 30+ produtores genericos
- Modo `--audit` para auditoria no Render
- Modo `--validate-y2` para validar y2_results

**NAO esta integrado no fluxo de import.** E um script autonomo de auditoria. Para integrar, seria necessario importar as funcoes no import_render_z.py e rejeitar matches com produtor invalido antes do INSERT.

### 1.3 Filtro de nao-vinhos

**Script criado**: `C:\winegod-app\scripts\wine_filter.py`

Regex centralizado com 100+ keywords em 15 categorias, word boundaries, multilingual. Testado com 18 casos de nao-vinho (100% bloqueados) e 10 vinhos reais (100% passaram).

**NAO esta integrado no pipeline Y2.** O pipeline usa LLM (Gemini Flash) para classificacao. O wine_filter.py pode ser usado como pre-filtro antes do LLM ou como validacao pos-classificacao, mas essa integracao nao foi feita.

### 1.4 Tabela wine_aliases

**Migration criada**: `C:\winegod\migrations\003_wine_aliases.sql`

Contem CREATE TABLE com: source_wine_id, canonical_wine_id, source_type, confidence, review_status, created_at. Indices e constraints incluidos.

**NAO foi aplicada no banco.** E uma migration pronta para execucao:
```bash
psql -U postgres winegod < C:\winegod\migrations\003_wine_aliases.sql
```

### 1.5 EAN/GTIN

Campo `ean_gtin VARCHAR(20)` existe no schema mas **nao esta populado** por nenhum pipeline ou scraper. Sem cobertura real, nao pode ser usado para dedup loja-loja agora.

### 1.6 URL Vivino

Campo `vivino_url TEXT` existe e e preenchido pela migration 002. Preservado no ON CONFLICT. Pode ser usado como regra deterministica (mesma URL = mesmo vinho). Cobertura real nao verificada (requer query no banco).

### 1.7 wines.fontes

Campo `fontes JSONB` existe, inicializado como `["vivino"]`. O backend (tools, routes, prompts) **nao le esse campo em nenhum ponto**. `wine_sources` e a tabela que rastreia linhagem real. Conclusao: `wines.fontes` e redundante, nao precisa backfillar.

---

### Descoberta: escopo real de wine_aliases (2026-04-09)

O mapeamento `clean_id -> wines.id Render` revelou que **98.8% dos matched >= 0.7
NAO tem wines.id proprio no Render**. Esses vinhos de loja entraram como wine_sources
(links para o canonico), nao como entradas wines separadas.

Consequencia: wine_aliases NAO e operacao em massa sobre 648k matched. O escopo real e:
- ~25% dos wines no Render (~627K) NAO tem vivino_id = foram materializados de loja
- Desses, os que sombreiam um canonico existente sao candidatos reais de alias
- O match NAO pode ser por hash_dedup (hashes sao diferentes entre loja e canonico)
- O match deve ser por similaridade de nome (tokens LIKE), igual ao complemento de busca

Validacao dos 5 casos criticos:
- Chaski: LOJA id=1796520 => CANONICO id=94874 rating=4.1 (score 0.435 - ALIAS)
- Finca: LOJA id=1803853 => CANONICO id=40743 rating=3.4 (score 0.460 - ALIAS)
- Dom Perignon: NENHUM canonico no banco (lacuna de dados)
- Luigi Bosca De Sangre: NENHUM canonico no banco (lacuna de dados)
- Perez Cruz Piedra Seca: nao testado (ausente do banco)

Proximo passo: rodar find_alias_candidates.py --sample sobre wines sem vivino_id
para medir volume real de duplicatas. Depende do UPDATE de scores terminar.

---

### Piloto de aliases (2026-04-09)

10 aliases manualmente aprovados e justificados:
- `reports/approved_aliases_pilot.csv` — lista aprovada
- `reports/apply_alias_pilot.sql` — INSERT com lock_timeout
- `reports/rollback_alias_pilot.sql` — DELETE exato para reverter

Executado em 2026-04-10:
- Lock do UPDATE liberou apos ~6h
- Tabela wine_aliases criada no Render (schema completo, 9 colunas, 3 indices)
- Piloto de 10 aliases inserido com aprovacao explicita
- 10 de 10 inseridos (ON CONFLICT DO NOTHING, zero conflitos)
- Todos com source_type='manual', review_status='approved'
- rollback_alias_pilot.sql validado: bateria em exatamente 10 registros

### Quem consome wine_aliases e em que ordem

wine_aliases SOZINHA nao muda comportamento do app. Precisa de integracao
explicita em pelo menos 1 consumidor. Ordem recomendada:

**wine_aliases ATIVO EM PRODUCAO via search/details (2026-04-10)**
- Deploy runtime: commit bcba6ea0 (aliases.py + search.py + details.py)
- Lote 1 (piloto): 10 aliases. Validado 10/10.
- Lote 2: 21 aliases adicionais. Validado 31/31 details, 30/31 search (1 MISS por duplicata de nome, nao por falha).
- Controles sem alias: 5/5 preservados, nenhuma regressao.
- Total ativo: 31 aliases aprovados em producao.
- Vinhos de alto impacto cobertos: Almaviva (4.4), Clos Apalta (4.6), Purple Angel (4.4),
  Montes Alpha (todas uvas), Santa Rita 120 (CS/Merlot/SB), Chaski, Finca Las Moras.

**1. search.py (PRIMEIRO) — IMPLEMENTADO E VALIDADO (2026-04-10)**
- Funcao _resolve_aliases() adicionada ao search.py
- Pos-query: busca aliases aprovados para os IDs retornados,
  enriquece com COALESCE de vivino_rating, nota_wcf, winegod_score,
  vivino_reviews, vivino_id, produtor
- Mantém nome da source (o que o usuario buscou)
- Adiciona canonical_id e resolved_via='alias' no resultado
- Validado com os 10 aliases do piloto: 10 de 10 resolvidos
- Chaski: #2 mostra rating=4.1 via alias (antes: sem nota)
- Finca: #4 e #5 mostram rating=3.4 via alias (antes: sem nota)

**2. details.py (SEGUNDO)**
- Quando usuario pede detalhes de wine de loja com alias aprovado,
  enriquecer com dados do canonico (rating, tipo, regiao, uvas)
- Complementa o search: depois que o usuario clica no resultado,
  ve os dados completos

**3. Rebuild Fase 2 (TERCEIRO)**
- Usar aliases como mapa de dedup no banco sombra
- So apos volume significativo de aliases aprovados
- Nao depende de integracao no app

Justificativa da ordem: search.py e o unico ponto que o usuario
SEMPRE passa. Se a busca retornar o canonico com nota,
o details automaticamente mostra os dados certos. O rebuild
e operacao offline que pode esperar.

---

## FASE 2 -- Status: RUNBOOK PREPARADO

Arquivo: `C:\winegod-app\reports\RUNBOOK_FASE2_REBUILD.md`

Contem passo a passo com caminhos reais, notas sobre scripts que ainda nao existem (generate_aliases.py, recalc_scores.py), e checklist de validacao.

Correcao aplicada em 2026-04-09: `reconcile_vivino.py` usava colunas inexistentes (`produtor`, `rating`) na query contra `vivino_vinhos`. As colunas reais sao `vinicola_nome` e `rating_medio` (confirmado via `002_import_vivino.py` linhas 73-75). Script corrigido.

---

## Arquivos alterados nesta sessao

### Backend (para deploy em producao)

| Arquivo | Status Git | O que mudou |
|---------|-----------|-------------|
| `backend/tools/search.py` | Modified (nao commitado) | _CANONICAL_RANK no ORDER BY de todas as camadas |
| `backend/tools/normalize.py` | Untracked | Dependencia de search.py, precisa ir junto |
| `backend/services/cache.py` | Modified (nao commitado) | CACHE_VERSION=2, prefixo v2 nas chaves |
| `backend/prompts/baco_system.py` | Modified (nao commitado) | Instrucao para vinho sem nota, regras de foto/OCR |

### Scripts locais (nao vao para producao)

| Arquivo | O que e |
|---------|---------|
| `scripts/import_render_z.py` | Fix do threshold 0.0->0.5, constantes de 3 estados |
| `scripts/baseline_fase0.py` | Script de baseline pre/pos usando search_wine real |
| `scripts/guardrails_owner.py` | Script autonomo de auditoria de owners |
| `scripts/wine_filter.py` | Filtro centralizado de nao-vinhos (nao integrado) |
| `scripts/reconcile_vivino.py` | Reconciliacao Vivino vs Render |

### Repo winegod (migrations)

| Arquivo | O que e |
|---------|---------|
| `C:\winegod\migrations\003_wine_aliases.sql` | CREATE TABLE wine_aliases (nao aplicada) |

---

## Lista exata para deploy em producao

O working tree tem mudancas muito alem do dedup. O deploy precisa considerar TUDO.

### Mudancas especificas desta sessao de dedup (3 arquivos):

| Arquivo | Mudanca de dedup |
|---------|-----------------|
| `backend/tools/search.py` | _CANONICAL_RANK adicionado ao ORDER BY |
| `backend/services/cache.py` | CACHE_VERSION=2 |
| `backend/prompts/baco_system.py` | Instrucao para vinho sem nota (absorvida pela versao display_note) |

### Contexto: search.py depende de arquivos nao commitados

O search.py no working tree foi refatorado (busca em 4 camadas, parametros estruturados). Essa refatoracao e ANTERIOR a esta sessao de dedup. O search.py atual importa:

- `from tools.normalize import normalizar` -- **UNTRACKED** (precisa ser commitado)
- `from services.display import enrich_wines` -- **UNTRACKED** (precisa ser commitado)

### Todos os arquivos backend modificados no working tree

**Modificados (13):**
1. backend/db/models_share.py
2. backend/db/queries.py
3. backend/prompts/baco_system.py
4. backend/requirements.txt
5. backend/routes/chat.py
6. backend/routes/health.py
7. backend/services/baco.py
8. backend/services/cache.py
9. backend/tools/compare.py
10. backend/tools/details.py
11. backend/tools/media.py
12. backend/tools/schemas.py
13. backend/tools/search.py

**Novos nao commitados (5):**
1. backend/services/display.py
2. backend/services/tracing.py
3. backend/tests/test_search_cases.py
4. backend/tools/normalize.py
5. backend/tools/resolver.py

**ATENCAO**: deploying apenas os 3 arquivos de dedup nao e viavel — o search.py refatorado quebra sem normalize.py e display.py. E preciso deployar TODO o backend como conjunto, ou revert search.py para a versao commitada e aplicar _CANONICAL_RANK sobre ela.

---

## Verificacoes de fato

| Item | Resultado |
|------|-----------|
| Pipeline ativo? | Repos nao mostram scheduler integrado. Falta confirmar no dashboard Render e verificar execucoes manuais. |
| EAN loja-loja? | Sem cobertura -- campo existe mas nao populado |
| URL Vivino? | Existe e preenchido, pode ser regra deterministica. Cobertura nao quantificada. |
| wines.fontes usado pelo produto? | NAO -- backend nao le esse campo |
| Fase 0 aprovada? | Codigo alterado. Aprovacao depende de executar baseline pre/pos e confirmar resultado. |

---

## O que esta implementado vs apenas preparado

| Item | Implementado (codigo pronto) | Integrado no fluxo | Validado operacionalmente |
|------|-------|---------|----------|
| Fix threshold 0.0->0.5 | Sim | Sim (no script de import) | Nao (falta rodar) |
| ORDER BY canonico | Sim | Sim (no search.py real) | Nao (falta baseline) |
| CACHE_VERSION | Sim | Sim (no cache.py real) | Nao (falta deploy) |
| UX vinho sem nota | Sim | Sim (no baco_system.py real) | Nao (falta deploy) |
| Guardrails owner | Sim (script autonomo) | NAO | NAO |
| Filtro nao-vinhos | Sim (script autonomo, testado) | NAO | Teste unitario OK |
| Tabela wine_aliases | Sim (SQL pronto) | NAO (nao aplicada) | NAO |
| 3 estados matching | Parcial (constantes) | Parcial (check mostra, mas nao grava status) | NAO |
| Baseline script | Sim | N/A | NAO (falta executar) |
