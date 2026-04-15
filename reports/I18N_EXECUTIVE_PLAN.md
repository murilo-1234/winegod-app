# PLANO EXECUTIVO — I18N WineGod.ai

**Versão:** 2.0
**Data:** 2026-04-15
**Autor:** executor técnico (Claude) + founder (Murilo)
**Status:** rascunho aprovado pelo founder para arquivamento; nenhuma fase iniciada

## Alinhamento honesto antes de começar

1. **IA tradutora tem taxa de erro real** (~2-5% em frases ambíguas). Mitigamos com back-translation + cross-check de 2 IAs, mas zero-erro não existe.
2. **Política legal traduzida por IA tem risco jurídico residual** (GDPR/CCPA). Mitigável com disclaimer público ("versão pt-BR prevalece"), mas se o app abrir para mercado rigoroso (EU), melhor revisitar.
3. **Orçamento é baixíssimo para 20 idiomas** (~$80-150 USD setup + ~$15-30/mês manutenção) porque usa APIs que o founder já tem (Claude + Gemini).
4. **Founder continua sendo gate humano** em decisões estratégicas e em frases marcadas como "suspeitas" pela IA. Para 20 idiomas, esse gate vira ~400 strings de review (~3-4 horas totais, divisível em sessões).

## Meta

Transformar o WineGod.ai de **monolíngue pt-BR** em **produto global multi-idioma** (R5 do CLAUDE.md) usando **automação de IA** (Claude + fallback Gemini) sem contratar tradutor humano, cobrindo **até 20 idiomas** em rollout por ondas.

**Motivação direta:** 4M usuários do Cicno esperando lançamento multi-idioma. Cada onda entrega mais mercado.

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
- Objetivo final: até 20 idiomas, sem comprometer estabilidade

## Lista de 20 idiomas alvo

| Tier | Idioma | Código BCP 47 | Tratamento técnico | Observação |
|---|---|---|---|---|
| Base | Português (Brasil) | `pt-BR` | padrão | idioma atual |
| A | Inglês (EUA) | `en-US` | padrão | mercado global |
| A | Espanhol (México) | `es-MX` | padrão | América Latina |
| A | Francês | `fr-FR` | padrão | mercado consumidor de vinho |
| A | Italiano | `it-IT` | padrão | mercado consumidor de vinho |
| B | Alemão | `de-DE` | padrão (layout tolera +40%) | texto mais longo |
| B | Holandês | `nl-NL` | padrão | |
| B | Sueco | `sv-SE` | padrão | |
| B | Dinamarquês | `da-DK` | padrão | |
| B | Norueguês | `no-NO` | padrão | |
| B | Finlandês | `fi-FI` | padrão (layout tolera +50%) | texto muito longo |
| C | Russo | `ru-RU` | padrão | alfabeto Cirílico |
| C | Polonês | `pl-PL` | padrão | |
| C | Ucraniano | `uk-UA` | padrão | |
| C | Turco | `tr-TR` | padrão | |
| D (CJK) | Chinês (Simplificado) | `zh-CN` | **FASE 8** — fonte Noto Sans SC | requer trabalho técnico |
| D (CJK) | Japonês | `ja-JP` | **FASE 8** — fonte Noto Sans JP | requer trabalho técnico |
| D (CJK) | Coreano | `ko-KR` | **FASE 8** — fonte Noto Sans KR | requer trabalho técnico |
| E (RTL) | Árabe | `ar-SA` | **FASE 9** — layout invertido `dir="rtl"` | requer trabalho técnico |
| E (RTL) | Hebraico | `he-IL` | **FASE 9** — layout invertido `dir="rtl"` | requer trabalho técnico |

## Protocolos de referência

1. **Mozilla Fluent** — separação mensagem ↔ código
2. **Airbnb Polyglot / ICU MessageFormat** — plurais, interpolação
3. **GitHub Localization Workflow** — extração + PR automatizados
4. **Next.js + next-intl** — padrão de produção
5. **Unicode CLDR** — locales, data/moeda
6. **BCP 47** — códigos de idioma (pt-BR, en-US, es-MX)
7. **GDPR Art. 12 / CCPA 1798.130** — disclosure no idioma do usuário
8. **Continuous Localization** (Spotify/Netflix) — tradução como parte do CI/CD
9. **W3C Internationalization (i18n) Working Group** — HTML lang, dir, RTL best practices
10. **Google Noto Fonts** — cobertura tipográfica para CJK

