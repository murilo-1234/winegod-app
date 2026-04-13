# Handoff: Nota WCF v2 / Nota Oficial do WineGod

Data inicial: 2026-04-11
Ultima atualizacao: 2026-04-12

Status: documento de continuidade para retomar a discussão e a implementação sem perder contexto.

Objetivo deste documento:
- registrar o problema de negócio que estamos resolvendo
- consolidar o que já foi investigado e validado
- deixar explícito o que já foi decidido
- separar o que ainda falta decidir ou executar
- permitir que outra aba do Codex ou Claude continue daqui

Fonte principal deste handoff:
- conversa salva em `C:\Users\muril\OneDrive\Documentos\lixo\06042026\cod-11042026.txt`
- continuação da discussão nesta aba em 2026-04-11

Documentos complementares importantes:
- meta-análise consolidada de múltiplas IAs: `C:\winegod-app\reports\2026-04-12_meta_analysis_nota_wcf_v2.md`

Observação importante:
- o arquivo `cod-11042026.txt` começa no meio de uma resposta, já no item `5`
- então este handoff consolida tanto o que foi recuperado daquele arquivo quanto o que foi fechado depois nesta aba

## 1. Problema de negócio

Estamos definindo qual deve ser a nota oficial de qualidade do WineGod e como ela deve ser calculada de forma coerente.

Os problemas que motivaram essa revisão:
- existe confusão entre `nota_wcf`, `nota_estimada` e `vivino_rating`
- o sistema atual nem sempre mostra a nota que queremos mostrar
- a lógica precisa valorizar reviewers experientes sem permitir notas absurdas com amostra muito pequena
- o centro de correção não deve ser uma média global seca como `3,5`
- alguns vinhos têm dados insuficientes e não devem receber uma nota forçada

Em linguagem simples:
- a nota precisa premiar reviewers fortes
- mas também precisa ter freio quando há poucas reviews
- e esse freio deve puxar para uma base contextual, não para uma média mundial genérica

## 1.1. Tese de produto do fundador que precisa orientar esta frente

Este ponto é importante para qualquer IA julgar corretamente as decisões desta frente.

O WineGod não quer apenas repetir o prestígio dos rótulos antigos e famosos.

A tese defendida pelo fundador é:
- vinhos novos e menos famosos podem ser melhores oportunidades do que vinhos antigos e super conhecidos, mesmo quando têm a mesma nota
- vinhos antigos e marcas famosas carregam muito peso histórico, reconhecimento e volume acumulado de avaliações
- vinhos novos enfrentam concorrência maior, mais variedade de países, uvas e estilos, e ainda assim podem chegar em notas altas
- por isso, um vinho novo com nota forte e menos fama pode ser mais impressionante do que um vinho consagrado com massa enorme de avaliações
- isso é central para o objetivo do app: encontrar vinhos excelentes e subvalorizados, não apenas repetir os nomes mais óbvios do mercado

Consequências práticas dessa tese:
- o sistema não deve premiar fama antiga de forma automática
- contagens públicas gigantes de reviews não devem dominar a percepção do usuário
- a nota precisa distinguir credibilidade sem transformar volume histórico em vantagem excessiva
- a comunicação pública do número de reviews deve ter teto
- o teto público aprovado como direção é `500+ avaliações`

Regra interpretativa para qualquer IA que continuar esta frente:
- quando houver empate de nota entre um vinho muito famoso/antigo e um vinho novo/menos conhecido, o sistema deve evitar enviesar a favor do rótulo famoso apenas por volume histórico de reviews
- isso afeta diretamente:
  - o papel do `nota_wcf_sample_size`
  - a forma de falar quantidade de avaliações
  - a decisão de não exibir números públicos enormes como `20 mil avaliações`
  - a necessidade de manter `winegod_score` como camada separada de custo-benefício

## 2. Resumo executivo do estado atual

O entendimento consolidado até agora é:
- a nota principal do WG deve ser a `nota_wcf`
- a base do cálculo deve ser o `WCF antigo`
- `nota_estimada` deve sair da decisão do produto
- `winegod_score` continua existindo, mas é outra métrica
- a `nota_wcf` já vem com os pesos dos reviewers embutidos
- `nota_wcf_sample_size` não recalcula nota; ele só informa quantas reviews válidas entraram na conta
- `nota_wcf_sample_size` deixa de ser trava para existir nota e passa a ser medidor de credibilidade
- a nota final deve existir para todos os vinhos com contexto suficiente, mesmo sem reviews suficientes no Vivino
- a correção para pouca amostra deve usar um centro contextual em cascata
- não devemos usar `tipo global`
- não devemos usar fallback global universal
- se o vinho não tiver contexto suficiente, ele fica sem nota
- o campo `pais` (ISO 2 letras) deve ser usado na cascata; `pais_nome` hoje está muito incompleto
- a cascata aprovada precisa cobrir também `vinicola + tipo` como último degrau útil antes de `sem nota`
- notas puramente de cascata devem existir, mas precisam ser marcadas com credibilidade menor

