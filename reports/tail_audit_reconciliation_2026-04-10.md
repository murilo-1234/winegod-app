# Reconciliacao Oficial -- vivino_db vs Render (Etapa 1)

Data execucao: 2026-04-10 19:08:17
Executor: `scripts/audit_tail_snapshot.py`
Metodo: cursor server-side (psycopg2 named cursor) com `fetchmany` em batches de 50.000, cruzamento em memoria

## Universos

| Base | Metrica | Total |
|---|---|---|
| Render | wines com vivino_id IS NOT NULL | 1,727,058 |
| vivino_db | vivino_vinhos total | 1,738,585 |

## Resultado da Reconciliacao

| Categoria | Contagem |
|---|---|
| **in_both** (presentes em ambos) | 1,727,058 |
| **only_vivino_db** (presentes no vivino_db, ausentes no Render) | 11,527 |
| **only_render** (vivino_id no Render sem correspondencia no vivino_db) | 0 |

## Drift vs Referencia

| Metrica | Referencia | Live | Delta | Drift % | Status |
|---|---|---|---|---|---|
| in_both | 1,727,058 | 1,727,058 | +0 | 0.00% | OK |
| only_vivino_db | 11,527 | 11,527 | +0 | 0.00% | OK |
| only_render | 0 | 0 | +0 | 0.00% | OK |

## Confirmacao Explicita (only_render)

**only_render = 0.** Nenhum vivino_id existente no Render aponta para um ID inexistente no vivino_db. A camada Vivino do Render e um subconjunto do vivino_db.

## Amostra -- only_vivino_db (10 menores IDs)

Vinhos presentes no vivino_db local e ausentes no Render.

| vivino_id | nome | produtor | rating |
|---|---|---|---|
| 1003 | Cabernet Sauvignon | Brochelle | 4.2 |
| 3806 | Zinfandel | Windsor | 0.0 |
| 3944 | Chardonnay (Signature) | Darioush | 4.2 |
| 3955 | Chardonnay | King Estate | 3.9 |
| 4880 | Pinot Grigio | Bargetto | 3.4 |
| 6039 | Cabernet Sauvignon | Magnotta | 0.0 |
| 6043 | Cabernet Sauvignon | Magnotta | 3.5 |
| 6051 | Shiraz | Magnotta | 0.0 |
| 6054 | Cabernet Sauvignon | Magnotta | 0.0 |
| 6059 | Merlot | Magnotta | 3.2 |

## Conclusao Operacional

1. **Existe universo real de canonicos importaveis**: 11,527 vinhos no vivino_db ausentes do Render. Candidatos para a Etapa 2.
2. **Nao existe sujeira de `vivino_id` no Render sem correspondencia no vivino_db.**
3. **Cobertura Render/vivino_db**: 1,727,058 / 1,738,585 = 99.34%.

