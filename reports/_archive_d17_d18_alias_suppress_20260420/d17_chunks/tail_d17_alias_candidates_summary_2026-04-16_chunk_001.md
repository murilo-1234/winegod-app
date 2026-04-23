# D17 Alias Candidates -- Materializacao para QA

Data: 2026-04-17 03:21:17
Modo: read-only contra Render; sem INSERT em `wine_aliases`

## Resultado curto

- Candidatos D17 validados: `10.687`
- `ALIAS_AUTO`: `10.416`
- `ALIAS_QA`: `271`
- QA pack humano: `549` linhas
- Runtime: `685s`

## Artefatos

- Full rowset: `C:\winegod-app\reports\tail_d17_alias_candidates_2026-04-16_chunk_001.csv.gz`
- QA CSV: `C:\winegod-app\reports\tail_d17_alias_qa_pack_2026-04-16_chunk_001.csv`

## Contagem por lane

| lane | candidatos | qa_sample |
| --- | --- | --- |
| ALIAS_AUTO | 10.416 | 521 |
| ALIAS_QA | 271 | 28 |

## Contagem por estrato

| estrato | candidatos |
| --- | --- |
| S6_GENERAL_REMAINDER | 9.658 |
| S5_SOURCE_RICH_STRUCTURED | 451 |
| S4_MULTI_CLEAN_OR_AMBIG_LINEAGE | 370 |
| S2_NO_SOURCE | 205 |
| S3_NO_LINEAGE_OR_ORPHAN | 3 |

## Evidencia principal

| evidencia | candidatos |
| --- | --- |
| strong_name_token_overlap>=2 | 5.316 |
| strong_name_and_producer_overlap | 4.832 |
| name_and_source_to_canonical_producer | 179 |
| stripped_name | 158 |
| y2_plus_text_evidence | 113 |
| broad_name_with_strong_producer | 61 |
| exact_name | 28 |

## Suppress removido antes do D17

| reason | wines |
| --- | --- |
| d16_strong_patterns_2026-04-15 | 59.902 |
| d16_wine_filter_expansion_2026-04-15 | 13.320 |
| d16_wine_filter_round3_2026-04-15 | 11.726 |
| d16_wine_filter_round4_2026-04-15 | 19.137 |

## Rejeicoes principais

### Source

| motivo | wines |
| --- | --- |
| suppressed | 104.085 |
| stratum_s1_after_filter | 1.586 |
| wine_filter:flor | 1.128 |
| wine_filter:biere | 812 |
| wine_filter:espresso | 432 |
| wine_filter:beef | 401 |
| wine_filter:armagnac | 340 |
| wine_filter:conditioner | 301 |
| wine_filter:soccer | 273 |
| wine_filter:bacardi | 269 |
| wine_filter:bier | 255 |
| wine_filter:chicken | 250 |
| wine_filter:infusion | 228 |
| wine_filter:chips | 225 |
| wine_filter:cafe | 201 |
| wine_filter:salmon | 196 |
| wine_filter:kase | 187 |
| wine_filter:jus | 163 |
| wine_filter:flores | 162 |
| wine_filter:fish | 160 |
| wine_filter:bra | 151 |
| wine_filter:pork | 136 |
| wine_filter:ham | 135 |
| wine_filter:honey | 132 |
| wine_filter:schnapps | 128 |
| wine_filter:liquore | 121 |
| wine_filter:hoodie | 117 |
| wine_filter:jam | 115 |
| wine_filter:crisp | 102 |
| wine_filter:mel | 100 |

### Candidato

| motivo | ocorrencias |
| --- | --- |
| producer_incompatible | 1.004.495 |
| tipo_mismatch | 340.592 |
| weak_single_token_or_no_text_evidence | 65.475 |
| no_scored_candidate | 21.205 |
| no_candidate_pool | 9.951 |
| score_below_030 | 7.940 |
| s6_medium_excluded_for_d19 | 6.298 |
| s6_auto_floor_weak_name_anchor | 781 |
| s6_auto_floor_weak_evidence | 379 |
| score_gap_below_d17 | 371 |
| s6_auto_floor_no_producer_anchor | 328 |

### Validacao live Render

| motivo | ocorrencias |
| --- | --- |
| <nenhum> | 0 |

## Como revisar

Marque `CORRECT` somente se source e canonical forem o mesmo vinho. Na duvida,
marque `ERROR` ou deixe pendente. O limite operacional original de D17 e erro
abaixo de 3% para alias.