## 3. O que foi investigado e validado

### 3.1. Validação do WCF antigo

Foi validado que:
- `wcf_calculado` representa o resultado do WCF antigo
- foi feita uma amostra de 2.000 vinhos
- a fórmula antiga foi recalculada e comparada com o valor salvo
- o batimento foi de `98,6%`

Interpretação:
- isso não prova batimento com a nota pública do Vivino
- isso prova que o WCF antigo é uma referência interna consistente e estável

Conclusão:
- o WCF antigo foi tratado como a melhor base para a nova nota do WG

### 3.2. O que o produto mostra hoje

Foi confirmado no código que a camada de display usa:
- `nota_wcf` quando existe `nota_wcf_sample_size` suficiente
- `vivino_rating` quando esse critério não é atendido

Referências:
- `backend/services/display.py`
- `scripts/calc_score.py`

Comportamento relevante em `backend/services/display.py`:
- `sample >= 100` e `vivino > 0` -> `verified / wcf`
- `sample >= 25` e `vivino > 0` -> `estimated / wcf`
- caso contrário, se houver Vivino -> `estimated / vivino`

Evidência no repositório:
- `backend/services/display.py:4`
- `backend/services/display.py:5`
- `backend/services/display.py:57`
- `backend/services/display.py:83`

Conclusão prática:
- hoje o produto não está usando `nota_estimada`
- quando `nota_wcf_sample_size` está vazio, a tela cai para `vivino_rating`

Conclusão de produto para a v2:
- essa trava de `sample >= 25` não deve mais decidir a existência da nota
- ela deve virar regra de credibilidade da nota

### 3.3. `nota_estimada`

Na investigação anterior foi concluído que:
- o produto atual não usa `nota_estimada` como base principal
- a decisão passou a ser ignorar esse campo no produto

Busca local nesta aba:
- `rg -n "nota_estimada" backend frontend scripts`
- sem resultados

Conclusão:
- `nota_estimada` não deve mais entrar na decisão da nota oficial
- mas não deve ser deletada agora porque ainda existe escrita nela fora deste repositório

Risco operacional conhecido:
- `C:\Users\muril\vivino-broker\server.js` ainda escreve em `nota_estimada`

### 3.4. `nota_wcf_sample_size`

Entendimento consolidado:
- `nota_wcf` = nota já calculada
- `nota_wcf_sample_size` = quantidade de reviews válidas usadas nessa conta
- esse campo não guarda pesos
- os pesos dos reviewers entram antes, na geração da `nota_wcf`
- esse campo deve ser usado para classificar confiança interna da nota
- ele não serve para exibir números públicos grandes como `500+ avaliações`, porque o CSV atual do WCF está capado em no máximo `128`

Como preencher:
- a origem já existe em `scripts/wcf_results.csv`
- cabeçalho do CSV:
  - `vinho_id,nota_wcf,total_reviews_wcf`
- portanto:
  - `total_reviews_wcf -> wines.nota_wcf_sample_size`

Referências:
- `scripts/wcf_results.csv:1`
- `database/migrations/005_add_nota_wcf_sample_size.sql:5`
- `database/migrations/005_add_nota_wcf_sample_size.sql:7`

### 3.5. Por que `nota_wcf_sample_size` está vazio hoje

Foi identificado o motivo mais provável:
- `scripts/calc_wcf.py` atualiza `nota_wcf`, `confianca_nota`, `winegod_score_type` e `nota_wcf_sample_size`
- `scripts/calc_wcf_fast.py` atualiza `nota_wcf`, `confianca_nota` e `winegod_score_type`, mas não grava `nota_wcf_sample_size`

Referências:
- `scripts/calc_wcf.py:78`
- `scripts/calc_wcf.py:95`
- `scripts/calc_wcf_fast.py:65`
- `scripts/calc_wcf_fast.py:73`
- `scripts/calc_wcf_fast.py:86`

Conclusão:
- o motivo mais provável para o campo estar vazio é uso do script rápido

### 3.6. Faixas práticas de reviews e comunicação pública

Foi medido o arquivo `scripts/wcf_results.csv`:
- total de linhas: `1.289.183`
- distribuição:
  - `1–9` -> `656.132`
  - `10–19` -> `191.580`
  - `20–24` -> `53.393`
  - `25–49` -> `139.228`
  - `50–99` -> `101.728`
  - `100+` -> `147.122`
- percentis:
  - `p50 = 9`
  - `p75 = 33`
  - `p90 = 100`
  - `max = 128`

Conclusões:
- `nota_wcf_sample_size` deve ser usado para credibilidade técnica da nota
- a fala pública do Baco sobre volume de avaliações deve usar preferencialmente `vivino_reviews`
- o teto público recomendado é `500+ avaliações`

