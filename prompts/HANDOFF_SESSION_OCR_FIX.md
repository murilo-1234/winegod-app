# HANDOFF — Sessao OCR Fix (P1/P2/P3/P4/P11/P12/P13)

## Quem voce e neste chat
Voce e um assistente de desenvolvimento para o WineGod.ai. O usuario (Murilo) NAO e programador. Respostas simples, diretas, sem jargao. Caminhos sempre completos.

## O que e o WineGod.ai
IA sommelier global. Usuario manda foto de vinho -> Gemini OCR extrai dados -> Claude Haiku (personagem Baco) responde.

## O que foi feito nesta sessao (concluido e validado)

### Entrega principal: correcao de P1, P2, P3, P4, P11, P12, P13

Problemas resolvidos:
- **P1**: OCR classificava 100% das fotos como "shelf", mesmo close-ups de 1 garrafa. Corrigido: prompt agora usa "dominancia visual" em vez de "single bottle".
- **P2**: Precos lidos errados (pegava preco/litro em vez de preco da garrafa). Corrigido: Price rules especificas para etiquetas BR.
- **P3**: total_visible inflado (120, 280 garrafas). Corrigido: redefinido como SKUs distintos, estimativa conservadora.
- **P4**: Typos nos nomes (Trivent, PONTGRAS). Corrigido: Name cleanup rules no prompt.
- **P11**: Baco dizia "vi ~15 garrafas" baseado em estimativa fraca. Corrigido: total_visible removido do contexto + regra NUNCA no Baco.
- **P12**: OCR trocava uva (Petit Sirah vs Petit Verdot). Corrigido: Grape rules — retornar null se ambiguo.
- **P13**: Preco da foto era descartado, Baco citava preco de outro pais. Corrigido: preco preservado em TODOS os caminhos (label/shelf/screenshot/batch) + regra de ancora no Baco.

### Arquivos alterados

1. **C:\winegod-app\backend\tools\media.py**
   - IMAGE_UNIFIED_PROMPT reescrito: classificacao por dominancia visual, price em label, Price/Name/Grape/Shelf rules
   - _handle_label: preco na descricao, fora do search_text
   - _handle_shelf: sem "~N garrafas" na descricao
   - SDK Gemini migrado para google.genai (feito por linter automatico, nao por nos)

2. **C:\winegod-app\backend\routes\chat.py**
   - Fluxo simples restaurado: OCR -> contexto textual -> Claude
   - _build_image_context: label inclui preco da foto, screenshot inclui preco+rating (sem source), shelf inclui preco (sem total_visible)
   - _build_batch_context: preserva preco para todos os tipos, rating para screenshot
   - Removidos imports de resolver e tracing
   - Removido pre-resolve no banco

3. **C:\winegod-app\backend\prompts\baco_system.py**
   - 3 regras novas em NUNCA: nao transformar estimativa em contagem, nao trocar preco da foto, nao inventar dados do OCR
   - Nova secao FOTOS E OCR: preco da foto e ancora, falar so do que veio no contexto
   - 3 items novos no checklist interno
   - BACO_SYSTEM_PROMPT_SHORT atualizado com as mesmas regras

4. **C:\winegod-app\backend\services\baco.py**
   - Removidos parametros photo_mode e trace (eram dead code)
   - Removido import de TOOLS_PHOTO_MODE
   - Removida classe _noop_ctx

### Dead code residual (NAO importado, NAO afeta nada)
- `C:\winegod-app\backend\tools\resolver.py` — arquivo orfao, nao importado
- `C:\winegod-app\backend\services\tracing.py` — arquivo orfao, nao importado
- `C:\winegod-app\backend\tools\schemas.py` tem TOOLS_PHOTO_MODE definido mas ninguem importa

### O que NAO foi tocado (fora de escopo)
- P5: cobertura do banco (75% sem rating)
- P6: busca retorna vinhos errados (ILIKE)
- P7: discrepancia nota WCF vs Vivino
- P8: performance (28-98s por foto)
- P9: Render cold starts
- P10: Gemini SDK deprecated (ja migrado pelo linter)
- Frontend, search.py, executor.py, schemas.py (exceto dead code)

### Validacao executada (tudo PASS)
- Label preserva preco da foto
- Screenshot preserva preco + rating, sem source
- Shelf preserva preco, sem total_visible, sem "~N garrafas"
- Batch preserva preco/rating em todos os tipos
- Nenhum import de resolver/tracing/photo_mode
- Sintaxe Python OK em todos os arquivos
- baco.py funcional sem parametros extras

### Proximos passos possiveis (NAO iniciados)
- Testar com as 24 fotos reais (diretorio: C:\winegod\fotos-vinhos-testes) usando C:\winegod-app\test_ocr_direto.py
- Atacar P5/P6 (busca e cobertura do banco)
- Remover dead code (resolver.py, tracing.py, TOOLS_PHOTO_MODE em schemas.py)
- Deploy e teste em producao

## Regras para esta sessao
- Ler CLAUDE.md em C:\winegod-app\CLAUDE.md antes de qualquer acao
- NAO fazer commit sem perguntar
- NAO mexer em arquivos fora do escopo sem autorizacao
- Caminhos sempre completos
- Respostas simples e diretas
