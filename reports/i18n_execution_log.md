# WineGod.ai - I18N Execution Log (append-only)

Proposito: registro cronologico de cada fase concluida das 4 trilhas (T1 INFRA / T2 FRONTEND / T3 LEGAL / T4 QA).

Formato: append-only. Nunca editar entradas ja gravadas. Novas entradas ao final.

Plano mestre: `C:\winegod-app\reports\WINEGOD_MULTILINGUE_PLANO_EXECUCAO.md` V2.1
Decisoes travadas: `C:\winegod-app\reports\WINEGOD_MULTILINGUE_DECISIONS.md`
Handoff arquitetural: `C:\winegod-app\reports\WINEGOD_MULTILINGUE_HANDOFF_OFICIAL.md`

---

## 2026-04-19 - T4 Preflight concluido

- Trilha: T4 (QA + Release + Observabilidade + Docs)
- Acao: Preflight rigoroso conforme brief do Codex.
- Resultado:
  - `.sync/t1_onda0_complete` confirmado (pre-requisito base OK).
  - `.sync/t1_f6_4b_done` nao existe - F6.6 bloqueada ate T1 entregar contrato Baco multi-eixo.
  - `.sync/t2_onda4_complete`, `.sync/t1_onda6_complete`, `.sync/t3_onda7_complete`, `.sync/t3_onda8_complete` nao existem - Onda 9 bloqueada ate convergencia.
  - Artefatos da matriz T4 ainda nao existem (scripts/i18n validadores, test_baco_regression, runbooks, playwright, qa-tests.yml, admin_i18n.py).
  - Conflitos brief vs DECISIONS resolvidos: F12.5 juridico deferido (P3/P4/P5); F9.9 usa 301 permanente (P19).
- Aprovado por: Codex (administrador)
- Aprovado em: 2026-04-19

## 2026-04-19 - T4 Direcao operacional: antecipacao de fases docs/scripts

- Trilha: T4
- Decisao do Codex:
  - Antecipar F12.1, F12.2, F12.3 (runbooks e limitations) fora da ordem original, uma fase por vez.
  - Apos runbooks, antecipar F9.1, F9.5, F9.6 (validadores e checklist), tambem uma fase por vez.
  - Baseline de conversao pt-BR (DECISIONS P9 TBD) NAO bloqueia Onda 9. Fica registrado como risco/pendencia de observabilidade a ser tratada na Onda 11 (PostHog instrumentado).
  - F6.6: as 10 perguntas curadas passam por aprovacao do Codex antes de gerar snapshots.
- Aprovado por: Codex
- Aprovado em: 2026-04-19

## 2026-04-19 - T4 F12.1 - Runbook de kill switch / rollback i18n (v1 REPROVADA)

- Fase: F12.1 (antecipada; Onda 12 original).
- Resultado: REPROVADA pelo Codex.
- Motivos:
  - Runbook cravou `C:\winegod-app\.env` como fonte da credencial de producao - artefatos do repo divergem sobre o local do `.env`.
  - Plano B frontend cravou `ENABLED_LOCALES` em Vercel sem tratar o conflito entre `NEXT_PUBLIC_ENABLED_LOCALES` (handoff oficial linhas 1068-1077) e `ENABLED_LOCALES` (plano macro linhas 284/374/406/1363). Operador poderia editar a variavel errada.
  - Arquivos com mojibake em PowerShell (pontuacao Unicode tipo em-dash). Precisam ser ASCII simples.
- Acao: regravar arquivos com correcoes na v2.

## 2026-04-19 - T4 F12.1 v2 - Runbook de kill switch / rollback i18n

- Fase: F12.1 (revisao apos reprovacao).
- Entrada: direcao operacional + feedback do Codex.
- Arquivos regravados:
  - `C:\winegod-app\docs\RUNBOOK_I18N_ROLLBACK.md` (ASCII puro, sem afirmacao rigida de path do .env, secao de env var frontend com aviso explicito de divergencia)
  - `C:\winegod-app\reports\i18n_execution_log.md` (este log; entrada v1 REPROVADA preservada, entrada v2 adicionada; ASCII puro)
- Correcoes v1 -> v2:
  - Credencial producao: operador precisa ter acesso aprovado de escrita ao Postgres de producao (DATABASE_URL), sem fixar path local. Referencia generica a "ambiente local seguro do operador, conforme convencao do repo".
  - Env var frontend: runbook instrui operador a confirmar no dashboard Vercel qual variavel esta efetivamente em uso (`NEXT_PUBLIC_ENABLED_LOCALES` OU `ENABLED_LOCALES`) antes de editar, citando explicitamente a divergencia documental entre handoff oficial e plano macro.
  - Env var backend: mantido `ENABLED_LOCALES` (consistente em todos os docs).
  - Encoding: ASCII puro, hifen comum no lugar de em-dash, aspas retas no lugar de tipograficas.
- Trechos deliberadamente condicionais (documentados no runbook):
  - Nome da env var em Vercel (confirmar antes de editar).
  - Existencia de feature_flags / endpoint `/api/config/enabled-locales` em producao (entregas F1.6/F1.8 de T1 - runbook ja serve como doc pronta).
- Escopo respeitado: Tolgee disaster NAO incluido (F12.2). Sem instrucoes destrutivas. Credenciais humanas marcadas como passo do operador.
- Regras refletidas: Render deploy manual (R7), Onda 10 single-threaded, sem acesso automatizado a producao.
- Risco documentado (observabilidade): baseline de conversao pt-BR (DECISIONS P9) permanece como pendencia a ser resolvida na Onda 11 (F11.4 PostHog eventos). Nao bloqueia fechamento de Onda 9.
- Commit: nao realizado (brief proibiu commit nesta rodada).
- Gate: aguarda aprovacao do Codex.

## 2026-04-19 - T4 F12.1 v2 - APROVADA pelo Codex

- Fase: F12.1 (revisao apos reprovacao).
- Resultado: APROVADA. Os tres pontos criticos foram resolvidos (path do .env generalizado, divergencia de env var frontend tratada, ASCII puro).
- Aprovado por: Codex
- Aprovado em: 2026-04-19

## 2026-04-19 - T4 F12.2 - Runbook disaster recovery Tolgee

- Fase: F12.2 (antecipada; Onda 12 original).
- Entrada: F12.1 aprovada; direcao operacional de antecipar runbooks um por vez.
- Arquivos criados:
  - `C:\winegod-app\docs\RUNBOOK_I18N_DISASTER.md` (ASCII puro, cenarios 1-4 + secao 8 permanente)
- Arquivos alterados:
  - `C:\winegod-app\reports\i18n_execution_log.md` (este log; entrada de F12.1 v2 aprovada + entrada F12.2)