Faixas públicas recomendadas para a conversa:
- `25–49` -> `mais de 20 avaliações`
- `50–99` -> `mais de 50 avaliações`
- `100–199` -> `mais de 100 avaliações`
- `200–499` -> `mais de 200 avaliações`
- `500+` -> `mais de 500 avaliações`

### 3.7. Pesos dos reviewers

A lógica validada para o WCF antigo foi:
- `1–10` avaliações do reviewer -> peso `1x`
- `11–50` -> peso `1,5x`
- `51–200` -> peso `2x`
- `201–500` -> peso `3x`
- `500+` -> peso `4x`

Referência:
- `C:\natura-automation\_pesquisa_P4_nota_ponderada_experts.py`

Evidência:
- `..._pesquisa_P4_nota_ponderada_experts.py:29`
- `..._pesquisa_P4_nota_ponderada_experts.py:35`
- `..._pesquisa_P4_nota_ponderada_experts.py:37`
- `..._pesquisa_P4_nota_ponderada_experts.py:39`
- `..._pesquisa_P4_nota_ponderada_experts.py:41`
- `..._pesquisa_P4_nota_ponderada_experts.py:75`
- `..._pesquisa_P4_nota_ponderada_experts.py:113`

Conclusão:
- sim, a `nota_wcf` já vem com os pesos dos reviewers embutidos
- `nota_wcf_sample_size` não muda esses pesos

### 3.8. Registros sem contexto suficiente e cobertura mínima

Medições confirmadas nesta rodada:
- existem `779.387` vinhos sem nota "real" hoje, isto é:
  - `nota_wcf IS NULL`
  - e `vivino_rating IS NULL ou <= 0`
- entre esses `779.387`:
  - `596.290` têm `tipo`
  - `494.245` têm `vinicola + tipo`
  - `244.259` têm `pais + tipo`
  - `107.712` têm `regiao + tipo`
  - `57.496` têm `sub_regiao + tipo`
  - `200.672` têm `vinicola + pais + tipo`
  - `91.013` têm `vinicola + regiao + tipo`
  - `49.119` têm `vinicola + sub_regiao + tipo`

Também foi confirmado que:
- o campo `pais` existe na tabela `wines` e é muito mais útil do que `pais_nome` neste bloco
- `pais_nome` está praticamente vazio nesse grupo, mas `pais` aparece em `263.954` registros
- em nova medição desta aba, foram encontrados `0` casos com `pais` vazio e `pais_nome` preenchido

Conclusão prática adicional:
- `pais_nome` não ajuda hoje a preencher `pais`
- o fluxo útil é o contrário:
  - usar `pais` como base operacional da cascata
  - se necessário, preencher `pais_nome` a partir de `pais` para exibição ou consistência

Piso seguro atual do bloco sem contexto mínimo:
- `183.097` vinhos sem `tipo`
- `56.781` vinhos com `tipo`, mas sem `vinicola`, sem `sub_regiao`, sem `regiao` e sem `pais`
- total mínimo sem contexto hoje = `239.878`

Leitura prática:
- com a cascata nova e o uso de `pais`, o número de vinhos sem nota não é mais `~180k`
- o piso seguro hoje é `239.878`
- por consequência, o bloco com contexto mínimo para tentativa de nota fica em torno de `539.509`

Perfil observado desse bloco:
- quase todos vêm de lojas
- não vêm do Vivino
- têm mistura de lixo claro e vinho real incompleto

Exemplos de lixo claro vistos na amostra:
- laveta microfibra
- Eau de Cologne
- chilli jam
- BARILLA
- Chocomilk

Exemplos de vinho real vistos na amostra:
- Domaine Mosse Magic of Juju Blanc 2023
- Moscato d’Asti
- Haut Brion 2014
- Lambruscone 2023

Conclusão importante:
- não é seguro apagar esse bloco em massa
- por enquanto, a decisão foi não dar nota para esse grupo e não apagar agora

Observações:
- o número antigo de `176k–183k` vinha de uma leitura anterior e de uma cascata diferente
- o piso seguro atual para `sem nota` é maior porque a regra final ficou mais rígida
- esse total ainda pode cair no futuro com enrichment, normalização e eventual inferência de `pais`

### 3.9. Clamp empírico entre `nota_wcf` e `vivino_rating`

Foi executada uma medição sobre `691.921` vinhos com `nota_wcf` e `vivino_rating`:
- média de `nota_wcf - vivino_rating`: `-0,0505`
- desvio padrão: `0,1529`
- `p25 = -0,13`
- mediana = `-0,04`
- `p75 = 0,04`
- `23.090` casos ficaram acima de `+0,20`
- `81.789` casos ficaram abaixo de `-0,20`

Conclusão:
- o WCF já tende a ficar levemente abaixo do Vivino
- por isso, o clamp recomendado para a v2 deixa mais espaço para baixo do que para cima

Clamp recomendado:
- mínimo = `vivino_rating - 0,30`
- máximo = `vivino_rating + 0,20`

## 4. Modelo conceitual aprovado até aqui

