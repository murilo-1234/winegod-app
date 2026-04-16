# Abertura D17 -- Alias dos MATCH_RENDER Fortes

Data: 2026-04-16 00:30:56 Hora oficial do Brasil
Modo: read-only / sem escrita em producao

## Estado atual

- Cauda original auditada: `779.383`
- Cauda ativa pos-NOT_WINE: `675.307`
- Cauda ja suprimida: `104.085`
- Escopo de qualquer D17 agora: somente `vivino_id IS NULL AND suppressed_at IS NULL`

## Escopo D17 original

| lane | estimativa original | entrada | gate |
| --- | --- | --- | --- |
| ALIAS_AUTO | 78.869 | MATCH_RENDER HIGH | QA 5% antes de executar |
| ALIAS_QA | 11.136 | MATCH_RENDER MEDIUM S2-S5 | QA 10% antes de executar |
| fora do D17 | 105.882 | MATCH_RENDER MEDIUM S6 | Vai para D19/ALIAS_REVIEW |

Total planejado D17: `90.005` candidatos a alias. Esse numero continua sendo baseline de planejamento, mas nao deve ser executado diretamente. O lote real precisa ser rematerializado contra a cauda ativa atual, porque 104k+ itens ja foram suprimidos e nao podem virar alias.

## Por que nao executei alias agora

Os scripts antigos encontrados nao sao suficientes para producao:

- `scripts/find_alias_candidates.py` e uma triagem/amostra manual; nao materializa o lote D17 completo.
- `scripts/generate_aliases.py` registra a propria ressalva de que o `source_wine_id` nao esta resolvido corretamente.
- D17 exige uma tabela final `(source_wine_id, canonical_wine_id)` com source ativo, canonico ativo, gap positivo e produtor compativel.

Executar alias sem esse rowset seria trocar uma limpeza segura por risco de deduplicacao errada.

## Travas obrigatorias para o proximo script D17

| trava | regra |
| --- | --- |
| source ativo | source_wine_id precisa ter vivino_id IS NULL e suppressed_at IS NULL |
| canonico ativo | canonical_wine_id precisa ter vivino_id IS NOT NULL e suppressed_at IS NULL |
| sem alias aprovado previo | nao duplicar source_wine_id ja aprovado |
| gap positivo | score do canonico precisa vencer alternativas; empate nao entra em massa |
| produtor compativel | producer/manufacturer nao pode conflitar |
| bloqueio NOT_WINE | source nao pode bater nos termos do catalogo NOT_WINE |
| backup/rollback | D17 so prepara; escrita fica para D18 apos QA |

## Plano executavel imediato

1. Criar materializador D17 que gere `reports/tail_d17_alias_candidates_2026-04-16.csv.gz`.
2. Usar somente source com `vivino_id IS NULL AND suppressed_at IS NULL`.
3. Usar somente canonical com `vivino_id IS NOT NULL AND suppressed_at IS NULL`.
4. Remover tudo que ja tem alias aprovado.
5. Separar `ALIAS_AUTO` e `ALIAS_QA`.
6. Gerar amostras QA antes de qualquer insert.
7. Deixar escrita em producao apenas para D18, com backup e rollback.

## Conclusao

D17 esta aberto, mas ainda nao executavel em producao. O proximo artefato necessario e o rowset de candidatos ativos e validados. Sem isso, o risco principal e gravar alias com `source_wine_id` errado ou ressuscitar item que ja foi suprimido.
