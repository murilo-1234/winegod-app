# WINEGOD MULTILINGUE - METODO GAPS E PENDENCIAS

Data: 2026-04-23
Status: gaps isolados do primeiro metodo oficial

---

## 1. Objetivo

Este documento separa o que ainda nao virou metodo fechado. Ele existe para impedir que o metodo base prometa automacao que ainda nao existe.

---

## 2. Gaps tecnicos atuais

### G1 - `tools/i18n_parity.mjs` ainda e especifico dos 4 locales atuais

Estado observado:

- o script lista `["pt-BR", "en-US", "es-419", "fr-FR"]`
- para validar `<LOCALE>`, o job precisa adaptar o script ou refatora-lo para receber lista parametrica

Regra ate resolver:

- todo job de novo locale deve incluir uma decisao T3 sobre parity validator
- nao declarar F2/F4 verdes se `<LOCALE>` nao entrou no gate estrutural

Melhoria futura:

- adicionar `--locales` ou ler de arquivo/config oficial

### G2 - Smoke PowerShell atual cobre Tier 1, nao qualquer locale

Estado observado:

- `scripts/i18n/smoke_test.ps1` existe e e Windows-friendly
- rotas estao fixas para os 4 locales atuais

Regra ate resolver:

- cada job deve usar o smoke template parametrico do metodo

Melhoria futura:

- criar `scripts/i18n/smoke_locale.ps1 -Locale <LOCALE> -Short <LOCALE_SHORT> -BaseUrl <URL>`

### G3 - Ativacao de `enabled_locales` ainda depende de acesso operacional

Estado:

- backend usa `feature_flags.enabled_locales`
- alterar producao exige credencial DB ou endpoint admin futuro
- Vercel `NEXT_PUBLIC_ENABLED_LOCALES` exige dashboard/redeploy
- V2 endureceu o gate final: override local nao basta; o frontend publicado precisa ser provado por smoke real

Regra:

- registrar como intervencao humana/operacional quando nao houver acesso aprovado
- guardar evidencia de deploy frontend publicado
- validar `/<LOCALE_SHORT>/c/<SMOKE_SHARE_ID>` em producao antes de declarar fechamento

Melhoria futura:

- endpoint admin autenticado para toggle de locale
- runbook unico de ativacao com log automatico
- script dedicado para coletar deploy id/header Vercel e smoke share prefixado

### G4 - Middleware e routing precisam de auditoria por rota nova

Estado:

- o H4 aprendeu que matcher incompleto pode deixar rotas como `/plano`, `/conta`, `/favoritos` fora do comportamento esperado

Regra:

- novo locale precisa testar rotas principais sem e com prefixo
- se a rota nao for publica com prefixo por design, isso precisa estar documentado

Melhoria futura:

- matriz oficial de rotas i18n: publica prefixada, app privada, legal, share, asset, API

### G5 - Legal local nao e automatizavel com seguranca

Estado:

- o fechamento ES/FR aceitou legal como traducao operacional
- isso nao equivale a revisao juridica local

Regra:

- O1 sempre explicita se legal e proprio, bloqueado ou traducao operacional
- mercado comercial regulado deve exigir decisao do founder

Melhoria futura:

- biblioteca de templates revisados por jurisdicao

### G6 - Qualidade editorial ainda depende de julgamento

Estado:

- cross-review multi-IA funcionou no H4
- nao prova suficiencia para scripts distantes, polidez asiatica ou mercado de receita alta

Regra:

- Classe C/D recomenda humano nativo antes de full rollout publico

Melhoria futura:

- rubricas por idioma e checklists de termos nativos

### G7 - CJK/RTL nao tem gate visual especifico

Estado:

- Playwright cobre rotas i18n atuais
- nao ha prova de layout robusto para CJK ou RTL

Regra:

- nao abrir Classe C/D como se fosse Classe A/B

Melhoria futura:

- adicionar suite visual para texto sem espacos, fonte CJK, line-height, RTL e overflow

### G8 - Observabilidade por locale nao e gate universal ainda

Estado:

- Sentry/PostHog aparecem como stack alvo em docs antigos
- o fechamento atual validou por smoke e checks diretos

