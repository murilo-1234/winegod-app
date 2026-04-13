# PROMPT EXECUTIVO — Finalizacao do Auto-Cadastro Online de Vinhos Novos

**Data**: 2026-04-13  
**Objetivo**: levar o novo fluxo online de auto-cadastro de vinhos novos a 100% de conclusao operacional, usando o handoff master como historico canonico.

---

## 1. Contexto resumido

O pipeline anterior ja foi homologado e aprovado:

- Fase 0B: PDF/video integrados ao resolver com wording correto
- Fase 1: texto colado/transcricao no mesmo pipeline de pre-resolve
- Fase 2: discovery/enrichment para unresolved
- Fase 3: discovery_log + persistencia basica
- homologacao final: `148/148` testes passaram, sem bloqueadores

Depois disso, abriu-se um escopo NOVO fora do plano original:

- quando um cliente manda foto, PDF, video ou texto com um vinho que NAO existe na base, o sistema deve conseguir:
  - classificar se e vinho / spirit / not_wine
  - completar dados essenciais via IA
  - inserir em `wines` online, na hora
  - responder ao usuario imediatamente com nota estimada, se houver
  - ou responder que ainda nao tem nota, sem inventar dado

Importante:

- isso deve ser SEPARADO do flush offline de scraping/lojas
- nao usar o pipeline de scraping como dependencia do fluxo online
- o pipeline batch Y2/Codex/Mistral continua existindo e validado, mas este escopo novo e "online/imediato"

---

## 2. Historico do que ja foi feito neste escopo novo

O prompt historico foi localizado em:

- `C:\winegod-app\prompts\PROMPT_CODEX_BASE_V2.md`
- `C:\winegod-app\scripts\mistral_classifier.py`
- `C:\winegod-app\prompts\HANDOFF_CADASTRO_AUTO_VINHOS_NOVOS.md`

Implementacao local ja feita no worktree:

- novo modulo:
  - `C:\winegod-app\backend\services\new_wines.py`
- integracoes:
  - `C:\winegod-app\backend\routes\chat.py`
  - `C:\winegod-app\backend\services\display.py`
  - `C:\winegod-app\backend\tools\media.py`
  - `C:\winegod-app\backend\tools\search.py`
  - `C:\winegod-app\backend\tools\compare.py`
  - `C:\winegod-app\backend\db\models_share.py`
- testes novos/ajustados:
  - `C:\winegod-app\backend\tests\test_new_wines_pipeline.py`
  - mocks nos testes de chat/text/discovery/discovery_log para isolar DB

Comportamento implementado:

1. `auto_create_unknowns(...)`
   - processa ate 2 itens nao resolvidos por request
   - usa prompt multi-item inspirado no fluxo Codex/Mistral
   - tenta Qwen primeiro
   - fallback Gemini texto puro
   - classifica `wine`, `spirit`, `not_wine`, `unknown`
   - so insere se:
     - `kind == "wine"`
     - `confidence >= 0.75`

2. Persistencia online
   - insere direto em `wines`
   - idempotencia por `hash_dedup`
   - `hash_dedup = md5(produtor_normalizado|nome_normalizado|safra)`
   - `nome` salvo no formato canonico do vinho, separado de `produtor`
   - NAO grava preco OCR/cardapio em `preco_min/preco_max`
   - marca `fontes = ["chat_auto_<canal>"]`

3. Nota imediata
   - quando a IA retorna `estimated_note` com confianca suficiente:
     - salva `nota_wcf`
     - salva `confianca_nota`
   - `services/display.py` foi estendido para expor isso como:
     - `display_note_type = "estimated"`
     - `display_note_source = "ai"`

4. Integracao nos canais
   - PDF
   - video
   - texto colado/transcricao
   - imagem
   - batch images

5. Guardrails
   - respeita `initial_seen_ids`
   - nao duplica `wine.id` ja resolvido antes no mesmo request
   - non-wine/spirit nao entram no banco

