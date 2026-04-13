# ANALISE DOS PROMPTS - EXECUCAO AUTONOMA

Data: 2026-04-07

Objetivo desta analise:
- verificar erros nos prompts principais ligados ao fluxo atual
- alinhar os prompts com o codigo real do repositorio
- garantir execucao direta, sem aprovacao previa, com teste, correcao e reteste

## RESUMO

Os erros mais graves estavam em 4 grupos:
1. Contradicao entre orquestracao e execucao
2. Comandos de terminal incompatíveis com PowerShell
3. Prompts de midia desalinhados com o contrato real do sistema
4. Falta de loop obrigatorio de testes e retestes

## PONTO A PONTO

### 1. Contradicao no prompt principal sobre quem executa

Arquivo:
- `prompts/PROMPT_CTO_WINEGOD_V2.md`

Problema:
- O texto dizia ao mesmo tempo que o CTO "NAO EXECUTA CODIGO" e que os prompts devem "executar tudo diretamente".

Por que e erro:
- Isso gera comportamento ambiguo. Um agente pode interpretar que deve apenas planejar, enquanto outro entende que deve implementar. Em fluxo autonomo, essa ambiguidade faz o prompt parar cedo ou pedir confirmacao.

Correcao aplicada:
- O prompt principal agora se declara explicitamente como prompt de orquestracao.
- Foi adicionado um mandato claro para que os prompts executores leiam o codigo, implementem, testem, corrijam e retestem.

### 2. Dependencia indevida de aprovacao humana durante a execucao tecnica

Arquivo:
- `prompts/PROMPT_CTO_WINEGOD_V2.md`

Problema:
- O texto dizia que o fundador aprova as decisoes tecnicas.

Por que e erro:
- Isso conflita com o requisito de execucao direta sem aprovacao antecipada.
- Aprovacao humana so faz sentido para acao externa, irreversivel ou fora do repo, como DNS, OAuth, Redis, compra, billing ou escolha estetica.

Correcao aplicada:
- O prompt agora limita escalacao humana a bloqueios externos e escolhas inevitavelmente humanas.

### 3. Comandos de execucao em sintaxe errada para o ambiente real

Arquivos:
- `prompts/PROMPT_CTO_WINEGOD_V2.md`

Problema:
- Os comandos usavam `$(cat arquivo)` para passar o prompt ao Claude.

Por que e erro:
- O ambiente do usuario e PowerShell. `$(cat ...)` e padrao shell POSIX/bash, nao o formato correto para PowerShell.
- Isso quebra o fluxo "copiar e colar e rodar".

Correcao aplicada:
- Os comandos foram atualizados para `-p (Get-Content prompts/ARQUIVO.md -Raw)`.

### 4. Prompt do avatar tratado como se fosse prompt executavel

Arquivos:
- `prompts/PROMPT_CTO_WINEGOD_V2.md`
- `prompts/PROMPT_AVATAR_BACO.md`

Problema:
- O bloco do avatar estava listado como algo para "rodar agora" no Claude Code.
- O proprio conteudo do arquivo do avatar e um guia para Midjourney, DALL-E, Flux, Leonardo, Ideogram e exige escolha humana.

Por que e erro:
- Claude Code local nao gera automaticamente esses resultados externos sem APIs e sem contas dessas plataformas.
- O fluxo depende de julgamento visual humano. Logo, nao e um prompt de implementacao automatica no repo.

Correcao aplicada:
- O prompt do avatar agora esta marcado explicitamente como MANUAL/EXTERNO.
- Foi removida a ideia de rodar esse arquivo com `claude -p`.

### 5. Ausencia de loop obrigatorio de testes, correcao e reteste

Arquivos:
- `prompts/PROMPT_CTO_WINEGOD_V2.md`
- `prompts/PROMPT_MEDIA_VIDEO_PDF.md`
- `prompts/PROMPT_MEDIA_FOTOS_BATCH.md`

Problema:
- Os prompts antigos pediam "como testar", mas nao obrigavam a rodar os testes antes de encerrar.
- Tambem nao exigiam correcao e novo teste em caso de falha.

Por que e erro:
- Sem isso, o agente pode editar o codigo e parar sem verificar nada.
- Isso viola o requisito de execucao completa e aumenta o risco de entregar alteracao quebrada.

Correcao aplicada:
- Todos os prompts relevantes agora mandam explicitamente:
  - ler o codigo atual
  - implementar
  - rodar checks
  - corrigir falhas
  - retestar ate passar ou ate existir bloqueio externo real

### 6. Prompt de media apontava para arquivos errados ou incompletos

Arquivos de prompt:
- `prompts/PROMPT_MEDIA_VIDEO_PDF.md`
- `prompts/PROMPT_MEDIA_FOTOS_BATCH.md`

Arquivos reais do sistema afetados:
- `frontend/lib/api.ts`
- `frontend/app/page.tsx`
- `backend/db/models_auth.py`

Problema:
- Os prompts de midia listavam apenas `ChatInput.tsx`, `chat.py`, `credits.py` e `media.py`.
- O codigo real mostra que o contrato de envio passa tambem por `frontend/lib/api.ts` e `frontend/app/page.tsx`.
- O modelo de credito real esta em `backend/db/models_auth.py`, porque o sistema hoje conta mensagens no `message_log`.

