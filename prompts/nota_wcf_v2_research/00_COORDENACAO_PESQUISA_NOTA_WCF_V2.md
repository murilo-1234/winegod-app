# Coordenação de Pesquisa: Nota WCF v2

Objetivo deste pacote:
- dividir as dúvidas restantes da `nota_wcf v2` em frentes paralelas
- dar contexto suficiente para outras abas do Claude Code trabalharem sem retrabalho
- evitar que cada aba reabra decisões já fechadas
- concentrar o esforço em pesquisa, validação e proposta, não em implementação

Status desta coordenação em 2026-04-12:
- `WG SAI NOTA_ESTIMADA` = concluída como pesquisa
- referência final da frente: `C:\winegod-app\reports\2026-04-12_pesquisa_06_remocao_nota_estimada.md`

Arquivos principais de contexto para todas as abas:
- [2026-04-11_handoff_nota_wcf_v2.md](C:/winegod-app/reports/2026-04-11_handoff_nota_wcf_v2.md)
- [2026-04-12_meta_analysis_nota_wcf_v2.md](C:/winegod-app/reports/2026-04-12_meta_analysis_nota_wcf_v2.md)
- [PROMPT_CTO_WINEGOD_V2.md](C:/winegod-app/prompts/PROMPT_CTO_WINEGOD_V2.md)

Regras gerais para todas as abas:
- não implementar nada no produto
- não alterar schema, pipeline ou backend
- não apagar dados
- trabalhar em modo estudo e recomendação
- usar código, banco e CSVs apenas para leitura e validação
- se alguma afirmação não puder ser provada, dizer explicitamente que não foi provada
- separar sempre:
  - dado medido
  - inferência razoável
  - opinião de produto

Formato mínimo esperado de resposta de cada aba:
1. Resumo executivo
2. O que foi medido
3. O que foi encontrado
4. Opções possíveis
5. Riscos de cada opção
6. Recomendação final
7. O que ainda ficou aberto

Decisões já fechadas e que não devem ser reabertas sem evidência muito forte:
- nota oficial = `nota_wcf`
- base matemática = `WCF antigo`
- pesos dos reviewers = `1x / 1,5x / 2x / 3x / 4x`
- excluir reviews com `usuario_total_ratings = 0/NULL`
- `nota_estimada` sai da decisão do produto
- `nota_wcf_sample_size` vira credibilidade, não trava
- `tipo` é obrigatório na cascata
- sem `tipo global`
- sem fallback global universal
- `winegod_score` não aparece para nota puramente contextual
- cascata aprovada:
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
- força de puxão aprovada por enquanto = `20`

Medições já conhecidas e úteis:
- correlação `nota_wcf` vs `vivino_rating` = `0,916369`
- delta médio `nota_wcf - vivino_rating` = `-0,050294`
- cobertura de `uvas`:
  - banco inteiro: `9,54%`
  - bloco sem nota real: `18,80%`
- `pais_nome` não ajuda hoje a preencher `pais`:
  - casos com `pais` vazio e `pais_nome` preenchido = `0`
- thresholds no `wcf_results.csv`:
  - `25+` = `388.078`
  - `50+` = `248.850`
  - `100+` = `147.122`
- vinhos com `n > 0` no CSV WCF = `410.290`
- entre esses, `44.186` não têm encaixe estrutural na cascata atual
- entre esses `44.186`:
  - `43.395` estão sem `tipo`
  - `791` têm `tipo`, mas sem produtor, sub_região, região e país

Quantidade de abas recomendada:
- `6` abas

Distribuição recomendada:
1. `01_ESTUDO_PAIS_VS_PAIS_NOME.md`
2. `02_ESTUDO_NORMALIZACAO_TIPO.md`
3. `03_ESTUDO_CLAMP_E_CONFIANCA.md`
4. `04_ESTUDO_CASCATA_COBERTURA_E_UVAS.md`
5. `05_ESTUDO_NOTA_BASE_PENALIDADE_E_FALLBACK.md`
6. `06_ESTUDO_REMOCAO_NOTA_ESTIMADA.md`

Princípio de coordenação:
- cada aba deve ficar no seu escopo
- se descobrir algo que afeta diretamente outra aba, deve mencionar, mas não assumir o trabalho dela
- o objetivo é trazer material para decisão final do CTO, não “ganhar” a discussão
