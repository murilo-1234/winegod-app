# Resumo — Fase 0 Dedup/Matching

Data: 2026-04-09
Status: CONCLUIDA, APROVADA E DEPLOYADA

## Em uma frase

A Fase 0 nao fez a deduplicacao estrutural completa do banco. Ela resolveu o sintoma mais visivel na busca, conteve nova contaminacao do pipeline e deixou a base pronta para as fases de correcao reversivel e rebuild.

## Problema original

O banco em producao ficou com duas camadas misturadas:
- registros canonicos vindos do snapshot Vivino, com `vivino_id`, `vivino_rating`, `nota_wcf` e `winegod_score`;
- registros de lojas para o mesmo vinho, mas sem nota.

Na pratica, isso fazia a busca devolver a versao de loja sem nota em vez do vinho canonico com rating. Casos como `Chaski Petit Verdot` e `Finca Las Moras Cabernet Sauvignon` mostravam esse problema com clareza.

Havia tambem um problema operacional no pipeline local/manual:
- `scripts/import_render_z.py` aceitava `match_score >= 0.0` na fase de import de `matched`, permitindo nova contaminacao com links fracos.

## O que a Fase 0 resolveu

### 1. Busca em producao voltou a encontrar o canonico util

Arquivos de runtime deployados:
- `backend/tools/search.py`
- `backend/tools/normalize.py`
- `backend/services/display.py`

O que mudou:
- a busca passou a usar `_CANONICAL_RANK` para favorecer registros com sinais canonicos;
- a busca em camadas ganhou um complemento por tokens quando exact/prefix/producer retornam apenas registros sem sinal canonico;
- isso permitiu recuperar canonicos com nome em ordem diferente, sem depender so do `pg_trgm`.

Efeito pratico validado em producao:
- `Chaski Petit Verdot`: voltou a retornar `Petit Verdot Chaski` como `#1`, com rating `4.1`;
- `Finca Las Moras Cabernet Sauvignon`: passou a retornar `Las Moras Cabernet Sauvignon` como `#1`, com rating `3.4`;
- `Dom Perignon` e `Luigi Bosca De Sangre`: nao pioraram; continuaram sem nota por lacuna de dados, nao por erro de busca;
- `Perez Cruz Piedra Seca`: confirmado como lacuna de dados no banco, nao regressao da busca.

### 2. Cache antigo deixou de mascarar a nova busca

Arquivo deployado:
- `backend/services/cache.py`

O que mudou:
- `CACHE_VERSION=2`, forçando novas chaves de cache para busca/detalhes.

Efeito pratico:
- os resultados da busca nova nao ficam escondidos atras do cache antigo.

### 3. Baco passou a responder corretamente quando o vinho existe, mas nao tem nota

Arquivo deployado:
- `backend/prompts/baco_system.py`

O que mudou:
- instrucoes explicitas para nao inventar nota quando `vivino_rating` e `nota_wcf` estao nulos;
- fallback de UX para explicar que o vinho foi encontrado, mas sem nota verificada.

Efeito pratico:
- melhora a resposta ao usuario em casos de lacuna de dados.

### 4. Nova sujeira deixou de entrar pelo import local/manual

Arquivo corrigido localmente:
- `scripts/import_render_z.py`

O que mudou:
- `match_score >= 0.0` foi endurecido para `match_score >= 0.5`.

Importante:
- isso nao foi parte do deploy do backend no Render;
- continua sendo uma correcao do script operacional local/manual, usada para evitar nova contaminacao futura.

## O que a Fase 0 NAO resolveu

### 1. Nao houve deduplicacao historica completa do banco

O banco ainda contem:
- vinhos de loja duplicando vinhos canonicos;
- owners historicos errados ou duvidosos;
- registros que precisam de mapeamento reversivel, nao de merge destrutivo.

Em outras palavras:
- a Fase 0 melhorou a busca sobre a base atual;
- ela nao limpou toda a base.

### 2. Lacunas reais de catalogo continuam existindo

