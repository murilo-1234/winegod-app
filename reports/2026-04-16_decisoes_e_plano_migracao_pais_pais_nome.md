# Decisoes e Plano de Execucao: Migracao `pais` / `pais_nome`

Data: 2026-04-16 (v2 — reescrito apos revisao tecnica)
Handoff de referencia: `C:\winegod-app\reports\2026-04-16_handoff_pesquisa_01_pais_vs_pais_nome.md`
Prompt original da pesquisa: `C:\winegod-app\prompts\nota_wcf_v2_research\01_ESTUDO_PAIS_VS_PAIS_NOME.md`

---

## 1. Resumo da situacao

A pesquisa da aba 01 (`pais` vs `pais_nome`) foi concluida, revisada e aprovada. A decisao arquitetural e firme: `pais` (ISO) e o campo canonico. O plano v1 foi revisado e tinha 4 erros serios:

1. Subestimou o blast radius da trigger no backfill (263K updates disparariam 263K recalculos de score)
2. Ia destruir dados validos de Noruega (`no`) e Namibia (`na`) tratando como lixo
3. Nao incluiu o pipeline de score (`calc_score.py`, `calc_score_incremental.py`) como dependencia
4. Tratou sub-etapas como independentes quando todas precisam de um modulo central primeiro

Este plano v2 corrige tudo isso.

---

## 2. Decisoes acumuladas

### Chat original (pesquisa)

| # | Decisao | Status |
|---|---|---|
| D1 | `pais` (ISO) e o campo canonico | Aprovado |
| D2 | `pais_nome` deve migrar para papel exclusivo de exibicao | Aprovado com ressalva: hoje ainda participa de logica funcional |
| D3 | Nenhum campo sera deletado agora | Aprovado |
| D4 | Dicionario ISO→nome em codigo resolve a preferencia por nome completo | Aprovado |
| D5 | Opcao A (pais ISO canonico) e a escolha final | Aprovado |

### Sessao de retomada (2026-04-16)

| # | Decisao | Motivo |
|---|---|---|
| D6 | Backfill ANTES de migrar o codigo (Opcao B) | Os 263K vinhos ja aparecem corretos durante a transicao |
| D7 | Os dois campos ficam no banco | `pais` = canonico. `pais_nome` = display. Nenhum deletado. |
| D8 | Backfill so preenche campos vazios | Nunca sobrescreve valor existente |

### Revisao tecnica (2026-04-16)

| # | Decisao | Motivo |
|---|---|---|
| D9 | Modulo central de paises obrigatorio como primeira etapa | 3 mapas duplicados no codigo (`new_wines.py:38`, `enrichment_v3.py:65`, `resolver.py:21`). Sem centralizar, a duplicacao volta. |
| D10 | Modulo precisa de 3 capacidades: `iso_to_name`, `text_to_iso`, aliases PT/EN/sem acento | O usuario digita "France", "Franca", "franca" ou "fr". Sem conversor, trocar `ILIKE` por `=` quebra a busca. |
| D11 | Revisao row-level dos 19 valores ambiguos antes de qualquer limpeza | `No` = Noruega (ISO valido), `NA` = Namibia (ISO valido). Nao sao lixo. |
| D12 | Backfill exige desativar trigger temporariamente OU ser feito depois da migracao de trigger | A trigger em `009:34` monitora `pais_nome`. Backfill de 263K rows gera 263K itens na fila de recalculo. |
| D13 | Pipeline de score (`calc_score.py:179`, `calc_score_incremental.py:116`) precisa migrar de `pais_nome` para `pais` junto com a trigger | O calculo de score agrupa vinhos por `pais_nome` como chave de peer. Se so migrar trigger sem migrar score, o score fica preso ao campo antigo. |
| D14 | Migrar writers alem de readers | `new_wines.py:381` escreve `pais_nome` em ingles. `enrichment_v3.py:542` emite `country` em ingles. Se nao migrar, a inconsistencia volta no dia seguinte. |
| D15 | Definir contrato de display da API | Decidir se a API continua mandando `pais_nome` ou passa a mandar `pais_display` derivado do dicionario. |
| D16 | Decidir se `pais_nome` existente (1.723.345) sera canonizado ou fica legacy | Backfill dos vazios nao resolve idioma misto nos valores ja existentes. |

