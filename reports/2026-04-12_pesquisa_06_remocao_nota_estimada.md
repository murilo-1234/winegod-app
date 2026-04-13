# Pesquisa 6 — Estudo para remoção segura de `nota_estimada`

**Data:** 2026-04-12
**Tipo:** Pesquisa de impacto (somente leitura — nada foi alterado)
**Escopo:** winegod-app, winegod, vivino-broker, vivino_db (local), winegod (Render)

---

## 1. Resumo Executivo

`nota_estimada` não existe hoje no banco de produção (Render) e não foi encontrada evidência de que tenha sido criada lá — nenhuma migration, SQL ou script do produto a referencia. Ela só existe no banco local (`vivino_db.vivino_vinhos`). O produto (`winegod-app`) não lê, não escreve e não depende dela — zero referências em código funcional (Python, JavaScript/TypeScript, SQL, scripts). Ainda existem referências documentais/históricas em prompts e reports.

O **único escritor ativo** é o `vivino-broker/server.js`, que recalcula `nota_estimada` toda vez que processa reviews de um vinho. Esse processo está rodando agora (re-scrape de 147K vinhos, ~60 dias restantes).

**Não existe nenhum leitor ativo** de `nota_estimada` em código funcional do produto. A migration `002_import_vivino.py` é um **leitor legado/morto** — faz SELECT do campo mas descarta o valor (não mapeia no INSERT). Ainda existem referências documentais em prompts e reports que tratam o campo como conceito histórico.

O risco principal não é técnico — é **documental**. O `PROMPT_CTO_WINEGOD_V2.md` ainda tem planos futuros que dizem "recalcular nota_estimada e subir pro Render". Se alguém seguir isso ao pé da letra, vai reintroduzir o campo que foi decidido remover.

---

## 2. Inventário de Dependências

### 2.1 Código funcional (onde aparece em lógica executável)

| Localização | Arquivo | Tipo | Status |
|---|---|---|---|
| `vivino-broker` (EXTERNO) | `server.js:553,568` | **ESCRITOR ATIVO** | Rodando agora. Escreve em `vivino_vinhos.nota_estimada` no banco local |
| `winegod` (EXTERNO) | `migrations/002_import_vivino.py:80` | LEITOR MORTO | Faz SELECT mas descarta o valor — não usa no INSERT |

### 2.2 Código do produto (winegod-app)

| Camada | Referências encontradas |
|---|---|
| `backend/` (Python) | **Zero em código funcional** |
| `frontend/` (JS/TS) | **Zero em código funcional** |
| `scripts/` (calc_wcf, calc_score) | **Zero em código funcional** |
| `database/` (SQL, migrations) | **Zero em código funcional** |
| `backend/services/display.py` | Usa `"estimated"` como valor de `display_note_type` — **conceito diferente**, não é a coluna `nota_estimada` |

### 2.3 Documentação (menções como conceito)

| Arquivo | Natureza |
|---|---|
| `prompts/PROMPT_CTO_WINEGOD_V2.md` (linhas 151, 1222, 2334) | **RISCO:** Planos futuros mencionam recalcular e subir nota_estimada pro Render |
| `prompts/ETAPA_1_INVESTIGACAO_NOTA_ESTIMADA.md` | Investigação histórica (dados estatísticos) |
| `prompts/HANDOFF_RECALC_WCF_UPLOAD_RENDER.md` (linha 25) | Referência ao schema do vivino_db local |
| `prompts/nota_wcf_v2_research/00_COORDENACAO_PESQUISA_NOTA_WCF_V2.md` | Coordenação — diz que nota_estimada sai da decisão |
| `reports/2026-04-11_handoff_nota_wcf_v2.md` | Handoff com decisão documentada de remoção |
| `reports/2026-04-12_meta_analysis_nota_wcf_v2.md` | Meta-análise — menção tangencial |

---

## 3. Escritores Ainda Ativos

| # | Quem | Onde | O que faz | Banco afetado |
|---|---|---|---|---|
| 1 | `vivino-broker/server.js` função `recalculateEstimatedRating()` | `C:\Users\muril\vivino-broker\server.js:520-573` | Calcula média ponderada bayesiana dos reviews (peso = sqrt do total_ratings do reviewer). Escreve resultado em `nota_estimada` ou NULL se sem dados. | `vivino_db.vivino_vinhos` (LOCAL) |

**Detalhes da fórmula do broker:**
- Constantes: `ESTIMATED_RATING_GLOBAL_MEAN = 3.5`, `ESTIMATED_RATING_DUMMY_WEIGHT = 3.0`
- Fórmula: média bayesiana (weighted average + prior pull)
- Chamada: toda vez que reviews de um vinho são processados via `/api/vivino/broker/reviews`
- Status: **ATIVO AGORA** — o re-scrape dos 147K vinhos está rodando e chama essa função

