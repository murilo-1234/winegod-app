# WINEGOD - Commerce TRIGGER LIST (Fase N)

Data: 2026-04-24  
Escopo: documento operacional unico com todos os "botoes" que o usuario
aperta para ativar cada peca commerce local. Cada TRIGGER e
independente e pode ser executado fora de ordem (exceto os que exigem
pre-requisito explicito).

Regras gerais:

- Cada TRIGGER que faz apply (escreve em Render) exige env autorizadora.
- Sem env, o wrapper aborta limpo (exit 2) com mensagem ABORT.
- Validator FULL roda antes de qualquer apply.
- Ladder padrao: 50 -> 200 -> 1000 (ou 500 em Tier).
- Nada aqui chama Gemini pago ou mexe em `C:\natura-automation\`.

## TRIGGER 1 - Amazon legacy backfill (one-time)

Pre-requisitos:

- `winegod_db` local acessivel (env `WINEGOD_DATABASE_URL`).
- Scraper Amazon legacy ja nao esta rodando (desativado, dados
  historicos).
- Artefato ainda nao existe OU esta obsoleto.

Comandos:

```powershell
# 1. Exporter (piloto 50k)
python scripts\data_ops_producers\export_amazon_legacy.py --max-items 50000

# 2. Validator FULL
python scripts\data_ops_producers\validate_commerce_artifact.py `
  --artifact-dir reports\data_ops_artifacts\amazon_local_legacy_backfill `
  --expected-family amazon_local_legacy_backfill

# 3. Apply gated (one-time)
$env:COMMERCE_APPLY_AUTHORIZED_AMAZON_LEGACY = "1"
powershell -File scripts\data_ops_scheduler\run_commerce_apply_amazon_legacy.ps1
```

Criterios de sucesso:

- validator: `OK mode=full ...`
- apply ladder completa sem BLOCKED_QUEUE_EXPLOSION
- state `reports/data_ops_export_state/amazon_legacy_backfill_done.json`
  criado

## TRIGGER 2 - Amazon mirror diario (recorrente)

Pre-requisitos:

- Scraper Amazon espelho rodando no PC espelho (ativo).
- Dump diario chegando via `backup_diario.bat` em
  `gdrive:winegod-backups/` (04:00) - ou `winegod_db` local up-to-date.

Comandos (diario):

```powershell
# 1. Exporter incremental (usa state file)
python scripts\data_ops_producers\export_amazon_mirror.py --mode incremental --max-items 50000

# 2. Validator FULL
python scripts\data_ops_producers\validate_commerce_artifact.py `
  --artifact-dir reports\data_ops_artifacts\amazon_mirror `
  --expected-family amazon_mirror_primary

# 3. Apply ladder diario
$env:COMMERCE_APPLY_AUTHORIZED_AMAZON_MIRROR = "1"
powershell -File scripts\data_ops_scheduler\run_commerce_apply_amazon_mirror.ps1
```

Criterios de sucesso:

- state `reports/data_ops_export_state/amazon_mirror.json` atualizado
  com `last_captured_at` incrementado
- ladder completa

## TRIGGER 3 - Tier1 global (semanal)

Pre-requisitos:

- Scraper Codex Tier1 (`C:\natura-automation\winegod_admin\scraper_tier1.py`)
  rodou recentemente.
- `lojas_scraping` tem lojas com `metodo_recomendado` em
  {`api_shopify`, `api_woocommerce`, `api_vtex`, `sitemap_html`,
  `sitemap_jsonld`, `sitemap_*`}.

Comandos (semanal):

```powershell
python scripts\data_ops_producers\export_tier1_global.py --max-items 50000

python scripts\data_ops_producers\validate_commerce_artifact.py `
  --artifact-dir reports\data_ops_artifacts\tier1 `
  --expected-family tier1

$env:COMMERCE_APPLY_AUTHORIZED_TIER1 = "1"
powershell -File scripts\data_ops_scheduler\run_commerce_apply_tier1_global.ps1
```

Se scraper nao rodou (sem lojas Tier1 elegiveis):

- exporter retorna `FAIL reason=no_producer_tier1_global` (exit=2),
  **comportamento esperado, nao e erro**. Pular TRIGGER 3 esta semana.

## TRIGGER 4 - Tier2 global (semanal)

Pre-requisitos:

- Scraper Codex Tier2 (`winegod_admin\scraper_tier2.py`) rodou.
- `lojas_scraping` tem lojas `metodo_recomendado='playwright_ia'` fora
  de BR.

Comandos:

```powershell
python scripts\data_ops_producers\export_tier2_global.py --max-items 50000