---

## 3. O que muda para cada campo

| | Hoje | Depois da migracao |
|---|---|---|
| `pais` (ISO) | Canonico mas o codigo nem sempre usa ele | Canonico de verdade — toda busca, filtro, trigger, score e logica usam `pais` |
| `pais_nome` (texto) | Usado em busca, filtro, trigger, score, display — tudo misturado | So display — fica no banco preenchido e em PT-BR, mas nenhum codigo depende dele pra funcionar |

---

## 4. Plano de execucao completo (v2)

### Marco historico — Pesquisa salva
- **Status:** FEITO
- Handoff: `C:\winegod-app\reports\2026-04-16_handoff_pesquisa_01_pais_vs_pais_nome.md`
- Decisoes: este documento

---

### Etapa 1 — Criar modulo central de paises

- **O que:** Modulo unico com 3 capacidades:
  - `iso_to_name(code)` — `"fr"` → `"França"`
  - `text_to_iso(text)` — `"France"` → `"fr"`, `"franca"` → `"fr"`, `"fr"` → `"fr"`
  - Aliases em PT-BR, EN e sem acento (ex: `"franca"`, `"france"`, `"francia"` → `"fr"`)
- **Onde:** `C:\winegod-app\backend\utils\country_names.py`
- **Dados base:** Os ~84 codigos ISO que existem no banco + os nomes de `_KNOWN_COUNTRIES` em `resolver.py:21`
- **Risco:** Zero (arquivo novo, ninguem usa ainda)
- **Toca producao:** Nao
- **Reversivel:** Sim
- **Validacao:** Mostrar o modulo completo pro Murilo antes de prosseguir
- **Criterio de aceite:** `text_to_iso` retorna ISO correto para todas as variantes testadas (PT, EN, sem acento, ISO puro)

---

### Etapa 2 — Revisao row-level dos ~19 valores ambiguos em `pais`

- **O que:** Revisar cada um dos 19 vinhos com valores fora do padrao:
  - `ZA` (1 vinho) — provavelmente `za` (Africa do Sul), so precisa lowercase
  - `No` (14 vinhos) — provavelmente `no` (Noruega), verificar com dados do vinho
  - `NA` (1 vinho) — provavelmente `na` (Namibia), verificar com dados do vinho
  - `eq` (1 vinho) — nao e ISO valido, revisar manualmente
  - `we` (2 vinhos) — Westeros, ficticio
- **Metodo:** SELECT dos 19 vinhos com nome, produtor, regiao pra confirmar cada caso
- **Risco:** Zero (19 vinhos, revisao manual)
- **Reversivel:** Sim
- **Criterio de aceite:** Cada um dos 19 casos tem decisao justificada com evidencia

---

### Etapa 3 — Migrar pipeline de score + trigger

**Fazer ANTES do backfill pra evitar o blast radius da trigger.**

- **3a — Migrar `calc_score.py`**
  - Trocar `SELECT pais_nome` por `SELECT pais` nas duas queries (linhas 179 e 253)
  - A chave de peer passa de `pais_nome` (texto misto) para `pais` (ISO)
  - **Arquivo:** `C:\winegod-app\scripts\calc_score.py`
  - **Risco:** Medio — muda a base de agrupamento de peers. Mas `pais` tem mais cobertura (+263K) e e mais consistente, entao os peers ficam melhores, nao piores.
  - **Validacao:** Rodar em modo dry-run, comparar distribuicao de peers antes/depois

- **3b — Migrar `calc_score_incremental.py`**
  - Mesma troca: `SELECT pais_nome` → `SELECT pais` (linha 116)
  - **Arquivo:** `C:\winegod-app\scripts\calc_score_incremental.py`
  - **Risco:** Mesmo da 3a
  - **Validacao:** Mesma da 3a

