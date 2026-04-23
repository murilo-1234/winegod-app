Voce vai atuar como mantenedor do metodo oficial de rollout i18n do WineGod.

Seu objetivo nesta rodada e unico:

CORRIGIR O PRIMEIRO RASCUNHO DO METODO
sem reabrir o projeto inteiro, sem reinventar a estrutura e sem espalhar mudancas desnecessarias.

Esta e uma rodada V2 curta e cirurgica.
O pacote atual ja existe.
Voce nao deve reconstruir do zero.
Voce deve corrigir apenas os gaps materiais encontrados na auditoria final do metodo.

Trabalhe de ponta a ponta, sem interrupcao, e pare apenas quando a V2 estiver pronta.
Se houver pequena ambiguidade documental, resolva e registre no resultado final.
Nao pare no meio para pedir confirmacao.

IMPORTANTE:
- Nao altere app, env remoto, banco, feature flags ou deploy.
- Nao rode rollout de locale.
- Nao mexa em producao.
- Seu escopo e somente DOCUMENTACAO DO METODO.

==================================================
CONTEXTO
==================================================

Ja existe um pacote inicial do metodo oficial em `reports/`.
Esse pacote foi auditado e a conclusao foi:

- bom primeiro rascunho
- ainda nao pronto para congelar como metodo oficial reutilizavel
- precisa de uma V2 curta corrigindo 4 pontos

Seu trabalho e fazer essa V2.

==================================================
LEITURA OBRIGATORIA
==================================================

Leia estes arquivos antes de editar qualquer coisa:

1. `C:\winegod-app\docs\metodo-linguas\WINEGOD_MULTILINGUE_METODO_BASE_OFICIAL.md`
2. `C:\winegod-app\docs\metodo-linguas\WINEGOD_MULTILINGUE_TEMPLATE_JOB_NOVO_LOCALE.md`
3. `C:\winegod-app\docs\metodo-linguas\WINEGOD_MULTILINGUE_TEMPLATE_DECISIONS_NOVO_LOCALE.md`
4. `C:\winegod-app\docs\metodo-linguas\WINEGOD_MULTILINGUE_TEMPLATE_RESULTADO_NOVO_LOCALE.md`
5. `C:\winegod-app\docs\metodo-linguas\WINEGOD_MULTILINGUE_TEMPLATE_HANDOFF_FINAL_NOVO_LOCALE.md`
6. `C:\winegod-app\docs\metodo-linguas\WINEGOD_MULTILINGUE_METODO_GAPS_E_PENDENCIAS.md`
7. `C:\winegod-app\docs\metodo-linguas\WINEGOD_MULTILINGUE_METODO_RESUMO_EXECUTIVO.md`
8. `C:\winegod-app\reports\WINEGOD_MULTILINGUE_METODO_RESULTADO_DA_CONSTRUCAO.md`
9. `C:\winegod-app\reports\WINEGOD_MULTILINGUE_METODO_LINEAR_LOCALE_NOVO_RUNBOOK.md`
10. `C:\winegod-app\reports\WINEGOD_MULTILINGUE_H4_METODO_REPLICAVEL_OUTRAS_LINGUAS_HANDOFF.md`
11. `C:\winegod-app\reports\i18n_execution_log.md`

Leitura de referencia historica, se realmente precisar:

12. `C:\winegod-app-h4-closeout\reports\WINEGOD_MULTILINGUE_FECHAMENTO_TOTAL_RESULTADO.md`
13. `C:\winegod-app-h4-closeout\reports\WINEGOD_MULTILINGUE_FECHAMENTO_TOTAL_HANDOFF.md`
14. `C:\winegod-app-h4-closeout\reports\WINEGOD_MULTILINGUE_DECISIONS.md`

ATENCAO:
- O metodo V2 deve ficar AUTOCONTIDO no repo principal `C:\winegod-app`.
- Os docs de `C:\winegod-app-h4-closeout\...` podem existir como referencia historica opcional.
- Eles NAO podem continuar como dependencia obrigatoria do metodo oficial.

==================================================
OS 4 PROBLEMAS QUE VOCE DEVE RESOLVER
==================================================

Voce deve corrigir exatamente estes 4 pontos:

1. F0 INCOMPLETA

Hoje o metodo promete branch dedicada, worktree limpa e ambiente controlado,
mas o preflight real nao garante isso.

Voce deve corrigir a F0 para:
- exigir branch dedicada ou worktree dedicada
- registrar claramente qual das duas abordagens e a oficial
- bloquear nao so `untracked`, mas tambem `modified tracked files` no write-set de producao
- deixar explicito o que fazer se o repo estiver sujo
- usar comandos reais de Windows/PowerShell

Nao basta dizer “trabalhar limpo”.
Tem que existir gate operacional real.

