Voce vai atuar como mantenedor do metodo oficial de rollout i18n do WineGod.

Objetivo desta rodada:

AJUSTAR A V2 PARA FECHAR DE VEZ O SUPORTE A BRANCH OU WORKTREE
sem reabrir o metodo inteiro.

Esta e uma rodada V2.1 pequena, cirurgica e documental.
Nao reconstrua o pacote.
Nao mude escopo.
Corrija apenas a ambiguidade restante encontrada na auditoria.

==================================================
CONTEXTO
==================================================

A V2 melhorou o metodo e resolveu quase tudo.
Mas ainda sobrou um problema:

- o metodo diz que aceita branch dedicada OU worktree dedicada
- porem varios comandos ainda estao hardcoded para `C:\winegod-app` e `C:\winegod-app\frontend`
- isso enfraquece a opcao de worktree e pode fazer operador rodar no root errado

Sua missao e corrigir isso de ponta a ponta.

==================================================
LEITURA OBRIGATORIA
==================================================

Leia antes de editar:

1. `C:\winegod-app\reports\WINEGOD_MULTILINGUE_METODO_V2_RESULTADO_CORRETIVO.md`
2. `C:\winegod-app\docs\metodo-linguas\WINEGOD_MULTILINGUE_METODO_BASE_OFICIAL.md`
3. `C:\winegod-app\docs\metodo-linguas\WINEGOD_MULTILINGUE_TEMPLATE_JOB_NOVO_LOCALE.md`
4. `C:\winegod-app\docs\metodo-linguas\WINEGOD_MULTILINGUE_TEMPLATE_RESULTADO_NOVO_LOCALE.md`
5. `C:\winegod-app\docs\metodo-linguas\WINEGOD_MULTILINGUE_TEMPLATE_HANDOFF_FINAL_NOVO_LOCALE.md`
6. `C:\winegod-app\docs\metodo-linguas\WINEGOD_MULTILINGUE_METODO_RESUMO_EXECUTIVO.md`
7. `C:\winegod-app\reports\WINEGOD_MULTILINGUE_METODO_RESULTADO_DA_CONSTRUCAO.md`
8. `C:\winegod-app\reports\i18n_execution_log.md`

==================================================
PROBLEMA A CORRIGIR
==================================================

Corrigir apenas isto:

1. A opcao de worktree precisa funcionar de verdade, nao so no texto.

Hoje ainda existem comandos e evidencias com:
- `Set-Location C:\winegod-app`
- `Set-Location C:\winegod-app\frontend`
- referencias textuais fixas ao clone principal

Voce deve tornar o metodo consistente com uma unica regra:

- sempre usar um root parametrico, como `$repoRoot`
- quando precisar entrar no frontend, usar caminho derivado do root, nao caminho fixo
- logs, evidencias, templates e sanity checks devem refletir branch OU worktree corretamente

==================================================
O QUE AJUSTAR
==================================================

Voce deve revisar e corrigir, no minimo:

- `C:\winegod-app\docs\metodo-linguas\WINEGOD_MULTILINGUE_METODO_BASE_OFICIAL.md`
- `C:\winegod-app\docs\metodo-linguas\WINEGOD_MULTILINGUE_TEMPLATE_JOB_NOVO_LOCALE.md`
- `C:\winegod-app\docs\metodo-linguas\WINEGOD_MULTILINGUE_TEMPLATE_RESULTADO_NOVO_LOCALE.md`
- `C:\winegod-app\docs\metodo-linguas\WINEGOD_MULTILINGUE_TEMPLATE_HANDOFF_FINAL_NOVO_LOCALE.md`
- `C:\winegod-app\reports\WINEGOD_MULTILINGUE_METODO_RESUMO_EXECUTIVO.md`
- `C:\winegod-app\reports\WINEGOD_MULTILINGUE_METODO_RESULTADO_DA_CONSTRUCAO.md`

Se precisar tocar mais algum arquivo do pacote para manter coerencia, pode.
Mas nao abra uma refatoracao ampla.

==================================================
CRITERIOS DA V2.1
==================================================

Ao final:

1. branch dedicada e worktree dedicada devem estar descritas como caminhos oficiais validos
2. os comandos nao podem depender implicitamente do clone principal
3. os exemplos de build, Playwright, sanity e baseline devem usar root parametrico
4. logs e evidencias devem registrar corretamente o local de execucao
5. o metodo deve continuar Windows-first
6. o pacote deve ficar menor ou igual em complexidade operacional, nao mais confuso

==================================================
ARQUIVO OBRIGATORIO DE RESULTADO
==================================================

Ao terminar, escreva:

`C:\winegod-app\reports\WINEGOD_MULTILINGUE_METODO_V2_1_RESULTADO_CORRETIVO.md`

Esse arquivo deve conter:

1. resumo do ajuste
2. arquivos editados
3. como o root parametrico foi aplicado
4. como branch e worktree ficaram equivalentes operacionalmente
5. trechos que foram des-hardcoded
6. gaps que ainda sobraram, se houver
7. veredito final:
   - `METODO V2.1 PRONTO PARA CONGELAR`
   - ou `AINDA NAO PRONTO`

==================================================
REGRAS
==================================================

- Nao mexer em app
- Nao mexer em producao
- Nao mexer em env remota
- Nao mexer em deploy
- Nao reabrir os outros temas ja fechados
- Corrigir somente o suporte real a worktree/root parametrico

Se precisar escolher entre texto bonito e operacao correta, escolha operacao correta.

Comece agora.
