# HANDOFF - Midia P3A: PDF

## Quem e voce neste chat
Voce e o engenheiro responsavel por fazer o WineGod.ai lidar bem com **PDFs de carta, catalogo e lista de vinhos**, aproveitando a base tecnica ja estabilizada para imagens.

---

## Pre-requisito

Este prompt so deve ser executado depois que:

- `HANDOFF_MEDIA_P1_SHELF_SCREENSHOT.md` estiver validado
- `HANDOFF_MEDIA_P2_MULTI_IMAGE.md` estiver validado

---

## Objetivo

Permitir que o usuario envie:

- PDF de carta
- PDF de catalogo
- PDF de lista/exportacao de vinhos

e receba uma resposta util sobre os vinhos realmente lidos.

---

## O problema desta fase

PDF nao e so "outra imagem". Ele pode ter:

- texto estruturado
- colunas e tabelas
- secoes
- precos proximos a muitos itens
- PDF nativo com texto
- PDF escaneado como imagem

---

## O que investigar

1. `process_pdf()` em `C:\winegod-app\backend\tools\media.py`
2. como o contexto do PDF e passado ao Claude em `C:\winegod-app\backend\routes\chat.py`
3. se hoje o backend esta so descrevendo ou tambem resolvendo vinhos
4. como relacionar nome e preco sem inventar
5. onde PDF nativo e PDF escaneado se comportam de forma diferente

---

## O que precisa melhorar

- separar vinho de texto decorativo
- associar preco ao item certo quando possivel
- nao transformar layout em vinho
- manter resposta util sem fingir certeza total
- deixar claro quando o dado veio de texto extraido vs OCR visual

---

## Arquivos principais

- `C:\winegod-app\backend\tools\media.py`
- `C:\winegod-app\backend\routes\chat.py`
- `C:\winegod-app\backend\tools\resolver.py`
- `C:\winegod-app\backend\prompts\baco_system.py`

---

## Criterios de aceite

1. um PDF simples de carta gera resposta util
2. um PDF com varios precos nao associa preco errado de forma grosseira
3. PDF escaneado tem fallback honesto
4. o sistema nao inventa itens nao lidos
5. nao ha travamento excessivo

---

## Como validar

Validar com:

1. PDF simples de carta de vinhos
2. PDF com varios precos
3. PDF com secoes e titulos
4. PDF escaneado

---

## O que entregar

1. diagnostico
2. implementacao
3. arquivos alterados
4. validacao
5. riscos residuais
