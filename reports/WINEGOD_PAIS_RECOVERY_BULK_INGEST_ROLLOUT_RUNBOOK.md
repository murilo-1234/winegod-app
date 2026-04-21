# WINEGOD_PAIS_RECOVERY — Runbook de Rollout do bulk_ingest

Data: 2026-04-21
Escopo: preparar validacao operacional do endpoint `POST /api/ingest/bulk`
e do servico `services/bulk_ingest.py` antes de liberar ingestao real.

Nada aqui executa apply em volume. Todo passo e dry-run ou smoke isolado.

---

## 0. Estado de pronto

- 16/16 testes passando com DB (`REQUIRE_DB_TESTS=1 python -m tests.test_bulk_ingest`).
  Breakdown: 10 offline (validacao/filtro/hash) + 6 DB (dedup, dry-run,
  apply, regressao de duplicata, total_fontes).
- Bug critico de duplicata por tripla/hash diferente corrigido.
- `total_fontes = 0` em novos INSERTs (bulk_ingest nao cria `wine_sources`).
- Endpoint exige header `X-Ingest-Token`; sem token = 401.
- CLI wrapper (`scripts/ingest_via_bulk.py`) e dry-run por default
  (precisa `--apply` explicito).
- `score_recalc_queue` em 0.
- `trg_score_recalc` ativo.

---

## 1. Pre-requisitos no Render

1. **Setar `BULK_INGEST_TOKEN`** (web service). Token forte, pelo menos 32 bytes
   hex aleatorios. Sem token setado o endpoint responde 401 para todo POST.
2. Confirmar `DATABASE_URL` aponta pra `winegod` em `dpg-*.oregon-postgres.render.com`.
3. Confirmar deploy manual — `git push` NAO dispara deploy (REGRA 7).
   Depois do merge, acionar **Manual Deploy** no dashboard do web service.
4. Opcional: setar `BULK_INGEST_BATCH_SIZE` (default 10.000) e
   `BULK_INGEST_MAX_ITEMS` (default 50.000) se quiser ajustar limites.

---

## 2. Smoke local (antes de ir pra producao)

A suite separa testes offline (10) de testes DB (6). Se o banco nao
estiver acessivel, os testes DB aparecem como **SKIP** e o exit code
continua 0 — bom pra dev local sem rede. Para rollout de producao use
`REQUIRE_DB_TESTS=1`, que **aborta** com exit code 1 se nao conseguir
conectar.

```bash
# 2.1 Modo default (offline basta; DB indisponivel -> SKIP claro)
cd backend && python -m tests.test_bulk_ingest
# com DB:       esperado "16 passed, 0 skipped, 0 failed"
# sem DB:       esperado "10 passed, 6 skipped, 0 failed"

# 2.2 Modo strict (OBRIGATORIO antes de liberar rollout)
#   bash:
REQUIRE_DB_TESTS=1 python -m tests.test_bulk_ingest
#   PowerShell:
$env:REQUIRE_DB_TESTS='1'; python -m tests.test_bulk_ingest
# esperado: "16 passed, 0 skipped, 0 failed (strict mode)"
# se DB cair: "ABORTADO: modo strict exige DB" + exit code 1

# 2.2 Subir Flask local
cd backend && BULK_INGEST_TOKEN=dev-smoke-$(date +%s) python app.py
```

Em outro terminal (ajuste BULK_INGEST_TOKEN pro mesmo valor):

```bash
# 401 sem token
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  http://localhost:5000/api/ingest/bulk \
  -H "Content-Type: application/json" \
  -d '{"items":[]}'
# esperado: 401

# 400 payload invalido
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  http://localhost:5000/api/ingest/bulk \
  -H "Content-Type: application/json" \
  -H "X-Ingest-Token: $BULK_INGEST_TOKEN" \
  -d '{"items":"nao e lista"}'
# esperado: 400

# 200 dry-run com item valido
curl -s -X POST http://localhost:5000/api/ingest/bulk \
  -H "Content-Type: application/json" \
  -H "X-Ingest-Token: $BULK_INGEST_TOKEN" \
  -d '{"items":[{"nome":"Chateau Runbook Grand Cru","produtor":"Chateau Runbook","safra":"2020","pais":"fr"}],"dry_run":true,"source":"runbook_smoke"}'
# esperado: 200 + received:1 valid:1 would_insert:1
```

Alternativa automatica: `python scripts/smoke_bulk_ingest_endpoint.py`.

---