python scripts\data_ops_producers\validate_commerce_artifact.py `
  --artifact-dir reports\data_ops_artifacts\tier2_global `
  --expected-family tier2

$env:COMMERCE_APPLY_AUTHORIZED_TIER2_GLOBAL = "1"
powershell -File scripts\data_ops_scheduler\run_commerce_apply_tier2_global.ps1
```

Se sem producer: `FAIL reason=no_producer_tier2_global`, pular.

## TRIGGER 5 - Tier2 BR (semanal)

Pre-requisitos:

- Scraper Codex Tier2 BR rodou (ou `vinhos_brasil\main.py`).
- `lojas_scraping` tem lojas BR com `playwright_ia`.

Comandos:

```powershell
python scripts\data_ops_producers\export_tier2_br.py --max-items 10000

python scripts\data_ops_producers\validate_commerce_artifact.py `
  --artifact-dir reports\data_ops_artifacts\tier2\br `
  --expected-family tier2

$env:COMMERCE_APPLY_AUTHORIZED_TIER2_BR = "1"
powershell -File scripts\data_ops_scheduler\run_commerce_apply_tier2_br.ps1
```

## TRIGGER 6 - Commerce health check (recorrente, read-only)

Pre-requisitos: nenhum alem de Python no PATH.

Comandos:

```powershell
# Snapshot humano-leitora
powershell -File scripts\data_ops_scheduler\run_commerce_health_check.ps1 -Md `
  -WriteMd reports\WINEGOD_COMMERCE_HEALTH_LATEST.md

# Ou rapido para Task Scheduler
powershell -File scripts\data_ops_scheduler\run_commerce_health_check.ps1
```

Exit codes:

- 0 = ok (todos observed, disk < 2 GB)
- 2 = warning (artefato ausente em familia esperada, disk 2-5 GB)
- 3 = failed (contrato invalido em producao, disk > 5 GB)

Executar **antes** de qualquer TRIGGER de apply.

## TRIGGER 7 - Retencao + rotacao (periodico)

Pre-requisito: nenhum.

Comandos:

```powershell
# Primeiro, plano (nao apaga nada)
python scripts\data_ops_producers\rotate_commerce_artifacts.py --plan-only

# Se plano OK, aplicar (gated)
$env:COMMERCE_ROTATION_AUTHORIZED = "1"
python scripts\data_ops_producers\rotate_commerce_artifacts.py --apply
```

Comportamento:

- mantem ultimos 10 arquivos OU 30 dias (o que for menor);
- arquivos com >7 dias sao comprimidos (gzip) antes de descartar;
- `.jsonl.quarantined` sao preservados (trilha de incidentes);
- summaries sempre acompanham o JSONL.

## TRIGGER 8 - Adicionar logs+checkpoints ao backup (one-time, fora do repo)

Pre-requisito: acesso ao `backup_diario.bat` (ou equivalente) em
`C:\natura-automation\` ou Task Scheduler.

Procedimento (nao rodado automaticamente; o usuario integra):

1. Abrir `reports\data_ops_backup_patches\add_logs_checkpoints_to_backup.patch`.
2. Copiar o snippet para o arquivo `backup_diario.bat` ativo, entre o
   pg_dump e o rclone final.
3. Rodar manualmente 1x pelo Task Scheduler para validar.
4. Confirmar que `gdrive:winegod-backups/backup_natura_amazon_logs_*.zip`
   apareceu.

Testes de sintaxe do patch (nao aplicam, so validam):

```powershell
python -m pytest scripts\data_ops_producers\tests\test_backup_patch_logs_checkpoints.py -v
```

## Sintese - ordem recomendada pos-lancamento

1. **Hoje** (antes do lancamento): TRIGGER 6 (health) + TRIGGER 8
   (backup patch) em paralelo.
2. **Semana 1** pos-ativacao dos scrapers: TRIGGER 1 (legacy one-time),
   depois TRIGGER 2 diario.
3. **Semana 1+** recorrente: TRIGGER 3/4/5 semanal (Tier1 + Tier2
   global + Tier2 BR), TRIGGER 6 diario, TRIGGER 7 mensal.

## Dependencias externas (bloqueadores conhecidos)

- TRIGGER 3/4/5: dependem dos scrapers Codex voltarem a rodar. Hoje
  (2026-04-24) estao PAUSADOS; exporters retornarao `no_producer_*`
  limpo ate isso acontecer.
- TRIGGER 8: depende do usuario achar o backup_diario.bat real (Task
  Scheduler local).
- Nenhuma outra dependencia externa.
