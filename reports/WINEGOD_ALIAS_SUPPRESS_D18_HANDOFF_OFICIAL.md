# WINEGOD_ALIAS_SUPPRESS_D18_HANDOFF_OFICIAL

Status oficial: FECHADO COM EXCECAO FORMAL

Data de fechamento: 2026-04-20

Documento de decisoes travadas:
- `C:\winegod-app\reports\WINEGOD_ALIAS_SUPPRESS_D18_DECISIONS.md`

## 1. Escopo que fica oficialmente fechado

- D17 gerou o rowset de candidatos em `C:\winegod-app\reports\tail_d17_alias_candidates_2026-04-16.csv.gz` com `75.586` pares.
- O QA final foi consolidado em `C:\winegod-app\reports\tail_d17_alias_qa_pack_2026-04-16_final.csv`.
- O freeze final rodou e gerou `C:\winegod-app\reports\tail_d17_alias_approved_2026-04-16.csv.gz` com `72.580` aprovados para D18.
- O D18 cumpriu o objetivo operacional de soft-suppress dos source wines duplicados para eles nao aparecerem em fluxos que filtram `suppressed_at IS NULL`.

## 2. O que significa os 3,30%

- O `3,30%` veio do QA da amostra: `130` erros em `3.940` pares revisados.
- Esses `130` casos sao candidatos de alias que foram julgados errados no QA.
- Eles representam risco de match incorreto e, por isso, ficam FORA do lote aprovado.
- Em outras palavras: os `3,30%` NAO sao vinhos que o D18 suprimiu errado; sao aliases da amostra que foram rejeitados no controle de qualidade.

Arquivo de evidencia:
- `C:\winegod-app\reports\tail_d17_alias_qa_closeout_2026-04-16.md` -> `Gate: FAIL`, `Error rate: 3.30%`.

## 3. Excecao formal registrada

- Pelo plano original do handoff de `2026-04-18`, o gate estatistico precisava PASSar abaixo de `3%` antes do freeze e do execute.
- Na pratica, o gate ficou em `3,30%`, portanto FAIL.
- Mesmo assim, o job foi executado porque a decisao operacional final foi tratar o D18 como limpeza de busca/discovery:
  source wines duplicados aprovados devem ser soft-suppressed para nao poluir resultados.
- A interpretacao oficial deste fechamento e:
  D18 = suppress operacional de duplicatas provaveis para busca
  Nao = certificacao de verdade canonica perfeita em `100%` do universo

## 4. Estado final apurado

### 4.1 Freeze e apply

- Freeze aprovado: `72.580` linhas.
- Apply em `wine_aliases` materializado no D18: `72.415` aliases D17 com `source_type = d17_20260419_221902`.
- Diferenca entre freeze e apply: `165` sources aprovados que nao entraram no apply D17; na verificacao final, esses `165` ja estavam suppressed por outro estado anterior e nao precisavam de nova acao.

Arquivos de evidencia:
- `C:\winegod-app\reports\tail_d17_alias_freeze_summary_2026-04-16.md`
- `C:\winegod-app\reports\d18_apply_diff_20260419_221902.csv`

### 4.2 Suppress em wines

- Universo lido pelo suppress: `72.458` aliases aprovados (`72.415` D17 + `43` aliases manuais legados).
- Desses `72.458`:
  - `72.454` terminaram com `suppress_reason = d18_alias_suppress_*`
  - `4` ja estavam suppressed antes por outro motivo
- Rodadas EXECUTE que efetivamente gravaram:
  - `26.500` em `d18_alias_suppress_20260419_224446`
  - `7.750` em `d18_alias_suppress_20260419_230738`
  - `37.954` em `d18_alias_suppress_20260419_231915`
  - `250` em `d18_alias_suppress_20260419_234936`
- O residuo de `250` apos a rodada `231915` foi resolvido na rodada `234936`.
- Estado final do suppress: `targets ainda ativos apos execucao: 0`.

Arquivos de evidencia:
- `C:\winegod-app\reports\d18_alias_suppress_summary_20260419_231915.md`
- `C:\winegod-app\reports\d18_alias_suppress_summary_20260419_234936.md`

## 5. Estado atual de wine_aliases

- Depois do suppress, houve um cleanup adicional:
  `C:\winegod-app\scripts\remove_d17_aliases_keep_suppress.py`
- Em `2026-04-20 04:18`, esse passo removeu `72.415` aliases D17 de `wine_aliases` e deixou apenas `43` aliases manuais aprovados.
- Isso NAO desfaz o suppress em `wines`.
- Portanto, o estado final oficial fica assim:
  - `wines`: sources D18 seguem suppressed
  - `wine_aliases`: aliases D17 foram limpos; permanecem so `43` manuais

Arquivos de evidencia:
- `C:\winegod-app\reports\d18_remove_d17_aliases_summary_20260420_041816.md`
- `C:\winegod-app\reports\d18_reapply_d17_aliases_20260420_041816.sql`

## 6. Interpretacao oficial para o produto

- O trabalho D18 deve ser lido como CONCLUIDO para o objetivo de produto:
  remover duplicatas source dos resultados de busca e discovery via `suppressed_at`.
- O trabalho D18 NAO deve ser lido como prova de que todo alias D17 virou verdade canonica permanente.
- A excecao do gate (`3,30%`) fica aceita e documentada neste arquivo.
- Nao ha acao adicional obrigatoria de banco para fechar este job.

## 7. Pendencia apenas de versionamento

- Este fechamento oficial esta documentado no repo.
- Se quiser formalizacao em historico git, falta apenas commit posterior ao `3c9bf2a4` incluindo este handoff e os summaries finais relevantes.
