# PLANO EXECUTIVO — I18N WineGod.ai

**Versão:** 1.0
**Data:** 2026-04-15
**Autor:** executor técnico (Claude) + founder (Murilo)
**Status:** rascunho aprovado pelo founder para arquivamento; nenhuma fase iniciada

## Alinhamento honesto antes de começar

1. **IA tradutora tem taxa de erro real** (~2-5% em frases ambíguas). Mitigamos com back-translation + cross-check de 2 IAs, mas zero-erro não existe.
2. **Política legal traduzida por IA tem risco jurídico residual** (GDPR/CCPA). Mitigável com disclaimer público ("versão pt-BR prevalece"), mas se algum dia o app for para mercado rigoroso (EU), melhor revisitar.
3. **Orçamento é baixíssimo** (~$15-20 USD setup + ~$2-5/mês manutenção) porque usa APIs que o founder já tem (Claude + Gemini).
4. **Founder continua sendo gate humano** em decisões estratégicas e em frases marcadas como "suspeitas" pela IA. Não some 100%.

## Meta

Transformar o WineGod.ai de **monolíngue pt-BR** em **produto multi-idioma global** (R5 do CLAUDE.md) usando **automação de IA** (Claude + fallback Gemini) sem contratar tradutor humano.

## Contexto técnico do sistema atual (já auditado)

- **Frontend:** Next.js 15 + React 19 + TypeScript + Tailwind, build static + rotas dinâmicas (`/chat/[id]`, `/c/[id]`)
- **Backend:** Flask Python, endpoints REST — o texto do chat já é internacional (Baco responde no idioma do usuário via system prompt)
- **Banco:** PostgreSQL 16 no Render
- **15 rotas frontend** com texto em pt-BR hardcoded
- **Páginas legais:** `/privacy`, `/terms`, `/data-deletion` (prosa longa, risco legal maior)
- **Páginas funcionais:** `/ajuda`, `/conta`, `/plano`, `/favoritos` + componentes (`Sidebar`, `SearchModal`, `WelcomeScreen`, `UserMenu`, `ChatInput`, `CreditsBanner`, etc.)
- **Total estimado:** ~250-400 strings únicas na UI
- **Já decidido em sessão anterior:** chat URL permanente em `/chat/<id>` — vira `/pt/chat/<id>`, `/en/chat/<id>` etc.

## Restrições firmes

- Sem tradutor humano contratado
- Orçamento apertado — só custo de API
- Sem prazo de calendário; fases por gate de processo
- Founder não-programador — cada fase tem output inspecionável

## Protocolos de referência

1. **Mozilla Fluent** — separação mensagem ↔ código
2. **Airbnb Polyglot / ICU MessageFormat** — plurais, interpolação
3. **GitHub Localization Workflow** — extração + PR automatizados
4. **Next.js + next-intl** — padrão de produção
5. **Unicode CLDR** — locales, data/moeda
6. **BCP 47** — códigos de idioma (pt-BR, en-US, es-MX)
7. **GDPR Art. 12 / CCPA 1798.130** — disclosure no idioma do usuário
8. **Continuous Localization** (Spotify/Netflix) — tradução como parte do CI/CD

## Estrutura de fases

Cada fase tem: **Entrada** · **Saída** · **Gate** · **Automação** · **Rollback**. Nenhuma fase avança sem aprovação do founder no gate.

---

### FASE 0 — Decisões estratégicas (gate humano, sem código)

**Objetivo:** congelar decisões antes de tocar em código.

**Decisões obrigatórias do founder:**

1. **Idiomas MVP** — recomendado `pt-BR + en-US + es-MX` (começar com 3; >3 explode custo de QA)
2. **Idiomas Fase 2** — `fr, it, de, zh, ja` (baseado em analytics de origem dos usuários)
3. **IA tradutora primária** — Claude Sonnet 4.5 (qualidade melhor) com fallback Gemini Flash (barato) — ambos já contratados
4. **Estratégia de URL** — recomendado **subpath** (`chat.winegod.ai/en/chat/<id>`), simples e ótimo pra SEO
5. **Default language** — `en-US` (global) ou `pt-BR` (tráfego atual)?
6. **Políticas legais traduzidas por IA** — aceitar risco + disclaimer, ou manter só em idiomas que confia?