Validacao local ja feita:

- `python -m tests.test_new_wines_pipeline` -> `8 passed`
- `python -m tests.test_chat_pdf_video` -> `24 passed`
- `python -m tests.test_text_pipeline` -> `17 passed`
- `python -m tests.test_discovery_pipeline` -> `20 passed`
- `python -m tests.test_discovery_log` -> `19 passed`
- `python -m tests.test_pdf_pipeline` -> `22 passed`
- `python -m tests.test_item_status` -> `17/17`
- `python -m tests.test_resolver_pdf` -> `29 passed`

Checagens manuais ja feitas com monkeypatch:

- PDF auto-create -> nota estimada e sem unresolved remanescente
- video auto-create -> wording de video correto
- texto auto-create -> wording de texto correto
- imagem auto-create -> `photo_mode=True` preservado

---

## 3. O que AINDA falta para considerar 100% concluido

O fluxo novo esta forte no nivel de codigo local + testes offline, mas NAO esta 100% fechado operacionalmente.

Faltam os blocos abaixo:

1. Homologacao de escrita REAL no banco alvo
   - provar que o insert em `wines` funciona no ambiente configurado
   - confirmar schema real, constraints e trigger reais
   - confirmar leitura posterior pelo proprio app

2. Verificacao de ambiente real das IAs
   - confirmar `DASHSCOPE_API_KEY`
   - confirmar Gemini fallback, se necessario
   - confirmar parse real do JSON de resposta

3. Validacao ponta a ponta controlada
   - subir um vinho sinteticamente novo ou um caso real controlado
   - deixar o fluxo cair em `auto_create_unknowns`
   - confirmar:
     - classificacao correta
     - insert correto
     - resposta correta ao usuario

4. Auditoria de poluicao da base
   - garantir que `not_wine` e `spirit` nao entram
   - garantir que vinho de baixa confianca nao entra
   - deixar trilha clara dos criados por `chat_auto_*`

5. Fechamento documental
   - atualizar handoff master com os resultados reais
   - registrar se ficou:
     - aprovado sem ressalvas
     - aprovado com riscos residuais
     - ou bloqueado

---

## 4. Definicao de pronto para este escopo

Considere o job 100% concluido somente se TODOS os pontos abaixo forem verdade:

1. Um vinho novo vindo de foto/PDF/video/texto:
   - passa por OCR
   - falha no pre-resolve
   - falha no discovery
   - entra no auto-create online
   - e inserido em `wines`
   - volta para o contexto final da mesma resposta

2. Se houver nota estimada confiavel:
   - a resposta final usa nota `estimated`

3. Se nao houver nota:
   - a resposta final admite que ainda nao ha nota

4. Se o item nao for vinho ou for spirit:
   - NAO entra em `wines`

5. O fluxo NAO depende do pipeline offline de scraping/lojas

6. O fluxo NAO duplica `wine.id`

7. O fluxo NAO polui `preco_min/preco_max` com preco OCR/cardapio

8. O handoff master fica atualizado com a validacao real final

---

## 5. Plano executivo para a nova aba

### Etapa A — Auditoria factual do estado atual

Objetivo:

- confirmar que o worktree atual bate com o que o handoff diz
- identificar se existe algum gap entre a implementacao local e a expectativa de produto

Tarefas:

1. Ler:
   - `C:\winegod-app\reports\2026-04-13_handoff_discovery_pipeline_master.md`
   - `C:\winegod-app\reports\2026-04-13_prompt_execucao_final_auto_create_online.md`

2. Inspecionar:
   - `backend/services/new_wines.py`
   - `backend/routes/chat.py`
   - `backend/services/display.py`
   - `backend/tools/media.py`
   - `backend/tools/search.py`
   - `backend/tools/compare.py`
   - `backend/db/models_share.py`
   - `backend/tests/test_new_wines_pipeline.py`

3. Revalidar as suites relevantes

