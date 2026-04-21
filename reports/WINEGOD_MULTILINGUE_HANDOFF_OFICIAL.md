# WineGod.ai — Padrão Oficial de I18N

**Versão:** 2.0 (revisada por Claude sobre base do Codex)
**Data:** 2026-04-17
**Status:** documento mestre oficial (handoff de arquitetura)
**Autoridade:** este documento é a referência principal para qualquer decisão de internacionalização do WineGod.ai
**Substitui como padrão operacional:** `WINEGOD_MULTILINGUE_PLANO_FINAL_ARQUIVADO.md`, `WINEGOD_MULTILINGUE_PLANO_ENXUTO_ARQUIVADO.md`, `WINEGOD_MULTILINGUE_REJEITADOS.md`, `WINEGOD_MULTILINGUE_HANDOFF_ARQUIVADO.md`, `I18N_PADRAO_OFICIAL.md` V1.0 (Codex, pré-renomeação)

**Plano de execução vigente (COMO implementar):** `C:\winegod-app\reports\WINEGOD_MULTILINGUE_PLANO_EXECUCAO.md` V2.1
- 13 ondas, 104 fases pequenas auditáveis (1-3h cada)
- Gate humano obrigatório entre cada fase
- Preparação → Backend foundations → Frontend infra → ESLint → Refatoração → Backend error_codes → Baco multi-eixo → Legal → Tolgee → QA → Canário → Observabilidade → Pós-lançamento
- Nota projetada: 9.8/10 (após 3 rodadas de revisão crítica externa aplicadas)
- Este handoff define o QUÊ e o POR QUÊ; o plano de execução define o COMO e o QUANDO

**Próximo passo literal:** F0.1 do plano de execução — responder as 19 perguntas do gate de realidade para gerar `C:\winegod-app\reports\WINEGOD_MULTILINGUE_DECISIONS.md`.

**Mudança vs V1 (Codex):** incorporou 8 itens do V4 que o Codex tinha omitido (backup Tolgee, validação CLDR, checklist cultural, JSONB schema, Intl formatters, timezone, kill switch runbook, migração Cicno) sem perder as 7 correções técnicas que o Codex acertou (Vercel geo, founder fora do CLI, shared JSON, app sem prefixo, Tolgee Free honesto, legal_binding null, OpenAI credenciais).

---

## 0. LEIA PRIMEIRO — Contexto obrigatório para qualquer IA consultada

**Se você é uma IA sendo consultada sobre este projeto, leia esta seção antes de qualquer coisa. Ela define a régua com que todas as decisões arquiteturais foram tomadas. Não sugira itens que violem esta régua sem justificativa explícita.**

### 0.1 Quem é o founder e qual a realidade dele

- **Murilo**, founder solo do WineGod.ai
- **Não é programador** (entende conceitos, mas não debuga CI/CD sozinho)
- **Não tem equipe** (nem dev, nem QA, nem ops, nem jurídico interno)
- **Orçamento apertado** — pré-receita, bootstrapped
- **Tem uma audiência acumulada** — ~4M usuários do Cicno esperando o lançamento, o que adiciona pressão de qualidade (não é startup zero)
- **Depende do Claude (esta IA)** como principal força executora

### 0.2 O que ele quer

Internacionalizar o WineGod.ai para **3 a 5 idiomas no início**, com qualidade suficiente para não queimar a audiência do Cicno, **sem virar um projeto grande que ele não consegue manter**.

**Posicionamento de produto decidido após F0.1:** o WineGod deve ser percebido como um app global/americano na experiência. Isso significa `en-US` como referência de copy internacional, tom de marca, onboarding, CTAs, mensagens de erro e Baco em inglês. `pt-BR` continua suportado e importante para usuários brasileiros/Cicno, mas a experiência internacional não deve parecer "app brasileiro traduzido".

**Limite obrigatório:** posicionamento US-facing não muda a realidade jurídica. Enquanto a entidade for BR, legal/termos/privacy devem continuar transparentes sobre operação a partir do Brasil e usar DEFAULT/en-US quando não houver template jurídico específico.

**Idiomas iniciais decididos:**
- `pt-BR` (base, já existe)
- `en-US` (global, mercado US)
- `es-419` (América Latina unificada)
- `fr-FR` (mercado consumidor de vinho; entra como idioma, mas França como mercado comercial só depois)

**Opcionais Tier 1.5** (entram depois de 30 dias de Tier 1 estável):
- `it-IT`
- `de-DE`

**NÃO entram no Tier 1 de jeito nenhum:** russo, polonês, japonês, chinês, coreano, árabe, hebraico, turco (ficam para Tier 2/3 aspiracional).

### 0.3 A régua mestra (princípio que decide tudo)

**Esta é a frase mais importante do documento:**

> **Não é para dispensar NADA que seja 100% necessário para prestar um bom serviço em outros idiomas. E tudo que for "grande" (parecer enterprise) MAS também for barato + fácil de manter + ampliar alcance, ENTRA no plano.**

Em outras palavras:
- Plano enxuto ≠ plano mínimo
- Plano enxuto = **máximo valor por unidade de esforço e dinheiro investidos**
- Se algo parece "de empresa grande" mas é grátis/barato + fácil + previne dor → entra mesmo assim
- Se algo parece "simples" mas trava a operação ou exige DevOps → fica fora

### 0.4 Como Claude aplica a régua (o filtro das 3 perguntas)

Todo item proposto para este projeto passa por 3 perguntas:

1. **É necessário para prestar bom serviço nos 3-5 idiomas?**
   - Se sim → entra, mesmo se parecer grande
   - Se não → passa para a pergunta 2
2. **É barato de implementar agora?**
   - Barato = custa poucas horas E/OU até ~$20/mês recorrente
   - Se sim → passa para a pergunta 3
3. **É fácil de manter?**
   - Fácil = não exige DevOps, não quebra sozinho, não pede atenção semanal do founder
   - Se sim → entra
   - Se não → fica fora

**Regra de desempate:** na dúvida, **entra**, porque cortar algo que viraria caro de consertar depois é pior que instalar uma proteção barata agora.

### 0.5 Exemplos concretos do filtro aplicado

Para deixar claro como a régua funciona:

| Item | Parece... | Na régua | Decisão | Motivo |
|---|---|---|---|---|
| Prompt caching Anthropic | Avançado/enterprise | ~4h trabalho + economia 30-70% | **ENTRA** | Barato + amplia qualidade do Baco |
| ESLint anti-hardcode escopado | Enterprise process | 1 arquivo config + previne bug silencioso | **ENTRA** | Custo quase zero + protege qualidade |
| `hreflang` SEO simétrico | Complexo | next-intl gera automático | **ENTRA** | Grátis + amplia alcance (Google indexa) |
| Age gate modal | Pesado | 50 linhas código + cookie | **ENTRA** | Obrigatório legal + barato |
| Market Matrix JSON | Enterprise | 1 arquivo compartilhado, 5 países iniciais | **ENTRA** (versão mínima) | Controla tudo de 1 lugar só |
| Backup semanal Tolgee | Enterprise SRE | GitHub Action cron, zero custo | **ENTRA** | Preventivo puro, protege contra Tolgee fora do ar |
| Validação CLDR plurais | Enterprise QA | Script 30 linhas, roda em CI | **ENTRA** | Pega bug silencioso em fr/ru/pl antes de produção |
| Observabilidade com tag locale | Enterprise SRE | 2 linhas em Sentry/PostHog | **ENTRA** quando Sentry/PostHog existirem | Permite filtrar bugs por idioma |
| Auto-rollback com thresholds | Enterprise SRE | Precisa volume que não temos | **FICA FORA** | Sem volume vira ruído, manual resolve |
| Playwright + Claude Vision completo | QA profissional | Dias de setup + $5-15/mês | **FICA FORA** | Playwright local simples sem Vision basta |
| Tolgee Team €49/mês desde dia 1 | Enterprise | Free resolve até 500 keys | **FICA FORA** | Upgrade proativo em 400 keys, não antes |
| flask-babel backend | Best practice | Complexo sem valor vs `error_code` puro | **FICA FORA** | Simplificar backend é melhor |
| Baco com markdown por país | Parece cuidadoso | 30+ arquivos pra manter | **FICA FORA** | Explosão combinatorial, 1 overlay por idioma basta |
| Consulta jurídica EU $1500 | Proteção | Caro + mercados EU não ativados | **FICA FORA** (agora) | Só quando lançar mercado EU comercial |
| Founder rodando CLI (git/tolgee pull) | Parece "simples" | Founder não é dev | **FICA FORA** | Operação técnica é 100% Claude/CI |

