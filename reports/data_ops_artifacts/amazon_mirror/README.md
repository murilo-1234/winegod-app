# Amazon Mirror Primary - ponto de entrega de artefato

Este diretorio e o ponto de entrega do feed oficial da Amazon (fonte
`amazon_mirror_primary`). O operador do PC espelho deposita aqui:

- `<YYYYMMDD_HHMMSS>_<run_id>.jsonl`
- `<YYYYMMDD_HHMMSS>_<run_id>_summary.json`

Assim que os dois arquivos aparecem, o scheduler local
`scripts/data_ops_scheduler/run_commerce_artifact_dryruns.ps1` passa a
consumir automaticamente o mais recente em dry-run. Sem os dois arquivos,
a fonte continua em `blocked_external_host` honesto.

## Contrato obrigatorio

Fonte de verdade: `docs/TIER_COMMERCE_CONTRACT.md`.

### JSONL - campos por item

Obrigatorios (nao vazios; `safra` e `preco` podem ser `null`):

```
pipeline_family   -> "amazon_mirror_primary"
run_id            -> identificador unico da execucao
country           -> ISO-2 lowercase (ex: "us", "br")
store_name        -> nome da loja (ex: "Amazon US")
store_domain      -> dominio sem protocolo (ex: "amazon.com")
url_original      -> URL completa do produto
nome              -> nome do vinho
produtor          -> vinicola/produtor
safra             -> ano (pode ser null)
preco             -> numero (pode ser null)
moeda             -> ISO-4217 (ex: "USD")
captured_at       -> ISO-8601 UTC
source_pointer    -> pointer auditavel (id + path)
```

Opcionais aceitos: `asin`, `ean_gtin`, `tipo`, `regiao`, `sub_regiao`,
`uvas`, `imagem_url`, `url_imagem`, `harmonizacao`, `descricao`,
`disponivel`.

### Summary - `<prefix>_summary.json`

Mesmo prefix do JSONL, com `_summary.json`. Campos obrigatorios:

```json
{
  "run_id": "amazon_mirror_primary_20260424_120000",
  "pipeline_family": "amazon_mirror_primary",
  "started_at": "2026-04-24T12:00:00Z",
  "finished_at": "2026-04-24T12:05:00Z",
  "host": "pc_espelho",
  "input_scope": "US,BR",
  "items_emitted": 1234,
  "artifact_sha256": "<sha256 do JSONL>"
}
```

`artifact_sha256` TEM de bater com o hash SHA-256 do JSONL real, senao o
contrato e rejeitado.

## Checklist antes de entregar

1. JSONL validado linha a linha (sem linha invalida, sem campo obrigatorio
   vazio).
2. Summary com os 8 campos obrigatorios.
3. `summary.artifact_sha256` = SHA-256 real do JSONL.
4. `pipeline_family` do summary = `amazon_mirror_primary`.
5. Todos os items carregam `pipeline_family = amazon_mirror_primary`.

## Validar localmente antes de plugar

Rodar o validator local em modo FULL (default; nao escreve no banco):

```powershell
python scripts\data_ops_producers\validate_commerce_artifact.py `
  --artifact-dir reports\data_ops_artifacts\amazon_mirror `
  --expected-family amazon_mirror_primary
```

Modo full le TODAS as linhas do JSONL, valida os 13 campos de cada item,
checa summary + SHA-256 e compara `summary.items_emitted` com o total real
de linhas JSON validas. Ou seja: uma linha invalida 5000 itens depois da
primeira reprovará o contrato.

Smoke rapido (opcional, so para JSONL muito grande; NAO substitui a
validacao full antes de plugar):

```powershell
python scripts\data_ops_producers\validate_commerce_artifact.py `
  --artifact-dir reports\data_ops_artifacts\amazon_mirror `
  --expected-family amazon_mirror_primary `
  --window 50
```

Saidas:

- `OK mode=full ...` = contrato OK de ponta a ponta, pode deixar o
  scheduler consumir.
- `FAIL mode=full reason=contrato_invalido` = ler `notes:` para ver o
  que falta (campo obrigatorio, summary, SHA mismatch, linha invalida,
  `summary_items_emitted_mismatch`).
- `FAIL mode=full reason=nenhum_artefato_jsonl_em=...` = nenhum JSONL
  encontrado.

## Precedencia com `amazon_local`

- `amazon_mirror_primary` tem precedencia sobre `amazon_local_legacy_backfill`.
- `amazon_local_legacy_backfill` so entra em lotes controlados de backfill.
- `amazon_local` observer continua read-only para diagnostico.

## Operacao recorrente apos primeiro JSONL

1. Operador do PC espelho deposita `<prefix>.jsonl` + `<prefix>_summary.json`.
2. Dry-run canonico:
   ```powershell
   powershell -File scripts\data_ops_scheduler\run_commerce_artifact_dryruns.ps1
   ```
3. Apply em escada (50 -> 200 -> 1000):
   ```powershell
   python -m sdk.plugs.commerce_dq_v3.runner --source amazon_mirror_primary --limit 50 --apply
   python -m sdk.plugs.commerce_dq_v3.runner --source amazon_mirror_primary --limit 200 --apply
   python -m sdk.plugs.commerce_dq_v3.runner --source amazon_mirror_primary --limit 1000 --apply
   ```
4. Parar se `ingestion_review_queue` subir acima do cap (5%) ou se
   `not_wine_rejections` crescer anormalmente em um degrau.

## O que NAO fazer

- Nao escrever direto em `public.wines` / `public.wine_sources`.
- Nao subir JSONL sem summary casado.
- Nao reutilizar `run_id` de execucao anterior.
- Nao promover `amazon_local` como feed primario competindo com este.
