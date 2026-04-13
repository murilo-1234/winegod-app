# Julgamento Completo do Handoff do Codex

Data: 2026-04-06
Autor: Claude Code (Opus)
Documento julgado: `C:\winegod-app\prompts\HANDOFF_AUDITORIA_LINHAGEM_LINKS_RENDER.md`

Base do julgamento: investigacao empirica com queries nos bancos LOCAL e Render, simulacao do script `import_render_z.py`, analise de 76,812 wines afetados.

---

## Contexto

O Codex produziu um handoff para que outro chat execute uma auditoria completa da linhagem de links de loja no Render. Este documento julga topico a topico o que deve ser mantido, ajustado ou descartado, com base em evidencia empirica.

---

## Missao (linhas 1-14)

**MANTER, mas ajustar o numero.** O documento fala em "~88K" — o numero real confirmado por query e **76,812**. Fora isso, a missao esta perfeita: reconstruir linhagem, descobrir onde se perdeu, gerar artefatos, deixar trilha.

---

## Regra Absoluta (linhas 18-27)

**MANTER 100%.** Read-only, banco local como fonte de verdade, Render como estado auditado. Perfeito.

---

## Entregaveis (linhas 30-42)

**MANTER, mas item 5 e CRITICO e o Codex nao percebeu a escala.** O Codex pede "CSV com wine_sources associados ao vinho errado". Minha analise provou que existem **84,654 fontes excedentes** em 17,314 wines — esse CSV vai ser grande e e tao importante quanto o de faltantes.

---

## Contexto Atual (linhas 45-77)

**AJUSTAR numeros.** O documento diz "~88K" — o correto e **76,812** (query direta). O breakdown por rodada tambem precisa incluir o que descobri: **duas rodadas no dia 05/04** (14h com 12K wines e 18h com 767K wines), com taxa de erro crescente de 5.7% para 13.3%.

Falta tambem o historico de "delete dos wine_sources errados" entre rodadas — esse e o elo que permite wines existirem sem sources.

---

## Verdades Nao Negociaveis (linhas 81-94)

Julgamento individual:

| # | Afirmacao | Veredicto |
|---|-----------|-----------|
| 1 | Todo vinho de scraping nasceu de uma URL | **CORRETO** — confirmei 99.4% |
| 2 | Fonte de verdade = vinhos_XX_fontes | **CORRETO** — wines_clean.fontes esta vazio em 96% |
| 3 | wines_clean.id ≠ vinhos_XX.id | **CORRETO** — 0 duplicatas de (pais, id_original) |
| 4 | Ponte = pais_tabela + id_original | **CORRETO** — simulei e funciona 100% |
| 5 | y2_results.vivino_id = wines.id do Render | **CORRETO** |
| 6 | New tem 2 caminhos (hash ou check_exists) | **CORRETO** — e o check_exists e onde mora o bug principal |
| 7 | Um wine Render consolida varias linhas locais | **CORRETO** |
| 8 | Um hash_dedup consolida varios clean_id | **NAO CONFIRMADO.** Testei — 0 pares (pais, id_original) duplicados. Na pratica hash_dedup e unico por clean_id. Teoricamente possivel mas nao ocorre nos dados atuais |
| 9 | Script atual e batch com workers | **CORRETO** |
| 10 | Render nao e fonte de verdade dos links | **CORRETO** |

**Veredicto: MANTER, mas marcar #8 como "teoricamente possivel, nao confirmado nos dados".**

---

## Mapa de Entidades (linhas 98-151)

**MANTER 100%.** Correto e completo. Nada a ajustar.

---

## Linhagem Canonica (linhas 154-208)

**MANTER, mas adicionar aviso critico no Caminho N1.**

O documento descreve o caminho `check_exists_in_render` como "absorvido por vinho existente" — correto. Mas falta o aviso: **esse caminho e a fonte principal do bug**. Quando o produtor e generico (espumante, langhe, il, etc.), a absorcao vai pro wine ERRADO. O chat que receber esse handoff precisa saber disso ANTES de comecar.

Sugestao de adicao apos a descricao do Caminho N1:

> **ATENCAO**: O caminho N1 e onde ocorre a maioria dos links errados. Produtores curtos/genericos (<= 10 chars) como "espumante", "langhe", "barbera", "il" geram false matches. Verificado: 84,654 fontes excedentes em wines receptores com esses produtores.

---

## "Ligar Todas as Fases" — Canonica vs Replay (linhas 212-236)

**MANTER e EXCELENTE.** A distincao entre "reconstrucao canonica" (o que DEVERIA ser) e "replay historico" (o que o script FEZ) e muito boa. A maioria das auditorias confunde os dois.