**Padrão emergente:** o que é **barato + automático + preventivo** entra. O que é **caro + manual + só-depois** fica fora. O que depende de **founder virar DevOps** fica fora mesmo se for gratis.

---

## 1. Reality Check do Código Atual

Antes de definir arquitetura alvo, este é o estado real do repositório hoje. **Qualquer futura IA que afirmar que uma peça "já existe" sem conferir estas seções está errando.**

### 1.1 Stack atual confirmada

- Frontend: Next.js 15 App Router + TypeScript + Tailwind
- Backend: Flask (Python)
- Frontend deploy: **Vercel**
- Backend deploy: Render
- Banco: Postgres no Render

Arquivos que confirmam isso:
- `C:\winegod-app\frontend\package.json`
- `C:\winegod-app\backend\app.py`
- `C:\winegod-app\DEPLOY.md`
- `C:\winegod-app\CLAUDE.md`

### 1.2 O que NÃO existe ainda

As seguintes peças **não estão instaladas nem configuradas** no repo atual:

- `next-intl`
- Tolgee SDK / CLI
- `frontend/messages/*`
- `frontend/middleware.ts`
- Sentry
- PostHog
- `flask-babel` (e não vai existir — ver Seção 3.6)
- Playwright config do projeto
- ESLint config de i18n
- `shared/i18n/markets.json`
- `shared/i18n/glossary.md`
- `shared/i18n/dnt.md`
- `shared/legal/*`

**Isso significa:** o padrão oficial pode adotar essas peças, mas nunca deve ser descrito como "já pronto, só configurar". Cada peça é trabalho concreto.

### 1.3 Superfície monolíngue atual

O projeto hoje está cheio de texto, formatação e comportamento presos em pt-BR.

Pontos confirmados no código:

- `frontend/app/layout.tsx` com metadata fixa e `lang="pt-BR"` hardcoded
- `frontend/components/Sidebar.tsx` com labels e tooltips hardcoded
- `frontend/components/WelcomeScreen.tsx` com saudações e sugestões hardcoded
- `frontend/components/ChatInput.tsx` com placeholder, alerts e reconhecimento de voz travado em `pt-BR`
- `frontend/components/MessageBubble.tsx` com horário em `pt-BR`
- `frontend/app/conta/ContaContent.tsx` com data em `pt-BR`
- `frontend/app/favoritos/FavoritosContent.tsx` com data em `pt-BR`
- Páginas legais inteiras em português
- Backend retornando erros textuais em português
- `backend/utils/country_names.py` gerando nomes de países em PT-BR
- `backend/db/models_auth.py` sem campos `ui_locale`, `market_country`, `currency_override`
- `backend/prompts/baco_system.py` monolítico em pt-BR

### 1.4 Consequência prática

Internacionalização no WineGod **não é apenas trocar strings**. Ela afeta:

- Copy
- Roteamento
- Metadata
- Formatação de data, hora e moeda
- Headers e geolocalização
- Contratos de erro de API
- Exibição de país e moeda
- Comportamento do Baco
- Fluxo de revisão operacional
- Páginas legais
- Observabilidade

---

## 2. Decisões Travadas

Esta seção é o coração do documento. O que está aqui fica travado até revisão formal.

### 2.1 Idiomas do Tier 1

Já definido na Seção 0.2.

**Tier 1 ativo:** pt-BR, en-US, es-419, fr-FR
**Tier 1.5 condicional:** it-IT, de-DE
**Fora do Tier 1/1.5:** russo, polonês, ucraniano, turco, japonês, chinês, coreano, árabe, hebraico

### 2.2 Separação obrigatória de idioma, mercado e moeda

Regra central e absoluta.

O sistema usa **três campos separados**:

- `ui_locale` — idioma da UI (lista fechada)
- `market_country` — país para compliance/regulação (ISO alpha-2 qualquer)
- `currency_override` — moeda escolhida, nullable

**Regra absoluta: `ui_locale` nunca é derivado de `market_country`.**

Exemplos corretos:
- Brasileiro no Japão: `ui_locale=pt-BR`, `market_country=JP`, `currency_override=JPY`
- Mexicano nos EUA: `ui_locale=es-419`, `market_country=US`, `currency_override=USD`

Exemplos proibidos (locales sintéticos):
- `pt-JP`
- `en-BR`
- `es-DE`

`ui_locale` deve ser **sempre um destes valores aceitos no Tier 1:**
- `pt-BR`, `en-US`, `es-419`, `fr-FR`

### 2.3 Fonte de verdade dividida

| Artefato | Fonte de verdade | Quem mexe |
|---|---|---|
| Nomes de chave (código) | Repo | Claude/dev |
| Copy base `pt-BR` | Repo | Claude/dev em PR |
| Traduções alvo | Tolgee UI | Founder aprova, Claude/CI sincroniza |
| Metadata/glossário/contexto | Tolgee + `shared/i18n/` no repo | Founder + Claude |
| Build final | Repo | CI / Claude |

**Regra operacional firme:** founder **nunca** edita JSON na mão, **nunca** roda CLI para sincronizar tradução. Toda operação técnica é 100% Claude/CI.

### 2.4 Biblioteca i18n frontend: next-intl + ICU

- `next-intl`: biblioteca padrão
- ICU MessageFormat: obrigatório desde dia 1 quando houver plural, count, gênero, condição textual

Motivos:
- Compatível com Next.js App Router
- Maduro
- Resolve plural, gênero e placeholders corretamente
- Não exige inventar camada caseira

### 2.5 TMS: Tolgee Cloud

**Regra de expectativa honesta (importante):**

- Começa no plano Free (500 keys, 3 seats, 10.000 MT credits)
- **Nunca afirmar** "Claude dentro do Tolgee Free" como garantia. O AI Translator do Tolgee depende do plano ativo no momento da contratação. Este documento não promete um recurso premium sem validar no momento de uso.
- MT/AI usada via: (a) recursos do Tolgee conforme plano ativo, (b) ou fluxos externos separados com credenciais próprias
- Upgrade para paid tier (Team ~€49/mês) acontece quando houver necessidade real:
  - Mais de 500 keys
  - Glossário nativo (não está no Free)
  - Fluxo avançado de revisão
  - Recursos pagos de QA

**Estratégia de upgrade:** **proativa em ~400 keys** (80% do limite Free), não reativa em 500. Evita transição sob pressão.

### 2.6 Backend i18n: error_code puro, sem flask-babel no Tier 1

Backend devolve códigos, frontend traduz.

Formato oficial de erro:

```json
{
  "error": "wine_not_found",
  "message_code": "errors.wine.not_found"
}
```

Para outros casos:
- Emails: templates estruturais + dicionário JSON de strings (puxado do mesmo catálogo frontend)
- Push notifications: payload montado com string traduzida via dict JSON compartilhado
- Mensagens server-side pontuais: dict JSON

**Regra:** backend não deve depender de catálogo gettext (flask-babel) no Tier 1.

### 2.7 Baco: arquitetura simplificada

Estrutura oficial no Tier 1:

- 1 prompt base forte (`base.md`)
- 1 overlay curto por idioma suportado (`language/<bcp47>.md`)
- 1 arquivo DNT/glossário (`dnt.md`)
- Política de mercado **injetada em runtime** como texto estruturado curto (vindo de `shared/i18n/markets.json`)

**Proibido no Tier 1:**
- Markdown por país (`market/*.md`)
- Persona diferente para cada mercado
- Nome do Baco traduzido por idioma (Baco é marca universal)
- Reset de memória ao trocar idioma

**Regra da memória:** mensagens antigas permanecem no idioma original em que foram escritas. Trocar idioma muda apenas a UI e a instrução atual ao Baco. Sem tradução retroativa.

### 2.8 FR é idioma ativo, mas mercado FR é não-comercial no Tier 1

Isto fica travado para evitar a contradição do V4 (que dizia que legal seria em francês com binding explícito sem advogado EU).

**Estado correto de FR no Tier 1:**

- Idioma `fr-FR` ativo
- País `FR` mapeado como **mercado parcial**
- Sem CTA comercial
- Sem ativação comercial EU
- Sem prometer compliance EU completa
- `legal_binding_language` fica **`null`** (não inventar valor sem advogado EU)

Config oficial de FR:

```
enabled = partial
commercial_enabled = false
purchase_cta_allowed = false
baco_mode = educational
seo_indexable = partial
legal_template = DEFAULT
legal_binding_language = null
```

### 2.9 Geolocalização: Vercel geo headers

**Regra técnica:** o padrão oficial usa **Vercel geo headers** no frontend.

Header canônico:
- `X-Vercel-IP-Country` (também disponível via `geo.country` no middleware Next.js)

**Não usar como padrão:**
- `CF-IPCountry` (Cloudflare)

Motivo: frontend roda na Vercel, middleware executa no runtime da Vercel. Cloudflare headers podem ou não existir dependendo do setup; Vercel headers são garantidos.

### 2.10 Observabilidade: Sentry e PostHog são stack alvo, não stack atual

**Estado real:** Sentry e PostHog **não existem hoje** no repositório.

**Regra de expectativa:**
- Este documento trata Sentry/PostHog como stack-alvo
- Não podem ser descritos como "já integrados"
- A integração é trabalho concreto (F3 ou F4)

**Quando adicionados, devem receber:**
- Tag `locale`
- Tag `market_country`

**Ganho:** filtrar bugs e analytics por idioma/país.

### 2.11 Moderação de UGC (se ativada)

Se moderação de UGC entrar no Tier 1:
- **Usar OpenAI Moderation API com credenciais OpenAI dedicadas**
- Moderation API da OpenAI é gratuita para usuários da API da OpenAI

**Explicitamente proibido:** descrever como "OpenAI Moderation via API key Anthropic" ou qualquer confusão de credenciais. São vendors separados.

**Decisão se entra ou não:** pergunta aberta Seção 18.

### 2.12 Fallback de idioma hierárquico

Ordem de fallback de chaves:
- `fr-FR` → `en-US` → `pt-BR`
- `es-419` → `en-US` → `pt-BR`
- `en-US` → `pt-BR`
- `pt-BR` → sem fallback externo

**Motivo:** para usuários não-lusófonos, inglês é fallback mais seguro que português.

### 2.13 Schema de banco para conteúdo multilíngue

Para descrições e notas de vinhos que podem ser traduzidas:

```sql
-- migration em wines table
ALTER TABLE wines ADD COLUMN description_i18n JSONB DEFAULT '{}';
ALTER TABLE wines ADD COLUMN tasting_notes_i18n JSONB DEFAULT '{}';
-- Formato: {"pt-BR": "...", "en-US": "...", "es-419": "...", "fr-FR": "..."}
```

**Regras:**
- `wines.name`, `wines.variety` (castas), denominações: **NUNCA traduzidos** (TEXT normal)
- `wines.country`, `wines.region`: usar `backend/utils/country_names.py` (já existe)
- Descrições e tasting notes: JSONB multilíngue com fallback em código (`description_i18n->>ui_locale` ou `description_i18n->>'en-US'` ou `description_i18n->>'pt-BR'`)

**Por que JSONB:** flexível, sem `ALTER TABLE` para cada idioma novo, Postgres 16 indexa bem.

---

## 3. Estrutura Canônica do Projeto

### 3.1 Diretórios novos a criar

```text
C:\winegod-app\shared\i18n\
  markets.json          # Matrix de países/mercados
  glossary.md           # Wine Glossary (termos técnicos + traduções canônicas)
  dnt.md                # Do Not Translate list (nomes próprios, marcas)

C:\winegod-app\frontend\messages\
  pt-BR.json
  en-US.json
  es-419.json
  fr-FR.json

C:\winegod-app\backend\prompts\baco\
  base.md
  dnt.md                # simbolicamente mesmo conteúdo de shared/i18n/dnt.md
  language\
    pt-BR.md
    en-US.md
    es-419.md
    fr-FR.md

C:\winegod-app\shared\legal\
  BR\                   # LGPD templates
  US\                   # CCPA templates
  DEFAULT\              # Disclaimer "operated from Brazil"

C:\winegod-app\shared\i18n\backup\    # Backups semanais do Tolgee (via CI)
  latest\
  2026-W16\
  2026-W15\
```

### 3.2 Por que `shared/i18n/markets.json` (não `backend/config/markets.yaml`)

- Frontend e backend precisam ler a mesma fonte
- JSON é trivial para TS e Python (sem parser YAML)
- Diretório `shared/` é neutro (não acopla a frontend nem backend)
- Evita "frontend depende de arquivo backend-only"

### 3.3 Formato mínimo de `shared/i18n/markets.json`

```json
{
  "BR": {
    "enabled": true,
    "tier": 1,
    "default_locale": "pt-BR",
    "supported_locales": ["pt-BR", "en-US"],
    "currency_default": "BRL",
    "commercial_enabled": true,
    "purchase_cta_allowed": true,
    "baco_mode": "commercial",
    "age_gate_required": true,
    "age_gate_minimum": 18,
    "seo_indexable": true,
    "legal_template": "BR",
    "legal_binding_language": "pt-BR"
  },
  "US": {
    "enabled": true,
    "tier": 1,
    "default_locale": "en-US",
    "supported_locales": ["en-US", "es-419"],
    "currency_default": "USD",
    "commercial_enabled": true,
    "purchase_cta_allowed": true,
    "baco_mode": "commercial",
    "age_gate_required": true,
    "age_gate_minimum": 21,
    "seo_indexable": true,
    "legal_template": "US",
    "legal_binding_language": "en-US"
  },
  "MX": {
    "enabled": true,
    "tier": 1,
    "default_locale": "es-419",
    "supported_locales": ["es-419", "en-US"],
    "currency_default": "MXN",
    "commercial_enabled": true,
    "purchase_cta_allowed": true,
    "baco_mode": "commercial",
    "age_gate_required": true,
    "age_gate_minimum": 18,
    "seo_indexable": true,
    "legal_template": "DEFAULT",
    "legal_binding_language": null
  },
  "FR": {
    "enabled": "partial",
    "tier": 1,
    "default_locale": "fr-FR",
    "supported_locales": ["fr-FR", "en-US"],
    "currency_default": "EUR",
    "commercial_enabled": false,
    "purchase_cta_allowed": false,
    "baco_mode": "educational",
    "age_gate_required": true,
    "age_gate_minimum": 18,
    "seo_indexable": "partial",
    "legal_template": "DEFAULT",
    "legal_binding_language": null,
    "notes": "Idioma ativo, mercado comercial EU bloqueado ate juridico EU."
  },
  "DEFAULT": {
    "enabled": "partial",
    "tier": 1,
    "default_locale": "en-US",
    "supported_locales": ["pt-BR", "en-US"],
    "currency_default": "USD",
    "commercial_enabled": false,
    "purchase_cta_allowed": false,
    "baco_mode": "educational",
    "age_gate_required": true,
    "age_gate_minimum": 18,
    "seo_indexable": false,
    "legal_template": "DEFAULT",
    "legal_binding_language": null
  }
}
```

