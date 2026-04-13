# Pilot 120 -- Instrucoes para Murilo

Data: 2026-04-11
Arquivo a preencher: `C:\winegod-app\reports\tail_pilot_120_for_murilo_2026-04-10.csv`

---

## 1. O que voce vai fazer

Revisar 120 wines da cauda Vivino e preencher 4 campos de classificacao + 1 campo livre de anotacoes, para cada wine.

Voce NAO precisa classificar nada alem desses 5 campos.
Voce NAO precisa rodar scripts.
Voce NAO precisa escrever em banco.

O arquivo ja vem com a classificacao R1 do Claude visivel nas colunas `r1_*` para voce comparar -- concorde ou discorde, sem pressao.

Este pilot inteiro (120 wines) sera usado para medir concordancia Claude vs Murilo. Cada wine conta.

---

## 2. Arquivo de trabalho

**Caminho absoluto:** `C:\winegod-app\reports\tail_pilot_120_for_murilo_2026-04-10.csv`

Tem **120 linhas** (1 por wine) e 49 colunas. Abre em Excel, LibreOffice, Google Sheets, ou editor de texto.

Quando abrir em Excel, salve de volta mantendo `encoding = UTF-8 (Comma delimited)`. Se usar LibreOffice, no "Save As" escolha CSV e marque `Keep Current Format`.

**Nao renomeie o arquivo.** O validador e o comparador apontam para esse nome.

---

## 3. Colunas que voce deve preencher

Apenas as 5 colunas que comecam com `murilo_`:

| coluna | o que e | obrigatorio? |
|---|---|---|
| `murilo_business_class` | sua classe final para o wine | sim |
| `murilo_review_state` | seu estado de revisao | sim |
| `murilo_confidence` | sua confianca na decisao | sim |
| `murilo_action` | acao operacional recomendada | sim |
| `murilo_notes` | texto livre (opcional mas util) | nao |

Todas as demais colunas sao contexto/leitura. **Nao altere nada fora dos campos `murilo_*`**.

---

## 4. Valores validos (taxonomia oficial)

### `murilo_business_class`
- `MATCH_RENDER` -- este wine e o mesmo que um canonico que ja existe no Render (deve virar alias)
- `MATCH_IMPORT` -- este wine e o mesmo que um canonico no vivino_db local mas ainda nao esta no Render
- `STANDALONE_WINE` -- e um vinho real mas nao tem canonico igual em nenhum lado (mantem solo)
- `NOT_WINE` -- nao e vinho (alias: whisky, suco, sabao, voucher, etc.)

### `murilo_review_state`
- `RESOLVED` -- voce decidiu com confianca
- `SECOND_REVIEW` -- voce decidiu mas quer um segundo par de olhos (ou achou ambiguo)
- `UNRESOLVED` -- voce NAO conseguiu decidir (dados ruins, caso muito raro, etc.)

### `murilo_confidence`
- `HIGH` -- tem certeza
- `MEDIUM` -- bastante certo mas com alguma duvida
- `LOW` -- mais duvida do que certeza, palpite educado

### `murilo_action`
- `ALIAS` -- aponta este wine para o canonico Render (so faz sentido com `MATCH_RENDER`)
- `IMPORT_THEN_ALIAS` -- primeiro trazer o canonico do vivino_db pro Render, depois alias (so faz sentido com `MATCH_IMPORT`)
- `KEEP_STANDALONE` -- manter como wine unico (faz sentido com `STANDALONE_WINE`)
- `SUPPRESS` -- suprimir/ocultar do produto (faz sentido com `NOT_WINE`)

A relacao canonica `business_class -> action`:

| business_class | action esperada |
|---|---|
| `MATCH_RENDER` | `ALIAS` |
| `MATCH_IMPORT` | `IMPORT_THEN_ALIAS` |
| `STANDALONE_WINE` | `KEEP_STANDALONE` |
| `NOT_WINE` | `SUPPRESS` |

O validador emite **warning** (nao fail) se voce quebrar essa relacao. Voce pode quebra-la em casos especiais com nota no `murilo_notes` explicando por que.

---

## 5. Como tratar os casos

### 5.1 Caso obvio (HIGH confidence, RESOLVED)
- Abra a linha, leia nome/produtor/safra/tipo, olhe os candidatos sugeridos em `top1_render_human` e `top3_render_summary`
- Se bater, preencha:
  - `murilo_business_class = MATCH_RENDER`
  - `murilo_review_state = RESOLVED`
  - `murilo_confidence = HIGH`
  - `murilo_action = ALIAS`
- Pode deixar `murilo_notes` vazio

### 5.2 Caso ambiguo (gap zero, empate SQL)
- Se o top1 render tem score bom mas `top1_render_gap = 0`, existem varios canonicos empatados. Olhe `top3_render_summary` para ver quem mais empata. Se o top1 e claramente o correto, `MATCH_RENDER` + `SECOND_REVIEW` + `MEDIUM`. Se nenhum dos 3 bate bem, `STANDALONE_WINE` + `SECOND_REVIEW` + `LOW`.
- Anote no `murilo_notes` o motivo, ex.: "top1 bate melhor que top2" ou "nenhum dos 3 e o mesmo winemaker".

