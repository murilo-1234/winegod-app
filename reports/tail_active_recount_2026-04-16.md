# Recontagem da Cauda Ativa Pos-Suppress

Data: 2026-04-16 00:30:56 Hora oficial do Brasil
Banco: Render PostgreSQL
Modo: read-only

## Resultado curto

- Frame original da cauda em 2026-04-10: `779.383`
- Cauda ativa agora: `675.307`
- Cauda ja suprimida: `104.085`
- Reducao visivel vs frame original: `104.076` (`13,35%`)
- Canonicos Vivino oficiais preservados: `1.727.058`

## Contagens principais

| metrica | valor | leitura |
| --- | --- | --- |
| wines total derivado | 2.506.450 | canonicos oficiais + cauda live |
| canonicos Vivino oficiais | 1.727.058 | Snapshot aprovado de 2026-04-10 |
| cauda total sem vivino_id | 779.392 | Ativos + suprimidos |
| cauda ativa | 675.307 | Escopo real que ainda aparece no produto |
| cauda suprimida | 104.085 | NOT_WINE removido logicamente |
| wine_aliases total | 43 | Estado atual da tabela |
| wine_aliases approved | 43 | Aliases aprovados existentes |

## Suppress da cauda por motivo

| suppress_reason | wines | % da cauda suprimida |
| --- | --- | --- |
| d16_strong_patterns_2026-04-15 | 59.902 | 57,55% |
| d16_wine_filter_expansion_2026-04-15 | 13.320 | 12,80% |
| d16_wine_filter_round3_2026-04-15 | 11.726 | 11,27% |
| d16_wine_filter_round4_2026-04-15 | 19.137 | 18,39% |

Os motivos acima vieram dos CSVs de backup das quatro rodadas D16 e reconciliam exatamente com a contagem live da cauda suprimida.

## Leitura operacional

A limpeza NOT_WINE ja tirou `104.085` itens da cauda visivel. O proximo trabalho nao deve olhar mais para a cauda historica inteira; deve operar somente sobre `vivino_id IS NULL AND suppressed_at IS NULL`, hoje com `675.307` wines.