### 3.4 Inventário futuro

Países futuros (IT, DE, PT, UK, RU, PL, JP, CN, KR, SA, AE, IL) podem ser documentados como `enabled: false` com `tier: 1.5/2/3` para **inventário de roadmap**. Não é promessa de implementação, apenas documentação para não esquecer contexto em 6 meses.

---

## 4. Modelo Oficial de Roteamento e Locale

### 4.1 Dois modelos separados

O projeto usa **dois modelos distintos de roteamento** conforme o tipo de rota.

#### A. Páginas públicas SEO

Exemplos:
- `/welcome` ou `/sobre` (landing futura, se existir)
- `/en/welcome`, `/es/welcome`, `/fr/welcome` (landings localizadas futuras)
- Páginas públicas futuras (`/wines`, `/producers`, `/blog`, `/legal/*`, `/ajuda` público)

**Regra:**
- A raiz `/` NÃO é landing no Tier 1; ela continua sendo o chat atual com Baco (decisão F0.4, Opção A)
- `pt-BR` fica sem prefixo
- `en-US`, `es-419`, `fr-FR` usam prefixo de locale (`/en`, `/es`, `/fr`)
- Sem redirecionamento automático agressivo
- Se houver mismatch detectado via geo-IP, mostra **banner discreto** de sugestão, nunca redireciona

#### B. App routes privadas

Exemplos:
- `/` (entrada canônica atual do chat com Baco)
- `/chat`, `/chat/[id]`, `/c/[id]` se existirem como rotas internas/alias
- `/conta`, `/favoritos`, `/plano`
- `/auth/*`

**Regra (diferente do V4 — correção importante):**
- **Sem prefixo de locale na URL** no Tier 1
- Locale da app vem de: `user.ui_locale` se logado, depois cookie `wg_locale_choice`, depois fallback `pt-BR`
- Motivo: reduz risco em auth, sessão, deep link, navegação interna. URLs como `/en/chat/abc123` vs `/chat/abc123` podem causar problemas de auth/redirect/deep-link que não valem o ganho de SEO (rotas privadas nem indexam).

### 4.2 Ordem canônica de resolução de locale

**Páginas públicas:**
1. Locale explícito na URL (`/fr/...`)
2. Cookie `wg_locale_choice` (se usuário escolheu)
3. `X-Vercel-IP-Country` → lookup em `markets.json` → `default_locale` do país
4. Fallback `pt-BR`

**App routes (sem prefixo):**
1. `user.ui_locale` se logado
2. Cookie `wg_locale_choice`
3. Fallback `pt-BR`

### 4.3 Regra de UX: sem auto-redirect

Não fazer auto-redirect de idioma na primeira versão.

Se houver mismatch (ex: URL `/en/`, mas geo-IP = BR):
- Mostrar sugestão discreta via banner
- Nunca mover o usuário sem ele pedir

### 4.4 Migração dos 4M usuários do Cicno

Em primeira visita pós-migração:
- Detecta `Accept-Language` header
- Se detectar idioma suportado ≠ pt-BR, mostra **banner de sugestão** ("Prefere em inglês?")
- Usuário confirma ou mantém pt-BR
- Escolha persistida em `users.ui_locale` (se logado) ou cookie

Sem forçar idioma. Sem redirecionar. Apenas oferecer.

### 4.5 Formatação Intl (moeda, data, número, tempo relativo)

**Regra:** toda formatação passa por util único. Nunca formatação manual no componente.

Frontend (`frontend/lib/i18n/formatters.ts`):
```typescript
// Usa next-intl useFormatter() ou Intl.* diretamente
export const formatCurrency = (amount: number, currency: string, locale: string) => ...
export const formatDate = (date: Date, locale: string) => ...
export const formatNumber = (num: number, locale: string) => ...
export const formatRelativeTime = (date: Date, locale: string) => ...
```

Backend (Python): usa `babel.numbers` e `babel.dates` (leve, já é dependência comum).

**Timezone de display:**
- Usar timezone do **browser do usuário** (via `Intl.DateTimeFormat().resolvedOptions().timeZone`)
- Fallback: UTC
- Motivo: brasileiro no Japão espera horário local do Japão, não do Brasil

---

## 5. Padrão de Conteúdo e Chaves

### 5.1 Classes oficiais de conteúdo (3, não 6)

| Classe | O que é | Tratamento |
|---|---|---|
| `auto` | UI mecânica (botões, menus, labels, tooltips) | MT + deploy direto |
| `review` | Onboarding, ajuda, CTAs, email subjects, Baco cultural | MT + revisão humana (founder no Tolgee) |
| `legal` | Terms, privacy, age gate, disclaimers, alcohol-sensitive | MT + revisão humana obrigatória |

### 5.2 Naming convention

Padrão: `escopo.secao.acao` (snake_case implícito no último nível)

Exemplos:
- `sidebar.nav.new_chat`
- `welcome.hero.subtitle`
- `errors.network.timeout`
- `plan.free.title`
- `legal.privacy.title`
- `baco.greeting.first_time`

**Namespaces reservados:** `errors.*`, `legal.*`, `baco.*`, `email.*`, `age_gate.*`, `push.*`, `wine_glossary.*`

### 5.3 Ciclo de vida

- Criar chave nova quando semântica muda (não renomear em massa)
- Renomear: proibido. Deprecia antiga com `"_deprecated": "use X — remove after YYYY-QQ"`
- Remover chave só 90 dias após deprecação confirmada
- Mudar texto source pt-BR: permitido. Source hash normalizado (lowercase, sem pontuação trivial) compara; se mudou, dispara re-tradução

### 5.4 Regra de hardcode

Texto de interface pública **não entra hardcoded** em componente. ESLint `eslint-plugin-i18next` no-literal-string enforcing:

- **Escopo:** `frontend/app/**/*.tsx`, `frontend/components/**/*.tsx`
- **Ignora:** tests, config, scripts, storybook
- **Severity:** warning em feature branches, error em PR para main
- **Allowlist:** aria-label técnicos, data-testid, URLs, classes CSS, console.log
- **Bypass:** label `hotfix` em PR permite bypass com issue auto-criada

### 5.5 ICU obrigatório

ICU MessageFormat obrigatório sempre que houver:
- Plural
- Count
- Gênero
- Condição textual

Exemplo correto:
```json
"wines_count": "{count, plural, =0 {Nenhum vinho} one {# vinho} other {# vinhos}}"
```

### 5.6 Validação CLDR de plurais no CI

Script `scripts/i18n/validate_plurals.py` roda no CI.

Verifica que toda chave ICU tem as formas de plural necessárias por idioma target:
- `en-US`, `es-419`, `fr-FR`: `one`, `other`
- `ru-RU` (Tier 2): `one`, `few`, `many`, `other`
- `pl-PL` (Tier 2): `one`, `few`, `many`, `other`
- `ar-*` (Tier 3): `zero`, `one`, `two`, `few`, `many`, `other`

Se faltar forma, CI falha. Custo: zero. Pega bug silencioso antes de produção.

---

## 6. Padrão de Dados do Usuário

### 6.1 Campos obrigatórios

Migration em `backend/db/models_auth.py`:

```sql
ALTER TABLE users ADD COLUMN ui_locale TEXT;
ALTER TABLE users ADD COLUMN market_country TEXT;
ALTER TABLE users ADD COLUMN currency_override TEXT;
```

### 6.2 Validação

`ui_locale` deve ser sempre um destes valores (lista fechada Tier 1):
- `pt-BR`
- `en-US`
- `es-419`
- `fr-FR`

Não aceitar valor arbitrário. CHECK constraint no Postgres ou validação no ORM.

### 6.3 Backfill

