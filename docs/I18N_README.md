# WineGod.ai - I18N README

Este arquivo e o indice operacional dos documentos de internacionalizacao (i18n) do WineGod.ai. Serve como ponto de entrada unico para qualquer pessoa (founder, Claude, Codex, trilhas paralelas T1/T2/T3/T4) localizar rapidamente os documentos canonicos, decisoes principais e proximos passos.

Gerado em F0.3 do plano `reports/WINEGOD_MULTILINGUE_PLANO_EXECUCAO.md` V2.1.

---

## 1. Documentos canonicos

Estes sao os documentos de verdade. Qualquer conflito entre arquivos deve ser resolvido a favor destes aqui.

- `reports/WINEGOD_MULTILINGUE_DECISIONS.md` - 19 decisoes travadas no gate F0.1 (Tier 1, juridico, budget, tecnico anti-surpresa).
- `reports/WINEGOD_MULTILINGUE_HANDOFF_OFICIAL.md` - Padrao Oficial V2.0. Ancora estrategica do projeto.
- `reports/WINEGOD_MULTILINGUE_PLANO_EXECUCAO.md` - Plano V2.1 em 13 ondas e 104 fases pequenas com gate humano.
- `reports/WINEGOD_MULTILINGUE_PLANO_PARALELO.md` - Plano paralelo V1.0 (trilhas T1/T2/T3/T4).
- `reports/i18n_execution_log.md` - Log append-only de cada fase concluida.

## 2. Documentos operacionais

Documentos de runbook e limitacoes ja presentes no repositorio.

- `docs/RUNBOOK_I18N_ROLLBACK.md` - Kill switch duplo (Plano A dinamico via feature_flags + Plano B via env var).
- `docs/RUNBOOK_I18N_DISASTER.md` - Disaster recovery Tolgee e snapshot de traducoes.
- `docs/I18N_LIMITATIONS.md` - Limitacoes conhecidas (search match exato, CJK/RTL fora do escopo, moderacao UGC nao ativa, matriz legal enxuta).

## 3. Decisoes principais (resumo operacional)

Todas essas decisoes estao detalhadas em `reports/WINEGOD_MULTILINGUE_DECISIONS.md`. Resumo para consulta rapida:

- **Tier 1 de idiomas:** `pt-BR`, `en-US`, `es-419`, `fr-FR`.
- **Rota raiz:** `/` continua sendo o chat atual com Baco. Nao virou landing.
- **Landing futura:** se um dia existir, fica em `/welcome` ou `/sobre`. Nunca em `/`.
- **Posicionamento do produto:** WineGod.ai deve parecer US-facing / global-first na experiencia do usuario. Copy, defaults de UI, ordem de idiomas no seletor e tom geral precisam refletir esse posicionamento.
- **Entidade juridica:** segue Brasil (BR). Legal deve ser transparente sobre isso: disclaimers "operated from Brazil" em paginas legais da matriz DEFAULT.
- **Locale cross-domain:** frontend Vercel (`chat.winegod.ai`) envia para backend Render (`api.winegod.ai`) via header `X-WG-UI-Locale` (mais `X-WG-Market-Country` e `X-WG-Currency`). Cookie cross-domain nao e caminho confiavel.
- **Fallback de traducao:**
  - `fr-FR -> en-US -> pt-BR`
  - `es-419 -> en-US -> pt-BR`
  - `en-US -> pt-BR`
  - `pt-BR` e o fallback absoluto.

## 4. Estrutura criada em F0.2

A fase F0.2 criou os diretorios abaixo com `.gitkeep` em cada um. Conteudo real sera adicionado nas fases F1.1-F1.3 e Onda 7.

- `shared/i18n/` - artefatos de i18n compartilhados (markets.json, dnt.md, glossary.md nas proximas fases).
- `shared/i18n/backup/` - backup semanal de traducoes exportadas do Tolgee (F8.7).
- `shared/legal/BR/` - matriz legal Brasil (LGPD) em pt-BR.
- `shared/legal/DEFAULT/` - matriz legal fallback global em en-US com disclaimer "operated from Brazil".

## 5. Proximos passos apos F0.3

Em ordem, respeitando gates humanos entre cada fase:

- **F0.5 - Bootstrap tooling.** CONCLUIDA. Troca `next lint` (deprecated no Next 15) por `eslint .` com flat config. Instala dependencias agregadas usadas em fases posteriores: `eslint` + plugins, `eslint-plugin-i18next` (F3.1), `swr` (F2.4c), `gray-matter` (F7.1). Nao instala `next-intl` nem Tolgee CLI nem Playwright (ficam em F2.1, F8.x e F9.3 respectivamente).
- **F0.6 - Kill switch duplo (decisao).** CONCLUIDA como documentacao. Plano A (flag dinamica via tabela `feature_flags`, TTL 10-30s) e Plano B (`ENABLED_LOCALES` env var + redeploy, 2-5 min) foram decididos como arquitetura oficial; a implementacao real comeca em F1.6 (tabela) e F1.8 (endpoint). Fail-safe absoluto cai em `["pt-BR"]`. Secao dedicada em `reports/WINEGOD_MULTILINGUE_DECISIONS.md`. Runbook operacional continua em `docs/RUNBOOK_I18N_ROLLBACK.md`.
- **F1.1 (proximo passo real)** - Criar `shared/i18n/markets.json` com 5 paises (BR, US, MX, FR, DEFAULT). Abre a Onda 1 (backend foundations: markets.json, dnt.md, glossary, migrations 015-017, endpoints `PATCH /api/auth/me/preferences` e `GET /api/config/enabled-locales`).

Cada fase acima exige gate humano explicito antes da proxima comecar.