### 4.1. Separação correta entre as duas etapas do cálculo

Este ponto gerou dúvida e foi esclarecido:

Não é correto misturar:
- peso do reviewer
- nota-base contextual

na mesma média simples.

O modelo correto tem 2 etapas:

Etapa 1:
- calcular a `nota_wcf_bruta`
- aqui entram as reviews e os pesos dos reviewers

Etapa 2:
- aplicar o freio para pouca amostra
- aqui a `nota_wcf_bruta` é puxada para a `nota_base` contextual

Resumo:
- o peso `4x` do reviewer entra na etapa 1
- o puxão para o centro entra na etapa 2
- o puxão deve usar o número de reviews válidas, não a soma dos pesos

Por que isso foi escolhido:
- porque 2 reviewers muito fortes devem influenciar mais que 10 reviewers fracos
- mas 2 reviewers fortes não podem, sozinhos, gerar uma nota final absurda

### 4.2. Fórmula alvo da nota final

Regra fechada até agora:

```text
nota_final = (n / (n + 20)) * nota_wcf_bruta
           + (20 / (n + 20)) * nota_base
```

Onde:
- `nota_wcf_bruta` = média ponderada das reviews usando os pesos do WCF antigo
- `nota_base` = nota contextual encontrada pela cascata
- `n` = número de reviews válidas usadas

Decisão já fechada nesta aba:
- a força do puxão será `20`

Interpretação simples:
- com poucas reviews, a `nota_base` ainda segura bastante
- com mais reviews, a `nota_wcf_bruta` domina cada vez mais

Regra adicional para vinhos sem reviews válidas:
- quando `n = 0`, não existe `nota_wcf_bruta`
- nesse caso, a nota vem puramente da cascata contextual
- a nota contextual deve receber um ajuste conservador conforme o degrau da cascata

Penalidade contextual aprovada como referência de implementação:
- `vinicola + sub_regiao + tipo` -> `0,00`
- `sub_regiao + tipo` -> `-0,03`
- `vinicola + regiao + tipo` -> `-0,05`
- `regiao + tipo` -> `-0,08`
- `vinicola + pais + tipo` -> `-0,10`
- `pais + tipo` -> `-0,12`
- `vinicola + tipo` -> `-0,15`

### 4.3. Exclusões na base de reviews

Regra aprovada:
- reviews com `usuario_total_ratings = 0` ou `NULL` ficam fora da ponderação

Motivo:
- a review continua no banco
- mas não entra no cálculo como se viesse de um reviewer minimamente confiável

## 5. Decisões de negócio já fechadas

Esta é a lista que deve ser tratada como decisão atual aprovada.

### 5.1. Nota oficial

- a nota principal do WG passa a ser a `nota_wcf`
- `nota_estimada` sai da decisão do produto
- `winegod_score` continua separado e não é a nota de qualidade
- quando não houver `nota_wcf`, mas houver contexto suficiente, o vinho deve receber uma nota contextual
- quando não houver `nota_wcf` nem contexto suficiente, o vinho fica sem nota

### 5.2. Base do cálculo

- a base da nova nota será o `WCF antigo`
- pesos dos reviewers:
  - `1–10` -> `1x`
  - `11–50` -> `1,5x`
  - `51–200` -> `2x`
  - `201–500` -> `3x`
  - `500+` -> `4x`
- reviews com `usuario_total_ratings = 0` ou `NULL` ficam fora da ponderação

### 5.3. Centro contextual

- vamos manter o puxão para o centro
- esse centro não será média mundial seca
- ele será uma nota-base contextual por cascata
- o campo `pais` da tabela `wines` entra na cascata; `pais_nome` não deve ser usado como base principal nesta etapa

### 5.4. Cascata final aprovada nesta aba

Ordem aprovada:
- mesma `vinícola + sub_regiao + tipo`
- mesma `sub_regiao + tipo`
- mesma `vinícola + regiao + tipo`
- mesma `regiao + tipo`
- mesma `vinícola + pais + tipo`
- mesma `pais + tipo`
- mesma `vinícola + tipo`
- se não encaixar em nada disso: `sem nota`

Regras complementares já aprovadas:
- `vinícola` não entra sozinha sem `tipo`
- sempre deve existir `tipo`
- referência geográfica é preferida, mas a exceção final aprovada é `vinícola + tipo`
- não usar `tipo global`
- não usar fallback global universal
- se o vinho não tiver contexto suficiente, fica sem nota

Suporte mínimo por degrau aprovado:
- `vinícola + sub_regiao + tipo` -> mínimo `2`
- `sub_regiao + tipo` -> mínimo `10`
- `vinícola + regiao + tipo` -> mínimo `3`
- `regiao + tipo` -> mínimo `10`
- `vinícola + pais + tipo` -> mínimo `3`
- `pais + tipo` -> mínimo `10`
- `vinícola + tipo` -> mínimo `5`