**Saída:** `reports/I18N_DECISIONS.md` com as 6 respostas.
**Gate:** founder aprova.
**Rollback:** trivial — só documento.

---

### FASE 1 — Auditoria de strings do sistema

**Objetivo:** mapear exatamente o que tem que traduzir antes de uma linha de código.

**Automação:**
- Script Node (`scripts/i18n/extract_strings.js`) faz AST walk em todo `.tsx`/`.ts` do frontend e extrai: JSX text, `title=`, `aria-label=`, `placeholder=`, `alt=`, template strings simples
- Ignora: imports, paths, classes CSS, URLs
- Claude classifica cada string em: **UI** / **prosa longa** / **mensagem de erro** / **nunca traduzir** (nomes próprios)

**Saída:** `reports/I18N_INVENTORY.json` com ~250-400 strings categorizadas + lista "nunca traduzir" (Baco, WineGod, winegod.ai, nomes de vinhos, castas)

**Gate:** founder valida amostra aleatória de 20 strings.
**Rollback:** apagar o JSON — zero impacto.

---

### FASE 2 — Infraestrutura técnica (sem mudar nada visual)

**Objetivo:** instalar `next-intl` e reorganizar rotas pra `[locale]`. Site continua 100% em pt-BR.

**Automação:**
- Script `scripts/i18n/bootstrap.sh`:
  1. `npm install next-intl`
  2. Cria `frontend/messages/pt-BR.json`, `en-US.json`, `es-MX.json` (vazios)
  3. Cria `frontend/i18n.ts` com config de locales
  4. Cria `frontend/middleware.ts` com detecção de locale
  5. Move rotas de `app/*` para `app/[locale]/*`
  6. Adiciona seletor de idioma (dropdown com bandeiras) no header do `AppShell`
- Build verde obrigatório

**Saída:** PR deployável em produção. `chat.winegod.ai/pt/chat/<id>` funciona igual hoje; `/en/*` funciona mas mostra texto em pt-BR (fallback).

**Gate:** build + tsc verdes + deploy sem regressão visual (QA manual ou screenshot test).
**Rollback:** revert do commit.

---

### FASE 3 — Refatoração: todo código usa chaves

**Objetivo:** cada string hardcoded vira `t("chave")`. `pt-BR.json` preenchido 100%.

**Automação (lote por arquivo):**
- Script `scripts/i18n/refactor.js` para cada arquivo do inventário:
  1. Manda arquivo + lista de strings pra Claude
  2. Prompt: *"Substitua cada string por `t('chave')` seguindo convenção `componente.secao.acao`. Gere também as entradas JSON correspondentes. Não altere nenhum outro código."*
  3. Gera diff do arquivo + update do JSON
  4. Founder revê diff (1 arquivo por vez ou em lote pequeno)

**Contrato de chaves:** `sidebar.newChat`, `favoritos.empty.title`, `errors.network`, etc.

**Saída:** zero strings em pt-BR hardcoded no `.tsx`. `pt-BR.json` é a fonte de verdade.

**Gate:** `grep` por palavras portuguesas comuns (`Salvar`, `Excluir`, `Sair`, `Conversa`) no `.tsx` retorna 0. Build verde. Produção mantém pt-BR idêntico (via fallback).
**Rollback:** revert por arquivo.

---

### FASE 4 — Pipeline automatizado de tradução (coração do plano)

**Objetivo:** gerar `en-US.json` e `es-MX.json` a partir de `pt-BR.json`.

**Pipeline de 3 passes (por idioma):**

**Passe 1 — Tradução primária (Claude Sonnet):**
- Script `scripts/i18n/translate.js` processa `pt-BR.json` em lotes de 50 strings
- Prompt estruturado:
  ```
  Você é tradutor profissional pt-BR → en-US especializado em
  interface de produto de vinhos. Regras absolutas:
  1. NUNCA traduza: Baco, WineGod, winegod.ai, nomes de vinhos, castas, denominações (Bordeaux, Rioja…)
  2. Preserve placeholders {{...}} intactos
  3. Preserve o tom (formal/informal) do original
  4. Se ambíguo, prefira tradução mais curta (cabe em botão)
  5. Se a string é uma mensagem de erro, preserve neutralidade técnica
  [50 strings com contexto de cada]
  ```
