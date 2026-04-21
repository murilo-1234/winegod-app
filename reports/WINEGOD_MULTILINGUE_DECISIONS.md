# WINEGOD.ai — Decisões do Gate de Realidade F0.1

**Data:** 2026-04-19
**Founder:** Murilo
**Status:** travadas e aprovadas
**Projeto:** i18n rollout (multilíngue)
**Plano mestre:** `C:\winegod-app\reports\WINEGOD_MULTILINGUE_PLANO_EXECUCAO.md` V2.1
**Plano paralelo:** `C:\winegod-app\reports\WINEGOD_MULTILINGUE_PLANO_PARALELO.md` V1.0

Este documento trava as 19 decisões estratégicas pré-execução do F0.1 e registra decisões complementares sobre roteamento raiz e posicionamento de produto. Todas as trilhas (T1/T2/T3/T4) devem usar este documento como fonte única de verdade para qualquer decisão coberta abaixo. Mudanças nestas decisões exigem nova assinatura do founder.

---

## Decisões travadas

### Seção A — Idiomas

**1. Tier 1 confirmado:** pt-BR + en-US + es-419 + fr-FR
- Decisão: **SIM** (aprovado)
- Implicação: todas as 4 ondas de frontend, backend error_codes, Baco overlays e legal matrix cobrem esses 4 locales no lançamento.

**2. it-IT e de-DE em Tier 1.5:**
- Decisão: **NÃO** — adiar Tier 1.5
- Racional: consolidar os 4 primeiros antes de expandir. Expansão italiana/alemã entra em release posterior, após validação de tração Tier 1.

**3. FR ativa mercado EU agora ou só idioma:**
- Decisão: **só idioma**
- Racional: francês ativa como UI/tradução, mas NÃO como mercado comercial EU. Não há entidade EU, não há processamento de pagamento em EUR, não há compliance GDPR completo. Mercado EU vem em release posterior com tração e budget.
- Implicação pra T3 Legal: usar template DEFAULT para `/fr/*` (não FR-específico com regras EU completas).

### Seção B — Jurídico

**4. Consulta jurídica BR+US agora ($300-500):**
- Decisão: **depois** (não gastar agora)
- Racional: copiar templates de referências grandes do setor (Vivino, Wine-searcher, Delectable) e ajustar pro nosso contexto. Consulta jurídica profissional fica pra quando houver receita/tração.
- Implicação pra T3: templates legais vêm de fontes públicas (Vivino/Wine-searcher/Delectable) com adaptação mínima. Disclaimers de "operated from Brazil" e "not legal advice" obrigatórios.

**5. Consulta jurídica EU agora ($500-1500):**
- Decisão: **depois**
- Racional: mesmo raciocínio. FR é só idioma, não mercado EU comercial completo — redução de exposição GDPR. Templates copiados cobrem mínimo viável.

**6. Entidade jurídica:** BR (Brasil)
- Decisão: **BR**
- Racional: já é o home base do founder. Minimiza complexidade tributária e bancária no lançamento. Migração para Delaware (se necessário por investidor US ou Stripe Atlas) fica pra quando houver trigger concreto.

### Seção C — Budget

**7. Revisão Fiverr Tier 1 (~$135) aprovada:**
- Decisão: **SIM, aprovado**
- Racional: $135 pra 1 freelancer nativo por idioma revisando traduções IA. Barato pra qualidade percebida pelo usuário. Economia falsa cortar aqui.
- Quando usar: após Onda 4 (refator frontend) e antes da Onda 10 (canário).

**8. Budget cap mensal para APIs pagas:**
- Decisão: **$100/mês conservador**
- Racional: teto de segurança para Claude API, OpenAI (Codex), Gemini (OCR), Tolgee, Sentry/PostHog combinados. Sistema deve ter kill-switch quando ultrapassar.
- Revisar cap mensalmente após lançamento.

### Seção D — Negócio

**9. Baseline conversão pt-BR atual:**
- Decisão: **TBD — sem dados consolidados atualmente**
- Ação: medir baseline antes de liberar canário da Onda 10. Instrumentar PostHog (Onda 11) pra capturar funil atual.
- Sem baseline, a T4 (QA) não consegue medir regressão pós-i18n. Essa medição é pré-requisito da Onda 9.

**10. Horas/semana do founder disponíveis no Mês 1:**
- Decisão: **40 horas/semana** (full-time)
- Racional: founder dedicado ao projeto, disponível pra responder gates, aprovar fases, validar previews Vercel, resolver decisões ad-hoc que apareçam.

**11. MX (México) comercial ou caution:**
- Decisão: **caution**
- Racional: español (es-419) já cobre MX como idioma. "Comercial completo" (impostos, LGPD-MX equivalente, pagamento local) fica pra release posterior com análise específica do mercado.