## 3. Smoke producao (Render)

Rodar de maquina autorizada, **sem** logar o token:

```bash
# em shell com BULK_INGEST_TOKEN exportado (nao hardcodar no runbook)
BASE="https://<seu-service>.onrender.com"

# 3.1 sem token
curl -s -o /dev/null -w "%{http_code}\n" -X POST "$BASE/api/ingest/bulk" \
  -H "Content-Type: application/json" -d '{"items":[]}'
# esperado: 401

# 3.2 payload invalido
curl -s -o /dev/null -w "%{http_code}\n" -X POST "$BASE/api/ingest/bulk" \
  -H "Content-Type: application/json" \
  -H "X-Ingest-Token: $BULK_INGEST_TOKEN" \
  -d '{"items":"x"}'
# esperado: 400

# 3.3 dry-run com 1 item benigno
curl -s -X POST "$BASE/api/ingest/bulk" \
  -H "Content-Type: application/json" \
  -H "X-Ingest-Token: $BULK_INGEST_TOKEN" \
  -d '{"items":[{"nome":"Chateau Production Smoke","produtor":"Chateau Production Smoke","safra":"2020","pais":"fr"}],"dry_run":true,"source":"prod_smoke"}'
# esperado: 200 com received=1 valid=1
```

Criterio de verde: 401 + 400 + 200 nos 3 smokes. Qualquer desvio, **abortar**.

---

## 4. Piloto real (dry-run)

Objetivo: mandar 100-500 items reais de um scraping existente pelo pipeline
em modo dry-run e avaliar.

```bash
# CSV/JSONL do scraping, coluna obrigatoria: nome
# opcionais: produtor, safra, tipo, pais (ISO), regiao, uvas, teor_alcoolico, ...
python scripts/ingest_via_bulk.py \
  --input /caminho/para/piloto_500.jsonl \
  --source scraping_piloto_$(date +%Y%m%d)
# dry-run por default, nao precisa de token pq roda local
```

Metricas a validar no output:
- `received` == tamanho do arquivo.
- `valid` >= 80% (senao, payload tem muito lixo — revisar fonte).
- `filtered_notwine` tem amostra dos rejeitados com razao.
- `rejected` tem amostra das rejeicoes nao-notwine (nome_ausente, curto, etc).
- `would_insert` + `would_update` == `valid`.
- `duplicates_in_input`: quanto vem repetido dentro do proprio arquivo.

### Criterios para BLOQUEAR apply

- `valid / received < 0.80` — fonte suja, revisar extracao primeiro.
- `would_insert > 1000` num unico piloto — volume grande demais pra apply
  pequeno, quebrar em lotes menores.
- `errors` nao vazio.
- Se inspecao aleatoria das amostras `rejected` mostrar rejeicao errada
  (vinhos validos sendo barrados), corrigir filtro antes.

### Criterios para LIBERAR apply pequeno

- Smoke local e prod verdes.
- Piloto dry-run com `valid / received >= 0.80`.
- `errors` vazio.
- Amostra manual de 10 `would_insert` valida que sao wines legitimos.
- Amostra manual de 10 `would_update` valida que os matches fazem
  sentido (tripla produtor/nome/safra compativel).

---

## 5. Apply pequeno

Maximo **100-500 items** no primeiro apply real. Nao pular pra milhares.

```bash
python scripts/ingest_via_bulk.py \
  --input /caminho/para/piloto_100_validado.jsonl \
  --source scraping_piloto_$(date +%Y%m%d) \
  --apply
```

Checklist pos-apply:

1. **score_recalc_queue**
   ```sql
   SELECT COUNT(*) FROM score_recalc_queue;
   ```
   Tolerancia: pode subir igual ao numero de inserted+updated (o trigger
   enfileira). Checar que nao explodiu alem disso.

2. **Duplicata por tripla**
   ```sql
   SELECT produtor_normalizado, nome_normalizado, safra, COUNT(*) AS n
   FROM wines
   WHERE suppressed_at IS NULL
     AND atualizado_em > NOW() - INTERVAL '1 hour'
   GROUP BY 1,2,3
   HAVING COUNT(*) > 1
   LIMIT 50;
   ```
   Esperado: 0 resultados (o bug esta corrigido). Qualquer hit = regressao,
   parar e investigar.

