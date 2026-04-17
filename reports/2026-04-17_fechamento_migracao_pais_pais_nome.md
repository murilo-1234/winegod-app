# Fechamento da Migracao `pais` / `pais_nome`

Data: 2026-04-17
Commit base: c87c8496 (Migrate pais to canonical field, pais_nome to display only)
Escopo: executar rigidamente o plano aprovado de fechamento da trilha.

---

## Estado final

### Banco de dados

| Metrica | Valor antes (c87c8496) | Valor agora | Observacao |
|---|---|---|---|
| `pais IS NOT NULL AND BTRIM(pais) = ''` | 3.713 | 0 | lixo estrutural convertido para NULL |
| `pais IS NOT NULL AND pais_nome vazio/NULL` | 82.111 | 0 | backfill residual concluido (+66.111 nesta sessao, 16.000 no primeiro attempt) |
| `pais_nome vazios totais` | 519.154 | 437.043 | restantes sao vinhos SEM qualquer pais (pais IS NULL, validado) |
| `pais_nome mismatch vs ISO` | 0 | 0 | mantido |
| Trigger monitora | `pais` (ISO) | `pais` (ISO) | migration 014 aplicada |
| Trigger monitora `pais_nome` | Nao | Nao | mantido |

**Interpretacao correta**: `pais_nome` vazio = 0 APENAS para linhas com `pais` ISO valido. Existem 437.043 linhas SEM qualquer pais (pais IS NULL e pais_nome vazio, validado). Isso NAO e uma falha da migracao — sao vinhos que ja foram ingeridos sem nenhuma informacao de pais.

**Validacao final em producao (2026-04-17, pos-fechamento)**:
- `pais_empty_string = 0`
- `valid_iso_sem_pais_nome = 0`
- `sem_nenhum_pais = 437.043` (pais IS NULL + pais_nome vazio)
- `trigger_has_pais_nome = False`
- `trigger_uses_pais_iso = True`

### Codigo

**Correcao de regressao da migracao**
- `backend/services/enrichment_v3.py`: `to_discovery_enriched()` restaurou contrato em INGLES (Spain/France/Italy). A tentativa de migrar esse contrato para PT-BR quebrou `test_to_discovery_enriched_converts_country_code_to_name`. Esse campo alimenta o pipeline de discovery que envia nomes de pais para o Gemini — manter ingles preserva compatibilidade com prompts upstream.

**Politica A (compat documentada)**
- `backend/tools/search.py`, `backend/tools/compare.py`, `backend/tools/stats.py`: fallback para `pais_nome ILIKE` quando `text_to_iso()` nao reconhece o texto livre. Comentario `# Politica A (compat)` inline marca cada ponto.
- Racional: usuarios digitam texto livre em varios idiomas ("frança", "france", "Italia"). A camada canonica tenta ISO primeiro; quando o lookup falha, o fallback em `pais_nome` garante que a busca ainda funcione.

**Contrato share/OG explicito**
- `backend/db/models_share.py`: campo novo `pais_display` exposto pela API (derivado canonicamente de `pais` ISO via `iso_to_name`). `pais_nome` mantido como compat para clientes legados.
- `frontend/app/c/[id]/page.tsx`: consome `pais_display || pais_nome`.
- `frontend/app/c/[id]/opengraph-image.tsx`: consome `pais_display || pais_nome`.

**Scripts auxiliares migrados**
- `scripts/score_report.py`: usa `pais` canonico e traduz via `iso_to_name()` para exibicao.

**Scripts auxiliares nao migrados (legacy, fora do app principal)**
- `scripts/auditoria_4_casos.py`, `scripts/clean_wines.py`, `scripts/study_scores.py`, `scripts/teste_amostra_50.py`: scripts de analise/auditoria standalone que leem `pais_nome` como coluna de conveniencia. Mantidos como estao; nao afetam o runtime do produto.

### Testes

Rodei a suite direcionada em ambiente isolado (worktree limpo em `c87c8496`):

- `test_enrichment_v3.py`, `test_new_wines_pipeline.py`, `test_resolver_pdf.py`, `test_text_pipeline.py`, `test_chat_pdf_video.py`, `test_item_status.py` → **110 passed, 0 failed**.
- `test_discovery_pipeline.py` → 5 falhas. **Essas falhas sao PRE-EXISTENTES** no commit pre-migracao `813ce70b`. Causa: `ENRICHMENT_MODE=gemini_hybrid_v3` e default mas os mocks dos testes ainda visam o path legacy `qwen_text_generate`. Fora do escopo desta trilha.

Compile check (`python -m py_compile`): todos os arquivos da trilha compilam.

---

## Criterios de aceite

| Criterio | Status |
|---|---|
| `pais = ''` → 0 | OK |
| `valid_iso_sem_pais_nome = 0` | OK |
| `pais_nome_mismatch_vs_iso = 0` | OK |
| Trigger ativa usando `pais` | OK |
| Regressao de discovery corrigida | OK |
| Validacao em worktree limpo | OK (110/110 na suite da trilha) |
| Relatorio com numeros reais | OK (este documento) |

---

## Correcao de honestidade vs relatorio anterior

O resumo anterior dizia "pais_nome vazios: 0" para o banco inteiro. Isso era falso:
- **Verdade**: 0 quando o registro tem `pais` ISO valido.
- **Realidade**: ainda existem ~437k registros **sem pais nenhum** (pais IS NULL), herdados da ingestao. Esses registros nao tem origem de pais conhecida — nao e tarefa de backfill, e sim de enrichment futuro.

O relatorio anterior tambem agrupava 62 ISOs diferentes sob "0 linhas" quando na verdade havia 82.111 linhas residuais (com pais valido mas pais_nome ainda NULL) que foram ignoradas pelo backfill original — provavelmente por usar `WHERE pais_nome = ''` (string vazia) sem cobrir `pais_nome IS NULL`. Corrigido agora.

---

## O que NAO esta no escopo deste fechamento

- Corrigir os 5 testes pre-existentes em `test_discovery_pipeline.py` (causados por v3 default sem mocks — tarefa separada).
- Preencher pais para os ~437k vinhos sem origem (tarefa de enrichment, nao de migracao de schema).
- Drop da coluna `pais_nome` (prematura — requer confirmar que nenhum writer externo ainda escreve nela).
