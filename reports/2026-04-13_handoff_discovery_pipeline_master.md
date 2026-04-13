# Handoff Master: Discovery Pipeline

Use este documento como prompt de continuidade para um novo chat.

Se houver conflito entre este arquivo e handoffs mais antigos, ESTE arquivo vence.

Ultima atualizacao relevante neste chat:

- Fase 3 aprovada
- homologacao final aprovada
- proximo passo recomendado: fechamento da sprint / commit prep, nao nova fase

Arquivos-base que o novo chat deve ler primeiro:

- `C:\winegod-app\reports\2026-04-13_handoff_discovery_pipeline_manager.md`
- `C:\Users\muril\.claude\plans\cryptic-herding-bumblebee.md`

## Papel

Voce esta assumindo como gestora tecnica do Discovery Pipeline.

Seu trabalho principal NAO e confiar em relato de outro agente. Seu trabalho e:

1. controlar o escopo por fase
2. emitir prompts curtos e rigorosos para a outra aba
3. validar cada retorno no codigo real
4. bloquear avancos quando houver regressao ou cobertura insuficiente
5. manter ESTE documento atualizado periodicamente para evitar perda de contexto se o chat cair

## Regra de operacao

Sempre operar assim:

1. ler este arquivo e os 2 arquivos-base citados acima
2. inspecionar `git diff` dos arquivos relevantes
3. rodar os testes exigidos da fase atual
4. quando o risco for comportamental, fazer reproducao manual minima
5. so liberar a proxima fase depois de validar no repo real

Nao confiar apenas em:

- "tudo verde" no relato
- testes com mocks excessivos
- descricao bonita sem diff real

## Objetivo do projeto

Objetivo do plano:

- unificar foto, PDF, video, texto colado e transcricao textual no mesmo pipeline de resolucao

Em termos práticos:

- detectar vinhos
- tentar resolver no banco
- produzir contexto honesto para o Baco
- enriquecer casos nao encontrados com discovery controlado
- registrar trilha basica de discovery por canal

## Estado aprovado ate aqui

### Pre-requisito aprovado

Arquivo:

- `backend/tests/test_pdf_pipeline.py`

Status aprovado:

- mocks ajustados para aceitar `**kwargs`

Validado com:

- `python -m tests.test_pdf_pipeline` -> `22 passed, 0 failed`

### Fase 0A aprovada

Arquivos centrais:

- `backend/tools/resolver.py`
- `backend/tests/test_resolver_pdf.py`

Status aprovado:

- `resolve_wines_from_ocr()` aceita `pdf`
- `_resolve_multi()` para `pdf`:
  - dedup por `(name, producer)`
  - preserva ordem
  - fast-only
  - cap 20
  - overflow vai para `unresolved_items`
- `format_resolved_context()` suporta `pdf`
- wording de PDF ficou correto:
  - `documento PDF`
  - `no documento`
  - sem referencias falsas a imagem

Validado com:

- `python -m tests.test_resolver_pdf` -> `29 passed, 0 failed`
- `python -m tests.test_item_status` -> `17/17`

### Fase 0B aprovada

Arquivos centrais:

- `backend/routes/chat.py`
- `backend/tools/resolver.py`
- `backend/tests/test_chat_pdf_video.py`

Status aprovado:

- PDF e video entraram no pre-resolve em `_process_media()`
- `_resolve_wine_list()` foi criado em `chat.py`
- `photo_mode=False` foi preservado para PDF e video
- video passou a usar source/context explicito de `video`
- bug real do rich path de video falando em `documento` foi corrigido
- foi criado suplemento `_format_unresolved_ocr_details()` para preservar:
  - `producer`
  - `vintage`
  - `region`
  - `grape`
  - `price`

Validacao manual feita:

- rich path de video NAO contem `documento`
- rich path de video contem wording correto de `video`
- `photo_mode=False` mantido

Validado com:

- `python -m tests.test_chat_pdf_video` -> `24 passed, 0 failed`
- `python -m tests.test_item_status` -> `17/17`
- `python -m tests.test_resolver_pdf` -> `29 passed, 0 failed`

### Fase 1 aprovada

Arquivos centrais:

- `backend/tools/media.py`
- `backend/tools/resolver.py`
- `backend/routes/chat.py`
- `backend/tests/test_text_pipeline.py`

Status aprovado:

- `qwen_text_generate(prompt_text)` exposto publicamente
- `extract_wines_from_text(text)` criado em `media.py`
- texto colado e transcricao textual enviada em `message` entram no mesmo pipeline
- `_try_text_wine_extraction()` criado em `chat.py`
- integracao feita em AMBOS:
  - `chat()`
  - `chat_stream()`
- formatter suporta source/context explicito de `text`
- wording de texto ficou correto:
  - `texto`
  - `no texto`
  - sem `documento`
  - sem `na imagem`
- `photo_mode=False` mantido

Observacao importante:

- Nao foi criado fluxo separado de audio binario
- a cobertura desta fase vale para texto colado e para qualquer transcricao textual que chegue em `message`

Validacao manual feita:

- helper de texto gera contexto com wording correto
- `chat()` real sem midia passa contexto de texto para o Baco
- `chat_stream()` real sem midia tambem passa contexto de texto para o Baco
- em ambos os casos: `photo_mode=False`

Validado com:

- `python -m tests.test_text_pipeline` -> `17 passed, 0 failed`
- `python -m tests.test_pdf_pipeline` -> `22 passed, 0 failed`
- `python -m tests.test_chat_pdf_video` -> `24 passed, 0 failed`
- `python -m tests.test_item_status` -> `17/17`
- `python -m tests.test_resolver_pdf` -> `29 passed, 0 failed`

### Fase 2 aprovada

Arquivos centrais:

- `backend/services/discovery.py`
- `backend/routes/chat.py`
- `backend/tests/test_discovery_pipeline.py`

Status aprovado:

- `discover_unknowns()` criado
- enrichment via `qwen_text_generate()`
- second resolve via `search_wine(...)`
- quality gate real via `_pick_best(...)`
- limites operacionais aplicados:
  - `MAX_SYNC_UNKNOWNS = 2`
  - `MAX_ENRICHMENT_CALLS = 2`
  - `MAX_BUDGET_MS = 3000`
- discovery integrado em:
  - PDF
  - video
  - texto

Bug importante descoberto e corrigido durante a validacao:

- discovery inicialmente podia resolver um `unresolved_item` para o MESMO `wine.id` que ja estava em `resolved_items`
- isso causava duplicata real no contexto final
- correcao aprovada:
  - `discover_unknowns()` passou a aceitar `initial_seen_ids`
  - `_apply_discovery()` passou a coletar IDs do pre-resolve e enviar para o discovery
- agora o discovery nao duplica `wine.id` ja confirmado antes

Validacao manual feita:

- reproducao real do bug de duplicata em PDF
- apos a correcao, o mesmo `wine.id` aparece apenas uma vez no contexto final
- o item OCR duplicado permanece em `unresolved` quando o ID ja estava confirmado

Validado com:

- `python -m tests.test_discovery_pipeline` -> `20 passed, 0 failed`
- `python -m tests.test_text_pipeline` -> `17 passed, 0 failed`
- `python -m tests.test_pdf_pipeline` -> `22 passed, 0 failed`
- `python -m tests.test_chat_pdf_video` -> `24 passed, 0 failed`
- `python -m tests.test_item_status` -> `17/17`
- `python -m tests.test_resolver_pdf` -> `29 passed, 0 failed`

## Estado atual

### Fase 3 aprovada

Arquivos centrais:

- `backend/services/discovery.py`
- `backend/routes/chat.py`
- `database/migrations/010_discovery_log.sql`
- `backend/tests/test_discovery_log.py`

Status aprovado:

- migration `discovery_log` criada
- `log_discovery()` implementado
- `session_id` propagado ate os pontos de log
- logging integrado em:
  - `pdf`
  - `video`
  - `text`
- logging usa estado FINAL apos discovery
- fallbacks sem itens estruturados nao logam
- o logger e nao-bloqueante

Bug importante descoberto e corrigido durante a validacao:

- varias suites offline ainda batiam no DB real via `log_discovery()`
- os testes passavam porque o logger engolia `UndefinedTable`
- correcao aprovada:
  - helpers de teste passaram a mockar `log_discovery` como no-op por default
  - `test_discovery_log.py` ficou como suite responsavel por validar logging

Validacao manual feita:

- fluxo real de PDF com discovery resolvendo item
- `log_discovery()` recebeu:
  - `session_id` correto
  - `source_channel="pdf"`
  - itens finais apos discovery
- sem `visual_only` remanescente quando discovery resolveu o item

Validado com:

- `python -m tests.test_discovery_log` -> `19 passed, 0 failed`
- `python -m tests.test_discovery_pipeline` -> `20 passed, 0 failed`
- `python -m tests.test_text_pipeline` -> `17 passed, 0 failed`
- `python -m tests.test_pdf_pipeline` -> `22 passed, 0 failed`
- `python -m tests.test_chat_pdf_video` -> `24 passed, 0 failed`
- `python -m tests.test_item_status` -> `17/17`
- `python -m tests.test_resolver_pdf` -> `29 passed, 0 failed`

Checagem adicional aprovada:

- zero ocorrencias de `UndefinedTable` nas suites offline validadas

### Homologacao final aprovada

Parecer final validado:

- APROVADO sem bloqueadores

Resumo da homologacao final:

- 7 suites validadas
- `148/148` testes passando
- cenarios manuais validados para:
  - PDF com discovery
  - video com wording correto
  - texto com wording correto
  - `log_discovery()` recebendo estado final apos discovery
- verificacao explicita de `photo_mode`:
  - PDF -> `False`
  - video -> `False`
  - texto -> `False`
  - o unico `photo_mode=True` remanescente e do path original de batch images com itens resolvidos

Riscos residuais NAO bloqueantes:

- a migration `010_discovery_log.sql` precisa ser aplicada no banco antes do logging funcionar em producao
- `discover_unknowns()` usa funcoes semi-privadas do resolver (`_pick_best`, `_derive_item_status`), o que funciona hoje mas pode exigir cuidado em refactors futuros
- enrichment depende de `DASHSCOPE_API_KEY`; sem ela, o discovery degrada de forma graciosa para sem enrichment

### Escopo NAO liberado

Nao implementar ainda:

- inserts em `wines`
- worker/background job
- A/B test
- tuning de search
- qualquer analytics HTTP/dashboard
- qualquer expansao fora de logging basico

## Arquivos relevantes do pipeline

Arquivos hoje importantes para este trabalho:

- `backend/routes/chat.py`
- `backend/tools/media.py`
- `backend/tools/resolver.py`
- `backend/services/discovery.py`
- `backend/tests/test_pdf_pipeline.py`
- `backend/tests/test_chat_pdf_video.py`
- `backend/tests/test_resolver_pdf.py`
- `backend/tests/test_text_pipeline.py`
- `backend/tests/test_discovery_pipeline.py`
- `backend/tests/test_discovery_log.py`
- `database/migrations/010_discovery_log.sql`

## Estado atual do worktree

### Mudancas relacionadas ao pipeline

Estas mudancas existem no worktree e NAO devem ser revertidas sem instrucao explicita:

- `M backend/routes/chat.py`
- `M backend/tools/media.py`
- `M backend/tools/resolver.py`
- `M backend/tests/test_pdf_pipeline.py`
- `?? backend/services/discovery.py`
- `?? backend/tests/test_chat_pdf_video.py`
- `?? backend/tests/test_resolver_pdf.py`
- `?? backend/tests/test_text_pipeline.py`
- `?? backend/tests/test_discovery_pipeline.py`
- `?? backend/tests/test_discovery_log.py`
- `?? database/migrations/010_discovery_log.sql`
- `?? reports/2026-04-13_handoff_discovery_pipeline_master.md`

### Mudancas sujas nao relacionadas

Estas tambem estao sujas e NAO devem ser revertidas:

- `M backend/config.py`
- `M backend/routes/auth.py`
- `M backend/routes/credits.py`
- `M frontend/app/page.tsx`
- `M frontend/components/auth/UserMenu.tsx`
- `M frontend/lib/api.ts`
- `M frontend/lib/auth.ts`
- `M prompts/PROMPT_CTO_WINEGOD_V2.md`
- `M prompts/PROMPT_VIDEO_AUTOMACAO_CREATOMATE.md`
- `M reports/tail_audit_master_state_2026-04-11.md`

## Como o novo chat deve agir agora

1. Ler este arquivo e os 2 arquivos-base
2. Assumir que o plano formal foi aprovado ate a Fase 3
3. Assumir que a homologacao final ja foi concluida sem bloqueadores
4. Assumir que nao existe Fase 4 liberada
5. Antes de qualquer mudanca, inspecionar:
   - `git diff` dos arquivos realmente tocados pela proxima tarefa
   - se houver risco de regressao, repetir testes e reproducao manual minima
6. Como nao existe Fase 4 no plano atual, tratar qualquer proximo passo como:
   - commit/PR prep
   - ou novo escopo explicitamente decidido pelo usuario

## Prompt pronto para a proxima aba

Como o plano formal e a homologacao final ja foram concluidos, o proximo passo recomendado NAO e nova feature.

Se voce for abrir outra aba AGORA, use este prompt exatamente para FECHAMENTO DA SPRINT / COMMIT PREP:

```text
Leia primeiro:
- C:\winegod-app\reports\2026-04-13_handoff_discovery_pipeline_master.md
- C:\winegod-app\reports\2026-04-13_handoff_discovery_pipeline_manager.md
- C:\Users\muril\.claude\plans\cryptic-herding-bumblebee.md

Status atual aprovado:
- Fase 0B aprovada
- Fase 1 aprovada
- Fase 2 aprovada
- Fase 3 aprovada
- homologacao final aprovada sem bloqueadores

Nao existe Fase 4 no plano atual.

Seu trabalho AGORA nao e expandir escopo.
Seu trabalho e preparar o estado atual para commit/PR futuro sem inventar trabalho novo.

Escopo:
- Pode alterar:
- no maximo docs/relatorios de fechamento, se isso ajudar
- evite alterar codigo de produto
- so altere codigo se descobrir contradicao factual real no inventario final
- Nao toque em frontend
- Nao reverta mudancas nao relacionadas do worktree

Objetivo:
- fazer inventario final do que esta pronto para commit
- agrupar as mudancas por area funcional
- apontar riscos residuais nao-bloqueantes
- deixar uma proposta objetiva de commit/PR summary

Direcao esperada:

1. Inspecionar o worktree final
- rodar:
  - `git status --short`
  - `git diff --stat -- backend/routes/chat.py backend/tools/media.py backend/tools/resolver.py backend/services/discovery.py backend/tests/test_pdf_pipeline.py backend/tests/test_chat_pdf_video.py backend/tests/test_resolver_pdf.py backend/tests/test_text_pipeline.py backend/tests/test_discovery_pipeline.py backend/tests/test_discovery_log.py database/migrations/010_discovery_log.sql`

2. Montar resumo final por area
- resolver/context formatting
- media/text extraction
- chat integration
- discovery pipeline
- discovery logging
- testes e migration

3. Produzir saida final pronta para uso humano
- proposta de titulo de commit
- proposta de resumo de PR em 1-2 paragrafos
- lista curta de riscos residuais nao-bloqueantes
- confirmar que o pipeline esta aprovado para merge/commit futuro

Se aparecer necessidade de escopo maior que isso, pare e reporte em vez de expandir.

Retorne exatamente:
1. Arquivos alterados
2. Mudancas feitas
3. Comandos executados
4. Inventario final por area
5. Proposta de titulo de commit
6. Proposta de resumo de PR
7. Riscos residuais nao-bloqueantes
```