3. **total_fontes = 0 nos novos**
   ```sql
   SELECT id, nome, total_fontes, fontes
   FROM wines
   WHERE fontes @> '["bulk_ingest:scraping_piloto_..."]'::jsonb
     AND descoberto_em > NOW() - INTERVAL '1 hour'
   LIMIT 20;
   ```
   Esperado: `total_fontes = 0` para todos os novos; `fontes` contem
   exatamente `["bulk_ingest:<source>"]`.

4. **Contagem agregada**
   ```sql
   SELECT COUNT(*) FROM wines WHERE fontes @> '["bulk_ingest:scraping_piloto_..."]'::jsonb;
   ```
   Deve bater com `inserted + updated` retornados pelo CLI.

Se algum item falhar: **parar**, nao rodar apply maior ate diagnostico.

---

## 6. Rollback operacional

### 6.1 Desativar endpoint sem redeploy

Tirar ou zerar `BULK_INGEST_TOKEN` no Render:
- Zerar → endpoint volta a responder 401 em todas as chamadas.
- Effect imediato (endpoint le Config a cada request).

### 6.2 Reverter codigo

Arquivos a remover (novos):
- `backend/services/bulk_ingest.py`
- `backend/routes/ingest.py`
- `backend/tests/test_bulk_ingest.py`
- `scripts/ingest_via_bulk.py`
- `scripts/smoke_bulk_ingest_endpoint.py`

Arquivos a reverter:
- `backend/app.py` (tirar `from routes.ingest import ingest_bp` e o
  `register_blueprint(ingest_bp, url_prefix='/api')`).
- `backend/config.py` (tirar as 3 envs `BULK_INGEST_*`).

Nenhuma migration SQL foi executada por este pipeline — nao ha rollback
de schema.

### 6.3 Reverter dados inseridos por um piloto

```sql
-- substituir <source> pelo identificador usado
BEGIN;
DELETE FROM wines
WHERE fontes @> '["bulk_ingest:<source>"]'::jsonb
  AND descoberto_em > NOW() - INTERVAL '2 hours'
  AND total_fontes = 0;  -- seguranca extra: so registros sem fonte comercial
-- SELECT COUNT(*) FROM wines WHERE ... -- checar antes do COMMIT
COMMIT;
```

Se algum wine ja ganhou `wine_sources` entre o apply e o rollback,
**nao deletar** — so limpar o provenance textual:

```sql
UPDATE wines
SET fontes = fontes - 'bulk_ingest:<source>'
WHERE fontes @> '["bulk_ingest:<source>"]'::jsonb;
```

---

## 7. Riscos remanescentes

1. **Concorrencia sem indice unico na tripla.** Duas ingestoes
   simultaneas da mesma tripla com hashes diferentes podem criar 2 rows
   antes do UPDATE resolver. Mitigacao atual: apply pequeno sequencial.
   Fix definitivo: `CREATE UNIQUE INDEX ON wines (produtor_normalizado,
   nome_normalizado, COALESCE(safra, ''))` — mudanca de schema, fora
   desta rodada.

2. **`fontes` JSONB pode crescer.** A cada source distinta, entry novo.
   Em producao com 10+ sources por wine, lista pode crescer. Nao e
   bloqueante, mas vale revisitar se passar de ~50 elementos por wine.

3. **bulk_ingest nao cria `wine_sources`.** Por design. Quando o
   pipeline comercial for integrado, o contador `total_fontes` sera
   atualizado por aquele lado — nao por aqui.

4. **Parser descricao continua bloqueado por gate humano.** Dry-run
   entregue em `WINEGOD_PAIS_RECOVERY_PARSER_DRYRUN.md`; UPDATE real
   sobre 139k wines NAO foi aprovado. Recomendacao concreta: so
   preencher `teor_alcoolico` onde NULL (53k wines, risco baixo).

5. **Race entre dry-run e apply.** O estado do banco muda entre os
   dois; `would_update` pode divergir de `updated` se outro processo
   tocar a tripla nesse intervalo. Piloto pequeno sequencial mitiga.

---

## 8. Referencias

- Pipeline: `backend/services/bulk_ingest.py`
- Endpoint: `backend/routes/ingest.py`
- CLI wrapper: `scripts/ingest_via_bulk.py`
- Smoke: `scripts/smoke_bulk_ingest_endpoint.py`
- Testes: `backend/tests/test_bulk_ingest.py`
- Handoff: `reports/WINEGOD_PAIS_RECOVERY_HANDOFF_OFICIAL.md`
- Parser (bloqueado): `reports/WINEGOD_PAIS_RECOVERY_PARSER_DRYRUN.md`