Leitura prática dessa decisão:
- degraus com `vinícola` são mais específicos e aceitam suporte menor
- degraus amplos precisam de suporte maior para não virarem contexto genérico demais
- a regra final não usa mais um mínimo uniforme para toda a cascata

### 5.5. Força do puxão

Decisão final nesta aba:
- usar `20`

### 5.6. Registros sem contexto suficiente

- com os dados atuais, pelo menos `239.878` vinhos ficam sem contexto mínimo para nota
- não vamos forçar nota global nesses registros
- não vamos apagar esse bloco agora

### 5.7. Normalização

- vamos normalizar `tipo`

Isso é importante porque já foi observado que o banco separa valores por capitalização e acentuação, por exemplo:
- `tinto` / `Tinto`
- `rose` / `Rosé`

### 5.8. Tipos de nota e credibilidade

Classificação aprovada:
- `verified` = vinho com `nota_wcf` e `nota_wcf_sample_size >= 100`
- `estimated` = vinho com `nota_wcf` e `nota_wcf_sample_size entre 1 e 99`
- `contextual` = vinho sem reviews válidas usadas no WCF; nota veio apenas da cascata
- `sem nota` = vinho sem contexto suficiente

Regra de produto:
- `nota_wcf_sample_size` não deve mais ser usado para bloquear a existência da nota
- ele deve ser usado para classificar a credibilidade da nota

### 5.9. Clamp contra Vivino

Decisão recomendada para a v2:
- usar clamp assimétrico contra `vivino_rating`
- limite inferior: `-0,30`
- limite superior: `+0,20`

### 5.10. Papel do `winegod_score`

Ponto confirmado:
- o `winegod_score` hoje é impactado pela lógica da nota, porque `calc_score.py` usa `compute_nota_base(...)`

Direção aprovada:
- `winegod_score` não deve ser exibido para vinho puramente `contextual`
- `winegod_score` continua válido para notas com base real de WCF

### 5.11. Remoção futura de `nota_estimada`

Direção aprovada:
- o campo deve ser removido do pipeline e, depois, do banco
- isso precisa ser feito em 2 etapas:
  - parar de escrever no campo
  - depois remover a coluna

## 6. O que ainda falta decidir

No plano conceitual principal, quase tudo já foi fechado.

Os pontos abaixo ainda precisam de decisão explícita ou confirmação final:

- decidir se a v2 já vai incluir `uvas` na cascata ou se isso fica para uma fase seguinte
- decidir se haverá enrichment/backfill de `pais_nome` a partir de `pais` antes do rollout
- decidir se haverá inferência de `pais` a partir de `regiao`/`sub_regiao` antes do rollout
- definir como a `nota_base` será agregada dentro de cada balde da cascata:
  - média simples
  - média ponderada
  - média ponderada com teto de contribuição por vinho
- decidir fallback formal para vinhos com `n > 0`, mas sem encaixe em nenhum degrau da cascata
- confirmar se o threshold de `verified` fica em `100+` ou se será rebaixado
- confirmar se o clamp final será fixo ou progressivo por confiança

Observação:
- esses pontos já são bem menores do que as decisões estruturais
- a direção de negócio principal está praticamente fechada

## 7. O que falta executar

Mesmo com a regra quase fechada, ainda faltam tarefas operacionais para transformar isso em comportamento real do produto.

### 7.1. Implementação da WCF v2

Falta implementar:
- cálculo da `nota_wcf_bruta` com a lógica do WCF antigo
- exclusão de reviews com `usuario_total_ratings = 0` ou `NULL`
- cálculo da `nota_base` usando a cascata aprovada
- aplicação da fórmula com puxão `20`

### 7.2. Normalização de `tipo`

Falta definir e implementar:
- mapa de normalização
- tratamento de caixa
- tratamento de acentos
- tratamento de sinônimos e grafias inconsistentes

### 7.3. `nota_wcf_sample_size`

Falta garantir no pipeline:
- gravação de `total_reviews_wcf` em `wines.nota_wcf_sample_size`
- uso desse campo para classificar `verified / estimated / contextual`
- sem usar esse campo como trava para exibir nota

Opções óbvias:
- ajustar `calc_wcf_fast.py`
- ou voltar a usar `calc_wcf.py`

### 7.4. Verificação do comportamento final do produto

Depois da implementação, ainda será preciso validar:
- quando a tela mostra `wcf`
- quando a tela mostra `contextual`
- quando a tela fica sem nota
- impacto em `display.py`
- impacto em `calc_score.py`
- impacto do novo sample size
- impacto do clamp novo `-0,30 / +0,20`

### 7.5. Medição final do bloco sem nota

Falta medir no banco:
- quantos vinhos ficam sem nota depois de usar `pais` e `vinicola + tipo`
- qual parte desse bloco é vinho real incompleto
- qual parte parece lixo de loja

## 8. Riscos e cuidados

### 8.1. Não apagar o bloco de ~240k agora

Motivo:
- ele está misturado
- há lixo claro, mas também há vinho real