Resultado esperado:

- inventario fiel do que esta implementado
- lista objetiva do que ainda falta para 100%

### Etapa B — Validacao de schema/ambiente real

Objetivo:

- descobrir se o banco configurado e seguro para homologacao controlada
- descobrir se o schema real suporta o novo fluxo

Tarefas:

1. Inspecionar a conexao ativa do backend
2. Confirmar se o alvo e:
   - local/dev/homolog
   - ou banco compartilhado/producao
3. Confirmar no banco:
   - tabela `wines`
   - colunas usadas pelo novo fluxo
   - indice/constraint de `hash_dedup`
   - trigger de score relevante

Guardrail critico:

- se o banco atual for claramente compartilhado/producao, NAO inserir dado sintetico sem reportar antes

Resultado esperado:

- classificacao objetiva do risco do ambiente
- schema real validado

### Etapa C — Homologacao ponta a ponta controlada

Objetivo:

- provar o fluxo online real, sem depender apenas de monkeypatch

Tarefas:

1. Escolher 1 caso controlado de vinho novo
2. Rodar o caminho real do app ate cair em `auto_create_unknowns`
3. Confirmar:
   - insert em `wines`
   - `nome` e `produtor` corretos
   - `hash_dedup` coerente
   - `fontes` com `chat_auto_<canal>`
   - `nota_wcf`/`confianca_nota` quando houver nota estimada
   - resposta final do chat coerente

4. Rodar pelo menos:
   - 1 canal textual (`text` ou `pdf`)
   - 1 canal visual (`image` ou `video`)

Resultado esperado:

- prova factual de que o fluxo online funciona com insert real

### Etapa D — Correcoes minimas se aparecer bloqueador real

Objetivo:

- corrigir apenas o minimo necessario

Tarefas:

- se aparecer bug de schema, insert, duplicata, display ou resposta final:
  - corrigir o minimo
  - adicionar/ajustar teste necessario
  - rerodar suites relevantes

Resultado esperado:

- fluxo estabilizado sem expandir escopo

### Etapa E — Fechamento final

Objetivo:

- deixar o escopo pronto para commit/homologacao final

Tarefas:

1. Atualizar o handoff master
2. Registrar:
   - o que foi validado de verdade
   - o que ainda e risco residual
3. Produzir parecer final:
   - aprovado
   - aprovado com riscos
   - bloqueado

---

## 6. Como usar os 2 prompts

Sequencia obrigatoria:

1. Executar o PROMPT 1
2. Deixar a nova aba decidir e agir sozinha
3. Se o PROMPT 1 concluir que o ambiente e seguro para homologacao real, executar o PROMPT 2
4. Se o PROMPT 1 concluir que o ambiente NAO e seguro, a propria nova aba deve resolver esse bloqueio dentro do escopo dela:
   - identificando alternativa segura
   - ou preparando homologacao controlada
   - ou deixando parecer final bloqueado com justificativa tecnica concreta

Importante:

- a nova aba deve ser 100% autonoma
- ela NAO deve assumir que havera uma terceira pessoa decidindo por ela
- ela NAO deve depender de retornar a este chat para continuar

---

## 7. PROMPT 1 — auditoria, ambiente e decisao executiva

Cole exatamente isto na nova aba:

```text
Leia primeiro:
- C:\winegod-app\reports\2026-04-13_handoff_discovery_pipeline_master.md
- C:\winegod-app\reports\2026-04-13_prompt_execucao_final_auto_create_online.md

Contexto:
- O pipeline discovery antigo ja foi homologado e aprovado.
- Existe agora um escopo NOVO fora do plano original: auto-cadastro online imediato de vinhos novos.
- O objetivo e fechar esse escopo ate 100%, sem depender do fluxo offline de scraping/lojas.

Historico ja implementado:
- Prompt historico encontrado em:
  - `C:\winegod-app\prompts\PROMPT_CODEX_BASE_V2.md`
  - `C:\winegod-app\scripts\mistral_classifier.py`
  - `C:\winegod-app\prompts\HANDOFF_CADASTRO_AUTO_VINHOS_NOVOS.md`
- Codigo novo ja existe em:
  - `C:\winegod-app\backend\services\new_wines.py`
- Integracoes ja feitas em:
  - `C:\winegod-app\backend\routes\chat.py`
  - `C:\winegod-app\backend\services\display.py`
  - `C:\winegod-app\backend\tools\media.py`
  - `C:\winegod-app\backend\tools\search.py`
  - `C:\winegod-app\backend\tools\compare.py`
  - `C:\winegod-app\backend\db\models_share.py`
- Suite nova ja existe:
  - `C:\winegod-app\backend\tests\test_new_wines_pipeline.py`

Estado atual esperado:
- O fluxo online:
  - classifica `wine` / `spirit` / `not_wine`
  - usa Qwen primeiro e Gemini fallback
  - auto-cadastra ate 2 itens por request em `wines`
  - nao grava preco OCR em `preco_min/preco_max`
  - salva `nota_wcf` + `confianca_nota` quando ha nota estimada confiavel
  - expõe essa nota como `estimated` via `display.py`
  - evita duplicata de `wine.id` no mesmo request
- Validacao local previa:
  - `python -m tests.test_new_wines_pipeline` -> 8 passed
  - `python -m tests.test_chat_pdf_video` -> 24 passed
  - `python -m tests.test_text_pipeline` -> 17 passed
  - `python -m tests.test_discovery_pipeline` -> 20 passed
  - `python -m tests.test_discovery_log` -> 19 passed
  - `python -m tests.test_pdf_pipeline` -> 22 passed
  - `python -m tests.test_item_status` -> 17/17
  - `python -m tests.test_resolver_pdf` -> 29 passed
- Tambem houve validacao manual com monkeypatch em PDF/video/text/image.

Seu objetivo AGORA:
- levar esse fluxo online a 100% de conclusao operacional
- com foco em HOMOLOGACAO REAL do insert e da resposta final
- sem reabrir o escopo do pipeline antigo
- sem depender do flush offline de scraping/lojas

Definicao de pronto:
1. vinho novo vindo de foto/PDF/video/texto entra no auto-create online depois de falhar em pre-resolve + discovery
2. e inserido em `wines`
3. volta na mesma resposta como confirmado
4. se tiver nota estimada confiavel, responde com nota `estimated`
5. se nao tiver nota, responde honestamente sem nota
6. non-wine/spirit NAO entram na base
7. nao duplica `wine.id`
8. nao polui `preco_min/preco_max`

Escopo:
- Pode alterar:
  - `C:\winegod-app\backend\services\new_wines.py`
  - `C:\winegod-app\backend\routes\chat.py`
  - `C:\winegod-app\backend\services\display.py`
  - `C:\winegod-app\backend\tools\media.py`
  - `C:\winegod-app\backend\tools\search.py`
  - `C:\winegod-app\backend\tools\compare.py`
  - `C:\winegod-app\backend\db\models_share.py`
  - `C:\winegod-app\backend\tests\test_new_wines_pipeline.py`
  - ajustes minimos em testes relacionados se forem estritamente necessarios
  - `C:\winegod-app\reports\2026-04-13_handoff_discovery_pipeline_master.md`
- Nao toque em:
  - frontend
  - pipeline Y2 offline
  - scraping de lojas
  - migrations novas, a menos que descubra bloqueio real de schema
- Nao reverta mudancas nao relacionadas do worktree

Plano executivo que voce deve seguir:

ETAPA A — Auditoria factual
- conferir se o codigo atual bate com o handoff
- conferir os diffs e os testes existentes

ETAPA B — Schema e ambiente real
- descobrir para qual DB o backend esta apontando
- validar schema real da tabela `wines` e constraints usadas
- se o DB atual for compartilhado/producao, NAO fazer insert sintetico sem reportar o bloqueio

ETAPA C — Homologacao controlada
- se o ambiente for seguro para isso, fazer um teste real ponta a ponta com insert
- confirmar o comportamento por pelo menos:
  - 1 canal textual (`text` ou `pdf`)
  - 1 canal visual (`image` ou `video`)
- confirmar:
  - insert real em `wines`
  - `nome` e `produtor` corretos
  - `hash_dedup` coerente
  - `fontes` com `chat_auto_<canal>`
  - `nota_wcf` e `confianca_nota` quando houver
  - resposta final coerente ao usuario

ETAPA D — Fix minimo se houver bug real
- corrigir so o minimo necessario
- adicionar/ajustar teste
- rerodar suites relevantes

ETAPA E — Fechamento
- atualizar o handoff master com o resultado factual
- dar parecer final: aprovado / aprovado com riscos / bloqueado

Validacao obrigatoria minima:
- `python -m tests.test_new_wines_pipeline`
- `python -m tests.test_chat_pdf_video`
- `python -m tests.test_text_pipeline`
- `python -m tests.test_discovery_pipeline`
- `python -m tests.test_discovery_log`
- `python -m tests.test_pdf_pipeline`
- `python -m tests.test_item_status`
- `python -m tests.test_resolver_pdf`

Retorne exatamente:
1. Arquivos alterados
2. O que ja estava feito ao chegar
3. O que faltava para 100%
4. Mudancas feitas
5. Comandos executados
6. Resultado dos testes
7. Resultado da validacao real de DB/ambiente
8. Parecer final: aprovado, aprovado com riscos, ou bloqueado
```