- **3c — Migrar trigger de score recalc**
  - Nova migration SQL (nao edita 007 nem 009)
  - Trigger passa a monitorar `pais` em vez de `pais_nome`
  - **Arquivo:** Nova migration `C:\winegod-app\database\migrations\010_score_trigger_pais_iso.sql`
  - **Risco:** Medio
  - **Reversivel:** Sim (rollback SQL)
  - **Validacao:** Mostrar SQL pro Murilo antes de rodar

- **Criterio de aceite da etapa 3:** Score recalculado nao tem regressao significativa vs score atual. Trigger responde a `pais`, nao a `pais_nome`. Backfill de `pais_nome` nao gera avalanche na fila.

---

### Etapa 4 — Backfill dos 263.950 vinhos

**Agora e seguro porque a trigger ja nao observa `pais_nome`.**

- **O que:** Preencher `pais_nome` onde esta vazio, usando o dicionario da etapa 1
- **Regra:** So toca vinhos onde `pais` tem valor E `pais_nome` e NULL/vazio
- **Nao faz:** Nao sobrescreve nenhum `pais_nome` que ja exista
- **Metodo:**
  1. Dry-run: SELECT mostrando quantos seriam afetados por pais
  2. Auditoria: listar os ISO codes que serao traduzidos e os nomes PT-BR correspondentes
  3. Batch update em lotes (ex: 10K por vez)
  4. Validacao de contagem antes/depois
- **Risco:** Baixo (apos migracao da trigger)
- **Reversivel:** Sim (pode setar de volta pra NULL)
- **Criterio de aceite:** Contagem de `pais_nome` vazios cai de 263.950 para o esperado. Nenhum valor existente foi sobrescrito.

---

### Etapa 5 — Decidir contrato de display da API

**Decisao do Murilo antes de migrar os readers.**

- **Pergunta:** Quando o backend manda dados de vinho pro frontend ou pro Baco, o campo de pais vai ser:
  - **Opcao A:** Continua mandando `pais_nome` (preenchido a partir do dicionario se necessario)
  - **Opcao B:** Manda um campo novo `pais_display` derivado do dicionario
- **Impacto:** Define como todas as etapas 6-8 vao funcionar
- **Recomendacao:** Opcao A — manter `pais_nome` como nome do campo na API, mas garantir que o valor vem do dicionario (ISO→nome) e nao do campo bruto do banco. Menos breaking changes pro frontend.

---

### Etapa 6 — Migrar readers do backend

**Depende do modulo central (etapa 1) e do contrato de display (etapa 5).**

Todas as sub-etapas usam `text_to_iso()` pra converter entrada e `iso_to_name()` pra converter saida.

| Sub-etapa | Arquivo | O que muda | Linhas | Notas |
|---|---|---|---|---|
| 6a | `backend/tools/search.py` | Entrada: `text_to_iso(pais)` → `WHERE pais = %s`. Saida: `iso_to_name()` no resultado. | 15, 225, 525, 540, 553, 579, 587 | Mais linhas, mais critica. Fazer primeiro. |
| 6b | `backend/tools/compare.py` | Mesma troca de entrada/saida | 17, 62, 81 | |
| 6c | `backend/tools/stats.py` | `GROUP_COLUMNS["pais"]` → coluna `pais`. Pos-processar GROUP BY pra mostrar nome bonito. `filter_pais` normalizado via `text_to_iso()`. `count_countries` conta `pais` em vez de `pais_nome`. `_count_stores` e `_count_sources` normalizam filtro. | 20, 54, 151, 182, 196 | A mais traicoeira. GROUP BY `pais` retorna ISO; precisa mapear pra nome na saida. |
| 6d | `backend/tools/prices.py` | SELECT troca `pais_nome` por `pais` + nome via dicionario na saida | 96 | Simples. |
| 6e | `backend/tools/resolver.py` | Display via `iso_to_name()` em vez de `w.get('pais_nome')`. Centralizar `_KNOWN_COUNTRIES` (linha 21) usando o modulo central. | 21, 746 | |
| 6f | `backend/db/models_share.py` | SELECT e lista de colunas. Garantir que o campo exposto ao frontend segue o contrato da etapa 5. | 101, 113 | |