## Estrutura de fases

Cada fase tem: **Entrada** · **Saída** · **Gate** · **Automação** · **Rollback**. Nenhuma fase avança sem aprovação do founder no gate.

---

### FASE 0 — Decisões estratégicas (gate humano, sem código)

**Objetivo:** congelar decisões antes de tocar em código.

**Decisões obrigatórias do founder:**

1. **Lista final de 20 idiomas** — confirmar tabela acima ou ajustar (ex: trocar `no-NO` por `hi-IN` se prioridade for Índia)
2. **IA tradutora primária** — Claude Sonnet 4.5 (qualidade melhor) com fallback Gemini Flash (barato) — ambos já contratados
3. **Estratégia de URL** — recomendado **subpath** (`chat.winegod.ai/en/chat/<id>`), simples e ótimo pra SEO
4. **Default language** — `en-US` (global) ou `pt-BR` (tráfego atual)?
5. **Políticas legais traduzidas por IA** — aceitar risco + disclaimer, ou manter só em idiomas de confiança?
6. **Ordem das ondas** — confirmar sequência abaixo ou reordenar por prioridade de mercado

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

**Saída:** `reports/I18N_INVENTORY.json` com ~250-400 strings categorizadas + lista "nunca traduzir" (Baco, WineGod, winegod.ai, nomes de vinhos, castas, denominações como Bordeaux, Rioja, Barolo).

**Gate:** founder valida amostra aleatória de 20 strings.
**Rollback:** apagar o JSON — zero impacto.

---

### FASE 2 — Infraestrutura técnica (sem mudar nada visual)

**Objetivo:** instalar `next-intl` e reorganizar rotas pra `[locale]`. Site continua 100% em pt-BR.

**Automação:**
- Script `scripts/i18n/bootstrap.sh`:
  1. `npm install next-intl`
  2. Cria `frontend/messages/pt-BR.json` (+ stubs vazios de cada locale da FASE 0)
  3. Cria `frontend/i18n.ts` com config de locales
  4. Cria `frontend/middleware.ts` com detecção de locale
  5. Move rotas de `app/*` para `app/[locale]/*`
  6. Adiciona seletor de idioma (dropdown com bandeiras) no header do `AppShell`
- Build verde obrigatório

**Saída:** PR deployável em produção. `chat.winegod.ai/pt/chat/<id>` funciona igual hoje; qualquer outro locale funciona mas mostra texto em pt-BR (fallback).

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

**Objetivo:** gerar `<locale>.json` a partir de `pt-BR.json` para cada idioma alvo.

**Reutilizada em TODAS as ondas.** O pipeline é o mesmo — só muda o locale de saída.

**Pipeline de 3 passes (por idioma):**

**Passe 1 — Tradução primária (Claude Sonnet):**
- Script `scripts/i18n/translate.js --locale=<bcp47>` processa `pt-BR.json` em lotes de 50 strings
- Prompt estruturado:
  ```
  Você é tradutor profissional pt-BR → <IDIOMA ALVO> especializado em
  interface de produto de vinhos. Regras absolutas:
  1. NUNCA traduza: Baco, WineGod, winegod.ai, nomes de vinhos, castas,
     denominações (Bordeaux, Rioja, Barolo, Champagne, Chianti…)
  2. Preserve placeholders {{...}} intactos
  3. Preserve o tom (formal/informal) do original
  4. Se ambíguo, prefira tradução mais curta (cabe em botão)
  5. Se a string é uma mensagem de erro, preserve neutralidade técnica
  6. Para idiomas com variedades regionais (pt-PT vs pt-BR, en-US vs en-GB),
     use a variedade especificada no locale BCP 47
  [50 strings com contexto de cada]
  ```
- Cache de prompt do Claude reduz custo em ~90% em lotes repetidos

**Passe 2 — Back-translation (Claude):**
- Traduz `<locale>` → pt-BR **sem ver o original**
- Script compara similaridade semântica (embedding ou regras simples)
- Similaridade <85% → marca como **suspeita** pra review

**Passe 3 — Cross-check (Gemini Flash):**
- Gemini traduz o mesmo lote pt-BR → `<locale>` independentemente
- Se Claude e Gemini divergem >30% nas palavras-chave → marca como **divergência**