---

## 8. PROMPT 2 — homologacao real/autonoma ate fechamento

Cole este segundo prompt SOMENTE depois que o PROMPT 1 terminar.

Se o PROMPT 1 tiver liberado ambiente seguro, este PROMPT 2 deve executar a homologacao real.

Se o PROMPT 1 tiver concluido que o ambiente nao e seguro, este PROMPT 2 deve agir de forma autonoma para FECHAR o job do melhor jeito possivel:

- ou encontrar alternativa segura dentro do proprio ambiente
- ou preparar uma homologacao controlada sem contaminar producao
- ou concluir bloqueado com evidencias concretas, se nao houver caminho seguro

Cole exatamente isto:

```text
Leia primeiro:
- C:\winegod-app\reports\2026-04-13_handoff_discovery_pipeline_master.md
- C:\winegod-app\reports\2026-04-13_prompt_execucao_final_auto_create_online.md

Voce esta assumindo a fase FINAL do job.

Premissas:
- O fluxo online de auto-cadastro ja esta implementado no worktree.
- Seu papel agora e FECHAR o job ate o maximo grau de conclusao seguro e factual.
- Voce NAO podera depender de retorno para outra pessoa decidir por voce.
- Se o ambiente for seguro, faca a homologacao real.
- Se o ambiente nao for seguro, resolva isso sozinho do jeito correto:
  - encontrando alternativa segura
  - ou preparando uma forma de validacao controlada
  - ou encerrando como bloqueado com justificativa tecnica irrefutavel

Objetivo:
- sair deste job com um destes 3 estados finais:
  1. aprovado sem ressalvas
  2. aprovado com riscos residuais claros
  3. bloqueado com evidencias concretas

O que ja deve ter sido feito antes de voce comecar:
- auditoria do codigo
- validacao das suites locais
- avaliacao preliminar do ambiente/DB

Sua responsabilidade agora:

1. Reconfirmar rapidamente o estado do codigo e do ambiente
2. Decidir sozinho o caminho operacional correto
3. Executar a homologacao real se existir caminho seguro
4. Corrigir o minimo necessario se aparecer bug real
5. Atualizar o handoff master com o resultado final
6. Encerrar com parecer definitivo

Regras duras:
- Nao expanda escopo para frontend, pipeline offline Y2 ou scraping de lojas
- Nao reverta mudancas nao relacionadas do worktree
- Nao faca insert sintetico em ambiente claramente compartilhado/producao sem criar uma estrategia tecnicamente segura
- Nao esconda risco operacional
- Nao marque como aprovado se o insert real ou a validacao equivalente nao foi comprovado de forma defensavel

Ordem de execucao obrigatoria:

ETAPA 1 — Reconhecimento rapido
- ler os 2 docs de contexto
- revisar:
  - `backend/services/new_wines.py`
  - `backend/routes/chat.py`
  - `backend/services/display.py`
  - `backend/tests/test_new_wines_pipeline.py`

ETAPA 2 — Decisao do ambiente
- verificar para qual DB o backend aponta
- verificar se o ambiente atual e:
  - seguro para teste real
  - inseguro mas contornavel
  - inseguro e bloqueante

ETAPA 3 — Acao autonoma conforme o cenario

CENARIO A: ambiente seguro
- executar homologacao real ponta a ponta
- validar pelo menos:
  - 1 canal textual (`text` ou `pdf`)
  - 1 canal visual (`image` ou `video`)
- confirmar:
  - insert real em `wines`
  - leitura posterior do vinho pelo proprio app
  - `nome`, `produtor`, `hash_dedup`, `fontes`
  - `nota_wcf` e `confianca_nota` quando existirem
  - resposta final coerente ao usuario

CENARIO B: ambiente inseguro mas contornavel
- encontrar alternativa segura sem depender de outra pessoa
- exemplos aceitaveis:
  - usar banco local/dev configurado no proprio repo
  - usar fixture controlada
  - criar validacao real em ambiente isolado ja disponivel
- depois executar homologacao o mais real possivel

CENARIO C: ambiente inseguro e bloqueante
- NAO force o teste
- documente exatamente:
  - por que o ambiente e inseguro
  - por que nao existe caminho seguro disponivel neste contexto
  - o que falta operacionalmente para fechar 100%
- nesse caso, encerrar como bloqueado com evidencias

ETAPA 4 — Fix minimo se necessario
- se aparecer bug real de insert, display, duplicata, parse, schema ou resposta final:
  - corrigir o minimo
  - adicionar/ajustar teste
  - rerodar as suites relevantes

ETAPA 5 — Fechamento factual
- atualizar:
  - `C:\winegod-app\reports\2026-04-13_handoff_discovery_pipeline_master.md`
- registrar:
  - o que foi comprovado
  - o que ficou como risco residual
  - se o job esta aprovado ou bloqueado

Validacao minima obrigatoria antes de encerrar:
- `python -m tests.test_new_wines_pipeline`
- `python -m tests.test_chat_pdf_video`
- `python -m tests.test_text_pipeline`
- `python -m tests.test_discovery_pipeline`
- `python -m tests.test_discovery_log`
- `python -m tests.test_pdf_pipeline`
- `python -m tests.test_item_status`
- `python -m tests.test_resolver_pdf`

Retorne exatamente:
1. Cenario encontrado: seguro, inseguro mas contornavel, ou inseguro bloqueante
2. Arquivos alterados
3. O que foi comprovado de forma real
4. Mudancas feitas
5. Comandos executados
6. Resultado dos testes
7. Resultado da homologacao real ou da tentativa controlada
8. Atualizacao feita no handoff master
9. Parecer final: aprovado sem ressalvas, aprovado com riscos, ou bloqueado
```

---

## 9. Regra operacional

Se a nova aba fizer qualquer descobrimento relevante, ela deve atualizar:

- `C:\winegod-app\reports\2026-04-13_handoff_discovery_pipeline_master.md`

Especialmente quando:

- encontrar bloqueio real
- concluir homologacao real
- decidir que ainda falta algum gap para os 100%
- encerrar o chat com contexto importante
