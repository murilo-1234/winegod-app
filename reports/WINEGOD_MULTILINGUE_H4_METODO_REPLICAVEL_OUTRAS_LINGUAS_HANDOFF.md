# WINEGOD MULTILINGUE - HANDOFF DE METODO REPLICAVEL PARA OUTRAS LINGUAS

**Data:** 2026-04-22  
**Origem do metodo:** execucao completa do H4 em `pt-BR`, `en-US`, `es-419`, `fr-FR`  
**Objetivo deste arquivo:** transformar o que foi feito no H4 em um formato reaproveitavel para novas linguas, novos mercados ou novas ondas de i18n

---

## 1. O que este handoff e

Este documento nao e um relatorio de um idioma especifico. Ele e um **metodo operacional**.

Ele responde a pergunta:

> "Se formos abrir um novo locale depois do H4, qual e o processo minimo que funciona, quais gates precisam existir, quais artefatos precisam ser salvos e como administrar Claude/Codex sem virar improviso?"

O metodo aqui e **replicavel**, mas nao e 100% generico. Ele parte da arquitetura atual do projeto:

- `next-intl`
- fallback chain por locale
- middleware com prefixos publicos
- mensagens em `frontend/messages/*.json`
- QA com Playwright
- trilha administrativa separada de trilha de codigo

---

## 2. Quando usar este metodo

Use este handoff em 3 cenarios:

1. **Novo idioma completo**
   - exemplo: `de-DE`, `it-IT`, `ja-JP`

2. **Nova variante de mercado/idioma**
   - exemplo: `en-GB`, `es-ES`, `fr-CA`

3. **Nova onda de endurecimento i18n**
   - exemplo: locale ja existe, mas ainda depende de fallback demais, tem leaks de outro idioma, metadata errada, errors nao localizados, QA visual pouco confiavel

Nao use este metodo quando a mudanca for so:

- um ajuste de 2 ou 3 strings;
- um polimento isolado de UX;
- uma decisao puramente editorial sem impacto estrutural.

---

## 3. O que o H4 ensinou de forma reutilizavel

O H4 deixou 8 licoes que valem para qualquer novo locale:

1. **Nao abrir locale so com fallback silencioso.**  
   Locale sem produto proprio gera falsa sensacao de prontidao.

2. **Separar problema estrutural de problema editorial.**  
   Parity, placeholders, routing, metadata, errors, middleware sao uma classe. Naturalidade e tom sao outra.

3. **Criar branch e baseline antes de tocar em qualquer coisa.**  
   Sem baseline, todo bug vira discussao subjetiva.

4. **Fazer commits atomicos por concern.**  
   Metadata, hardcoded UI, error contract, middleware, formatting, translation, QA: cada um em sua trilha.

5. **Ter um gate estrutural determinista.**  
   `tools/i18n_parity.mjs` foi decisivo. Sem isso, traducao vira opiniao.

6. **Tratar release policy como trilha separada.**  
   Legal, OG image, `alt`, rollout e canary nao devem ser misturados com fix de codigo do app.

7. **Administracao por fase funciona melhor que execucao solta.**  
   Prompt, resposta, veredito, proxima fase ou corretivo. Sempre com trilha salva.

8. **Auditoria final precisa aceitar corretivo.**  
   O H4 so fechou direito porque a auditoria conseguiu aprovar o nucleo tecnico e isolar 2 desvios reais de qualidade textual.

---

## 4. Estrutura-padrao replicavel

Para qualquer novo locale, usar esta estrutura:

### 4.1 Artefatos administrativos

- `reports/<JOB>_PLANO_EXECUCAO_FINAL.md`
- `reports/<JOB>_HANDOFF.md`
- `reports/<JOB>_PROMPT_CLAUDE_F0.md`
- `reports/<JOB>_CLAUDE_RESPOSTA_F0.md`
- `reports/<JOB>_PROMPT_CLAUDE_F<n>.md`
- `reports/<JOB>_CLAUDE_RESPOSTA_F<n>.md`
- `reports/<JOB>_CODEX_VEREDITO_F<n>.md`

### 4.2 Diretorio de baseline

- `reports/_backup_<job>/`

Deve conter:

- backup escopado dos arquivos que serao tocados
- estado inicial do git
- baseline de lint/build/teste
- contagem de leaves dos locales
- qualquer diff ou grep usado como prova