**12. Moderação UGC entra Tier 1:**
- Decisão: **NÃO**
- Racional: chat Baco é conversa privada user↔IA. Não há feed público, comentários, reviews ou conteúdo user-to-user. Sem UGC, não há necessidade de moderação no lançamento.
- Se product pivotar pra incluir UGC (ex: review público, feed social), revisitar.

**13. Sentry e PostHog na Onda 11 ou depois:**
- Decisão: **Onda 11** (entram)
- Racional: observabilidade básica no lançamento é obrigatória. Sentry pega erros em prod; PostHog mede funil e comportamento. Ambos já previstos na Onda 11 do plano. Sem eles, rollout às cegas.

**14. Demografia 4M Cicno — % poliglotas:**
- Decisão: **estimativa 30% poliglotas / 70% monolíngues**
- Racional: estimativa conservadora baseada em média LatAm. Sem survey próprio ainda. Implicação: i18n é crítico (70% falam só 1 idioma, se não é o deles, perdem valor do Baco).
- Ação: incluir pergunta de auto-declaração de idiomas no onboarding pós-Onda 4, refinar estimativa após 1000 users.

### Seção E — Técnico anti-surpresa

**15. Pico de lançamento — Claude API rate limit:**
- Decisão: **investigar** (responsabilidade da T1 Infra)
- Racional: descobrir o limite atual do plano Anthropic (Tier do account) e documentar no `reports/i18n_execution_log.md`. Se 100k pessoas chegarem no dia D com 20% em browsers inglês, saber se o rate limit aguenta.
- Se não aguentar: paralelizar calls, cache Baco mais agressivo, ou upgrade de tier antes do lançamento.

**16. Fallback de tradução parcial em lançamento:**
- Decisão: **inglês (en)** como fallback universal
- Racional: se `fr-FR` está 80% pronto no dia D, os 20% restantes caem em EN (não PT). EN é fallback internacional padrão e reduz estranhamento. PT só como fallback final se EN também faltar (improvável — EN é Tier 1).
- Implementação: cadeia `fr-FR → en-US → pt-BR`.

**17. Tolgee cai no lançamento — site funciona via snapshot:**
- Decisão: **SIM, obrigatório**
- Racional: traduções devem ser baixadas em build time de Tolgee e snapshotadas no repo em `frontend/messages/<locale>.json`. Runtime não depende de Tolgee disponível — Tolgee só é plataforma de edição.
- Implementação: script de build que puxa de Tolgee e commita o snapshot. Fallback: último snapshot válido em git.

**18. Locale cross-domain (chat.winegod.ai → api.winegod.ai):**
- Decisão: **SIM, header `X-WG-UI-Locale`**
- Racional: cookie cross-domain é frágil (SameSite, CORS, browsers bloqueando third-party). Header HTTP custom é a opção mais robusta e auditável. Frontend Vercel inclui `X-WG-UI-Locale: fr-FR` em toda request pra `api.winegod.ai` Render.
- Fallback no backend: se header ausente, usar `user.ui_locale` do JWT (auth) ou `Accept-Language` do browser.

**19. Link indexado desligado:**
- Decisão: **301 permanente para `/c/abc123`** (rota sem locale)
- Racional: mantém SEO (Google propaga pro novo link), não quebra user experience (ele chega no conteúdo mesmo), evita 404 que degradaria ranking. Fallback silencioso seria confuso (usuário clica em `/fr/c/abc` e vê conteúdo em outro idioma sem aviso).
- Implementação: middleware detecta locale desligado em path, emite 301 pra versão sem locale.

---

## Decisão complementar F0.4 — Roteamento raiz

**Decisão:** **Opção A — manter como está.**

- `chat.winegod.ai/` continua abrindo direto o chat atual com Baco.
- A rota raiz `/` não vira landing page no Tier 1.
- Se no futuro houver landing pública ou página de boas-vindas, ela ficará em `/welcome` ou `/sobre`.
- Não migrar o chat para `/chat` nesta fase.

**Racional:** menor risco operacional. O produto atual já usa `/` como entrada do chat, e mudar a raiz agora exigiria alterar redirects, links internos, OAuth callback, navegação e comunicação com usuários existentes.

**Implicação para a Onda 2:** toda infra de i18n deve tratar `/` como app route do chat sem prefixo de locale. Páginas públicas/SEO futuras podem usar `/welcome`, `/sobre` e variantes localizadas, mas não substituem a entrada atual.

---

## Decisão complementar — Posicionamento US-facing

**Decisão:** WineGod deve ser percebido como um app global/americano na experiência de produto.