A regra pratica esta perfeita: canonica para correcao, replay para prova de causa raiz.

---

## Fonte de Verdade por Camada (linhas 239-262)

**MANTER 100%.** Hierarquia de confianca correta. Destaco: "Para dono do link new: hash_final reproduzido, se nao resolver replay de check_exists_in_render, se nao resolver ambiguo." Isso esta perfeito.

---

## Pontos de Falha Ja Suspeitos (linhas 265-324)

Aqui esta o ponto mais critico do documento. Julgamento de cada um:

### Ponto 1: Rollback do batch inteiro (linhas 267-288)

**PARCIALMENTE CORRETO mas INCOMPLETO como causa raiz.**

O que o Codex diz esta certo: rollback perde wines bons junto com o ruim. E correto que `result["erros"]` subconta.

**Mas falta a peca-chave**: rollback sozinho nao produz wines sem sources, porque o rollback reverte AMBOS (wines e sources estao na mesma transacao, um unico commit na linha 486). So produz wines sem sources se o wine ja existia de uma rodada anterior (cujos sources foram deletados entre rodadas) e a nova rodada falha ao recriar sources.

**Ajuste necessario**: Adicionar que o rollback so explica wines sem sources quando combinado com "wine inserido em rodada anterior + sources deletados entre rodadas + nova rodada falha ao recriar sources".

### Ponto 2: Overwrite em hash_to_fontes (linhas 290-303)

**CORRETO mas IRRELEVANTE na pratica.** Verifiquei: 0 duplicatas de (pais, id_original) no wines_clean. O overwrite so aconteceria com colisoes de `gerar_hash_dedup`, que e raro. Pode manter como "bug a corrigir" mas nao como causa dos 76K.

### Ponto 3: Falta de observabilidade (linhas 305-314)

**CORRETO e IMPORTANTE.** A Fase 2 nao mede quantos new ficaram sem fontes, sem loja, perderam source por erro. Isso dificultou muito o diagnostico. Ponto valido.

### Ponto 4: Branch check_exists_in_render (linhas 316-324)

**CORRETO mas CRITICAMENTE INCOMPLETO.** O documento apenas diz que o wine "depende de fontes_map e depende do batch sobreviver". Falta a descoberta mais importante da investigacao:

> **O check_exists_in_render com produtores genericos REDIRECIONA fontes pro wine errado. Isso e a causa dominante dos 76K, nao so um "ponto de falha suspeito".**

Evidencia:
- 84,654 fontes excedentes em 17,314 wines receptores
- Ratio 84,654 / 76,812 = 1.10x (quase 1:1 com os wines sem link)
- Mesmos produtores nos dois lados (espumante, gruner, langhe, barbera, il, barolo)
- Taxa de erro cresce com o tempo: 5.7% as 18h → 13.3% as 19h → 8.7% as 20h
- Conforme render_by_prod acumula mais candidatos, falsos matches aumentam

**Este ponto deveria ser o #1 do documento, nao o #4.**

---

## Reproducao Fiel de Regras (linhas 326-374)

**MANTER 100%.** Perfeito: get_domain, hash_final, check_exists_in_render, stopwords. O chat que executar precisa reproduzir EXATAMENTE essas regras.

---

## Estrategia de Execucao — 4 Camadas (linhas 378-448)

**MANTER a estrutura, mas a execucao e EXCESSIVAMENTE COMPLEXA para o problema real.**

O Codex propoe:
1. Inventario local canonico
2. Inventario Render observado
3. Tabela de expectativa
4. Comparacao esperado vs observado

Isso e academicamente perfeito mas operacionalmente exagerado. A investigacao ja provou com queries diretas:
- Cat A = 74,520 (hash → wines_clean → fontes → dominio → store = tudo existe)
- Cat B = 9
- Cat C = 2,084
- Cat D = 199

Para CORRIGIR, nao precisa de 10 CSVs. Precisa de 1 script que:
1. Busca wines sem source no Render
2. Mapeia hash → local → fontes → store
3. INSERT wine_sources

**Veredicto: MANTER como referencia de auditoria completa, mas avisar o chat que para CORRECAO a abordagem direta e mais eficiente.**

---

## Passos 0-11 (linhas 452-799)

Julgamento de cada passo:

