# WINEGOD PRE_INGEST — QA dos enriched_ready.jsonl (guarded)

Input: `reports/ingest_pipeline_enriched/20260421_120957_vinhos_brasil_vtex_20260421_113807_guarded/enriched_ready.jsonl`
Total auditado: **47**

## Distribuicao de risco

| Nivel | Count |
|---|---:|
| ok | 24 |
| review | 23 |
| **blocker** | 0 |

## Contagem por pais final

| pais | count |
|---|---:|
| fr | 41 |
| pt | 3 |
| es | 2 |
| it | 1 |

## Contagem por modelo Gemini

| modelo | count |
|---|---:|
| gemini-2.5-flash-lite | 47 |

## Sinais de URL hint

- Itens com URL que tem pattern `/vin-XX-`: **40**
- Conflitos URL hint vs pais final: **0** (se > 0 o guardrail falhou — investigar)
- Conflitos `pais` original vs Gemini: **0** (pelo design do merge conservador, pais original e preservado — mas o guardrail tambem bloqueia antes do merge)

## Itens blocker

_Nenhum blocker detectado._

## Itens review (aplicar so aceitando risco)

| router_index | nome | produtor | pais | razoes |
|---|---|---|---|---|
| 127 | Château Léoville-barton | château léoville-barton | fr | REVIEW: produtor_igual_nome |
| 237 | Château Monbrison | château monbrison | fr | REVIEW: produtor_igual_nome |
| 241 | Château de Ferrand | château de ferrand | fr | REVIEW: produtor_igual_nome |
| 353 | Château Lynch-Moussas | château lynch-moussas | fr | REVIEW: produtor_igual_nome |
| 354 | Château Lalande | château lalande | fr | REVIEW: produtor_igual_nome |
| 376 | Château Haut-Bailly | château haut-bailly | fr | REVIEW: produtor_igual_nome |
| 390 | Château Lafaurie-Peyraguey | château lafaurie-peyraguey | fr | REVIEW: produtor_igual_nome |
| 416 | Château Croizet-Bages | château croizet-bages | fr | REVIEW: produtor_igual_nome |
| 431 | Château Clément-Pichon | château clément-pichon | fr | REVIEW: produtor_igual_nome |
| 441 | Château Nenin | château nenin | fr | REVIEW: produtor_igual_nome |
| 444 | Château Canon-La-Gaffelière | château canon-la-gaffelière | fr | REVIEW: produtor_igual_nome |
| 450 | Chateau Beau Sejour Becot | chateau beau sejour becot | fr | REVIEW: produtor_igual_nome |
| 451 | Château Clos Junet | château clos junet | fr | REVIEW: produtor_igual_nome |
| 452 | Château Lassegue | château lassegue | fr | REVIEW: produtor_igual_nome |
| 453 | Château Pavie Decesse | château pavie decesse | fr | REVIEW: produtor_igual_nome |
| 454 | Château Clerc Milon | château clerc milon | fr | REVIEW: produtor_igual_nome |
| 455 | Château D'agassac | château d'agassac | fr | REVIEW: produtor_igual_nome |
| 457 | Château Larrivet Haut-Brion | château larrivet haut-brion | fr | REVIEW: produtor_igual_nome |
| 460 | Château Belle Assise Coureau | château belle assise coureau | fr | REVIEW: produtor_igual_nome |
| 461 | Château Coutet | château coutet | fr | REVIEW: produtor_igual_nome |
| 462 | Château Le Gay | château le gay | fr | REVIEW: produtor_igual_nome |
| 477 | Château Beaumont | château beaumont | fr | REVIEW: produtor_igual_nome |
| 495 | Château Baret | château baret | fr | REVIEW: produtor_igual_nome |

## Nota sobre `produtor_igual_nome` (23 itens)

Inspecao amostral dos 23 items marcados `review:produtor_igual_nome`:
todos sao vinhos franceses do tipo `Château X` / `Domaine X` onde o
**nome do vinho e o mesmo do produtor** por convencao da fonte (Bordeaux
Grand Cru). Exemplos: `Chateau Leoville-Barton`, `Chateau Monbrison`,
`Chateau Haut-Bailly`, `Chateau Croizet-Bages`, `Chateau Lalande`.

Isso **nao e alucinacao** — e padrao de rotulo Bordeaux. O heuristic
`produtor_igual_nome` foi deliberadamente conservador; aqui gera falso
positivo. Em apply real, esses 23 podem ser tratados como `ok` desde
que o operador inspecione a amostra (o CSV tem todos eles).

Nenhum outro heuristic foi disparado neste lote (sem blocker, sem
`possivel_kit`, sem `palavra_not_wine_no_nome`, sem `teor_alcoolico`
atipico, sem URL hint conflitando com pais).

## Recomendacao

Tecnicamente **pronto para apply pequeno**, aguardando autorizacao humana explicita. Existem 23 item(s) em `review` — operador decide se aceita o risco ou retira manualmente.

CSV detalhado: `reports/WINEGOD_PRE_INGEST_ENRICHED_READY_QA_20260421.csv`