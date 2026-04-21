# WINEGOD_PAIS_RECOVERY — Parser Descricao (DRY-RUN)

Data: 2026-04-21 02:02:13
Wines processados: **157,183**
Com pelo menos 1 campo extraido: **150,937** (96.03%)

## Cobertura por campo

| Campo | Extraidos | % |
|---|---:|---:|
| abv | 139,221 | 88.57% |
| classificacao | 104,296 | 66.35% |
| corpo | 148,358 | 94.39% |
| docura | 149,416 | 95.06% |
| harmonizacao | 147,336 | 93.74% |
| envelhecimento | 147,389 | 93.77% |
| temperatura | 146,919 | 93.47% |

## ABV: parsed vs coluna `teor_alcoolico`

| Categoria | Count |
|---|---:|
| match (<= 0.2 diff) | 28,011 |
| mismatch | 57,969 |
| so extraido (coluna null) | 53,241 |
| so coluna (extraido null) | 10,682 |
| ambos null | 7,280 |

## Harmonizacao divergente da coluna existente: 87,027

## Top 15 valores extraidos

### Corpo
- `medio`: 78,740 (padrao)
- `encorpado`: 35,037 (padrao)
- `leve`: 32,077 (padrao)
- `doce`: 486
- `carne vermelha`: 231
- `frutos do mar, peixe`: 125
- `aperitivo`: 112
- `frutos do mar`: 78
- `carne vermelha, caca`: 58
- `carne vermelha, caça`: 57
- `aperitivo, frutos do mar`: 54
- `peixe, frutos do mar`: 54
- `brut`: 47
- `carne vermelha, massas`: 42
- `???`: 38

### Docura
- `seco`: 123,074 (padrao)
- `doce`: 9,245 (padrao)
- `brut`: 9,000
- `750ml`: 1,813
- `demi-sec`: 1,493
- `extra brut`: 657
- `brut nature`: 471
- `suave`: 289 (padrao)
- `bruto`: 279
- `nature`: 240
- `meio seco`: 178 (padrao)
- `frizzante`: 125
- `meio-seco`: 108 (padrao)
- `extra dry`: 101
- `feinherb`: 101

### Classificacao (top 15 distintas)
- `DOC`: 6,050
- `IGT`: 5,606
- `IGP`: 5,587
- `AOC`: 3,663
- `Grand Cru`: 1,645
- `AVA`: 1,483
- `IGP Pays d'Oc`: 1,344
- `Reserva`: 1,285
- `DOCG`: 1,173
- `DO`: 1,090
- `IGT Toscana`: 1,075
- `1er Cru`: 1,021
- `IGP Mendoza`: 934
- `medio`: 837
- `DAC`: 824

## Decisao pendente (gate humano)

- Aprovar UPDATE real em `wines` (colunas novas ou existentes)?
- Criar colunas: `abv` (ou reutilizar `teor_alcoolico`), `classificacao`, `corpo`, `docura`, `envelhecimento`, `temperatura_servico`?
- Estrategia de apply: desativar `trg_score_recalc`, UPDATE em chunks de 2.000, reativar — mesma receita do pais_recovery.

CSV de amostras: `C:\winegod-app\reports\WINEGOD_PAIS_RECOVERY_PARSER_DRYRUN_samples.csv`