| Passo | Veredicto |
|-------|-----------|
| 0 — Ler docs | **MANTER** |
| 1 — Validar conexoes | **MANTER** |
| 2A — Universo matched | **MANTER** mas peso menor (matched tem cobertura 99.8%) |
| 2B — Universo new | **MANTER — e o foco principal** |
| 3A/B/C — Render inventory | **SIMPLIFICAR** — nao precisa baixar 2.5M wines + 3.6M sources. Focar nos 76K sem source |
| 4A — matched owner | **MANTER** |
| 4B — new por hash | **MANTER — caminho principal** |
| 4C — new por check_exists | **MANTER para diagnostico, DESCARTAR para correcao.** Na correcao, usar so hash |
| 5 — Mapa (pais, id_original) | **MANTER — essencial** |
| 6 — Carregar fontes | **MANTER mas filtrar** — so carregar para os 76K, nao para 5.6M |
| 7 — Links esperados | **MANTER** |
| 8 — Inventario Render | **SIMPLIFICAR** — focar nos 76K |
| 9 — Comparacao | **MANTER** — mas a comparacao "wrong_wine_association" e a mais importante |
| 10 — Classificar A/B/C/D | **JA FEITO** — numeros exatos disponoveis |
| 11 — Links errados | **MANTER e PRIORIZAR** — 84K fontes em wines errados |

---

## Sinais de Caminho Errado (linhas 1047-1061)

**MANTER 100%.** Todos os 10 sinais sao validos. Destaco #7 e #9 como os mais relevantes (ignorar check_exists_in_render e ignorar rollback).

**Adicionar #11**: "Ignorar que check_exists_in_render com produtores genericos redireciona fontes pro wine errado"

---

## RESUMO FINAL

### O que APLICAR do documento Codex:
- Toda a estrutura de linhagem (excelente)
- Verdades nao negociaveis (com ajuste no #8)
- Reproducao fiel das regras do script
- Distincao canonica vs replay
- Passo 11 (links errados) — critico
- Sinais de caminho errado

### O que DESCARTAR ou AJUSTAR:
1. **Numero "~88K"** → corrigir para **76,812**
2. **Causa raiz = so rollback** → INCOMPLETO. Adicionar check_exists_in_render como causa dominante
3. **Ponto de falha #4** → PROMOVER a causa raiz #1
4. **10 CSVs de artefatos** → SIMPLIFICAR para correcao (overkill para o problema real)
5. **Baixar 2.5M wines + 3.6M sources** → FILTRAR para os 76K afetados
6. **Verdade #8 (hash consolida clean_ids)** → Marcar como "nao confirmado nos dados atuais"
7. **Falta o historico de delete entre rodadas** → ADICIONAR como contexto critico

### O que FALTA no documento e a investigacao empirica prova:
1. **84,654 fontes excedentes** em wines receptores (prova do mismatch de check_exists_in_render)
2. **Duas rodadas no dia 05/04** (14h e 18h) com taxa crescente de erro
3. **Produtores genericos** como causa dominante (espumante, langhe, barbera, il, barolo, etc.)
4. **Contagem exata A/B/C/D**: A=74,520 (97.0%) | B=9 (0.0%) | C=2,084 (2.7%) | D=199 (0.3%)
5. **Delete de sources entre rodadas** como pre-condicao do bug
6. **Distribuicao por pais**: 54,731 (71%) dos wines sem link tem pais=NULL no Render

### Diagnostico unificado (Codex + investigacao empirica):

Duas causas raiz operando em conjunto:

| Causa | Mecanismo | Peso estimado | Evidencia |
|-------|-----------|---------------|-----------|
| **check_exists_in_render mismatch** | Produtores genericos matcham ao wine errado, fontes sao redirecionadas | ~60-70% | 84K fontes excedentes, mesmos produtores, taxa crescente |
| **Rollback de batch inteiro** | Erro em 1 wine mata sources de todo o batch para wines ja existentes de rodadas anteriores | ~30-40% | Historico de erros de encoding/varchar nas rodadas |

### Proposta de correcao (para o chat que receber o handoff):

A correcao NAO precisa reescrever a Fase 2. Precisa de um script NOVO e simples:

1. Buscar todos os wines no Render onde `vivino_id IS NULL AND NOT EXISTS wine_sources`
2. Para cada wine: `hash_dedup` → `wines_clean` → `(pais_tabela, id_original)` → `vinhos_XX_fontes`
3. Para cada fonte: `get_domain(url)` → `stores.dominio` → `store_id`
4. `INSERT INTO wine_sources ON CONFLICT DO NOTHING`
5. Processar em batches de 500, com SAVEPOINT por batch
6. Sem workers, sem check_exists_in_render, sem hash_to_fontes

Estimativa: ~74,520 wines passarao a ter link. ~141K wine_sources serao criados.