### 4.3 Diario administrativo

O handoff do job precisa registrar, para cada fase:

- status
- prompt emitido
- resposta recebida
- escopo autorizado
- escopo vedado
- evidencias
- julgamento do administrador
- decisao seguinte

---

## 5. Fases replicaveis

O H4 mostrou uma sequencia que da para reaproveitar quase inteira.

### F0. Setup seguro e baseline

Objetivo:

- criar branch dedicada
- salvar backup escopado
- registrar baseline tecnico
- contar leaves dos locales atuais

Saida minima:

- branch pronta
- `reports/_backup_<job>/` preenchido
- baseline conhecido

Sem F0, o resto perde auditabilidade.

### F1. Core fixes antes da traducao

Esta fase corrige vazamentos arquiteturais antes de popular o locale novo.

Checklist reutilizavel:

- metadata locale-aware
- componentes com texto hardcoded migrados para `next-intl`
- contrato de erro sem string inline de um idioma fixo
- middleware preservando locale em redirects/rewrite
- formatacao sensivel a locale (`Intl.NumberFormat`, datas, etc.)

Regra:

- traduzir arquivo gigante antes de consertar esses pontos costuma mascarar bug real

### F2. Gate estrutural

Criar ou reaproveitar um validador como `tools/i18n_parity.mjs`.

Ele precisa checar:

- missing keys
- extra keys
- ICU placeholders
- rich tags
- plural branches
- warnings heuristicos de leak de idioma

Esse gate e obrigatorio antes de declarar que um locale "existe".

### F3. Popular o locale

So entra aqui depois de F1/F2 estabilizados.

Regras:

- basear no locale-fonte definido para aquele caso
- preservar placeholders/tags/plurals/selects
- obedecer a variante escolhida
- corrigir desde ja os textos conhecidos como sensiveis

Exemplos de texto sensivel:

- age gate
- legal fallback banner
- prompts de ajuda
- chat input default
- mensagens de erro visiveis

### F4. Hardening

Mudancas tipicas:

- `Accept-Language` como fallback final
- banners de fallback tecnico reescritos em linguagem de usuario
- polimentos da lingua-base que ficaram no caminho

Essa fase melhora robustez, mas nem sempre deve bloquear o canary inicial.

### F5. QA determinista e visual

Precisa ter 2 camadas:

1. **Specs deterministas**
   - routing
   - locale prefix
   - metadata/title
   - redirects

2. **Baselines visuais**
   - home guest
   - ajuda/help
   - age gate
   - legal, se aplicavel

Sem essa fase, locale novo passa "na teoria" e quebra na superficie real.

### F6. Auditoria editorial complementar

Opcional, mas muito util para locale novo.

Serve para:

- naturalidade
- neutralidade regional
- tom de produto
- erros que parity nao pega

Pode ser multi-IA, humano, ou ambos.

### FR. Release policy

Trilha separada de codigo.

Perguntas classicas:

- legal desse locale vai existir ou vai cair em fallback?
- OG image desse locale vai existir ou vai cair em ingles?
- `alt` ou metadata residual em outro idioma e aceitavel?
- qual e a ordem do canary?

Sem FR, o projeto fica tecnicamente pronto e operacionalmente indefinido.

---

## 6. Template mental para qualquer novo locale

Ao abrir um novo locale `<L>`, preencher antes esta ficha:

### 6.1 Identidade do locale

- locale alvo: `<L>`
- tipo: `idioma novo` ou `variante de mercado`
- prefixo publico: `<prefix>` ou `sem prefixo`
- fallback chain: `<L> -> ...`
- locale-fonte editorial: `en-US` ou outro

### 6.2 Superficie impactada

- `frontend/messages/<L>.json`
- metadata de rotas importantes
- componentes com texto visivel
- errors
- middleware/routing
- legal
- OG/share
- visual baselines

### 6.3 Politicas que precisam de decisao

- legal publica ou fallback?
- OG proprio ou fallback?
- rollout imediato ou canary progressivo?
- precisa auditoria editorial antes de abrir para publico?

Se essa ficha nao estiver preenchida, o trabalho comeca cego.

---

## 7. Checklist replicavel de auditoria

Quando o executor disser "pronto", o administrador deve sempre checar:

1. O locale tem o mesmo numero de leaves do baseline esperado?
2. `node tools/i18n_parity.mjs` fecha com exit 0?
3. Nao ha strings hardcoded antigas nos componentes?
4. Metadata critica foi localizavel de verdade?
5. Error contract parou de depender de texto cru em idioma fixo?
6. Middleware preserva locale em redirects sensiveis?
7. Formatacao de moeda/data respeita locale ativo?
8. Baselines visuais realmente divergem por locale?
9. O locale novo esta natural ou so estruturalmente correto?
10. O que resta e bug de produto ou decisao operacional?
11. **`git ls-files --others --exclude-standard` nao retorna arquivos de producao?** (licao H4: divida de untracked acumulada quebra deploy)
12. **`git status` em frontend/, backend/, shared/ nao mostra `M` nao commitados?** (licao H4: arquivos modified locais mascaram o estado de git)
13. **`rm -rf .next && npm run build` passa limpo?** (licao H4: build incremental mascara arquivos untracked)
14. **Smoke test curl com N rotas em producao pos-deploy retorna 200?** (licao H4: sem smoke obrigatorio, rota 404 de legal passou despercebida por minutos)

Esse ultimo item e central. O H4 melhorou muito quando separou essas duas coisas.

### 7.1 Licoes aprendidas no H4 (2026-04-22/23)

Tres padroes que quebraram o deploy e devem ser regra daqui em diante:

#### Licao 1 - Divida de untracked acumulada

**Sintoma:** build local passava sempre, build Vercel falhou 4 vezes seguidas com `Module not found`.

**Raiz:** 65+ arquivos estavam no disco local desde 21/abr mas nunca commitados. Sem deploy Vercel no meio, a divida nao foi sinalizada. Arquivos tracked importavam simbolos/rotas que existiam so local.

**Regra:** antes de merge em `main`, rodar `git ls-files --others --exclude-standard` e `git status` no frontend inteiro. Se houver arquivo de producao nao commitado ou modified nao commitado, **abortar merge ate resolver**. Adicionar ao preflight F0 obrigatoriamente.

#### Licao 2 - Build incremental mascara untracked

**Sintoma:** `npm run build` local passou em todas as rodadas, mas o Vercel falhava.

**Raiz:** `.next/` ja tinha artefato de builds anteriores que resolveram os imports internamente. Vercel comecou do zero e nao encontrou.

**Regra:** **toda revalidacao final (Trilha C) deve rodar `rm -rf .next && npm run build`, nao apenas `npm run build`**. So build a frio e prova confiavel.

#### Licao 3 - Smoke test nao pode ser opcional

**Sintoma:** deploy verde no Vercel, mas `/privacy`, `/terms`, `/data-deletion` em producao retornavam 404 (markdowns de `shared/legal/` estavam untracked).

**Raiz:** Vercel so valida build webpack, nao conteudo de runtime filesystem. Se o codigo roda mas o arquivo .md nao existe em producao, a rota retorna 404 sem warning no deploy.

**Regra:** **toda Trilha de deploy deve terminar com smoke test obrigatorio**:
```bash
for path in "/" "/ajuda" "/plano" "/conta" "/favoritos" "/age-verify" "/privacy" "/terms" "/data-deletion"; do
  code=$(curl -s -o /dev/null -L -w "%{http_code}" --cookie "wg_age_verified=BR:18:2026-01-01T00:00:00Z" "https://PROD_URL$path")
  echo "$code  $path"
done
```
Qualquer rota 404/5xx bloqueia declaracao de H4/H<N> fechado.

---

## 8. Categorias padrao de problema

Para reaproveitar em outras linguas, usar estas categorias:

### S1. Bloqueante

Quando impede dizer que o locale existe como produto:

- arquivo de messages incompleto
- metadata em idioma errado
- componentes centrais com texto fixo
- errors visiveis em idioma errado
- middleware quebrando prefixo/rota
- fallback tecnico visivel ao usuario

### S2. Importante

Quando o locale existe, mas ainda causa UX ruim:

- formatacao de moeda/data errada
- fallback global ruim para estrangeiro
- baselines visuais enganando
- texto sensivel com tom ruim

### S3. Polimento

Quando ja nao bloqueia rollout:

- microcopy
- diacriticos em banner secundario
- frase menos natural, mas compreensivel