- **Risco por arquivo:** Baixo
- **Reversivel:** Sim (git revert)
- **Criterio de aceite:** `rg "pais_nome" backend/tools` so retorna hits em SELECTs de display/legacy, nenhum em WHERE/filtro/agrupamento.

---

### Etapa 7 — Migrar writers do backend

- **7a — `new_wines.py`**
  - Linha 381: troca `_COUNTRY_NAMES.get(pais)` local pelo `iso_to_name()` do modulo central
  - Remove o `_COUNTRY_NAMES` duplicado (linhas 38-67)
  - `pais_nome` gravado em PT-BR via modulo central
  - **Arquivo:** `C:\winegod-app\backend\services\new_wines.py`

- **7b — `enrichment_v3.py`**
  - Linha 542: `_COUNTRY_NAMES.get(...)` emite nome em ingles. Trocar pelo modulo central.
  - Remove o `_COUNTRY_NAMES` duplicado (linhas 65-94)
  - **Arquivo:** `C:\winegod-app\backend\services\enrichment_v3.py`

- **Risco:** Baixo
- **Reversivel:** Sim
- **Criterio de aceite:** Vinhos novos criados apos a migracao tem `pais_nome` em PT-BR, nao em ingles. Nenhum `_COUNTRY_NAMES` local sobrevive fora do modulo central.

---

### Etapa 8 — Migrar frontend (share/OG)

- **Escopo real:** So share/OG. O chat ja trabalha com dados vindos do backend.
- **Arquivos:**
  - `C:\winegod-app\frontend\app\c\[id]\page.tsx` (linhas 14, 43)
  - `C:\winegod-app\frontend\app\c\[id]\opengraph-image.tsx` (linhas 12, 143)
- **O que muda:** Segue o contrato da etapa 5. Se opcao A, o campo continua `pais_nome` e o frontend nao muda nada (ja recebe valor bonito do backend).
- **Risco:** Baixo
- **Reversivel:** Sim

---

### Etapa 9 — Canonizar `pais_nome` existente (decisao pendente)

**Decisao do Murilo.**

Os 1.723.345 vinhos que ja tem `pais_nome` preenchido continuam com idioma misto (5 valores em ingles: "New Zealand", "Uruguay", "Serbia", "Luxembourg", "State of Palestine"). Opcoes:

- **Opcao A:** Canonizar tudo pra PT-BR usando o modulo central. UPDATE simples: `SET pais_nome = iso_to_name(pais) WHERE pais IS NOT NULL`. Sobrescreve valores existentes.
- **Opcao B:** Deixar como esta. `pais_nome` vira legacy/inconsistente mas nenhum codigo depende dele.

**Recomendacao:** Opcao A. Se `pais_nome` vai ficar no banco como coluna de conveniencia, faz sentido que esteja limpo e consistente. Apos a migracao de trigger (etapa 3c), esse UPDATE nao gera blast radius.

---

### Etapa 10 — Testar tudo end-to-end

- **Testes manuais:**
  - Busca por pais em PT ("vinhos da Franca"), EN ("wines from France"), sem acento ("franca"), ISO ("fr")
  - Comparacao ("compare este com outro italiano")
  - Estatisticas ("quantos paises temos?") — verificar que retorna nomes, nao codigos ISO
  - Share/OG (abrir link de vinho compartilhado)
- **Testes automatizados:**
  - Testes unitarios do modulo central (`text_to_iso`, `iso_to_name`, aliases)
  - Teste de regressao de busca: mesmas queries de antes retornam mesmos resultados (ou mais, pelos 263K extras)
  - Validacao de score: comparar score antes/depois da migracao de peers
