# RELATORIO — Match Results Final (30/03/2026)

## NUMEROS GERAIS

| Metrica | Valor |
|---|---|
| Total processados | 3,962,334 |
| Destino A (match Vivino) | 2,350,407 (59.3%) |
| Destino B (vinho novo) | 256,440 (6.5%) |
| Destino C2 (incerto) | 452,690 (11.4%) |
| Destino D (nao-vinho) | 856,559 (21.6%) |
| Destino E (destilado) | 46,238 (1.2%) |

## VINHOS UNICOS (DEDUPLICADOS POR VIVINO ID)

| Metrica | Valor |
|---|---|
| Vivino IDs unicos que matcharam | **381,134** |
| Vinhos novos sem Vivino (B) | **256,440** |
| Total vinhos unicos | **637,574** |
| Media de lojas por vinho Vivino | 6.2 |

## DISTRIBUICAO DE LOJAS POR VINHO

| Lojas | Vinhos | Observacao |
|---|---|---|
| 1 loja | 143,785 | Normal |
| 2 lojas | 66,330 | Normal |
| 3 lojas | 38,025 | Normal |
| 4-10 lojas | 87,482 | Normal |
| 11-50 lojas | 40,437 | Aceitavel |
| 51-100 lojas | ~3,000 | Suspeito |
| 100+ lojas | ~2,000 | Quase certamente errado |
| 1000+ lojas | ~15 | Definitivamente errado |

## PROBLEMAS ENCONTRADOS

### 1. Top 15 vinhos com mais lojas — maioria ERRADA

```
2528 lojas | "spumante dolce" — ERRADO. Nome generico, nao e 1 vinho
2048 lojas | "chateau latour a pomerol" — SUSPEITO. Vinho caro com 2048 lojas?
1934 lojas | "chateau margaux" — ERRADO. Nao existem 1934 lojas vendendo Margaux
1583 lojas | "moet chandon imperial brut" — POSSIVEL. E um dos mais vendidos do mundo
1361 lojas | "negociant chateauneuf du pape" — ERRADO. "Negociant" e generico
1352 lojas | "santangelo dabruzzo cerasuolo" — SUSPEITO
1350 lojas | "chateau pauillac" — ERRADO. "Pauillac" e uma regiao, nao 1 vinho
1293 lojas | "espumante brut" — ERRADO. Generico total
1292 lojas | "tinto colheita reserva do pai" — SUSPEITO
1285 lojas | "chateau clos saint-emilion" — SUSPEITO
1276 lojas | "chateau de meursault charmes" — SUSPEITO
1254 lojas | "marlborough vines sauvignon blanc" — SUSPEITO
1233 lojas | "chateau mouton rothschild → monton grignan" — ERRADO. Match absurdo
1228 lojas | "opus one" — SUSPEITO. Vinho de $400, 1228 lojas?
1086 lojas | "popup sparkling" — ERRADO. Generico
```

Causa: nomes genericos de loja (ex: "espumante brut", "tinto reserva") matcharam com 1 unico Vivino ID e acumularam milhares de registros de lojas diferentes. Sao falsos positivos em massa.

### 2. Precisao estimada do Destino A

Baseado em testes anteriores (200 vinhos manuais + 2000 por letra):

| Faixa de score | Precisao estimada |
|---|---|
| >= 0.80 | ~85-90% |
| 0.70-0.79 | ~55-65% |
| 0.60-0.69 | ~35-45% |
| 0.50-0.59 | ~20-30% |
| 0.40-0.49 | ~10-15% |

O Destino A aceita scores a partir de ~0.45 (com produtor) e ~0.70 (sem produtor). Isso significa que uma parte significativa dos 2.35M matches tem precisao baixa.

### 3. Matches errados por produtor similar

Problema recorrente: sistema acha palavra em comum e matcha vinhos de produtores DIFERENTES.

```
"j alberto 2020" (Argentina) → "alberto quacquarini serrapetrona" (Italia)
  Causa: "alberto" em comum

"chateau mouton rothschild" → "monton grignan-les-adhemar"
  Causa: "mouton/monton" similar

"d angels classique red" → "angels gate red angel"
  Causa: "angels" em comum
```