Conclusão:
- não apagar em massa
- se houver limpeza futura, ela deve ser feita com triagem separando:
  - não-vinho quase certo
  - vinho real incompleto
  - duvidoso

### 8.2. Não deletar `nota_estimada` agora

Motivo:
- ainda existe escrita nesse campo fora deste repositório

Conclusão:
- remover do processo decisório agora
- deletar o campo apenas depois de mapear e desligar os escritores restantes

### 8.3. Não confundir sample size com peso

Este ponto precisa ficar claro para qualquer continuação:
- `nota_wcf_sample_size` não representa peso dos reviewers
- ele representa quantidade de reviews válidas
- os pesos dos reviewers já estão dentro da `nota_wcf`

### 8.4. Não usar `nota_wcf_sample_size` como número público de avaliações

Este ponto também precisa ficar claro:
- `nota_wcf_sample_size` não é o número público total de reviews do vinho
- hoje ele está limitado pelo processo do WCF e vai só até `128`
- para comunicação pública do tipo `500+ avaliações`, usar `vivino_reviews`

### 8.5. Perguntas da meta-análise já respondidas com dados

Esta subseção existe para evitar retrabalho. Parte das perguntas levantadas pela meta-análise já foi respondida nesta aba com medições reais.

Perguntas já respondidas com base suficiente para orientar decisão:

1. Distribuição de vinhos por degrau da cascata

Leitura correta:
- o bloco estrutural com contexto mínimo continua em torno de `539.509` vinhos
- mas contexto estrutural não é o mesmo que suporte mínimo suficiente no degrau escolhido
- depois de aplicar os mínimos por degrau aprovados, a distribuição observada no bloco sem nota real ficou:
  - `vinícola + sub_regiao + tipo` -> `834`
  - `sub_regiao + tipo` -> `39.662`
  - `vinícola + regiao + tipo` -> `1.936`
  - `regiao + tipo` -> `44.150`
  - `vinícola + pais + tipo` -> `2.144`
  - `pais + tipo` -> `156.476`
  - `vinícola + tipo` -> `8.802`
  - sem bucket utilizável com os mínimos atuais -> `525.383`

Conclusão:
- os degraus amplos concentram a maior parte da cobertura real
- os degraus com `vinícola` continuam úteis, mas cobrem bem menos quando se exige suporte mínimo

2. Desvio-padrão médio por degrau

Resposta disponível nesta rodada:
- ainda não foi medido com `nota_wcf_bruta` recalculada vinho a vinho
- mas já existe um proxy útil com a `nota_wcf` atual armazenada
- média do desvio-padrão por grupo com suporte mínimo:
  - `vinícola + sub_regiao + tipo` -> `0,1225`
  - `sub_regiao + tipo` -> `0,2363`
  - `vinícola + regiao + tipo` -> `0,2676`
  - `regiao + tipo` -> `0,3561`
  - `vinícola + pais + tipo` -> `0,2846`
  - `pais + tipo` -> `0,3897`
  - `vinícola + tipo` -> `0,3148`

Conclusão:
- os grupos mais específicos realmente são mais coesos
- os grupos mais amplos realmente são mais dispersos

3. Correlação entre `vivino_rating` e `nota_wcf`

Resultado medido:
- base comparada: `697.533` vinhos com ambos
- correlação de Pearson = `0,916369`
- delta médio `nota_wcf - vivino_rating` = `-0,050294`
- desvio-padrão do delta = `0,151131`
- mediana do delta = `-0,0400`

Conclusão:
- a relação é forte
- o WCF não é cópia do Vivino, mas também não é independente dele no resultado final observado

4. Quantas reviews são excluídas pela regra `usuario_total_ratings = 0/NULL`

Resultado medido no `vivino_db`:
- reviews brutas com rating > 0: `33.175.419`
- reviews válidas após exclusão: `33.110.922`
- reviews excluídas: `64.497`
- impacto percentual: `0,19%`
- vinhos afetados: `26.994`
- média de reviews excluídas por vinho afetado: `2,39`

Impacto em thresholds:
- cru `>= 10` e válido `< 10` -> `185` vinhos
- cru `>= 25` e válido `< 25` -> `132`
- cru `>= 50` e válido `< 50` -> `85`
- cru `>= 100` e válido `< 100` -> `3.231`

Conclusão:
- o impacto global é pequeno
- mas o impacto em fronteiras de credibilidade não é zero

5. Cobertura do campo `uvas`

Resultado medido:
- no banco `wines` inteiro: `238.992` de `2.506.441` -> `9,54%`
- no bloco sem nota real: `146.512` de `779.387` -> `18,80%`

Conclusão:
- `uva` parece promissora conceitualmente
- mas ainda está pouco preenchida para virar eixo central da cascata nesta fase

6. Variância interna de `vinícola + tipo`

