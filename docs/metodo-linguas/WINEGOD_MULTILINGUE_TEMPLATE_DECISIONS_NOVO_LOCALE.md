# WINEGOD MULTILINGUE - TEMPLATE DECISIONS NOVO LOCALE

Status: template
Uso: copiar para `reports/WINEGOD_<JOB_NAME>_DECISIONS.md`.

---

## 1. Identificacao

- Data:
- Founder:
- Operador:
- Job: `<JOB_NAME>`
- Locale: `<LOCALE>`
- Prefixo publico: `/<LOCALE_SHORT>`
- Source locale: `<SOURCE_LOCALE>`
- Pais legal: `<COUNTRY_ISO>`
- Classe do locale: `<LOCALE_CLASS>`

---

## 2. Decisoes tecnicas

### T1 - Source locale e fallback chain

**Decisao:**

- [ ] A - usar `<SOURCE_LOCALE>` como source editorial e `<FALLBACK_CHAIN>` como fallback.
- [ ] B - usar outro source/fallback.

**Escolha:**

**Racional:**

**Impacto:**

### T2 - Config estrutural

**Decisao:**

- [ ] A - atualizar configs existentes para reconhecer `<LOCALE>`.
- [ ] B - nao atualizar configs porque o locale sera validado por mecanismo parametrico ja existente.

**Arquivos esperados:**

- `frontend/i18n/routing.ts`
- `frontend/i18n/request.ts`
- `frontend/lib/i18n/fallbacks.ts`
- `frontend/lib/i18n/formatters.ts`
- `frontend/middleware.ts`
- `tools/i18n_parity.mjs`
- `frontend/tests/i18n/*`

**Escolha:**

**Racional:**

### T3 - Parity validator

**Decisao:**

- [ ] A - `tools/i18n_parity.mjs` sera atualizado para incluir `<LOCALE>`.
- [ ] B - `tools/i18n_parity.mjs` sera refatorado/parametrizado.
- [ ] C - outro validador sera usado temporariamente e documentado.

**Escolha:**

**Racional:**

**Residual aceito, se houver:**

---

## 3. Decisoes operacionais

### O1 - Legal `<LOCALE>`

**Decisao:**

- [ ] A - publicar legal proprio em `shared/legal/<COUNTRY_ISO>/<LOCALE>/*` antes de ativar.
- [ ] B - manter `<LOCALE>` fora de `enabled_locales` publico ate legal proprio existir.
- [ ] C - publicar legal como traducao operacional sem revisao juridica local, com risco aceito.

**Escolha do founder:**

**Racional:**

**Pendencia humana residual:**

### O2 - OG image localizado

**Decisao:**

- [ ] A - localizar OG image/copy para `<LOCALE>` agora.
- [ ] B - aceitar OG em ingles como residual consciente no primeiro canary.

**Escolha:**

**Racional:**

**Residual aceito:**

### O3 - OG alt/static metadata

**Decisao:**

- [ ] A - tornar alt/static metadata locale-aware agora.
- [ ] B - aceitar alt/static em ingles como residual por limitacao atual.

**Escolha:**

**Racional:**

**Residual aceito:**

### O4 - Revisao nativa humana

**Decisao:**

- [ ] A - cross-review multi-IA basta para este job.
- [ ] B - humano nativo recomendado antes de full rollout, mas canary fechado pode seguir.
- [ ] C - humano nativo obrigatorio antes de qualquer producao publica.

**Escolha:**

**Racional:**

**Gatilhos para escalar:**

### O5 - Canary strategy

**Decisao:**

- [ ] A - canary fechado, sem publico amplo.
- [ ] B - canary comprimido com smoke imediato.
- [ ] C - canary gradual em etapas.
- [ ] D - nao ativar ainda; somente deixar pronto em codigo/docs.

**Escolha:**

**Racional:**

**Rollback:**

### O6 - Vercel/Render intervencao humana

**Decisao:**

- [ ] A - founder atualiza Vercel `NEXT_PUBLIC_ENABLED_LOCALES` e dispara redeploy.
- [ ] B - operador com acesso aprovado executa.
- [ ] C - nao aplicavel porque nao havera ativacao remota.

**Escolha:**

**Racional:**

### O7 - Share smoke publicado

**Decisao:**

- [ ] A - usar um share publico existente como `<SMOKE_SHARE_ID>` para validar `/<LOCALE_SHORT>/c/<SMOKE_SHARE_ID>`.
- [ ] B - criar/publicar um share seguro para smoke antes da ativacao.
- [ ] C - nao ativar ate existir share id real para smoke.

**Escolha:**

**SMOKE_SHARE_ID aprovado:**

**Racional:**

---

## 4. Residuais aceitos

Preencher apenas o que foi aceito conscientemente.

| ID | Classe | Descricao | Risco | Dono | Data para revisitar |
|---|---|---|---|---|---|
| R1 |  |  |  |  |  |

---

## 5. Pendencias humanas finais

| ID | Pendencia | Por que e humana | Bloqueia canary? | Dono |
|---|---|---|---|---|
| H1 |  |  |  |  |

---

## 6. Assinatura

```text
Founder:
Data:
O1:
O2:
O3:
O4:
O5:
O7:
Autorizacao de ativacao remota: SIM/NAO
```

---

## 7. Veredito de decisions

- [ ] Decisions suficientes para seguir implementacao local.
- [ ] Decisions suficientes para ativar canary.
- [ ] Decisions insuficientes; locale deve ficar em codigo/docs, sem producao.
