"""
Executar DELETE dos 4.191 wrong_owner delete_only_safe.
Fonte unica: wrong_owner_delete_only_candidates.csv (congelado).
Zero INSERT. Validacao pre-delete por linha.
Auto-abort se taxa de falha > 1%.
"""
import csv
import os
import sys
from datetime import datetime, timezone
import _env

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import psycopg2

RENDER_DB = os.environ["DATABASE_URL"]

DIR = os.path.dirname(__file__)
SOURCE_CSV = os.path.join(DIR, "wrong_owner_delete_only_candidates.csv")
EXECUTED_CSV = os.path.join(DIR, "wrong_owner_delete_only_executed.csv")
SKIPPED_CSV = os.path.join(DIR, "wrong_owner_delete_only_skipped.csv")
REVERT_CSV = os.path.join(DIR, "wrong_owner_delete_only_revert.csv")

BATCH_SIZE = 100
ABORT_THRESHOLD = 0.01  # 1%


def main():
    print("=" * 80, flush=True)
    print("EXECUCAO DELETE_ONLY WRONG_OWNER — 4.191 LINHAS", flush=True)
    print("=" * 80, flush=True)

    # Carregar CSV fonte
    with open(SOURCE_CSV, encoding="utf-8") as f:
        all_rows = list(csv.DictReader(f))
    total = len(all_rows)
    print(f"CSV fonte: {total:,} linhas", flush=True)

    rc = psycopg2.connect(
        RENDER_DB, options="-c statement_timeout=300000",
        keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=5,
    )
    r = rc.cursor()

    # Snapshot antes
    r.execute("SELECT COUNT(*) FROM wine_sources")
    ws_antes = r.fetchone()[0]
    print(f"Wine_sources ANTES: {ws_antes:,}", flush=True)

    # ══════════════════════════════════════════════════════════════════════════
    # VALIDACAO PRE-DELETE
    # ══════════════════════════════════════════════════════════════════════════
    print(f"\nFase 1: Validacao pre-delete ({total:,} linhas)...", flush=True)

    validated = []
    skipped = []

    for idx, row in enumerate(all_rows):
        if (idx + 1) % 500 == 0:
            pct_skip = len(skipped) / (idx + 1) * 100
            print(f"  {idx+1:,}/{total:,} | ok={len(validated):,} skip={len(skipped):,} ({pct_skip:.2f}%)", flush=True)

            # Auto-abort check
            if len(skipped) > total * ABORT_THRESHOLD:
                print(f"\n  *** AUTO-ABORT: {len(skipped)} skipped (>{total * ABORT_THRESHOLD:.0f} limite 1%) ***", flush=True)
                # Salvar skipped ate agora
                _write_skipped(skipped)
                r.close(); rc.close()
                return

        ws_id = int(row["ws_id"])
        actual_wine_id = int(row["actual_wine_id"])
        expected_wine_id = int(row["expected_wine_id"])
        store_id = int(row["store_id"])
        url = row["url"]

        # Check 1: ws_id ainda existe
        r.execute(
            "SELECT wine_id, store_id, url, preco, moeda, disponivel, descoberto_em, atualizado_em FROM wine_sources WHERE id = %s",
            (ws_id,),
        )
        ws_row = r.fetchone()

        if not ws_row:
            skipped.append({**row, "motivo": "ws_id nao existe mais"})
            continue

        ws_wine, ws_store, ws_url, ws_preco, ws_moeda, ws_disp, ws_desc, ws_atua = ws_row

        # Check 2: ws_id bate com actual_wine_id + store_id + url
        if ws_wine != actual_wine_id or ws_url != url:
            skipped.append({**row, "motivo": f"dados divergem: wine={ws_wine} url={ws_url[:50]}"})
            continue

        # Check 3: expected_wine_id possui wine_source com mesma url + store_id
        r.execute(
            "SELECT COUNT(*) FROM wine_sources WHERE wine_id = %s AND store_id = %s AND url = %s",
            (expected_wine_id, store_id, url),
        )
        if r.fetchone()[0] == 0:
            skipped.append({**row, "motivo": "owner correto nao possui este link"})
            continue

        # Validado — guardar snapshot para revert
        validated.append({
            **row,
            "ws_preco": str(ws_preco) if ws_preco is not None else "",
            "ws_moeda": ws_moeda or "",
            "ws_disponivel": str(ws_disp),
            "ws_descoberto_em": str(ws_desc),
            "ws_atualizado_em": str(ws_atua),
        })

    pct_skip_final = len(skipped) / total * 100
    print(f"\n  Validacao completa:", flush=True)
    print(f"    Validados: {len(validated):,}", flush=True)
    print(f"    Skipped:   {len(skipped):,} ({pct_skip_final:.2f}%)", flush=True)

    # Auto-abort final
    if pct_skip_final > ABORT_THRESHOLD * 100:
        print(f"\n  *** AUTO-ABORT: {pct_skip_final:.2f}% > {ABORT_THRESHOLD*100}% ***", flush=True)
        _write_skipped(skipped)
        r.close(); rc.close()
        return

    # ══════════════════════════════════════════════════════════════════════════
    # EXECUCAO DELETE
    # ══════════════════════════════════════════════════════════════════════════
    print(f"\nFase 2: Executando {len(validated):,} DELETEs...", flush=True)

    deleted = 0
    errors = 0

    for batch_start in range(0, len(validated), BATCH_SIZE):
        batch = validated[batch_start:batch_start + BATCH_SIZE]

        try:
            r.execute("SAVEPOINT wo_del_batch")

            for v in batch:
                r.execute("DELETE FROM wine_sources WHERE id = %s", (int(v["ws_id"]),))
                deleted += r.rowcount

            r.execute("RELEASE SAVEPOINT wo_del_batch")
            rc.commit()

        except Exception as ex:
            print(f"  ERRO batch {batch_start}: {ex}", flush=True)
            r.execute("ROLLBACK TO SAVEPOINT wo_del_batch")
            rc.commit()
            errors += 1

        if (batch_start // BATCH_SIZE) % 10 == 0:
            print(f"  {batch_start + len(batch):,}/{len(validated):,} | deleted={deleted:,}", flush=True)

    # ══════════════════════════════════════════════════════════════════════════
    # ARTEFATOS
    # ══════════════════════════════════════════════════════════════════════════
    print(f"\nGerando artefatos...", flush=True)

    # Executed CSV
    exec_fields = list(validated[0].keys()) if validated else []
    with open(EXECUTED_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=exec_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(validated)
    print(f"  {EXECUTED_CSV} ({len(validated):,} linhas)", flush=True)

    # Skipped CSV
    _write_skipped(skipped)

    # Revert CSV (snapshot completo para re-INSERT)
    revert_fields = [
        "ws_id", "actual_wine_id", "store_id", "url",
        "ws_preco", "ws_moeda", "ws_disponivel", "ws_descoberto_em", "ws_atualizado_em",
    ]
    with open(REVERT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=revert_fields, extrasaction="ignore")
        writer.writeheader()
        for v in validated:
            writer.writerow({
                "ws_id": v["ws_id"],
                "actual_wine_id": v["actual_wine_id"],
                "store_id": v["store_id"],
                "url": v["url"],
                "ws_preco": v.get("ws_preco", ""),
                "ws_moeda": v.get("ws_moeda", ""),
                "ws_disponivel": v.get("ws_disponivel", ""),
                "ws_descoberto_em": v.get("ws_descoberto_em", ""),
                "ws_atualizado_em": v.get("ws_atualizado_em", ""),
            })
    print(f"  {REVERT_CSV} ({len(validated):,} linhas)", flush=True)

    # ══════════════════════════════════════════════════════════════════════════
    # VALIDACAO FINAL
    # ══════════════════════════════════════════════════════════════════════════
    r.execute("SELECT COUNT(*) FROM wine_sources")
    ws_depois = r.fetchone()[0]

    print(f"\n{'=' * 80}", flush=True)
    print(f"RESULTADO", flush=True)
    print(f"{'=' * 80}", flush=True)
    print(f"  Previstas:    {total:,}", flush=True)
    print(f"  Validadas:    {len(validated):,}", flush=True)
    print(f"  Deletadas:    {deleted:,}", flush=True)
    print(f"  Puladas:      {len(skipped):,}", flush=True)
    print(f"  Erros batch:  {errors}", flush=True)
    print(f"  WS antes:     {ws_antes:,}", flush=True)
    print(f"  WS depois:    {ws_depois:,}", flush=True)
    print(f"  Delta:        {ws_antes - ws_depois:,}", flush=True)

    # 20 exemplos — confirmar que ws_id sumiu e owner correto manteve
    print(f"\n  20 exemplos conferidos:", flush=True)
    for i, v in enumerate(validated[:20], 1):
        ws_id = int(v["ws_id"])
        exp = int(v["expected_wine_id"])
        sid = int(v["store_id"])
        url = v["url"]

        # ws_id sumiu?
        r.execute("SELECT COUNT(*) FROM wine_sources WHERE id = %s", (ws_id,))
        still_exists = r.fetchone()[0] > 0

        # Owner correto ainda tem?
        r.execute(
            "SELECT COUNT(*) FROM wine_sources WHERE wine_id = %s AND store_id = %s AND url = %s",
            (exp, sid, url),
        )
        correct_has = r.fetchone()[0] > 0

        status = "OK" if not still_exists and correct_has else f"PROBLEMA (exists={still_exists} correct={correct_has})"
        print(f"  [{i:>2}] ws_id={ws_id} | deleted={'SIM' if not still_exists else 'NAO'} | correct_has={'SIM' if correct_has else 'NAO'} | {status}", flush=True)
        print(f"       {v['url'][:55]}", flush=True)

    # Skipped motivos
    if skipped:
        motivos = {}
        for s in skipped:
            m = s.get("motivo", "?")
            motivos[m] = motivos.get(m, 0) + 1
        print(f"\n  Motivos de skip:", flush=True)
        for m in sorted(motivos, key=lambda x: -motivos[x]):
            print(f"    {motivos[m]:>5}  {m}", flush=True)

    r.close(); rc.close()
    print(f"\nFim.", flush=True)


def _write_skipped(skipped):
    if not skipped:
        with open(SKIPPED_CSV, "w", newline="", encoding="utf-8") as f:
            f.write("(vazio)\n")
        return
    fields = list(skipped[0].keys())
    with open(SKIPPED_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(skipped)
    print(f"  {SKIPPED_CSV} ({len(skipped):,} linhas)", flush=True)


if __name__ == "__main__":
    main()