**Não existe nenhum outro escritor** em nenhum repo analisado.

---

## 4. Leitores Ainda Ativos

**Nenhum leitor ativo em código funcional do produto.** Existe um leitor legado/morto externo.

| Candidato | Verificação | Resultado |
|---|---|---|
| Backend Python (`winegod-app`) | grep em todo o `backend/` | Zero em código funcional |
| Frontend (Next.js) | grep em todo o `frontend/` | Zero em código funcional |
| Scripts (calc_wcf, calc_score) | grep em `scripts/` | Zero em código funcional |
| SQL / Migrations (winegod-app) | grep em `database/` e `*.sql` | Zero em código funcional |
| Migration 002 (`winegod`) | Lê no SELECT mas não usa no INSERT | **Leitor legado/morto** — valor é buscado e descartado |
| `display.py` | Usa `"estimated"` como `display_note_type` | **Conceito diferente** — não é a coluna |
| `baco_system.py` | Usa `"estimated"` na formatação de notas | **Conceito diferente** — não é a coluna |
| Banco Render (views/triggers/functions) | Coluna não existe na tabela `wines` | Não se aplica |

---

## 5. Estado nos Bancos de Dados

### 5.1 Banco de produção — `winegod` (Render)

- Tabela `wines`: 35 colunas documentadas nos schemas (`schema_atual.md` e `schema_completo.md`, ambos de 2026-03-27) — **`nota_estimada` não consta**
- Nenhuma migration SQL no repo `winegod-app/database/` cria ou referencia essa coluna
- A migration `002_import_vivino.py` (repo `winegod`) lê o campo do banco local mas não escreve no Render
- Não foram encontradas views, triggers, functions ou índices que referenciem o campo
- **Evidência:** baseada em documentação de schema + ausência em migrations + ausência em código. Não foi feita verificação direta via `psql` no Render nesta pesquisa

### 5.2 Banco local — `vivino_db`

- Tabela `vivino_vinhos`: **TEM a coluna `nota_estimada`**
- 932.222 vinhos com valor preenchido (de 1.738.585 total) — dado da Etapa 1
- O re-scrape em andamento está gerando mais escritas nessa coluna agora
- Não foram identificadas views ou triggers no banco local que dependam do campo (apenas o broker escreve via UPDATE direto)

---

## 6. Plano de Desativação Seguro

### Etapa 1 — Limpar documentação contraditória (pode fazer agora)

**O que:** Atualizar `PROMPT_CTO_WINEGOD_V2.md` para remover os planos de "recalcular nota_estimada e subir pro Render" (linhas 1222 e 2334).

**Por que:** Esses planos contradizem a decisão já tomada. Se alguém seguir o CTO prompt ao pé da letra, vai reintroduzir o que foi decidido remover.

**Risco:** Nenhum. É só texto.

### Etapa 2 — Parar de escrever (após conclusão do re-scrape, ~60 dias)

**O que:** Remover a função `recalculateEstimatedRating()` do `vivino-broker/server.js` e as duas queries UPDATE (linhas 551-556 e 566-571).

**Por que:** Depois que o re-scrape terminar, não haverá mais razão para calcular nota_estimada. A nota WCF já substituiu esse conceito no produto.

**Risco:** Baixo. O broker continuaria funcionando — só pararia de calcular um valor que ninguém lê. Verificar antes se algum outro script surgiu entre agora e a data da remoção.

**Alternativa conservadora:** Em vez de remover a função, adicionar um flag `SKIP_NOTA_ESTIMADA=true` no broker. Isso permite reverter sem redeploy se algo inesperado aparecer.

### Etapa 3 — Monitorar (2-4 semanas após Etapa 2)

**O que:** Confirmar que nada quebrou. Verificar:
- Logs do broker (sem erros novos)
- Produto funcionando normalmente
- Nenhum novo script referenciando `nota_estimada`

**Critério de sucesso:** Zero menções a `nota_estimada` em logs, código novo ou issues.

### Etapa 4 — Remover coluna do banco local (após monitoramento)

**Pré-requisito obrigatório:** Rodar grep final em TODOS os repos (`winegod-app`, `winegod`, `vivino-broker`) por `nota_estimada` em arquivos `.py`, `.js`, `.ts`, `.sql`. Confirmar zero referências em código funcional antes de prosseguir.

**O que:** `ALTER TABLE vivino_vinhos DROP COLUMN nota_estimada;` no `vivino_db` local.

**Por que:** Limpar o schema. A coluna com 932K+ valores ocupa espaço desnecessário.

**Risco:** Baixíssimo se as etapas anteriores foram cumpridas. Fazer backup do vivino_db antes por segurança.

