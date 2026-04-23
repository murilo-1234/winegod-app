# D17 Alias Candidates -- Materializacao para QA

Data: 2026-04-17 03:09:47
Modo: read-only contra Render; sem INSERT em `wine_aliases`

## Resultado curto

- Candidatos D17 validados: `12.453`
- `ALIAS_AUTO`: `11.996`
- `ALIAS_QA`: `457`
- QA pack humano: `646` linhas
- Runtime: `736s`

## Artefatos

- Full rowset: `C:\winegod-app\reports\tail_d17_alias_candidates_2026-04-16_chunk_000.csv.gz`
- QA CSV: `C:\winegod-app\reports\tail_d17_alias_qa_pack_2026-04-16_chunk_000.csv`

## Contagem por lane

| lane | candidatos | qa_sample |
| --- | --- | --- |
| ALIAS_AUTO | 11.996 | 600 |
| ALIAS_QA | 457 | 46 |

## Contagem por estrato

| estrato | candidatos |
| --- | --- |
| S6_GENERAL_REMAINDER | 10.168 |
| S2_NO_SOURCE | 870 |
| S5_SOURCE_RICH_STRUCTURED | 791 |
| S4_MULTI_CLEAN_OR_AMBIG_LINEAGE | 624 |

## Evidencia principal

| evidencia | candidatos |
| --- | --- |
| strong_name_token_overlap>=2 | 6.386 |
| strong_name_and_producer_overlap | 5.291 |
| stripped_name | 236 |
| name_and_source_to_canonical_producer | 186 |
| y2_plus_text_evidence | 180 |
| exact_name | 94 |
| broad_name_with_strong_producer | 80 |

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
| producer_incompatible | 1.440.463 |
| tipo_mismatch | 288.828 |
| weak_single_token_or_no_text_evidence | 72.991 |
| no_scored_candidate | 20.325 |
| no_candidate_pool | 9.182 |
| score_below_030 | 7.956 |
| s6_medium_excluded_for_d19 | 6.040 |
| score_gap_below_d17 | 861 |
| s6_auto_floor_weak_name_anchor | 701 |
| s6_auto_floor_weak_evidence | 235 |
| s6_auto_floor_no_producer_anchor | 201 |

### Validacao live Render

| motivo | ocorrencias |
| --- | --- |
| source_already_has_approved_alias | 2 |

## Como revisar

Marque `CORRECT` somente se source e canonical forem o mesmo vinho. Na duvida,
marque `ERROR` ou deixe pendente. O limite operacional original de D17 e erro
abaixo de 3% para alias.
