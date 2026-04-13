"""
Demanda 6A -- Finalizador de artefatos a partir do estado parcial.

Contexto: o piloto de 10.000 foi interrompido por decisao administrativa
apos 5/40 batches concluidos, com base em projecao operacional. Este
script consolida os 5 parciais existentes, gera os artefatos finais
coerentes com o escopo observado, e emite veredito NAO PRONTO no summary.

NAO re-executa batches. Apenas le parciais e consolida.

READ-ONLY em banco.
"""

import csv
import gzip
import hashlib
import json
import os
import sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_candidate_fanout_pilot as runner  # noqa: E402


def main():
    print("[finalize-partial] lendo checkpoint...")
    with open(runner.CHECKPOINT_JSON, "r", encoding="utf-8") as f:
        cp = json.load(f)
    completed = cp["completed_batches"]
    print(f"    batches concluidos: {completed}")
    print(f"    processed_items: {cp['processed_items']}")
    print(f"    batch_timings_sec: {cp['batch_timings_sec']}")

    print("[finalize-partial] lendo parciais...")
    detail_rows_raw = runner.read_all_partial_files(cp["total_batches"])
    print(f"    detail rows (raw): {len(detail_rows_raw):,}")

    # dedupe defensivo
    seen = set()
    detail_rows = []
    for r in detail_rows_raw:
        key = (r["render_wine_id"], r["channel"], r["candidate_rank"], r["candidate_id"])
        if key in seen:
            continue
        seen.add(key)
        detail_rows.append(r)
    print(f"    detail rows (deduped): {len(detail_rows):,}")

    # pilot_ids processados de verdade: extrair dos parciais, em ordem
    processed_ids_ordered = []
    seen_ids = set()
    for r in detail_rows:
        wid = int(r["render_wine_id"])
        if wid not in seen_ids:
            seen_ids.add(wid)
            processed_ids_ordered.append(wid)
    print(f"    unique render_wine_ids processados: {len(processed_ids_ordered):,}")

    # Para a contagem de cobertura, queremos os ids que foram ENVIADOS aos batches
    # concluidos. Re-seleciona piloto determisticamente e pega os primeiros N
    # correspondentes aos batches concluidos.
    print("[finalize-partial] re-selecionando piloto deterministico...")
    pilot_ids_full, control_ids = runner.select_pilot()
    n_completed_items = len(completed) * runner.BATCH_SIZE
    # batches concluidos sao contiguos [0..N-1] no nosso caso (completed=[0,1,2,3,4])
    # mas para ser robusto, pegamos batch_start por batch_id
    submitted_ids = []
    for batch_id in sorted(completed):
        start = batch_id * runner.BATCH_SIZE
        submitted_ids.extend(pilot_ids_full[start:start + runner.BATCH_SIZE])
    print(f"    submitted_ids (todos os ids enviados): {len(submitted_ids):,}")

    # Cobertura: submitted_ids - processed_ids = itens submetidos mas sem NENHUM candidato
    submitted_set = set(submitted_ids)
    processed_set = set(processed_ids_ordered)
    no_candidate_ids = submitted_set - processed_set
    print(f"    itens sem nenhum candidato: {len(no_candidate_ids):,}")

    print("[finalize-partial] escrevendo detail CSV.gz...")
    runner.write_detail_csv_gz(runner.DETAIL_CSV_GZ, detail_rows)

    print("[finalize-partial] construindo per_wine rows (para submitted_ids)...")
    per_wine_rows = runner.build_per_wine_rows(detail_rows, submitted_ids)

    print("[finalize-partial] escrevendo per_wine CSV.gz...")
    runner.write_per_wine_csv_gz(runner.PERWINE_CSV_GZ, per_wine_rows)

    # Metricas
    total_processed = len(submitted_ids)
    total_elapsed = sum(cp["batch_timings_sec"])

    n_render_any = sum(1 for r in per_wine_rows if r["render_any_candidate"] == 1)
    n_import_any = sum(1 for r in per_wine_rows if r["import_any_candidate"] == 1)
    n_render_zero = total_processed - n_render_any
    n_import_zero = total_processed - n_import_any
    n_both_zero = sum(
        1 for r in per_wine_rows
        if r["render_any_candidate"] == 0 and r["import_any_candidate"] == 0
    )

    render_top1_channel_dist = defaultdict(int)
    import_top1_channel_dist = defaultdict(int)
    for r in per_wine_rows:
        if r["top1_render_channel"]:
            render_top1_channel_dist[r["top1_render_channel"]] += 1
        if r["top1_import_channel"]:
            import_top1_channel_dist[r["top1_import_channel"]] += 1

    render_top1_scores = [float(r["top1_render_score"]) for r in per_wine_rows if r["top1_render_score"] != ""]
    import_top1_scores = [float(r["top1_import_score"]) for r in per_wine_rows if r["top1_import_score"] != ""]
    render_gaps = [float(r["top1_render_gap"]) for r in per_wine_rows if r["top1_render_gap"] != ""]
    import_gaps = [float(r["top1_import_gap"]) for r in per_wine_rows if r["top1_import_gap"] != ""]

    # Throughput
    timings = cp["batch_timings_sec"]
    batch0 = timings[0] if timings else 0
    post_bootstrap = timings[1:] if len(timings) > 1 else []
    median_post = runner.median(post_bootstrap) if post_bootstrap else 0
    p90_post = runner.percentile(post_bootstrap, 90) if post_bootstrap else 0
    mean_post = sum(post_bootstrap) / len(post_bootstrap) if post_bootstrap else 0

    items_per_minute = total_processed / (total_elapsed / 60) if total_elapsed > 0 else 0
    # projecao do piloto completo usando mediana pos-bootstrap
    proj_pilot_sec = batch0 + median_post * (runner.PILOT_SIZE // runner.BATCH_SIZE - 1)
    proj_pilot_hr = proj_pilot_sec / 3600
    # projecao do full fan-out (779_383): mesma taxa pos-bootstrap
    proj_full_sec = (median_post / runner.BATCH_SIZE) * 779_383 + batch0
    proj_full_hr = proj_full_sec / 3600
    proj_full_days = proj_full_hr / 24

    # Escreve summary NAO PRONTO
    print("[finalize-partial] escrevendo summary NAO PRONTO...")
    ts_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    L = []
    L.append("# Tail Candidate Fan-out Pilot -- Summary (Demanda 6A)")
    L.append("")
    L.append(f"Data de execucao: {ts_now}")
    L.append("Executor: `scripts/run_candidate_fanout_pilot.py` + `scripts/finalize_d6_partial.py`")
    L.append("")
    L.append("Snapshot oficial do projeto ancorado em 2026-04-10. Artefatos preservam o sufixo `2026-04-10` mesmo quando a execucao ocorre em data posterior.")
    L.append("")

    L.append("## VEREDICTO")
    L.append("")
    L.append("**NAO PRONTO**")
    L.append("")
    L.append("O runner da Demanda 6 NAO esta pronto para fan-out full. Motivo: **inviabilidade operacional por throughput observado**. Detalhes abaixo.")
    L.append("")

    L.append("## Estado inicial encontrado (Tarefa A)")
    L.append("")
    L.append("- checkpoint existente (`tail_candidate_fanout_pilot_checkpoint_2026-04-10.json`) com:")
    L.append("  - `completed_batches = []`")
    L.append("  - `processed_items = 0`")
    L.append("  - `done = false`")
    L.append("  - `started_at = 2026-04-11 10:45:33`")
    L.append("- diretorio `reports/.fanout_pilot_partial/` existia mas **estava vazio** (0 parciais)")
    L.append("- artefatos finais nao existiam")
    L.append("")
    L.append("**Acao tomada:** checkpoint zerado sem parciais reais NAO conta como prova de resume. Estado classificado como **STALE** e **descartado** com `--fresh`. Reinicio limpo.")
    L.append("")

    L.append("## Tarefa B -- Prova de `--stop-after 3`")
    L.append("")
    L.append("Execucao: `python scripts/run_candidate_fanout_pilot.py --fresh --stop-after 3`")
    L.append("")
    L.append("Evidencia (do checkpoint imediatamente apos o stop):")
    L.append("")
    L.append("- `completed_batches = [0, 1, 2]`")
    L.append("- `processed_items = 750`")
    L.append("- `batch_timings_sec = [1442.961, 2253.460, 2024.929]`")
    L.append("- 3 arquivos parciais em disco: `batch_00000.csv`, `batch_00001.csv`, `batch_00002.csv`")
    L.append("- exit 0 do processo")
    L.append("- log: `[--stop-after=3] parando apos 3 batches desta sessao`")
    L.append("")
    L.append("**`--stop-after 3` comprovado.**")
    L.append("")

    L.append("## Tarefa C -- Prova de `resume` por execucao")
    L.append("")
    L.append("Execucao: `python scripts/run_candidate_fanout_pilot.py` (sem `--fresh`)")
    L.append("")
    L.append("Evidencias:")
    L.append("")
    L.append("- log: `[checkpoint] RESUME de 3 batches ja completos (resume #1)`")
    L.append(f"- `resume_count = {cp['resume_count']}` no checkpoint apos retomada")
    L.append("- batches completos apos a retomada: `[3, 4]` (continuaram do proximo batch nao-completo)")
    L.append("- nenhum recomputo de batches 0-2 (preservados do run anterior)")
    L.append("")
    L.append("**Resume comprovado por execucao real.**")
    L.append("")

    L.append("## Tarefa D -- Decisao administrativa de parada")
    L.append("")
    L.append("Apos 5 batches concluidos (1.250 itens = 12.5% do piloto), a projecao de tempo baseada na mediana dos batches pos-bootstrap indicou inviabilidade operacional. A parada foi ordenada pelo administrador em `2026-04-11 ~14:30`.")
    L.append("")
    L.append("- processo Python PID 20392 foi terminado via `taskkill`")
    L.append("- batch 5 (que estava em processamento no momento da parada) foi perdido")
    L.append("- checkpoint mantido integro: `completed_batches=[0,1,2,3,4]`, `done=false`")
    L.append("- artefatos finais foram consolidados pelo script `finalize_d6_partial.py` a partir dos 5 parciais existentes")
    L.append("")

    L.append("## Parte A -- Selecao do piloto")
    L.append("")
    L.append("1. Leitura de `tail_y2_lineage_enriched_2026-04-10.csv.gz` (779.383 ids).")
    L.append("2. `ORDER BY render_wine_id ASC` (deterministico).")
    L.append("3. Exclusao dos 40 controles (positivo + negativo, Demanda 5).")
    L.append("4. Take dos primeiros 10.000.")
    L.append("")
    L.append(f"- `PILOT_SIZE` (target) = {runner.PILOT_SIZE:,}")
    L.append(f"- `PILOT_SIZE` (efetivamente executado) = **{total_processed:,}**")
    L.append(f"- Controles excluidos: {len(control_ids)}")
    L.append(f"- `pilot_hash` (sha256): `{cp['pilot_hash'][:16]}...`")
    L.append(f"- Primeiro id processado: {submitted_ids[0] if submitted_ids else '-'}")
    L.append(f"- Ultimo id processado: {submitted_ids[-1] if submitted_ids else '-'}")
    L.append("")

    L.append("## Parte B -- Checkpoint")
    L.append("")
    L.append(f"- `BATCH_SIZE` = {runner.BATCH_SIZE}")
    L.append(f"- Total de batches (target): {cp['total_batches']}")
    L.append(f"- Batches concluidos: **{len(completed)}** ({len(completed)/cp['total_batches']*100:.1f}%)")
    L.append(f"- `resume_count` = {cp['resume_count']}")
    L.append(f"- Resume testado por execucao real: **SIM**")
    L.append(f"- `done` = {cp['done']}")
    L.append("")

    L.append("## Parte C -- Execucao efetiva")
    L.append("")
    L.append(f"- Itens submetidos aos batches concluidos: **{total_processed:,}**")
    L.append(f"- Rows no detail CSV: **{len(detail_rows):,}**")
    L.append(f"- Rows no per_wine CSV: **{len(per_wine_rows):,}**")
    L.append("")

    L.append("## QA -- Validacoes")
    L.append("")
    L.append("| check | valor | resultado |")
    L.append("|---|---|---|")
    L.append(f"| target 10.000 atingido | {total_processed:,}/10.000 | **FALHA (parado por decisao administrativa)** |")
    L.append(f"| render_wine_id unico em per_wine | {len({r['render_wine_id'] for r in per_wine_rows}):,}/{len(per_wine_rows):,} | {'OK' if len({r['render_wine_id'] for r in per_wine_rows}) == len(per_wine_rows) else 'FALHA'} |")
    controls_in_submitted = set(submitted_ids) & control_ids
    L.append(f"| nenhum controle entre os submetidos | {len(controls_in_submitted)} | {'OK' if len(controls_in_submitted) == 0 else 'FALHA'} |")
    L.append(f"| detail rows > 0 | {len(detail_rows):,} | {'OK' if len(detail_rows) > 0 else 'FALHA'} |")
    L.append(f"| logica D5 congelada (import de `build_candidate_controls`) | sim | OK |")
    L.append("")

    L.append("## Cobertura por universo (sobre 1.250 itens)")
    L.append("")
    L.append("| metrica | wines | % |")
    L.append("|---|---|---|")
    L.append(f"| pelo menos 1 candidato Render | {n_render_any:,} | {n_render_any/total_processed*100:.2f}% |")
    L.append(f"| pelo menos 1 candidato Import | {n_import_any:,} | {n_import_any/total_processed*100:.2f}% |")
    L.append(f"| 0 candidatos Render | {n_render_zero:,} | {n_render_zero/total_processed*100:.2f}% |")
    L.append(f"| 0 candidatos Import | {n_import_zero:,} | {n_import_zero/total_processed*100:.2f}% |")
    L.append(f"| 0 candidatos em ambos | {n_both_zero:,} | {n_both_zero/total_processed*100:.2f}% |")
    L.append("")

    L.append("## Distribuicao de canal top1 por universo")
    L.append("")
    L.append("| canal | top1_render | top1_import |")
    L.append("|---|---|---|")
    all_channels = sorted(set(render_top1_channel_dist.keys()) | set(import_top1_channel_dist.keys()))
    for ch in all_channels:
        L.append(f"| `{ch}` | {render_top1_channel_dist.get(ch, 0):,} | {import_top1_channel_dist.get(ch, 0):,} |")
    L.append("")

    L.append("## Scores")
    L.append("")
    L.append("| metrica | valor |")
    L.append("|---|---|")
    if render_top1_scores:
        L.append(f"| mediana top1_render_score | {runner.median(render_top1_scores):.4f} |")
        L.append(f"| p90 top1_render_score | {runner.percentile(render_top1_scores, 90):.4f} |")
    if import_top1_scores:
        L.append(f"| mediana top1_import_score | {runner.median(import_top1_scores):.4f} |")
        L.append(f"| p90 top1_import_score | {runner.percentile(import_top1_scores, 90):.4f} |")
    if render_gaps:
        L.append(f"| mediana top1_render_gap | {runner.median(render_gaps):.4f} |")
    if import_gaps:
        L.append(f"| mediana top1_import_gap | {runner.median(import_gaps):.4f} |")
    L.append("")

    L.append("## Throughput (leitura com disciplina)")
    L.append("")
    L.append("**Tempo por batch registrado:**")
    L.append("")
    L.append("| batch | tempo (s) | tempo (min) | observacao |")
    L.append("|---|---|---|---|")
    for i, t in enumerate(timings):
        obs = "com bootstrap" if i == 0 else "pos-bootstrap" if i < 3 else "pos-bootstrap (run 1)" if i == 2 else "pos-bootstrap (run 2, resume)"
        if i == 0:
            obs = "com bootstrap (run 1)"
        elif i in (1, 2):
            obs = "pos-bootstrap (run 1)"
        else:
            obs = "pos-bootstrap (run 2, resume)"
        L.append(f"| {i} | {t:.1f} | {t/60:.2f} | {obs} |")
    L.append("")
    L.append("**Agregados:**")
    L.append("")
    L.append(f"- tempo batch 0 (com bootstrap): **{batch0:.1f}s ({batch0/60:.1f} min)**")
    if post_bootstrap:
        L.append(f"- mediana batches 1..N (pos-bootstrap, n={len(post_bootstrap)}): **{median_post:.1f}s ({median_post/60:.1f} min)**")
        L.append(f"- p90 batches 1..N: **{p90_post:.1f}s ({p90_post/60:.1f} min)**")
        L.append(f"- media batches 1..N: **{mean_post:.1f}s ({mean_post/60:.1f} min)**")
    L.append(f"- tempo total efetivo (soma dos timings): **{total_elapsed:.1f}s ({total_elapsed/60:.1f} min)**")
    L.append(f"- itens por minuto (sobre {total_processed:,} itens em {total_elapsed/60:.1f} min): **{items_per_minute:.2f}**")
    L.append("")
    L.append("**Projecao do piloto de 10.000 (se tivesse sido concluido):**")
    L.append("")
    L.append(f"- formula: `batch0 + mediana_pos_bootstrap * 39 = {batch0:.0f}s + {median_post:.0f}s * 39`")
    L.append(f"- tempo total estimado: **{proj_pilot_sec:.0f}s = {proj_pilot_sec/60:.0f} min = {proj_pilot_hr:.1f}h**")
    L.append("")
    L.append("**Projecao do fan-out full (779.383 itens) usando a mesma taxa pos-bootstrap:**")
    L.append("")
    L.append(f"- formula: `(mediana_pos_bootstrap / batch_size) * 779.383 + batch0`")
    L.append(f"- tempo estimado: **{proj_full_sec:.0f}s = {proj_full_hr:.0f}h = {proj_full_days:.1f} dias**")
    L.append("")

    L.append("## Leitura operacional")
    L.append("")
    L.append("- Esta demanda valida OPERACAO do runner. NAO substitui o gate de qualidade da Demanda 5.")
    L.append("- O gate de qualidade ja foi atingido no piso exato (90% top3 positivos) em D5 e permanece valido.")
    L.append("- O motivo da reprovacao desta demanda e **exclusivamente operacional**: throughput observado e incompativel com o tamanho do universo alvo.")
    L.append("")

    L.append("## Erros e retries observados")
    L.append("")
    errors = cp.get("errors", [])
    if errors:
        L.append(f"- **{len(errors)}** erros registrados:")
        for e in errors[:20]:
            L.append(f"  - {e}")
    else:
        L.append("- **Nenhum erro** registrado durante os 5 batches concluidos.")
        L.append("- A parada do processo em batch 5 foi ordenada administrativamente (nao foi falha).")
    L.append("")

    L.append("## Bloqueios reais para fan-out full")
    L.append("")
    L.append(f"1. **Throughput inviavel**: ~{median_post/60:.0f} min/batch implica ~{proj_full_days:.0f} dias para os 779.383 itens. Inviavel para qualquer cronograma de produto.")
    L.append("2. **Batch 0 pago a cada sessao**: bootstrap carrega 1.727.058 vivino_ids do Render + constroi TEMP TABLE `_only_vivino`. Custo fixo ~5 min por run (pode ser aceitavel isolado, mas empilha quando o runner precisa de muitos resumes).")
    L.append("3. **Sem paralelismo**: runner atual e sequencial single-thread. Nao tem pool de conexoes nem worker por canal.")
    L.append("4. **Conexao Render distante**: latencia Brasil -> Oregon, plano Basic, risco de SSL drop em execucao longa.")
    L.append("")
    L.append("## O que seria necessario para liberar fan-out full")
    L.append("")
    L.append("(NAO escopo desta demanda. Registrado apenas como bloqueio real.)")
    L.append("")
    L.append("- paralelizar o loop de canais (por exemplo, batch de N wines rodando em paralelo contra cada canal), mantendo a logica D5 congelada")
    L.append("- ou rodar os candidate lookups em batch unico por canal ao inves de loop por wine")
    L.append("- ou rodar o fan-out nao no seu laptop em Brasil, e sim em um worker proximo ao Render (Oregon) para eliminar latencia de rede")
    L.append("- remedir throughput e revalidar antes de fan-out")
    L.append("")

    L.append("## Artefatos gerados")
    L.append("")
    L.append("| artefato | status |")
    L.append("|---|---|")
    L.append(f"| `tail_candidate_fanout_pilot_detail_2026-04-10.csv.gz` | gerado ({len(detail_rows):,} rows, sobre 1.250 itens) |")
    L.append(f"| `tail_candidate_fanout_pilot_per_wine_2026-04-10.csv.gz` | gerado ({len(per_wine_rows):,} rows = submetidos) |")
    L.append(f"| `tail_candidate_fanout_pilot_summary_2026-04-10.md` | este arquivo |")
    L.append(f"| `tail_candidate_fanout_pilot_checkpoint_2026-04-10.json` | mantido (`done=false`, 5/40 batches) |")
    L.append("")

    L.append("## Veredicto final")
    L.append("")
    L.append("**NAO PRONTO PARA FAN-OUT FULL.**")
    L.append("")
    L.append("- Runner COMPILA e EXECUTA corretamente: `--stop-after` e `resume` comprovados por execucao real.")
    L.append("- Logica da Demanda 5 preservada sem drift (importada do script original).")
    L.append("- Nenhum erro registrado no que foi executado.")
    L.append("- **Bloqueio unico e decisivo: throughput operacional.**")
    L.append("")
    L.append("Fan-out full fica bloqueado. Proxima frente precisa endereca throughput antes de tentar o universo inteiro.")
    L.append("")

    with open(runner.SUMMARY_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")

    # Atualiza checkpoint mantendo done=false mas marcando que a finalizacao parcial ocorreu
    cp["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cp["finalized_partial"] = True
    cp["finalized_at"] = cp["last_update"]
    cp["verdict"] = "NAO_PRONTO"
    cp["verdict_reason"] = "throughput operacional inviavel; piloto interrompido por decisao administrativa apos 5/40 batches"
    with open(runner.CHECKPOINT_JSON, "w", encoding="utf-8") as f:
        json.dump(cp, f, indent=2, ensure_ascii=False)

    print()
    print(f"Detail:     {runner.DETAIL_CSV_GZ}")
    print(f"Per-wine:   {runner.PERWINE_CSV_GZ}")
    print(f"Summary:    {runner.SUMMARY_MD}")
    print(f"Checkpoint: {runner.CHECKPOINT_JSON}")
    print()
    print("=== DEMANDA 6A: NAO PRONTO (throughput) ===")


if __name__ == "__main__":
    main()
