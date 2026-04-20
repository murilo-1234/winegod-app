# Archive D17/D18 Alias Suppress

Data da higiene: 2026-04-20

Este diretorio guarda artefatos operacionais e intermediarios do pipeline D17/D18 que nao precisam ficar poluindo a raiz de `reports/`.

## O que ficou no topo de `reports/`

Foram mantidos fora deste arquivo apenas os artefatos finais que servem como referencia direta do fechamento:

- `WINEGOD_ALIAS_SUPPRESS_D18_HANDOFF_OFICIAL.md`
- `WINEGOD_ALIAS_SUPPRESS_D18_DECISIONS.md`
- `tail_d17_alias_candidates_2026-04-16.csv.gz`
- `tail_d17_alias_qa_pack_2026-04-16_final.csv`
- `tail_d17_alias_approved_2026-04-16.csv.gz`
- `tail_d17_alias_freeze_summary_2026-04-16.md`
- `tail_d17_alias_qa_closeout_2026-04-16.md`
- `d18_apply_diff_20260419_221902.csv`
- `d18_alias_suppress_summary_20260419_231915.md`
- `d18_alias_suppress_summary_20260419_234936.md`
- `d18_remove_d17_aliases_summary_20260420_041816.md`
- `d18_reapply_d17_aliases_20260420_041816.sql`

## Subpastas

- `d17_chunks/`
  artefatos chunkados do materializador e do QA pack.
- `d17_support/`
  relatorios e derivados auxiliares de QA/review/export.
- `d18_intermediate/`
  dry-runs, diffs intermediarios e rollbacks operacionais.
- `d18_backups/`
  backups CSV.gz gerados durante apply/suppress/remove.

## Regra pratica

Se alguem precisar reconstruir a historia operacional do D17/D18, consulte primeiro os 2 documentos oficiais no topo de `reports/` e depois use este arquivo como repositorio de apoio.