- Cache de prompt do Claude reduz custo em ~90% em lotes repetidos

**Passe 2 — Back-translation (Claude):**
- Traduz en-US → pt-BR **sem ver o original**
- Script compara similaridade semântica (embedding ou regras simples)
- Similaridade <85% → marca como **suspeita** pra review

**Passe 3 — Cross-check (Gemini Flash):**
- Gemini traduz o mesmo lote pt-BR → en-US independentemente
- Se Claude e Gemini divergem >30% nas palavras-chave → marca como **divergência**

**Validações automáticas (gate):**
- Todo placeholder `{{var}}` do original existe na tradução
- Tamanho ≤ 1.5x do original (evita layout quebrado)
- Nenhum nome da lista "nunca traduzir" virou outra coisa
- UTF-8 válido, sem HTML injetado

**Saída:** `en-US.json`, `es-MX.json` 100% preenchidos + `reports/I18N_TRANSLATION_LOG_<locale>.md` com lista de suspeitas e divergências.

**Gate:** founder revê lista de suspeitas+divergências (tipicamente 3-8% dos casos = ~15-30 strings por idioma) e aprova/edita.
**Rollback:** apagar arquivo do idioma — site continua em pt-BR.

---

### FASE 5 — QA automatizado visual por idioma

**Objetivo:** detectar layout quebrado, tradução estranha, chave faltante — tudo automatizado.

**Automação (4 testes):**

**Teste 1 — Contrato de chaves (lint):**
- Toda chave em `pt-BR.json` existe em `en-US.json` e `es-MX.json`
- CI falha se faltar

**Teste 2 — Visual regression com Playwright:**
- Script abre cada rota em cada idioma (ex: 9 rotas × 3 idiomas = 27 screenshots)
- Claude Vision analisa cada imagem:
  - "Algum texto estoura o container?"
  - "Algum botão ficou cortado?"
  - "Algum texto parece nonsense ou mal traduzido?"
- Lista achados em `reports/I18N_QA_<locale>.md`

**Teste 3 — Formato de data/moeda:**
- `Intl.DateTimeFormat("en-US").format(...)` retorna formato US
- Preços formatam conforme locale (R$, $, €)

**Teste 4 — RTL detection (futuro):**
- Se algum idioma adicionado for árabe/hebraico, abrir trilho próprio (CSS precisa `dir="rtl"`)

**Gate:** 0 chaves faltando + 0 texto estourado + <10 findings da IA Vision (ou triados).
**Rollback:** não deploya idioma problemático.

---

### FASE 6 — Lançamento escalonado por idioma

**Objetivo:** ativar 1 idioma por vez em produção, com monitoramento.

**Automação:**

1. **Feature flag** (env var `ENABLED_LOCALES=pt-BR,en-US`):
   - Middleware só redireciona pra locale se estiver na flag
   - Vercel edge config: ativar `en-US` pra 10% do tráfego → 100% se estável

2. **Seletor de idioma na UI:**
   - Dropdown na Sidebar com bandeiras
   - Salva em `localStorage` + perfil do usuário
   - Respeita `Accept-Language` do browser na primeira visita

3. **SEO:**
   - `<html lang="...">` automático
   - Sitemap inclui todos os idiomas
   - `<link rel="alternate" hreflang="...">` no `<head>`

4. **Páginas legais:**
   - Banner fixo: *"Automated translation. In case of conflict, the Portuguese version prevails."*
   - Link sempre visível pra versão pt-BR

5. **Monitoramento (PostHog):**
   - Eventos: `locale_selected`, `translation_missing_key`
   - Alerta se algum idioma tiver >1% de erros JS em 48h

