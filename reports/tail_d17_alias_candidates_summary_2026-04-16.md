# D17 Alias Candidates -- Merged from chunks (2026-04-16)

Data: 2026-04-17 05:27:11
Modo: merge deterministico de chunks read-only (sem INSERT em wine_aliases)

## Resultado curto

- Candidatos D17 validados (mergeados): `75.586`
- `ALIAS_AUTO`: `72.390`
- `ALIAS_QA`: `3.196`
- QA pack: `3.940`
- Chunks agregados: `14`
- Duplicatas dropadas no merge: `0`

## Artefatos

- Full rowset: `C:\winegod-app\reports\tail_d17_alias_candidates_2026-04-16.csv.gz`
- QA CSV: `C:\winegod-app\reports\tail_d17_alias_qa_pack_2026-04-16.csv`

## Contagem por chunk

| chunk | rows |
| --- | --- |
| tail_d17_alias_candidates_2026-04-16_chunk_000.csv.gz | 12.453 |
| tail_d17_alias_candidates_2026-04-16_chunk_001.csv.gz | 10.687 |
| tail_d17_alias_candidates_2026-04-16_chunk_002.csv.gz | 4.560 |
| tail_d17_alias_candidates_2026-04-16_chunk_003.csv.gz | 5.018 |
| tail_d17_alias_candidates_2026-04-16_chunk_004.csv.gz | 7.952 |
| tail_d17_alias_candidates_2026-04-16_chunk_005.csv.gz | 4.229 |
| tail_d17_alias_candidates_2026-04-16_chunk_006.csv.gz | 4.300 |
| tail_d17_alias_candidates_2026-04-16_chunk_007.csv.gz | 5.305 |
| tail_d17_alias_candidates_2026-04-16_chunk_008.csv.gz | 2.926 |
| tail_d17_alias_candidates_2026-04-16_chunk_009.csv.gz | 3.166 |
| tail_d17_alias_candidates_2026-04-16_chunk_010.csv.gz | 4.073 |
| tail_d17_alias_candidates_2026-04-16_chunk_011.csv.gz | 4.282 |
| tail_d17_alias_candidates_2026-04-16_chunk_012.csv.gz | 5.174 |
| tail_d17_alias_candidates_2026-04-16_chunk_013.csv.gz | 1.461 |

## Contagem por lane

| lane | candidatos | qa_sample |
| --- | --- | --- |
| ALIAS_AUTO | 72.390 | 3.620 |
| ALIAS_QA | 3.196 | 320 |

## Contagem por estrato

| estrato | candidatos |
| --- | --- |
| S6_GENERAL_REMAINDER | 64.647 |
| S5_SOURCE_RICH_STRUCTURED | 4.506 |
| S4_MULTI_CLEAN_OR_AMBIG_LINEAGE | 4.267 |
| S2_NO_SOURCE | 1.860 |
| S3_NO_LINEAGE_OR_ORPHAN | 306 |

## Evidencia principal

| evidencia | candidatos |
| --- | --- |
| strong_name_token_overlap>=2 | 37.324 |
| strong_name_and_producer_overlap | 32.445 |
| name_and_source_to_canonical_producer | 1.837 |
| stripped_name | 1.783 |
| y2_plus_text_evidence | 901 |
| exact_name | 831 |
| broad_name_with_strong_producer | 465 |