**Validações automáticas (gate):**
- Todo placeholder `{{var}}` do original existe na tradução
- Tamanho ≤ 1.5x do original para idiomas padrão, ≤ 1.8x para alemão/finlandês
- Nenhum nome da lista "nunca traduzir" virou outra coisa
- UTF-8 válido, sem HTML injetado
- CJK: verifica que a string tem caracteres CJK (não é vazio)
- Árabe/hebraico: verifica direção de texto consistente

**Saída:** `<locale>.json` 100% preenchido + `reports/I18N_TRANSLATION_LOG_<locale>.md` com suspeitas e divergências.

**Gate:** founder revê lista de suspeitas+divergências (tipicamente 3-8% dos casos = ~15-30 strings por idioma) e aprova/edita.
**Rollback:** apagar arquivo do idioma — site continua em pt-BR.

---

### FASE 5 — QA automatizado visual por idioma

**Objetivo:** detectar layout quebrado, tradução estranha, chave faltante — tudo automatizado.

**Reutilizada em TODAS as ondas.** O QA é o mesmo — só muda o locale.

**Automação (4 testes):**

**Teste 1 — Contrato de chaves (lint):**
- Toda chave em `pt-BR.json` existe em `<locale>.json`
- CI falha se faltar

**Teste 2 — Visual regression com Playwright:**
- Script abre cada rota em cada idioma (ex: 9 rotas × 20 idiomas = 180 screenshots no total acumulado)
- Claude Vision analisa cada imagem:
  - "Algum texto estoura o container?"
  - "Algum botão ficou cortado?"
  - "Algum texto parece nonsense ou mal traduzido?"
  - "(Para RTL) A direção da interface está correta?"
- Lista achados em `reports/I18N_QA_<locale>.md`

**Teste 3 — Formato de data/moeda/número:**
- `Intl.DateTimeFormat("<locale>").format(...)` retorna formato correto
- Preços formatam conforme locale (R$, $, €, ¥, ₪, د.إ)
- Números: separador decimal correto (`,` em pt, `.` em en)

**Teste 4 — Specifics por tier:**
- **CJK:** fontes Noto carregaram, caracteres renderizando (não aparece tofu `□`)
- **RTL:** direção `dir="rtl"` aplicada, ícones espelhados onde apropriado

**Gate:** 0 chaves faltando + 0 texto estourado + <10 findings da IA Vision (ou triados).
**Rollback:** não deploya idioma problemático.

---

### FASE 6 — Lançamento escalonado por idioma

**Objetivo:** ativar 1 idioma por vez em produção, com monitoramento.

**Reutilizada em TODAS as ondas.**

**Automação:**

1. **Feature flag** (env var `ENABLED_LOCALES=pt-BR,en-US,...`):
   - Middleware só redireciona pra locale se estiver na flag
   - Vercel edge config: ativar novo idioma pra 10% do tráfego → 100% se estável

2. **Seletor de idioma na UI:**
   - Dropdown na Sidebar com bandeiras + nomes nativos (ex: "Português", "English", "日本語", "العربية")
   - Salva em `localStorage` + perfil do usuário
   - Respeita `Accept-Language` do browser na primeira visita

3. **SEO:**
   - `<html lang="...">` automático
   - `<html dir="rtl">` automático para locales RTL
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

**Objetivo:** toda string nova traduzida automaticamente para os 20 idiomas antes do deploy.

**Entrada:** última onda concluída.

**Automação:**

1. **Git pre-commit hook:**
   - Detecta chaves novas em `pt-BR.json`
   - Chama pipeline da FASE 4 automaticamente para todos os locales ativos
   - Se suspeitas/divergências, bloqueia commit e pede review

2. **GitHub Action pós-merge:**
   - Roda contrato de chaves + QA visual
   - Falha CI se inconsistente

3. **Drift mensal:**
   - Cron: Claude re-traduz amostra aleatória de cada locale, compara com produção
   - Se divergência >5%, abre issue automaticamente

4. **Feedback do usuário:**
   - Botão "Report bad translation" em cada página
   - Abre issue no GitHub com screenshot + chave + locale

**Gate:** dev adiciona 1 string nova em pt-BR → ao merge, os 20 outros idiomas já têm tradução sem intervenção humana.
**Rollback:** desligar hook/action — não afeta produção.

---

### FASE 8 — Suporte CJK (chinês, japonês, coreano)