**Gate:** idioma funciona em produção + usuário não troca de volta pra pt-BR em <10s + zero erro crítico em 48h.
**Rollback:** remover idioma do `ENABLED_LOCALES` — instantâneo, sem deploy.

---

### FASE 7 — Manutenção contínua automatizada

**Objetivo:** toda string nova traduzida automaticamente antes do deploy. Zero intervenção humana em mudanças pequenas.

**Automação:**

1. **Git pre-commit hook:**
   - Detecta chaves novas em `pt-BR.json`
   - Chama pipeline da FASE 4 automaticamente
   - Se suspeitas/divergências, bloqueia commit e pede review

2. **GitHub Action pós-merge:**
   - Roda contrato de chaves + QA visual
   - Falha CI se inconsistente

3. **Drift mensal:**
   - Cron: Claude re-traduz amostra aleatória, compara com prod
   - Se divergência >5%, abre issue automaticamente

4. **Feedback do usuário:**
   - Botão "Report bad translation" em cada página
   - Abre issue no GitHub com screenshot + chave + locale

**Gate:** dev adiciona 1 string nova em pt-BR → ao merge, os 2 outros idiomas já têm tradução sem intervenção humana.
**Rollback:** desligar hook/action — não afeta produção.

---

## Orçamento estimado (só APIs)

| Fase | Chamadas | Custo USD |
|---|---|---|
| 1 (auditoria) | ~400 strings × Claude Haiku | **$1-2** |
| 4 (tradução 3 idiomas × 3 passes) | 400 × 3 × 3 Claude Sonnet + Gemini Flash | **$8-15** |
| 5 (QA Vision) | 27 imagens × Claude Vision | **$2-3** |
| 7 (manutenção mensal) | ~50 strings novas × 3 locales × 3 passes | **$2-5/mês** |

**Setup: ~$15-20 USD. Manutenção: ~$2-5 USD/mês.**

---

## Riscos explícitos registrados

1. IA traduz mal frase ambígua — mitigado por back-translation + cross-check, não zero
2. Políticas legais com falha jurídica — mitigado por disclaimer, risco residual real no EU
3. Layout quebra em idioma específico — mitigado por Visual Regression, pode escapar
4. Drift com strings novas sem tradução — mitigado pela FASE 7
5. Custo de API se usuário explodir — **sem risco**: tradução é one-shot, não por request

---

## Ordem de execução

```
FASE 0 → gate founder
  ↓
FASE 1 → gate founder valida inventário
  ↓
FASE 2 → deploy prod (pt-BR idêntico)
  ↓
FASE 3 → deploy prod (pt-BR via fallback)
  ↓
FASE 4 (en-US) → gate founder aprova suspeitas
  ↓
FASE 5 (en-US) → gate findings triados
  ↓
FASE 6 (en-US escalonado 10%→100%) → monitoramento 48h
  ↓
Repete 4+5+6 pra es-MX
  ↓
FASE 7 (automação contínua)
  ↓
Fase 2 de idiomas: fr, it, de, zh, ja
```

---

## Prompt de execução (para outra aba/IA retomar)

```
Você é executor técnico do plano de i18n do WineGod.ai em
reports/I18N_EXECUTIVE_PLAN.md.

Repositório: C:\winegod-app
Stack: Next.js 15 + React 19 + TypeScript + Tailwind
Idioma atual: pt-BR hardcoded
Idiomas alvo MVP: pt-BR, en-US, es-MX
Restrições: sem tradutor humano, automação Claude+Gemini, orçamento baixo

Tarefa: executar FASE <N> do plano.

Antes de começar:
1. Leia reports/I18N_EXECUTIVE_PLAN.md completo
2. Leia reports/I18N_DECISIONS.md (decisões da FASE 0)
3. Se fase anterior não concluída, PARE e reporte
4. Nunca pule gates do founder
5. Todo commit passa npm run build + npx tsc --noEmit sequencial
6. Sem nenhum mock de tradução — APIs reais ou pare

Entrega obrigatória:
A. O que foi executado
B. Artefatos gerados (arquivos, screenshots, logs)
C. Validação real executada
D. Gate pendente para o founder
E. Próxima fase sugerida
```
