# Handoff: Pesquisa 01 — Campo `pais` vs `pais_nome`

Data: 2026-04-16
Origem: chat terminal que caiu (arquivo: `C:\Users\muril\OneDrive\Documentos\Programação\erros-terminal\nota_wcf\pais-nome.txt`, 694 linhas)
Aba: `01_ESTUDO_PAIS_VS_PAIS_NOME.md` dentro de `nota_wcf_v2_research`
Prompt original: `C:\winegod-app\prompts\nota_wcf_v2_research\01_ESTUDO_PAIS_VS_PAIS_NOME.md`

---

## 1. Contexto

A tabela `wines` tem dois campos de pais:
- `pais` — codigo ISO 2 letras (ex: `fr`, `it`, `ar`)
- `pais_nome` — nome por extenso (ex: `França`, `Itália`, `Argentina`)

A cascata da `nota_wcf v2` ja usa `pais` (ISO). O fundador prefere trabalhar com nome completo se for seguro. A pesquisa foi encomendada para resolver essa duplicidade.

---

## 2. Timeline do chat

### Fase 1 — Plano (linhas 1-74)
- Agente leu o prompt `01_ESTUDO_PAIS_VS_PAIS_NOME.md`
- Apresentou plano em 3 frentes: banco (queries SELECT), codigo (grep), docs (leitura)
- Restricoes: zero alteracoes, zero migrations, zero edits em producao
- Murilo aprovou com "sim"

### Fase 2 — Pesquisa (linhas 76-240)
- Grep de `pais` e `pais_nome` no backend — mapeou onde cada um aparece
- Tentou rodar queries via `psql` — nao instalado no Windows
- Trocou para Python + `psycopg2` — funcionou
- Conexao SSL caiu uma vez — retentou com sucesso
- Encoding `cp1252` do terminal quebrou acentos — contornou com UTF-8 forcado
- Todas as queries de inventario foram concluidas com sucesso

### Fase 3 — Primeiro relatorio (linhas 247-463)
- Entregou relatorio completo com os 9 pontos pedidos
- Recomendacao: `pais` (ISO) como campo canonico
- Conclusao sobre `pais_nome`: "utilidade apenas para exibicao"

### Fase 4 — Revisao do fundador (linhas 466-520)
- Murilo atuou como "aba WG PAIS_NOME" e revisou o relatorio
- Aprovou a recomendacao central
- Apontou 6 problemas:
  1. Disse que `pais_nome` e "so exibicao" cedo demais — no codigo atual ainda participa de logica funcional
  2. Inventario de dependencias incompleto — faltaram prices.py, resolver.py, models_share.py, frontend share/OG, triggers
  3. Conclusao sobre papel de `pais_nome` precisa reescrever
  4. Numeros nao provados ("5 min", "300MB+") devem ser removidos
  5. Plano de etapas precisa incluir migracao explicita de cada arquivo antes de deprecar
  6. Impacto na cascata precisa ser mais detalhado

### Fase 5 — Relatorio corrigido (linhas 528-694)
- Agente releu os 9 arquivos faltantes (triggers, frontend, share/OG, etc.)
- Entregou relatorio corrigido com todas as 6 correcoes incorporadas
- Terminal morreu logo depois — nao houve resposta do Murilo

---

## 3. Dados medidos no banco (confirmados via queries)

### Distribuicao cruzada pais x pais_nome

| Cenario | Vinhos | % |
|---|---|---|
| Ambos preenchidos | 1.723.345 | 68,8% |
| So `pais` (sem `pais_nome`) | 263.950 | 10,5% |
| So `pais_nome` (sem `pais`) | 0 | 0% |
| Nenhum dos dois | 519.146 | 20,7% |
| **Total** | **2.506.441** | **100%** |

### Cardinalidade
- `pais`: 84 valores distintos
- `pais_nome`: 62 valores distintos

### Valores sujos em `pais` (~19 vinhos)

| Valor | Qtd | Problema |
|---|---|---|
| `No` | 14 | Nao e ISO valido |
| `ZA` (maiusculo) | 1 | Duplicata de `za` (34.995) |
| `NA` | 1 | Provavelmente "nao disponivel" |
| `eq` | 1 | Nao e ISO valido |
| `we` | 2 | Westeros (ficticio) |

### Problemas em `pais_nome`
- Idioma misturado: maioria PT-BR, mas 5 valores em ingles ("New Zealand", "Uruguay", "Serbia", "Luxembourg", "State of Palestine")
- Sem padrao internacional
- Ficticio: "Westeros" (2 vinhos)
- Zero indices — todas as queries ILIKE fazem table scan em 2.5M rows
- 263.950 vinhos a menos de cobertura que `pais`

### 263K sem `pais_nome` — distribuicao por pais

| Pais | Qtd |
|---|---|
| `fr` (Franca) | 109.565 |
| `it` (Italia) | 53.449 |
| `es` (Espanha) | 18.000+ |
| Outros | ~83.000 |

### 519K sem nenhum pais
- Vinhos importados de fontes sem info de pais (ex: batch `wines_clean`)
- Problema separado, nao depende desta decisao

---

## 4. Inventario completo de dependencias de `pais_nome` (21 pontos)

### Backend — logica funcional (filtros, queries, triggers)