Resultado medido com proxy baseado em `nota_wcf` atual:
- grupos totais: `515.075`
- grupos com `5+` vinhos: `90.329`
- tamanho médio do grupo: `3,35`
- média do desvio-padrão em grupos `5+`: `0,3148`
- mediana do desvio-padrão em grupos `5+`: `0,2839`
- desvio-padrão máximo observado: `2,0000`

Conclusão:
- o risco existe e não é pequeno
- `vinícola + tipo` continua útil só como último degrau, com mínimo próprio e penalidade mais conservadora

7. O `n` capado do CSV distorce fortemente o shrinkage?

Resposta medida:
- no bloco `100+` do CSV, quase todos os vinhos ficam em torno de `100`
- só `4` vinhos apareceram com `valid_reviews` local claramente acima do `csv_n`
- o `avg(valid_reviews - csv_n)` ficou em `-0,07`
- o maior excesso observado foi `17.389`, mas em um conjunto minúsculo

Conclusão:
- existe risco de distorção no topo
- mas ele não parece hoje um problema amplo de massa

Perguntas parcialmente respondidas:

1. O campo `vinícola` tem nomes genéricos ou duplicados que misturam contextos espúrios?
- parcialmente respondido
- já sabemos que existe `produtor_normalizado`, o que reduz parte do ruído
- também já foi medido que `vinícola + tipo` tem variância interna relevante
- o que ainda falta é uma auditoria direta dos nomes genéricos/ambíguos mais frequentes

2. Existem vinhos com `n > 0` que não se encaixam em nenhum degrau da cascata?
- ainda não foi consolidado com uma query dedicada cruzando o CSV completo do WCF com os campos contextuais da tabela `wines`
- portanto, este ponto continua aberto

Perguntas ainda abertas e que exigem rodada específica:

1. Qual `k` minimiza erro preditivo em cross-validation nos vinhos com `n >= 50`?
- ainda não respondido
- nenhuma análise de IA consegue fechar isso sem experimento dedicado

2. Qual é a versão final do cálculo da `nota_base` dentro de cada balde?
- ainda falta explicitar se a base será média simples, média ponderada, ou outra forma de agregação
- esta é uma lacuna importante do desenho atual

### 8.6. Leitura crítica de uma análise externa posterior

Uma análise externa posterior trouxe pontos fortes e também alguns exageros numéricos. Esta subseção registra o julgamento tópico por tópico, para que a próxima aba não trate essa resposta nem como verdade automática nem como algo a ser ignorado.

1. "A correlação 0,916 muda o jogo"

Minha opinião:
- concordo em grande parte
- uma correlação de `0,916` é alta e mostra que `nota_wcf` e `vivino_rating` andam muito juntos na massa
- isso enfraquece a ideia de que a nota, sozinha, já seria uma voz totalmente independente do Vivino
- por outro lado, isso não invalida o WCF
- a parte interessante do produto continua justamente nos desvios e caudas

Onde eu ajusto a conclusão externa:
- dizer que o clamp vira tema "quase acadêmico" é um exagero
- ele realmente atua mais nas caudas, mas as caudas ainda importam para discovery
- a leitura mais forte aqui não é "remover clamp de vez"
- é considerar clamp mais inteligente ou progressivo por confiança

2. "A cascata, com suporte mínimo, quase não funciona"

Minha opinião:
- concordo parcialmente
- a intuição central está correta: os mínimos por degrau reduziram muito a cobertura real
- também está correto que a maior parte da cobertura útil vem dos degraus amplos

Mas a conta citada nessa análise está errada com base nas medições desta aba:
- `525.383` não é `97,4%` de `539.509`
- o número correto é:
  - universo sem nota real medido = `779.387`
  - com bucket utilizável após mínimos = `254.004`
  - sem bucket utilizável após mínimos = `525.383`
- dentro do bloco com contexto estrutural mínimo (`539.509`), isso significa que cerca de `254.004` sobrevivem ao filtro de suporte e cerca de `285.505` não sobrevivem

Conclusão correta:
- a cascata com mínimos não morreu
- mas ela ficou muito mais estreita do que parecia no desenho conceitual
- isso aumenta muito a importância dos degraus amplos
- e mostra que discutir só ordem da cascata era insuficiente sem medir suporte

3. "A ausência de `uva` não é o maior problema da v2"

Minha opinião:
- concordo
- com `9,54%` de cobertura no banco inteiro, `uva` ainda não está madura para virar eixo central da v2
- ela pode voltar em fase seguinte, mas hoje não deve travar a implementação

4. "O impacto da exclusão de reviews é pequeno; isso favorece baixar `verified` de 100 para 50"

Minha opinião:
- concordo com a primeira metade
- discordo da conclusão automática

Parte correta:
- o impacto global da exclusão é pequeno mesmo
- e os thresholds de confiança realmente importam mais do que a exclusão em si

Parte que eu não compraria automaticamente:
- os dados da exclusão não provam, sozinhos, que `verified` deva cair para `50`
- isso é decisão de produto, não consequência matemática direta dessa medição
- baixar de `100` para `50` aumentaria bastante o universo `verified`, então essa mudança precisa ser julgada separadamente

