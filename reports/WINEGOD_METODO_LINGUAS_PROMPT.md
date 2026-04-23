Voce vai atuar como arquiteto de metodo operacional do rollout i18n do WineGod.

Seu objetivo e unico e fechado:

CRIAR O PRIMEIRO METODO OFICIAL, REPLICAVEL E OPERACIONAL
para abrir novos locales no WineGod do zero ate producao,
sem improviso, com minimo de intervencao humana, usando como base o que ja foi aprendido no H4 e no fechamento total do rollout atual.

Voce deve trabalhar de ponta a ponta, sem parar no meio para pedir confirmacoes.
Assuma decisoes razoaveis quando houver ambiguidade pequena.
Se existir alguma intervencao humana realmente inevitavel, NAO pare no meio:
- siga todo o trabalho que puder
- registre a intervencao humana pendente apenas no bloco final
- deixe isso consolidado no fim como “pendencias humanas residuais”
A meta e terminar tudo de uma vez.

IMPORTANTE:
- Nao execute rollout de produto
- Nao mexa em env remoto
- Nao altere producao
- Nao faca deploy
- Nao mude feature_flags reais
- Nao trabalhe no app em si
- Seu trabalho e DOCUMENTAR, ESTRUTURAR, PADRONIZAR e TRANSFORMAR o aprendizado em METODO

Voce deve produzir o metodo completo no repositorio, em arquivos finais, prontos para uso futuro.
Depois disso, eu vou pedir para outro Codex auditar o que voce fez.

==================================================
CONTEXTO
==================================================

O WineGod acabou de fechar o rollout multilingue atual com 4 locales ativos:
- pt-BR
- en-US
- es-419
- fr-FR

O projeto acumulou aprendizado real de:
- parity estrutural
- routing e middleware
- age gate por locale
- legal docs por locale
- QA visual e determinista
- cross-review multi-IA
- decisions O1/O2/O3
- canary / ativacao gradual
- pitfalls de git, untracked, build incremental e smoke em producao

Agora queremos transformar isso em UM METODO REPLICAVEL
para novos idiomas e variantes futuras, como por exemplo:
- de-DE
- it-IT
- ja-JP
- zh-CN
- en-GB
- es-ES
- fr-CA
- pt-PT

==================================================
DOCUMENTOS FONTE - LEITURA OBRIGATORIA
==================================================

LEIA ESTES DOCUMENTOS ANTES DE QUALQUER COISA:

1. C:\winegod-app\reports\WINEGOD_MULTILINGUE_METODO_LINEAR_LOCALE_NOVO_RUNBOOK.md
2. C:\winegod-app\reports\WINEGOD_MULTILINGUE_H4_METODO_REPLICAVEL_OUTRAS_LINGUAS_HANDOFF.md
3. C:\winegod-app-h4-closeout\reports\WINEGOD_MULTILINGUE_FECHAMENTO_TOTAL_RESULTADO.md
4. C:\winegod-app-h4-closeout\reports\WINEGOD_MULTILINGUE_FECHAMENTO_TOTAL_HANDOFF.md
5. C:\winegod-app-h4-closeout\reports\WINEGOD_MULTILINGUE_DECISIONS.md
6. C:\winegod-app-h4-closeout\reports\i18n_execution_log.md

Leitura complementar recomendada, se precisar:
7. C:\winegod-app\reports\WINEGOD_MULTILINGUE_PLANO_EXECUCAO_FECHAMENTO_TOTAL.md
8. C:\winegod-app\reports\WINEGOD_MULTILINGUE_PLANO_EXECUCAO_V2.5.md
9. C:\winegod-app\reports\WINEGOD_MULTILINGUE_HANDOFF_OFICIAL.md
10. C:\winegod-app\DEPLOY.md

==================================================
MISSAO
==================================================

Voce deve transformar esse material em um METODO OFICIAL reutilizavel.

Nao basta “melhorar a documentacao”.
Voce deve:

1. separar o que e licao do H4
2. separar o que e regra universal
3. separar o que e excecao
4. separar o que e decisao operacional
5. separar o que e script padrao
6. separar o que e ponto humano inevitavel
7. produzir uma estrutura que permita a qualquer futuro locale novo ser aberto sem depender da memoria do H4

Em uma frase:
o metodo final deve permitir que um futuro operador abra um locale novo do zero ate producao com minimo atrito, maxima auditabilidade e sem improviso.

==================================================
O QUE VOCE DEVE ENTREGAR
==================================================

Voce deve criar, no minimo, ESTES ARQUIVOS FINAIS:

1. C:\winegod-app\docs\metodo-linguas\WINEGOD_MULTILINGUE_METODO_BASE_OFICIAL.md
   - documento mestre
   - regras universais do metodo
   - o que sempre vale para qualquer locale novo

2. C:\winegod-app\docs\metodo-linguas\WINEGOD_MULTILINGUE_TEMPLATE_JOB_NOVO_LOCALE.md
   - template operacional para abrir um locale novo
   - com placeholders tipo:
     - <LOCALE>
     - <LOCALE_SHORT>
     - <SOURCE_LOCALE>
     - <COUNTRY_ISO>
     - <JOB_NAME>

3. C:\winegod-app\docs\metodo-linguas\WINEGOD_MULTILINGUE_TEMPLATE_DECISIONS_NOVO_LOCALE.md
   - template das decisoes do locale novo
   - com O1/O2/O3 e outras decisoes que sejam realmente gerais
   - separar claramente:
     - decisao tecnica
     - decisao operacional
     - residual aceito

4. C:\winegod-app\docs\metodo-linguas\WINEGOD_MULTILINGUE_TEMPLATE_RESULTADO_NOVO_LOCALE.md
   - template de resultado final
   - evidencias obrigatorias
   - validacoes obrigatorias
   - output esperado

5. C:\winegod-app\docs\metodo-linguas\WINEGOD_MULTILINGUE_TEMPLATE_HANDOFF_FINAL_NOVO_LOCALE.md
   - template de handoff final
   - pronto para ser preenchido ao final de um novo rollout de locale

6. C:\winegod-app\docs\metodo-linguas\WINEGOD_MULTILINGUE_METODO_GAPS_E_PENDENCIAS.md
   - o que ainda NAO virou metodo
   - o que ainda depende de julgamento humano
   - o que e excecao por classe de locale
   - o que ainda pode melhorar no futuro

7. C:\winegod-app\docs\metodo-linguas\WINEGOD_MULTILINGUE_METODO_RESUMO_EXECUTIVO.md
   - versao curta, para founder/admin
   - o metodo em visao de 1 pagina
   - sequencia de alto nivel
   - gates
   - custo humano esperado
   - risco residual padrao

8. C:\winegod-app\reports\WINEGOD_MULTILINGUE_METODO_RESULTADO_DA_CONSTRUCAO.md
   - relatorio do que voce fez nesta rodada
   - quais docs analisou
   - quais decisoes metodologicas tomou
   - quais conflitos encontrou
   - o que consolidou
   - o que ficou como gap

Se durante o trabalho voce concluir que faz sentido criar mais 1 ou 2 arquivos alem desses, pode criar.
Mas esses 8 acima sao obrigatorios.

==================================================
PADRAO DE QUALIDADE
==================================================

O metodo final precisa ter estas propriedades:

1. REPLICAVEL
- deve funcionar para qualquer locale novo com adaptacoes pequenas

2. OPERACIONAL
- nao pode ser so conceitual
- precisa dizer exatamente como executar

3. AUDITAVEL
- deve deixar claro o que gera evidencia
- o que salva log
- o que salva handoff
- o que salva resultado

4. LINEAR
- deve existir uma ordem clara
- sem dependencias confusas
- sem vai-e-volta desnecessario

5. MINIMO DE PONTOS HUMANOS
- so deixar humano onde for realmente inevitavel
- todo o resto deve ser agente-executavel

6. SEPARACAO CORRETA
- codigo
- QA
- editorial
- legal
- release
- canary
- docs
- tudo precisa ficar em trilhas compreensiveis