### 4. Nomes genericos acumulando matches

Vinhos com nome generico na loja (ex: "tinto reserva", "espumante brut", "cabernet sauvignon") matcham com 1 Vivino ID e acumulam centenas/milhares de registros. Esses NAO sao matches reais — sao coincidencias.

## RECOMENDACOES PARA O PROXIMO CTO

### ANTES de subir pro Render:

**1. Limpar matches com >100 lojas**
Vinhos com 100+ lojas sao quase todos falsos positivos (nomes genericos). Mover pra quarentena.
```sql
-- Quantos vinhos tem >100 lojas
SELECT COUNT(*) FROM (
    SELECT vivino_id, COUNT(*) as lojas
    FROM match_results_final WHERE destino = 'A'
    GROUP BY vivino_id HAVING COUNT(*) > 100
) sub;
```

**2. Validar amostra de 500 matches do Destino A**
Pegar 100 de cada faixa de score (0.45-0.55, 0.55-0.65, 0.65-0.75, 0.75-0.85, 0.85+) e verificar manualmente se o match esta correto. Isso da a precisao REAL por faixa.

**3. Subir apenas matches com score >= 0.70 no primeiro momento**
Baseado nos testes anteriores, score >= 0.70 tem ~60-65% de precisao. Abaixo disso cai rapido. Isso significaria subir ~150-200K vinhos unicos com confianca razoavel em vez de 381K com muitos erros.

**4. Tratar vinhos com 1000+ lojas como ERRADO**
Mover pra destino D ou C2. Nenhum vinho real e vendido em 2528 lojas.

**5. Tratar nomes genericos**
Registros como "espumante brut", "tinto reserva", "cabernet sauvignon" sem produtor especifico nao deveriam matchear com nenhum Vivino. Sao descricoes genericas, nao vinhos especificos.

### O QUE SUBIR PRO RENDER (Chat Z):

```
FASE 1 (segura):
  - Matches com score >= 0.70 E lojas <= 100
  - Estimativa: ~150-200K vinhos unicos
  - Cada um vira wine_sources no Render

FASE 2 (depois de validar):
  - Matches com score 0.50-0.70 que passarem validacao
  - Vinhos novos (Destino B) com wine_likeness >= 4

NUNCA SUBIR:
  - Matches com score < 0.50
  - Vinhos com 100+ lojas (falsos positivos)
  - Destino D (nao-vinho)
  - Destino E (destilados, a menos que decidam incluir)
```

## TABELAS DISPONIVEIS NO BANCO LOCAL

| Tabela | Registros | Descricao |
|---|---|---|
| `vinhos_{pais}` (50 tabelas) | ~4,170,000 | Dados originais do scraping |
| `wines_clean` | 3,955,624 | Fase W — limpos |
| `wines_unique` | 2,942,304 | Fase X — deduplicados |
| `match_results_final` | 3,962,334 | Match com Vivino (5 destinos) |
| `vinhos_recuperados` | 6,710 | Vinhos removidos na fase W que parecem reais |
| `vivino_match` | 1,727,058 | Copia local do Vivino |

## ARQUIVOS DE REFERENCIA

| Arquivo | Conteudo |
|---|---|
| `C:\winegod-app\prompts\PROMPT_CTO_WINEGOD_V2.md` | Documento principal do projeto |
| `C:\winegod-app\prompts\ANALISE_CTO_2000_VINHOS.md` | Analise dos 2000 vinhos por letra |
| `C:\winegod-app\prompts\BRIEFING_CTO_Y_METRICAS_2000.md` | Metricas pedidas pro teste |
| `C:\winegod-app\scripts\lista_200_vinhos.txt` | 200 vinhos verificados manualmente |
| `C:\winegod-app\scripts\analise_letra_*.txt` | 8 arquivos com 250 vinhos cada |
| `C:\winegod-app\scripts\vinhos_removidos_possiveis.json` | 24.9K vinhos removidos na fase W que podem ser reais |
| `C:\winegod-app\scripts\match_vivino.py` | Script de match (8 grupos paralelos) |
