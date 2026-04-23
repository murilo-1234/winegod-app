# WINEGOD MULTILINGUE - METODO RESUMO EXECUTIVO

Data: 2026-04-23
Status: versao curta V2.1 para founder/admin

---

## 1. O que existe agora

Existe um metodo oficial V2.1 para abrir novos locales no WineGod sem depender da memoria do H4 ou de um caminho fixo do clone principal.

Ele transforma o aprendizado do rollout atual (`pt-BR`, `en-US`, `es-419`, `fr-FR`) em uma sequencia operacional com:

- preflight
- branch/worktree dedicada
- traducao estruturada
- review editorial
- legal/O1
- QA
- canary
- smoke
- log append-only
- resultado
- handoff

---

## 2. Sequencia de alto nivel

1. Definir `<LOCALE>`, `<LOCALE_SHORT>`, `<SOURCE_LOCALE>`, `<COUNTRY_ISO>` e `<JOB_NAME>`.
2. Rodar F0 com branch/worktree dedicada, bloquear write-set sujo e salvar baseline.
3. Preparar routing, fallback, middleware, parity e tests para o locale.
4. Criar `frontend/messages/<LOCALE>.json` a partir do source.
5. Traduzir preservando ICU, tags, plurais e DNT.
6. Rodar cross-review editorial por 2 revisores independentes.
7. Resolver O1 legal e age gate.
8. Rodar parity, build frio e Playwright i18n.
9. Decidir O2/O3 e canary.
10. Ativar dynamic/static enabled locales quando autorizado.
11. Provar frontend publicado e rota `/<LOCALE_SHORT>/c/<SMOKE_SHARE_ID>`.
12. Rodar smoke de producao.
13. Atualizar `reports/i18n_execution_log.md`.
14. Fechar resultado e handoff.

---

## 3. Gates que nao podem ser pulados

- F0 branch/worktree + dirty write-set: evita repetir a cadeia de hotfix do H4.
- Parity: evita JSON quebrado, placeholder perdido ou plural divergente.
- Build frio: evita build incremental mascarar arquivo faltante.
- Review editorial: evita calque e idioma artificial.
- O1 legal: evita ativar locale sem base juridica definida.
- Smoke producao com share prefixado: evita declarar pronto com backend correto e frontend publicado antigo.
- Append-only log: cria trilha de auditoria minima por job.
- Handoff final: evita dependencia de memoria de chat.

---

## 4. Custo humano esperado

Para um locale Classe A/B:

- Founder: 2 a 5 minutos se legal e env/deploy forem simples.
- Agente: cerca de 1 a 2 horas, dependendo de traducao, QA e ajustes.
- Humano nativo: opcional, recomendado quando o mercado for importante ou a IA divergir.

Para Classe C/D:

- Founder: mais tempo de decisao.
- Humano nativo/legal: recomendado ou obrigatorio, conforme risco.

---

## 5. Decisoes humanas tipicas

- O1: legal proprio, bloqueio ou traducao operacional aceita.
- Vercel: atualizar `NEXT_PUBLIC_ENABLED_LOCALES` e redeployar.
- Share smoke: indicar ou criar um `<SMOKE_SHARE_ID>` real para validar `/<LOCALE_SHORT>/c/...`.
- Revisao nativa: IA basta ou humano entra.
- Canary: fechado, comprimido ou gradual.
- Residual: aceitar ou bloquear.

---

## 6. Risco residual padrao

Mesmo com o metodo, os riscos que podem sobrar sao:

- legal sem revisao local especializada
- OG ou alt em ingles
- polimento editorial S3
- scripts ainda nao parametrizados automaticamente para `<LOCALE>`
- share smoke depende de id real publicado
- CJK/RTL sem suite visual especifica

Esses riscos nao ficam escondidos. O metodo obriga que eles aparecam em Decisions, Resultado e Handoff.

---

## 7. Veredito executivo

O WineGod agora tem um metodo oficial utilizavel para abrir novos locales.

Ele nao e "automacao total", mas ja e operacional e autocontido: qualquer proximo job consegue seguir uma ordem, preencher templates, rodar gates e gerar evidencias a partir do `$repoRoot` escolhido, seja branch no clone principal ou worktree dedicada.