**Objetivo:** habilitar infraestrutura tipográfica para idiomas asiáticos antes da Onda 4.

**Entrada:** Ondas 1-3 concluídas.

**Automação:**

1. **Fontes Noto Sans:**
   - Adicionar via `next/font` com subset específico:
     - Noto Sans SC (chinês simplificado) — para `zh-CN`
     - Noto Sans TC (chinês tradicional) — para `zh-TW` (opcional)
     - Noto Sans JP (japonês) — para `ja-JP`
     - Noto Sans KR (coreano) — para `ko-KR`
   - Carregamento condicional: só inclui a fonte no bundle se locale ativo

2. **Fallback de fonte:**
   - CSS `font-family` do `<html>` muda conforme `lang`
   - Ex: `<html lang="ja">` usa Noto Sans JP primeiro, Inter depois

3. **Renderização de caracteres:**
   - Teste automatizado: cada string CJK não renderiza como tofu (`□`)
   - Screenshot de cada rota em zh-CN / ja-JP / ko-KR com texto legível

4. **Tamanho do bundle:**
   - Cada fonte CJK pesa ~300-500KB (já com subset)
   - Estratégia: só carrega a fonte do locale ativo do usuário (não todas juntas)

**Saída:** infraestrutura de fontes instalada, sem locales CJK ativos ainda.

**Gate:** teste visual em todos os navegadores confirma renderização sem tofu; bundle não aumentou para usuários em outros idiomas.
**Rollback:** remover fontes do `next/font`.

---

### FASE 9 — Suporte RTL (árabe, hebraico)

**Objetivo:** habilitar layout direita-pra-esquerda antes da Onda 5.

**Entrada:** Ondas 1-4 concluídas.

**Automação:**

1. **Atributo `dir` dinâmico:**
   - `<html dir="rtl">` quando locale é árabe/hebraico/persa
   - `<html dir="ltr">` nos demais

2. **Tailwind RTL:**
   - Habilitar plugin `tailwindcss-logical` ou usar variantes nativas `rtl:` / `ltr:`
   - Substituir classes direcionais: `ml-4` → `ms-4` (margin-start), `text-left` → `text-start`, etc.
   - Auditar cada componente: Sidebar vai pra direita, SearchModal espelhado, ícones de chevron invertidos

3. **Ícones e elementos direcionais:**
   - Setas de "enviar" e "voltar" espelhadas
   - Logo do header: manter como está (logos não são espelhados)
   - Números: **não espelhar** (números arábicos mantêm ordem esquerda-pra-direita mesmo em árabe)

4. **Teste visual:**
   - Playwright abre cada rota em `ar-SA` / `he-IL`
   - Claude Vision valida: sidebar à direita, texto alinhado à direita, botões invertidos

**Saída:** infraestrutura RTL instalada, sem locales RTL ativos ainda.

**Gate:** screenshots comparativos ltr vs rtl passam na revisão visual.
**Rollback:** remover classes `rtl:` e `dir` dinâmico.

---

## Orçamento estimado para 20 idiomas (só APIs)

| Item | Detalhe | Custo USD |
|---|---|---|
| Fase 1 (auditoria) | ~400 strings × Claude Haiku | **$1-2** |
| Fase 4 (tradução 20 idiomas × 3 passes) | 400 × 20 × 3 chamadas Claude Sonnet + Gemini Flash com prompt caching | **$60-120** |
| Fase 5 (QA Vision 20 idiomas) | ~180 imagens × Claude Vision | **$15-25** |
| Fase 8 (suporte CJK — fontes) | sem custo de API, só código | $0 |
| Fase 9 (suporte RTL — layout) | sem custo de API, só código | $0 |
| Fase 7 (manutenção mensal) | ~50 strings novas × 20 locales × 3 passes | **$15-30/mês** |

**Setup total: ~$80-150 USD. Manutenção: ~$15-30 USD/mês.**

**Custo de tempo do founder no gate humano:** ~400 strings de review (20 × ~20 suspeitas por idioma), ~3-4 horas totais divididas ao longo das ondas.

---

## Riscos explícitos registrados