Por que e erro:
- Se o prompt proibe editar esses arquivos, a feature nao fecha ponta a ponta.
- O agente fica preso entre "nao posso editar" e "preciso editar para a feature funcionar".

Correcao aplicada:
- Os prompts de midia agora autorizam explicitamente esses arquivos.

### 7. Modelo de credito do sistema nao suportava as regras novas descritas no prompt

Arquivos de codigo:
- `backend/routes/credits.py`
- `backend/db/models_auth.py`

Problema:
- Os prompts antigos falavam em "video = 3 creditos", "PDF = 3", "multiplas fotos = 3".
- O sistema real so registra 1 linha por mensagem em `message_log` e soma quantidade de linhas.

Por que e erro:
- Mudar apenas `credits.py` nao resolve custo variavel.
- Sem alterar persistencia e contagem, o prompt promete uma regra que o sistema nao consegue cumprir.

Correcao aplicada:
- Os prompts agora explicam que e necessario ajustar `models_auth.py` e a forma de somar custo.

### 8. Testes propostos dependiam de arquivos inexistentes no repositorio

Arquivos:
- `prompts/PROMPT_MEDIA_VIDEO_PDF.md`
- `prompts/PROMPT_MEDIA_FOTOS_BATCH.md`

Problema:
- Os testes antigos referenciavam `test.pdf`, `test.mp4`, `test_label.jpg`, `test_screenshot.png`, `test1.jpg` etc.

Por que e erro:
- Esses arquivos nao existem no repo.
- O agente podia seguir o prompt corretamente e ainda assim falhar nos testes por causa de fixture inexistente.

Correcao aplicada:
- Os prompts passaram a exigir:
  - `python -m compileall .`
  - checks de import e rotas Flask
  - `npm run lint`
  - `npm run build`
  - smoke tests reais apenas se houver fixture local ou temporario seguro

### 9. Prompt de PDF subestimava a parte de OCR em PDF-imagem

Arquivo:
- `prompts/PROMPT_MEDIA_VIDEO_PDF.md`

Problema:
- O texto antigo dizia para usar `pdfplumber` e, se o PDF fosse imagem, "converter cada pagina em imagem" sem definir a dependencia que realmente renderiza pagina.

Por que e erro:
- `pdfplumber` extrai texto, mas renderizacao de pagina para OCR exige ferramenta adequada.
- Sem isso, o prompt fica incompleto e o agente precisa adivinhar a implementacao.

Correcao aplicada:
- O prompt passou a exigir dependencia especifica para renderizacao de paginas em imagem (`pypdfium2`) e deixou explicito que `pdfplumber` sozinho nao basta nesse fallback.

### 10. Falta de alinhamento entre prompt de media e fluxo real do chat

Arquivos de codigo:
- `backend/routes/chat.py`
- `frontend/lib/api.ts`
- `frontend/app/page.tsx`

Problema:
- O sistema atual so processa `image`.
- Os prompts de midia assumiam suporte imediato a `video`, `pdf` e `images`, mas sem descrever o ajuste completo do payload e do contrato entre frontend e backend.

Por que e erro:
- Sem alinhar o contrato inteiro, o backend pode aceitar uma coisa e o frontend continuar mandando outra.
- Em TypeScript isso ainda pode quebrar compilacao.

Correcao aplicada:
- Os prompts novos agora exigem ajuste ponta a ponta do contrato real.

### 11. Contradicao sobre commit nos prompts

Arquivo:
- `prompts/PROMPT_CTO_WINEGOD_V2.md`

Problema:
- O texto dizia ao mesmo tempo "NAO fazer git commit/push" e tambem trazia regra detalhada para cada chat commitar seus arquivos.

Por que e erro:
- Isso cria dupla interpretacao desnecessaria.
- Em execucao automatica, comandos de git precisam ser explicitamente opt-in.

Correcao aplicada:
- O prompt agora diz que commit/push so pode acontecer se o proprio prompt pedir explicitamente.

## ESTADO FINAL APOS CORRECAO

Prompts corrigidos:
- `prompts/PROMPT_CTO_WINEGOD_V2.md`
- `prompts/PROMPT_AVATAR_BACO.md`
- `prompts/PROMPT_MEDIA_VIDEO_PDF.md`
- `prompts/PROMPT_MEDIA_FOTOS_BATCH.md`

Melhorias efetivas:
- execucao sem aprovacao previa para trabalho tecnico dentro do repo
- comandos compativeis com PowerShell
- testes obrigatorios com reteste
- alinhamento com os arquivos reais do sistema
- separacao clara entre automacao tecnica e etapas humanas inevitaveis

## LIMITACOES QUE CONTINUAM EXISTINDO

1. Avatar continua exigindo escolha humana ou integracao real com APIs externas de imagem/video.
2. `ffmpeg` no Render continua sendo dependencia externa de deploy, nao algo resolvido so pelo prompt.
3. Features que dependem de painel externo, conta third-party ou credencial ausente continuam bloqueios reais e devem ser reportadas, nao ignoradas.