Casos confirmados:
- `Dom Perignon`: sem canonicos com rating no banco atual;
- `Luigi Bosca De Sangre Malbec`: sem canonico correspondente no banco atual;
- `Perez Cruz Piedra Seca`: zero canonicos corretos no banco atual.

Esses casos precisam de cobertura de catalogo, nao apenas de busca.

### 3. `wine_aliases` ainda nao foi aplicado no banco

Ja existe migration em:
- `C:\winegod\migrations\003_wine_aliases.sql`

Mas ainda falta:
- aplicar no banco;
- preencher aliases aprovados;
- usar aliases como mecanismo reversivel de resolucao loja -> canonico.

### 4. Guardrails e filtro de nao-vinho ainda nao estao integrados no fluxo

Scripts preparados:
- `scripts/guardrails_owner.py`
- `scripts/wine_filter.py`

Ainda falta:
- integrar isso ao fluxo de import/classificacao;
- bloquear producer generico, conflito de tipo, nao-vinhos e outras entradas ruins antes de materializar.

### 5. Rebuild historico em sombra ainda nao foi executado

O runbook existe em:
- `reports/RUNBOOK_FASE2_REBUILD.md`

Mas ainda falta:
- reconciliar `vivino_db` com o snapshot efetivo do produto;
- rebuild local em sombra;
- validar;
- fazer cutover controlado.

## Evidencia que aprovou a Fase 0

Arquivos principais:
- `reports/baseline_fase0.txt`
- `reports/pos_hotfix_fase0.txt`
- `reports/pos_hotfix_fase0_v2.txt`
- `reports/RELATORIO_SESSAO_DEDUP_2026-04-08.md`

Conclusao operacional:
- busca corrigida e validada em producao;
- cache validado;
- UX validada;
- import endurecido localmente para evitar nova contaminacao.

## O que ainda falta para considerar o problema de dedup "resolvido"

Para considerar P5 estruturalmente resolvido, ainda faltam 3 etapas:

### Etapa 1 — Correcao reversivel na base atual

Objetivo:
- reduzir sombra de versoes de loja sobre canonicos sem fazer merge destrutivo.

Fazer:
- aplicar `wine_aliases`;
- gerar/aprovar aliases de alta confianca;
- integrar guardrails de owner;
- integrar filtro de nao-vinho;
- endurecer criterios do fluxo novo.

### Etapa 2 — Fechar lacunas de catalogo

Objetivo:
- garantir que casos famosos ou recorrentes tenham canonicos reais no banco.

Fazer:
- reconciliar `vivino_db` com o snapshot atual em producao;
- identificar vinhos faltantes com alta prioridade;
- importar canonicos faltantes quando existirem fora do snapshot atual.

### Etapa 3 — Rebuild historico em sombra local

Objetivo:
- reconstruir a base limpa sem misturar correcao com o banco live.

Fazer:
- montar banco sombra local;
- carregar camada canonica reconciliada;
- reimportar lojas com regras novas;
- aplicar aliases;
- recalcular scores/precos;
- validar e so depois considerar cutover.

## Leitura recomendada para a proxima sessao

1. Este resumo: `reports/RESUMO_FASE0_DEDUP_2026-04-09.md`
2. Relatorio detalhado: `reports/RELATORIO_SESSAO_DEDUP_2026-04-08.md`
3. Runbook do rebuild: `reports/RUNBOOK_FASE2_REBUILD.md`

## Resumo executivo final

O que foi resolvido:
- a busca voltou a expor o canonico com nota nos casos em que ele ja existia no banco;
- o cache foi invalidado corretamente;
- o Baco passou a tratar vinhos sem nota de forma honesta;
- o import local/manual deixou de aceitar match muito fraco.

O que ainda falta:
- deduplicacao historica reversivel;
- aliases aplicados;
- guardrails integrados;
- lacunas de catalogo fechadas;
- rebuild em sombra local com validacao e possivel cutover.