Regra:

- se observabilidade existir, checar tags por locale
- se nao existir, nao bloquear o job por isso, mas registrar residual

Melhoria futura:

- gate padrao de erro JS/HTTP por locale nos primeiros minutos do canary

### G9 - Tolgee/Fiverr vs cross-IA nao esta 100% unificado operacionalmente

Estado:

- handoff oficial antigo previa Tolgee/Fiverr
- H4 final aceitou AI Native Review Pack como caminho padrao

Regra:

- metodo atual usa repo snapshots + cross-review multi-IA como default
- Tolgee/Fiverr viram escalacao ou fluxo futuro quando houver operacao madura

Melhoria futura:

- decidir oficialmente se Tolgee volta como workflow padrao ou fica como opcional

### G10 - Smoke de share depende de um id real publicado

Estado:

- o gate V2 exige `/<LOCALE_SHORT>/c/<SMOKE_SHARE_ID>`
- id sintetico nao serve, porque pode produzir 404 por inexistencia do share e mascarar o teste de locale

Regra ate resolver:

- cada job precisa preencher O7 com um share publico real antes da ativacao
- se nao existir share seguro, criar/publicar um antes do canary ou manter o locale sem ativacao

Melhoria futura:

- manter um share publico de smoke controlado e documentado para release i18n

---

## 3. Pontos humanos inevitaveis

Sempre humanos ou operacionalmente dependentes:

- O1 legal quando envolve risco comercial/juridico
- Vercel dashboard para `NEXT_PUBLIC_ENABLED_LOCALES`, salvo automacao futura
- Redeploy frontend depois de env build-time
- acesso a DB/feature flags de producao
- escolha ou criacao de um `<SMOKE_SHARE_ID>` real se nao houver fixture publica segura
- revisao juridica local
- revisao nativa humana para Classe C/D ou mercado importante
- aprovacao de residual que afeta risco de marca/legal

Nao devem ser tratados como humanos:

- parity
- build frio
- Playwright
- smoke
- consolidacao de reviews IA
- geracao de docs finais

---

## 4. Excecoes por classe de locale

### Variante pequena

Pode ter metodo reduzido, mas ainda precisa:

- parity
- review editorial
- legal/O1
- smoke
- handoff

### Novo idioma latino

Precisa de:

- cross-review multi-IA
- QA visual de texto longo
- legal/O1

### Script distante

Precisa de cautela extra:

- review humano recomendado
- QA visual mais forte
- decisao explicita sobre fonte, fonte tipografica e line breaks

### RTL

Nao usar metodo basico sem plano adicional:

- directionality
- layout mirroring
- icons
- inputs
- screenshots

### Mercado legal sensivel

Nao ativar publicamente sem O1 forte:

- legal local
- disclaimers
- compra/CTA
- idade minima

---

## 5. O que ainda pode melhorar

Backlog metodologico:

- Parametrizar `tools/i18n_parity.mjs`.
- Criar `scripts/i18n/smoke_locale.ps1`.
- Criar matriz oficial de rotas por tipo.
- Criar script de gate final que combina dynamic backend, deploy frontend publicado e share prefixado.
- Manter fixture publica de share smoke por ambiente.
- Criar checklist especifico para Classe C/D.
- Criar validador de `shared/legal` por locale.
- Adicionar checklist de hash visual por locale.
- Criar template de prompt por familia linguistica.
- Criar script de resultado que coleta outputs automaticamente.
- Criar endpoint admin seguro para enabled locales.

---

## 6. Regra de honestidade

Enquanto estes gaps existirem, o metodo oficial e utilizavel, mas nao deve afirmar:

- "100% automatizado"
- "sem humano em todos os casos"
- "qualquer idioma sem adaptacao"
- "legal resolvido por IA"
- "CJK/RTL suportado igual a idioma latino"

O correto e:

```text
Metodo oficial utilizavel para abrir novos locales com automacao local alta,
gates claros e pontos humanos isolados. Alguns scripts ainda precisam ser
parametrizados por job, e idiomas/mercados de alto risco exigem cautela extra.
```