7. WINDOWS-FIRST
- ambiente real e Windows/PowerShell
- se houver comandos, eles devem ser oficiais para esse ambiente
- nao deixe o metodo dependente de bash como padrao

8. REALISTA
- o metodo nao pode prometer automacao que nao existe
- se algo depende de Vercel dashboard, diga isso
- se algo depende de founder, diga isso
- se algo pode ser automatizado localmente, automatize no metodo

==================================================
O QUE ANALISAR E EXTRAIR
==================================================

Voce deve olhar os documentos-fonte e responder implicitamente, no metodo, estas perguntas:

1. O que no H4 foi especifico daquele caso e nao universal?
2. O que e universal para qualquer locale novo?
3. Quais fases atuais ja sao reutilizaveis sem mudanca?
4. Quais fases precisam ser reescritas para ficarem genericas?
5. Quais gates sao realmente obrigatorios?
6. Quais artefatos precisam existir sempre?
7. O que deve ser template?
8. O que deve ser checklist?
9. O que deve ser script?
10. O que deve ser decisao do founder?
11. O que pode ser default aceito?
12. Como separar locale novo grande vs variante pequena?
13. Como separar problema estrutural vs problema editorial vs problema juridico?
14. Como registrar residuais aceitos?
15. Como garantir que a proxima execucao nao dependa da memoria do H4?

==================================================
DECISOES METODOLOGICAS QUE VOCE DEVE TOMAR
==================================================

Voce deve decidir e explicitar no metodo:

1. qual e a fase zero oficial
2. qual e o checklist minimo de entrada
3. qual e o gate estrutural universal
4. qual e o gate editorial universal
5. qual e o gate de QA universal
6. qual e o gate de release universal
7. qual e o gate de canary universal
8. quais tipos de locale exigem cautela extra
9. quando IA basta e quando humano e recomendado
10. qual e o bloco de evidencias obrigatorias
11. qual e o bloco de residuais aceitos
12. qual e o bloco de pendencias humanas finais

==================================================
REGRAS DE EXECUCAO
==================================================

1. Trabalhe sem interrupcao ate entregar tudo.
2. Nao fique parando para pedir confirmacao se puder inferir razoavelmente.
3. Se houver conflito entre documentos:
   - resolva
   - escolha uma linha
   - registre a decisao no relatorio final
4. Se houver duplicacao:
   - consolide
   - nao replique bagunca
5. Se houver material demais:
   - abstraia
   - preserve o que e regra
   - descarte o que e so ruido historico
6. Se houver algum ponto que realmente dependa de founder:
   - nao pare
   - coloque no documento de gaps/pendencias
   - deixe isso no final como pendencia residual
7. Nao execute deploy, nao mude env remota, nao altere banco remoto.
8. Pode editar somente documentacao e artefatos do metodo.
9. Se criar scripts ou comandos dentro do metodo, eles devem ser realistas para Windows/PowerShell.
10. Nao deixe o resultado “meio template, meio brainstorm”.
    O resultado tem que parecer um metodo oficial.

==================================================
FORMATO DO RESULTADO DESTA RODADA
==================================================

Ao terminar, escreva no arquivo:

C:\winegod-app\reports\WINEGOD_MULTILINGUE_METODO_RESULTADO_DA_CONSTRUCAO.md

Esse arquivo deve conter:

1. documentos lidos
2. resumo do que foi consolidado
3. lista de arquivos gerados
4. principais decisoes metodologicas tomadas
5. conflitos resolvidos
6. gaps remanescentes
7. veredito:
   - se ja existe um primeiro metodo oficial utilizavel
   - ou se ainda ficou so como rascunho melhorado

==================================================
CRITERIO DE PRONTO
==================================================

Considere a tarefa pronta somente quando:

- todos os arquivos obrigatorios existirem
- o metodo-base estiver claro
- os templates estiverem claros
- os gaps estiverem isolados
- o resumo executivo existir
- o relatorio final existir
- e o conjunto estiver coerente como um sistema, nao como arquivos soltos

Se precisar escolher entre “mais bonito” e “mais operacional”, escolha “mais operacional”.

Comece agora.
