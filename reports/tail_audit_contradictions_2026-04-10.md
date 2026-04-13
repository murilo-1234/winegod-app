# Contradicoes Factuais -- Documentos Historicos vs Estado Live

Data execucao: 2026-04-10 19:08:17
Executor: `scripts/audit_tail_snapshot.py`

## Principio Metodologico

- **FATO** = valor live obtido por query nesta execucao, comparado a valor historico documentado.
- **HIPOTESE** = explicacao operacional **NAO provada** por artefato verificavel nesta etapa.

Nenhuma linha desta secao deve ser lida como prova de execucao de `DELETE`, script ou cleanup. Onde houver suposicao causal, ela aparece explicitamente como `HIPOTESE ... NAO PROVADA`.

## Fatos Verificaveis -- Delta live vs historico

Cada linha compara um valor historico documentado com o valor live obtido nesta execucao.

| tema | fonte_historico | valor_historico | valor_live | delta | delta_% | status |
|---|---|---|---|---|---|---|
| wine_sources_total | HANDOFF_AUDITORIA_LINHAGEM_LINKS_RENDER.md (2026-04-06) | 3,659,501 | 3,484,975 | -174,526 | -4.77% | CONTRADIZ |
| stores_total | HANDOFF_AUDITORIA_LINHAGEM_LINKS_RENDER.md (2026-04-06) | 19,881 | 19,889 | +8 | +0.04% | CONTRADIZ (menor) |
| new_without_sources | HANDOFF_AUDITORIA / PROMPT_RECRIAR_WINE_SOURCES_FALTANTES.md | ~76,812 | 8,071 | -68,741 | -89.49% | CONTRADIZ (massivo) |

### Nota sobre `database/schema_atual.md`

O prompt Etapa 1 orienta tratar `database/schema_atual.md` como historico, nao como fonte de verdade live. **Fato**: as contagens live desta auditoria nao dependem de `schema_atual.md`.

## Hipoteses Operacionais -- NAO PROVADAS nesta etapa

As explicacoes abaixo sao plausiveis mas **nao sao confirmadas por nenhum log, query, commit, tag ou artefato referenciavel** dentro desta etapa. Nao devem ser lidas como fato ate que uma evidencia verificavel confirme.

- **HIPOTESE H1** -- `wine_sources_total` -174,526 (-4.77%)
  - Plausivel: o delta pode decorrer de limpeza de `wine_sources` associados ao vinho errado (tema `wrong_wine_association` discutido em `HANDOFF_AUDITORIA_LINHAGEM_LINKS_RENDER.md`).
  - Esta etapa NAO verifica log de `DELETE`, commit, tag, nem execucao de cleanup.
  - **NAO PROVADA.**

- **HIPOTESE H2** -- `new_without_sources` -68,741 (-89.49%)
  - Plausivel: o delta pode decorrer da execucao do script descrito em `PROMPT_RECRIAR_WINE_SOURCES_FALTANTES.md`, que visa recriar `wine_sources` para wines da cauda.
  - Esta etapa NAO verifica log de execucao, contagem antes/depois, commit ou tag desse script.
  - **NAO PROVADA.**

- **HIPOTESE H3** -- `stores_total` +8 (+0.04%)
  - Plausivel: adicao incremental de lojas via pipeline de scraping.
  - Esta etapa NAO verifica quando e como essas lojas foram adicionadas.
  - **NAO PROVADA.**

Nenhuma dessas hipoteses e necessaria para sustentar o snapshot live. Elas apenas tentam explicar o delta entre docs historicos e estado atual; nao mudam o que e fato.

## Fatos Historicos Confirmados pelo Live

Valores de referencia da Etapa 1 reconfirmados nesta execucao:

- `wines_total` = 2,506,441
- `wines_com_vivino_id` = 1,727,058
- `wines_sem_vivino_id` = 779,383
- `wine_aliases_approved` = 43
- `canonical_distintos` = 23
- `wine_sources_total` = 3,484,975
- `stores_total` = 19,889
- `cauda_sem_sources` = 8,071
- `cauda_com_sources` = 771,312
- `vivino_vinhos_total` = 1,738,585
- `y2_matched_vivino` = 1,465,480
- `y2_matched_07` = 648,374
- `in_both` = 1,727,058
- `only_vivino_db` = 11,527
- `only_render` = 0

## Fatos Historicos Desatualizados (live nao confirma)

- `wine_sources_total` NAO e mais 3,659,501 (historico) -- live: 3,484,975
- `stores_total` NAO e mais 19,881 (historico) -- live: 19,889
- `new_without_sources` NAO e mais ~76,812 (historico) -- live: 8,071
- `wines_com_link` e `wines_sem_link` (HANDOFF_AUDITORIA 2026-04-06) nao foram revalidados nesta etapa; tratar como desatualizados.

