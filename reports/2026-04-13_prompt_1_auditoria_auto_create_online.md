# PROMPT 1 — Auditoria, Ambiente e Decisao Executiva

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
  - expoe essa nota como `estimated` via `display.py`
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
