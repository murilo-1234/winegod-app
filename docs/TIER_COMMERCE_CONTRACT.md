# Contrato de saida Tier1/Tier2 e Amazon mirror

## Escopo

Este contrato define o formato padronizado dos artefatos de execucao que
`tier1_global`, `tier2_*` e `amazon_mirror_primary` devem emitir para serem
consumidos de forma auditavel pelo `plug_commerce_dq_v3`.

Nao cria novo canal. O destino final continua sendo
`plug_commerce_dq_v3 -> DQ V3 -> public.wines + public.wine_sources`.

O que muda e a origem: em vez do plug ler `winegod_db` misturado, ele le um
artefato JSONL gravado pela execucao.

## Local padrao

```
reports/data_ops_artifacts/amazon_mirror/<YYYYMMDD_HHMMSS>_<run_id>.jsonl
reports/data_ops_artifacts/tier1/<YYYYMMDD_HHMMSS>_<run_id>.jsonl
reports/data_ops_artifacts/tier2/<chat>/<YYYYMMDD_HHMMSS>_<run_id>.jsonl
```

`<chat>` deve ser `chat1`, `chat2`, `chat3`, `chat4`, `chat5` ou `br` (o sufixo
do `scraper_id` correspondente: `commerce_tier2_chat1` -> `chat1`).

Variaveis de ambiente opcionais:

- `AMAZON_MIRROR_ARTIFACT_DIR`
- `TIER1_ARTIFACT_DIR`
- `TIER2_ARTIFACT_DIR`

## Campos obrigatorios por item

| Campo | Tipo | Observacao |
| --- | --- | --- |
| `pipeline_family` | string | `tier1`, `tier2` ou `amazon_mirror_primary` |
| `run_id` | string | identificador unico por execucao |
| `country` | string (ISO-2) | lowercase: `us`, `br`, `fr`, ... |
| `store_name` | string | nome da loja |
| `store_domain` | string | dominio sem protocolo, ex `vinhoclub.com.br` |
| `url_original` | string | URL completa do produto |
| `nome` | string | nome do vinho |
| `produtor` | string | produtor / vinicola |
| `safra` | string/int | ano da safra (pode ser null) |
| `preco` | number | preco unitario (pode ser null) |
| `moeda` | string | ISO-4217 (ex `BRL`, `USD`) |
| `captured_at` | string | ISO-8601 UTC |
| `source_pointer` | string | pointer auditavel (id da tabela, path do HTML, etc) |

Campos opcionais que o exporter aceita se presentes:

`asin`, `ean_gtin`, `tipo`, `regiao`, `sub_regiao`, `uvas`, `imagem_url`,
`url_imagem`, `harmonizacao`, `descricao`, `disponivel`.

## Campos obrigatorios por execucao (summary)

Ao lado do JSONL, a execucao deve gravar `<prefix>_summary.json`:

```json
{
  "run_id": "...",
  "pipeline_family": "tier1",
  "started_at": "2026-04-23T19:30:00Z",
  "finished_at": "2026-04-23T19:45:00Z",
  "host": "este_pc",
  "input_scope": "FR,ES,PT",
  "items_emitted": 1234,
  "artifact_sha256": "..."
}
```

## Comportamento do plug ao ler o artefato

- o exporter pega o JSONL mais recente no diretorio alvo (ordenado por mtime);
- valida formato linha-a-linha (ignora linhas vazias/invalidas);
- filtra por `pipeline_family` quando o campo existe;
- resolve `store_id` pelo `store_domain`/`url_original` via `public.stores`;
- anota no `ExportBundle.notes`:
  - `items_exported=<n>`
  - `artifact=<filename>`
  - `artifact_sha256=<hash>`
  - `pipeline_family=<value>`

## Precedencia

- Amazon: `amazon_mirror_primary` tem precedencia sobre `amazon_local_legacy_backfill`.
- Tier1/Tier2: artefato padronizado tem precedencia sobre leitura direta do
  `winegod_db` misturado (que so sobrevive via `winegod_admin_legacy_mixed`,
  com lineage explicita).

## Verificacao obrigatoria antes de apply

1. dry-run contra o artefato mais recente: observar `received`, `valid`, `filtered_notwine`.
2. checar `ingestion_review_queue` nao explodiu acima do cap (5%).
3. confirmar `source_pointer` nao vazio em amostra.
4. confirmar `artifact_sha256` e unico por artefato (nao re-aplicar o mesmo).

## O que NAO vale

- gravar direto em `public.wines` / `public.wine_sources` por fora do plug;
- mesclar Tier1 com Tier2 sem isolar `pipeline_family`;
- usar `amazon_local` como feed primario novo (congelado como legado);
- inventar `run_id` ou `captured_at` no exporter se o artefato nao trouxer.