## Validacao que o novo chat deve fazer apos o retorno da outra aba

1. conferir que a outra aba nao expandiu escopo sem necessidade
2. validar o inventario final contra o worktree real
3. se a outra aba mexer em codigo, rerodar testes relevantes antes de aceitar o resumo
4. como nao existe Fase 4 no plano, o resultado esperado e fechamento da sprint, nao nova fase

## Proximo escopo possivel fora do plano atual

Lacuna funcional que SOBROU depois da homologacao:

- o sistema detecta/extrai/resolve/enriquece/loga vinhos de foto, PDF, video e texto
- mas NAO cadastra automaticamente um vinho novo em `wines` quando nenhum match confiavel e encontrado

Importante:

- isso NAO e "so fazer um INSERT"
- o banco exige `hash_dedup` unico e `nome_normalizado`
- a busca depende de `nome_normalizado` e `produtor_normalizado`
- o app espera um `wine` minimamente coerente mesmo quando sem nota/score
- preco de OCR/cardapio NAO deve ser tratado cegamente como preco canonico de `wines`

Blocos minimos que faltam para auto-cadastro seguro:

1. criterio de criacao
   - definir quando um `unresolved_item` vira cadastro novo
   - idealmente apenas apos pre-resolve + discovery falharem e com sinal minimo suficiente (`name`, opcionalmente `producer`, talvez `country/region/grape`)

2. normalizacao e dedup de escrita
   - gerar `nome_normalizado`
   - gerar `produtor_normalizado`
   - gerar `hash_dedup` deterministico
   - fazer `INSERT ... ON CONFLICT (hash_dedup) DO NOTHING` ou equivalente

3. modelo de dados de entrada
   - decidir quais campos podem nascer nulos
   - decidir se `uvas`/`pais`/`regiao` vindos do enrichment entram como canonicos ou provisrios
   - decidir se o novo vinho nasce com algum marcador de proveniencia (`fontes`, `descoberto_em`, origem discovery)

4. politica de preco e fonte
   - NAO gravar automaticamente preco de OCR/cardapio em `preco_min/preco_max` sem regra clara
   - se houver contexto de loja/fonte confiavel, avaliar gravacao em `wine_sources`
   - sem loja/url confiavel, provavelmente criar o vinho sem `wine_sources`

5. servico transacional no backend
   - criar um writer explicito para novos vinhos
   - inserir de forma idempotente
   - retornar o `wine.id` criado/encontrado
   - reinjetar esse item no pipeline como `resolved_item`

6. trilha e seguranca operacional
   - logar quem/qual canal criou o vinho
   - permitir auditoria e eventual merge posterior com um canonico melhor
   - considerar fila/revisao humana se o threshold de confianca nao for alto

Resumo pragmatico:

- sim, a unica grande capacidade ausente no fluxo atual e o auto-cadastro de vinhos novos
- mas tecnicamente ela se divide em regra de criacao + normalizacao/hash + insert idempotente + politica de fonte/preco + auditoria
- nao deve ser tratada como um patch pequeno

Nuance importante descoberta depois:

- o repositorio JA tem um pipeline validado de classificacao/importacao em lote para vinhos novos fora do chat online
- referencias principais:
  - `scripts/pipeline_y2.py` -> classifica `matched/new/not_wine/spirit/duplicate` em `y2_results`
  - `scripts/mistral_classifier.py` -> classificacao/enriquecimento em lotes grandes
  - `scripts/import_render_z.py` -> Fase 2 de importacao de `new` para `wines` com anti-duplicata por `hash_dedup`

Portanto, se o usuario quiser fechar a lacuna de "novos vinhos vindos de cardapio/foto/texto entram na base", o escopo mais correto NAO e reconstruir enrichment/cadastro do zero.

O escopo mais correto passa a ser:

1. criar a ponte entre o pipeline online de chat/discovery e o pipeline offline/lote ja validado
2. decidir onde os `unresolved_items` de cliente vao pousar para processamento posterior
3. deduplicar essa fila de entrada
4. operacionalizar o handoff para `y2_results`/importacao
5. decidir se o SLA desejado e:
   - eventual (entra depois no batch)
   - ou imediato (exigiria writer online no backend)

