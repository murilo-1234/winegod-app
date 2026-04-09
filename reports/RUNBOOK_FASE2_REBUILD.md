# Runbook -- Fase 2: Rebuild Historico em Sombra Local

Data: 2026-04-09 (atualizado)
Status: PREPARADO (nao executado)

## Objetivo

Rebuild completo do banco com regras corrigidas, em sombra local.
Nenhum cutover live ate validacao completa.

## Pre-requisitos

- [ ] Fase 0 aprovada (hotfixes deployados e validados)
- [ ] Fase 1 artefatos revisados (guardrails, aliases, filtro)
- [ ] PostgreSQL local rodando (winegod_db)
- [ ] vivino_db local populado (1.7M vinhos)
- [ ] .env configurado com DATABASE_URL do Render (read-only)

## Passo a Passo

### 2.1 Reconciliar vivino_db vs Render

```bash
cd C:\winegod-app
python scripts/reconcile_vivino.py --report --sample 20
```

Verificar:
- Quantos vinhos em ambos
- Quantos so no Vivino (faltando no Render)
- Quantos so no Render (vivino_id nao encontrado)
- Amostra de cada grupo para sanity check

### 2.2 Criar banco sombra local

```bash
createdb -U postgres winegod_shadow

# Aplicar schema (caminho real no repo winegod)
psql -U postgres winegod_shadow < C:\winegod\migrations\001_initial_schema.sql

# Aplicar tabela de aliases (caminho real no repo winegod)
psql -U postgres winegod_shadow < C:\winegod\migrations\003_wine_aliases.sql
```

### 2.3 Importar camada canonica Vivino

```bash
cd C:\winegod
python migrations/002_import_vivino.py
# NOTA: script atual nao aceita --target. Antes de executar,
# ajustar LOCAL_DB ou DATABASE_URL para apontar ao winegod_shadow.
```

Verificar:
- Total importado == total vivino_db
- vivino_id populado em 100%
- vivino_rating populado na cobertura esperada

### 2.4 Reimportar lojas com regras novas

```bash
cd C:\winegod-app
# NOTA: import_render_z.py nao aceita --target shadow.
# Antes de executar, ajustar RENDER_DB no script para apontar ao shadow local.
python scripts/import_render_z.py --check
python scripts/import_render_z.py --fase all --dry-run
python scripts/import_render_z.py --fase all
```

Verificar:
- Zero itens com match_score < 0.5 no auto-link
- Zero itens com match_score < 0.3 no banco
- Filtro de nao-vinho bloqueando casos conhecidos

### 2.5 Aplicar aliases

**PENDENTE**: script `generate_aliases.py` ainda nao existe.
Precisa ser criado antes de executar esta etapa.
Logica esperada:
- Ler y2_results com match_score >= 0.7
- Para cada par (clean_id, vivino_id), criar alias em wine_aliases
- review_status = 'pending' para revisao

### 2.6 Recalcular scores

**PENDENTE**: script `recalc_scores.py` ainda nao existe.
Precisa ser criado antes de executar esta etapa.
Logica esperada:
- Recalcular nota_wcf e winegod_score para todos os wines
- Usar logica existente de calc_wcf.py como base

### 2.7 Validacao

```bash
cd C:\winegod-app
python scripts/guardrails_owner.py --audit
python scripts/baseline_fase0.py --pos
```

## Checklist de Validacao (Criterios de Aceite)

### Contagens
- [ ] Total wines >= total atual Render (nao perdeu vinhos)
- [ ] Total wine_sources >= total atual (nao perdeu fontes)

### Owners
- [ ] Nenhum produtor com > 2% de concentracao (exceto grandes casas como "LVMH")
- [ ] Zero produtores vazios com wine_sources linkados

### Casos do handoff
- [ ] "Dom Perignon" retorna versao canonica com rating
- [ ] "Finca Las Moras Cabernet Sauvignon" retorna com nota
- [ ] "Chaski Petit Verdot" retorna resultado coerente
- [ ] "Luigi Bosca De Sangre Malbec" retorna com rating
- [ ] "Perez Cruz Piedra Seca" retorna resultado

### Matching
- [ ] Zero producao nova com matched < 0.5 no auto-link
- [ ] Zero producao com matched < 0.3 no banco
- [ ] Filtro de nao-vinho bloqueando: comida, decoracao, perfume, bourbon, mixer, tacas

### Amostra aleatoria
- [ ] 50 vinhos aleatorios: produtor correto, tipo coerente, rating plausivel
- [ ] 20 wine_sources aleatorios: URL valida, store_id correto, preco coerente

### Owner collapse
- [ ] Bloqueio ativo para produtor vazio no fluxo novo
- [ ] Bloqueio ativo para produtor generico
- [ ] Bloqueio ativo para conflito tinto/branco

## Cutover (NAO EXECUTAR SEM AUTORIZACAO)

O cutover do shadow para live envolve:
1. Fazer backup completo do Render atual
2. Pausar o backend (maintenance mode)
3. Truncar e reimportar wines + wine_sources no Render
4. Aplicar wine_aliases
5. Invalidar cache Redis (incrementar CACHE_VERSION em backend/services/cache.py)
6. Rodar baseline pos-cutover
7. Retomar backend

IMPORTANTE: Cutover so com autorizacao explicita do Murilo.

## Artefatos existentes

| Artefato | Caminho real | Status |
|----------|-------------|--------|
| baseline_fase0.py | C:\winegod-app\scripts\baseline_fase0.py | Existe |
| guardrails_owner.py | C:\winegod-app\scripts\guardrails_owner.py | Existe (script autonomo, nao integrado no import) |
| wine_filter.py | C:\winegod-app\scripts\wine_filter.py | Existe (testado, nao integrado no pipeline) |
| reconcile_vivino.py | C:\winegod-app\scripts\reconcile_vivino.py | Existe |
| 003_wine_aliases.sql | C:\winegod\migrations\003_wine_aliases.sql | Existe (nao aplicado no banco) |

## Artefatos pendentes (precisam ser criados)

| Artefato | Descricao |
|----------|-----------|
| generate_aliases.py | Gerar wine_aliases a partir de matches de alta confianca |
| recalc_scores.py | Recalcular nota_wcf e winegod_score |
