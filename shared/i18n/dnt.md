# WineGod.ai - Do Not Translate (DNT)

Este documento lista nomes, termos e padroes que NAO devem ser traduzidos em nenhum contexto do produto: UI (frontend Next.js), plataforma de traducao (Tolgee), Baco (prompts e overlays da Onda 6), paginas legais (Onda 7), conteudo de vinho, e-mails, notificacoes, descricoes de compartilhamento e documentos de marketing.

Gerado em F1.2. Fonte de verdade unica para decisoes de "traduzir vs preservar" em pt-BR, en-US, es-419 e fr-FR.

---

## 1. Regra geral

- Termos listados neste arquivo devem permanecer EXATAMENTE como estao, incluindo capitalizacao, espacos, pontuacao e hifens.
- Se um termo esta em caixa alta, deve continuar em caixa alta. Se tem hifen, mantem o hifen.
- Esta regra vale para TODOS os idiomas suportados. Nao ha excecao cultural.
- Se a mensagem for traduzida e o termo DNT cair no meio da frase, o termo fica intocado e o resto da frase se adapta ao idioma ao redor.
- Na duvida entre preservar ou traduzir: PRESERVAR. Traducao errada de nome proprio ou marca e pior do que preservar.

---

## 2. Marca e produto

Nomes de marca e produtos proprios do WineGod e contexto relacionado. Nunca traduzir. Nunca adaptar. Nunca "localizar".

- WineGod
- WineGod.ai
- Baco
- Cicno
- Vivino
- Wine-Searcher
- Delectable

Observacoes:

- `Baco` e nome de personagem / marca. NAO traduzir para `Bacchus`, `Bacchus AI`, `Dionysus`, `Dioniso` ou variantes mitologicas em outro idioma.
- `WineGod` e marca. NAO traduzir para `Deus do Vinho`, `Dios del Vino`, `Dieu du Vin`, `God of Wine` ou similares.
- `WineGod.ai` com dominio completo tambem e marca; nunca dividir ou inverter.
- `Cicno` e nome proprio da base de usuarios ancoragem; nunca traduzir nem flexionar.
- `Vivino`, `Wine-Searcher`, `Delectable` sao plataformas externas referenciadas apenas quando necessario em contexto de produto; jamais traduzidas. Atencao: Regra R1 do projeto (ver `CLAUDE.md`) proibe mencionar Vivino para o usuario final no chat; aqui o DNT cobre apenas a grafia correta em contextos internos e documentos.

---

## 3. Nomes de vinhos, produtores, vinicolas e rotulos

Regra:

- NUNCA traduzir nomes proprios de vinhos, vinicolas, produtores, negociantes, cuvees, rotulos e marcas comerciais de vinho.
- Esta regra vale para os 3.8M de vinhos da base, mesmo que o nome tenha palavras que pareceriam traduziveis em isolado.

Exemplos (lista nao exaustiva, apenas referencia):

- Chateau Margaux
- Chateau Lafite Rothschild
- Chateau Mouton Rothschild
- Chateau Petrus
- Opus One
- Sassicaia
- Tignanello
- Ornellaia
- Masseto
- Vega Sicilia
- Unico
- Catena Zapata
- Almaviva
- Concha y Toro
- Don Melchor
- Dom Perignon
- Krug
- Ruinart
- Penfolds Grange
- Henschke Hill of Grace
- Screaming Eagle
- Harlan Estate
- Gaja
- Antinori
- Barca Velha

Regra de bordas:

- Se um nome contem "Cabernet Sauvignon", "Merlot" ou outra casta, o nome completo do vinho continua preservado; apenas nao traduzir a casta em citacoes avulsas (ver secao 4).
- Titulos honorificos no nome do produtor (ex: `Marques de Riscal`) fazem parte do nome e nao devem ser traduzidos.

---

## 4. Castas e variedades de uva

Regra pragmatica:

- Manter as castas internacionais no nome canonico mais reconhecivel pelo mercado global de vinho.
- NAO traduzir nomes de uvas para equivalentes literais estranhos (ex: "Uvas Cabernet" fica ruim).
- Sinonimos regionais sao aceitos quando ja cristalizados (ex: `Syrah` e `Shiraz`, `Grenache` e `Garnacha`); sempre preservar o que esta escrito no contexto original.

Lista minima coberta (ampliar sob demanda em futuras revisoes):

- Cabernet Sauvignon
- Cabernet Franc
- Merlot
- Pinot Noir
- Pinot Grigio
- Pinot Gris
- Chardonnay
- Sauvignon Blanc
- Syrah
- Shiraz
- Malbec
- Tempranillo
- Sangiovese
- Nebbiolo
- Riesling
- Chenin Blanc
- Grenache
- Garnacha
- Tannat
- Carmenere
- Touriga Nacional
- Touriga Franca
- Tinta Roriz
- Albarino
- Gewurztraminer
- Viognier
- Zinfandel
- Primitivo
- Montepulciano
- Nero d'Avola
- Aglianico
- Mourvedre
- Monastrell