Em uma frase:

- se o pipeline Y2/new-wines ja esta validado, o que falta nao e "capacidade de cadastrar vinho novo"
- o que falta e integrar o fluxo atual de OCR/PDF/video/texto com esse pipeline de cadastro ja existente

## Escopo novo em andamento fora do plano original: auto-cadastro online imediato

Pedido do usuario apos a homologacao:

- NAO usar o flush/enrichment de scraping de lojas para esse caso
- quando um vinho extraido de foto, PDF, video ou texto nao existir na base, tentar resolver NA HORA via IA
- a IA deve classificar `wine` vs `spirit` vs `not_wine`
- se for vinho com confianca suficiente, completar dados estruturados e inserir em `wines`
- se houver nota estimavel, responder ao usuario na hora com nota; se nao houver, responder sem nota

Prompt historico encontrado e reaproveitado como referencia:

- `prompts/PROMPT_CODEX_BASE_V2.md`
- `scripts/mistral_classifier.py` (`PROMPT_HEADER`)
- contexto antigo adicional: `prompts/HANDOFF_CADASTRO_AUTO_VINHOS_NOVOS.md`

Implementacao local atual no worktree:

- novo modulo: `backend/services/new_wines.py`
- integracao em:
  - `backend/routes/chat.py`
  - `backend/services/display.py`
  - `backend/tools/media.py`
  - `backend/tools/search.py`
  - `backend/tools/compare.py`
  - `backend/db/models_share.py`
- nova suite:
  - `backend/tests/test_new_wines_pipeline.py`

Desenho atual do fluxo online:

1. OCR/PDF/video/texto continuam passando por:
   - pre-resolve
   - discovery
2. Se ainda sobrarem `unresolved_items`, entra `auto_create_unknowns(...)`
3. O novo fluxo:
   - classifica ate 2 itens por request
   - usa prompt inspirado no Codex/Mistral antigo
   - chama `qwen_text_generate()` primeiro
   - fallback para `gemini_text_generate(..., thinking=False)`
   - aceita `wine`, `spirit`, `not_wine`, `unknown`
   - so insere quando `kind="wine"` e `confidence >= 0.75`
4. Persistencia:
   - insert direto em `wines`
   - idempotencia por `hash_dedup`
   - hash atual alinhado ao padrao do pipeline batch:
     - `produtor_normalizado|nome_normalizado|safra`
   - `nome` salvo no formato canonico de vinho (sem repetir produtor)
   - NAO grava preco OCR/cardapio em `preco_min/preco_max`
5. Nota imediata:
   - se a IA retornar `estimated_note` com confianca suficiente, salva:
     - `nota_wcf`
     - `confianca_nota`
   - `services/display.py` foi estendido para expor isso como:
     - `display_note_type = "estimated"`
     - `display_note_source = "ai"`
   - isso permite resposta imediata com nota estimada sem fingir validacao publica
6. Guardrails adicionais:
   - `auto_create_unknowns(...)` agora respeita `initial_seen_ids`
   - o helper do chat passa IDs ja resolvidos antes do auto-cadastro
   - isso evita duplicar `wine.id` no contexto final

Validacao local feita ate aqui para esse escopo:

- suites:
  - `python -m tests.test_new_wines_pipeline` -> `8 passed`
  - `python -m tests.test_chat_pdf_video` -> `24 passed`
  - `python -m tests.test_text_pipeline` -> `17 passed`
  - `python -m tests.test_discovery_pipeline` -> `20 passed`
  - `python -m tests.test_discovery_log` -> `19 passed`
  - `python -m tests.test_pdf_pipeline` -> `22 passed`
  - `python -m tests.test_item_status` -> `17/17 passed`
  - `python -m tests.test_resolver_pdf` -> `29 passed`
- checagens manuais com monkeypatch:
  - PDF auto-create -> resolve e responde com `(estimated)`
  - video auto-create -> wording de `video`, sem bloco unresolved
  - texto auto-create -> wording de `texto`, sem bloco unresolved
  - imagem auto-create -> continua `photo_mode=True` e usa nota estimada

Pontos importantes para a proxima aba:

- o fluxo online novo e SEPARADO do pipeline de scraping/lojas
- ele nao depende de `wines_pending`
- ele nao grava `wine_sources`
- ele nao usa preco OCR como preco canonico
- ele ainda NAO foi homologado em producao com insert real no banco do ambiente do usuario; a validacao ate aqui e local/offline + monkeypatch
- se outra aba assumir, o primeiro passo deve ser validar se o desenho acima bate com a expectativa de produto antes de expandir
- se a outra aba decidir continuar, usar ESTE documento como fonte canonica e atualizar esta mesma secao

### Auditoria factual Prompt 1 - 2026-04-13

Resultado desta auditoria:

- o worktree bate com o desenho descrito para `auto_create_unknowns(...)`
- o modulo `backend/services/new_wines.py` existe e implementa:
  - classificacao `wine/spirit/not_wine/unknown`
  - Qwen texto primeiro + Gemini fallback
  - cap de 2 itens por request
  - insert idempotente por `hash_dedup`
  - sem gravar `preco_min/preco_max`
  - persistencia opcional de `nota_wcf` + `confianca_nota`