- A experiência internacional deve parecer **US-first / global-first**, não "app brasileiro traduzido".
- `en-US` é o idioma de referência para copy internacional, tom de marca, onboarding, mensagens de erro, empty states, CTAs e Baco em inglês.
- Para usuários fora do Brasil ou sem país detectado, a apresentação padrão deve privilegiar convenções americanas/internacionais: inglês americano, USD quando moeda não estiver definida, datas/números no padrão do locale ativo e tom de produto SaaS americano.
- `pt-BR` continua suportado e importante para usuários brasileiros/Cicno, mas não deve ditar o estilo de produto internacional.
- Baco em `en-US` deve soar como um sommelier digital nativo em inglês americano, não como tradução literal do Baco brasileiro.
- O design, microcopy e fluxos devem evitar sinais de improviso local: nada de português vazando, nada de formato BR em tela internacional, nada de mensagens "traduzidas demais".

**Limite legal:** isso é posicionamento de produto, não declaração jurídica. Enquanto a entidade continuar BR, termos/privacy devem manter transparência: serviço operado do Brasil, template DEFAULT/en-US quando aplicável, sem fingir incorporação, endereço ou compliance US que ainda não exista.

**Implicação para o Tier 1:** `en-US` passa a ser a referência principal de percepção global. Traduções `es-419` e `fr-FR` podem adaptar culturalmente, mas devem manter o polimento e a estrutura de um produto global.

---

## Decisão complementar F0.6 - Kill switch de locales

**Decisão:** implementar **Plano A + Plano B** (ambos). Plano A e o kill switch principal. Plano B e o backup resiliente.

### Plano A - Flag dinamica (principal)

- Fonte principal: tabela Postgres `feature_flags`.
- Chave: `enabled_locales`. Valor: lista JSON de locales permitidos, ex: `["pt-BR"]`, `["pt-BR","en-US"]`.
- Leitura: backend le em runtime a cada request critico.
- Cache: TTL de 10 a 30 segundos (10-30s) em memoria do processo (cache simples, nao Redis) para evitar hit constante no DB.
- Toggle real esperado: **10 a 30 segundos (10-30s)** entre um `UPDATE feature_flags ...` e o comportamento novo aparecer em producao.
- Alteracao feita via SQL direto com credencial protegida ou via endpoint admin futuro (fora de escopo nesta fase).

### Plano B - Env var (fallback resiliente)

- Fallback: variavel de ambiente `ENABLED_LOCALES` (lista separada por virgula ou JSON, a definir em F1.8).
- Uso: acionado quando o backend nao consegue ler `feature_flags` (DB inacessivel, tabela corrompida, row ausente).
- Propagacao: exige **redeploy manual** em Vercel (frontend) e Render (backend) conforme REGRA 7 do `CLAUDE.md`.
- Tempo esperado: **2 a 5 minutos (2-5 min)**, dependendo de deploy saudavel.
- **Nao e kill switch instantaneo.** Plano B existe para o caso de Plano A estar indisponivel, nao como via primaria.

### Fail-safe absoluto

- Se Plano A e Plano B falharem simultaneamente (DB inacessivel **e** env var ausente ou invalida), backend e frontend devem cair em `["pt-BR"]` de forma silenciosa.
- Racional: pt-BR e o idioma baseline do produto; preferivel servir em pt-BR a retornar erro e quebrar o chat.

### O que NAO e kill switch

- Env var sozinha **nao** e kill switch instantaneo: depende de redeploy.
- Cookie cross-domain **nao** e mecanismo de kill switch. Cookie so controla preferencia de UI por usuario; nao filtra locales em escala de produto.

### Implicacoes para fases seguintes

- **F1.6:** cria a migracao da tabela `feature_flags` e faz o seed inicial com `["pt-BR"]`.
- **F1.8:** cria o endpoint `GET /api/config/enabled-locales` que le Plano A com fallback em Plano B e fail-safe final em `["pt-BR"]`.
- **Onda 10 (canario):** ativacao progressiva de `en-US`, `es-419`, `fr-FR` usa **Plano A** via `UPDATE feature_flags SET value_json=...`. Rollback equivalente a reverter o UPDATE.
- **Runbook operacional:** procedimento passo a passo fica em `docs/RUNBOOK_I18N_ROLLBACK.md` (ja existente; revisao/alinhamento com esta decisao acontece em F12.1).

### Nenhum codigo nesta fase

Esta decisao e documental. Nao criar migration, nao criar endpoint, nao mexer em backend ou frontend. Implementacao real comeca em F1.6.

---

## Assinatura

```
Founder: Murilo
Data: 2026-04-19
Decisões F0.1 travadas: 19 (todas respondidas)
Decisão F0.4: Opção A — manter `/` como chat atual
Posicionamento: US-facing / global-first na experiência de produto
```

## Próximo passo

Com este documento e o arquivo `.sync/t1_onda0_complete` publicados, T1 pode avançar para F0.2 (criar estrutura `shared/`), T2 pode iniciar F0.5 (tooling ESLint + deps), T3 pode iniciar revisão de Onda 7 (Legal) usando as decisões travadas aqui como input.

T4 (QA) está travada em outro problema (zombie em bootstrap) — requer diagnóstico técnico separado, não relacionado a este gate.
