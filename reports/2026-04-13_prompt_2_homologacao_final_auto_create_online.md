# PROMPT 2 — Homologacao Final Autonoma

Cole este segundo prompt SOMENTE depois que o PROMPT 1 terminar.

```text
Leia primeiro:
- C:\winegod-app\reports\2026-04-13_handoff_discovery_pipeline_master.md
- C:\winegod-app\reports\2026-04-13_prompt_execucao_final_auto_create_online.md
- C:\winegod-app\reports\2026-04-13_prompt_1_auditoria_auto_create_online.md

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
- ler os 3 docs de contexto
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