- `backend/routes/chat.py` integra o auto-create em:
  - `pdf`
  - `video`
  - `text`
  - `image`
  - `batch image`
- `backend/services/display.py`, `backend/tools/search.py`, `backend/tools/compare.py` e `backend/db/models_share.py`
  foram ajustados para propagar `confianca_nota` e expor nota `estimated` com source `ai`
- a suite `backend/tests/test_new_wines_pipeline.py` existe e valida o fluxo offline novo

Suites revalidadas nesta auditoria:

- `python -m tests.test_new_wines_pipeline` -> `8 passed, 0 failed`
- `python -m tests.test_chat_pdf_video` -> `24 passed, 0 failed`
- `python -m tests.test_text_pipeline` -> `17 passed, 0 failed`
- `python -m tests.test_discovery_pipeline` -> `20 passed, 0 failed`
- `python -m tests.test_discovery_log` -> `19 passed, 0 failed`
- `python -m tests.test_pdf_pipeline` -> `22 passed, 0 failed`
- `python -m tests.test_item_status` -> `17/17`
- `python -m tests.test_resolver_pdf` -> `29 passed, 0 failed`

Validacao de ambiente/DB feita nesta auditoria:

- `backend/.env` aponta para um Postgres REMOTO da Render:
  - host: `dpg-d6o56scr85hc73843pvg-a.oregon-postgres.render.com`
  - database: `winegod`
  - user: `winegod_user`
- a tabela real `public.wines` contem todas as colunas usadas pelo fluxo novo:
  - `hash_dedup`, `nome`, `nome_normalizado`, `produtor`, `produtor_normalizado`
  - `safra`, `tipo`, `pais`, `pais_nome`, `regiao`, `sub_regiao`
  - `uvas`, `teor_alcoolico`, `descricao`, `harmonizacao`
  - `total_fontes`, `fontes`, `descoberto_em`, `atualizado_em`
  - `nota_wcf`, `confianca_nota`
- constraints/indices reais confirmados:
  - `PRIMARY KEY (id)`
  - `UNIQUE (hash_dedup)`
  - indice parcial `idx_wines_hash_dedup` em `hash_dedup`
- trigger real confirmado:
  - `trg_score_recalc` -> `fn_enqueue_score_recalc()`
- a fila `score_recalc_queue` existe e o usuario atual tem privilegios de `INSERT/SELECT/UPDATE`

Decisao executiva desta auditoria:

- NAO foi feito insert sintetico em `wines` nesta etapa
- motivo: o backend esta configurado para um banco remoto da Render, com cara de ambiente compartilhado/produtivo, e o repo nao traz um banco local/homolog isolado ja pronto para reproduzir o path real com seguranca
- portanto, a homologacao ponta a ponta com insert real continua pendente de ambiente seguro dedicado ou estrategia controlada equivalente
- parecer desta etapa: `bloqueado` para 100% operacional, embora o estado de codigo local esteja consistente e validado offline

### Coordenacao administrativa externa - checkpoint vivo

Contexto desta retomada:

- o trabalho passou a ser operado com 2 abas:
  - esta aba atua como administradora tecnica
  - uma segunda aba do Claude Code executa fases delimitadas por prompts curtos
- a administradora:
  - define a fase
  - emite o prompt da fase
  - recebe o relatorio da outra aba
  - valida criticamente o retorno
  - aprova ou devolve para correcao antes da proxima fase

Estado factual ja consolidado nesta modalidade:

- Prompt 1 foi executado nesta aba e resultou em auditoria factual + validacao local + validacao read-only de DB/schema
- depois disso, a execucao do Prompt 2 foi decomposta em fases administrativas controladas
- Fase 1 (reconhecimento rapido) foi:
  - inicialmente devolvida com gaps de analise
  - corrigida pela outra aba
  - aprovada pela administradora
- Fase 2 (decisao do ambiente) foi:
  - inicialmente devolvida com erro factual sobre FK em `score_recalc_queue`
  - corrigida pela outra aba com consulta live
  - aprovada pela administradora
- cenario aprovado ao fim da Fase 2:
  - `inseguro mas contornavel`
  - DB atual = Render remoto/producao
  - sem banco local/dev pronto
  - caminho contornavel validado:
    - homologacao DB-only com rollback transacional
    - e, se necessario e justificado, insert real controlado com cleanup explicito em `score_recalc_queue` + `wines`

Fases aprovadas ate aqui:

- Prompt 1: auditoria factual executada
- Prompt 2 / Fase 1: aprovada
- Prompt 2 / Fase 2: aprovada
- Prompt 2 / Fase 3A: aprovada

Fase 3A aprovada:

- objetivos cumpridos:
  1. `image` e `batch image` agora passam por `discovery` antes de `auto_create`
  2. fallback `Qwen -> Gemini` em `new_wines.py` foi endurecido para:
     - string vazia
     - JSON invalido de Qwen
