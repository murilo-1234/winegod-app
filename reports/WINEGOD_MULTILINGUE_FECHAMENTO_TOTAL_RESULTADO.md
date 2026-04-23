# WINEGOD MULTILINGUE - FECHAMENTO TOTAL

**Data:** 2026-04-23  
**Status final:** concluido  
**Commit de fechamento:** `9be95488672a5eb742fa337d4bb533c9f3903230`

## Escopo fechado

- `O1` virou `A`
- `pt-BR`, `en-US`, `es-419` e `fr-FR` ativos
- legal `es-419` e `fr-FR` publicado
- redirects legacy (`/privacy`, `/terms`, `/data-deletion`) alinhados por locale
- age gate apontando para legal do locale renderizado
- `feature_flags.enabled_locales` atualizado para `["pt-BR","en-US","es-419","fr-FR"]`

## Mudancas executadas

### Frontend / roteamento

- helper novo: `frontend/lib/legal-routing.ts`
- `frontend/app/legal/[country]/[lang]/[doc]/page.tsx`
  - matriz publicada expandida para `pt-BR`, `en-US`, `es-419`, `fr-FR`
  - fallback canonico agora respeita o `lang` pedido quando ele existe
- `frontend/app/age-verify/page.tsx`
  - links de `terms` e `privacy` passam a seguir o locale real da pagina
- `frontend/app/privacy/page.tsx`
- `frontend/app/terms/page.tsx`
- `frontend/app/data-deletion/page.tsx`
  - redirects legacy passam a usar o mesmo helper

### Legal docs

Arquivos publicados:

- `shared/legal/DEFAULT/es-419/privacy.md`
- `shared/legal/DEFAULT/es-419/terms.md`
- `shared/legal/DEFAULT/es-419/data-deletion.md`
- `shared/legal/DEFAULT/es-419/cookies.md`
- `shared/legal/DEFAULT/fr-FR/privacy.md`
- `shared/legal/DEFAULT/fr-FR/terms.md`
- `shared/legal/DEFAULT/fr-FR/data-deletion.md`
- `shared/legal/DEFAULT/fr-FR/cookies.md`

Ajuste adicional:

- `shared/legal/BR/pt-BR/cookies.md`
  - removido o comentario antigo que dizia que a pagina nao era publicada

### QA / tooling

- `frontend/tests/i18n/legal-routing.spec.ts` criado
- `frontend/tests/i18n/legal-visual.spec.ts` expandido para ES/FR
- `frontend/playwright.config.ts`
  - suite principal passa a refletir o estado final com 4 locales
- `frontend/playwright.share-disabled.config.ts`
  - suite dedicada preserva a regressao do caso `locale desligado` em share route
- `tools/enabled_locales_check.mjs`
  - default alinhado ao estado final de 4 locales

## Validacao local

- `node tools/i18n_parity.mjs`
  - `OK: 4 locales with parity (0 warnings to review)`
- `cd frontend && npm run lint`
  - `0 errors`, `10 warnings` preexistentes do Next
- `cd frontend && npm run build`
  - verde
- `cd frontend && npx playwright test`
  - `74 passed`
- `cd frontend && npm run test:e2e:share-disabled`
  - `4 passed`

## Ativacao dinamica

- Banco: `feature_flags.enabled_locales`
  - de `["pt-BR","en-US"]`
  - para `["pt-BR","en-US","es-419","fr-FR"]`
- API publica revalidada:
  - `https://winegod-app.onrender.com/api/config/enabled-locales`
  - resposta final: `{"enabled_locales":["pt-BR","en-US","es-419","fr-FR"], ... "source":"db"}`
- `node tools/enabled_locales_check.mjs`
  - `OK: static and dynamic enabled_locales lists match.`

## Producao revalidada

Deploy para `main` realizado. A Vercel propagou o frontend novo e o backend ja refletia os 4 locales pela flag dinamica.

Checagens confirmadas em producao:

- `/es/privacy` -> `/legal/DEFAULT/es-419/privacy`
- `/fr/privacy` -> `/legal/DEFAULT/fr-FR/privacy`
- `/es/terms` -> `/legal/DEFAULT/es-419/terms`
- `/fr/data-deletion` -> `/legal/DEFAULT/fr-FR/data-deletion`
- `/legal/DEFAULT/es-419/cookies` -> `200`
- `/legal/DEFAULT/fr-FR/cookies` -> `200`
- `/api/config/enabled-locales` -> 4 locales

## Residuais aceitos

- `O2 = B`
  - OG de `es-419` e `fr-FR` continua em ingles
- `O3 = aceitar residual`
  - `alt` de OG continua fixo em ingles
- legal `es-419` e `fr-FR`
  - traducao operacional publicada sem revisao juridica local

## Observacao de teste backend

- `python -m pytest -q` neste branch continua no mesmo estado preexistente de teardown/capture no Windows; nao foi introduzido por este fechamento.
- Nao houve mudanca de codigo backend nesta rodada. A ativacao backend foi feita pela fonte dinamica oficial (`feature_flags`).

## Veredito

**Projeto fechado no escopo autorizado.**

- 4 locales ativos: **sim**
- producao refletindo `pt-BR`, `en-US`, `es-419`, `fr-FR`: **sim**
- codigo, docs legais e roteamento alinhados: **sim**
