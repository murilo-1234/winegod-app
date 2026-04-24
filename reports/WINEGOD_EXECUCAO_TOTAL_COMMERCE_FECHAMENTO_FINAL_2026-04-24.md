# WINEGOD - Execucao Total Commerce Fechamento Final

Data: 2026-04-24  
Executor: Claude Code (Opus 4.7 1M context)  
Prompt fonte: `prompts/PROMPT_CLAUDE_EXECUCAO_TOTAL_COMMERCE_FECHAMENTO_FINAL_2026-04-24.md`  
Branch: `data-ops/execucao-total-commerce-fechamento-final-20260424`  
Base: `ab39d816` (HEAD origin/data-ops/correcao-minima-commerce-readme-validator-20260424)  
Auditor final: **Claude admin/auditor mestre**

## 1. Resumo executivo

Pronto 100% localmente:
- inventario arquitetural dos 5 scrapers em `C:\natura-automation\` + 101
  tabelas `vinhos_<pais>` + `lojas_scraping` no `winegod_db`;
- 5 exporters canonicos + CLIs + testes (amazon_legacy, amazon_mirror,
  tier1_global, tier2_global, tier2_br);
- observabilidade commerce com health check (exit 0/2/3) + snapshot
  markdown;
- manifests coverage test + retention + disk monitor + integration
  tests end-to-end;
- 5 apply wrappers PS1 gated por env var + testes de pre-flight;
- runbook operacional expandido com rollback, thresholds, incident
  response e dependencias externas;
- TRIGGER_LIST operacional com 8 triggers;
- git cleanup diagnostico (nao-destrutivo);
- patch backup logs+checkpoints pronto para o usuario copiar em
  `backup_diario.bat`.

Bloqueado por dependencia externa (usuario ativa):
- scrapers Codex Tier1 / Tier2 / Tier2 BR: exporters retornam
  `no_producer_<familia>` ate scraper voltar;
- Amazon mirror primary (`amazon_mirror_primary`): exporter lendo
  `winegod_db` funciona; validator reprova ate JSONL + summary existir;
  - precheck usuario: rodar `export_amazon_mirror.py --mode full` apos
    scraper espelho atualizar `winegod_db`;
- backup patch logs+checkpoints: usuario localiza `backup_diario.bat`
  no Task Scheduler e cola o snippet entregue.

Nenhum apply produtivo rodou nesta rodada. Nenhuma escrita em
`C:\natura-automation\`. Zero chamada paga.

## 2. Arquivos criados/modificados

### 2.1 Criados (novos modulos / scripts / docs)

**Exporters**:
- `sdk/plugs/commerce_dq_v3/artifact_exporters/__init__.py`
- `sdk/plugs/commerce_dq_v3/artifact_exporters/base.py`
- `sdk/plugs/commerce_dq_v3/artifact_exporters/_db.py`
- `sdk/plugs/commerce_dq_v3/artifact_exporters/amazon_legacy.py`
- `sdk/plugs/commerce_dq_v3/artifact_exporters/amazon_mirror.py`
- `sdk/plugs/commerce_dq_v3/artifact_exporters/tier1_global.py`
- `sdk/plugs/commerce_dq_v3/artifact_exporters/tier2_global.py`
- `sdk/plugs/commerce_dq_v3/artifact_exporters/tier2_br.py`

**CLIs producers**:
- `scripts/data_ops_producers/export_amazon_legacy.py`
- `scripts/data_ops_producers/export_amazon_mirror.py`
- `scripts/data_ops_producers/export_tier1_global.py`
- `scripts/data_ops_producers/export_tier2_global.py`
- `scripts/data_ops_producers/export_tier2_br.py`
- `scripts/data_ops_producers/rotate_commerce_artifacts.py`

**Observabilidade + retencao**:
- `sdk/plugs/commerce_dq_v3/health.py`
- `sdk/plugs/commerce_dq_v3/retention.py`
- `sdk/plugs/commerce_dq_v3/disk_monitor.py`

**Fixtures + testes**:
- `sdk/plugs/commerce_dq_v3/tests/fixtures/__init__.py`
- `sdk/plugs/commerce_dq_v3/tests/fixtures/commerce_rows.py`
- `sdk/plugs/commerce_dq_v3/tests/test_exporter_amazon_legacy.py` (9 testes)
- `sdk/plugs/commerce_dq_v3/tests/test_exporter_amazon_mirror.py` (10 testes)
- `sdk/plugs/commerce_dq_v3/tests/test_exporter_tier1_global.py` (9 testes)
- `sdk/plugs/commerce_dq_v3/tests/test_exporter_tier2_global.py` (9 testes)
- `sdk/plugs/commerce_dq_v3/tests/test_exporter_tier2_br.py` (9 testes)
- `sdk/plugs/commerce_dq_v3/tests/test_health.py` (8 testes)
- `sdk/plugs/commerce_dq_v3/tests/test_manifests_coverage.py` (8 testes)
- `sdk/plugs/commerce_dq_v3/tests/test_retention_disk.py` (10 testes)
- `sdk/plugs/commerce_dq_v3/tests/test_integration_end_to_end.py` (11 testes)
- `scripts/data_ops_producers/tests/test_commerce_apply_wrappers.py` (16 testes)
- `scripts/data_ops_producers/tests/test_backup_patch_logs_checkpoints.py` (8 testes)

**Apply wrappers PS1**:
- `scripts/data_ops_scheduler/run_commerce_apply_amazon_mirror.ps1`
- `scripts/data_ops_scheduler/run_commerce_apply_amazon_legacy.ps1`
- `scripts/data_ops_scheduler/run_commerce_apply_tier1_global.ps1`
- `scripts/data_ops_scheduler/run_commerce_apply_tier2_global.ps1`
- `scripts/data_ops_scheduler/run_commerce_apply_tier2_br.ps1`
- `scripts/data_ops_scheduler/run_commerce_health_check.ps1`

**Docs + relatorios**:
- `reports/WINEGOD_COMMERCE_SCRAPER_INVENTORY_2026-04-24.md` (Fase A)
- `reports/WINEGOD_COMMERCE_GIT_CLEANUP_2026-04-24.md` (Fase L)
- `reports/WINEGOD_COMMERCE_TRIGGER_LIST_2026-04-24.md` (Fase N)
- `reports/WINEGOD_COMMERCE_HEALTH_LATEST.md` (Fase G)
- `reports/data_ops_backup_patches/add_logs_checkpoints_to_backup.patch` (Fase M)
- `reports/WINEGOD_EXECUCAO_TOTAL_COMMERCE_FECHAMENTO_FINAL_2026-04-24.md` (ESTE)
- `CLAUDE_RESPOSTAS_EXECUCAO_TOTAL_COMMERCE_FECHAMENTO_FINAL_2026-04-24.md`

### 2.2 Modificados

- `sdk/plugs/commerce_dq_v3/artifact_contract.py` - adiciona
  `validate_artifact_dir_full()` + `_load_jsonl_full()` com checagem
  tipada de `items_emitted` (rejeita string/float/bool, detecta mismatch).
- `scripts/data_ops_producers/validate_commerce_artifact.py` -
  CLI default passa a ser FULL SCAN; `--window N` opcional para smoke.
- `scripts/data_ops_scheduler/run_all_plug_dryruns.ps1` - lista
  canonica pos-2026-04-24 (remove `amazon_mirror` stub + `tier2_chat1..5`
  deprecated; adiciona `amazon_local_legacy_backfill`,
  `amazon_mirror_primary`, `tier2_global_artifact`,
  `winegod_admin_legacy_mixed`).
- `docs/RUNBOOK_COMMERCE_OPERACAO_RECORRENTE.md` - expansao (Fase H):
  exporters, fluxos por familia, rollback, thresholds, incident
  response, dependencias externas, retencao, health.

## 3. Mapeamento arquitetural

Ver `reports/WINEGOD_COMMERCE_SCRAPER_INVENTORY_2026-04-24.md` (Fase A).

Resumo:
- 5 scrapers identificados em `C:\natura-automation\` com paths + estado
  + tabelas alvo.
- 101 tabelas `vinhos_<pais>` (49 ISO-2 + fontes) com ~4.98M vinhos e
  ~5.81M fontes em `winegod_db` local.
- `lojas_scraping` com 86.089 lojas (18k Tier2 playwright_ia + 19k Tier1
  APIs/sitemap + 44k url_morta + resto).
- 64.8k linhas `amazon%` nas tabelas de fontes (top: JP 24.5k, BR 15.7k,
  DE 7k, NL 4.3k, US 3.7k).
- Fluxo: scraper -> `winegod_db` local -> dump gdrive -> exporters deste
  repo -> JSONL canonico -> plug `commerce_dq_v3` -> Render (`wines` +
  `wine_sources`).

## 4. 5 exporters - status

| Exporter | Funcional se... | Stub se... | Modulo | CLI |
|---|---|---|---|---|
| `amazon_legacy` | `WINEGOD_DATABASE_URL` ok + vinhos_* tem fonte in {amazon, amazon_scraper, amazon_scrapingdog} | DSN ausente -> `dsn_missing` | `amazon_legacy.py` | `export_amazon_legacy.py` |
| `amazon_mirror` | DSN ok + fonte `amazon_playwright` presente | DSN ausente, ou zero rows com captured_at > state | `amazon_mirror.py` | `export_amazon_mirror.py` (modo full/incremental) |
| `tier1_global` | DSN ok + lojas_scraping com methods Tier1 | zero lojas Tier1 -> `no_producer_tier1_global` | `tier1_global.py` | `export_tier1_global.py` |
| `tier2_global` | DSN ok + lojas_scraping com playwright_ia non-BR | zero Tier2 non-BR -> `no_producer_tier2_global` | `tier2_global.py` | `export_tier2_global.py` |
| `tier2_br` | DSN ok + lojas_scraping com playwright_ia e pais=BR | zero Tier2 BR -> `no_producer_tier2_br` | `tier2_br.py` | `export_tier2_br.py` |

Todos aplicam:
- 13 campos obrigatorios do contrato (validate_artifact_dir_full OK).
- Dedup por `url_original`.
- Respeito a REGRA 5 (batch de 10.000 linhas).
- Connection read-only (`SET TRANSACTION READ ONLY` + statement_timeout).
- Estado (amazon_mirror): `reports/data_ops_export_state/amazon_mirror.json`
  com `last_captured_at` para modo incremental.

## 5. Observabilidade instalada

- `sdk/plugs/commerce_dq_v3/health.py`:
  - checa 5 familias (amazon_mirror, amazon_legacy, tier1, tier2_global,
    tier2_br) + disco + state files;
  - `ok / warning / failed` com exit 0/2/3;
  - `--stdout md` + `--write-md <path>` para snapshot.
- `sdk/plugs/commerce_dq_v3/disk_monitor.py`: classify (ok <2 GB,
  warning 2-5 GB, failed >5 GB).
- `sdk/plugs/commerce_dq_v3/retention.py`: build_plan + apply_plan
  (preserva `.jsonl.quarantined`, comprime >7d, deleta >30d ou
  >max_files).
- Snapshot atual: `reports/WINEGOD_COMMERCE_HEALTH_LATEST.md`
  (`overall=warning` porque amazon_mirror sem JSONL, esperado ate PC
  espelho entregar).

## 6. Runbook expandido

`docs/RUNBOOK_COMMERCE_OPERACAO_RECORRENTE.md` (secoes 11-18 novas):

- secao 11: exporters mapa (modulo / CLI / output);
- secao 12: fluxos por familia com apply em escada;
- secao 13: rollback + quarantena + reverse no Render;
- secao 14: thresholds de alerta;
- secao 15: incident response (validator FAIL em producao semanal);
- secao 16: dependencias externas (DSN, PC espelho, rclone);
- secao 17: retencao + rotacao;
- secao 18: health recorrente.

## 7. 5 apply wrappers gated

Cada wrapper:

1. Exige env `COMMERCE_APPLY_AUTHORIZED_<FAMILIA>=1`. Sem env -> ABORT
   exit 2.
2. Roda validator FULL antes. Fail -> abort.
3. `-DryRunOnly` para pular apply apos validator OK.
4. Ladder default configuravel (50/200/1000 ou 500).
5. Detecta `BLOCKED_QUEUE_EXPLOSION` entre degraus e aborta exit 3.
6. `amazon_legacy` tambem checa state `amazon_legacy_backfill_done.json`
   (one-time).

16 testes cobrindo: env ausente aborta, validator chamado, env correta,
ladders ascending, BLOCKED_QUEUE_EXPLOSION detection, flag
`amazon_legacy_backfill_done.json` para one-time.

## 8. Retencao + rotacao + disk monitor

- CLI `rotate_commerce_artifacts.py` default `--plan-only`.
- `--apply` exige env `COMMERCE_ROTATION_AUTHORIZED=1`.
- Plan atual (smoke): 3 keep (todos artefatos < 7 dias).
- Disk atual: 372 KB (`ok`).
- 10 testes cobrindo plan/apply/classify/preservacao de quarantined.

## 9. Integration tests end-to-end

`sdk/plugs/commerce_dq_v3/tests/test_integration_end_to_end.py` (11
testes):

- pipeline exporter -> JSONL -> validator FULL por familia;
- summary.items_emitted bate com linhas reais;
- dedup preserva contrato;
- max_items respeitado;
- artifact_sha256 consistente;
- 5 familias coexistem sem cross-contamination.

## 10. Backup patch (nao aplicado)

`reports/data_ops_backup_patches/add_logs_checkpoints_to_backup.patch`:

- snippet em BAT + PowerShell para:
  - zipar `_amazon_*.log` em `backup_natura_amazon_logs_YYYYMMDD.zip`;
  - zipar `_ct_scraper_*.json` em `backup_natura_ct_checkpoints_YYYYMMDD.zip`;
  - zipar `_ct_*.progress.json` em `backup_natura_ct_progress_YYYYMMDD.zip`;
  - upload via rclone para `gdrive:winegod-backups/`.
- NAO aplicado automaticamente. Usuario deve:
  1. localizar `backup_diario.bat` real (nao encontrado por varredura);
  2. colar o snippet entre pg_dump e rclone final;
  3. rodar 1x manual.
- 8 testes estaticos confirmam patch correto.

## 11. TRIGGER_LIST operacional

`reports/WINEGOD_COMMERCE_TRIGGER_LIST_2026-04-24.md` (8 triggers):

1. Amazon legacy backfill (one-time)
2. Amazon mirror diario (recorrente)
3. Tier1 global (semanal, bloqueado por scraper Codex)
4. Tier2 global (semanal, bloqueado por scraper Codex)
5. Tier2 BR (semanal, bloqueado por scraper)
6. Commerce health check (read-only)
7. Retencao + rotacao (periodico)
8. Adicionar logs+checkpoints ao backup (one-time, fora do repo)

## 12. Git cleanup diagnostico

`reports/WINEGOD_COMMERCE_GIT_CLEANUP_2026-04-24.md`:

- Branches commerce consolidadas (5, das quais 1 aberta).
- Branches contaminadas por commits commerce acidentais (3 locais).
- Branches `gone` seguras para deletar local (2).
- Comandos sugeridos (opt-in). Nenhum delete remoto executado.

## 13. Cobertura de testes

| Suite | Testes novos | Total |
|---|---:|---:|
| commerce exporters (5 arquivos) | 46 | 46 |
| commerce health | 8 | 8 |
| commerce manifests coverage | 8 | 8 |
| commerce retention + disk | 10 | 10 |
| commerce integration e2e | 11 | 11 |
| producers apply wrappers | 16 | 16 |
| producers backup patch | 8 | 8 |
| **Total novos** | **107** | **107** |

Suite completa commerce + producers: **144 passed** (107 novos + 37
pre-existentes).

Suite global: **263 testes** nos modulos commerce/producers/adapters/sdk
(144 + 43 + 76), 0 falhas, 0 regressao.

## 14. Outputs dos dry-runs (evidencia)

### 14.1 Validator FULL (4 artefatos)

- `tier1` -> OK mode=full items_validados=346 sha256=e71322a4fb38
- `tier2_global` -> OK mode=full items_validados=176 sha256=493541ade1e4
- `tier2/br` -> OK mode=full items_validados=200 sha256=e1795383591e
- `amazon_mirror` -> FAIL mode=full reason=nenhum_artefato_jsonl_em=...
  (exit=2, esperado)

### 14.2 Scheduler `run_commerce_artifact_dryruns.ps1`

4 dry-runs, 3 observed + 1 blocked_external_host (amazon_mirror).

### 14.3 Scheduler `run_all_plug_dryruns.ps1`

9 commerce + 5 reviews + 1 discovery + 1 enrichment. Commerce:

| Fonte | state |
|---|---|
| winegod_admin_world | observed |
| vinhos_brasil_legacy | observed |
| amazon_local | observed |
| amazon_local_legacy_backfill | observed |
| amazon_mirror_primary | blocked_external_host |
| tier1_global | observed |
| tier2_global_artifact | observed |
| tier2_br | observed |
| winegod_admin_legacy_mixed | blocked_missing_source |

7 observed + 2 blocked honestos.

### 14.4 Health check

`overall=warning disk=ok bytes=372,318`
- amazon_mirror_primary: warning (artefato ausente, esperado)
- amazon_local_legacy_backfill: ok (accept_empty one-time)
- tier1: ok (346 items)
- tier2_global_artifact: ok (176 items)
- tier2_br: ok (200 items)

### 14.5 Rotation plan

`plan actions total=3` - 3 `keep` (todos < 7 dias). Zero compress/delete.

### 14.6 Apply wrapper sem env

`ABORT: COMMERCE_APPLY_AUTHORIZED_AMAZON_MIRROR != 1` (exit=2). Confirmado.

## 15. Env vars criadas (lista)

| Variavel | Onde usada | Default | Funcao |
|---|---|---|---|
| `WINEGOD_DATABASE_URL` | `_db.py` | - | DSN `winegod_db` local (leitura) |
| `COMMERCE_APPLY_AUTHORIZED_AMAZON_MIRROR` | `run_commerce_apply_amazon_mirror.ps1` | - | libera apply mirror |
| `COMMERCE_APPLY_AUTHORIZED_AMAZON_LEGACY` | `run_commerce_apply_amazon_legacy.ps1` | - | libera apply legacy (one-time) |
| `COMMERCE_APPLY_AUTHORIZED_TIER1` | `run_commerce_apply_tier1_global.ps1` | - | libera apply tier1 |
| `COMMERCE_APPLY_AUTHORIZED_TIER2_GLOBAL` | `run_commerce_apply_tier2_global.ps1` | - | libera apply tier2 global |
| `COMMERCE_APPLY_AUTHORIZED_TIER2_BR` | `run_commerce_apply_tier2_br.ps1` | - | libera apply tier2 br |
| `COMMERCE_ROTATION_AUTHORIZED` | `rotate_commerce_artifacts.py` | - | libera `--apply` da rotacao |

Nenhuma env default-on. Todas exigem opt-in explicito.

## 16. Confirmacoes

- **Zero apply produtivo executado** nesta rodada. Nenhum runner com
  `--apply` rodado; nenhum `COMMERCE_APPLY_AUTHORIZED_*` setado.
- **Zero chamada paga** a Gemini/Claude/DeepSeek cobrando.
- **Zero write em `C:\natura-automation\`**. Apenas leitura.
- **Zero write em `winegod_db`**. `connect_readonly()` com
  `SET TRANSACTION READ ONLY`.
- **Zero `git reset --hard`**, `git push --force`, merge em `main`,
  deploy Render/Vercel, mudanca em `.env`.
- **Canal unico preservado**: tudo via
  `plug_commerce_dq_v3 -> DQ V3 -> wines + wine_sources`. Nenhum
  writer paralelo.

## 17. Branch / commit / push

- Branch: `data-ops/execucao-total-commerce-fechamento-final-20260424`
- Base: `ab39d816 docs(data-ops): pin 7d617434 SHA in minimal corrective commerce docs`
- Commits: ver secao final apos push. Commits granulares por fase
  (Fases A, B-F, G, H, I, J, K, L, M, N, P).

## 18. Proximos passos bloqueados por dependencia externa

1. **Scraper Amazon espelho entregar JSONL**: enquanto o scraper nao
   atualiza `winegod_db` via dump, o exporter `amazon_mirror` roda com
   zero linhas novas no modo incremental. Solucao: usuario roda
   TRIGGER 2 apos o scraper ter rodado ou opta por `--mode full`
   (piloto).
2. **Scraper Codex Tier1 rodar**: exporter retorna
   `no_producer_tier1_global` ate haver lojas com metodos Tier1
   cadastradas. Desbloqueio: ativar Codex dashboard + rodar pipeline
   Tier1.
3. **Scraper Codex Tier2 rodar**: idem, para `playwright_ia`.
4. **Scraper Tier2 BR rodar**: idem, no `vinhos_brasil\main.py` ou
   pipeline winegod_admin Tier2 filtrando pais=BR.
5. **Backup logs+checkpoints**: usuario localiza `backup_diario.bat`
   e aplica o snippet manualmente.
6. **PC espelho operacional**: sem mudanca nesta rodada.

## Apendice - Arquivos a repassar para o Claude admin

```text
C:\winegod-app\reports\WINEGOD_EXECUCAO_TOTAL_COMMERCE_FECHAMENTO_FINAL_2026-04-24.md
C:\winegod-app\CLAUDE_RESPOSTAS_EXECUCAO_TOTAL_COMMERCE_FECHAMENTO_FINAL_2026-04-24.md
```

Docs de apoio:

```text
C:\winegod-app\reports\WINEGOD_COMMERCE_SCRAPER_INVENTORY_2026-04-24.md (Fase A)
C:\winegod-app\reports\WINEGOD_COMMERCE_TRIGGER_LIST_2026-04-24.md (Fase N)
C:\winegod-app\reports\WINEGOD_COMMERCE_HEALTH_LATEST.md (Fase G)
C:\winegod-app\reports\WINEGOD_COMMERCE_GIT_CLEANUP_2026-04-24.md (Fase L)
C:\winegod-app\reports\data_ops_backup_patches\add_logs_checkpoints_to_backup.patch (Fase M)
C:\winegod-app\docs\RUNBOOK_COMMERCE_OPERACAO_RECORRENTE.md (Fase H expandida)
```