- Pre-verificacao de repo:
  - `C:\winegod-app\shared\` NAO existe (glob em `shared/**` retornou zero matches). Portanto `shared/i18n/backup/` tambem nao existe. Criacao de `shared/` e entrega de T1 F0.2; cron de backup semanal e entrega de T3 F8.7.
  - Nao editei nada em `shared/**` (fora da minha matriz).
- Escopo do runbook:
  - Cenario 1: Tolgee API indisponivel.
  - Cenario 2: Projeto Tolgee deletado acidentalmente.
  - Cenario 3: Secret/token `TOLGEE_API_KEY` exposto.
  - Cenario 4: Divergencia entre snapshot local e Tolgee.
  - Secao 8: Tolgee morre permanentemente (conta suspensa ou servico descontinuado).
- Principio central reforcado (DECISIONS P17): Tolgee NAO e dependencia runtime; o site serve o snapshot em `frontend/messages/<locale>.json` e continua funcional mesmo com Tolgee fora. Runbook veta explicitamente descrever o produto como "fora do ar" por causa de incidente Tolgee.
- Premissas pendentes documentadas em secao 0 do runbook:
  - `shared/i18n/backup/` depende de T1 F0.2 + T3 F8.7.
  - Secrets `TOLGEE_API_KEY` em GitHub/Vercel/Render dependem de T3 F8.2.
  - Workflows `tolgee-push.yml` e `tolgee-pull.yml` dependem de T3 F8.5 e F8.6.
  - `@tolgee/cli` ainda nao instalado (Onda 8).
- Rigor conferido:
  - Nao inventei comandos especificos de CLI Tolgee alem de `tolgee push` e `tolgee pull` (ja citados no plano).
  - Passos que dependem de secrets/dashboard marcados como acao do operador humano.
  - Encoding ASCII puro (validado com grep `[^\x00-\x7F]` - zero matches).
  - Rollback de locale nao misturado aqui (ja em F12.1).
- Commit: nao realizado.
- Requests a outras trilhas: nao criados.
- Gate: aguarda aprovacao do Codex.

## 2026-04-19 - T4 F12.2 - APROVADA pelo Codex

- Fase: F12.2.
- Resultado: APROVADA. Runbook ficou consistente com brief e decisoes (Tolgee tratado como camada de edicao, nao runtime; ausencia atual de shared/i18n/backup/ documentada; nao inventou recuperacao que o repo nao suporta).
- Aprovado por: Codex
- Aprovado em: 2026-04-19

## 2026-04-19 - T4 F12.3 - Documentacao de limitacoes I18N Tier 1

- Fase: F12.3 (antecipada; ultima dos runbooks/docs).
- Entrada: F12.2 aprovada.
- Arquivos criados:
  - `C:\winegod-app\docs\I18N_LIMITATIONS.md`
- Arquivos alterados:
  - `C:\winegod-app\reports\i18n_execution_log.md` (este log)
- Limitacoes documentadas (total 15 itens em 9 areas):
  - Area 2 Idiomas e mercados: Tier 1 = 4 idiomas; fr-FR so idioma; MX caution.
  - Area 3 Busca e conteudo dinamico: match exato (DNT); reviews on-demand Redis TTL 1h; pre-traducao manual.
  - Area 4 Layout/scripts: CJK e RTL nao suportados.
  - Area 5 Moderacao/UGC: nao ativa (produto nao tem UGC publico).
  - Area 6 Legal: 2 celulas (BR/pt-BR + DEFAULT/en-US); legal_binding_language=null para nao revisados.
  - Area 7 Observabilidade: Sentry/PostHog so Onda 11; baseline pt-BR TBD.
  - Area 8 Tolgee: Free 500 chaves/3 seats; founder so UI web.
  - Area 9 Fallback: hierarquia fr->en->pt / es->en->pt / en->pt; 301 permanente se locale desligado; header X-WG-UI-Locale cross-domain.
- Classificacao explicita de cada item em 3 categorias:
  - (A) Escopo deliberado (decisao travada) - maioria dos itens.
  - (B) Estrutural temporaria (sai em fase futura especifica) - Sentry/PostHog Onda 11, baseline pt-BR pos-F11.4.
  - (C) Fallback aceitavel (caminho previsto, nao bug) - hierarquia de fallback, 301 de locale desligado, header cross-domain.
- Itens obrigatorios do brief (5): todos incluidos e sustentados em referencias.
- Itens NAO incluidos deliberadamente (justificativa em secao 10 do doc):
  - Regras de produto nao-ambiguas (nomes de vinho DNT - e regra de negocio, nao limitacao sentida).
  - Processos operacionais (preview Vercel 48h, founder fora do CLI, Render deploy manual) - ficam nos docs canonicos.
  - Rollback e disaster recovery - ja tem runbooks dedicados F12.1 e F12.2.
  - Canary translation por % usuarios - handoff 14.1 classifica como rejeitado por overengineering; incluir seria "vender backlog como bug".
  - Tolgee SDK React - handoff 14.2 marca como adiado Tier 1.5; nao e limitacao sentida agora.
  - Wishlist generica e roadmap.
- Rigor aplicado:
  - Nao misturei "nao implementado ainda" com "fora de escopo atual" (3 classes distintas com legenda no topo).
  - Cada item tem referencia verificavel a DECISIONS, handoff ou plano.
  - Documento ficou operacional/consultavel, nao manifesto tecnico (secao 10 explicita o que NAO cobre).
- Encoding: ASCII puro (validado com grep [^\x00-\x7F] retornando zero matches).
- Commit: nao realizado.
- Requests a outras trilhas: nao criados.
- Gate: aguarda aprovacao do Codex.

## 2026-04-19 - T4 F12.3 - APROVADA pelo Codex

- Fase: F12.3.
- Resultado: APROVADA. Documento objetivo, bem classificado, sem misturar escopo deliberado com pendencia temporaria. 5 limitacoes obrigatorias cobertas e sustentadas.
- Aprovado por: Codex
- Aprovado em: 2026-04-19

## 2026-04-19 - T4 F9.1 - Validador CLDR de plurais (antecipado)

- Fase: F9.1 (antecipada como artefato; Onda 9 original).
- Entrada: F12.3 aprovada; direcao operacional de antecipar F9.1/F9.5/F9.6 um por vez.
- Arquivos criados:
  - `C:\winegod-app\scripts\i18n\validate_plurals.py`
- Arquivos alterados:
  - `C:\winegod-app\reports\i18n_execution_log.md` (este log)
- Pre-verificacao de repo:
  - `C:\winegod-app\frontend\messages\` NAO existe ainda (entrega T2 F2.2). Script foi desenhado para rodar contra qualquer diretorio via `--dir`, nao depende dos arquivos reais existirem hoje.
  - `babel` 2.18.0 disponivel no Python local (validado via `python -c "import babel"`). NAO consta em `backend/requirements.txt` (nao e dependencia do backend; e dependencia do ambiente dev/CI onde este script roda).
  - API usada: `babel.Locale.parse(code.replace('-','_')).plural_form.rules.keys() | {'other'}` - retorna categorias CLDR por locale.
- Detalhes do script:
  - Python 3 standalone, ASCII puro (grep `[^\x00-\x7F]` zero matches).
  - CLI argparse com `--dir`, `--locales`, `--strict-extras`, `--json`, `--help`.
  - Default: `--dir frontend/messages` resolvido relativo a cwd.
  - Deteccao de bloco plural: dict cujas keys sao TODAS categorias CLDR (zero/one/two/few/many/other) E pelo menos 1 key nao-`other` (filtro defensivo contra falso-positivo em objeto com so `other`).
  - Deteccao cross-file via uniao de paths plurais: se um path e bloco plural em qualquer arquivo carregado, o script valida o mesmo path em todos os demais arquivos. Isso captura o caso tipico de tradutor copiar so `other` para locale secundario - detectado como `missing_plural_categories`.
  - Reporta: arquivo, caminho da chave, locale, categorias obrigatorias, presentes, faltantes, extras.
  - Extras CLDR (validas porem nao requeridas no locale) = warning por padrao, error com `--strict-extras`.
  - Keys nao-CLDR dentro de bloco plural = error estrutural dedicado.
  - Dependencia `babel` ausente = error claro e instrutivo, sem tentar instalar nada e sem editar manifests (REGRA 1 respeitada).
- Exit codes documentados no `--help` e testados:
  - 0 OK; 2 dir missing; 3 babel ausente (nao testavel sem mexer ambiente); 4 JSON invalido; 5 locale nao suportado; 6 categorias faltantes; 7 extras + --strict-extras.
- Verificacao executada:
  - `python -m py_compile` OK.
  - `python ... --help` renderiza CLI e exit codes.
  - Fixtures temporarias em `%TEMP%/wg_f91_v2_*` (fora de git):
    - CASE A (pt-BR com many/one/other valido, isolado): rc=0 obtido.
    - CASE B (en-US isolado, sem contexto cross-file): rc=0 obtido (correto - sem cross-file nao ha como saber que e plural).
    - CASE C (ambos arquivos juntos): rc=6 obtido; detectou `MISSING:['one']` em en-US via deteccao cross-file.
  - Fixtures adicionais para exit codes 2, 4, 5, 7: rc real = 2/4/5/7 conforme documentado.
  - JSON mode (`--json`): estrutura completa no stdout; testada com fixture pt-BR.
  - ASCII puro validado.
- Limitacao atual da F9.1 (depende de entregas futuras):
  - Valida contra arquivos `<locale>.json` conforme convencao oficial (T2 F2.2). Enquanto T2 nao criar `frontend/messages/*.json` definitivos, o script so roda util contra fixtures de teste.
  - Deteccao cross-file so funciona se o path for plural em pelo menos 1 arquivo carregado. Se todos os arquivos copiarem so `other` (nenhum tem bloco plural completo), o path nao entra na uniao e nao e validado. Mitigacao esperada: T2/T3 devem garantir que pt-BR (fonte) sempre tenha bloco plural completo. Alternativa futura: estender o validador com lista explicita de paths plurais conhecidos via arquivo de config (fora do escopo F9.1).
  - Script nao instala babel nem edita manifests. Se CI for usar, o manifest de dependencia Python do repo (quando existir) precisa incluir `Babel` - decisao fora da matriz T4. Por ora, o ambiente local do operador/CI ja tem.
- Commit: nao realizado.
- Requests a outras trilhas: nao criados.
- Gate: aguarda aprovacao do Codex.

## 2026-04-19 - T4 F9.1 v1 - REPROVADA pelo Codex

- Fase: F9.1 (v1).
- Resultado: REPROVADA.
- Motivo objetivo: script usava categorias brutas do babel/CLDR como contrato final, exigindo `many` para pt-BR, es-419 e fr-FR. Isso conflita com brief (exemplo pt one/other) e com handoff secao 5.6 (que trava pt-BR, en-US, es-419, fr-FR como `one/other`).
- Acao: separar contrato do projeto vs CLDR bruto; CLDR usado apenas como fallback para locales nao travados.

## 2026-04-19 - T4 F9.1 v2 - Validador CLDR com contrato de projeto

- Fase: F9.1 (revisao apos reprovacao v1).
- Arquivos alterados:
  - `C:\winegod-app\scripts\i18n\validate_plurals.py` (refatorado)
  - `C:\winegod-app\reports\i18n_execution_log.md` (este log)
- Regra final de categorias obrigatorias (implementada em `_required_categories_for`):
  1. Se locale esta em `PROJECT_PLURAL_CONTRACT` (exact match), usa essas categorias. Source tag: `project_contract`.
  2. Se locale casa um wildcard `<lang>-*` no contrato (ex: `ar-SA` -> `ar-*`), usa as categorias do wildcard. Source tag: `project_contract_wildcard`.
  3. Senao, tenta babel/CLDR (`_cldr_categories_for`). Source tag: `cldr_fallback`.
  4. Se babel nao importavel E locale nao contratado -> erro `missing_dependency` (exit 3).
  5. Se babel importavel mas nao reconhece o locale E locale nao contratado -> erro `unsupported_locale` (exit 5).
- Contrato do projeto (sustentado em handoff 5.6 + brief):
  - Tier 1: `pt-BR`, `en-US`, `es-419`, `fr-FR` -> `{one, other}`
  - Tier 2: `ru-RU`, `pl-PL` -> `{one, few, many, other}`
  - Tier 3 wildcard: `ar-*` -> `{zero, one, two, few, many, other}`
- Observacao importante: contracted locales NAO precisam mais de babel. Babel so e obrigatorio para locales fora do contrato. Isso torna o script mais resiliente em ambientes de CI minimos.
- Docstring do script atualizada para explicar a ordem de resolucao e o racional (CLDR sozinho bloquearia conteudo valido no projeto; contrato do projeto vence).
- Output humano agora mostra `Source : project_contract | project_contract_wildcard | cldr_fallback` por arquivo.
- Verificacao executada (todos os rc reais validados sem pipe):
  - TC1 pt-BR com `{one, other}` -> rc=0 (era 6 em v1).
  - TC2 en-US com `{one, other}` -> rc=0.
  - TC3 es-419 com `{one, other}` -> rc=0 (era 6 em v1).
  - TC4 fr-FR com `{one, other}` -> rc=0 (era 6 em v1).
  - TC5 todos 4 Tier 1 juntos -> rc=0.
  - TC6 falha cross-file (pt-BR completo, en-US so `other`) -> rc=6, MISSING=['one']. Ainda detecta.
  - TC7 ru-RU com `{one, other}` (Tier 2 exige few/many) -> rc=6, MISSING=['few','many'], source=project_contract.
  - TC8 ar-SA via wildcard com `{one, other}` -> rc=6, MISSING=['few','many','two','zero'], source=project_contract_wildcard.
  - TC9 de-DE nao contratado, fixture `{one, other}` -> rc=0, source=cldr_fallback (de-DE em CLDR e `one/other`, fixture e valido).
- Outras mudancas:
  - Nenhuma alem da correcao do contrato plural e do modulo de resolucao. Varredura recursiva, deteccao cross-file, flags CLI (`--dir`, `--locales`, `--strict-extras`, `--json`, `--help`), mensagens de erro claras, ausencia de edicao em manifests -- tudo preservado.
- Encoding: ASCII puro (grep `[^\x00-\x7F]` zero matches em script e log).
- Commit: nao realizado.
- Requests a outras trilhas: nao criados.
- Gate: aguarda aprovacao do Codex.

## 2026-04-19 - T4 F9.1 v2 - APROVADA pelo Codex

- Fase: F9.1 v2.
- Resultado: APROVADA. Separacao contrato de projeto vs CLDR bruto correta; Tier 1 passam com one/other; cross-file preservado; fallback para nao contratados preservado.
- Aprovado por: Codex
- Aprovado em: 2026-04-19

## 2026-04-19 - T4 F9.6 - QA Checklist de release gates (antecipado)

- Fase: F9.6 (antecipada como artefato; Onda 9 original).
- Entrada: F9.1 v2 aprovada; direcao operacional de antecipar F9.1/F9.5/F9.6 um por vez.
- Arquivos criados:
  - `C:\winegod-app\scripts\i18n\QA_CHECKLIST.md`
- Arquivos alterados:
  - `C:\winegod-app\reports\i18n_execution_log.md` (este log)
- Estrutura do checklist (5 gates + 3 apendices):
  - Legenda unica no topo: `[ ]` nao verificado / `[x]` OK / `[!]` FALHOU / `[b]` bloqueado por outra trilha / `[n]` nao aplicavel ainda.
  - Criticidade por item: (B) bloqueante / (A) aviso / (D-Tn) dependencia de outra trilha.
  - Gate 0 - Pre-condicoes de sincronizacao (10 itens): sinais `.sync` (t1_onda0, t1_f6_4b, t2_onda4, t1_onda6, t3_onda7, t3_onda8), feature_flags em prod, endpoint /api/config/enabled-locales, backup Tolgee.
  - Gate 1 - QA estatico (7 subsecoes): F9.1 plurals, F9.2 smoke, F9.4 Playwright visual, F9.5 pseudo-loc, F6.6 regressao Baco, lint frontend (D-T2), build frontend (D-T2).
  - Gate 2 - QA funcional manual (7 subsecoes, 2-3h per handoff 11.4): rotas publicas por 4 locales, app routes logado, cenarios criticos (age gate, CTA FR oculto), seletor de idioma, persistencia cross-domain, fallback de chaves, Baco cultural (amostragem).
  - Gate 3 - Readiness de release (6 subsecoes): F9.7.a report estatico, observabilidade runtime (condicional Onda 11), runbooks, F9.8 Fiverr, F9.9 URLs indexadas com 301 permanente, higiene de repo.
  - Gate 4 - Autorizacao Onda 10 SINGLE-THREADED (6 subsecoes): pre-flight imediato, autorizacao humana explicita (campos para preencher), sinalizacao .sync/t4_onda10_SINGLE_THREADED_START, verificacao de pausa T1/T2/T3, referencia operacional durante Onda 10, protocolo de saida.
  - Apendice A - Escalacao de falha (5 passos).
  - Apendice B - Itens deliberadamente NAO incluidos (ja cobertos por runbooks/limitations).
  - Apendice C - Historico de uso.
- Itens marcados explicitamente como dependencia externa (D-Tn) ou estado condicional:
  - Gate 0: 6 itens D-T1/T2/T3 com sinais `.sync` esperados citados.
  - Gate 0: backup Tolgee como (A, D-T3) - disaster recovery cai em modo degradado sem ele, coerente com RUNBOOK_I18N_DISASTER secao 0.
  - Gate 1: lint/build frontend (D-T2); regressao Baco (D-T1 para F6.4b).
  - Gate 2: age gate (D-T3), hook useEnabledLocales (D-T2), header X-WG-UI-Locale (D-T2).
  - Gate 3 secao 3.1: endpoint admin/i18n-health (D-T1 via request).
  - Gate 3 secao 3.2 inteira: Onda 11 ainda pode estar pendente - marcacao (n|B) com nota "aguarda F11.2 + F11.4".
  - Gate 3 secao 3.4 Fiverr: granularidade (B|A) porque o operador pode aceitar ativacao condicional.
  - Gate 4 secao 4.1: migration 018 (D-T1 via request + sinal `.sync/t1_migration_018_done`).
- Diferenciacao explicita no texto da legenda entre "nao aplicavel agora" (`[n]`), "bloqueado aguardando outra trilha" (`[b]`) e "falhou" (`[!]`). Apendice A define escalacao.
- Rigor aplicado:
  1. Nao transforma item bloqueado em checkbox enganoso de OK. Cada dependencia externa esta marcada com D-Tn e cita o sinal/arquivo esperado. Itens de Onda 11 ficam (n|B) ate F11.2+F11.4 fecharem.
  2. Baseline conversao pt-BR (DECISIONS P9 TBD) marcado como (A) em Gate 3 com nota explicita "per orientacao do administrador NAO bloqueia Onda 9".
- Itens importantes deliberadamente NAO incluidos (justificativa em Apendice B):
  - Passos de rollback - ja em RUNBOOK_I18N_ROLLBACK.md (F12.1).
  - Passos de disaster Tolgee - ja em RUNBOOK_I18N_DISASTER.md (F12.2).
  - Explicacao de limitacoes de produto - ja em I18N_LIMITATIONS.md (F12.3).
  - Roadmap/wishlist - fora do escopo.
  - Checklist completo de 20 perguntas culturais Fiverr - pertence ao brief do Fiverr.
  - Criterios de sucesso 30 dias - ja estao em HANDOFF_OFICIAL secao 16 (checklist cobre apenas entrega inicial).
  - Bugs ativos nao-i18n - usam backlog/Sentry.
- Encoding: ASCII puro (grep `[^\x00-\x7F]` zero matches).
- Commit: nao realizado.
- Requests a outras trilhas: nao criados.
- Gate: aguarda aprovacao do Codex.

## 2026-04-19 - T4 F9.6 - APROVADA pelo Codex

- Fase: F9.6.
- Resultado: APROVADA. Checklist operacional de verdade, gates claros, dependencia externa marcada sem maquiagem, protocolo Onda 10 bem amarrado ao single-threaded.
- Aprovado por: Codex
- Aprovado em: 2026-04-19

## 2026-04-19 - T4 F9.5 - Gerador de pseudo-localizacao (antecipado)

- Fase: F9.5 (antecipada como artefato; Onda 9 original).
- Entrada: F9.6 aprovada.
- Arquivos criados:
  - `C:\winegod-app\scripts\i18n\pseudo_loc.py`
- Arquivos alterados:
  - `C:\winegod-app\reports\i18n_execution_log.md` (este log)
- Pre-verificacao de repo:
  - `C:\winegod-app\frontend\messages\` NAO existe ainda (entrega T2 F2.2). Script foi desenhado para rodar contra qualquer par `--input`/`--output`, nao depende de caminho fixo.
- Respeito a matriz de ownership:
  - T2 e dona de `frontend/messages/**`. Esta fase NAO cria nem comita `frontend/messages/pseudo.json`. O script torna `--output` obrigatorio (sem default) para evitar escrita presumida em area de T2. Verificacao usou fixtures em `%TEMP%/wg_f95_fix/` (fora de git, removidas apos teste).
- Estrategia de transformacao (aplicada a strings SEGURAS):
  1. Substituicao de letras ASCII por look-alikes com diacriticos combinantes (ex: `a` -> `a\u0301`, `c` -> `c\u0327`). Mapa deterministico em `ACCENT_MAP`.
  2. Padding com tokens de filler (macrons) ate ~30% de aumento de comprimento. Tamanho extra = ceil(len * 0.30), calculo puro sem randomizacao.
  3. Wrap final com `[!! ... !!]` para QA humano identificar hardcodes pt-BR que escaparam ao refactor.
- Estrategia de preservacao segura (rigorosa - `_is_unsafe_to_transform`):
  - Regex `{...}`: bateu placeholder named/indexed OU ICU MessageFormat -> PRESERVA.
  - Regex `{{...}}`: bateu template mustache -> PRESERVA.
  - Regex `(^|[^\\])#`: bateu token ICU `#` literal (usado em `{count, plural, one {# item}}`) -> PRESERVA.
  - Regex `<...>`: bateu tag HTML/JSX -> PRESERVA.
  - Regex URL `\bhttps?://\S+`: PRESERVA.
  - Regex email: PRESERVA.
  - Regra de ouro: **preferir preservar do que gerar output invalido**. String preservada passa byte-identical.
- Keys NUNCA sao transformadas. Valores nao-string (int, bool, null, listas de nao-strings) passam byte-identical.
- Relatorio final imprime (stdout com `--summary`; JSON puro com `--json-report`):
  - input path, output path
  - strings_transformed
  - strings_preserved (seguros)
  - strings_empty_passthrough (string vazia)
  - non_string_passthrough
  - lista de paths preservados com reason tag (has_placeholder_or_icu, has_url, has_email, has_html_or_jsx_tag, has_mustache_template, has_icu_hash_token)
- Output: JSON valido, UTF-8, indent=2, sort_keys=True, ensure_ascii=False (acentos renderizam direto para o QA visual).
- CLI:
  - `--input` (obrigatorio)
  - `--output` (obrigatorio, sem default)
  - `--summary` (imprime resumo humano)
  - `--json-report` (emite relatorio completo em JSON no stdout)
  - `--help`
- Exit codes:
  - 0 sucesso; 2 argparse/CLI error ou input missing; 3 JSON invalido no input; 4 output path invalido ou nao writable.
- Verificacao executada:
  - `python -m py_compile` OK.
  - `--help` renderiza CLI + nota de ownership (T2 owns frontend/messages).
  - Fixture abrangente em `%TEMP%/wg_f95_fix/in.json` com 15 casos:
    - `simple: "Hello world"` -> transformada, wrapped `[!! ... !!]`, +acentos, +padding.
    - `short: "Oi"` -> transformada, wrapped.
    - `nested.subtitle` -> transformada.
    - `mixed_list[0]` "plain string" -> transformada.
    - `placeholder_name` `"Welcome, {name}!"` -> PRESERVADA (has_placeholder_or_icu).
    - `placeholder_count` `"You have {count} items"` -> PRESERVADA.
    - `icu_plural` `"{count, plural, one {# item} other {# items}}"` -> PRESERVADA.
    - `url_string` com https:// -> PRESERVADA (has_url).
    - `email_string` com @ -> PRESERVADA (has_email).
    - `html_tag` com `<a>` -> PRESERVADA (has_html_or_jsx_tag).
    - `double_brace` `"{{greeting}}"` -> PRESERVADA (has_placeholder_or_icu detecta `{...}` interno).
    - `mixed_list[1]` `"Welcome, {user}!"` -> PRESERVADA.
    - `empty: ""` -> passthrough vazio.
    - `number: 123`, `boolean: false`, `null_val: null`, `mixed_list[2..4]` -> passthrough nao-string.
  - Resumo produzido: transformed=4, preserved=8, empty=1, non-string=6 (contabiliza items de listas tambem).
  - JSON de output re-parseado com `json.load` sem erro.
  - Todas as 16 asserts de forma (wrap, len > input*1.2, preservacao byte-identical) passaram.
  - Exit codes validados em fixture: 2 (input missing), 3 (JSON invalido), 4 (output path invalido em drive inexistente Z:).
- ASCII puro: script usa `\uXXXX` escapes para todos os caracteres acentuados no codigo; arquivo-fonte 100% ASCII (grep `[^\x00-\x7F]` zero matches). O JSON de output contem caracteres acentuados por necessidade (isso e parte da pseudo-loc); o ARQUIVO do script em si e ASCII.
- Limitacoes residuais do gerador:
  - Regex `{...}` de placeholder e "greedy-safe" (balanceada num nivel). Strings com placeholder MUITO aninhado (ICU nested plural com multiplas camadas) podem ter match falso; nesses casos o script preserva a string, nao transforma. E por design: prefere skipping seguro a risco de quebrar.
  - Nao detecta marcacao de mercado especifico (ex: tokens `$<variable>` no estilo Rails). Se aparecer, ficara fora do escopo de "safe to transform" somente se casar uma das regras atuais; caso contrario sera transformada. Mitigacao futura: adicionar regra de `$\w+` se T2 adotar esse formato.
  - Nao transforma listas de strings puras recursivamente com contexto diferente - trata cada item independente (o que e o comportamento esperado).
  - `frontend/messages/pseudo.json` NAO foi criado per matriz de ownership (T2). Quando T2 aceitar a pseudo-loc, basta rodar o script contra o `pt-BR.json` real e commitar via PR aprovado por T2.
- Commit: nao realizado.
- Requests a outras trilhas: nao criados.
- Gate: aguarda aprovacao do Codex.

---

## F0.1 - Gate de realidade
- Data concluida: 2026-04-19
- Arquivo principal: reports/WINEGOD_MULTILINGUE_DECISIONS.md
- Resultado: 19 decisoes respondidas. F0.4 (rota `/` continua sendo chat) e posicionamento US-facing / global-first registrados posteriormente no mesmo documento como context adicional.
- Criterio de aceitacao: aprovado.

## F0.2 - Estrutura shared
- Data concluida: 2026-04-20 16:47
- Arquivos criados:
  - shared/i18n/.gitkeep
  - shared/i18n/backup/.gitkeep
  - shared/legal/BR/.gitkeep
  - shared/legal/DEFAULT/.gitkeep
- Teste: listagem recursiva de shared/ confirmando 4 diretorios e 4 `.gitkeep` de 0 bytes.
- Criterio de aceitacao: aprovado pelo Codex.

## F0.3 - Indice I18N_README + log inicializado
- Data concluida: 2026-04-20 16:48
- Arquivos criados/alterados:
  - docs/I18N_README.md (criado)
  - reports/i18n_execution_log.md (append com as 3 entradas desta secao)
- Teste:
  - Test-Path equivalente: docs/I18N_README.md existe, tamanho > 0.
  - Listagem: docs/I18N_README.md e reports/i18n_execution_log.md ambos presentes.
- Criterio de aceitacao: pronto para revisao do Codex.

## F0.5 - Bootstrap tooling ESLint + deps i18n/SWR
- Data concluida: 2026-04-20 16:53
- Arquivos modificados:
  - frontend/package.json (script `lint` trocado de `next lint` para `eslint .`; bloco de dependencias/devDependencies atualizado com as novas libs)
  - frontend/package-lock.json (atualizado pelo npm)
  - frontend/eslint.config.mjs (criado; flat config ESLint 9 + Next 15 com plugins `@next/next`, `react`, `react-hooks`, `@typescript-eslint` declarados; rules do `@next/next` recomendadas ativas; `eslint-plugin-i18next/no-literal-string` NAO ativado, fica para F3.1)
- Dependencias instaladas:
  - Runtime: `swr@2.4.1`, `gray-matter@4.0.3`
  - Dev: `eslint@9.39.4`, `@next/eslint-plugin-next@16.2.4`, `eslint-plugin-react@7.37.5`, `eslint-plugin-react-hooks@7.1.1`, `@typescript-eslint/eslint-plugin@8.59.0`, `@typescript-eslint/parser@8.59.0`, `typescript-eslint@8.59.0`, `eslint-plugin-i18next@6.1.4`
  - NAO instalados (fora de escopo): `next-intl` (F2.1), `@tolgee/cli` (Onda 8), `@playwright/test` (F9.3)
- Testes rodados:
  - `cd frontend && npm run lint` -> exit 0, 0 errors, 12 warnings (avisos `@next/next/no-img-element` e `@next/next/no-html-link-for-pages` preexistentes no codigo; nao sao bloqueio em F0.5; refatoracao de UI fica fora de escopo)
  - `cd frontend && npm run build` -> compiled successfully, 14 paginas geradas, bundle OK. Warning residual: "The Next.js plugin was not detected in your ESLint configuration" durante a etapa "Linting and checking validity of types" do build. Causa: heuristica do Next para detectar plugin via legacy config nao reconhece a flat config via import. Impacto: nulo (lint standalone roda normalmente com as regras `@next/next/*` ativas, ver saida de `npm run lint` acima). Deixar para fase posterior se virar necessidade.
  - `cd frontend && npm ls swr eslint-plugin-i18next gray-matter` -> os 3 listados nas versoes 2.4.1 / 6.1.4 / 4.0.3.
  - `cd frontend && npm ls next-intl @tolgee/cli @playwright/test` -> exit 1 com `(empty)`, comportamento esperado do npm quando pacotes pedidos nao estao instalados. Confirma que nenhum dos 3 foi adicionado.
- Criterio de aceitacao: atendido. `npm run lint` roda via `eslint .` sem wizard e retorna exit 0. `npm run build` passa. `npm ls` confirma presenca das 3 libs alvo e ausencia das 3 libs fora de escopo.
- Observacoes:
  - 1 warning de auditoria npm (high severity) foi reportado pela instalacao. Nao investigado nesta fase por estar fora do escopo F0.5; avaliar em fase dedicada se necessario.
  - 12 warnings de lint sao preexistentes do codigo (uso de `<img>` e `<a>` para `/`) e devem ser tratados em fase proprietaria de refatoracao UI, nao aqui.
- Gate: pronto para revisao do Codex.

## F0.6 - Decisao de kill switch
- Data concluida: 2026-04-20 16:58
- Arquivos modificados:
  - reports/WINEGOD_MULTILINGUE_DECISIONS.md (secao "Decisao complementar F0.6 - Kill switch de locales" adicionada antes da Assinatura)
  - docs/I18N_README.md (secao de proximos passos atualizada: F0.5 e F0.6 marcadas como concluidas; F1.1 registrada como proximo passo real)
  - reports/i18n_execution_log.md (esta entrada)
- Decisao: implementar Plano A (flag dinamica via `feature_flags`, cache TTL 10-30s) + Plano B (env var `ENABLED_LOCALES`, redeploy 2-5 min). Fail-safe em `["pt-BR"]`. Nenhum codigo criado nesta fase.
- Testes/validacao:
  - `grep -E "F0.6|feature_flags|ENABLED_LOCALES|10-30s|2-5 min" reports/WINEGOD_MULTILINGUE_DECISIONS.md` -> secao F0.6 encontrada com todos os marcadores.
  - `grep -E "F0.6 - Decisao de kill switch" reports/i18n_execution_log.md` -> entrada propria desta fase.
  - `grep -E "F0.6|F1.1|kill switch" docs/I18N_README.md` -> linha atualizada.
- Criterio de aceitacao: pronto para revisao do Codex.
- Observacao: implementacao concreta do kill switch fica para F1.6 (migration `feature_flags`), F1.8 (endpoint `GET /api/config/enabled-locales`) e Onda 10 (canario progressivo via `UPDATE feature_flags`). Esta fase e puramente decisao/documentacao.
- Gate: pronto para revisao do Codex.

## F0.6 - Correcao textual no I18N_README
- Data: 2026-04-20 17:02
- Arquivo: docs/I18N_README.md (linha da F0.6 nos proximos passos)
- Mudanca: substituir "sao ambos implementados" por "foram decididos como arquitetura oficial; a implementacao real comeca em F1.6 (tabela) e F1.8 (endpoint)", pois na F0.6 nao ha codigo implementado ainda.
- Teste: grep confirmou presenca de "F0.6", "foram decididos", "implementacao real comeca" e ausencia de "sao ambos implementados" em docs/I18N_README.md.
- Gate: pronto para revisao do Codex.

## F1.1 - shared/i18n/markets.json
- Data concluida: 2026-04-20 17:07
- Arquivos criados/alterados:
  - shared/i18n/markets.json (criado)
  - reports/i18n_execution_log.md (esta entrada)
- Mercados criados: BR, US, MX, FR, DEFAULT (5 chaves de topo).
- Decisoes aplicadas:
  - BR: tier 1, comercial completo, `legal_template: "BR"`, `legal_binding_language: "pt-BR"`, age 18.
  - US: US-facing / global-first com `baco_mode: "commercial"`, `commercial_enabled: true`, mas `legal_template: "DEFAULT"` e `legal_binding_language: null` ate revisao juridica US futura. Age 21.
  - MX: caution sem CTA comercial (`commercial_enabled: false`, `purchase_cta_allowed: false`, `baco_mode: "caution"`). Age 18.
  - FR: idioma apenas, mercado comercial EU bloqueado ate juridico EU (`enabled: "partial"`, `commercial_enabled: false`, `baco_mode: "educational"`, `seo_indexable: "partial"`). Age 18.
  - DEFAULT: fallback global US-facing en-US/USD, `commercial_enabled: false`, `baco_mode: "educational"`, `seo_indexable: false`, `legal_template: "DEFAULT"`. Age 18.
  - `legal_binding_language` = null em US, MX, FR e DEFAULT (sem revisao juridica); apenas BR mantem `pt-BR`.
- Testes rodados:
  - Node parse: `node -e "..."` imprimiu `[ 'BR', 'US', 'MX', 'FR', 'DEFAULT' ]`, `en-US USD` e `DEFAULT null` -> JSON valido em Node.
  - Python parse + asserts: `python -c "..."` imprimiu `ok`, confirmando `MX.legal_binding_language is None`, `FR.commercial_enabled is False` e `DEFAULT.default_locale == 'en-US'`.
  - JSON valido nos dois runtimes, conforme exigido pelo plano.
- Criterio de aceitacao: atendido.
- Gate: pronto para revisao do Codex.

## F1.2 - shared/i18n/dnt.md
- Data concluida: 2026-04-20 17:17
- Arquivos criados/alterados:
  - shared/i18n/dnt.md (criado, 7785 bytes, 8 secoes + header + footer)
  - reports/i18n_execution_log.md (esta entrada)
- Categorias cobertas:
  1. Regra geral de preservacao (capitalizacao, pontuacao, hifens; preservar na duvida).
  2. Marca e produto: WineGod, WineGod.ai, Baco, Cicno, Vivino, Wine-Searcher, Delectable. Observacoes de anti-traducao (Bacchus, Deus do Vinho, etc.).
  3. Nomes de vinhos, vinicolas, produtores: Chateau Margaux, Opus One, Sassicaia, Vega Sicilia, Catena Zapata, Almaviva, Dom Perignon, Penfolds Grange, Gaja, Antinori etc.
  4. Castas e variedades: Cabernet Sauvignon, Merlot, Pinot Noir, Chardonnay, Sauvignon Blanc, Syrah/Shiraz, Malbec, Tempranillo, Sangiovese, Nebbiolo, Riesling, Chenin Blanc, Grenache/Garnacha, Tannat, Carmenere, Touriga Nacional, Albarino, Gewurztraminer, Viognier, Zinfandel, Primitivo, Nero d'Avola etc.
  5. Denominacoes/regioes/classificacoes: Champagne, Bordeaux, Bourgogne, Burgundy, Napa Valley, Rioja, Ribera del Duero, Chianti Classico, Barolo, Brunello di Montalcino, Vinho Verde, Douro, Porto, Jerez, Sherry, Cava, Prosecco, Mendoza, Stellenbosch + DOC/DOCG/DOP/AOC/AOP/AVA/DO/DOCa/IGP/IGT/VDP/VQPRD/Cru/Premier Cru/Grand Cru.
  6. Termos tecnicos: terroir, cuvee, grand cru, premier cru, reserva, gran reserva, crianza, brut, extra brut, brut nature, vintage, non-vintage, millesime, blanc de blancs, blanc de noirs, rose, frizzante, spumante, solera, en primeur, negociant.
  7. URLs/codigos/IDs/variaveis: chat.winegod.ai, api.winegod.ai, /c/[id], /legal/:country/:lang/:doc, /api/auth/me, /api/config/enabled-locales, /auth/callback, placeholders ICU ({count}, {name}, {wine_name}, plural ICU, {{greeting}}), headers X-WG-UI-Locale / X-WG-Market-Country / X-WG-Currency, env vars ENABLED_LOCALES / TOLGEE_API_KEY / ANTHROPIC_API_KEY / DATABASE_URL / FLASK_ENV, cookies wg_locale_choice / wg_age_verified, feature_flags, tabela de locale/currency (pt-BR, en-US, es-419, fr-FR, BRL, USD, MXN, EUR).
  8. Como usar: guia para Tolgee, Baco (F6.2 copia para backend/prompts/baco/dnt.md), revisores Fiverr, Claude/Codex; fluxo de atualizacao aditivo.
- Testes rodados:
  - `ls shared/i18n/dnt.md` -> existe, 7785 bytes.
  - `grep -E "WineGod|Baco|Cabernet Sauvignon|Champagne|X-WG-UI-Locale|ENABLED_LOCALES" shared/i18n/dnt.md` -> 15 matches; todos os 6 tokens confirmados (linhas 1, 25, 93, 140, 270, 276 entre outras).
  - Validacao ASCII via Python: `re.findall(r'[^\x00-\x7F]', texto)` retornou lista vazia (0 caracteres nao-ASCII). Arquivo 100% ASCII puro, conforme regra.
- Criterio de aceitacao: atendido. Arquivo cobre marcas, nomes proprios, castas, denominacoes, termos tecnicos, URLs/variaveis; ASCII puro; glossary NAO criado nesta fase (fica para F1.3).
- Gate: pronto para revisao do Codex.

## F1.3 - shared/i18n/glossary.md
- Data concluida: 2026-04-20 18:04
- Arquivos criados/alterados:
  - shared/i18n/glossary.md (criado, 6653 bytes, UTF-8, 30 linhas de termos)
  - reports/i18n_execution_log.md (esta entrada)
- Total de termos: 30
- Idiomas cobertos: pt-BR, en-US, es-419, fr-FR (4 colunas de traducao + 1 de Key + 1 de Notes)
- Keys (ordem):
  1. wine, 2. red_wine, 3. white_wine, 4. rose_wine, 5. sparkling_wine, 6. dessert_wine, 7. vintage, 8. grape_variety, 9. blend, 10. producer, 11. winery, 12. region, 13. appellation, 14. terroir, 15. body, 16. acidity, 17. tannin, 18. aroma, 19. bouquet, 20. finish, 21. oak, 22. barrel, 23. aging, 24. pairing, 25. serving_temperature, 26. sweetness, 27. dry, 28. brut, 29. reserve, 30. organic_wine.
- Termos marcados (DNT) na coluna Notes: `vintage` (parcial, em rotulo), `appellation` (parcial, quando parte do nome oficial), `terroir` (total), `bouquet` (total), `brut` (total), `reserve` (parcial, quando categoria DOC). Total: 6 termos com clausula DNT parcial ou total.
- Testes rodados:
  - `ls shared/i18n/glossary.md` -> existe, 6653 bytes.
  - `grep -E "wine|terroir|brut|organic_wine|pt-BR|en-US|es-419|fr-FR" shared/i18n/glossary.md` -> 22 matches; todos os 8 tokens presentes.
  - Contagem de linhas da tabela via Python: `len(rows)==30` -> ok. Filtro usou startswith('| ') excluindo header (`| Key`) e separador (`|---`). 30 confirmadas.
  - Leitura UTF-8 via Python: `Path(...).read_text(encoding='utf-8')` sem excecao -> utf8 ok.
- Observacoes:
  - Acentos preservados apenas onde linguisticamente naturais em pt-BR/es/fr (ex: "region" mantida sem acento nas colunas por simplicidade, com nota inline autorizando render UTF-8 quando o frontend suportar). Evitadas aspas tipograficas, travessoes e emojis.
  - `terroir`, `bouquet`, `brut`: DNT total (mantem original em todos os idiomas).
  - `vintage`, `appellation`, `reserve`: DNT parcial (depende do contexto).
  - dnt.md NAO foi tocado, apenas referenciado.
- Criterio de aceitacao: atendido. Glossary draft cobre 30 termos nos 4 idiomas, marcacao DNT coerente com dnt.md, UTF-8 valido.
- Gate: pronto para revisao do Codex. Revisao nativa Fiverr fica para F12.4.

## F1.3 - Correcao de qualidade linguistica no glossary
- Data: 2026-04-20 18:15
- Arquivo: shared/i18n/glossary.md (mesmo arquivo da F1.3 original; sem troca de estrutura)
- Mudanca: acentos UTF-8 naturais restaurados em termos pt-BR, es-419 e fr-FR que haviam ficado sanitizados em ASCII. 30 keys preservadas, 6 colunas preservadas, marcacoes DNT preservadas. Tambem ajustado texto de prosa das secoes 1, 2 (intro) e 3 para leitura natural em pt-BR.
- Principais termos corrigidos: rose_wine (rose -> rose), vintage fr-FR (millesime -> millesime com acento), grape_variety fr-FR (cepage -> cepage com acento), winery pt-BR (vinicola -> vinicola com acento), region em pt-BR/es-419/fr-FR (regiao, region, region com acentos), appellation (denominacao/denominacion com til/acento + Contrôlée/Calificada nos exemplos), acidity fr-FR (acidite -> acidite com acento), aroma fr-FR (arome -> arome com acento), oak fr-FR (chene -> chene com acento), barrel fr-FR (fut -> fut com acento), aging fr-FR (elevage -> elevage com acento), pairing pt-BR (harmonizacao -> harmonizacao com til/cedilha), serving_temperature pt-BR/fr-FR (servico, temperature de service com acentos), sweetness pt-BR/fr-FR (docura, sucrosite com acentos), reserve fr-FR (reserve com acento), organic_wine pt-BR/es-419 (organico/organico com acentos). dnt.md NAO foi alterado.
- Testes:
  - Contagem de linhas: 30 rows (filtro startswith('| ') excluindo header/separador) -> ok.
  - UTF-8 legivel: ok.
  - Presenca de 15 tokens acentuados checados por grep -> 15 matches distribuidos nas secoes 1 (linha 8), tabela (linhas 29, 32, 33, 36, 37, 38, 41, 43, 46, 47, 48, 49, 50, 51, 55) e secao 3.
  - dnt.md: tamanho 7785 bytes, igual ao registrado na F1.2; git diff vazio -> intacto.
- Gate: pronto para revisao do Codex.

## F1.4 - Migration 015 user i18n fields
- Data concluida: 2026-04-20 18:30
- Arquivos criados/alterados:
  - database/migrations/015_add_user_i18n_fields.sql (criado; migration aditiva idempotente)
  - backend/db/models_auth.py (CREATE TABLE com os 3 campos novos para bancos novos; funcao `ensure_user_i18n_columns()` criada e chamada em `create_tables()`; `upsert_user()` e `get_user_by_id()` atualizados para retornar `ui_locale`, `market_country`, `currency_override` com fallbacks; assinatura das funcoes preservada)
  - reports/i18n_execution_log.md (esta entrada)
- Decisoes:
  - Migration 100% aditiva: somente `ADD COLUMN IF NOT EXISTS`. Nao usa NOT NULL nesta fase.
  - Forward-fix via `UPDATE ... WHERE ... IS NULL` (idempotente; REGRA 5 do CLAUDE.md: operar em LOCAL primeiro, prod depois; em prod, se base for grande, rodar em batches).
  - Constraint `users_ui_locale_check` adicionada via DO block consultando `pg_constraint` para garantir idempotencia (Postgres nao tem ADD CONSTRAINT IF NOT EXISTS universal).
  - Whitelist de `ui_locale`: apenas Tier 1 (`pt-BR`, `en-US`, `es-419`, `fr-FR`).
  - `currency_override` intencionalmente sem DEFAULT: null = usar currency_default do mercado (markets.json).
  - `market_country` com DEFAULT 'BR': preserva comportamento atual do produto (entidade juridica BR); usuarios US-facing que se autenticarem continuam podendo mudar pelo endpoint PATCH em F1.7.
  - `models_auth.py` espelha a migration dentro de `ensure_user_i18n_columns()` para bancos que sobem via `create_tables()` em dev/CI sem rodar a migration avulsa. `ensure_*` foi chamada junto de `ensure_cost_column` e `ensure_multi_provider_columns` dentro de `create_tables()`.
  - `upsert_user()`: tres caminhos (update por provider_id, update por email, insert novo) retornam agora as 3 novas colunas via RETURNING; a assinatura publica nao mudou.
  - `get_user_by_id()`: SELECT estendido; novo dict retornado inclui `ui_locale`, `market_country`, `currency_override` com fallback para 'pt-BR'/'BR'/None se o banco devolver NULL (defensivo, pois migration so roda apos deploy).
- Testes rodados:
  - `python -m py_compile backend/db/models_auth.py` -> OK.
  - `python -c "import models_auth; print('ok')"` -> `models_auth import ok`; `ensure_user_i18n_columns` presente.
  - `python -c "from pathlib import Path; s=...; asserts"` -> `migration text ok` (confirmou presenca das 3 `ADD COLUMN IF NOT EXISTS` e do nome `users_ui_locale_check`).
  - `psql` LOCAL nao foi rodado: este ambiente nao tem banco Postgres local configurado, e a REGRA 2 do CLAUDE.md + REGRA 7 impedem rodar em prod sem autorizacao explicita. Migration sera testada em banco LOCAL seguro em etapa separada de dev antes do deploy.
- Escopo respeitado:
  - Nao criou endpoint `/api/auth/me/preferences` (F1.7).
  - Nao mexeu em frontend.
  - Nao mexeu em `shared/i18n/markets.json`, `dnt.md` ou `glossary.md`.
  - Nao fez commit.
- Gate: pronto para revisao do Codex.

## F1.5 - Migration 016 wines i18n JSONB fields
- Data concluida: 2026-04-20 18:42
- Arquivos criados/alterados:
  - database/migrations/016_add_wines_i18n_jsonb_fields.sql (criado)
  - reports/i18n_execution_log.md (esta entrada)
- Decisoes:
  - Migration 100% aditiva e idempotente: `ADD COLUMN IF NOT EXISTS description_i18n JSONB DEFAULT '{}'::jsonb` e o mesmo para `tasting_notes_i18n`.
  - Sem NOT NULL: JSONB vazio default cobre leitura segura sem quebrar queries existentes.
  - Sem indice JSONB/GIN: nao e escopo da F1.5 (se consulta por chave de locale virar gargalo em fases futuras, avaliar `CREATE INDEX` em fase dedicada).
  - Sem backfill em wines (REGRA 5 do CLAUDE.md: base de ~1.72M linhas, evitar UPDATE monolitico; backfill multilingue real acontece em ondas de traducao dedicadas quando necessario).
  - Nao alterou queries existentes, nao tocou trigger de score recalc, nao tocou coluna antiga `description` (se existir).
  - Adicionado `COMMENT ON COLUMN` curto em cada coluna documentando o formato esperado (`{"<locale>": "<texto>"}`) e o default vazio. Estilo segue migrations 005 e anteriores do repo.
  - Nao tocou backend Python, frontend, shared/i18n, nem criou endpoint/model/service/script de backfill/teste (fora do escopo da F1.5 conforme handoff).
- Testes rodados:
  - `python -c "from pathlib import Path; s=Path(...).read_text(encoding='utf-8'); assert ...; print('migration text ok')"` -> `migration text ok` (4 asserts passaram: `ALTER TABLE wines`, `ADD COLUMN IF NOT EXISTS description_i18n JSONB`, `DEFAULT '{}'::jsonb`, `ADD COLUMN IF NOT EXISTS tasting_notes_i18n JSONB`).
  - Validacao textual apenas: nao ha banco Postgres LOCAL seguro configurado neste ambiente; REGRA 7 do CLAUDE.md impede rodar em prod. Migration sera aplicada em LOCAL/dev quando banco local estiver disponivel, e em prod via deploy manual conforme REGRA 7.
- Escopo respeitado:
  - Nao tocou backend Python (models, services, routes).
  - Nao tocou frontend.
  - Nao tocou `shared/i18n/markets.json`, `dnt.md`, `glossary.md`.
  - Nao criou migration adicional, nao alterou migrations anteriores.
  - Nao fez commit.
- Gate: pronto para revisao do Codex.

## F1.6 - Migration 017 feature_flags
- Data concluida: 2026-04-20 18:52
- Arquivos criados/alterados:
  - database/migrations/017_create_feature_flags.sql (criado)
  - reports/i18n_execution_log.md (esta entrada)
- Decisoes:
  - Tabela `feature_flags` implementa Plano A do kill switch decidido em F0.6. Estrutura minima: `key TEXT PRIMARY KEY`, `value_json JSONB NOT NULL`, `description TEXT`, `updated_at TIMESTAMPTZ DEFAULT NOW()`, `updated_by TEXT`.
  - Migration idempotente: `CREATE TABLE IF NOT EXISTS` + `INSERT ... ON CONFLICT (key) DO NOTHING`. Pode ser re-executada em LOCAL sem efeito colateral.
  - Seed inicial estrito: `enabled_locales = '["pt-BR"]'::jsonb`. en-US, es-419 e fr-FR NAO sao ativados agora; ativacao progressiva acontece em Onda 10 via `UPDATE feature_flags SET value_json = ... WHERE key='enabled_locales'`.
  - `updated_by = 'migration_017'` marca a origem da row seed para rastreabilidade em futuros audits.
  - NENHUM indice extra, trigger ou constraint alem da PRIMARY KEY. Tabela e pequena por design (< 100 rows esperadas em toda a vida do produto); indice secundario nao traz ganho.
  - Leitura runtime (endpoint `GET /api/config/enabled-locales`, cache TTL 10-30s, fallback em `ENABLED_LOCALES` env var, fail-safe `["pt-BR"]`) NAO esta nesta fase; vira em F1.8.
  - Nao tocou backend Python, frontend, shared/i18n, nem alterou migrations anteriores.
- Testes rodados:
  - `python -c "... asserts"` (6 asserts) -> `migration text ok`: confirma `CREATE TABLE IF NOT EXISTS feature_flags`, `key TEXT PRIMARY KEY`, `value_json JSONB NOT NULL`, `'enabled_locales'`, `'["pt-BR"]'::jsonb` e `ON CONFLICT (key) DO NOTHING` presentes.
  - `python -c "... seed asserts"` -> `seed only pt-BR ok`: confirma que apos `VALUES` o texto nao contem `en-US`, `es-419` nem `fr-FR`.
  - Validacao textual apenas: ambiente sem banco Postgres LOCAL seguro configurado; REGRA 7 do CLAUDE.md impede rodar em prod. Aplicacao em LOCAL/dev sera feita em etapa de deploy manual separada.
- Escopo respeitado:
  - Nao tocou backend Python (models, services, routes, config).
  - Nao tocou frontend.
  - Nao tocou `shared/i18n/markets.json`, `dnt.md`, `glossary.md`.
  - Nao criou endpoint `/api/config/enabled-locales` (F1.8).
  - Nao implementou leitura de `ENABLED_LOCALES` env var (F1.8).
  - Nao fez commit.
- Gate: pronto para revisao do Codex.

## F1.7 - Preferences endpoint
- Data concluida: 2026-04-20 19:05
- Arquivos alterados:
  - backend/db/models_auth.py (nova funcao `update_user_preferences(user_id, preferences)`; nao altera assinaturas de `upsert_user` ou `get_user_by_id`)
  - backend/routes/auth.py (nova rota `PATCH /auth/me/preferences` + helper `_validate_preferences`; `GET /auth/me` agora inclui bloco `preferences` no topo-level sem quebrar campos existentes)
  - reports/i18n_execution_log.md (esta entrada)
- Contrato do endpoint:
  - `PATCH /api/auth/me/preferences` (url_prefix `/api` ja esta no app.py; rota no arquivo usa `/auth/me/preferences`).
  - Header: `Authorization: Bearer <jwt>`.
  - Body: `{"preferences": {"ui_locale": "...", "market_country": "...", "currency_override": "..." | null}}`.
  - Ao menos uma das 3 chaves deve estar presente; chaves desconhecidas sao rejeitadas.
  - Response 200: `{"preferences": {"ui_locale": "...", "market_country": "...", "currency_override": ... | null}}`.
- Compatibilidade `GET /api/auth/me`:
  - Mantem `user` (id, name, email, picture_url, provider, last_login) e `credits` (used, remaining, limit) exatamente como antes.
  - Adiciona bloco `preferences` topo-level com `ui_locale`, `market_country`, `currency_override` (fallback "pt-BR"/"BR"/None).
  - Frontend atual continua funcionando: nenhum campo existente foi removido ou renomeado.
- Validacoes implementadas:
  - Body precisa ser JSON object (caso contrario: `invalid_json`, 400).
  - `preferences` obrigatorio (caso contrario: `missing_preferences`, 400).
  - `preferences` precisa ser dict (caso contrario: `invalid_preferences`, 400).
  - Chave desconhecida em `preferences`: `unknown_preference_field`, 400.
  - Nenhuma das 3 chaves aceitas presente: `no_preferences_fields`, 400.
  - `ui_locale` whitelist fechada (`pt-BR`, `en-US`, `es-419`, `fr-FR`); senao `invalid_ui_locale`, 400.
  - `market_country` regex `^[A-Za-z]{2}$`; aceita `us` e normaliza para `US`; senao `invalid_market_country`, 400.
  - `currency_override` pode ser `null`, ou regex `^[A-Za-z]{3}$` normalizado para upper (`usd` -> `USD`); senao `invalid_currency_override`, 400.
  - Token ausente/invalido: 401 com `message_code: errors.auth.unauthorized`.
  - User_id do JWT nao existe no banco (edge case): 404 com `message_code: errors.auth.user_not_found`.
  - Respostas de erro 400/401/404 seguem formato `{"error": "<code>", "message_code": "errors.auth.<code>"}` (compatibilidade com F4.0/Onda 5 do plano).
  - NAO valida contra `enabled_locales` ou `markets.json` aqui (fica para F1.8 / F2.9).
  - Stacktrace nao e vazado (request.get_json() envolvido em try/except).
- Decisoes:
  - `update_user_preferences()`: monta UPDATE dinamico apenas com as chaves presentes; se `preferences` for vazio (ja filtrado pela rota, mas defensivo), retorna estado atual; usa `RETURNING ui_locale, market_country, currency_override`; retorna None se `user_id` nao existir.
  - `currency_override = None` grava `NULL` via placeholder psycopg (adapter converte None para SQL NULL).
  - Assinatura e retorno das funcoes `upsert_user` e `get_user_by_id` preservadas (F1.4 ja havia incluido os 3 campos no retorno).
- Testes rodados:
  - `python -m py_compile backend/db/models_auth.py backend/routes/auth.py` -> `py_compile OK`.
  - `python -c "... hasattr(update_user_preferences) ... patch_preferences ..."` -> `imports ok`.
  - `python -c "... auth route text ok"` -> OK (decorador, `message_code`, e os 3 campos presentes).
  - `python -c "... model update text ok"` -> OK (funcao `update_user_preferences`, `UPDATE users SET`, `RETURNING ui_locale, market_country, currency_override`).
  - Teste unitario puro do helper `_validate_preferences`: 13 casos (5 OK + 8 erro) cobrindo todos os codigos de erro e normalizacao ISO. Todos passaram.
- Escopo respeitado:
  - Nao mexeu em frontend, shared/i18n, migrations, backend/app.py (auth_bp ja registrado com prefix `/api`).
  - Nao implementou leitura de feature_flags ou ENABLED_LOCALES (F1.8).
  - Nao criou endpoint de config/enabled-locales (F1.8).
  - Nao rodou em banco real.
  - Nao fez commit.
- Gate: pronto para revisao do Codex.

## F1.7 - Correcao user_not_found vs unauthorized
- Data: 2026-04-20 19:20
- Arquivo: backend/routes/auth.py (apenas; reports/i18n_execution_log.md recebe esta entrada)
- Bug corrigido:
  - `patch_preferences()` usava `get_current_user(request)`, que devolve `None` tanto para token invalido quanto para JWT valido cujo user_id nao existe mais no banco. Consequencia: usuario deletado recebia 401 `errors.auth.unauthorized`, em vez dos 404 `errors.auth.user_not_found` prometidos no contrato da F1.7.
- Correcao:
  - Novo helper privado `_get_bearer_payload(req)` em `backend/routes/auth.py` que retorna `(payload, err)` separando 401 (token ausente/invalido) de sucesso.
  - `patch_preferences()` agora:
    1. `payload, err = _get_bearer_payload(request)` -> se `err` 401, responde `unauthorized`.
    2. `user = get_user_by_id(payload["user_id"])` -> se `None`, responde `404 user_not_found`.
    3. Prossegue com a validacao de body/preferences e chama `update_user_preferences(user["id"], clean)` igual antes.
  - `get_current_user()` NAO foi tocado (outras rotas dependem do comportamento atual: `GET /auth/me` e `DELETE /auth/me` continuam retornando 401 quando user sumiu, preservando compatibilidade).
  - Nenhuma mudanca em `backend/db/models_auth.py`, frontend, shared/i18n, migrations ou `app.py`.
- Testes sem banco (via Flask test_request_context + monkeypatch local em `routes.auth`):
  - T3 sucesso: `decode_jwt -> {user_id:123}`, `get_user_by_id -> {id:123,...}`, `update_user_preferences -> clean`. Body `{"preferences": {"market_country":"us","currency_override":"usd"}}`. Resultado: status 200, `preferences.market_country == "US"`, `preferences.currency_override == "USD"` (normalizacao para upper preservada). PASS.
  - T1 user_not_found: `decode_jwt -> {user_id:123}`, `get_user_by_id -> None`. Resultado: status 404, `message_code == "errors.auth.user_not_found"`. PASS.
  - T2 unauthorized: `decode_jwt -> None`. Resultado: status 401, `message_code == "errors.auth.unauthorized"`. PASS.
  - `python -m py_compile backend/routes/auth.py backend/db/models_auth.py` -> OK.
  - `python -c "from routes import auth; assert hasattr(auth, 'patch_preferences')"` -> OK.
- Gate: pronto para revisao do Codex.

## F1.8 - Enabled locales endpoint
- Data concluida: 2026-04-20 19:40
- Arquivos criados/alterados:
  - backend/routes/config.py (criado; novo blueprint `config_bp` com rota `GET /config/enabled-locales`, helpers puros `_normalize_enabled_locales`, `_parse_enabled_locales_env`, `_load_enabled_locales_from_db` e resolver `_resolve_enabled_locales`)
  - backend/app.py (alterado: import `config_bp` + `register_blueprint(config_bp, url_prefix='/api')` apos `conversations_bp`)
  - reports/i18n_execution_log.md (esta entrada)
- Contrato final:
  - URL: `GET /api/config/enabled-locales`
  - Header de resposta: `Cache-Control: max-age=30`
  - Response 200: `{"enabled_locales": [...], "default_locale": "pt-BR", "updated_at": "<iso|null>", "source": "db"|"env"|"fail_safe"}`
  - Whitelist fechada de locales: `pt-BR`, `en-US`, `es-419`, `fr-FR`.
- Regras implementadas:
  - Plano A (DB): `SELECT value_json, updated_at FROM feature_flags WHERE key='enabled_locales'`. Aceita valor JSONB ja parseado (psycopg2 padrao) ou string JSON. Valida a lista via whitelist. Usa `source='db'` e devolve `updated_at` em ISO8601.
  - Plano B (env): se DB falhar / ausente / invalido, le `os.environ['ENABLED_LOCALES']`. Aceita JSON array (`["pt-BR","en-US"]`) ou CSV (`pt-BR,en-US`). Valida via whitelist. Usa `source='env'` e `updated_at=None`.
  - Fail-safe: se ambos falharem, retorna `["pt-BR"]` com `source='fail_safe'` e `updated_at=None`.
  - Sem cache em memoria nesta fase (HTTP `max-age=30` cobre o objetivo sem compartilhar estado entre workers Gunicorn).
  - SELECT apenas; nao faz INSERT/UPDATE; nao modifica a tabela `feature_flags`.
  - Exceptions de DB sao capturadas e caem para env/fail_safe sem vazar stacktrace.
  - `release_connection` sempre chamado no finally; robusto a `_load_enabled_locales_from_db` falhar antes do `get_connection` retornar.
- Decisoes de design:
  - `_normalize_enabled_locales` deduplica preservando ordem; rejeita lista vazia e itens fora da whitelist.
  - `_parse_enabled_locales_env` aceita dois formatos tolerantes (JSON array tem precedencia se comecar com `[`); strings vazias e None viram None.
  - `default_locale` fixo em `pt-BR`. Pode virar campo derivado do markets.json em fase futura, mas nao e necessario nesta fase.
  - O endpoint nao implementa locale persistence (F2.9) nem middleware de locale; apenas expoe o kill switch frontend-readable.
- Testes rodados:
  - `python -m py_compile backend/routes/config.py backend/app.py` -> `py_compile OK`.
  - `python -c "from app import create_app; app=create_app(); assert '/api/config/enabled-locales' in rules; print('route registered ok')"` -> `route registered ok`.
  - Helpers puros (7 asserts): `_normalize_enabled_locales(['pt-BR'])`, `(['en-US','pt-BR'])`, `(['de-DE']) is None`, `([]) is None`, `_parse_enabled_locales_env('[\"pt-BR\",\"en-US\"]')`, `_parse_enabled_locales_env('pt-BR,en-US')`, `_parse_enabled_locales_env('') is None` -> `pure helpers ok`.
  - Teste fail-safe via Flask test_client (DB monkeypatched para None, env removida): status 200, `enabled_locales=['pt-BR']`, `default_locale='pt-BR'`, `source='fail_safe'`, `updated_at=None`, `Cache-Control: max-age=30`. PASS.
  - Teste env via test_client (`ENABLED_LOCALES='pt-BR,en-US'`, DB monkeypatched para None): status 200, `enabled_locales=['pt-BR','en-US']`, `source='env'`, `updated_at=None`, header ok. PASS.
  - Teste DB via test_client (DB monkeypatched para `(['pt-BR'], '2026-04-20T00:00:00Z')`): status 200, `enabled_locales=['pt-BR']`, `source='db'`, `updated_at='2026-04-20T00:00:00Z'`, header ok. PASS.
  - Banco real: nao rodado (ambiente sem Postgres LOCAL seguro; REGRA 7 impede prod). Migration 017 ainda aguarda deploy manual.
- Escopo respeitado:
  - Nao tocou frontend, shared/i18n, migrations, `backend/routes/auth.py`, `backend/db/models_auth.py`.
  - Nao implementou middleware de locale nem F2.9.
  - Nao fez commit.
- Gate: pronto para revisao do Codex.

## F2.1 - Install next-intl
- Data concluida: 2026-04-20 20:00
- Versao instalada: next-intl@4.9.1
- Arquivos alterados:
  - frontend/package.json (adicionou dependencia `"next-intl": "^4.9.1"`)
  - frontend/package-lock.json (atualizado pelo npm; 20 pacotes adicionados no grafo de deps)
  - reports/i18n_execution_log.md (esta entrada)
- Nao criou:
  - frontend/messages/ (fica para F2.2)
  - frontend/middleware.ts (fica para F2.5)
  - next-intl config em next.config.ts (fica para F2.3)
  - provider / layout wiring (fica para F2.3b)
  - routing/request config (fica para F2.4)
  - arquivos de traducao
  - testes novos
- Testes rodados:
  - `cd frontend && npm install next-intl@latest` -> ok, 20 pacotes adicionados em ~14s.
  - `cd frontend && npm ls next-intl` -> `next-intl@4.9.1` confirmado no topo do grafo.
  - `cd frontend && npm run build` -> Compiled successfully, 14 paginas geradas. Warning residual "The Next.js plugin was not detected in your ESLint configuration" do build continua da F0.5 (causa conhecida: heuristica legada do Next para flat config); impacto nulo, lint standalone funciona.
  - `cd frontend && npm run lint` -> exit 0, 0 errors, 12 warnings preexistentes (uso de `<img>` e `<a>` para `/`, todos da F0.5; nenhuma regressao introduzida por F2.1).
  - `cd frontend && npm ls @tolgee/cli @playwright/test` -> exit 1 com `(empty)`, comportamento esperado (pacotes nao instalados). Confirmado que F2.1 nao instalou libs fora de escopo.
  - `ls frontend/messages frontend/middleware.ts` -> nao existem (conforme esperado).
  - `next.config.ts` existe mas NAO foi editado (preexistente).
- Observacoes:
  - Warning `npm audit` high (1 vulnerabilidade) persiste desde F0.5; nao investigado aqui por estar fora do escopo F2.1, conforme ressalva da aprovacao da F0.5.
  - Nenhum backend, shared/i18n, migration, endpoint ou UI foi tocado.
  - Nao fez commit.
- Gate: pronto para revisao do Codex.

## F2.2 - frontend/messages skeleton
- Data concluida: 2026-04-20 20:15
- Arquivos criados:
  - frontend/messages/pt-BR.json (conteudo exato `{}`)
  - frontend/messages/en-US.json (conteudo exato `{}`)
  - frontend/messages/es-419.json (conteudo exato `{}`)
  - frontend/messages/fr-FR.json (conteudo exato `{}`)
  - reports/i18n_execution_log.md (esta entrada)
- Nao criou (reservado para fases seguintes):
  - frontend/i18n/ (request.ts/routing.ts ficam para F2.4)
  - frontend/middleware.ts (F2.5)
  - configuracao next-intl em next.config.ts (F2.3)
  - NextIntlClientProvider no root layout (F2.3b)
  - arquivos index.ts em messages/
  - chaves dummy ou comentarios
  - outros locales alem do Tier 1
- Testes rodados:
  - Script Python (estrutura + parse): confirma `frontend/messages/` existe, contem exatamente os 4 arquivos esperados, cada um parseavel como JSON valido e resolve para `{}`. Saida: `pt-BR.json {}`, `en-US.json {}`, `es-419.json {}`, `fr-FR.json {}`, `files ok`.
  - `cd frontend && npm run build` -> Compiled successfully, 14 paginas geradas. Warning residual do Next sobre plugin ESLint persiste da F0.5 (heuristica legada).
  - `cd frontend && npm run lint` -> exit 0, 0 errors, 12 warnings preexistentes (F0.5). Nenhuma regressao.
  - `ls frontend/i18n frontend/middleware.ts` -> nao existem (confirmado).
  - `next.config.ts` nao foi tocado nesta fase.
  - `package.json` / `package-lock.json` nao foram tocados nesta fase (mudancas visiveis no diff sao de F0.5 + F2.1 ja aprovadas).
- Gate: pronto para revisao do Codex.

## F2.3 - next-intl plugin config
- Data concluida: 2026-04-20 20:30
- Arquivos alterados:
  - frontend/next.config.ts (alterado: import `createNextIntlPlugin` de `next-intl/plugin`, `const withNextIntl = createNextIntlPlugin()`, export agora e `withNextIntl(nextConfig)`; `reactStrictMode: true` preservado)
  - frontend/i18n/request.ts (criado como STUB TECNICO MINIMO; vide justificativa abaixo)
  - reports/i18n_execution_log.md (esta entrada)
- Justificativa do stub em `frontend/i18n/request.ts`:
  - next-intl v4 (instalado: `next-intl@4.9.1`) exige um request config modulo no build. Tentativa de build apenas com o plugin ligado em `next.config.ts` falhou com erro explicito: `[next-intl] Could not locate request configuration module. This path is supported by default: ./(src/)i18n/request.{js,jsx,ts,tsx}`.
  - Criado stub minimo em `frontend/i18n/request.ts` com `getRequestConfig` retornando `locale: "pt-BR"` e `messages: {}`. Nao implementa resolucao real de locale (cookie, geo, fallback chain), nem carrega `messages/*.json` dinamicamente.
  - Arquivo contem comentario explicito avisando que sera **inteiramente substituido** em F2.4 (routing real + fallback chain) e complementado por F2.3b (NextIntlClientProvider no root layout).
- Nao criou nesta fase:
  - frontend/middleware.ts (F2.5)
  - NextIntlClientProvider wrapping em `app/layout.tsx` (F2.3b)
  - `frontend/i18n/routing.ts` (F2.4)
  - helpers de formatters / fallbacks (F2.6/F2.7)
  - locale context / seletor (F2.9)
- Testes rodados:
  - `python -c "... assert 'next-intl/plugin' in s; assert 'createNextIntlPlugin' in s; assert 'reactStrictMode' in s; print('next config ok')"` -> `next config ok`.
  - `cd frontend && npm run build` -> Compiled successfully, 14 paginas geradas, bundle identico ao de F2.2 (plugin sem runtime cost perceptivel nesta fase).
  - `cd frontend && npm run lint` -> exit 0, 0 errors, 12 warnings preexistentes (F0.5). Nenhuma regressao.
  - Messages continuam `{}`: script Python confirma `pt-BR.json {}`, `en-US.json {}`, `es-419.json {}`, `fr-FR.json {}`, `messages still empty ok`.
- Escopo respeitado:
  - Nao tocou backend, shared/i18n, migrations, package.json, package-lock.json.
  - Nao fez `npm install`.
  - Nao fez commit.
- Gate: pronto para revisao do Codex.

## F2.3b - NextIntlClientProvider no root layout
- Data concluida: 2026-04-20 20:50
- Arquivos alterados:
  - frontend/app/layout.tsx (alterado: imports `NextIntlClientProvider` de `next-intl` e `getLocale`/`getMessages` de `next-intl/server`; `RootLayout` virou `async function`; `<html lang>` agora dinamico via `locale = await getLocale()`; `<body>` envolve children em `<NextIntlClientProvider locale={locale} messages={messages}>`; metadata, fonts e classes preservados; nada de UI alterado)
  - frontend/i18n/request.ts (alterado: continua com `locale = "pt-BR"` HARDCODED, mas agora carrega dinamicamente `messages = (await import('../messages/${locale}.json')).default` para que `getMessages()` retorne o objeto certo. Comentario de cabecalho atualizado avisando que F2.4 substitui)
  - reports/i18n_execution_log.md (esta entrada)
- Nao criou nesta fase:
  - frontend/middleware.ts (fica para F2.5)
  - frontend/i18n/routing.ts (fica para F2.4)
  - fallback chain (F2.4)
  - cookie wg_locale_choice / header geo / precedencia F2.9 (fica para F2.4 + F2.9)
  - selector de idioma, hook `useEnabledLocales`, SWR (F2.4b/F2.4c/F2.9)
  - chaves dummy nos messages (proibido nesta fase)
- Comportamento atual:
  - Toda rota sem prefixo (`/`, `/chat/[id]`, `/conta`, `/favoritos`, `/plano`, `/ajuda`, etc.) renderiza com `lang="pt-BR"` no `<html>` e provider montado.
  - `useTranslations()` agora pode ser chamado em qualquer client component dentro do app: o provider esta montado.
  - Como messages estao todos `{}`, qualquer chave acessada via `t('foo')` retornara o key como fallback no momento (comportamento padrao do next-intl). Isso nao e regressao: nenhum chamada `useTranslations()` existe no codigo ainda; sera populado a partir de F4.x.
  - Locale ainda nao reflete cookie/geo: tudo cai em pt-BR. F2.4 substitui isso pela chain real.
- Testes rodados:
  - `python -c "... layout structural ok"` -> OK (provider, getLocale/getMessages, async, `<html lang={locale}>`, wrapper presentes).
  - `cd frontend && npm run build` -> Compiled successfully, 14 paginas geradas, bundle inalterado.
  - `cd frontend && npm run lint` -> exit 0, 0 errors, 12 warnings preexistentes (F0.5). Nenhuma regressao.
  - Messages ainda `{}`: `pt-BR.json/en-US.json/es-419.json/fr-FR.json` confirmados (script Python). Nenhuma chave dummy injetada.
  - `frontend/middleware.ts` e `frontend/i18n/routing.ts` continuam inexistentes (confirmado por `ls`).
- Escopo respeitado:
  - Nao tocou backend, shared/i18n, migrations, package.json, package-lock.json, next.config.ts.
  - Nao alterou metadata, fonts, classes, UI nem visual.
  - Nao fez `npm install`.
  - Nao fez commit.
- Gate: pronto para revisao do Codex.

## F2.3b - Correcao request locale minimo
- Data: 2026-04-20 21:10
- Arquivo: frontend/i18n/request.ts (apenas; reports/i18n_execution_log.md recebe esta entrada)
- Bug corrigido:
  - O hardcode `const locale = "pt-BR"` foi removido. F2.3b agora resolve o locale por request com base em sinais reais.
- Ordem de resolucao implementada:
  1. `requestLocale` do segmento `[locale]` (caso seja usado quando F2.4/F2.5 introduzir routing com prefixo).
  2. Cookie `wg_locale_choice` (escolha manual persistente do usuario).
  3. Header geo `X-Vercel-IP-Country` mapeado por `LOCALE_BY_COUNTRY` (`BR -> pt-BR`, `US -> en-US`, `MX -> es-419`, `FR -> fr-FR`).
  4. Fallback fixo `pt-BR`.
- Detalhes da implementacao:
  - `import { cookies, headers } from "next/headers"` + `import { getRequestConfig } from "next-intl/server"`.
  - `SUPPORTED_LOCALES = ["pt-BR","en-US","es-419","fr-FR"] as const` + type guard `isSupportedLocale`.
  - `LOCALE_BY_COUNTRY` cobrindo BR/US/MX/FR. Outros paises caem para `pt-BR`.
  - Loaders estaticos `MESSAGE_LOADERS` mapeados aos 4 JSON em `../messages/*.json` (webpack consegue analisar staticamente, evitando require dinamico).
  - `getRequestConfig(async ({ requestLocale }) => { ... })` async com `await cookies()` e `await headers()` (Next 15 retorna Promise).
  - Tentativa em ordem decrescente (1 -> 4); se nada bater, fallback `pt-BR`.
  - Trade-off conhecido: usar `cookies()` / `headers()` faz Next 15 marcar todas as rotas como dinamicas (`ƒ`) em vez de estaticas (`○`). Isso e o preco correto da resolucao real de locale por request; F2.4 mantem.
- Nao tocou nesta correcao:
  - frontend/app/layout.tsx (intacto desde F2.3b original; provider continua montado igual).
  - frontend/messages/*.json (continuam `{}`).
  - frontend/next.config.ts.
  - frontend/middleware.ts (nao existe; F2.5).
  - frontend/i18n/routing.ts (nao existe; F2.4).
  - frontend/package.json / package-lock.json.
  - backend, shared/i18n, migrations.
- Testes rodados:
  - `cd frontend && npm run build` -> Compiled successfully, 14 paginas geradas. Rotas marcadas como `ƒ` (dynamic) por causa de `cookies()`/`headers()` no request config; comportamento esperado.
  - `cd frontend && npm run lint` -> exit 0, 0 errors, 12 warnings preexistentes (F0.5). Nenhuma regressao.
  - `python -c "... request locale resolver ok"` -> 11 asserts (10 presenca + 2 ausencia do hardcode em aspas duplas e simples) passaram.
  - `python -c "... messages still empty ok"` -> 4 JSON continuam `{}`. Nenhuma chave dummy.
- Gate: pronto para revisao do Codex.

## F2.4 - routing.ts + request.ts definitivo (fallback chain)
- Data concluida: 2026-04-20 21:35
- Arquivos alterados:
  - frontend/i18n/routing.ts (criado)
  - frontend/i18n/request.ts (reescrito; consome `routing.ts` e implementa fallback chain de messages)
  - reports/i18n_execution_log.md (esta entrada)
- routing.ts (contrato):
  - `import { defineRouting } from "next-intl/routing"`
  - `locales = ["pt-BR","en-US","es-419","fr-FR"] as const`
  - `type AppLocale = (typeof locales)[number]`
  - `defaultLocale: AppLocale = "pt-BR"`
  - `routing = defineRouting({ locales, defaultLocale, localePrefix: "as-needed", localeDetection: false })`
  - `isAppLocale(value): value is AppLocale` (type guard publico)
- request.ts:
  - Reutiliza `AppLocale`, `defaultLocale`, `isAppLocale`, `locales` de `./routing.ts`.
  - Resolucao de locale (mantida da F2.3b): requestLocale -> cookie wg_locale_choice -> header `X-Vercel-IP-Country` mapeado por `LOCALE_BY_COUNTRY` -> `defaultLocale`.
  - Loaders estaticos para os 4 JSON em `../messages/*.json`.
  - `FALLBACK_CHAIN`:
    - `pt-BR -> pt-BR`
    - `en-US -> en-US -> pt-BR`
    - `es-419 -> es-419 -> en-US -> pt-BR`
    - `fr-FR -> fr-FR -> en-US -> pt-BR`
  - Helpers puros: `isPlainObject`, `deepMerge` (preserva subarvores; locale principal sobrescreve fallback).
  - `loadMessagesWithFallback(locale)` carrega da camada mais generica para a mais especifica e mescla via `deepMerge`.
- Nao tocou nesta fase:
  - frontend/app/layout.tsx (provider continua intacto desde F2.3b).
  - frontend/middleware.ts (nao existe; F2.5).
  - frontend/messages/*.json (continuam `{}`).
  - frontend/next.config.ts, package.json, package-lock.json.
  - hook `useEnabledLocales`, consumidor de `/api/config/enabled-locales` (F2.4b/F2.4c).
  - F2.9 (sync bidirecional cookie x user.ui_locale).
  - backend, shared/i18n, migrations.
- Testes rodados:
  - `cd frontend && npm run build` -> Compiled successfully, 14 paginas geradas (rotas continuam `ƒ` por causa de `cookies()`/`headers()` no request config; comportamento esperado).
  - `cd frontend && npm run lint` -> exit 0, 0 errors, 12 warnings preexistentes (F0.5). Sem regressao.
  - Asserts estruturais Python (1 bloco, 5 secoes): messages `{}` em pt-BR/en-US/es-419/fr-FR; middleware.ts ausente; routing.ts contem `defineRouting`, `localePrefix: "as-needed"`, `localeDetection: false`, os 4 locales e `defaultLocale: AppLocale = "pt-BR"`; request.ts contem `wg_locale_choice`, `X-Vercel-IP-Country`, `requestLocale`, as 4 cadeias FALLBACK_CHAIN, e NAO contem `const locale = "pt-BR"` (aspas duplas) ou `'pt-BR'` (aspas simples). `ALL F2.4 STRUCTURAL CHECKS PASS`.
- Gate: pronto para revisao do Codex.

## F2.4b - Backend locale normalizer + decorator
- Data concluida: 2026-04-20 22:00
- Arquivos alterados:
  - backend/utils/i18n_locale.py (criado)
  - backend/routes/chat.py (import `with_request_locale` + decorator em `POST /chat` e `POST /chat/stream`, ordem: `@route -> @with_request_locale -> @require_credits -> def`; locale resolve cedo, sem interferir em creditos)
  - backend/routes/auth.py (import `with_request_locale` + decorator em `GET /auth/me`, `PATCH /auth/me/preferences`, `DELETE /auth/me`; comportamento das rotas inalterado)
  - reports/i18n_execution_log.md (esta entrada)
- Escopo respeitado:
  - Nada de frontend (`useEnabledLocales`, seletor, middleware, `messages/*.json`).
  - Nada de migration, `shared/i18n`, `services/baco.py`, prompt builder.
  - Reaproveitou `routes.config._resolve_enabled_locales`, `ALLOWED_LOCALES`, `DEFAULT_LOCALE`, `FAIL_SAFE_LOCALES` (sem duplicar logica DB/env/fail-safe).
- Contrato do normalizador (`backend/utils/i18n_locale.py`):
  - `is_allowed_locale(value)` -> bool, valida contra Tier 1.
  - `normalize_locale(requested, enabled=None)` -> sempre retorna locale Tier 1 habilitado; aplica `FALLBACK_CHAIN` (`pt-BR -> pt-BR`, `en-US -> en-US -> pt-BR`, `es-419 -> es-419 -> en-US -> pt-BR`, `fr-FR -> fr-FR -> en-US -> pt-BR`); requested invalido -> ponto de partida `DEFAULT_LOCALE`; enabled vazio/invalido -> `FAIL_SAFE_LOCALES` (`["pt-BR"]`); nunca retorna None nem 400.
  - `extract_request_locale(req)` -> tupla `(value, source)`; ordem header `X-WG-UI-Locale` -> header `x-wg-ui-locale` -> body JSON `ui_locale` -> `(None, "default")`. `req.get_json(silent=True)` evita exception.
  - `resolve_request_locale(req)` -> dict `{requested_locale, effective_locale, enabled_locales, fallback_applied, source}`. Se `_resolve_enabled_locales` levantar, cai em `FAIL_SAFE_LOCALES`.
  - `apply_request_locale(req=None)` -> grava `g.wg_requested_locale`, `g.wg_ui_locale`, `g.wg_enabled_locales`, `g.wg_locale_fallback_applied`. Quando `fallback_applied=True`, imprime `locale_fallback{from:<requested>, to:<effective>, route:<path>}` em stdout via `print(..., flush=True)`.
  - `with_request_locale(fn)` decorator: chama `apply_request_locale()` antes da view; em caso de excecao defensiva, defaults seguros sao gravados em `g` e a rota segue normalmente. NUNCA bloqueia request nem retorna 400.
- Rotas onde o decorator foi aplicado:
  - `POST /api/chat` (chat.py)
  - `POST /api/chat/stream` (chat.py)
  - `GET /api/auth/me` (auth.py)
  - `PATCH /api/auth/me/preferences` (auth.py)
  - `DELETE /api/auth/me` (auth.py)
- Exemplos de fallback observados nos testes:
  - `fr-FR` solicitado + enabled `["pt-BR","en-US"]` -> `en-US`, `fallback_applied=True`, log emitido.
  - `fr-FR` solicitado + enabled `["pt-BR"]` -> `pt-BR`, `fallback_applied=True`, log emitido.
  - `pt-BR` solicitado + enabled `["pt-BR"]` -> `pt-BR`, `fallback_applied=False`, sem log.
  - body `{"ui_locale":"es-419"}` + enabled `["pt-BR","en-US"]` -> `en-US`, `source="body"`.
- Testes rodados:
  - `python -m py_compile backend/utils/i18n_locale.py backend/routes/chat.py backend/routes/auth.py` -> `py_compile OK`.
  - 8 casos puros `normalize_locale(...)`: todos passaram (`fr-FR`/`en-US`/`es-419`/`pt-BR`/`de-DE`/None vs varias listas enabled, incluindo `[]` e `None`).
  - 4 cenarios Flask com `app.test_request_context` + monkeypatch em `_resolve_enabled_locales`: T1 fr-FR -> pt-BR (fallback True), T2 fr-FR -> en-US (fallback True), T3 pt-BR -> pt-BR (fallback False), T4 body es-419 -> en-US (source="body"). Logs `locale_fallback{...}` aparecem nas 3 primeiras (na T3 nao ha fallback).
  - `from app import create_app; create_app()` boota normalmente; `/api/chat`, `/api/chat/stream`, `/api/auth/me`, `/api/auth/me/preferences`, `/api/config/enabled-locales` registradas.
  - `psql` real nao rodado (sem banco LOCAL seguro; REGRA 7 impede prod).
- Observacao operacional:
  - Ordem dos decorators em chat.py preservada: `@chat_bp.route -> @with_request_locale -> @require_credits -> def`. Em runtime, `with_request_locale` envolve `require_credits`, garantindo que `g.wg_*` ja esta populado antes do gate de creditos rodar.
  - Funcoes pre-existentes em auth.py (`get_current_user`, `_validate_preferences`, `patch_preferences`) nao foram modificadas funcionalmente.
- Gate: pronto para revisao do Codex.

## F2.4c - Hook frontend useEnabledLocales (SWR)
- Data concluida: 2026-04-20 22:20
- Arquivos alterados:
  - frontend/lib/i18n/useEnabledLocales.ts (criado; pasta `frontend/lib/i18n/` tambem criada na hora)
  - reports/i18n_execution_log.md (esta entrada)
- Escopo respeitado:
  - Nao tocou backend, app/, components/, request.ts, routing.ts, messages/*.json, package.json, package-lock.json, migrations, shared/i18n.
  - Nao criou middleware, seletor de idioma, context provider, persistencia de cookie, integracao com chat.
- Contrato do hook:
  - `"use client";` no topo (client-only).
  - `import useSWR from "swr";`
  - `API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000"`; endpoint = `${API_URL}/api/config/enabled-locales`.
  - Tipos: `SupportedLocale = "pt-BR" | "en-US" | "es-419" | "fr-FR"`; `SUPPORTED_LOCALES` readonly array.
  - Constantes seguras: `FALLBACK_LOCALES = ["pt-BR"]`, `DEFAULT_LOCALE = "pt-BR"`.
  - Helpers puros: `isSupportedLocale(value)`, `normalizeLocalesList(value)`, `normalizeDefault(value)`, `normalize(payload)`.
  - `fetcher(url)`: usa `fetch(url, { credentials: "omit" })` (sem cookies cross-domain), valida `response.ok`, parseia JSON; lanca `Error` se HTTP nao-2xx.
  - SWR config: `refreshInterval: 30000` (30s), `revalidateOnFocus: true`, `shouldRetryOnError: true`, `errorRetryInterval: 5000`.
  - Hook publico: `useEnabledLocales(): { locales: string[], defaultLocale: string, isLoading: boolean }`.
- Como funciona o fallback seguro:
  - Em qualquer falha (rede, HTTP nao-2xx, JSON invalido, payload sem `enabled_locales`, lista nao-array, todos itens fora da whitelist, lista vazia), o hook retorna `locales = ["pt-BR"]` e `defaultLocale = "pt-BR"`.
  - `isLoading` reflete o flag do SWR (true so na primeira carga; revalidacoes em background nao alteram).
  - Validacao: `enabled_locales` e filtrado contra a whitelist Tier 1, deduplicado preservando ordem; vazio depois disso = fallback.
  - `default_locale` so e usado se for um locale suportado; senao `"pt-BR"`.
- Testes rodados:
  - `cd frontend && npm run build` -> Compiled successfully, 14 paginas geradas, bundle inalterado em relacao a F2.4 (hook nao e importado por nenhum componente ainda).
  - `cd frontend && npm run lint` -> exit 0, 0 errors, 12 warnings preexistentes (F0.5). Sem regressao.
  - Asserts estruturais Python: arquivo existe; contem `"use client"`, `useSWR`, `/api/config/enabled-locales`, `refreshInterval: 30000`, `pt-BR`. `middleware.ts` ausente. `messages/*.json` continuam `{}`. Saida final: `ALL F2.4c CHECKS PASS`.
- Gate: pronto para revisao do Codex.

## F2.5 - Middleware restrito de locale (rotas publicas SEO)
- Data concluida: 2026-04-20 22:45
- Arquivos alterados:
  - frontend/middleware.ts (criado)
  - reports/i18n_execution_log.md (esta entrada)
- Escopo respeitado:
  - Nao tocou frontend/app/*, components/*, request.ts, routing.ts, useEnabledLocales.ts, messages/*.json, package.json, package-lock.json, backend/*, migrations/*, shared/i18n/*.
  - SHAs antes/depois confirmam request.ts/routing.ts/useEnabledLocales.ts intactos.
- Como o middleware decide bypass vs rota publica:
  - 1. `isBypassPath(pathname)` -> retorna `NextResponse.next()` sem alteracao para: `/`, `/api/*`, `/_next/*`, `/chat`, `/chat/*`, `/auth`, `/auth/*`, `/conta(/...)`, `/favoritos(/...)`, `/plano(/...)`, qualquer extensao de asset (`.png/.jpg/.svg/.webp/.ico/.woff/.woff2/.css/.js/.map`), e `/c/<id>/opengraph-image`.
  - 2. `stripPublicLocalePrefix(pathname)` extrai `/en|/es|/fr` se presente. Apos strip, se o path resultante for bypass (ex: `/en/chat/abc` -> `/chat/abc`), tambem nao toca.
  - 3. Apos strip, so atua se `isPublicSeoPath(targetPath)` for true. Conjunto fechado: `/ajuda`, `/privacy`, `/terms`, `/data-deletion`, `/welcome`, e `/c/<id>` (regex `^/c/[^/]+/?$`).
  - 4. Qualquer outra coisa segue `NextResponse.next()` sem mexer.
- Como funciona `/en|/es|/fr` com REWRITE interno:
  - `/en/ajuda` -> rewrite interno para `/ajuda` (URL no browser permanece `/en/ajuda`), com request header `X-NEXT-INTL-LOCALE: en-US`.
  - `/es/terms` -> rewrite para `/terms` com `X-NEXT-INTL-LOCALE: es-419`.
  - `/fr/privacy` -> rewrite para `/privacy` com `X-NEXT-INTL-LOCALE: fr-FR`.
  - `/en/chat/abc` -> bypass total (nao reescrita; chat continua funcionando como rota privada sem locale prefix).
  - `/en/c/abc/opengraph-image` -> bypass total (OG dinamica intocada).
- Resolucao de locale para rotas publicas SEM prefixo:
  - Cookie `wg_locale_choice` (se for Tier 1) -> header geo `X-Vercel-IP-Country`/`x-vercel-ip-country` mapeado por LOCALE_BY_COUNTRY (BR->pt-BR, US->en-US, MX->es-419, FR->fr-FR) -> fallback `pt-BR`.
  - Cookie sync com perfil/PATCH preferences NAO esta nesta fase (F2.9).
- Compatibilidade next-intl:
  - Request header `X-NEXT-INTL-LOCALE` setado em todos os caminhos onde middleware atua. Isso alimenta `requestLocale` em frontend/i18n/request.ts (passo 1 da cadeia de resolucao da F2.4).
  - NAO usa `createMiddleware(routing)` do next-intl: substituicao manual evita reescrita ampla que quebraria rotas privadas.
- Confirmacao de zero redirect:
  - Texto do arquivo NAO contem `NextResponse.redirect`. Todas as transicoes sao `NextResponse.next()` ou `NextResponse.rewrite()`.
- Header geo auxiliar:
  - Quando o request traz `X-Vercel-IP-Country`/`x-vercel-ip-country`, o valor e ecoado no response header `X-Vercel-IP-Country`. Sem esse header no request, nada e adicionado.
- Matcher restrito:
  - `/ajuda`, `/privacy`, `/terms`, `/data-deletion`, `/welcome`, `/c/:path*`, `/en/:path*`, `/es/:path*`, `/fr/:path*`. `/api`, `/_next`, app routes privadas e assets nem entram no middleware. F2.5b finaliza allowlist se necessario.
- Testes rodados:
  - `cd frontend && npm run build` -> Compiled successfully, 14 paginas geradas + linha `ƒ Middleware  35 kB` apareceu (esperado: middleware.ts agora compilado).
  - `cd frontend && npm run lint` -> exit 0, 0 errors, 12 warnings preexistentes (F0.5). Sem regressao.
  - Asserts estruturais Python: middleware.ts contem `X-NEXT-INTL-LOCALE`, `NextResponse.rewrite`, todos os 5 paths publicos e todos os 7 mention-de-bypass; nao contem `NextResponse.redirect`. SHAs de request.ts/routing.ts/useEnabledLocales.ts inalterados em relacao a F2.4/F2.4c. messages/*.json continuam `{}`. Saida: `ALL F2.5 STRUCTURAL CHECKS PASS`.
- Gate: pronto para revisao do Codex.

## F2.5b - Matcher allowlist explicito
- Data concluida: 2026-04-20 23:00
- Arquivos alterados:
  - frontend/middleware.ts (apenas o bloco `export const config.matcher` foi reescrito; `isBypassPath` e toda a logica de bypass / `withLocaleHeader` / `copyGeoHeader` / resolucao de locale ficam intactas como cinto de seguranca)
  - reports/i18n_execution_log.md (esta entrada)
- Escopo respeitado:
  - Nao tocou frontend/app/*, components/*, request.ts, routing.ts, useEnabledLocales.ts, messages/*.json, package.json, package-lock.json, backend/*, migrations/*, shared/i18n/*.
  - SHAs antes/depois confirmam request.ts/routing.ts/useEnabledLocales.ts intactos vs F2.5.
- Matcher final explicito (24 entradas):
  - Sem prefixo (6): `/ajuda`, `/privacy`, `/terms`, `/data-deletion`, `/welcome`, `/c/:id`.
  - Prefixo `/en` (6): `/en/ajuda`, `/en/privacy`, `/en/terms`, `/en/data-deletion`, `/en/welcome`, `/en/c/:id`.
  - Prefixo `/es` (6): `/es/ajuda`, `/es/privacy`, `/es/terms`, `/es/data-deletion`, `/es/welcome`, `/es/c/:id`.
  - Prefixo `/fr` (6): `/fr/ajuda`, `/fr/privacy`, `/fr/terms`, `/fr/data-deletion`, `/fr/welcome`, `/fr/c/:id`.
- Removidos:
  - `/c/:path*`, `/en/:path*`, `/es/:path*`, `/fr/:path*` (matchers amplos da F2.5). Confirmado por grep negativo nos asserts.
- Confirmacao "fora do matcher" (consequencia):
  - OAuth (`/auth/*`, `/auth/callback`), chat (`/chat`, `/chat/*`), app routes (`/conta`, `/favoritos`, `/plano` e suas subarvores), API (`/api/*`), assets (`/_next/*`, imagens, fontes), `/c/<id>/opengraph-image` e a rota raiz `/` SEQUER entram no middleware. O matcher restrito garante isso no nivel do framework, e o `isBypassPath` continua como cinto de seguranca caso o matcher seja ampliado por engano em fase futura.
- Confirmacao zero redirect:
  - Texto do middleware NAO contem `NextResponse.redirect`. Apenas `NextResponse.next()` e `NextResponse.rewrite()`.
- Nota sobre contagem:
  - O prompt menciona "25 matchers"; a lista enumerada contem 6 base + (6 x 3 prefixados) = 24 entradas exatas. Implementacao seguiu fielmente os 24 itens listados.
- Testes rodados:
  - `cd frontend && npm run build` -> Compiled successfully, 14 paginas + `ƒ Middleware  35.2 kB`. Diferenca de tamanho desprezivel vs F2.5 (35 kB), esperado pelo matcher mais especifico.
  - `cd frontend && npm run lint` -> exit 0, 0 errors, 12 warnings preexistentes (F0.5). Sem regressao.
  - Asserts estruturais Python: 24 entradas explicitas presentes; 4 matchers amplos ausentes; `X-NEXT-INTL-LOCALE` e `NextResponse.rewrite` presentes; `NextResponse.redirect` ausente; tokens de bypass `/auth`, `/chat`, `/conta`, `/favoritos`, `/plano`, `/api`, `/_next`, `opengraph-image` presentes; SHAs de request.ts/routing.ts/useEnabledLocales.ts inalterados; messages/*.json continuam `{}`. Saida: `ALL F2.5b CHECKS PASS`.
- Gate: pronto para revisao do Codex.

## F2.6 - Formatters i18n (Intl.* nativo)
- Data concluida: 2026-04-20 23:25
- Arquivos alterados:
  - frontend/lib/i18n/formatters.ts (criado)
  - reports/i18n_execution_log.md (esta entrada)
- Escopo respeitado:
  - Nao usou `"use client"` (server-safe).
  - Nenhuma dependencia externa, somente `Intl.NumberFormat`, `Intl.DateTimeFormat`, `Intl.RelativeTimeFormat`.
  - SHAs antes/depois confirmam request.ts/routing.ts/useEnabledLocales.ts/middleware.ts intactos.
- Contrato das 4 funcoes:
  - `formatCurrency(value: number, locale?: string, currency?: string, options?: Intl.NumberFormatOptions): string` -> `Intl.NumberFormat` com `style: "currency"`. Currency: parametro `currency` (3 letras, normalizado upper) ou default por locale (`pt-BR -> BRL`, `en-US -> USD`, `es-419 -> MXN`, `fr-FR -> EUR`). `options` extras shallow-merge.
  - `formatDate(value: Date | string | number, locale?: string, options?: Intl.DateTimeFormatOptions): string` -> normaliza para `Date`; se `isNaN(date.getTime())` retorna `""` (UI nao quebra). Default `{ dateStyle: "medium" }`; quando `options` e passado, substitui o default.
  - `formatNumber(value: number, locale?: string, options?: Intl.NumberFormatOptions): string` -> `Intl.NumberFormat` puro com `options` opcional.
  - `formatRelativeTime(value: number, unit: Intl.RelativeTimeFormatUnit, locale?: string, options?: Intl.RelativeTimeFormatOptions): string` -> `Intl.RelativeTimeFormat`; default `{ numeric: "auto" }`; merge raso com `options`.
- Defaults por locale/currency:
  - pt-BR -> BRL
  - en-US -> USD
  - es-419 -> MXN
  - fr-FR -> EUR
  - Locale fora da whitelist (ex: `zh-CN`, `invalid`) cai em `pt-BR` via `resolveLocale`. Nunca lanca; helpers puros.
- Testes rodados:
  - `cd frontend && npm run build` -> Compiled successfully, 14 paginas + middleware. Tree-shaker mantem o arquivo fora do bundle ate ser importado por algum componente (Onda 4).
  - `cd frontend && npm run lint` -> exit 0, 0 errors, 12 warnings preexistentes (F0.5). Sem regressao.
  - Teste unitario em Node via `typescript.transpileModule` + `Module._compile` (sem criar arquivo permanente). 12 asserts cobriram:
    - `formatCurrency(1234.5, "en-US")` -> `"$1,234.50"` (contem `$`).
    - `formatCurrency(1234.5, "pt-BR")` -> `"R$ 1.234,50"` (contem `R$`).
    - `formatNumber(1234.5, "fr-FR")` -> `"1 234,5"` (nao vazio).
    - `formatDate("2026-04-20T00:00:00Z", "en-US")` -> `"Apr 19, 2026"` (nao vazio; data UTC com timezone local Windows).
    - `formatDate("not-a-date", "en-US")` -> `""` (caso invalido sem throw).
    - `formatRelativeTime(-1, "day", "en-US")` -> `"yesterday"` (numeric: "auto").
    - `formatCurrency(1234.5, "zh-CN")` -> `"R$ 1.234,50"` (locale invalido cai em pt-BR/BRL).
    - `formatNumber(1234.5, "invalid")` -> `"1.234,5"` (locale invalido cai em pt-BR sem throw).
    - `formatCurrency(1234.5, "es-419")` -> `"MXN 1,234.50"`.
    - `formatCurrency(1234.5, "fr-FR")` -> `"1 234,50 €"`.
    - `formatDate(Date(...), "pt-BR")` -> `"19 de abr. de 2026"`.
    - `formatDate(timestamp, "en-US")` -> nao vazio.
    - Saida: `ALL FORMATTER TESTS PASS`.
  - Asserts estruturais Python: arquivo existe; contem `Intl.NumberFormat`, `Intl.DateTimeFormat`, `Intl.RelativeTimeFormat`; exporta `formatCurrency`, `formatDate`, `formatNumber`, `formatRelativeTime`. SHAs de request.ts/routing.ts/useEnabledLocales.ts/middleware.ts inalterados. messages/*.json continuam `{}`. Saida: `ALL F2.6 STRUCTURAL CHECKS PASS`.
- Gate: pronto para revisao do Codex.

## F2.7 - Fallback chain helper (puro)
- Data concluida: 2026-04-20 23:45
- Arquivos alterados:
  - frontend/lib/i18n/fallbacks.ts (criado)
  - reports/i18n_execution_log.md (esta entrada)
- Escopo respeitado:
  - Sem `"use client"` (server-safe).
  - Sem dependencia externa.
  - SHAs antes/depois confirmam request.ts/routing.ts/useEnabledLocales.ts/formatters.ts/middleware.ts intactos.
- Contrato de `getFallbackChain`:
  - `export function getFallbackChain(locale?: string): SupportedLocale[]`
  - Retorna nova copia (`[...FALLBACK_CHAIN[locale]]`) para evitar mutacao acidental do array interno.
  - Locale invalido / ausente / vazio / null / fora da whitelist Tier 1 -> `["pt-BR"]`.
  - Cadeia canonica:
    - `pt-BR -> ["pt-BR"]`
    - `en-US -> ["en-US","pt-BR"]`
    - `es-419 -> ["es-419","en-US","pt-BR"]`
    - `fr-FR -> ["fr-FR","en-US","pt-BR"]`
  - Tambem exporta `SupportedLocale` (type), `defaultLocale` ("pt-BR") e `isSupportedLocale(value): value is SupportedLocale`.
- Resultado dos testes:
  - `cd frontend && npm run build` -> Compiled successfully, 14 paginas + middleware. Bundle inalterado (helper ainda nao consumido por componentes).
  - `cd frontend && npm run lint` -> exit 0, 0 errors, 12 warnings preexistentes (F0.5). Sem regressao.
  - Teste unitario via `typescript.transpileModule` + `Module._compile` (sem arquivo permanente). 13 asserts: pt-BR/en-US/es-419/fr-FR retornam as cadeias corretas; `de-DE`, `undefined`, `''`, `null` -> `["pt-BR"]`; mutar o array retornado nao afeta a proxima chamada (isolamento confirmado); `isSupportedLocale` valida pt-BR true, de-DE false, undefined false. Saida: `ALL FALLBACKS TESTS PASS`.
  - Asserts estruturais Python: arquivo existe; contem `getFallbackChain` e os 4 locales Tier 1; primeira linha de codigo (descontados comentarios e blanks) NAO e `"use client";`. SHAs de request.ts/routing.ts/useEnabledLocales.ts/formatters.ts/middleware.ts inalterados vs F2.6. messages/*.json continuam `{}`. Saida: `ALL F2.7 STRUCTURAL CHECKS PASS`.
- Gate: pronto para revisao do Codex.

## F2.8 - preflight local OK, aguardando autorizacao commit/push
- Data: 2026-04-20 23:55
- Status: PREFLIGHT VERDE. Sem commit, sem push. Sem deploy.
- Validacoes locais executadas:
  - `cd frontend && npm run build` -> Compiled successfully, 14 paginas + middleware (35.2 kB).
  - `cd frontend && npm run lint` -> exit 0, 0 errors, 12 warnings preexistentes (F0.5).
  - `python -m py_compile backend/app.py backend/db/models_auth.py backend/routes/auth.py backend/routes/chat.py backend/routes/config.py backend/utils/i18n_locale.py` -> `py_compile ALL OK`.
  - `create_app()` boota; rotas confirmadas: `/api/config/enabled-locales`, `/api/auth/me`, `/api/auth/me/preferences`, `/api/chat`, `/api/chat/stream`. Saida: `ALL ROUTES REGISTERED`.
  - Frontend textual: routing.ts (4 locales, `localePrefix: "as-needed"`); request.ts (4 cadeias FALLBACK_CHAIN); middleware.ts (24/24 matchers explicitos, sem `NextResponse.redirect`); useEnabledLocales.ts (SWR + `refreshInterval: 30000`); formatters.ts (4 exports); fallbacks.ts (`getFallbackChain`); messages/*.json (4 = `{}`). Saida: `ALL F2.8 FRONTEND TEXTUAL CHECKS OK`.
- Git audit: ver Lista A / Lista B na resposta da fase ao Murilo.
- Acao pendente: aguardar Murilo autorizar explicitamente:
  - criar/checkout `i18n/onda-2`
  - `git add` apenas Lista A
  - `git commit -m "i18n: bootstrap multilingual rollout through wave 2"`
  - `git push -u origin i18n/onda-2`
- Nada disso foi feito ainda. F2.8 NAO esta concluida final.

## F2.8 - Correcao do preflight: Lista A passa para 36 paths
- Data: 2026-04-21 00:10
- Motivo: revisao do Codex apontou (1) contagem incorreta no relatorio anterior (Lista A tem 34 paths originais, nao 35) e (2) falta de 2 docs canonicos:
  - reports/WINEGOD_MULTILINGUE_PLANO_EXECUCAO.md
  - reports/WINEGOD_MULTILINGUE_HANDOFF_OFICIAL.md
- Lista A final = 34 paths originais + 2 docs canonicos = 36 paths.
- Validacoes:
  - Script Python conferiu existencia em disco dos 36 paths -> `TODOS OS 36 PATHS DA LISTA A EXISTEM EM DISCO`.
  - `git status --short` para os 5 docs canonicos (`docs/I18N_README.md`, `reports/WINEGOD_MULTILINGUE_DECISIONS.md`, `reports/WINEGOD_MULTILINGUE_PLANO_EXECUCAO.md`, `reports/WINEGOD_MULTILINGUE_HANDOFF_OFICIAL.md`, `reports/i18n_execution_log.md`) confirma os 5 como `??` (untracked); precisam ser staged via `git add` quando autorizado.
  - Lista B continua intacta (sem alteracao): `.gitignore`, `CLAUDE.md`, `backend/config.py`, `backend/.env - Copia.example`, `backend/tests/test_search_pipeline_matrix.py`, prompts/* preexistentes, scripts/* preexistentes, `.claude/`, `.duo_orchestrator/`, etc. Plus os outros docs/ (`I18N_LIMITATIONS.md`, `ORQUESTRADOR_DUO_USO.md`, `ORQUESTRADOR_HANDOFF.md`, `RUNBOOK_I18N_DISASTER.md`, `RUNBOOK_I18N_ROLLBACK.md`, `TEMPLATE_PROJETO_REFINADO.md` -- Lista B porque sao preexistentes e a pasta `docs/` ainda nao foi adicionada ao git).
- NAO foi feito: `git add`, `git checkout -b`, `git commit`, `git push`, deploy. Nenhum codigo alterado.
- Comando de stage atualizado registrado na resposta da fase ao Murilo.
- Status: F2.8 segue aguardando autorizacao explicita de commit/push do Murilo.

## F2.8 - Commit + push da Onda 2 (autorizado)
- Data: 2026-04-21 00:25
- Branch: `i18n/onda-2` (criada a partir de main, working tree preservado).
- Commit: `efb02ac8` - "i18n: bootstrap multilingual rollout through wave 2".
- Auditoria pre-commit: 36/36 paths exatos da Lista A; ZERO vazamento da Lista B (audit Python `EXTRA: NENHUM`, `MISSING: NENHUM`).
- `git diff --cached --stat`: 36 files changed, 11972 insertions(+), 951 deletions(-).
- Push: `git push -u origin i18n/onda-2` -> branch nova criada no remote, tracking configurado.
- PR sugerido pelo GitHub: https://github.com/murilo-1234/winegod-app/pull/new/i18n/onda-2 (NAO aberto automaticamente; aguarda decisao do Murilo).
- Lista B continua sem alteracao no working tree (todos os arquivos sujos preexistentes seguem como `M`/`??` no status, fora deste commit).
- Render: NAO foi acionado deploy (REGRA 7 do CLAUDE.md). Migrations 015/016/017 aguardam deploy manual quando o Murilo decidir.
- Vercel: preview podera aparecer automaticamente se o repo estiver ligado a Vercel para PRs/branches; nao houve invencao de URL.
- Status F2.8: push feito, preview pendente (depende de Vercel auto-deploy de branch).

## FECHAMENTO TOTAL - 2026-04-23
- Founder autorizou `O1=A` e execucao continua ate fechar 4 locales.
- Worktree limpo usado para execucao: `C:\winegod-app-h4-closeout`.
- Commit final enviado para `main`: `9be95488672a5eb742fa337d4bb533c9f3903230` (`i18n: publish es/fr legal docs and enable 4 locales`).
- Codigo executado:
  - helper `frontend/lib/legal-routing.ts`
  - roteamento legal expandido em `age-verify`, `privacy`, `terms`, `data-deletion`, `legal/[country]/[lang]/[doc]`
  - 8 markdowns legais publicados em `shared/legal/DEFAULT/es-419/*` e `shared/legal/DEFAULT/fr-FR/*`
  - QA final: `legal-routing.spec.ts`, `legal-visual.spec.ts`, `playwright.share-disabled.config.ts`
- Validacoes locais:
  - `node tools/i18n_parity.mjs` -> OK, 335 leaves x4
  - `cd frontend && npm run lint` -> 0 errors, 10 warnings
  - `cd frontend && npm run build` -> verde
  - `cd frontend && npx playwright test` -> 74 passed
  - `cd frontend && npm run test:e2e:share-disabled` -> 4 passed
- Ativacao dinamica em producao:
  - `feature_flags.enabled_locales` atualizado de `["pt-BR","en-US"]` para `["pt-BR","en-US","es-419","fr-FR"]`
  - `https://winegod-app.onrender.com/api/config/enabled-locales` revalidado com 4 locales e source=`db`
  - `node tools/enabled_locales_check.mjs` -> OK (static == dynamic)
- Producao revalidada apos propagacao da Vercel:
  - `/es/privacy` -> `/legal/DEFAULT/es-419/privacy`
  - `/fr/privacy` -> `/legal/DEFAULT/fr-FR/privacy`
  - `/es/terms` -> `/legal/DEFAULT/es-419/terms`
  - `/fr/data-deletion` -> `/legal/DEFAULT/fr-FR/data-deletion`
  - `/legal/DEFAULT/es-419/cookies` -> 200
  - `/legal/DEFAULT/fr-FR/cookies` -> 200
- Decisoes finais confirmadas:
  - `O1=A`
  - `O2=B`
  - `O3=aceitar residual`
- Residual consciente mantido:
  - legal `es-419`/`fr-FR` publicado como traducao operacional sem revisao juridica local
  - OG `es-419`/`fr-FR` permanece em ingles
- Artefato de fechamento: `reports/WINEGOD_MULTILINGUE_FECHAMENTO_TOTAL_RESULTADO.md`