### 5.3 Nao-vinho claro (NOT_WINE)
- Se o nome e obviamente nao-vinho (voce ve isso lendo), preencha `NOT_WINE` + `RESOLVED` + `HIGH` + `SUPPRESS`.
- A coluna `wine_filter_category` mostra se o filtro de palavras ja capturou. Se `wine_filter_category` estiver preenchida, o Claude ja propos `NOT_WINE` -- voce so valida.
- Se `wine_filter_category` esta vazia mas `y2_any_not_wine_or_spirit=1`, significa que alguma run de y2 marcou como nao-vinho mas o filtro nao. Use julgamento humano: se for comida ou destilado, `NOT_WINE`; se for wine non-alcoolico (ex.: "Ara Zero Rosé"), eh seu criterio -- anote em `murilo_notes`.

### 5.4 Dados insuficientes (UNRESOLVED)
- Se nome esta quebrado, produtor vazio, sem candidatos, ou voce genuinamente nao sabe, preencha:
  - `murilo_business_class = STANDALONE_WINE` (best guess)
  - `murilo_review_state = UNRESOLVED`
  - `murilo_confidence = LOW`
  - `murilo_action = KEEP_STANDALONE`
- Anote em `murilo_notes`: "dados insuficientes" ou motivo especifico.
- Regra oficial do projeto: **`UNRESOLVED` nunca e business_class**. business_class sempre tem que ser um dos 4 valores. UNRESOLVED vai em review_state apenas.

### 5.5 Concorde com o Claude
- Voce pode simplesmente copiar os valores das colunas `r1_*` para as colunas `murilo_*` correspondentes quando concordar integralmente. Isso ainda conta como revisao valida.

### 5.6 Discorde do Claude
- Preencha a sua decisao. O comparador vai listar os disagreements e vamos passar por eles juntos na adjudicacao.

---

## 6. Colunas de contexto que ajudam voce

Use essas colunas (nao mexa nelas) para fundamentar sua decisao:

| coluna | para que serve |
|---|---|
| `pilot_bucket_proxy` | onde o pilot caiu o wine na estratificacao (P1..P6) -- NAO e business_class |
| `block` | de qual bloco do working pool o wine veio (random / no_source / suspect_not_wine) |
| `overflow_from` | se o pilot pegou do overflow (quando P5 faltou) |
| `wine_filter_category` | se o filtro lexical bloqueou (se preenchida, e sinal forte de NOT_WINE) |
| `y2_any_not_wine_or_spirit` | baseline y2 -- sinal, nao verdade |
| `reason_short_proxy` | razao curta que colocou o wine no bucket |
| `nome`, `produtor`, `safra`, `tipo` | metadata do proprio wine |
| `preco_min`, `wine_sources_count_live` | impacto operacional |
| `no_source_flag` | 1 = sem fonte ativa (ja deveria estar em UNRESOLVED se nao bater em nada) |
| `top1_render_candidate_id` + `top1_render_human` | candidato top1 render proposto pelo Claude |
| `top3_render_summary` | os 3 melhores candidatos render, legivel, ja em ordem |
| `top1_import_*`, `top3_import_summary` | idem para import (raramente util na cauda) |
| `r1_business_class` ... `r1_match_blockers` | a classificacao completa do Claude |
| `murilo_review_reason` | porque Claude marcou este wine como "precisa do Murilo" |

---

## 7. Quando terminar

1. Salve o arquivo (UTF-8, comma-delimited, mesmo nome).
2. Rode o validador para conferir erros:
   ```
   cd C:\winegod-app
   python scripts/validate_murilo_csv.py
   ```
   - Exit `0`: tudo ok, pode passar para a proxima etapa.
   - Exit `1`: tem erro estrutural, leia a mensagem e corrija.
   - Exit `2`: arquivo estruturalmente ok mas ainda vazio (aconteceu se voce rodou antes de preencher).
3. Rode o comparador para gerar o relatorio de concordancia:
   ```
   python scripts/compare_claude_vs_murilo.py
   ```
4. Rode o builder de adjudicacao para gerar a lista de disagreements:
   ```
   python scripts/build_adjudication_template.py
   ```
5. Artefatos gerados:
   - `reports/tail_pilot_120_concordance_2026-04-10.md` -- relatorio de concordancia
   - `reports/tail_pilot_120_disagreements_2026-04-10.csv` -- apenas os casos divergentes
   - `reports/tail_pilot_120_adjudication_2026-04-10.csv` -- CSV para adjudicar os disagreements

Depois a gente abre o CSV de adjudicacao juntos e decide os casos divergentes.

---

## 8. Regras sagradas

- **Nao renomeie o arquivo.**
- **Nao altere colunas fora de `murilo_*`.**
- **Nao apague linhas.** Se voce nao quer classificar, deixe os campos vazios -- o comparador trata. Mas tente preencher tudo.
- **`UNRESOLVED` NAO e business_class.** Use em `review_state` apenas.
- **y2 nao e verdade.** Use como baseline/sinal, nao como decisao.
- **Este pilot e calibragem.** Ele nao vira producao automaticamente. Suas respostas vao calibrar thresholds para a proxima rodada.

Qualquer duvida durante o preenchimento, anote em `murilo_notes`. Se travar em um caso, deixe os 4 campos vazios nesse row e continue -- o validador vai reportar os pendentes no fim.
