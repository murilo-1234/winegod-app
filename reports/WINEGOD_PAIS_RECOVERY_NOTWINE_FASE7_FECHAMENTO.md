# WINEGOD_PAIS_RECOVERY — Fase 7 (notwine escondidos): Fechamento

Data: 2026-04-21
Arquivo analisado: `reports/notwine_escondidos_candidatos_2026-04-17.md` (588 wines).

## Varredura automatica de padroes

Scan de regex sobre nomes + produtores, em busca de grupos repetidos
que justificariam adicionar termo ao `wine_filter.py` + `pre_ingest_filter.py`.

| Padrao | Hits | Decisao |
|---|---:|---|
| `reposado` / `anejo` / `añejo` / `joven` (tequila) | 4 | **Nao aplicar** — muito raro (0,68% do set), risco FP em vinhos espanhois/mexicanos |
| Sake/soju/shoyu | 1 | ja coberto no filtro atual |
| Liqueur/licor/aperitif | 3 | ja coberto (`liqueur`, `aperitif` estao no filtro) |
| Beer/ale/lager | 1 | ja coberto |
| Pack/caixa/case+numero | 7 | ja coberto via `pre_ingest_filter.CASE_NUM_RE*` |
| "Red"/"White"/"Blanc" solo | 21 | **NAO suprimir** — sao nomes pobres mas vinhos validos |
| "Dry Red" / "Sparkling White" | 8 | idem (padrao legitimo de rotulo) |
| MMIX/MMV (latim) | 3 | safra em latim — vinho valido |
| "Brut" solo | 5 | espumante valido |

## Produtores repetidos (>= 3 hits)

- 378 entradas sem produtor — isso nao e padrao de notwine, e sinal de
  metadados pobres. Nao justifica supressao.
- `Tree of Life` (6), `Aldi` (4), `Elite Collection`/`Gile`/`Eleven Buddies`/
  `Soul Wine`/`Marks & Spencer`/`Brothers Line` (3 cada).
- Nenhum desses e marca de destilado conhecida. Sao varejistas/labels
  privadas e colecoes genericas. Vinhos mal-cadastrados, nao notwine.

## Decisao

**Arquivar sem acao automatica.**

Razoes:
- Os 588 sao 0,023% do banco ativo (2,22M wines). Ganho marginal.
- Qualquer supressao automatica baseada nesses padroes geraria FP em
  vinhos legitimos (o produtor `Venus` tem vinho chamado `Blanc` — isso
  e nome valido, nao e liqueur).
- `wine_filter.py` + `pre_ingest_filter.py` ja capturam todos os
  padroes fortes que aparecem neste set.

## Se aparecer volume maior (regra futura)

Se um dia surgir um set de candidatos notwine com padroes concentrados
(>= 5% do set num unico termo), revisitar: adicionar no `wine_filter.py`,
propagar pro `pre_ingest_filter.py` (regra de propagacao documentada em
memoria), dry-run, medir FP, aplicar suppress em chunks via
`wine_filter_apply_suppress.py`.

## Arquivos

- Script de analise reproduzivel: inline no final deste documento.
- Lista original: `reports/notwine_escondidos_candidatos_2026-04-17.md`
  (nao deletar — arquivo historico).

```python
# Script usado pra varredura (inline, reproduzivel)
import re, collections
lines = open('reports/notwine_escondidos_candidatos_2026-04-17.md', encoding='utf-8').readlines()
entries = []
for line in lines:
    m = re.match(r'\|\s*\d+\s*\|\s*(\d+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|', line)
    if m:
        entries.append((int(m.group(1)), m.group(2).strip(), m.group(3).strip()))
# ... aplicar regex por padrao, contar hits ...
```
