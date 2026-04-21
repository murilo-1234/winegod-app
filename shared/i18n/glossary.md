# WineGod.ai - I18N Glossary

Glossário base de 30 termos de vinho nos 4 idiomas do Tier 1 (pt-BR, en-US, es-419, fr-FR).

- Serve como referência para UI, Baco, Tolgee e revisão humana.
- DNT (termos que não devem ser traduzidos) fica em `shared/i18n/dnt.md`. Em caso de conflito com este arquivo, DNT vence.
- Este é um draft inicial. Revisão nativa via Fiverr acontece em F12.4. Até lá, use como baseline para tradução interna.
- Posicionamento do produto: WineGod deve parecer US-facing / global-first. en-US é a referência de polimento internacional; pt-BR permanece como fonte atual do produto; es-419 deve ser neutro para América Latina (sem regionalismo forte de MX/AR/Espanha); fr-FR usa vocabulário vinícola natural da França.

---

## 1. Uso

- Tradutores e revisores devem consultar este glossário para manter consistência entre telas, mensagens do Baco e conteúdo legal.
- Conflito entre este arquivo e `dnt.md`: DNT vence. Se um termo aparece como DNT no `dnt.md`, este glossário apenas documenta o equivalente cultural sem autorizar a troca.
- Termos técnicos e internacionais (terroir, brut, bouquet) são marcados `(DNT)` na coluna Notes; devem ser preservados no original em todos os idiomas, mesmo quando a frase ao redor é traduzida.
- Se tradutor ou revisor discordar de uma escolha aqui, registrar sugestão no processo de review (Fiverr/Tolgee). NÃO alterar silenciosamente as traduções no código ou em `messages/*.json`.
- `reserve` é caso sensível: o termo "reserva" tem significado legal/comercial diferente entre países (ex: Rioja Reserva tem regras DOC específicas, enquanto "reserva" em outros contextos é apenas nome comercial). Usar com consciência; quando possível manter no original.

---

## 2. Glossary Table

| Key | pt-BR | en-US | es-419 | fr-FR | Notes |
|---|---|---|---|---|---|
| wine | vinho | wine | vino | vin | Core UI term. |
| red_wine | vinho tinto | red wine | vino tinto | vin rouge | Core UI term. |
| white_wine | vinho branco | white wine | vino blanco | vin blanc | Core UI term. |
| rose_wine | vinho rosé | rosé wine | vino rosado | vin rosé | Em en-US, "rosé" (com acento) é a forma padrão em contexto de vinho; "rose" sozinho é ambíguo. |
| sparkling_wine | espumante | sparkling wine | vino espumoso | vin effervescent | Em fr-FR também aparece "mousseux"; manter "effervescent" como padrão neutro. |
| dessert_wine | vinho de sobremesa | dessert wine | vino de postre | vin de dessert | Core UI term. |
| vintage | safra | vintage | cosecha | millésime | (DNT) quando usado como adjetivo no rótulo (ex: "vintage 2018"). Traduzir apenas quando o texto da UI pedir a palavra local para "ano da colheita". |
| grape_variety | casta | grape variety | variedad de uva | cépage | "casta" é o termo consagrado em pt-BR; en-US usa "grape variety" (não "grape"); fr-FR usa "cépage". |
| blend | corte | blend | mezcla | assemblage | "corte" em pt-BR é consagrado; "assemblage" em fr-FR é o termo nativo; "blend" pode aparecer em contexto internacional mesmo em fr-FR. |
| producer | produtor | producer | productor | producteur | Core UI term. |
| winery | vinícola | winery | bodega | domaine | "domaine" é natural em fr-FR para produtor/propriedade; "bodega" em es-419 cobre tanto vinícola quanto loja, usar conforme contexto. |
| region | região | region | región | région | Core UI term. Acentos UTF-8 preservados em pt-BR, es-419 e fr-FR. |
| appellation | denominação de origem | appellation | denominación de origen | appellation | (DNT) quando parte do nome oficial (ex: Appellation d'Origine Contrôlée, Denominación de Origen Calificada). |
| terroir | terroir | terroir | terroir | terroir | (DNT) Termo enológico internacional. NÃO traduzir. |
| body | corpo | body | cuerpo | corps | Core UI term. |
| acidity | acidez | acidity | acidez | acidité | Core UI term. |
| tannin | tanino | tannin | tanino | tanin | Core UI term. |
| aroma | aroma | aroma | aroma | arôme | Core UI term. |
| bouquet | bouquet | bouquet | bouquet | bouquet | (DNT) Termo técnico internacional usado em degustação. Manter em todos os idiomas. |
| finish | final | finish | final en boca | finale | Em es-419, a expressão completa "final en boca" é mais clara que "final" sozinho. |
| oak | carvalho | oak | roble | chêne | Core UI term. |
| barrel | barrica | barrel | barrica | fût | "barrique" também é comum em fr-FR; "fût" é mais genérico. |
| aging | envelhecimento | aging | crianza | élevage | "crianza" em es-419 é padrão; "élevage" em fr-FR é o termo técnico. Atenção: em Rioja, "Crianza" também é categoria DOC; evitar confusão. |
| pairing | harmonização | pairing | maridaje | accord mets-vins | "accord mets-vins" é a expressão francesa consagrada; não traduzir para "pairing" em fr-FR. |
| serving_temperature | temperatura de serviço | serving temperature | temperatura de servicio | température de service | Core UI term. |
| sweetness | doçura | sweetness | dulzor | sucrosité | Em fr-FR, "sucrosité" é técnico; contextos mais casuais podem usar "douceur". Padrão aqui é técnico. |
| dry | seco | dry | seco | sec | Core UI term. Oposto direto de "sweet". |
| brut | brut | brut | brut | brut | (DNT) Classificação oficial de espumante (brut, extra brut, brut nature). NÃO traduzir. |
| reserve | reserva | reserve | reserva | réserve | Sensível: em Rioja, Ribera del Duero, Douro e outras regiões "Reserva" tem regras DOC específicas. Quando aparecer como parte do nome oficial do vinho, tratar como DNT. Quando for nome comercial genérico, traduzir normalmente. |
| organic_wine | vinho orgânico | organic wine | vino orgánico | vin biologique | "vin biologique" (ou "vin bio") é o termo legal/consagrado em fr-FR. |

---

## 3. Review Notes

- Este arquivo é um DRAFT INICIAL. Não tratar como final.
- Revisão nativa (Fiverr) acontece em F12.4, após as ondas 4-8 terem consumido o glossário. Orçamento previsto: 3 idiomas x ~USD 45.
- Mudanças futuras devem ser feitas via PR revisável. Não sobrescrever traduções em massa sem registrar no log de execução `reports/i18n_execution_log.md`.
- DNT vence este arquivo em caso de conflito. Se um termo vira DNT no `dnt.md`, atualizar a coluna Notes aqui marcando `(DNT)` e manter o valor original preservado em todos os idiomas.
- Feedback dos revisores Fiverr deve retornar como anotações neste arquivo ou em arquivo irmão de revisão, nunca como overwrite silencioso.
- Termos com marcação `(DNT)` neste draft: `vintage` (em contexto de rótulo), `appellation` (em nome oficial), `terroir`, `bouquet`, `brut`, e `reserve` (apenas quando for categoria oficial DOC / denominação). Total: 6 termos com cláusula DNT parcial ou total.

Fim do glossário.