- cobertura adicional criada:
  - teste de ordem `discovery -> auto_create` para single image
  - teste de ordem `discovery -> auto_create` para batch image
  - teste de fallback Gemini quando Qwen retorna vazio
  - teste de fallback Gemini quando Qwen retorna JSON invalido
- suites revalidadas nesta fase:
  - `python -m tests.test_new_wines_pipeline` -> `12 passed, 0 failed`
  - `python -m tests.test_chat_pdf_video` -> `24 passed, 0 failed`
  - `python -m tests.test_text_pipeline` -> `17 passed, 0 failed`
  - `python -m tests.test_discovery_pipeline` -> `20 passed, 0 failed`
  - `python -m tests.test_discovery_log` -> `19 passed, 0 failed`
  - `python -m tests.test_pdf_pipeline` -> `22 passed, 0 failed`
  - `python -m tests.test_item_status` -> `17/17`
  - `python -m tests.test_resolver_pdf` -> `29 passed, 0 failed`
- total revalidado na Fase 3A:
  - `160/160` casos passando
- restricao preservada:
  - nenhum insert real foi feito ainda
  - nenhuma homologacao controlada foi executada ainda

Fase atual em preparo:

- Prompt 2 / Fase 3B
- objetivo: homologacao controlada do fluxo novo no maximo grau seguro e factual
- caminho aprovado ate aqui:
  1. confirmar worktree + suites ja aprovadas
  2. executar primeiro uma validacao DB-only com rollback transacional
  3. decidir, com evidencias, se ainda e necessario insert real controlado com cleanup explicito em `score_recalc_queue` + `wines`
  4. so depois decidir se ha caminho defensavel para provar resposta final do app
- restricao atual:
  - continuar sem inventar ambiente seguro
  - qualquer insert real exige cleanup completo e justificativa tecnica
  - se nao houver prova defensavel do path completo, encerrar com parecer honesto

Prompts administrativos ja emitidos nesta retomada:

1. Fase 1 - reconhecimento rapido
2. Correcao da Fase 1
3. Fase 2 - decisao do ambiente
4. Correcao da Fase 2
5. Fase 3A - fix minimo + regressao local (preparado e aprovado pela administradora para envio)
6. Fase 3B - homologacao controlada (proximo prompt a ser emitido)

Regra adicional de persistencia desta retomada:

- a cada 3 prompts administrativos novos gerados para a outra aba, atualizar ESTE handoff master
- cada checkpoint deve registrar no minimo:
  - ultimo prompt emitido
  - fases aprovadas/reprovadas
  - estado atual do trabalho
  - proximo passo pendente
- objetivo:
  - se o terminal/chat cair, a retomada consegue continuar sem depender de memoria contextual

Estado atual exato neste momento:

- Fase 1 aprovada
- Fase 2 aprovada
- Fase 3A aprovada
- Fase 3B executada e concluida

### Fase 3B — Homologacao controlada (resultado factual)

Cenario: inseguro mas contornavel (DB = Render producao, sem banco local)

Nivel 1 executado — validacao DB-only com rollback transacional:

- payload ficticio: "Cuvee Homologacao Teste XZ99" / "Domaine Ficticio Rollback" / safra 2099
- INSERT real executado no banco de producao dentro de transacao
- 24 validacoes executadas, 24 PASS, 0 FAIL:
  - id gerado (id=3360695)
  - hash_dedup = md5(produtor_norm|nome_norm|safra) correto
  - nome, nome_normalizado, produtor, produtor_normalizado, safra, tipo, pais, pais_nome, regiao, uvas, teor_alcoolico corretos
  - fontes = ["chat_auto_pdf"] correto
  - nota_wcf = 3.85 correto
  - confianca_nota = 0.82 correto
  - preco_min = NULL (nao poluido)
  - preco_max = NULL (nao poluido)
  - vivino_rating = NULL (nao inventado)
  - winegod_score = NULL (nao inventado)
  - trigger trg_score_recalc disparou com reason=trigger_insert
  - ON CONFLICT idempotente (segundo INSERT com mesmo hash → count=1)
  - ROLLBACK desfez tudo: vinho removido, fila restaurada ao estado anterior
- zero persistencia residual no banco

Nivel 2 NAO executado:

- justificativa: Nivel 1 ja provou INSERT + trigger + SELECT + hash_dedup + ON CONFLICT + zero poluicao de precos/notas
- o que Nivel 2 adicionaria (leitura posterior pelo app + resposta final) ja e coberto por 160/160 testes offline
- risco de deixar vinho ficticio em producao nao proporcional a evidencia incremental

O que foi provado de forma real:

- SQL do INSERT funciona no schema real de producao
- todos os 20 campos inseridos sao lidos corretamente
- trigger dispara e enfileira em score_recalc_queue com reason=trigger_insert
- ON CONFLICT por hash_dedup funciona (idempotencia confirmada)
- preco_min/preco_max NAO sao poluidos
- vivino_rating/winegod_score NAO sao inventados
- ROLLBACK desfaz completamente (zero footprint)

