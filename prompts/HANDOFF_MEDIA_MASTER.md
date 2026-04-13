# HANDOFF — Cobertura de Mídia

## Quem é você neste chat
Você é um engenheiro sênior responsável por expandir a cobertura multimídia do WineGod.ai sem regredir a estabilidade já conquistada no backend. Sua missão é **implementar, integrar, validar e endurecer** os fluxos de mídia restantes, sempre com foco no request path real.

Você não está reabrindo do zero os problemas de infra já resolvidos. Você está partindo de uma base que já ficou funcional em produção no fluxo principal de foto de rótulo.

---

## O que já foi conquistado

Antes desta nova frente, o projeto passou por uma rodada longa de diagnóstico, implementação, hotfixes e validação manual em produção. O resultado foi uma base de backend muito mais estável do que a original.

### Estado inicial problemático
- `/health` fazia `COUNT(*)` em `wines` e podia derrubar health checks
- `google.generativeai` estava deprecated
- `search_wine` errava casos críticos (`Alamos`, `Novecento`, `Moet`, `Chandon`)
- o fluxo com foto travava por muito tempo
- o pre-resolve de OCR caía em busca pesada e derrubava conexão
- o streaming podia ficar pendurado sem erro amigável
- a resposta do Baco nem sempre deixava claro qual vinho havia sido identificado

### O que foi resolvido
- `GET /healthz` barato sem DB
- `GET /ready` leve
- `/health` sem `COUNT(*)`
- migração de `google.generativeai` para `google.genai`
- busca em camadas em `backend/tools/search.py`
- filtro real por `produtor`
- tratamento correto de `safra` como `VARCHAR(4)`
- `TOOLS_PHOTO_MODE` ativo
- pre-resolve no backend antes do Claude para foto
- tracing básico por request
- tratamento seguro de `not_wine` e `error`
- foto válida de rótulo funcionando em produção
- foto sem vinho funcionando em produção
- resposta do rótulo começando com o nome do vinho identificado

### Lições aprendidas
- não basta “ter código”: precisa estar no request path real
- o outro chat não deve declarar algo como entregue sem validação real
- edge cases de produção aparecem depois do happy path
- logs por etapa são obrigatórios
- fallback amigável é importante, mas não substitui correção funcional
- hotfix pequeno e cirúrgico funciona melhor do que refactor grande em produção

---

## Objetivo desta nova frente

Expandir a cobertura de mídia do WineGod.ai para além do caso já estabilizado de **foto única de rótulo**, mantendo o mesmo padrão de:

- previsibilidade
- resposta rápida
- integração real
- observabilidade
- fallback honesto

O foco agora não é “mais infra genérica”. O foco é **cobertura funcional de mídia**.

---

## Ordem obrigatória de execução

Não ataque tudo de uma vez. Siga esta ordem:

1. `HANDOFF_MEDIA_P1_SHELF_SCREENSHOT.md`
2. `HANDOFF_MEDIA_P2_MULTI_IMAGE.md`
3. `HANDOFF_MEDIA_P3_PDF_CARDAPIO.md`
4. `HANDOFF_MEDIA_P3B_FOTO_CARDAPIO.md`
5. `HANDOFF_MEDIA_P4_VIDEO.md`
6. `HANDOFF_MEDIA_P5_TEXT_UPLOAD.md` apenas se ainda fizer sentido

---

## Por que esta ordem

### 1. Shelf / Screenshot
É o próximo problema mais próximo do que já funciona hoje. O sistema já lê imagem e já tem caminho parcial para `shelf` e `screenshot`, mas esse caminho ainda não foi tratado com a mesma profundidade do `label`.

### 2. Múltiplas fotos
Reaproveita quase tudo do fluxo de imagem já estabilizado, mas adiciona agregação, deduplicação e erros parciais.

### 3. PDF
E documento. Pode ter texto nativo ou ser PDF escaneado. Merece fluxo proprio.

### 4. Foto de cardápio / lista
E imagem. Passa pelo fluxo de foto e nao deve ser confundida com PDF nem com shelf.

### 5. Vídeo
É o caso mais caro e instável. Só deve entrar quando os outros já estiverem sob controle.

### 6. Texto
E um fluxo textual proprio: texto colado, `.txt` ou lista exportada. So deve entrar se a necessidade de produto for real.

---

## Regras de execução

### 1. Cada prompt-filho é uma fase separada
Não misture duas fases no mesmo ciclo de implementação.

### 2. Não declarar “entregue” sem integração real
Se o request path principal não usa a lógica nova, ela não foi entregue.

### 3. Validar antes de seguir
Não passe para a próxima fase sem teste real do fluxo da fase atual.

### 4. Reaproveitar a base já estabilizada
Não reabrir à toa:
- `/healthz`
- `google.genai`
- pre-resolve do rótulo simples
- `TOOLS_PHOTO_MODE`
- logs básicos

### 5. Mudanças pequenas, observáveis e reversíveis
Se surgir um problema de produção, o sistema precisa ser corrigível via hotfix curto.

---

## Definição de pronto para qualquer fase de mídia

Uma fase só está pronta quando:

1. o fluxo novo está integrado no request path
2. a resposta chega ao usuário sem travar
3. os logs permitem saber em que etapa falhou
4. o sistema não inventa informação que o OCR não viu
5. os fallbacks são honestos
6. o caso principal daquela fase passa em produção ou em validação real equivalente

---

## O que não deve acontecer de novo

- código “pronto” mas não usado
- fluxo novo só em helper morto
- resposta boa apenas no happy path local
- fallback amigável escondendo bug de produção por semanas
- prompt gigante cobrindo 4 problemas ao mesmo tempo
- mudança de mídia reabrindo regressão em foto simples de rótulo

---

## Entregáveis esperados por fase

Cada prompt-filho deve entregar:

1. diagnóstico objetivo do fluxo atual
2. proposta técnica mínima para aquele tipo de mídia
3. implementação integrada
4. validação
5. riscos residuais
6. passos manuais de deploy, se houver

---

## Arquivos-base que provavelmente serão relevantes

- `C:\winegod-app\backend\routes\chat.py`
- `C:\winegod-app\backend\tools\media.py`
- `C:\winegod-app\backend\tools\resolver.py`
- `C:\winegod-app\backend\tools\search.py`
- `C:\winegod-app\backend\tools\schemas.py`
- `C:\winegod-app\backend\services\baco.py`
- `C:\winegod-app\backend\services\tracing.py`
- `C:\winegod-app\backend\prompts\baco_system.py`

---

## Relação com os handoffs existentes

Esta frente nova não substitui os handoffs antigos:

- `HANDOFF_INFRA.md` resolveu a base técnica
- `HANDOFF_PROMPTS.md` continua sendo referência importante para problemas de OCR e prompt
- `HANDOFF_P5_DEDUP.md` e `HANDOFF_P7_SCORES.md` continuam independentes

Aqui, o objetivo é pegar a base que já melhorou e expandi-la para outros formatos de mídia.

---

## Resultado esperado ao final desta família de handoffs

Ao final desta nova frente, o WineGod.ai deve ter:

- rótulo simples estável
- prateleira/screenshot útil
- múltiplas fotos consolidadas
- PDF utilizável
- foto de cardapio/lista utilizavel
- vídeo pelo menos com fallback honesto ou fluxo básico funcional

Sem perder:

- disponibilidade
- previsibilidade
- qualidade de resposta
- logs