5. "A variância valida a direção das penalidades, mas os valores atuais não seguem os dados"

Minha opinião:
- concordo com a crítica geral
- as penalidades continuam heurísticas
- a variância por degrau reforça que o topo é mais coeso e a base é mais ruidosa

Onde eu discordo da conta feita nessa análise:
- a frase de que as penalidades "subpenalizam" os buckets ruidosos com base na razão `0,03 -> 0,15` não fecha matematicamente do jeito que foi escrita
- se compararmos `0,03` com `0,15`, a razão de penalidade é maior que a razão simples entre alguns desvios-padrão citados
- então a conclusão numérica específica ficou mal formulada

Conclusão mais segura:
- a direção da crítica está certa
- mas a calibração ainda precisa ser feita de forma mais cuidadosa do que essa conta resumida

6. "O cálculo da `nota_base` dentro do balde é a lacuna mais perigosa"

Minha opinião:
- concordo fortemente
- esse é, hoje, um dos pontos mais perigosos do desenho
- se a base for média simples, um vinho extremo com baixa amostra pode contaminar demais o balde

Minha leitura da proposta feita:
- média ponderada por `min(n, 50)` é uma candidata forte
- ela tem uma vantagem importante: valoriza vinhos com mais base real sem deixar rótulos gigantes dominarem tudo
- além disso, conversa bem com a tese do fundador de não transformar fama histórica em peso infinito

Status:
- proposta forte
- ainda não aprovada como regra final

7. "Precisamos de fallback para vinhos com `n > 0` mas sem degrau"

Minha opinião:
- concordo
- se existir vinho com `n > 0` e sem `nota_base`, a fórmula de shrinkage fica sem prior
- nesse cenário, a saída mais limpa é usar `nota_wcf_bruta` diretamente com rótulo de confiança baixa

Status:
- isso ainda depende de medição dedicada
- mas como fallback conceitual, é a melhor proposta que apareceu até aqui

8. Leitura geral dessa análise externa

Minha opinião final sobre ela:
- é uma boa análise
- ela melhorou a conversa em pontos realmente importantes
- ela acertou especialmente ao recolocar o foco em:
  - cobertura real da cascata
  - importância dos degraus amplos
  - papel limitado de `uva` nesta fase
  - urgência de definir como a `nota_base` é agregada

Os exageros ou ajustes necessários foram:
- superestimar o colapso da cascata com uma conta percentual errada
- tirar conclusão muito rápida sobre baixar `verified` para `50`
- formular de forma imprecisa a crítica numérica às penalidades

## 9. Estado atual em uma frase

O plano atual é transformar a `nota_wcf`, calculada com a lógica antiga de pesos, na nota oficial do WG, permitir nota contextual para vinhos sem reviews suficientes mas com contexto mínimo, usar `nota_wcf_sample_size` como credibilidade e não como trava, e deixar sem nota apenas os vinhos realmente sem contexto mínimo.

## 10. Próximo passo recomendado

O próximo passo mais lógico é produzir uma especificação final da `nota_wcf v2` pronta para implementação, contendo:
- fórmula definitiva
- definição formal da cascata
- regra de exclusão de reviews inválidas
- regra de preenchimento de `nota_wcf_sample_size`
- regra de classificação `verified / estimated / contextual`
- regra de ocultação de `winegod_score` para notas contextuais
- casos de teste esperados

## 11. Checklist curto para a próxima aba

Se outra aba for continuar daqui, ela deve assumir como verdade atual:
- `nota_wcf` será a nota principal
- `nota_estimada` está fora da decisão, mas não será deletada agora
- `winegod_score` continua separado, mas hoje depende da lógica da nota
- base matemática = WCF antigo
- pesos = `1x / 1,5x / 2x / 3x / 4x`
- reviews com `0/NULL` ratings do reviewer saem da ponderação
- fórmula de puxão usa `20`
- cascata final aprovada é:
  - `vinícola + sub_regiao + tipo`
  - `sub_regiao + tipo`
  - `vinícola + regiao + tipo`
  - `regiao + tipo`
  - `vinícola + pais + tipo`
  - `pais + tipo`
  - `vinícola + tipo`
  - senão `sem nota`
- mínimos por degrau aprovados:
  - `2 / 10 / 3 / 10 / 3 / 10 / 5`
  - ordem correspondente aos 7 degraus acima
- usar `pais` (ISO 2 letras) na cascata
- não usar `tipo global`
- não usar fallback global universal
- normalizar `tipo`
- preencher `nota_wcf_sample_size`
- `nota_wcf_sample_size` classifica confiança e não bloqueia mais a nota
- tipos de nota:
  - `verified = 100+`
  - `estimated = 1–99`
  - `contextual = 0`
- clamp recomendado = `vivino -0,30 / +0,20`
- não exibir `winegod_score` para nota puramente contextual
- não apagar o bloco de `~240k` agora