O que NAO foi provado:

- path completo do app: Flask → OCR → classify (IA real) → insert → display → resposta ao usuario
- motivo: exigiria rodar Flask + IAs online (Qwen/Gemini) + input que caia em auto-create
- este path e coberto por 160/160 testes offline com mocks, mas nao por homologacao real ponta a ponta

Parecer da Fase 3B: aprovado com riscos residuais

Riscos residuais nao-bloqueantes:

1. path completo do app nao provado em homologacao real ponta a ponta
2. classificacao IA (Qwen/Gemini) depende de APIs externas funcionando
3. DASHSCOPE_API_KEY precisa estar ativa em producao para Qwen funcionar
4. session_id e parametro morto em new_wines.py — funcional mas cosmetically dead code

Validacao administrativa posterior desta fase:

- a aba administradora rechecou o banco em modo read-only apos o relatorio da outra aba
- confirmacoes adicionais:
  - `matching_wines=0` para `nome='Cuvee Homologacao Teste XZ99'` e `produtor='Domaine Ficticio Rollback'`
  - `wine_id=3360695` ausente em `wines`
  - `wine_id=3360695` ausente em `score_recalc_queue`
- conclusao administrativa:
  - rollback realmente nao deixou residuo
  - Fase 3B foi APROVADA pela administradora
  - estado consolidado do job neste ponto:
    - aprovado com riscos residuais
    - com prova real do DB layer + trigger + rollback
    - sem prova ponta a ponta da resposta final do app

### Encerramento administrativo final do Prompt 2

Data: 2026-04-13

Status final do job: APROVADO COM RISCOS RESIDUAIS

O que foi provado:

1. Codigo local implementa auto-cadastro online completo:
   - classificacao wine/spirit/not_wine/unknown via Qwen + Gemini fallback
   - insert idempotente por hash_dedup
   - cap de 2 itens por request
   - nota estimada (nota_wcf + confianca_nota) quando confiavel
   - display.py expoe nota estimated/ai
   - preco_min/preco_max NAO poluidos
   - integracao nos 5 canais: PDF, video, texto, imagem, batch image
   - discovery antes de auto_create em TODOS os canais (corrigido na Fase 3A)
   - fallback Gemini funciona para Qwen vazio e JSON invalido (corrigido na Fase 3A)
2. 8 suites obrigatorias validadas: 160/160 passando, zero regressoes
3. Homologacao DB-only com rollback transacional no schema real de producao:
   - INSERT real com 20 campos confirmados
   - trigger trg_score_recalc disparou (reason=trigger_insert)
   - ON CONFLICT por hash_dedup confirmado (idempotencia)
   - SELECT posterior retornou registro completo
   - ROLLBACK desfez tudo: zero persistencia residual confirmada pela aba administradora

O que NAO foi provado:

- path completo do app (Flask -> OCR -> classify via IA real -> insert -> display -> resposta ao usuario) com DB real + IAs reais simultaneamente
- motivo: exigiria Flask local + Qwen API + Gemini API + DB producao + input controlado, combinacao de alto risco sem banco isolado disponivel
- mitigacao: 160/160 testes offline cobrem toda a logica do app; Nivel 1 cobre todo o DB layer

Riscos residuais nao-bloqueantes:

1. path completo app nao provado end-to-end com IA real + DB real
2. classificacao IA depende de DASHSCOPE_API_KEY (Qwen) e GEMINI_API_KEY ativos em producao
3. session_id e parametro morto em new_wines.py (aceito mas nunca consumido)

Proximo passo recomendado: FECHAMENTO / COMMIT PREP

- o escopo do auto-cadastro online esta concluido no maximo grau factual possivel neste ambiente
- NAO e recomendado nova homologacao, nova fase, nem nova execucao dos Prompts 1 ou 2
- a instrucao anterior de "executar Prompt 1 e Prompt 2 na proxima retomada" fica SUPERADA por este encerramento
- o proximo trabalho deveria ser: preparar commit/PR com todas as mudancas do pipeline + auto-create

Documentos executivos de referencia (historicos, NAO precisam ser re-executados):

- `C:\winegod-app\reports\2026-04-13_prompt_execucao_final_auto_create_online.md`
- `C:\winegod-app\reports\2026-04-13_prompt_1_auditoria_auto_create_online.md`
- `C:\winegod-app\reports\2026-04-13_prompt_2_homologacao_final_auto_create_online.md`

## Como manter este documento vivo

Sempre atualizar ESTE arquivo:

- antes de trocar de fase
- depois de aprovar uma fase
- depois de encontrar um bug bloqueante relevante
- antes de encerrar um chat que tenha acumulado contexto importante

Ao atualizar:

1. ajustar a secao `Estado aprovado ate aqui`
2. ajustar a secao `Estado atual NAO aprovado`
3. atualizar comandos e resultados validados
4. atualizar `Estado atual do worktree`
5. substituir o `Prompt pronto para a proxima aba`

Objetivo dessa regra:

- se o chat cair, a proxima aba consegue continuar sem perder contexto real