- **Validacao de performance:** Confirmar que queries usam indice de `pais` em vez de table scan em `pais_nome`
- **Risco:** Zero (so leitura)
- **Criterio de aceite:** Todas as rotas funcionam com entrada em PT, EN, sem acento e ISO. Score nao regrediu. Share/OG mostra nome bonito.

---

### Etapa 11 — Documentacao

- **O que:**
  - Marcar `pais_nome` como campo de display nos docs de schema
  - Documentar contrato de entrada/saida de pais: sistema aceita "France"/"Franca"/"franca"/"fr", sempre exibe nome bonito em PT-BR
  - Atualizar coordenacao da pesquisa (`00_COORDENACAO_PESQUISA_NOTA_WCF_V2.md`) marcando aba 01 como concluida e implementada
- **Onde:** `database/schema_completo.md`, `database/schema_atual.md`, coordenacao da pesquisa
- **Risco:** Zero

---

### Etapa 12 — (FUTURO, nao agora) Drop column `pais_nome`

- **Pre-requisitos:**
  1. Zero dependencia runtime restante de `pais_nome` (confirmado via grep)
  2. Periodo de observacao para garantir que nenhum writer externo (vivino-broker, scrapers) ainda toca `pais_nome`
- **Quando:** Decisao do Murilo, quando se sentir seguro
- **Risco:** Medio
- **Reversivel:** Nao

---

## 5. Ordem de execucao e dependencias

```
Etapa 1   Modulo central de paises        ← fundacao, tudo depende disso
  │
  ├── Etapa 2   Revisao dos 19 ambiguos   ← independente
  │
  └── Etapa 3   Score pipeline + trigger   ← depende do modulo (iso_to_name)
        │
        └── Etapa 4   Backfill 263K        ← so depois que trigger nao observa pais_nome
              │
              ├── Etapa 5   Contrato de display (decisao)
              │     │
              │     ├── Etapa 6   Migrar readers       ← depende do contrato
              │     ├── Etapa 7   Migrar writers       ← depende do modulo
              │     └── Etapa 8   Frontend share/OG    ← depende do contrato
              │
              └── Etapa 9   Canonizar pais_nome existente (decisao)
                    │
                    └── Etapa 10  Testar tudo
                          │
                          └── Etapa 11  Documentacao
                                │
                                └── Etapa 12  Drop column (FUTURO)
```

---

## 6. Resumo visual de risco

```
Etapa 1   Modulo central               ██ zero
Etapa 2   Revisao 19 ambiguos          ██ zero
Etapa 3   Score pipeline + trigger      █████ medio
Etapa 4   Backfill 263K                 ███ baixo (apos trigger migrada)
Etapa 5   Contrato de display           ██ zero (decisao)
Etapa 6   Migrar readers (6+ arq)       ████████ baixo
Etapa 7   Migrar writers (2 arq)        ████ baixo
Etapa 8   Frontend share/OG             ███ baixo
Etapa 9   Canonizar pais_nome           ███ baixo (apos trigger migrada)
Etapa 10  Testar tudo                   ██ zero
Etapa 11  Documentacao                  ██ zero
Etapa 12  Drop column (FUTURO)          █████ medio — NAO AGORA
```

---

## 7. Premissas e restricoes

- REGRA 2 do CLAUDE.md: NAO deletar dados existentes, NAO alterar colunas existentes (so adicionar novas)
- REGRA 1: SEMPRE perguntar antes de commit/push
- REGRA 0: respostas simples, sem jargao, caminhos completos
- Backfill so preenche campos vazios — nunca sobrescreve valor existente (exceto etapa 9, se aprovada)
- Trigger novo e criado como nova migration, nao edita migrations anteriores
- Nenhuma sub-etapa comeca sem o modulo central da etapa 1
- Score pipeline migra ANTES do backfill pra evitar blast radius
- Writers migram pra garantir que dados novos ja entram consistentes