| Arquivo | Linha | Uso | Tipo |
|---|---|---|---|
| `backend/tools/search.py` | 225 | `pais_nome ILIKE %s` | Filtro de busca |
| `backend/tools/search.py` | 540 | `pais_nome = %s` | Filtro vinhos similares |
| `backend/tools/search.py` | 579 | `pais_nome = %s` | Filtro fallback similares |
| `backend/tools/compare.py` | 62 | `pais_nome ILIKE %s` | Filtro recomendacoes |
| `backend/tools/stats.py` | 20 | `"pais": "pais_nome"` | Mapeamento API→coluna |
| `backend/tools/stats.py` | 54 | `LOWER(pais_nome) = LOWER(%s)` | Filtro estatisticas |
| `backend/tools/stats.py` | 151 | `pais_nome` | COUNT DISTINCT paises |
| `database/migrations/007` | 14 | `OLD.pais_nome IS DISTINCT FROM NEW.pais_nome` | Trigger score recalc |
| `database/migrations/009` | 34 | idem | Trigger score recalc v2 |

### Backend — SELECT para exibicao/montagem

| Arquivo | Linha | Uso |
|---|---|---|
| `backend/tools/search.py` | 15 | SELECT column na query principal |
| `backend/tools/search.py` | 525, 553, 587 | SELECT columns em similares |
| `backend/tools/compare.py` | 17, 81 | SELECT column em compare e recs |
| `backend/tools/prices.py` | 96 | SELECT column em store wines |
| `backend/tools/resolver.py` | 746 | `w.get('pais_nome', '?')` para display |
| `backend/db/models_share.py` | 101, 113 | SELECT column em share |

### Frontend

| Arquivo | Linha | Uso |
|---|---|---|
| `frontend/app/c/[id]/page.tsx` | 14, 43 | Interface + `pais: w.pais_nome \|\| ""` |
| `frontend/app/c/[id]/opengraph-image.tsx` | 12, 143 | Interface + display `{wine.pais_nome}` |

### Recurso existente
- `backend/services/new_wines.py:381` ja tem mapa ISO→nome (em ingles)
- Pode ser reutilizado e traduzido para PT-BR

---

## 5. Opcoes avaliadas

### Opcao A — `pais` (ISO) canonico + dicionario em codigo (RECOMENDADA)
- `pais` fica como fonte de verdade
- Dicionario Python mapeia `'fr'` → `'França'`
- `pais_nome` eventualmente vira coluna deprecated
- Exibicao sempre via dicionario

### Opcao B — Migrar tudo para `pais_nome` por extenso
- Preencher 263K faltantes
- Padronizar idioma (tudo PT-BR)
- `pais_nome` vira canonico, `pais` deprecated

### Opcao C — Manter os dois, preencher lacunas
- Backfill `pais_nome` nos 263K
- Manter ambos sem deprecar nenhum

---

## 6. Decisao final: Opcao A

Razoes decisivas:
1. **Performance**: 3 indices ja existem em `pais` (`idx_wines_pais`, `idx_wines_pais_rating`, `idx_wines_pais_wgscore`). `pais_nome` tem zero indices.
2. **Consistencia**: `stores.pais`, `executions.pais`, `country_summary.pais`, `platform_summary.pais` — todas usam ISO.
3. **Cascata nota_wcf v2**: ja desenhada e aprovada usando `pais` ISO.
4. **Padronizacao**: ISO 3166 e padrao global. `pais_nome` e campo livre sem padrao.
5. **Internacionalizacao**: com ISO, pode mostrar "Francia" em espanhol, "France" em ingles, "Franca" em portugues.
6. **Cobertura**: `pais` cobre 100% do que `pais_nome` cobre, mais 263.950 vinhos extras.

Para a preferencia do fundador (nome completo no produto):
- Satisfeita sem comprometer o banco. Dicionario em codigo mapeia ISO → nome. Usuario nunca ve codigo ISO.

---

## 7. O que nao foi concluido

- Relatorio corrigido nunca foi salvo em `reports/` (ficou so no chat que caiu)
- Nenhuma implementacao comecou
- Coordenacao (`00_COORDENACAO_PESQUISA_NOTA_WCF_V2.md`) nao foi atualizada
- Nenhum teste foi rodado

---

## 8. O que nao foi possivel provar

1. **Vivino-broker**: O CTO doc menciona que `server.js` no vivino-broker escreve dados. Nao foi possivel verificar se ele escreve em `pais` ou `pais_nome` porque o repo e separado.
2. **Fontes dos 263K**: Provavelmente o batch de `wines_clean` que nao fazia backfill de nome.
3. **Fontes dos 519K**: Vinhos com dados incompletos na origem. Investigacao separada.
4. **Encoding**: Nomes com acentos estao em UTF-8 no banco mas terminal Windows mostra com encoding quebrado. Problema de display local, nao do banco.

---

## 9. Riscos mapeados

| Risco | Gravidade | Mitigacao |
|---|---|---|
| Sistema externo escreve em `pais_nome` | Media | Verificar antes de dropar |
| Query hardcoded nao detectada | Baixa | Grep completo feito, 21 pontos mapeados |
| 519K vinhos sem nenhum pais | Alta (pre-existente) | Problema separado |
| Backfill errado do dicionario | Baixa | Dicionario ISO e deterministico |