1. IA traduz mal frase ambígua — mitigado por back-translation + cross-check, não zero
2. Políticas legais com falha jurídica — mitigado por disclaimer, risco residual real no EU
3. Layout quebra em idioma específico (alemão/finlandês) — mitigado por Visual Regression, pode escapar
4. Drift com strings novas sem tradução — mitigado pela FASE 7
5. Custo de API se usuário explodir — **sem risco**: tradução é one-shot, não por request
6. **Onda CJK (Fase 8):** bundle extra (~300-500KB por fonte) aumenta tempo de load no primeiro acesso de usuário asiático — mitigado por carregamento condicional
7. **Onda RTL (Fase 9):** componentes feitos com classes `ml-*`/`text-left` podem quebrar em árabe — mitigado por auditoria CSS na Fase 9
8. **Gate humano gargalo:** revisar 400 strings em 20 idiomas exige disciplina do founder — mitigado pela cadência onda-a-onda

---

## Ordem de execução por ONDAS

```
FASE 0 → gate founder (lista final 20 idiomas + decisões estratégicas)
  ↓
FASE 1 → gate founder valida inventário
  ↓
FASE 2 → deploy prod (pt-BR idêntico)
  ↓
FASE 3 → deploy prod (pt-BR via fallback)
  ↓

ONDA 1 (MVP — VALIDAR PIPELINE): pt-BR, en-US, es-MX
  FASE 4 (traduz en-US, es-MX) → gate founder aprova suspeitas
  FASE 5 (QA) → gate findings triados
  FASE 6 (lança en-US escalonado, depois es-MX)
  → monitoramento 48h em produção
  → GATE FOUNDER: pipeline validado? prosseguir para Onda 2?

  ↓

ONDA 2 (latim, baixo risco): fr-FR, it-IT
  FASE 4 + 5 + 6 (repete)
  → GATE FOUNDER

  ↓

ONDA 3 (germânico/eslavo/turco): de-DE, nl-NL, sv-SE, da-DK, no-NO, fi-FI, ru-RU, pl-PL, uk-UA, tr-TR
  FASE 4 + 5 + 6 (repete)
  Cuidado extra com layout em de/fi (texto longo)
  → GATE FOUNDER

  ↓

FASE 8 (suporte CJK) → gate técnico + visual

  ↓

ONDA 4 (CJK): zh-CN, ja-JP, ko-KR
  FASE 4 + 5 + 6 (repete)
  → GATE FOUNDER

  ↓

FASE 9 (suporte RTL) → gate técnico + visual

  ↓

ONDA 5 (RTL): ar-SA, he-IL
  FASE 4 + 5 + 6 (repete)
  Cuidado extra com layout invertido + ícones direcionais
  → GATE FOUNDER

  ↓

FASE 7 (automação contínua) → pipeline mantém os 20 idiomas sincronizados
```

**Por que ondas em vez de tudo de uma vez:**
- Se pipeline tem bug (ex: IA traduz "Baco" como "Bacchus"), descobrimos na Onda 1 e corrigimos antes de gastar API em 20 idiomas
- Founder não fica travado revisando 400 strings num dia só
- Trabalho técnico de CJK e RTL vira fase própria, não contamina ondas simples
- Cada onda valida uma hipótese diferente (pipeline, escala, tipografia, RTL)

---

## Prompt de execução (para outra aba/IA retomar)

```
Você é executor técnico do plano de i18n do WineGod.ai em
reports/I18N_EXECUTIVE_PLAN.md.

Repositório: C:\winegod-app
Stack: Next.js 15 + React 19 + TypeScript + Tailwind
Idioma atual: pt-BR hardcoded
Objetivo final: 20 idiomas via rollout em ondas
Restrições: sem tradutor humano, automação Claude+Gemini, orçamento baixo

Tarefa: executar FASE <N> do plano (opcionalmente ONDA <X> quando aplicável).

Antes de começar:
1. Leia reports/I18N_EXECUTIVE_PLAN.md completo
2. Leia reports/I18N_DECISIONS.md (decisões da FASE 0)
3. Se fase/onda anterior não concluída, PARE e reporte
4. Nunca pule gates do founder
5. Todo commit passa npm run build + npx tsc --noEmit sequencial
6. Sem nenhum mock de tradução — APIs reais ou pare
7. CJK e RTL exigem Fases 8 e 9 concluídas antes das Ondas 4 e 5

Entrega obrigatória:
A. O que foi executado
B. Artefatos gerados (arquivos, screenshots, logs)
C. Validação real executada
D. Gate pendente para o founder
E. Próxima fase/onda sugerida
```