2. METODO NAO AUTOCONTIDO

Hoje o metodo oficial ainda depende de caminhos obrigatorios em:
- `C:\winegod-app-h4-closeout\...`

Isso e fragil.

Voce deve:
- remover essa dependencia como fonte obrigatoria
- trazer para o metodo apenas o que precisa ser permanente
- reclassificar `winegod-app-h4-closeout` como referencia historica opcional, se necessario
- garantir que um operador com clone limpo de `C:\winegod-app` consiga usar o metodo sem depender daquele sibling worktree

3. GATE FINAL DE ATIVACAO FRACO

Hoje o metodo pode aprovar um locale usando override local de env,
sem provar que o frontend publicado recebeu o novo `NEXT_PUBLIC_ENABLED_LOCALES`.

Voce deve endurecer o gate final para exigir:
- prova de consistencia static x dynamic
- prova de frontend publicado
- prova por smoke em rota prefixada real de share:
  - `/<LOCALE_SHORT>/c/...`
- texto claro explicando por que esse gate existe

Nao aceite gate final que so prove backend dinamico ou override local.

4. APPEND-ONLY LOG NAO OBRIGATORIO

Hoje o metodo nao torna `reports/i18n_execution_log.md` obrigatorio em todo novo job.

Voce deve corrigir isso para:
- exigir append-only no log como artefato obrigatorio
- explicitar em quais momentos minimos o append deve acontecer
- alinhar isso no template de job, no template de resultado e no handoff final

==================================================
ESCOPO DE EDICAO
==================================================

Voce deve editar somente o que for necessario, preferindo mudanca pequena e precisa.

Arquivos provaveis de edicao:

- `C:\winegod-app\docs\metodo-linguas\WINEGOD_MULTILINGUE_METODO_BASE_OFICIAL.md`
- `C:\winegod-app\docs\metodo-linguas\WINEGOD_MULTILINGUE_TEMPLATE_JOB_NOVO_LOCALE.md`
- `C:\winegod-app\docs\metodo-linguas\WINEGOD_MULTILINGUE_TEMPLATE_RESULTADO_NOVO_LOCALE.md`
- `C:\winegod-app\docs\metodo-linguas\WINEGOD_MULTILINGUE_TEMPLATE_HANDOFF_FINAL_NOVO_LOCALE.md`
- `C:\winegod-app\docs\metodo-linguas\WINEGOD_MULTILINGUE_METODO_GAPS_E_PENDENCIAS.md`
- `C:\winegod-app\docs\metodo-linguas\WINEGOD_MULTILINGUE_METODO_RESUMO_EXECUTIVO.md`
- `C:\winegod-app\reports\WINEGOD_MULTILINGUE_METODO_RESULTADO_DA_CONSTRUCAO.md`

Voce pode editar outros arquivos do pacote se for realmente necessario,
mas nao abra uma refatoracao ampla.

==================================================
O QUE A V2 PRECISA ENTREGAR
==================================================

Ao final, o pacote precisa ficar com estas caracteristicas:

1. F0 realmente executavel
- com branch/worktree definida
- com gate para tracked modified e untracked
- com abort claro

2. Metodo autocontido
- utilizavel a partir de `C:\winegod-app`
- sem dependencia obrigatoria de `winegod-app-h4-closeout`

3. Gate final confiavel
- prova build-time + dynamic runtime
- inclui rota share prefixada publicada

4. Trilha append-only obrigatoria
- `reports/i18n_execution_log.md` incorporado como parte do metodo

==================================================
NOVO ARQUIVO OBRIGATORIO DE RESULTADO
==================================================

Ao terminar, escreva:

`C:\winegod-app\reports\WINEGOD_MULTILINGUE_METODO_V2_RESULTADO_CORRETIVO.md`

Esse arquivo deve conter:

1. resumo do que foi corrigido
2. lista de arquivos editados
3. como a F0 mudou
4. como a dependencia de `winegod-app-h4-closeout` foi resolvida
5. como o gate final de ativacao foi endurecido
6. como o append-only log passou a ser obrigatorio
7. gaps que ainda sobraram, se houver
8. veredito final:
   - `METODO V2 PRONTO PARA CONGELAR`
   - ou `AINDA NAO PRONTO`

==================================================
CRITERIO DE PRONTO
==================================================

So considere a tarefa pronta quando:

- os 4 pontos estiverem corrigidos de forma explicita
- o pacote continuar coerente como um sistema unico
- o metodo estiver mais forte sem virar um documento inflado
- existir o arquivo `WINEGOD_MULTILINGUE_METODO_V2_RESULTADO_CORRETIVO.md`

Se precisar escolher entre “mais elegante” e “mais seguro operacionalmente”, escolha “mais seguro operacionalmente”.

Comece agora.
