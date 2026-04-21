# WineGod.ai — Plano de Execução I18N V2.0 (Detalhado, Fases Pequenas Auditadas)

**Versão:** 2.1
**Data:** 2026-04-17
**Autor:** Claude Opus 4.7 (chefe técnico)
**Âncora de decisões:** `C:\winegod-app\reports\WINEGOD_MULTILINGUE_HANDOFF_OFICIAL.md` V2.0
**Base de código auditada:** estado real do repo em 2026-04-17 (Seção 0.2)
**Princípio operacional:** **fases pequenas (1-3h cada) com gate humano obrigatório entre cada uma**
**Substitui:** V1.0 deste plano (descontinuada após 2 rodadas de crítica externa)
**Nota projetada pós-V2:** 9.8/10 (revisor prometeu 9.6 nos ajustes técnicos; +0.2 por ideias extras de anti-surpresa)

---

## 0. Como usar este documento

### 0.1 Estrutura de cada fase

Toda fase tem o mesmo formato:

- **Número e nome** — identificação
- **Duração estimada** — em horas de Claude trabalhando
- **Entrada** — o que precisa estar pronto antes
- **Objetivo** — 1 frase
- **Arquivos afetados** — paths absolutos
- **Passos** — ordenados, acionáveis
- **Critério de aceitação** — o que Murilo verifica antes de aprovar
- **Como testar** — comando ou ação visual
- **Rollback / Forward-fix** — como desfazer OU mitigar se der errado
- **Log de auditoria** — o que gravar ao final
- **Gate** — Murilo aprova antes da próxima fase

### 0.2 Estado real do código auditado (2026-04-17)

Confirmado diretamente no repo:

**Frontend** (Next.js 15.1.0 + React 19 + TS 5.7 + Tailwind 3.4.16):
- **NÃO tem:** `next-intl`, Tolgee SDK/CLI, `middleware.ts`, `frontend/messages/`, `frontend/lib/i18n/`, ESLint config dedicado
- **TEM:** `react-markdown`, `lucide-react`, estrutura App Router completa
- Script atual: `"lint": "next lint"` em `package.json:5` — **deprecated no Next 15** ([doc oficial](https://nextjs.org/docs/15/pages/api-reference/cli/next))
- **Rota `/` hoje é o chat**, não landing. `frontend/app/page.tsx` importa `ChatHome` direto
- `frontend/app/layout.tsx` linha 36: `<html lang="pt-BR">` hardcoded. Sem `generateMetadata`

**Backend** (Flask 3.1 + anthropic 0.49.0 + Python):
- **NÃO tem:** `flask-babel`, `babel`, prompt caching configurado explicitamente
- **TEM:** `openai>=1.0.0` em `requirements.txt:8` (instalado mas **não usado ativamente** no código atual), `google-genai`, `psycopg2`, `redis`
- `backend/prompts/baco_system.py` ~500 linhas monolíticas em pt-BR
- `backend/services/baco.py:27` usa `client.messages.create(...)` simples sem `cache_control`
- `backend/routes/chat.py:818` passa apenas `message, session_id, history, photo_mode, trace` — não passa locale nem market
- `backend/routes/auth.py:127` tem `/api/auth/me` (e não `/api/me`)
- Modelo `users` em `backend/db/models_auth.py` **não tem** `ui_locale`, `market_country`, `currency_override`

**Database:** 14 migrations em `database/migrations/`. Próxima série: 015, 016, 017.

**Infra:**
- `README.md` **existe** na raiz (correção vs V1 do plano que dizia que não existia)
- `.env.example` existe apenas em `backend/`
- `DEPLOY.md` documenta Vercel (frontend) + Render (backend)
- **Domínios cross-origin:** `chat.winegod.ai` (Vercel) ↔ `api.winegod.ai` (Render). Cookies cross-domain frágeis
- **Zero ocorrências** no código para: `ENABLED_LOCALES`, `wg_locale_choice`, `ui_locale`, `market_country`, `currency_override`, `X-Vercel-IP-Country`, `Accept-Language`
- **Sem** `.github/workflows/`, CLAUDE.md tem regras de segurança (R1-R7)

**Frontend API clients (estado crítico):**
- `lib/api.ts:79` e `:111` — trata erros como texto cru; SSE `type:error` não parseado
- `lib/auth.ts:91` — descarta body de erro, retorna null
- `lib/conversations.ts:31` — só lança `HTTP ${status}`
- **Consequência:** adicionar `message_code` no backend sem refatorar clientes = usuário vê mensagens cruas ou nada

**Contagem de hardcodes pt-BR (auditoria confirmada):**
- `WelcomeScreen.tsx`: **52 strings** (saudações dinâmicas)
- `ChatInput.tsx`: 4 strings + `recognition.lang="pt-BR"` linha 298
- `Sidebar.tsx`: 16 strings
- `ajuda/page.tsx`: 100+ strings (FAQ)
- `privacy/page.tsx`, `terms/page.tsx`, `data-deletion/page.tsx`: ~150 strings
- `conta/ContaContent.tsx`: ~10
- `favoritos/FavoritosContent.tsx`: ~8
- `plano/PlanoContent.tsx`: ~20
- Mensagens erro Flask: ~40 strings

**Regras invioláveis do CLAUDE.md:**
- R5: Render pouca memória, sempre batches de 10k, evitar operações monolíticas
- R6: Gemini/APIs pagas precisam autorização explícita
- R7: Deploy Render é manual (git push NÃO dispara deploy)

### 0.3 Total de trabalho realista

~450 strings frontend + ~40 mensagens backend + ~500 linhas prompt Baco + migrations + infra = **102 fases pequenas, ~4-5 meses calendário** de Claude com gates humanos.

### 0.4 Decisão complementar: posicionamento US-facing

Decisão travada em `WINEGOD_MULTILINGUE_DECISIONS.md` após F0.1/F0.4:

- WineGod deve ser percebido como um app **global/americano** na experiência de produto.
- `en-US` é a referência de percepção internacional: copy, onboarding, CTAs, mensagens de erro, empty states, metadata e Baco em inglês.
- `pt-BR` continua suportado e importante para usuários brasileiros/Cicno, mas não deve ditar o estilo internacional.
- O app não pode parecer "app brasileiro traduzido"; nenhum texto, formato, data, moeda ou tom pt-BR deve vazar em experiência internacional.
- Limite legal: posicionamento US-facing não muda a entidade jurídica BR. Legal/termos/privacy continuam transparentes sobre operação a partir do Brasil até haver entidade/revisão jurídica US.

---

## 1. Visão macro — 13 ondas, 104 fases (V2.1)

```
ONDA 0  — Preparação (decisões + bootstrap tooling)             [6 fases]
ONDA 1  — Backend foundations (migrations + endpoints)          [8 fases]
ONDA 2  — Frontend infra (next-intl + provider + middleware)    [13 fases — +F2.3b]
ONDA 3  — ESLint guard                                          [3 fases]
ONDA 4  — Refatoração frontend                                  [20 fases]
ONDA 5  — Backend error_codes                                   [6 fases]
ONDA 6  — Baco multi-eixo                                       [13 fases]
ONDA 7  — Legal matriz enxuta                                   [8 fases]
ONDA 8  — Tolgee Cloud                                          [7 fases]
ONDA 9  — QA + release readiness (F9.7 dividida em a+b)         [10 fases]
ONDA 10 — Lançamento canário                                    [7 fases]
ONDA 11 — Observabilidade                                       [5 fases]
ONDA 12 — Pós-lançamento                                        [5 fases]
```

**Mudanças V2 → V2.1:**
- F2.3b nova (NextIntlClientProvider no root layout)
- F9.7 dividida em F9.7.a (métricas estáticas) e F9.7.b (runtime, depende Onda 11)
- F0.5 expandida (dependências agregadas)
- F2.9 reescrita (precedência única sem contradição)
- F6.4 e F6.4b com contrato fechado (builder sem `user`)

---

## 2. Políticas transversais (aplicam a todas as fases)

### 2.1 Migrations aditivas + forward-fix

- **NUNCA** `DROP COLUMN`, `DROP TABLE`, `ALTER TYPE` destrutivo em migration de i18n no Tier 1
- Toda migration: apenas `ADD COLUMN` com `DEFAULT` seguro
- Cada migration tem documento de **forward-fix** (não rollback): como mitigar se backfill ou consumo der errado sem precisar desfazer a migration
- Razão: rollback de SQL em produção com dados reais quase nunca é reversível sem perda

### 2.2 Snapshot de prompt antes de mexer em Baco

- Antes de **qualquer** fase Onda 6, copiar estado atual de `baco_system.py` / `baco/*.md` para `backend/prompts/baco/_backup/YYYY-MM-DD_HH-MM/`
- Rollback do Baco = copy-paste do snapshot (determinístico, sem Git)

### 2.3 Preview Vercel obrigatório por 48h antes de merge em main

- Toda PR que toca frontend (especialmente layout, middleware, rotas) gera preview Vercel
- Murilo navega preview no celular e desktop por 48h
- Sem preview limpo, sem merge em main

### 2.4 Feature branches por fase

- Branch: `i18n/f<N.M>-<slug>`
- 1 PR por fase. Nunca misturar fases
- ESLint enforcing em PR para main a partir da Onda 3

### 2.5 Testes obrigatórios por onda

- **Após cada fase:** `npm run build` no frontend + `python -c "import app; print('ok')"` no backend (mínimo)
- **Onda 6 (Baco):** suíte de regressão `backend/tests/test_baco_regression.py` deve passar antes de qualquer merge
- **Onda 10 (canário):** smoke test automático `scripts/i18n/smoke_test.sh` todos verdes

### 2.6 Regras críticas do CLAUDE.md aplicadas

- **R5 Render pouca memória:** migrations rodam em LOCAL primeiro, prod só após gate. Batches de 10k em backfills
- **R6 APIs pagas:** Claude (Baco) já é uso autorizado recorrente. Novos serviços (ex: OpenAI Moderation) precisam autorização explícita em F0.1
- **R7 Deploy Render manual:** toda fase backend que exige deploy lembra Murilo clicar Manual Deploy

### 2.7 Política US-facing (aplica a copy, UI, Baco, QA e legal)

- `en-US` deve ser tratado como idioma de referência para percepção global, não como tradução secundária.
- Todo texto internacional deve soar nativo em inglês americano. Proibido "traduzir literalmente" PT-BR para EN.
- Para usuário fora do Brasil ou sem país detectado, defaults de apresentação devem favorecer `en-US` e USD quando moeda não estiver definida.
- QA de i18n precisa validar ausência de sinais BR indevidos em experiência internacional: português vazando, `R$`, datas BR, tom local, disclaimers mal posicionados.
- Legal deve ser honesto: a marca pode parecer global/americana, mas termos/privacy não podem fingir entidade, endereço, incorporação ou compliance US inexistente.

---

## ONDA 0 — Preparação (sem código produtivo)

### F0.1 — Gate de realidade (19 perguntas)

- **Duração:** 1 hora (conversa founder + Claude)
- **Entrada:** Padrão Oficial V2.0 aprovado
- **Objetivo:** fechar todas as decisões estratégicas antes de código
- **Arquivos afetados:**
  - Criar: `C:\winegod-app\reports\WINEGOD_MULTILINGUE_DECISIONS.md`
- **Perguntas (14 originais + 5 novas anti-surpresa):**

**Originais (Padrão Oficial Seção 17):**
1. Tier 1 confirmado: pt-BR + en-US + es-419 + fr-FR?
2. it-IT e de-DE em Tier 1.5?
3. Consulta jurídica BR+US agora ($300-500)?
4. Consulta jurídica EU agora ($500-1500)? Bloqueante pra ativar FR como mercado comercial
5. Revisão Fiverr Tier 1 (~$135) aprovada?
6. Budget cap mensal — $100 conservador?
7. Entidade jurídica da WineGod: BR/PT/Delaware/Estônia?
8. Baseline atual de conversão pt-BR?
9. Horas/semana disponíveis no Mês 1?
10. FR ativa mercado EU agora ou só idioma?
11. Demografia dos 4M Cicno: % monolíngues vs poliglotas?
12. MX entra comercial completo ou com caution?
13. Moderação UGC entra no Tier 1?
14. Sentry e PostHog entram na Onda 11 ou só depois?

**Novas (gate de realidade anti-surpresa):**
15. **Pico de lançamento:** Se 100k dos 4M Cicno chegarem no dia do lançamento e 20% estiverem com browser em inglês, Baco aguenta responder com qualidade? Qual o teto de rate limit pro Claude API?
16. **Tradução parcial em dia D:** Se usuário francês abrir `/fr` no lançamento e tradução estiver 80% pronta, o que ele vê nas 20% faltantes? Fallback para inglês ou português?
17. **Tolgee cai no lançamento:** Site continua funcionando? (Deve ser SIM via snapshot no repo, mas força validação explícita)
18. **Locale cross-domain:** Como locale chega de `chat.winegod.ai` (Vercel) até `api.winegod.ai` (Render)? Via header `X-WG-UI-Locale` no request? Via body? Cookie cross-domain **não** é opção confiável.
19. **Link indexado desligado:** Google indexou `/fr/c/abc123`. Desligamos fr-FR. Usuário clica no link. O que acontece? 301 para `/c/abc123`? Fallback silencioso para DEFAULT? 404?

- **Critério:** todas 19 respondidas por escrito
- **Teste:** founder lê `WINEGOD_MULTILINGUE_DECISIONS.md` e confirma cada resposta
- **Rollback:** deletar arquivo, reabrir conversa
- **Log:** "F0.1 concluída — 19 decisões travadas"
- **Gate:** Murilo assina (commit com a assinatura dele no log)

### F0.2 — Criar estrutura de diretórios `shared/`

- **Duração:** 15 minutos
- **Entrada:** F0.1 concluída
- **Arquivos:**
  - Criar dirs: `shared/i18n/`, `shared/i18n/backup/`, `shared/legal/BR/`, `shared/legal/DEFAULT/`
  - (observação: **apenas 2 diretórios legal no Tier 1** — BR e DEFAULT; US fica como draft sem publicar conforme F7.0)
  - `.gitkeep` em cada pasta vazia
- **Critério:** estrutura no git
- **Teste:** `ls -la shared/`
- **Forward-fix:** se path precisar mudar depois, é renomeação de pasta
- **Log:** "F0.2"
- **Gate:** Murilo

### F0.3 — Criar `docs/I18N_README.md` e `reports/i18n_execution_log.md`

- **Duração:** 20 minutos
- **Arquivos:**
  - `docs/I18N_README.md` — índice dos docs oficiais
  - `reports/i18n_execution_log.md` — log de cada fase concluída
- **Critério:** log inicializado com F0.1 e F0.2 já registradas
- **Log:** próprio arquivo
- **Gate:** Murilo

### F0.4 — DECISÃO DE ROTEAMENTO RAIZ (crítica, antes de toda infra)

- **Duração:** 1 hora (decisão + documentação)
- **Entrada:** F0.3
- **Objetivo:** travar se `/` continua sendo chat ou vira landing pública. Decisão afeta Onda 2 inteira.
- **Contexto:**
  - Hoje `frontend/app/page.tsx` importa `ChatHome` direto
  - `AppShell.tsx:157` — logo volta para `/`
  - `auth/callback/page.tsx:17` e `:36` redirecionam para `/`
  - `LegalPage.tsx:18` linka para `/`
- **Opções:**
  - **A — Manter `/` como chat:** próximo do comportamento atual. Landing, se existir, fica em `/welcome` ou `/sobre`. Menor risco de quebra.
  - **B — Migrar `/` para landing pública, chat em `/chat`:** melhor para SEO e onboarding, mas requer atualizar 4+ lugares de redirect + comunicação de usuários existentes.
- **Decisão recomendada (chefe):** **Opção A no Tier 1.** Motivo: menor risco, 4M usuários Cicno estão acostumados com `/` sendo chat. Opção B fica como projeto futuro se métricas justificarem.
- **Arquivos:**
  - Gravar decisão em `WINEGOD_MULTILINGUE_DECISIONS.md` (pergunta 20, nova)
  - Atualizar `WINEGOD_MULTILINGUE_HANDOFF_OFICIAL.md` Seção 4.1.B com a decisão final
- **Critério:** decisão documentada e assinada por Murilo
- **Log:** "F0.4 — rota `/` fica como chat (opção A)"
- **Gate:** Murilo

### F0.5 — Bootstrap tooling: ESLint CLI real + deps de i18n e SWR (Next 15 compat)

- **Duração:** 1-2 horas
- **Entrada:** F0.4
- **Objetivo:** setup de tooling e instalação de TODAS as dependências que outras fases vão assumir existentes (evita "install surpresa" no meio de fase crítica)
- **Arquivos:**
  - `frontend/package.json` — trocar `"lint": "next lint"` por `"lint": "eslint ."`
  - Criar: `frontend/eslint.config.mjs` (flat config, Next 15 compat)

- **Instalações obrigatórias agora (concentradas em 1 fase):**
  - **ESLint stack:** `eslint`, `@next/eslint-plugin-next`, `eslint-plugin-react`, `eslint-plugin-react-hooks`, `@typescript-eslint/eslint-plugin`, `@typescript-eslint/parser`, `typescript-eslint`
  - **i18n lint:** `eslint-plugin-i18next` (consumido em F3.1; revisor apontou que faltava)
  - **Data fetching:** `swr` (consumido em F2.4c para `useEnabledLocales`; revisor apontou que faltava)
  - **Markdown (pra legal pages):** `gray-matter` (consumido em F7.1 para ler frontmatter de `shared/legal/*.md`; já que `react-markdown` existe)

- **Não instalar ainda (ficam pra fases apropriadas):**
  - `next-intl` → F2.1
  - `@tolgee/cli` → F8.x
  - `@playwright/test` → F9.3

- **Critério:**
  - `npm run lint` roda sem wizard
  - `npm ls swr eslint-plugin-i18next gray-matter` todos listados
  - Build continua passando (`npm run build`)
- **Teste:**
  - `cd frontend && npm run lint` — coerente
  - `cd frontend && npm run build` — verde
- **Forward-fix:** conflito com Next 15 → ajustar config flat; dep não resolve → pinar versão compatível
- **Log:** "F0.5 — ESLint + swr + eslint-plugin-i18next + gray-matter operacionais"
- **Gate:** Murilo

### F0.6 — Decisão: mecanismo de kill switch (flag dinâmica vs redeploy)

- **Duração:** 30 minutos (decisão)
- **Entrada:** F0.5
- **Objetivo:** definir como rollback de locale acontece em produção
- **Contexto:**
  - Vercel env var requer **redeploy** para propagar ([doc oficial](https://vercel.com/docs/environment-variables/managing-environment-variables))
  - Render env var **também** precisa redeploy manual (R7 CLAUDE.md)
  - "Kill switch em 30 segundos" via env var = fantasia técnica
- **Opções:**
  - **Plano A — Flag dinâmica via Postgres:** tabela `feature_flags(key, value_json)` lida por backend em runtime, cacheada TTL 10-30s. Frontend consulta `/api/config/enabled-locales`. Toggle real em ~10-30 segundos.
  - **Plano B — Redeploy:** `ENABLED_LOCALES` em env var, remover locale e redeployar Vercel+Render. Toggle real em ~2-5 minutos (sem downtime se saudável).
- **Decisão (chefe):** **Implementar os dois.** Plano A é kill switch principal (instantâneo). Plano B é backup resiliente (se DB cair, env var é fallback).
- **Critério:** decisão documentada
- **Log:** "F0.6 — Plano A (dinâmico) + Plano B (env var) ambos implementados"
- **Gate:** Murilo

---

## ONDA 1 — Backend foundations

### F1.1 — Criar `shared/i18n/markets.json` com 5 países

- **Duração:** 30 minutos
- **Arquivos:** `shared/i18n/markets.json` (BR, US, MX, FR, DEFAULT)
- **Critério:** JSON válido, `legal_binding_language: null` em MX/FR/DEFAULT; `DEFAULT.default_locale="en-US"` e `DEFAULT.currency_default="USD"` para reforçar posicionamento global/US-facing
- **Teste:** `node -e "console.log(Object.keys(JSON.parse(require('fs').readFileSync('shared/i18n/markets.json'))))"`
- **Forward-fix:** JSON inválido = backend falha ao carregar → rollback via Git é seguro
- **Log:** "F1.1"
- **Gate:** Murilo lê

### F1.2 — Criar `shared/i18n/dnt.md`

- **Duração:** 20 minutos
- **Arquivos:** `shared/i18n/dnt.md`
- **Critério:** cobre nomes de vinhos, castas, denominações, Baco/WineGod
- **Log:** "F1.2"
- **Gate:** Murilo

### F1.3 — Criar `shared/i18n/glossary.md` (30 termos base)

- **Duração:** 1 hora
- **Arquivos:** `shared/i18n/glossary.md`
- **Critério:** 30 termos × 4 idiomas em tabela markdown. Marcar "(DNT)" onde não traduz
- **Log:** "F1.3 — glossário draft; nativo Fiverr revisa em F12.4"
- **Gate:** Murilo aprova draft

### F1.4 — Migration 015: colunas `ui_locale`, `market_country`, `currency_override` em users

- **Duração:** 1 hora
- **Arquivos:**
  - `database/migrations/015_add_user_i18n_fields.sql`
  - `backend/db/models_auth.py` (expor campos no ORM)
- **SQL:**
  ```sql
  ALTER TABLE users ADD COLUMN ui_locale TEXT DEFAULT 'pt-BR';
  ALTER TABLE users ADD COLUMN market_country TEXT DEFAULT 'BR';
  ALTER TABLE users ADD COLUMN currency_override TEXT;
  ALTER TABLE users ADD CONSTRAINT users_ui_locale_check
    CHECK (ui_locale IN ('pt-BR','en-US','es-419','fr-FR'));
  ```
- **Forward-fix se backfill falhar:** `UPDATE users SET ui_locale='pt-BR' WHERE ui_locale IS NULL` (idempotente, roda em batches de 10k por R5)
- **Teste local:**
  - `psql $LOCAL_DB -f database/migrations/015_add_user_i18n_fields.sql`
  - `SELECT ui_locale, market_country FROM users LIMIT 5;`
- **Produção (R7):** Murilo clica Manual Deploy no Render após push
- **Log:** "F1.4 — local OK; prod pendente aprovação"
- **Gate:** Murilo autoriza execução em prod

### F1.5 — Migration 016: JSONB `description_i18n`, `tasting_notes_i18n` em wines

- **Duração:** 1 hora
- **SQL:**
  ```sql
  ALTER TABLE wines ADD COLUMN description_i18n JSONB DEFAULT '{}'::jsonb;
  ALTER TABLE wines ADD COLUMN tasting_notes_i18n JSONB DEFAULT '{}'::jsonb;
  ```
- **Forward-fix:** JSONB vazio não quebra queries existentes; não precisa mitigação
- **R5:** migration é leve, sem backfill
- **Teste local + prod:** conferir `\d wines`
- **Log:** "F1.5"
- **Gate:** Murilo autoriza prod

### F1.6 — Migration 017: tabela `feature_flags` (kill switch Plano A)

- **Duração:** 1 hora
- **SQL:**
  ```sql
  CREATE TABLE feature_flags (
    key TEXT PRIMARY KEY,
    value_json JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by TEXT
  );
  INSERT INTO feature_flags (key, value_json, description)
  VALUES ('enabled_locales',
          '["pt-BR"]'::jsonb,
          'Locales ativos em produção. Kill switch.');
  ```
- **Nota importante:** seed inicial é **apenas pt-BR** — outros locales ficam desativados até canário explícito
- **Forward-fix:** se tabela corromper, backend lê `ENABLED_LOCALES` env var (Plano B)
- **Log:** "F1.6 — feature_flags criada, seed com pt-BR apenas"
- **Gate:** Murilo autoriza prod

### F1.7 — Endpoint `PATCH /api/auth/me/preferences`

- **Duração:** 1-2 horas
- **Arquivos:** `backend/routes/auth.py` (adicionar handler)
- **Contrato:**
  ```
  PATCH /api/auth/me/preferences
  Authorization: Bearer <jwt>
  Body: { "preferences": { "ui_locale": "en-US", "market_country": "US", "currency_override": "USD" } }
  Response: 200 { "preferences": { ... } }
  ```
- **Validação:** `ui_locale` deve estar na lista fechada; `market_country` ISO alpha-2; `currency_override` ISO 4217 ou null
- **Endpoint complementar:** `GET /api/auth/me` passa a retornar `preferences` no payload (era só `user_id, email, name`)
- **Forward-fix:** se validação falhar, 400 com `message_code`
- **Teste:** curl com JWT válido
- **Log:** "F1.7 — preferences endpoint ativo"
- **Gate:** Murilo testa via dev tools

### F1.8 — Endpoint `GET /api/config/enabled-locales` (kill switch frontend-readable)

- **Duração:** 1 hora
- **Arquivos:** novo blueprint `backend/routes/config.py`
- **Contrato:**
  ```
  GET /api/config/enabled-locales
  Cache-Control: max-age=30
  Response: { "enabled_locales": ["pt-BR"], "default_locale": "pt-BR", "updated_at": "..." }
  ```
- **Fonte:** lê `feature_flags.enabled_locales` (Plano A). Se DB inacessível, lê `ENABLED_LOCALES` env var (Plano B)
- **Forward-fix:** se DB+env falharem, retorna `["pt-BR"]` hardcoded (fail-safe)
- **Log:** "F1.8"
- **Gate:** Murilo testa com curl

---

## ONDA 2 — Frontend infra

### F2.1 — Instalar `next-intl`

- **Duração:** 15 minutos
- **Arquivos:** `frontend/package.json`
- **Passos:** `cd frontend && npm install next-intl@latest`
- **Critério:** build continua passando
- **Teste:** `npm run build`
- **Log:** "F2.1"
- **Gate:** Murilo

### F2.2 — Criar estrutura `frontend/messages/` (arquivos vazios `{}`)

- **Duração:** 10 minutos
- **Arquivos:** `messages/pt-BR.json`, `en-US.json`, `es-419.json`, `fr-FR.json` todos `{}`
- **Log:** "F2.2"
- **Gate:** Murilo

### F2.3 — Configurar `next.config.ts` com `createNextIntlPlugin`

- **Duração:** 30 minutos
- **Critério:** `npm run build` passa
- **Log:** "F2.3"
- **Gate:** Murilo

### F2.3b — Bootstrap `NextIntlClientProvider` no root layout (app sem prefixo)

- **Duração:** 1-2 horas
- **Entrada:** F2.3
- **Objetivo:** garantir que `useTranslations()` funcione em rotas sem prefixo (`/`, `/chat/[id]`, `/conta`, `/favoritos`, `/plano`) — que é justamente onde o produto vive
- **Contexto do revisor:** o plano V2 tirava app routes do middleware de locale, mas não definia onde o provider é montado. Sem provider, `useTranslations()` crasha em runtime em toda rota privada.
- **Arquivos afetados:**
  - `frontend/app/layout.tsx` — envelopar children em `<NextIntlClientProvider>`
  - `frontend/i18n/request.ts` — carrega `messages` para locale resolvido (regra F2.9 aplicada server-side)
- **Passos:**
  1. Root layout faz `getLocale()` (helper custom que aplica regra F2.9 no server: cookie → header geo → fallback). Pode ser `headers()` do Next 15 para ler `X-Vercel-IP-Country` e cookie `wg_locale_choice`
  2. `getMessages()` carrega `messages/<locale>.json`
  3. `<html lang={locale}>` dinâmico
  4. `<NextIntlClientProvider locale={locale} messages={messages}>` envelopa todo children
  5. **Importante:** isso funciona para app sem prefixo (`/`, `/chat`, etc.) porque o locale vem do cookie/header, não do path
- **Critério:**
  - `useTranslations()` funciona em qualquer componente (Sidebar, ChatHome, ContaContent, etc.)
  - Troca de idioma via seletor (futuro) atualiza cookie → próximo refresh reflete
  - Rotas públicas com prefixo (`/en`, `/es`, `/fr` se usadas) continuam funcionando via middleware
- **Teste:**
  - Criar chave dummy em `pt-BR.json` (ex: `test.hello: "Olá"`)
  - Adicionar temporariamente em algum componente: `const t = useTranslations(); return <div>{t('test.hello')}</div>`
  - Verificar que aparece "Olá" em `/chat`, `/conta`, `/favoritos`
  - Remover dummy antes de commit
- **Forward-fix:** se provider quebrar renderização, isolar em `<ClientOnly>` wrapper ou ajustar carregamento de messages para async
- **Observação sobre rota `/`:** F0.4 travou que `/` continua sendo chat. Quando plano V2 menciona `/en` como teste (F10.2), entende-se `/` servido em en-US via cookie (não path). Se quiser path-prefix para teste SEO, `/en` renderiza landing placeholder. Ajuste final depende de F0.4.
- **Log:** "F2.3b — provider montado, app privado tem i18n"
- **Gate:** Murilo aprova quando dummy test funciona em `/chat`

### F2.4 — Criar `frontend/i18n/routing.ts` e `frontend/i18n/request.ts`

- **Duração:** 1 hora
- **Config-chave:**
  - `locales: ['pt-BR', 'en-US', 'es-419', 'fr-FR']`
  - `defaultLocale: 'pt-BR'`
  - `localePrefix: 'as-needed'`
  - `localeDetection: false`
- **Fallback chain** em `request.ts`: fr→en→pt, es→en→pt, en→pt, pt→só pt
- **Log:** "F2.4"
- **Gate:** Murilo

### F2.4b — Consumidor ENABLED_LOCALES no frontend (filtrar UI) + fallback normalizado backend

- **Duração:** 2 horas
- **Frontend:**
  - Hook `useEnabledLocales()` em `frontend/lib/i18n/useEnabledLocales.ts`
  - Lê `/api/config/enabled-locales` com SWR (revalidate 30s)
  - Seletor de idioma só mostra locales ativos
- **Backend:**
  - Middleware/decorator em rotas críticas (Baco, `/api/auth`, chat) que **normaliza** locale: se request vem com `ui_locale=fr-FR` mas `fr-FR` não está em `enabled_locales`, silenciosamente usa `en-US` e loga `locale_fallback{from:fr-FR, to:en-US, route:/api/chat}`
  - **NUNCA** retorna erro 400 por locale desativado (quebraria links antigos indexados)
- **Critério:** seletor frontend só mostra pt-BR (seed atual); backend aceita qualquer locale mas normaliza
- **Teste:** curl com `X-WG-UI-Locale: fr-FR` → resposta normal + log de fallback
- **Forward-fix:** se hook falhar, frontend mostra default `[pt-BR]`
- **Log:** "F2.4b — consumidor + fallback OK"
- **Gate:** Murilo testa

### F2.4c — Hook `useEnabledLocales` com SWR + revalidação

- **Duração:** 30 minutos
- **Detalhe técnico do F2.4b** separado em fase própria para controle
- **Arquivos:** `frontend/lib/i18n/useEnabledLocales.ts`
- **Comportamento:**
  - Fetch `/api/config/enabled-locales` no mount
  - Revalida a cada 30s em background
  - Retorna `{ locales: string[], defaultLocale: string, isLoading: boolean }`
  - Em falha de rede, retorna `['pt-BR']` como fallback seguro
- **Log:** "F2.4c"
- **Gate:** Murilo

### F2.5 — `frontend/middleware.ts` com next-intl (locale detection para rotas públicas)

- **Duração:** 1-2 horas
- **Escopo:** APENAS páginas públicas SEO (`/welcome` se existir, `/ajuda`, `/privacy`, `/terms`, `/data-deletion`, `/c/[id]`)
- **App routes ficam FORA:** `/chat`, `/conta`, `/favoritos`, `/plano`, `/auth/*` — locale vem de perfil/cookie `wg_locale_choice`
- **`X-Vercel-IP-Country`:** injetado como header auxiliar no response para banner de sugestão
- **Sem auto-redirect**
- **Log:** "F2.5"
- **Gate:** Murilo testa `/`, `/chat`, `/en`

### F2.5b — Middleware matcher/allowlist explícito

- **Duração:** 1 hora
- **Arquivos:** `frontend/middleware.ts` (completar export `config`)
- **Allowlist firme — middleware NÃO toca em:**
  ```
  /api/*
  /_next/*
  /auth/callback (OAuth callback, URL exata)
  /c/*/opengraph-image (OG image dinâmica)
  /favicon.ico
  /robots.txt
  /sitemap.xml
  /*.{png,jpg,svg,webp,ico,woff,woff2}
  ```
- **Critério:** login OAuth funciona, share page `/c/[id]` carrega, imagens servem normal
- **Teste:** login, abrir share link, verificar OG image
- **Forward-fix:** se algo quebrar, ajustar matcher (zero impacto de dados)
- **Log:** "F2.5b — matcher seguro"
- **Gate:** Murilo testa OAuth flow completo

### F2.6 — `frontend/lib/i18n/formatters.ts`

- **Duração:** 30 minutos
- **Exporta:** `formatCurrency`, `formatDate`, `formatNumber`, `formatRelativeTime`
- **Implementação:** `Intl.*` nativo
- **Teste unitário:** simples com cada locale
- **Log:** "F2.6"
- **Gate:** Murilo

### F2.7 — `frontend/lib/i18n/fallbacks.ts`

- **Duração:** 20 minutos
- **Função:** `getFallbackChain(locale)` → array
- **Log:** "F2.7"
- **Gate:** Murilo

### F2.8 — Build + preview Vercel verde

- **Duração:** 30 minutos
- **Passos:** push branch `i18n/onda-2`, abrir preview Vercel
- **Critério:** preview navegável; pt-BR idêntico à produção
- **Log:** "F2.8 — preview OK, aguardando 48h (política 2.3)"
- **Gate:** Murilo aprova após 48h

### F2.9 — Locale persistence end-to-end (contrato completo, regra única)

- **Duração:** 2-3 horas
- **Objetivo:** contrato de propagação de locale entre frontend, cookie, usuário logado e request do chat

- **REGRA ÚNICA DE PRECEDÊNCIA (aplica em frontend E backend, sem divergência):**

  **Esta é a ordem canônica. Frontend resolve e envia ao backend. Backend NÃO re-resolve se header/body presente — apenas valida e usa.**

  1. **`X-WG-UI-Locale` header OU `ui_locale` no body** (valor que o frontend já resolveu e enviou) — fonte autoritativa para o request atual
  2. Se ausente (request legado/externo): `user.ui_locale` do JWT decodificado (se request autenticado)
  3. Se ausente: `Accept-Language` do browser
  4. Se ausente: Geo-IP (`X-Vercel-IP-Country`) → `markets[country].default_locale`
  5. Fallback absoluto: `pt-BR`

  **Como frontend resolve antes de enviar (ordem interna, executada 1 vez por sessão e persistida):**

  1. `wg_locale_choice` cookie se usuário **trocou idioma MANUALMENTE nesta ou sessão anterior** (cookie tem TTL 1 ano)
  2. `user.ui_locale` carregado de `/api/auth/me` no login — **mas apenas na primeira carga após login**, e escreve no cookie `wg_locale_choice` sincronizando
  3. `Accept-Language` do browser
  4. Geo-IP → `markets[country].default_locale`
  5. `pt-BR`

  **Motivo da regra:** cookie manual vence `user.ui_locale` porque representa escolha explícita mais recente. Mas após login, frontend sincroniza (regra 2 escreve no cookie) — depois disso, os dois estão alinhados. Backend confia no que frontend enviar e não re-resolve.

- **Sync bidirecional pós-login:**
  - Guest escolhe fr-FR → `wg_locale_choice=fr-FR` cookie
  - Usuário faz login → frontend compara cookie vs `user.ui_locale`:
    - Se diferem E cookie é mais recente que `user.last_login` → chama `PATCH /api/auth/me/preferences { ui_locale: <cookie> }` (cookie ganha)
    - Se `user.ui_locale` é válido e cookie não existe → escreve cookie com valor do user
  - Resultado: cookie e `user.ui_locale` **sempre alinhados** após login

- **Propagação para API (cross-domain Vercel↔Render):**
  - Frontend envia em **todo** request para `api.winegod.ai`:
    - Header: `X-WG-UI-Locale: <locale>` + `X-WG-Market-Country: <country>` + `X-WG-Currency: <currency_override | null>`
    - No body de endpoints que aceitam JSON: também `{ "ui_locale": "...", "market_country": "...", "currency_override": "..." }` (redundância para robustez)
  - Backend aplica regra de precedência acima (header/body primeiro)
  - **Cookie cross-domain NÃO é caminho** (pode não chegar por restrições same-site)

- **Banner de sugestão:** aparece se geo-IP indica mismatch. Nunca força redirect.

- **Arquivos:**
  - `frontend/lib/i18n/locale-context.ts` (context provider + cookie)
  - `frontend/components/LocaleSuggestionBanner.tsx`
  - `frontend/lib/api.ts` — adicionar headers `X-WG-*` em todo request (interceptor)
  - `frontend/lib/auth.ts` — após login, sincronizar cookie → backend

- **Critério:**
  - Cookie `wg_locale_choice` grava e lê
  - Banner aparece só em mismatch
  - Login sincroniza preferência
  - Request chat inclui `X-WG-UI-Locale` header

- **Teste:**
  - Trocar idioma no seletor → cookie atualiza
  - Login → backend recebe preferência
  - DevTools Network → confirmar header em request

- **Forward-fix:** se backend não receber header (request antigo cached), fallback pra pt-BR (sem erro)

- **Log:** "F2.9 — persistence completo, cross-domain validado"
- **Gate:** Murilo testa 4 cenários (guest troca idioma; login sincroniza; banner aparece; header chega)

---

## ONDA 3 — ESLint guard

### F3.1 — Ativar regra `eslint-plugin-i18next no-literal-string` (warning)

- **Duração:** 30 minutos
- **Entrada:** F0.5 (ESLint CLI já funciona)
- **Config:** severity `warn` em feature branches
- **Escopo:** `frontend/app/**/*.tsx`, `frontend/components/**/*.tsx`
- **Allowlist:** aria-label técnicos, data-testid, URLs, classes CSS, console.log
- **Critério:** `npm run lint` retorna warnings (hardcodes existem)
- **Log:** "F3.1"
- **Gate:** Murilo

### F3.2 — Documentar baseline de warnings

- **Duração:** 20 minutos
- **Passos:** `npm run lint > reports/eslint_i18n_baseline.txt`
- **Log:** "F3.2 — baseline com N warnings documentado"
- **Gate:** Murilo

### F3.3 — GitHub Action `.github/workflows/lint.yml`

- **Duração:** 30 minutos
- **Comportamento:** roda em PR; falha se NOVOS warnings (não falha por warnings antigos; permite refactor incremental)
- **Log:** "F3.3"
- **Gate:** Murilo

---

## ONDA 4 — Refatoração frontend

### F4.0 — Normalizar error handling no frontend (pré-requisito Onda 5)

- **Duração:** 3-4 horas
- **Entrada:** F3.3
- **Objetivo:** frontend parser `{error, message_code, ...}` em todos os clients antes de backend mudar
- **Arquivos:**
  - `frontend/lib/api.ts:79` — `throw new APIError({ code, messageCode, ... })` em vez de texto cru
  - `frontend/lib/api.ts:111` — parser de SSE `type:error` idem
  - `frontend/lib/auth.ts:91` — captura body de erro, preserva `messageCode`
  - `frontend/lib/conversations.ts:31` — substitui `throw new Error('HTTP ${status}')` por `APIError`
  - Novo: `frontend/lib/i18n/translateError.ts` — helper que recebe `messageCode` e retorna string traduzida via next-intl
- **Compatibilidade:** se backend ainda retorna texto cru (pré-Onda 5), `translateError` fallback pra texto do servidor
- **Critério:** todos clients agora entendem `messageCode`; sem regressão em produção (backend não mudou ainda, tudo continua em texto pt-BR)
- **Teste:** forçar erro de API (ex: token inválido) e ver `APIError` no console
- **Forward-fix:** wrapper permite fallback gracioso
- **Log:** "F4.0 — error handling pronto para Onda 5"
- **Gate:** Murilo testa erro de login intencional

### F4.1 — Refatorar `layout.tsx` (`<html lang>` dinâmico + `generateMetadata`)

- **Duração:** 1-2 horas
- **Passos:**
  - `<html lang={locale}>` lendo do contexto next-intl
  - `export async function generateMetadata({ params })` traduz title/description via chaves `metadata.root.*`
  - Popular chaves em `messages/pt-BR.json` e `messages/en-US.json`; `en-US` deve ser copy nativa US-facing, não tradução literal
- **Critério:** view-source mostra `lang="pt-BR"` ainda, metadata igual
- **Log:** "F4.1"
- **Gate:** Murilo

### F4.2 — Popular chaves iniciais em 4 locales

- **Duração:** 30 minutos
- **pt-BR:** preservar sentido atual.
- **en-US:** preencher pelo menos metadata, navegação crítica, erros genéricos e empty states com copy US-facing polida. Não deixar `en-US` como `""`/`null` nas áreas que aparecerão no canário.
- **es-419/fr-FR:** podem começar como `""` ou `null` quando ainda dependem de Onda 8, mas fallback deve cair em `en-US` antes de `pt-BR`.
- **Log:** "F4.2"
- **Gate:** Murilo

### F4.3 — Refatorar `AppShell.tsx` (1 string)

- **Duração:** 20 minutos
- **Log:** "F4.3"
- **Gate:** Murilo

### F4.4 — Refatorar `Sidebar.tsx` (16 strings)

- **Duração:** 2 horas
- **Namespace:** `sidebar.*`
- **Log:** "F4.4"
- **Gate:** Murilo testa sidebar

### F4.5 — Refatorar `UserMenu.tsx` (2 strings)

- **Duração:** 30 minutos
- **Log:** "F4.5"
- **Gate:** Murilo

### F4.6 — Refatorar `CreditsBanner.tsx` (2 strings)

- **Duração:** 30 minutos
- **Log:** "F4.6"
- **Gate:** Murilo

### F4.7 — Refatorar `SearchModal.tsx` (2 strings)

- **Duração:** 30 minutos
- **Log:** "F4.7"
- **Gate:** Murilo

### F4.8 — Refatorar `ChatInput.tsx` (4 strings + `recognition.lang` dinâmico)

- **Duração:** 1-2 horas
- **Chave crítica:** `recognition.lang = ui_locale` (lido do context) em vez de `"pt-BR"` hardcoded
- **Teste:** gravação de voz em pt-BR continua funcional
- **Log:** "F4.8"
- **Gate:** Murilo testa voz

### F4.9 — Refatorar `ChatHome.tsx` (5 strings)

- **Duração:** 1 hora
- **Log:** "F4.9"
- **Gate:** Murilo

### F4.10 — Refatorar `MessageBubble.tsx` (data formatting via util)

- **Duração:** 1 hora
- **Mudança:** `toLocaleString('pt-BR')` → `formatDate(date, locale)` (util de F2.6)
- **Log:** "F4.10"
- **Gate:** Murilo

### F4.11 — Refatorar `WelcomeScreen.tsx` (52 strings, 4 sub-fases)

- **Duração total:** 4-6 horas

**F4.11.a — Estrutura de chaves (30 min):** definir namespace `welcome.greeting.<period>.<guest|named>` + `welcome.cards.*`

**F4.11.b — Substituição das saudações (2-3h):** mapear 4 períodos × 7 dias × 2 variantes → chaves ICU com seletor

**F4.11.c — Cards array (1h):** 6 cards → `welcome.cards.N.title/prompt`

**F4.11.d — Validação visual (30 min):** testar saudação em 4 horários simulados (mock Date)

- **Log:** "F4.11 — 4 sub-fases concluídas"
- **Gate:** Murilo por sub-fase

### F4.12 — `conta/ContaContent.tsx` (~10 strings)

- **Duração:** 1-2 horas
- **Log:** "F4.12"
- **Gate:** Murilo

### F4.13 — `favoritos/FavoritosContent.tsx` (~8 strings)

- **Duração:** 1 hora
- **Log:** "F4.13"
- **Gate:** Murilo

### F4.14 — `plano/PlanoContent.tsx` (~20 strings)

- **Duração:** 2 horas
- **Log:** "F4.14"
- **Gate:** Murilo

### F4.15 — `ajuda/page.tsx` (100+ strings, 4 sub-fases)

- **Duração total:** 6-8 horas

**F4.15.a** — Navegação + cabeçalho (1-2h)
**F4.15.b** — FAQ Chat + Fotos (2h)
**F4.15.c** — FAQ Notas + Créditos + Compartilhar + Conta (2h)
**F4.15.d** — Glossário + Contato (1-2h)

- **Log:** "F4.15"
- **Gate:** Murilo por sub-fase

### F4.16 — `auth/callback/page.tsx`

- **Duração:** 30 minutos
- **Cuidado:** rota está na allowlist do middleware (F2.5b). Aqui só traduz strings visuais
- **Log:** "F4.16"
- **Gate:** Murilo testa login

### F4.17 — `c/[id]/*` (share público + OG image)

- **Duração:** 2 horas
- **OG image:** texto traduzido via classe `review`
- **Log:** "F4.17"
- **Gate:** Murilo testa share link

### F4.18 — `not-found.tsx`

- **Duração:** 30 minutos
- **Log:** "F4.18"
- **Gate:** Murilo

### F4.19 — Ativar ESLint `no-literal-string` como **error** em PR para main

- **Duração:** 30 minutos
- **Entrada:** F4.1-F4.18 todas completas
- **Log:** "F4.19 — lint enforcing hard"
- **Gate:** Murilo

---

## ONDA 5 — Backend error_codes

### F5.1 — Refatorar `auth.py` (8 strings) para `{error, message_code}`

- **Duração:** 1 hora
- **Formato novo:** `jsonify({"error": "missing_field", "message_code": "errors.auth.missing_code", "field": "code"}), 400`
- **Log:** "F5.1"
- **Gate:** Murilo

### F5.2 — Refatorar `auth_facebook.py`, `auth_apple.py`, `auth_microsoft.py`

- **Duração:** 1-2 horas
- **Log:** "F5.2"
- **Gate:** Murilo

### F5.3 — Refatorar `chat.py` (2 strings)

- **Duração:** 30 minutos
- **Log:** "F5.3"
- **Gate:** Murilo

### F5.4 — Refatorar `conversations.py` (10 strings)

- **Duração:** 1-2 horas
- **Log:** "F5.4"
- **Gate:** Murilo

### F5.5 — Popular `messages/*.json` com namespace `errors.*`

- **Duração:** 1 hora
- **Log:** "F5.5"
- **Gate:** Murilo

### F5.6 — `country_names.py` multilíngue (parâmetro `locale`)

- **Duração:** 2-3 horas
- **Adicionar:** dicts en-US, es-419, fr-FR (84 países cada)
- **Assinatura:** `iso_to_name(code, locale='pt-BR')`
- **Callers:** atualizar onde for chamado com `user.ui_locale` (ou locale do request)
- **Log:** "F5.6"
- **Gate:** Murilo

---

## ONDA 6 — Baco multi-eixo

### F6.1 — Criar `backend/prompts/baco/base.md` (regras imutáveis)

- **Duração:** 1-2 horas
- **Snapshot antes:** copiar `baco_system.py` para `_backup/YYYY-MM-DD/` (política 2.2)
- **Extrair:** R1-R13, persona base, proteções anti-Vivino, "nunca inventar dados"
- **Log:** "F6.1"
- **Gate:** Murilo lê

### F6.2 — Criar `backend/prompts/baco/dnt.md`

- **Duração:** 15 minutos
- **Copy-paste de `shared/i18n/dnt.md`**
- **Log:** "F6.2"
- **Gate:** Murilo

### F6.3 — Criar `backend/prompts/baco/language/pt-BR.md` (voz brasileira)

- **Duração:** 2-3 horas
- **Extrair maneirismos brasileiros:** esquecimento cômico, superlativos, gírias, tom
- **Critério:** overlay captura 100% da voz atual
- **Log:** "F6.3"
- **Gate:** Murilo lê e aprova

### F6.4 — Criar `backend/prompts/baco_prompt_builder.py` (contrato final fechado)

- **Duração:** 2-3 horas
- **CONTRATO ÚNICO (fechado, sem argumentos redundantes):**
  ```python
  def build_baco_system(ui_locale: str, market_country: str) -> str:
      """
      Builder nao depende de user. Recebe apenas os 2 primitivos
      que o request resolveu (via regra de precedencia F2.9).
      market_policy e resolvido internamente via markets.json[market_country].
      """
      base = read('baco/base.md')
      language = read(f'baco/language/{ui_locale}.md')
      dnt = read('baco/dnt.md')
      market_policy = load_markets_json()[market_country]
      market_block = render_market_context(market_policy)
      return compose(base, language, dnt, market_block)
  ```
- **Motivo:** revisor apontou contradição — plano V2 ora passava `user`, ora `user + ui_locale + country`. V2.1 decide: **builder NÃO recebe user**. Recebe apenas `ui_locale` e `market_country` (strings). Isso desacopla builder de ORM, facilita testes, serve guest e logado com o mesmo código.
- **Sem prompt caching ainda** (F6.5b)
- **Teste unitário:** `test_baco_prompt_builder.py` valida output com combinações (pt-BR/BR, en-US/US, fr-FR/FR, etc.)
- **Log:** "F6.4 — contrato builder(ui_locale, market_country) fechado"
- **Gate:** Murilo

### F6.4b — Propagar locale/market da rota até o serviço (contrato fechado)

- **Duração:** 2 horas
- **Contexto crítico:** frontend e backend são cross-domain (`chat.winegod.ai` ↔ `api.winegod.ai`). Cookie não confiável.
- **Contrato de assinatura (fechado, sem user):**
  ```python
  # backend/services/baco.py
  def get_baco_response(
      message: str,
      session_id: str,
      history: list,
      photo_mode: bool,
      trace,
      ui_locale: str,        # NOVO — resolvido via precedencia F2.9
      market_country: str,   # NOVO — idem
  ) -> dict:
      system = build_baco_system(ui_locale, market_country)
      # ... resto igual ao fluxo atual
  ```
  **Serviço NÃO recebe `user`.** Recebe apenas os 2 primitivos. Alinhamento total com F6.4.
- **Mudanças:**
  - `frontend/lib/api.ts` — em request ao `/api/chat`, inclui `ui_locale` e `market_country` no body + headers `X-WG-UI-Locale`, `X-WG-Market-Country`
  - `backend/routes/chat.py:818` — aplica regra F2.9 de precedência e resolve `ui_locale` e `market_country` como strings antes de chamar o serviço
  - Passa para `get_baco_response(..., ui_locale=..., market_country=...)`
  - `backend/services/baco.py:15` — nova assinatura (acima)
- **Compatibilidade:** request antigo sem headers → backend aplica precedência (user.ui_locale se logado, senão pt-BR/BR) e chama serviço com strings resolvidas. Serviço nunca vê `None`.
- **Guest flow:** `session_id` + headers resolve; não depende de cookie backend
- **Log:** "F6.4b — contrato (ui_locale, market_country) end-to-end"
- **Gate:** Murilo testa chat com `X-WG-UI-Locale: en-US` via DevTools

### F6.5 — Substituir BACO_SYSTEM_PROMPT velho pelo builder no `services/baco.py`

- **Duração:** 1-2 horas
- **CRÍTICO:** fase de maior risco do projeto
- **Snapshot antes:** `_backup/baco_pre_F6.5/`
- **Mudanças:**
  - `services/baco.py:27` — `system = build_baco_system(user, market_policy, ui_locale, country)` substitui `BACO_SYSTEM_PROMPT`
  - `BACO_SYSTEM_PROMPT` antigo continua importado como **fallback de emergência** (deprecated, remover em F6.10)
  - Sem prompt caching ainda
- **Teste obrigatório (regressão):** 5 perguntas padrão do `baco_test_results.md` retornam respostas equivalentes em tom e conteúdo
- **Rollback:** reverter import + commit
- **Log:** "F6.5 — builder ativo, 5 perguntas verdes"
- **Gate:** Murilo faz 5 perguntas em staging

### F6.5b — Prompt caching SIMPLES (modo automático)

- **Duração:** 2-3 horas
- **Objetivo:** implementar caching do jeito mais simples antes de refinar
- **Referência oficial:** [Anthropic prompt caching](https://platform.claude.com/docs/pt-BR/build-with-claude/prompt-caching)
- **Passos:**
  1. Validar SDK atual (`anthropic==0.49.0`) suporta `cache_control`. Se não, upgrade para versão compatível (`>=0.50`)
  2. Em `services/baco.py`, mudar `system=<string>` para `system=[{"type": "text", "text": <builder_output>, "cache_control": {"type": "ephemeral"}}]`
  3. **Apenas 1 bloco de system com cache_control** no final (modo simples)
  4. Não refatorar em múltiplos blocks ainda
- **Medição:** coletar `response.usage.cache_read_input_tokens` e `cache_creation_input_tokens` por 48h em staging
- **Critério:** sem regressão em respostas; medição funcionando
- **Forward-fix:** se caching quebrar resposta, remover `cache_control` e ficar no modo sem cache
- **Log:** "F6.5b — caching simples ativo, medindo"
- **Gate:** Murilo testa

### F6.5c — Avaliar hit rate e refinar SE necessário

- **Duração:** 1 hora (decisão + eventual refatoração)
- **Entrada:** 48h de dados F6.5b
- **Regra:**
  - Hit rate ≥ 40% → **PARAR**. Caching simples é suficiente. Documentar métrica e fechar.
  - Hit rate < 40% → refatorar system em múltiplos blocks (base | language | dnt separados, cada um com `cache_control`). Medir novamente 48h.
- **Log:** "F6.5c — hit rate X%, decisão Y"
- **Gate:** Murilo aprova decisão

### F6.6 — Suíte de regressão curada

- **Duração:** 2-3 horas
- **Arquivos:** `backend/tests/test_baco_regression.py`
- **Estrutura:**
  - 10 perguntas padrão × 4 locales = 40 casos
  - Cada caso tem snapshot de resposta em `tests/snapshots/baco_<locale>_<Q>.json`
  - Assertions: (a) resposta contém N keywords esperadas, (b) NÃO contém palavras proibidas (Vivino, "como IA", "sou um modelo"), (c) idioma da resposta = locale esperado (detecção via heuristic ou `langdetect`)
  - String similarity ≥ 0.7 com snapshot de referência
- **Executa em CI** antes de qualquer merge que toque `prompts/baco/*` ou `services/baco.py`
- **Log:** "F6.6 — regressão curada"
- **Gate:** Murilo aprova suíte

### F6.7 — Criar `language/en-US.md` (voz americana)

- **Duração:** 2-3 horas
- **Adaptação cultural** (não tradução literal)
- **Critério US-facing:** Baco em inglês deve soar como sommelier digital nativo americano/global: natural, premium, direto, sem calques de português, sem gírias brasileiras traduzidas.
- **Prioridade:** `en-US` é overlay de referência internacional. `es-419` e `fr-FR` podem adaptar culturalmente, mas não devem copiar vícios do pt-BR.
- **Log:** "F6.7"
- **Gate:** Murilo testa 10 perguntas (F6.6)

### F6.8 — Criar `language/es-419.md`

- **Duração:** 2-3 horas
- **Log:** "F6.8"
- **Gate:** Murilo

### F6.9 — Criar `language/fr-FR.md`

- **Duração:** 2-3 horas
- **Cuidado extra:** vocabulário vinícola francês (terroir, cépage, millésime)
- **Log:** "F6.9"
- **Gate:** Murilo

### F6.10 — Desativar `baco_system.py` velho (manter 30 dias como fallback emergencial)

- **Duração:** 30 minutos
- **Marcar:** comentário `# DEPRECATED — remove after 2026-07-17 (30 dias post-F6.5)`
- **Log:** "F6.10"
- **Gate:** Murilo

---

## ONDA 7 — Legal matriz enxuta

### F7.0 — Matriz legal final (2 células ativas apenas)

- **Duração:** 1 hora (decisão + documentação)
- **Decisão:** publicamos **apenas**:
  1. `/legal/BR/pt-BR/{privacy,terms,cookies,data-deletion}` — LGPD
  2. `/legal/DEFAULT/en-US/{privacy,terms,cookies,data-deletion}` — disclaimer "operated from Brazil"
- **Fallback:** toda outra combinação (FR+fr-FR, US+es-419, etc.) **redireciona** para `/legal/DEFAULT/en-US/<doc>` com banner: "This page is shown in English because your jurisdiction-language pair is not yet published."
- **Não criar** URLs para combinações inexistentes. Frontend retorna 404 se `<country>/<lang>` não é 1 das 2 células.
- **Path único:** `/legal/:country/:lang/:doc`
- **Log:** "F7.0 — matriz 2 células, fallback para DEFAULT"
- **Gate:** Murilo aprova

### F7.1 — Migrar `privacy/page.tsx` para ler `shared/legal/BR/pt-BR/privacy.md`

- **Duração:** 2 horas
- **Passos:**
  - Extrair conteúdo do `.tsx` para markdown
  - Nova rota `/legal/:country/:lang/privacy` renderiza com react-markdown
  - `/privacy` (URL antiga) redireciona para `/legal/BR/pt-BR/privacy` (301 para preservar SEO)
  - Atualizar links internos em `terms/page.tsx:85`, `privacy/page.tsx:91`, `LegalPage.tsx:18`, `AppShell.tsx` (legal link no footer)
- **Log:** "F7.1"
- **Gate:** Murilo testa links

### F7.2 — Migrar `terms/page.tsx`

- **Duração:** 1 hora
- **Log:** "F7.2"
- **Gate:** Murilo

### F7.3 — Migrar `data-deletion/page.tsx` (com `DeleteAccountSection` intacto)

- **Duração:** 1-2 horas
- **Cuidado:** componente interativo `DeleteAccountSection.tsx` — separar lógica de texto
- **Log:** "F7.3"
- **Gate:** Murilo

### F7.4 — Criar `shared/legal/DEFAULT/en-US/*.md` (disclaimer "operated from Brazil")

- **Duração:** 2-3 horas
- **4 arquivos:** privacy, terms, cookies, data-deletion
- **Frontmatter:** `version: 1.0`, `effective_date: <F12.5>`, `binding_language: null`, `jurisdiction: DEFAULT`
- **Disclaimer obrigatório no topo:** "This is an automated/template document. Service operated from Brazil. LGPD applies."
- **Log:** "F7.4 — DEFAULT/en-US publicado"
- **Gate:** Murilo aprova texto

### F7.5 — Criar 404 handler para combinações `<country>/<lang>` inexistentes

- **Duração:** 1 hora
- **Comportamento:** se usuário acessa `/legal/FR/fr-FR/privacy`, sistema detecta que não está publicado → redireciona (302) para `/legal/DEFAULT/en-US/privacy` + banner visual
- **Log:** "F7.5"
- **Gate:** Murilo

### F7.6 — Componente `AgeGate.tsx` + integração middleware

- **Duração:** 2-3 horas
- **Passos:**
  - Modal com 2 botões: "I'm {age}+ years old" / "I'm not"
  - `age` lido de `markets.json[country].age_gate_minimum`
  - Cookie `wg_age_verified=<country>-<timestamp>` TTL 1 ano
  - Middleware bloqueia rotas **se `age_gate_required: true` E cookie ausente**, **exceto** allowlist de F2.5b + `/legal/*` + `/age-verify`
- **Textos:** classe `legal` (revisão obrigatória)
- **Log:** "F7.6"
- **Gate:** Murilo testa 1ª visita (ver modal) + aceita (próxima visita não mostra)

### F7.7 — Popular chaves `legal.*` e `age_gate.*`

- **Duração:** 1 hora
- **Log:** "F7.7"
- **Gate:** Murilo

---

## ONDA 8 — Tolgee Cloud

### F8.1 — Criar conta + projeto + 4 locales

- **Duração:** 30 minutos
- **Founder executa, Claude guia**
- **Plano Free** (500 keys, 3 seats)
- **Log:** "F8.1"
- **Gate:** Murilo confirma acesso

### F8.2 — Secrets `TOLGEE_API_KEY` em GitHub + Vercel + Render

- **Duração:** 20 minutos
- **Log:** "F8.2"
- **Gate:** Murilo

### F8.3 — Importar `messages/pt-BR.json` inicial

- **Duração:** 30 minutos
- **Passos:** Claude roda `tolgee push` local
- **Log:** "F8.3"
- **Gate:** Murilo navega Tolgee UI

### F8.4 — Importar glossary (se plano permitir)

- **Duração:** 30 minutos
- **Condicional:** Free pode não ter glossary nativo. Fica como TM se limitado.
- **Log:** "F8.4"
- **Gate:** Murilo

### F8.5 — GitHub Action `tolgee-push.yml` (pós-merge main)

- **Duração:** 1-2 horas
- **Log:** "F8.5"
- **Gate:** Murilo

### F8.6 — GitHub Action `tolgee-pull.yml` (cron + PR bot, nunca auto-merge)

- **Duração:** 2-3 horas
- **Comportamento:** cron diário → pull → abre PR → Claude revisa → merge manual
- **Log:** "F8.6"
- **Gate:** Murilo

### F8.7 — Backup semanal (domingo 02:00 UTC)

- **Duração:** 1 hora
- **Cron:** `tolgee pull --all` → commit em `shared/i18n/backup/`
- **Log:** "F8.7"
- **Gate:** Murilo

---

## ONDA 9 — QA + release readiness

### F9.1 — Script `scripts/i18n/validate_plurals.py` (CLDR)

- **Duração:** 2 horas
- **Log:** "F9.1"
- **Gate:** Murilo

### F9.2 — Script `smoke_test.sh` (4 locales carregam sem erro)

- **Duração:** 1-2 horas
- **Log:** "F9.2"
- **Gate:** Murilo

### F9.3 — Instalar Playwright + config local

- **Duração:** 1 hora
- **Log:** "F9.3"
- **Gate:** Murilo

### F9.4 — Testes Playwright visuais (sem Claude Vision)

- **Duração:** 3-4 horas
- **Escopo:** 5-8 rotas × 4 locales × 2 viewports ≈ 64 screenshots
- **Comparação:** `pixelmatch` puro
- **Log:** "F9.4"
- **Gate:** Murilo

### F9.5 — Script pseudo-localização

- **Duração:** 1-2 horas
- **Log:** "F9.5"
- **Gate:** Murilo

### F9.6 — Checklist QA `scripts/i18n/QA_CHECKLIST.md`

- **Duração:** 30 minutos
- **Log:** "F9.6"
- **Gate:** Murilo

### F9.7 — Release readiness report (dividida: métricas disponíveis agora vs após instrumentação)

- **Duração:** 2-3 horas
- **Não é dashboard web** (revisor apontou que não existe infra de admin/roles)

- **F9.7.a — Release readiness report (fonte: dados já existentes na Onda 9):**
  - Script `scripts/i18n/release_readiness_report.py` gera `reports/i18n_health_<date>.md`
  - **Métricas que FUNCIONAM antes da Onda 11 (já disponíveis):**
    - % chaves traduzidas por locale (conta chaves em `messages/<locale>.json` vs `pt-BR.json`)
    - % pending review no Tolgee (via Tolgee API)
    - Lint status (`npm run lint --format json`)
    - Build status (último CI run)
    - Smoke test status (F9.2)
    - Pseudo-loc visual diff count (F9.5)
    - Playwright screenshot diff count (F9.4)
  - Endpoint `GET /api/admin/i18n-health` protegido por header `Authorization: Bearer <ADMIN_SECRET>` (env var)
  - Sem UI. Acesso via curl/Postman.
  - **Log:** "F9.7.a — métricas estáticas de tradução/CI disponíveis"

- **F9.7.b — Report extendido (só ativa após Onda 11 — Sentry + PostHog):**
  - **Condicional:** essa fase é EXECUTADA apenas após F11.2 (Sentry com tags) e F11.4 (eventos PostHog).
  - **Métricas que dependem de instrumentação:**
    - Hit rate prompt caching 7d (precisa Sentry breadcrumbs + log `response.usage` no `tracing.py` — fase F11.2.b adicional de instrumentação)
    - Gasto API por serviço (precisa instrumentar `backend/services/tracing.py:123` para gravar `tokens_in`, `tokens_out`, `model`, `cost_usd` por call)
    - Missing key rate por locale (precisa evento `translation_missing_key` do PostHog — criado em F11.4)
    - `locale_fallback_applied` rate (F11.4)
    - Erro JS por locale (Sentry filtrado)
  - Mesmo script, mesmo endpoint, seção "Runtime metrics" só aparece com dados se instrumentação existe
  - **Log:** "F9.7.b — métricas runtime condicionadas a Onda 11"
  - **Gate:** Murilo só aprova F9.7.b APÓS F11.2 + F11.4 completas

- **Gate F9.7 (geral):** Murilo testa curl de F9.7.a e confirma que seção runtime fica "N/A — aguarda Onda 11"

### F9.8 — Teste de fogo pré-canário (Fiverr 30min nativo por idioma)

- **Duração:** 1-2 semanas (externo)
- **Budget:** $30/idioma × 3 = $90 (en-US, es-419, fr-FR)
- **Brief:** nativo usa staging por 30min, relatório escrito + opcional gravação
- **Brief obrigatório en-US:** avaliar se o app parece produto global/americano nativo ou "app brasileiro traduzido"; marcar qualquer português vazando, tom estranho, moeda/data inadequada, CTA artificial ou Baco com inglês não nativo.
- **Para es-419:** instrução explícita de marcar regionalismos (MX vs AR)
- **Critério:** feedback objetivo antes do canário respectivo
- **Log:** "F9.8"
- **Gate:** Murilo recebe 3 relatórios

### F9.9 — Teste URLs indexadas com locale desligado

- **Duração:** 2 horas
- **Objetivo:** validar que desligar um locale não gera 404s em links públicos já indexados
- **Cenário Playwright:**
  1. Simular `enabled_locales=['pt-BR','fr-FR']` (fr-FR ativo)
  2. Criar share link `/fr/c/abc123`
  3. Simular mudança para `enabled_locales=['pt-BR']` (fr-FR desligado)
  4. Acessar `/fr/c/abc123` → esperar comportamento definido em F0.1 pergunta 19
- **Comportamentos aceitáveis:**
  - Fallback silencioso para DEFAULT (conteúdo em en-US) — preferível
  - Redirect 301 para `/c/abc123` — aceitável
- **Inaceitável:** 404 puro
- **Log:** "F9.9"
- **Gate:** Murilo

---

## ONDA 10 — Lançamento canário

### F10.0 — Shadow mode LEVE (contadores locale decision, sem PII)

- **Duração:** 2 horas
- **Objetivo:** validar lógica de `markets.json` e resolução de locale em produção **sem mudar comportamento**
- **Implementação:**
  - Tabela `locale_decision_counters (hour_bucket, detected_locale, final_locale, count)` (migration 018)
  - Middleware e routes incrementam counter por hora sem PII (sem user_id, sem IP)
  - **NÃO loga prompt do Baco** (LGPD risk rejeitado)
  - **NÃO compara semanticamente** (ruído + sem infra de embeddings)
- **Observação:** contadores agregados permitem ver "quantos requests teriam caído em fr-FR se estivesse ativo"
- **Rodar por 7 dias** antes de F10.2
- **Log:** "F10.0 — shadow leve ativo"
- **Gate:** Murilo confirma contadores subindo

### F10.1 — Deploy `enabled_locales=['pt-BR']` (baseline zero-risk)

- **Duração:** 30 minutos
- **Passo:** UPDATE `feature_flags` SET value_json='["pt-BR"]' (via SQL direto com credencial protegida; F12.1 documenta)
- **Critério:** produção em pt-BR idêntica
- **Observação:** Plano A (dinâmico) aplica em ~10s (TTL cache). Plano B (env var) teria exigido redeploy
- **Log:** "F10.1 — pt-BR limpo"
- **Gate:** Murilo navega 24h

### F10.2 — Ativar `en-US` (Plano A dinâmico)

- **Duração:** 30 minutos
- **Passo:** `UPDATE feature_flags SET value_json='["pt-BR","en-US"]' WHERE key='enabled_locales'`
- **Teste:** Murilo + 3 amigos usam `/en`
- **Rollback:** reverter UPDATE (10-30s TTL cache)
- **Log:** "F10.2"
- **Gate:** Murilo + testers aprovam

### F10.3 — Monitorar en-US por 48h

- **Duração:** observação passiva
- **Log:** "F10.3"
- **Gate:** Murilo

### F10.4 — Ativar `es-419`

- **Duração:** 30 minutos
- **Log:** "F10.4"
- **Gate:** Murilo

### F10.5 — Monitorar es-419 por 48h

- **Log:** "F10.5"
- **Gate:** Murilo

### F10.6 — Ativar `fr-FR` (como idioma, sem mercado comercial)

- **Duração:** 30 minutos
- **Cuidado:** FR `commercial_enabled=false`, `purchase_cta_allowed=false` em markets.json — CTAs ocultos
- **Log:** "F10.6"
- **Gate:** Murilo

---

## ONDA 11 — Observabilidade

### F11.1 — Instalar Sentry frontend

- **Duração:** 2 horas
- **Log:** "F11.1"
- **Gate:** Murilo

### F11.2 — Sentry backend + tags `locale`, `market_country`

- **Duração:** 2 horas
- **Log:** "F11.2"
- **Gate:** Murilo

### F11.3 — Instalar PostHog

- **Duração:** 1-2 horas
- **Log:** "F11.3"
- **Gate:** Murilo

### F11.4 — Eventos customizados

- **Duração:** 1-2 horas
- **Eventos:** `locale_switch`, `translation_missing_key`, `translation_report_submitted`, `locale_fallback_applied`
- **Log:** "F11.4"
- **Gate:** Murilo

### F11.5 — Dashboard inicial conversão por locale (PostHog)

- **Duração:** 2 horas
- **Nada de admin custom; usa Insights nativo do PostHog**
- **Log:** "F11.5"
- **Gate:** Murilo

---

## ONDA 12 — Pós-lançamento

### F12.1 — Runbook kill switch (`docs/RUNBOOK_I18N_ROLLBACK.md`)

- **Duração:** 30 minutos
- **Conteúdo:**
  ```
  ## Plano A (instantâneo — preferencial)
  Acesso: psql / endpoint admin protegido
  UPDATE feature_flags SET value_json='["pt-BR","en-US"]' WHERE key='enabled_locales';
  Tempo: ~10-30s (TTL cache)

  ## Plano B (resiliente — se Plano A falhar)
  Vercel: Settings → Env → remover locale do ENABLED_LOCALES → redeploy
  Render: Environment → idem → redeploy manual (R7)
  Tempo: ~2-5 min
  ```
- **Log:** "F12.1"
- **Gate:** Murilo

### F12.2 — Runbook disaster recovery Tolgee (`docs/RUNBOOK_I18N_DISASTER.md`)

- **Duração:** 30 minutos
- **Log:** "F12.2"
- **Gate:** Murilo

### F12.3 — Documentar limitações (`docs/I18N_LIMITATIONS.md`)

- **Duração:** 1 hora
- **Conteúdo:**
  - Search/filtros Tier 1 match exato apenas
  - Reviews em idioma misto on-demand
  - CJK/RTL não suportado
  - Moderação UGC ainda não ativa (aguarda F0.1 pergunta 13)
  - Legal: só 2 células (BR/pt-BR + DEFAULT/en-US); outras combinações fallback
- **Log:** "F12.3"
- **Gate:** Murilo

### F12.4 — Fiverr Tier 1 (UI + Baco cultural + glossary + legal)

- **Duração:** 1-2 semanas externo
- **Budget:** ~$135 (3 idiomas × ~$45 total)
- **Critério adicional:** revisão en-US valida explicitamente posicionamento US-facing/global-first em UI, Baco, glossary e legal DEFAULT/en-US.
- **Log:** "F12.4"
- **Gate:** Murilo aceita entregas

### F12.5 — Consulta jurídica BR+US (se aprovado F0.1 P3)

- **Duração:** 1-2 semanas externo
- **Budget:** $300-500
- **Entrega:** templates validados, `effective_date` atualizado, `binding_language` preenchido
- **Log:** "F12.5"
- **Gate:** Murilo arquiva documentação

---

## 3. Ordem recomendada (caminho crítico)

| Período | Ondas |
|---|---|
| Semana 1-2 | Onda 0 + Onda 1 (decisões + backend foundations) |
| Semana 3-4 | Onda 2 + Onda 3 (frontend infra + ESLint guard) |
| Semana 5-8 | Onda 4 (refatoração arquivo por arquivo) |
| Semana 9 | Onda 5 (backend error_codes) |
| Semana 10-12 | Onda 6 (Baco — mais delicada) |
| Semana 13 | Onda 7 (legal enxuta) |
| Semana 14 | Onda 8 (Tolgee) |
| Semana 15 | Onda 9 (QA + release readiness) |
| Semana 16-18 | Onda 10 (canário gradual + shadow mode 7 dias) |
| Semana 19 | Onda 11 (observabilidade) |
| Semana 20+ | Onda 12 (Fiverr + jurídico + runbooks) |

**Total calendário realista: ~4-5 meses** com gates + revisões + externos.

---

## 4. Log de auditoria

Toda fase concluída adiciona entrada em `C:\winegod-app\reports\i18n_execution_log.md`:

```markdown
## F<N.M> — <Nome da fase>
- **Data concluída:** YYYY-MM-DD HH:MM
- **Duração real vs estimado:** Xh vs Yh
- **Arquivos modificados:** <lista com paths absolutos>
- **Testes rodados:** <comandos + resultado>
- **Critério de aceitação:** ✅ ou ❌
- **Observações:** <o que deu errado, se algo>
- **Forward-fix aplicado:** <se houve>
- **Aprovado por Murilo em:** YYYY-MM-DD HH:MM
```

---

## 5. Regras de segurança durante execução

1. **1 PR por fase.** Nunca misturar
2. **Feature branches:** `i18n/f<N.M>-<slug>`
3. **Preview Vercel 48h obrigatório** em fases de frontend críticas (Onda 2, 4, 7)
4. **Produção nunca quebra.** Preview valida antes
5. **Migrations aditivas + forward-fix** (política 2.1). Rodam em LOCAL primeiro, prod após gate (R5)
6. **Baco (Onda 6):** snapshot antes + testes regressão obrigatórios (política 2.2 + F6.6)
7. **APIs pagas:** Claude autorizado recorrente. Outros serviços (OpenAI Moderation, Gemini) exigem autorização F0.1 (R6)
8. **Deploy Render manual** após push (R7). Toda fase backend lembra Murilo clicar Manual Deploy

---

## 6. Projeção de nota

- **Estado inicial V1:** 8.2/10 (crítico externo)
- **V2 após aceitar 10 críticas + 4 correções refinadas + ideias extras:** 9.5/10 (crítico externo confirmou)
- **V2.1 após 5 correções de acabamento (precedência única, provider, contrato Baco, F9.7 dividida, deps agregadas em F0.5):** **9.8/10 projetado**

Risco residual impedindo 10/10: jurídico EU (só resolve com advogado EU, decisão F0.1 P4).

### Diff V2 → V2.1 (o que mudou)

1. **F2.9** — precedência única sem contradição; regra firme que frontend resolve e backend confia (não re-resolve). Sync bidirecional pós-login com cookie vs `user.ui_locale` documentado.
2. **F2.3b NOVA** — bootstrap `NextIntlClientProvider` no root layout para app sem prefixo funcionar. Sem isso, `useTranslations()` crasha em `/chat`, `/conta`, etc.
3. **F6.4 e F6.4b** — contrato do Baco fechado: builder recebe `(ui_locale, market_country)` como strings, NÃO recebe `user`. Alinhamento end-to-end.
4. **F9.7 dividida em F9.7.a + F9.7.b** — métricas disponíveis agora (tradução, lint, CI, smoke) vs métricas condicionadas à instrumentação da Onda 11. Report não promete o que não tem fonte.
5. **F0.5 expandida** — instala `swr`, `eslint-plugin-i18next`, `gray-matter` upfront (antes eram "assumidas" por F2.4c, F3.1, F7.1 sem fase de install).

---

## 7. Próximo passo literal

**F0.1 — responder as 19 perguntas do gate de realidade.**

Sem F0.1 assinada por Murilo, nenhuma outra fase pode começar.

---

**Fim do Plano de Execução V2.0.**