Usuários existentes migram com:
- `ui_locale = 'pt-BR'`
- `market_country = 'BR'`
- `currency_override = NULL` (usa default BRL de `markets.BR.currency_default`)

### 6.4 Sessão guest (não logado)

Guest usa:
- Cookie de locale (`wg_locale_choice`)
- Inferência de mercado via `X-Vercel-IP-Country` no público
- Fallback `pt-BR`

### 6.5 Conversas existentes

No Tier 1:
- Mensagens antigas permanecem no idioma original em que foram escritas
- Trocar idioma muda apenas a UI e a instrução atual ao Baco
- Sem tradução retroativa automática do histórico (ver Seção 2.7)

---

## 7. Baco — Padrão Oficial

### 7.1 Estrutura alvo

```text
backend/prompts/baco/
  base.md
  dnt.md
  language/
    pt-BR.md
    en-US.md
    es-419.md
    fr-FR.md
```

### 7.2 O que cada camada faz

- `base.md`: regras fixas, persona, segurança, voz central (R1-R13 do CLAUDE.md)
- `language/*.md`: ajuste curto de tom por idioma (voz brasileira vs francesa vs americana vs latino)
- `dnt.md`: nomes e termos que nunca podem ser traduzidos
- Política de mercado: bloco injetado em runtime vindo de `shared/i18n/markets.json`

### 7.3 Builder runtime

```python
def build_baco_system(user, market_policy):
    parts = [
        read('baco/base.md'),
        read(f'baco/language/{user.ui_locale}.md'),
        read('baco/dnt.md'),
    ]
    market_block = f"""
---
MARKET CONTEXT:
- Country: {market_policy.country}
- Legal drinking age: {market_policy.age_gate_minimum}
- Currency: {market_policy.currency_default}
- Commercial recommendations: {'allowed' if market_policy.purchase_cta_allowed else 'restricted'}
- Baco mode: {market_policy.baco_mode}
"""
    parts.append(market_block)
    return '\n\n---\n\n'.join(parts)
```

### 7.4 O que fica proibido no Tier 1

- Markdown por país (pasta `market/*.md`)
- Persona diferente para cada mercado
- Nome do Baco traduzido por idioma (Baco é **marca universal**)
- Reset de memória ao trocar idioma
- Tradução retroativa do histórico

### 7.5 DNT obrigatório

Conteúdo de `shared/i18n/dnt.md` (cópia simbólica em `backend/prompts/baco/dnt.md`):

```markdown
# Do Not Translate List

NUNCA traduza os seguintes termos, independentemente do idioma de resposta:

## Nomes próprios de vinhos
Château Margaux, Opus One, Sassicaia, Penfolds Grange, Vega Sicilia, Dominus, etc.

## Castas/variedades
Cabernet Sauvignon, Pinot Noir, Chardonnay, Malbec, Merlot, Sangiovese, Nebbiolo,
Riesling, Sauvignon Blanc, Cabernet Franc, Gewürztraminer, Viognier, Grenache,
Mourvèdre, Carmenère, Torrontés, Tannat, Syrah/Shiraz, Tempranillo, Garnacha

## Denominações / DOCs / AOCs
Bordeaux, Burgundy, Rioja, Barolo, Barbaresco, Chianti, Champagne, Sancerre,
Chablis, Brunello di Montalcino, Mosel, Douro, Vinho Verde, Napa Valley, Sonoma,
Willamette, Mendoza, Maipo, Stellenbosch

## Termos técnicos consolidados
terroir, sommelier, decanter, magnum, jeroboam, cuvée, château, domaine

## Marcas
Baco (personagem - universal), WineGod, winegod.ai
```

### 7.6 Prompt caching Anthropic

**Obrigatório** quando Baco usar Claude. Header: `anthropic-beta: prompt-caching-2024-07-31`.

Marcar como `cache_control: ephemeral`:
- `base.md` (imutável)
- `language/<locale>.md` (só 4 variantes no Tier 1, alto reuso)
- `dnt.md` (imutável)

**Não cachear:**
- Market context block (dinâmico por usuário)
- Mensagem do usuário

**Expectativa honesta:** implementação é ~4 horas de refactor no `baco_prompt_builder.py`. Ganho real: 30-70% economia no custo Claude (depende de reaproveitamento real, TTL padrão 5min).

### 7.7 Checklist cultural por idioma (10 perguntas obrigatórias)

Antes de ativar cada idioma Tier 1, nativo Fiverr revisa as 10 respostas:

**Técnicas gerais (5):**
1. "Qual vinho me recomenda para jantar romântico?"
2. "Cabernet ou Malbec para churrasco?"
3. "Qual melhor custo-benefício em tinto?"
4. "Como servir vinho branco?"
5. "Castas portuguesas conhecidas?"

**Culturais/tonais (5 por idioma):**
6. Pergunta local cultural (ex: en-US: "What's good for Thanksgiving?")
7. Harmonização local (ex: fr-FR: "Que vin pour un coq au vin?")
8. Gíria regional (ex: es-419 MX: "¿Qué vino va con tacos al pastor?")
9. Teste de tom (formal/informal apropriado ao mercado)
10. Pergunta de restrição (ex: "É seguro beber todo dia?" — deve dar resposta responsável)

**Critério de aprovação:** nativo aprova se todas soarem idiomáticas e culturalmente corretas. Rejeita se >2 respostas soarem "robóticas" ou "gringa".

Custo: ~$5 adicional no Fiverr por idioma (~30 min extra do nativo).

---

## 8. Legal e Compliance

### 8.1 Escopo do Tier 1

Tier 1 jurídico real:
- `BR` (LGPD)
- `US` (CCPA)

Outros mercados:
- Usam template `DEFAULT`
- Com disclaimer claro: "Service operated from Brazil. LGPD applies. This is an automated translation. Contact legal@winegod.ai for questions."

### 8.2 O que fica fora agora

- Mercado comercial FR/EU completo (bloqueia ativar FR como mercado comercial)
- GDPR completo por país europeu
- Versão binding por cada país sem revisão jurídica correspondente

### 8.3 Fonte única de conteúdo legal

Padrão:
```text
shared/legal/
  BR/
    privacy.md
    terms.md
    cookies.md
    data-deletion.md
  US/
    privacy.md
    terms.md
    cookies.md
    data-deletion.md
  DEFAULT/
    privacy.md
    terms.md
    cookies.md
    data-deletion.md
```

Não usar frontend inline ou backend-only como estado final.

### 8.4 Binding language

Regra: **não hardcodar `legal_binding_language` para mercados não revisados.**

Só usar valor explícito quando houver:
1. Entidade jurídica definida
2. Documento original definido na jurisdição
3. Revisão jurídica correspondente

Caso contrário: `null` + disclaimer "operated from Brazil".

### 8.5 Age gate

Tier 1:
- BR 18
- US 21
- MX 18
- FR 18 (educational)
- DEFAULT 18

Implementação V1:
- Modal simples com 2 botões ("Tenho {age}+ anos" / "Não tenho")
- Cookie `wg_age_verified=<country>-<timestamp>` por 1 ano
- Middleware bloqueia rotas exceto `/age-verify`, `/legal/*` se `age_gate_required: true` e cookie ausente
- UI do age gate é classe `legal` (revisão obrigatória)

### 8.6 Regra comercial FR

Enquanto FR estiver `enabled: partial`:
- Sem CTA de compra
- Sem copy comercial de compra
- Sem indexação comercial EU completa

### 8.7 Versionamento legal minimalista

Cada doc legal tem frontmatter markdown:

```markdown
---
version: 1.0
effective_date: 2026-05-01
jurisdiction: BR
language: pt-BR
binding_language: pt-BR
---
```

Sem tabela SQL de auditoria no Tier 1. Banner simples "Termos atualizados, clique para aceitar" quando binding version muda. Aceite em `users.consent_version`.

### 8.8 Consulta jurídica BR+US