**Nota:** Essa migration é NO banco LOCAL (`vivino_db`), não no Render. No banco de produção não foi encontrada evidência de que essa coluna exista.

### Etapa 5 — Limpeza documental e histórica

**O que:** Atualizar ou arquivar todas as referências documentais restantes:

- `prompts/ETAPA_1_INVESTIGACAO_NOTA_ESTIMADA.md` — marcar como histórico/arquivado (adicionar header dizendo que `nota_estimada` foi descontinuada)
- `prompts/HANDOFF_RECALC_WCF_UPLOAD_RENDER.md` (linha 25) — remover `nota_estimada` da tabela do schema do vivino_db
- `prompts/nota_wcf_v2_research/00_COORDENACAO_PESQUISA_NOTA_WCF_V2.md` — atualizar status da frente para "concluída/removida"
- `reports/2026-04-11_handoff_nota_wcf_v2.md` — já documenta a decisão de remoção, manter como está (é registro histórico)
- `reports/2026-04-12_meta_analysis_nota_wcf_v2.md` — menção tangencial, manter como está
- `winegod/migrations/002_import_vivino.py` — remover `v.nota_estimada` do SELECT (leitor legado/morto, dead code)

**Grep final de confirmação:** Após a limpeza, rodar grep em todos os repos. Referências restantes devem ser apenas em documentos de histórico claramente marcados como arquivados.

---

## 7. Critérios para Saber que Já É Seguro Apagar

A coluna `nota_estimada` pode ser removida do `vivino_db` quando TODOS estes critérios forem verdadeiros:

| # | Critério | Como verificar |
|---|---|---|
| 1 | Re-scrape dos 147K vinhos concluído | `SELECT COUNT(*) FROM vivino_vinhos WHERE reviews_coletados = FALSE;` → 0 |
| 2 | Função `recalculateEstimatedRating()` removida do broker | grep no `server.js` → zero matches |
| 3 | Nenhum novo código referencia o campo | grep em TODOS os repos (`winegod-app`, `winegod`, `vivino-broker`) → zero matches em `.py`, `.js`, `.ts`, `.sql` |
| 4 | Documentação CTO atualizada (sem planos de recalcular) | grep em `PROMPT_CTO_WINEGOD_V2.md` → zero menções operacionais |
| 5 | 2+ semanas sem incidentes após parar de escrever | Logs do broker e produto sem erros relacionados |

---

## 8. Riscos

| # | Risco | Gravidade | Probabilidade | Mitigação |
|---|---|---|---|---|
| 1 | **Alguém segue o CTO prompt e tenta subir nota_estimada pro Render** | Alta | Média | Limpar linhas 1222 e 2334 do CTO prompt agora (Etapa 1) |
| 2 | **Remover a coluna do vivino_db enquanto o broker ainda escreve** | Alta | Baixa | Só remover a coluna DEPOIS de remover a função do broker |
| 3 | **Novo script surge no intervalo que usa nota_estimada** | Média | Baixa | Grep completo em todos os repos antes de cada etapa |
| 4 | **Confusão entre "estimated" (display_note_type) e "nota_estimada" (coluna)** | Média | Média | São conceitos 100% diferentes — documentar isso claramente |
| 5 | **Perda de dados históricos (932K notas calculadas)** | Baixa | Baixa | Backup do vivino_db antes de DROP COLUMN |

---

## 9. Recomendação Final

**A remoção é segura e bem fundamentada. O campo já está morto no produto.**

Ações imediatas (pode fazer agora):
- **Atualizar o CTO prompt** para remover os planos contraditórios de "recalcular nota_estimada e subir pro Render"

Ações após o re-scrape (~60 dias):
- **Remover a função do broker** → monitorar → **remover a coluna do vivino_db** → **limpar documentação histórica**

No banco de produção (Render), não foi encontrada evidência de que a coluna exista — não há nada para remover lá.

A única dependência real e ativa é o `vivino-broker/server.js` escrevendo no banco local. Tudo mais são referências documentais/históricas que devem ser limpas na Etapa 5.

---

## Apêndice: Distinção Crítica — "estimated" vs "nota_estimada"

Existe um risco de confusão entre dois conceitos totalmente diferentes:

| Conceito | O que é | Onde vive | Status |
|---|---|---|---|
| `nota_estimada` (coluna) | Média bayesiana calculada pelo broker a partir de reviews brutos | `vivino_db.vivino_vinhos` (local) | **Sendo removida** |
| `"estimated"` (display_note_type) | Classificação da nota mostrada ao usuário (sample 25-99) | `display.py` e `baco_system.py` (runtime) | **Ativo e correto — não tem relação** |

O `display_note_type = "estimated"` indica que a nota WCF tem entre 25 e 99 reviews de base. É um conceito do produto. NÃO tem conexão com a coluna `nota_estimada` do banco local.