---

## 5. Denominacoes, regioes e classificacoes protegidas

Regra:

- NAO traduzir denominacoes de origem, regioes vinicolas e classificacoes oficiais (AOC, AOP, DOC, DOCG, DO, DOCa, AVA, IGP, IGT, VDP, etc.) quando usadas como nomes proprios.
- Nome geografico em contexto de vinho e parte da denominacao; nao virar "Champanha", "Borgonha" etc. no conteudo de produto.

Lista minima coberta:

Regioes e denominacoes:

- Champagne
- Bordeaux
- Bourgogne
- Burgundy
- Cote du Rhone
- Cotes du Rhone
- Chateauneuf-du-Pape
- Sancerre
- Alsace
- Napa Valley
- Sonoma
- Willamette Valley
- Finger Lakes
- Rioja
- Ribera del Duero
- Priorat
- Rias Baixas
- Chianti Classico
- Barolo
- Barbaresco
- Brunello di Montalcino
- Montepulciano d'Abruzzo
- Amarone della Valpolicella
- Vinho Verde
- Douro
- Porto
- Dao
- Alentejo
- Jerez
- Sherry
- Cava
- Prosecco
- Franciacorta
- Mosel
- Rheingau
- Mendoza
- Uco Valley
- Maipo Valley
- Colchagua
- Stellenbosch

Classificacoes e selos:

- DOC
- DOCG
- DOP
- AOC
- AOP
- AVA
- DO
- DOCa
- IGP
- IGT
- VDP
- VQPRD
- Cru
- Premier Cru
- Grand Cru

---

## 6. Termos tecnicos que podem permanecer no original

Regra:

- Alguns termos enologicos sao jargao internacional ou aparecem literalmente no rotulo. Mantem-se no original, mesmo em conteudo em pt-BR, en-US, es-419 ou fr-FR.
- Se o contexto pedir, usar em italico no frontend (classe CSS, nao traducao).

Lista minima coberta:

- terroir
- cuvee
- grand cru
- premier cru
- reserva
- gran reserva
- crianza
- brut
- extra brut
- brut nature
- demi-sec
- sec
- doux
- vintage
- non-vintage
- millesime
- blanc de blancs
- blanc de noirs
- rose
- frizzante
- spumante
- solera
- en primeur
- negociant

---

## 7. URLs, codigos, IDs e variaveis

Regra:

- NUNCA traduzir URLs, paths, query strings, dominios, IDs, slugs, nomes de cookies, headers HTTP, variaveis de ambiente, placeholders ICU ou nomes de eventos/telemetria.
- Tudo que esta dentro de `{}`, `<>`, backticks ou crases e codigo/valor tecnico: preservar byte a byte.

Exemplos (nao exaustivo):

Dominios e paths:

- `chat.winegod.ai`
- `api.winegod.ai`
- `/c/[id]`
- `/chat/[id]`
- `/legal/:country/:lang/:doc`
- `/api/auth/me`
- `/api/config/enabled-locales`
- `/auth/callback`

Placeholders ICU e variaveis de template:

- `{count}`
- `{name}`
- `{wine_name}`
- `{price}`
- `{currency}`
- `{user.first_name}`
- `{plural, one {# item} other {# items}}`
- `{{greeting}}`

Headers HTTP custom:

- `X-WG-UI-Locale`
- `X-WG-Market-Country`
- `X-WG-Currency`

Env vars e feature flags:

- `ENABLED_LOCALES`
- `TOLGEE_API_KEY`
- `ANTHROPIC_API_KEY`
- `DATABASE_URL`
- `FLASK_ENV`
- `wg_locale_choice`
- `wg_age_verified`
- `enabled_locales`
- `feature_flags`

Codigos de locale e currency:

- `pt-BR`, `en-US`, `es-419`, `fr-FR`
- `BRL`, `USD`, `MXN`, `EUR`

---

## 8. Como usar este arquivo

- Tolgee: pipeline de importacao e revisao deve respeitar DNT. Tradutores no Tolgee veem estes termos como "do not translate" quando a chave for marcada; termos livres dentro do texto devem seguir a regra 1 por inspecao humana.
- Baco (Onda 6): este arquivo e copiado para `backend/prompts/baco/dnt.md` pela fase F6.2. O builder de prompt injeta DNT como regra imutavel para o modelo.
- Revisores Fiverr: este arquivo e parte do brief entregue ao nativo. Serve como checklist para marcar "traducao indevida" quando encontrada.
- Claude/Codex: quando gerar microcopy novo, conferir se algum termo cai em DNT antes de propor traducao.
- Se houver duvida se um termo e nome proprio ou termo comum: PRESERVAR o original e abrir pergunta para revisao humana no proximo ciclo.
- Atualizacao: este arquivo e aditivo. Remover termos exige decisao explicita do founder. Adicionar termos novos e seguro.

---

Fim do documento.