**Status:** pergunta aberta (Seção 18). Recomendação: reservar ~$500 para revisão pré-lançamento de templates BR e US. Justificativa: 4M usuários = risco real de notificação LGPD/CCPA.

**Mas:** decisão fica com founder. Não imposto pelo documento.

---

## 9. Conteúdo Dinâmico

### 9.1 O que nunca se traduz

- Nome de vinho (`wines.name`)
- Produtor
- Denominação
- Casta/variedade
- Safra (ano)

### 9.2 O que pode ser traduzido depois

- Descrições longas (`wines.description_i18n` JSONB — ver Seção 2.13)
- Notas de degustação (`wines.tasting_notes_i18n`)
- Reviews de usuários

### 9.3 Regra do Tier 1

**Não criar sistema complexo de cache on-demand.**

Padrão:
- Foco em UI, app chrome, páginas principais, legal e Baco
- UGC longo com botão explícito "Traduzir" só se realmente necessário
- Sem tabela `translation_cache` complexa no primeiro ciclo

**Pré-tradução one-shot (opcional):**
- Script `scripts/i18n/translate_top_wines.py` pode pré-traduzir descrições dos top 100 vinhos mais acessados
- Resultado commit direto em `wines.description_i18n` JSONB
- Roda manualmente quando houver demanda

### 9.4 Conteúdo sensível

Mercado com `commercial_enabled: false` ou `purchase_cta_allowed: false`:
- Não auto-traduzir conteúdo que soe promocional/comercial sem filtro
- No Tier 1, só FR cai nesse caso (mercado parcial)
- Pode mostrar versão em idioma original (en-US ou pt-BR) como fallback

### 9.5 Reviews de usuários em idioma misto

- Detecta idioma do review (via lib `franc` ou campo explícito)
- Se `review.language !== user.ui_locale`, mostra botão "Traduzir"
- Cache de tradução on-demand: minimalista, em memória Redis com TTL 1h, sem tabela persistente no Tier 1
- Rate limit: 10/dia anônimo, 50/dia logado

---

## 10. Workflow Operacional Oficial

### 10.1 Regra fundamental

**Founder NUNCA usa Git, CLI do Tolgee, ou commit manual como parte do fluxo oficial.**

Founder opera:
- Produto (chat.winegod.ai)
- Painel Tolgee (UI web)
- Revisão humana de traduções
- Aprovações simples

Claude/CI opera:
- Código
- Sync de traduções (`tolgee push`, `tolgee pull`)
- PRs
- Merge
- Deploy técnico

### 10.2 Workflow oficial

#### Etapa 1 — Código
1. Claude adiciona ou altera strings base em `pt-BR` no repo
2. PR é revisado normalmente
3. Merge na `main`

#### Etapa 2 — Push da base
4. CI ou Claude faz `tolgee push` do source `pt-BR`
5. Tolgee gera sugestões/MT para idiomas alvo
6. Founder revisa no Tolgee UI

#### Etapa 3 — Sync seguro
7. Depois da aprovação, **Claude ou CI** puxa as traduções
8. O sistema abre um **PR de sync** (nunca commit direto em main)
9. Claude revisa o PR
10. Merge normal

### 10.3 O que fica proibido

- Founder rodar `npx tolgee pull`
- Founder fazer `git commit`
- CI commitar direto na `main`
- Auto-merge de PR de traduções sem revisão

### 10.4 Forma mínima aceitável no início

Se PR bot ainda não existir:
- Claude faz o sync manualmente
- Abre o PR
- Mergeia depois de revisão

Mesmo nesse caso, a regra continua: **founder só no Tolgee UI.**

### 10.5 Backup semanal do Tolgee

Cron GitHub Actions (todo domingo 02:00 UTC):

```yaml
# .github/workflows/tolgee-backup.yml
name: Weekly Tolgee Backup
on:
  schedule:
    - cron: '0 2 * * 0'
  workflow_dispatch:

jobs:
  backup:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npx @tolgee/cli pull --all --output ./shared/i18n/backup/latest/
      - run: cp -r ./shared/i18n/backup/latest ./shared/i18n/backup/$(date +%Y-W%V)
      - run: git config user.name "ci-bot"
      - run: git config user.email "ci@winegod.ai"
      - run: git add shared/i18n/backup/
      - run: git commit -m "chore(i18n): weekly backup $(date +%Y-%m-%d)" || echo "no changes"
      - run: git push
```

**Por que entra:** preventivo puro. Se Tolgee ficar fora do ar ou conta for suspensa, dados estão no git.

### 10.6 Kill switch manual (runbook)

Runbook em `docs/RUNBOOK_I18N_ROLLBACK.md`:

```markdown
# Runbook: Desligar Idioma de Emergência

Se um locale apresentar bug grave em produção:

## Passo 1 — Remover do ENABLED_LOCALES (30 segundos)
1. Abrir Vercel dashboard
2. Settings → Environment Variables
3. Editar `NEXT_PUBLIC_ENABLED_LOCALES`
4. Remover locale problemático (ex: de `pt-BR,en-US,es-419,fr-FR` para `pt-BR,en-US,es-419`)
5. Salvar → Vercel redeploy automático (~1 min)

## Passo 2 — Backend (Render)
1. Render dashboard → serviço winegod-api → Environment
2. Mesma variável `ENABLED_LOCALES`
3. Remover locale → salvar (aplica em <60s)

## Passo 3 — Comunicação
- Tweet/post sobre indisponibilidade temporária
- Email aos usuários com o idioma no perfil

## Passo 4 — Investigação
- Logs Sentry filtrados por tag `locale=<X>`
- Identificar causa
- Corrigir no Tolgee + push + validar em staging
- Reativar env var
```

### 10.7 Disaster recovery (Tolgee fora)

Runbook em `docs/RUNBOOK_I18N_DISASTER.md`:

```markdown
# Runbook: Tolgee Indisponível por >4 horas

## Ação imediata
- Site continua funcionando (JSONs estão no repo desde último pull)
- Novas strings não traduzem automaticamente
- Founder pode editar JSONs manualmente como emergência (mas precisa ajuda Claude)

## Se Tolgee morrer permanentemente
1. Ativar última versão do backup: `cp -r shared/i18n/backup/latest/* frontend/messages/`
2. Escolher nova plataforma (Locize, Crowdin)
3. Importar JSONs + glossary.md para nova plataforma
4. Tempo estimado: ~1 semana com Claude ajudando
5. Sem perda de JSONs. Perda: screenshots, TM acumulada, histórico de edição.
```

---

## 11. QA Oficial

### 11.1 O que entra no Tier 1

- QA manual com checklist claro
- Playwright local simples
- 1 viewport desktop + 1 viewport mobile
- Pseudo-localização leve dentro do teste visual
- Validação CLDR de plurais no CI
- Smoke test por idioma em CI

### 11.2 O que NÃO entra no Tier 1

- Matriz grande de viewports (tablet, 4K, etc.)
- Claude Vision para todos screenshots
- Pipeline enterprise de regressão visual
- Auto-rollback com thresholds

### 11.3 Playwright simples (sem Claude Vision)

- Script Playwright local, roda no GitHub Actions gratuito
- 5-8 rotas críticas × 4 idiomas × 2 viewports = ~40-64 screenshots
- Compara com baseline via `pixelmatch` (diff puro, sem IA)
- Roda apenas em PRs que alteram `messages/*.json` ou `components/`
- Baselines atualizados propositalmente quando UI muda

### 11.4 Checklist manual por idioma e por wave

Tempo realista: **2-3 horas por wave** (não 20 minutos).

```markdown
## Rotas públicas
- [ ] Landing (`/`, `/en`, `/es`, `/fr`) — CTAs visíveis, tradução coerente
- [ ] Legal (`/legal/<country>/<lang>/privacy`) — versão correta por país
- [ ] Wine list (se pública) — cards carregam

## App routes
- [ ] Login/signup — erros traduzidos
- [ ] Chat vazio (`/chat`) — welcome screen, placeholders
- [ ] Primeira mensagem ao Baco — resposta no idioma certo, tom OK
- [ ] Trocar idioma no meio — histórico mantém original, resposta nova no novo idioma
- [ ] Sidebar — todos items traduzidos
- [ ] Conta — labels OK, data formatada
- [ ] Favoritos — empty state + lista
- [ ] Plano — tiers traduzidos

## Cenários críticos
- [ ] Age gate em BR/US/MX (idades 18/21/18)
- [ ] CTA de compra em FR oculto (commercial_enabled: false)
- [ ] Email welcome chegou no idioma correto
- [ ] Push notification (se ativa) no idioma

## Visual (via Playwright diff)
- [ ] Layout não estoura em pseudo-loc alemão simulado (+40% texto)
- [ ] Moeda no formato correto (R$ vs $ vs € vs MXN)
- [ ] Data no formato correto
```

### 11.5 Pseudo-localização (leve)

Não como fase separada. Usar pseudo-loc **dentro do Playwright**:
- Script gera `pseudo-PL.json` com texto expandido 40% e caracteres acentuados
- Playwright roda rotas em `pseudo-PL` e compara layout
- Pega hardcodes esquecidos (aparecem sem colchetes `[!! !!]`) + layout estourando

### 11.6 Smoke test por idioma

Script `scripts/i18n/smoke_test.sh`:
- Para cada locale Tier 1, abre página principal em Playwright headless
- Verifica: status 200, sem erros JS em console, texto presente
- Roda em CI antes de cada deploy
- Deploy bloqueado se algum locale falhar

---

## 12. Observabilidade Oficial

### 12.1 Estado atual

**Hoje Sentry e PostHog NÃO existem no repo.** Qualquer menção a eles neste documento é estado-alvo.

### 12.2 Estado alvo (quando adicionados)

- Sentry com tags `locale` e `market_country`
- PostHog com propriedades `locale` e `market_country` registradas
- Eventos customizados: `locale_switch`, `translation_missing_key`, `translation_report_submitted`

### 12.3 O que medir

- Locale switch rate
- Fallback de chave (quando chave missing)
- Erro JS por locale (permite filtrar bugs específicos de idioma)
- Rotas com erro por locale
- Conversão por locale (comparado ao próprio baseline de 7d, não vs pt-BR)

### 12.4 O que não fazer no começo

- Auto-rollback estatístico (ruído sem volume)
- Autopromote de locale por thresholds fracos

No início: rollback e kill switch **manuais** via env var (Seção 10.6).

---

## 13. Budget Oficial

### 13.1 Princípios

- Custo fixo baixo no início
- Zero automação cara sem volume
- Zero stack duplicada
- Transparência: não prometer custo que não vai conseguir sustentar

### 13.2 Custo esperado (orientativo, não travado)

O documento não trava números exatos de vendor (mudam com o tempo). Mas a faixa esperada:

**Setup one-shot:**
- Tolgee Free: $0
- Configuração via Claude: $0 (horas do Claude)
- Claude API testes iniciais: ~$10
- Fiverr revisão Tier 1 (UI + Baco cultural + glossary + legal BR/US + checklist cultural): **~$135**
- Consulta jurídica BR+US (opcional, decisão do founder): **$0-500**
- **Total:** $145 a $645

**Manutenção mensal (orientativo):**
- Tier 1 (3-4 idiomas, Tolgee Free): **$10-30/mês**
- Pós-upgrade Tolgee Team: **$65-100/mês**

**Regra:** se Free parar de ser suficiente, upgrade proativo em ~400 keys.

### 13.3 Budget cap

Env var `TRANSLATION_BUDGET_USD_MONTHLY=100`.

Cron diário `scripts/i18n/budget_watchdog.py`:
- Soma gasto (Claude + qualquer API externa)
- `>80%` → alerta Discord/email
- `>100%` → alerta urgente, **sem pausa automática**
- Founder decide manualmente o que fazer

### 13.4 Regra operacional quando orçamento apertar

1. Pausar novos idiomas (Tier 1.5 adiado)
2. Pausar tradução de conteúdo dinâmico long-tail
3. Pausar revisão Claude secundária (só primária)
4. Manter **core de locales ativos consistente** (nunca deixar locale ativo com chave faltando)

### 13.5 Tempo do founder (honestidade)

| Fase | Horas/semana |
|---|---|
| Mês 1 (setup + refactor) | 3-5h |
| Mês 2 (lançamento Tier 1) | 3-4h (QA 2-3h em dia de wave) |
| Mês 3 (estabilização) | 1-3h |
| Mês 4+ (regime permanente) | **1-2h/semana** |

---

## 14. Itens Explicitamente Rejeitados

Estes itens ficam bloqueados até revisão formal deste documento.

### 14.1 Rejeitados agora

- `flask-babel` no backend
- Pipeline custom DeepL + Claude + Gemini orquestrado
- Auto-rollback automático desde dia 1
- Auto-merge de PR de tradução
- Commit direto na `main` por CI
- Founder usando CLI/Git para sync
- Cache on-demand complexo no Tier 1
- Baco com markdown por país (`market/*.md`)
- Jurídico EU completo agora
- CJK e RTL no Tier 1
- Feature flags por usuário individual
- Revisão nativa upfront de 20 idiomas
- Vercel KV no começo
- Locale sintético (`pt-JP`, `en-BR`)
- Auto-redirect por Accept-Language
- Paraglide JS (vale Tolgee SDK se entrar)
- Tolgee self-hosted
- TMS como fonte única de verdade (ou repo como fonte única)
- Gemini cross-check no pipeline
- Embedding drift detector
- Canary translation por string (5% → 100%)
- Tabela SQL versionamento legal enterprise
- Consent flow automatizado re-acceptance
- Source freeze com git tags (usa convenção social)
- Market Matrix com subjurisdições (estados US/IN) no Tier 1
- OpenAI Moderation via credenciais Anthropic
- Claude Vision em todos screenshots de QA

### 14.2 Rejeitados, mas com versão enxuta aceita

- Playwright completo → aceito Playwright local simples (desktop + mobile, sem Vision)
- Pseudo-localização completa → aceita como passo leve dentro do teste visual
- Tolgee SDK React → adiado (Founder usa UI web), mas opção condicional Tier 1.5+
- PR bot auto-sync → aceito se abrir PR seguro, nunca auto-merge
- Budget watchdog → aceito como alerta, nunca como pausa automática
- Observabilidade com tags → aceito quando Sentry/PostHog forem adicionados (F3/F4)

---

## 15. Fases Oficiais de Execução

### F0 — Preparação e estrutura (sem código)
- Criar `shared/i18n/markets.json` (5 países Tier 1)
- Criar `shared/i18n/glossary.md` (wine glossary inicial)
- Criar `shared/i18n/dnt.md`
- Criar estrutura `backend/prompts/baco/` simplificada (sem conteúdo ainda)
- Criar estrutura `shared/legal/` (esqueleto)

### F1 — Infra frontend
- Instalar `next-intl`
- Criar `frontend/messages/pt-BR.json` (extração inicial)
- Configurar provider/config next-intl
- Configurar `localePrefix: 'as-needed'`, `localeDetection: false`
- Criar `frontend/middleware.ts` com modelo de roteamento (Seção 4)
- Criar `frontend/lib/i18n/formatters.ts` (Intl util)
- Fallback hierárquico de chaves

### F2 — Refatoração do app core
Arquivos prioritários:
- `frontend/app/layout.tsx` (metadata dinâmica + lang via params)
- `frontend/components/Sidebar.tsx`
- `frontend/components/WelcomeScreen.tsx`
- `frontend/components/ChatInput.tsx`
- `frontend/components/ChatHome.tsx`
- `frontend/components/AppShell.tsx`
- `frontend/components/SearchModal.tsx`
- `frontend/components/MessageBubble.tsx`
- `frontend/app/conta/ContaContent.tsx`
- `frontend/app/favoritos/FavoritosContent.tsx`
- `frontend/app/plano/*`

ESLint escopado ativado ao final.

### F3 — Contratos de backend
- Migration em `backend/db/models_auth.py`: adicionar `ui_locale`, `market_country`, `currency_override`
- Backfill usuários existentes (pt-BR/BR/null)
- Trocar respostas do backend para `message_code` (remover texto localizado server-side)
- Schema JSONB em `wines`: `description_i18n`, `tasting_notes_i18n`
- Ajustar exibição de país/moeda (usar `country_names.py` existente)

### F4 — Legal e público
- Externalizar páginas legais para `shared/legal/`
- Criar templates BR (LGPD), US (CCPA), DEFAULT
- Versionamento simples (frontmatter markdown)
- Aplicar regra de FR parcial (sem CTA comercial, sem binding EU)
- Age gate modal + middleware

### F5 — Baco
- `base.md` com regras imutáveis
- Overlays `language/<locale>.md` por idioma Tier 1
- `dnt.md` com nomes protegidos
- Builder `baco_prompt_builder.py` com injeção de mercado
- Prompt caching Anthropic configurado

### F6 — Workflow operacional
- Setup Tolgee Cloud Free (conta, projeto, locales)
- Wine Glossary importado como TM/Termbase (conforme plano)
- CI: `tolgee push` pós-merge em `main`
- Founder revisa no Tolgee UI
- CI: `tolgee pull` → abre PR automático (nunca commit direto)
- Claude revisa PR e mergeia

### F7 — QA e launch
- QA manual com checklist (Seção 11.4)
- Playwright local simples (desktop + mobile)
- Pseudo-loc leve no Playwright
- Validação CLDR plurals no CI
- Smoke test por idioma
- Fiverr Tier 1: UI + Baco cultural + glossary + legal (+ checklist cultural 10 perguntas)
- Launch canário por locale (via `ENABLED_LOCALES`)

### F8 — Observabilidade e backup (quando agregar valor)
- Adicionar Sentry + tags locale/market_country
- Adicionar PostHog + propriedades locale/market_country
- Ativar cron de backup semanal Tolgee
- Documentar runbooks (rollback, disaster)

---

## 16. Critérios de Sucesso

Tier 1 é considerado bem-sucedido se, após 30 dias:

1. Os 4 locales funcionarem sem regressão grave em `pt-BR`
2. Founder não precisa usar Git/CLI para operar traduções
3. FR continuar claramente não-comercial (CTAs desabilitados)
4. Erros do backend não dependerem de texto localizado server-side
5. Datas, horas, moeda e país aparecerem de forma coerente por locale/mercado
6. App privado continuar estável sem quebrar auth e sessão
7. Time de manutenção caber em Claude + founder
8. Zero erros JS críticos de i18n em produção (validado quando Sentry entrar)
9. Conversão por idioma > 50% do próprio baseline de 7d pós-lançamento (não vs pt-BR)
10. Dev adiciona string nova → 3-4 idiomas traduzidos em <24h via fluxo oficial
11. Budget API dentro da faixa orientativa
12. Zero incidente jurídico em 3 meses (privacy + alcohol)
13. <1% dos usuários reportam "bad translation"
14. Baco culturalmente aceitável (checklist 10 perguntas aprovado por nativo Fiverr em cada idioma)
15. Backup semanal Tolgee funcionando (cron verde por 4 semanas consecutivas)
16. Market Matrix consultada corretamente por todos os consumidores (middleware, Baco, UI, Flask)

Só após 30 dias estáveis com esses critérios, Tier 1.5 abre.

---

## 17. Perguntas Abertas (Respostas Viram `WINEGOD_MULTILINGUE_DECISIONS.md`)

Estas perguntas continuam abertas e precisam ser fechadas antes de algumas fases:

1. **Tier 1 confirmado** em pt-BR + en-US + es-419 + fr-FR?
2. **it-IT e de-DE** entram em Tier 1.5 condicional ou ficam de fora completamente?
3. **Consulta jurídica BR+US** agora ($300-500)? Recomendado mas opcional. Founder decide.
4. **Consulta jurídica EU** agora ($500-1500)? Bloqueante para ativar FR/DE/IT como mercados comerciais.
5. **Revisão Fiverr Tier 1** (~$135 one-shot)? Aprovado?
6. **Budget cap mensal** — $100 conservador ou mais folga?
7. **Entidade jurídica da WineGod** registrada em qual país? Define `legal_binding_language` default quando houver template revisado.
8. **Baseline atual de conversão pt-BR**? Para saber se multiplicação por locales vale.
9. **Horas/semana disponíveis** no Mês 1 setup? Se <3h, timeline estende.
10. **FR ativa mercado EU comercial** agora (exige jurídico EU) ou só idioma com disclaimer?
11. **Demografia real dos 4M Cicno**: % brasileiros monolíngues vs poliglotas? Define prioridade de revisão.
12. **MX entra comercial completo** no Tier 1 ou com caution text?
13. **Moderação de UGC** entra no Tier 1 (OpenAI Moderation API com credenciais OpenAI próprias) ou fica para depois?
14. **Sentry e PostHog** entram na F3 ou só após primeiro locale extra em produção?

---

## 18. Referências Externas Validadas

Premissas sensíveis verificadas em 2026-04-17:

- Vercel geolocation headers: `X-Vercel-IP-Country`
  - https://vercel.com/kb/guide/geo-ip-headers-geolocation-vercel-functions
- Tolgee Free: 500 keys, 3 seats, 10.000 MT credits
  - https://tolgee.io/pricing
- Tolgee AI Translator: recursos variam por plano
  - https://docs.tolgee.io/platform/translation_process/ai_translator
  - https://docs.tolgee.io/platform/projects_and_organizations/machine-translation-settings
- OpenAI Moderation API: gratuita para usuários da API OpenAI (credenciais OpenAI separadas)
  - https://developers.openai.com/api/docs/pricing
  - https://help.openai.com/en/articles/4936833
- Anthropic prompt caching:
  - Header `anthropic-beta: prompt-caching-2024-07-31`
  - TTL padrão 5min (1h com custo extra)
  - https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching

---

## 19. Regra Para Futuras IAs e Futuras Sessões

Qualquer futura IA que tocar no WineGod i18n deve assumir:

1. **Este documento é o padrão oficial.** Se outro documento antigo discordar, este prevalece.
2. O plano precisa continuar **simples de operar**.
3. O founder **não entra em Git/CLI/DevOps**.
4. FR continua **idioma sem mercado comercial** no Tier 1.
5. Idioma, país e moeda continuam **separados** (nunca locale sintético).
6. Backend continua com `error_code`, **não flask-babel**.
7. Baco continua simplificado (base + language + dnt), **não combinatório por país**.
8. Qualquer expansão "enterprise" precisa provar valor concreto antes de entrar.
9. **Leia primeiro Seção 0** (régua mestra) antes de sugerir qualquer mudança.
10. Se sugerir item já rejeitado, apontar para a justificativa na Seção 14.
11. Afirmações sobre stack pronta devem ser validadas contra Seção 1.2 (o que NÃO existe ainda).

---

## 20. Decisão Final

O WineGod vai internacionalizar **de forma robusta, mas não grandiosa demais**.

O padrão oficial é:
- Multilíngue de verdade (qualidade no que estiver ativo)
- Operacional para founder solo
- Alinhado ao repo real (sem fingir que peças já estão instaladas)
- Sem promessas falsas de stack pronta
- Sem automação frágil
- Sem escopo mundial artificial no primeiro ciclo

**Este é o documento que deve guiar a implementação.**

---

**Fim do Padrão Oficial V2.0.**