### D. Decisao operacional

Nao chamar isso de bug se for:

- legal por publicar ou nao
- OG image de locale
- ordem de canary
- risco residual conscientemente aceito

---

## 9. O que deve ser padronizado de verdade

Se for replicar para outras linguas, estes 7 itens merecem padrao fixo:

1. **Naming dos arquivos de job**
   - mesmo padrao de prompt/resposta/veredito/handoff

2. **F0 sempre identica**
   - branch + backup + baseline + contagem de leaves

3. **Validador estrutural unico**
   - um script comum, so refinado quando necessario

4. **Diario administrativo**
   - sempre igual, para qualquer job

5. **Criterio de "pronto"**
   - parity + QA + sem leaks + release decisions mapeadas

6. **Separacao entre codigo e release**
   - nunca misturar

7. **Loop de corretivo**
   - aprovou -> proxima fase
   - falhou -> prompt corretivo especifico

---

## 10. Metodo minimo, mesmo incompleto

Se quiser um formato reduzido para novos idiomas, usar este MVP:

### MVP-A. Antes de traduzir

- F0 completo
- F1 apenas nos leaks reais
- F2 validador pronto

### MVP-B. Depois de traduzir

- `messages/<L>.json` com parity completa
- 1 rodada de audit editorial rapida
- 1 spec determinista
- 1 baseline visual por superficie critica

### MVP-C. Antes de abrir canary

- decidir legal
- decidir OG
- decidir rollout

Esse MVP e incompleto comparado ao H4 pleno, mas ja evita os erros mais caros.

---

## 11. Padrrao de prompt para executor

Para qualquer nova lingua, o prompt deve sempre travar:

- fase exata
- write-set exato
- o que pode fazer
- o que nao pode fazer
- quais validacoes sao obrigatorias
- qual arquivo de resposta precisa ser gerado
- qual commit message usar, se houver commit

Sem isso, o executor expande escopo.

---

## 12. Padrrao de resposta do executor

Toda resposta deve conter:

- status
- escopo executado
- arquivos alterados
- validacoes rodadas
- exit codes
- desvios ou bloqueios
- commit hash
- veredito para o administrador

O H4 funcionou melhor quando isso ficou obrigatorio.

---

## 13. Padrrao de decisao do administrador

O administrador nunca deve responder so "ok".

Deve sempre registrar:

- aprovado
- aprovado com ressalvas
- corretivo
- supersedido por execucao consolidada

E precisa dizer:

- o que validou
- o que nao validou
- por que liberou ou travou
- qual e o proximo gate

---

## 14. O que ainda nao esta completamente padronizado

Este metodo ainda nao resolveu 100%:

- como padronizar legal para novos locales sem virar projeto juridico paralelo
- como padronizar OG locale-specific sem espalhar strings duplicadas
- como medir naturalidade sem depender demais de julgamento editorial
- como diferenciar "locale novo grande" de "market variant pequeno"
- como automatizar melhor o gate visual sem carregar muito custo operacional

Entao este handoff e **replicavel, mas nao final**.

Ele ja serve como metodo real.

---

## 15. Formato resumido para copiar em novos jobs

```markdown
JOB: <nome do locale/onda>

F0. setup seguro + baseline
F1. core leaks
F2. parity validator
F3. locale population
F4. hardening
F5. deterministic + visual QA
F6. editorial audit (opcional)
FR. release decisions

Gate de pronto:
- parity 100%
- sem hardcoded leaks
- metadata correta
- errors corretos
- middleware correto
- baselines visuais confiaveis
- FR mapeada
```

---

## 16. Fecho

O que fizemos no H4 pode sim virar metodo para outras linguas.

O formato replicavel e este:

- branch + baseline
- core fixes antes da traducao
- gate estrutural determinista
- traducao com regras explicitas
- hardening separado
- QA determinista + visual
- auditoria editorial opcional
- release policy fora da trilha de codigo
- diario administrativo por fase
- corretivo sempre que auditoria encontrar problema real

Se quiser, o proximo passo natural e eu transformar este handoff em um **template ainda mais operacional**, com placeholders tipo `<LOCALE>`, `<PREFIX>`, `<SOURCE_LOCALE>`, `<CANARY_STAGE>`, pronto para clonar em cada novo idioma.
