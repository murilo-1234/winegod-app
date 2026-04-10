"""
wrong_owner_classe_b_batch_all.py
==================================
Executa UPDATE de wine_id nos 4058 casos restantes de move_needed_safe,
em batches de 500 com guardrails e revert lossless.

Exclui explicitamente os 100 ws_ids ja processados no piloto.
Zero INSERT, zero DELETE — apenas UPDATE.

Uso:
    python scripts/wrong_owner_classe_b_batch_all.py
"""

import csv
import os
import sys
import time
from datetime import datetime
import _env

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import psycopg2

RENDER_DB = os.environ["DATABASE_URL"]

DIR = os.path.dirname(os.path.abspath(__file__))
SAFE_CSV = os.path.join(DIR, 'wrong_owner_move_needed_safe.csv')
PILOT_REVERT_CSV = os.path.join(DIR, 'wrong_owner_move_needed_pilot_100_revert.csv')
BATCH_SIZE = 500

# Guardrails
MAX_ERRORS = 0          # qualquer erro = parar
MAX_SKIP_PCT = 0.01     # >1% skipped no batch = parar


def load_pilot_wsids():
    wsids = set()
    with open(PILOT_REVERT_CSV, 'r', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            wsids.add(r['ws_id'].strip())
    return wsids


def load_remaining(pilot_wsids):
    with open(SAFE_CSV, 'r', encoding='utf-8') as f:
        all_rows = list(csv.DictReader(f))
    remaining = [r for r in all_rows if r['ws_id'].strip() not in pilot_wsids]
    return remaining


def connect_render():
    conn = psycopg2.connect(
        RENDER_DB,
        options='-c statement_timeout=30000',
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )
    conn.autocommit = False
    return conn


def snapshot_row(cur, ws_id):
    cur.execute("""
        SELECT id, wine_id, store_id, url, preco, moeda, disponivel,
               descoberto_em, atualizado_em
        FROM wine_sources WHERE id = %s
    """, (ws_id,))
    row = cur.fetchone()
    if row:
        return {
            'ws_id': row[0], 'wine_id': row[1], 'store_id': row[2],
            'url': row[3], 'preco': row[4], 'moeda': row[5],
            'disponivel': row[6], 'descoberto_em': row[7], 'atualizado_em': row[8],
        }
    return None


def validate_and_update(cur, row, snapshot):
    ws_id = int(row['ws_id'])
    actual = int(row['actual_wine_id'])
    expected = int(row['expected_wine_id'])
    store_id = snapshot['store_id']
    url = snapshot['url']

    if snapshot['wine_id'] != actual:
        return 'skipped', f'wine_id mudou: era {actual}, agora {snapshot["wine_id"]}'

    csv_url = row.get('url', '').strip()
    if csv_url and csv_url != url:
        return 'skipped', f'url diverge: csv={csv_url[:60]} db={str(url)[:60]}'

    csv_store = row.get('store_id', '').strip()
    if csv_store and str(store_id) != csv_store:
        return 'skipped', f'store_id diverge: csv={csv_store} db={store_id}'

    cur.execute("SELECT 1 FROM wines WHERE id = %s", (expected,))
    if not cur.fetchone():
        return 'skipped', f'expected_wine_id {expected} nao existe'

    cur.execute("""
        UPDATE wine_sources
        SET wine_id = %s
        WHERE id = %s
          AND wine_id = %s
          AND NOT EXISTS (
              SELECT 1 FROM wine_sources w2
              WHERE w2.wine_id = %s AND w2.store_id = %s AND w2.url = %s
          )
    """, (expected, ws_id, actual, expected, store_id, url))

    if cur.rowcount == 1:
        return 'updated', 'ok'
    elif cur.rowcount == 0:
        cur.execute("SELECT wine_id FROM wine_sources WHERE id = %s", (ws_id,))
        check = cur.fetchone()
        if not check:
            return 'skipped', 'ws_id deletado'
        if check[0] != actual:
            return 'skipped', f'wine_id ja mudou para {check[0]}'
        cur.execute("""
            SELECT id FROM wine_sources
            WHERE wine_id = %s AND store_id = %s AND url = %s
        """, (expected, store_id, url))
        dup = cur.fetchone()
        if dup:
            return 'skipped', f'link ja existe no expected (ws_id={dup[0]})'
        return 'skipped', 'rowcount=0 desconhecido'
    else:
        return 'error', f'rowcount={cur.rowcount}'


REVERT_FIELDS = ['ws_id', 'old_wine_id', 'new_wine_id', 'store_id', 'url',
                 'preco', 'moeda', 'disponivel', 'descoberto_em', 'atualizado_em']
SKIPPED_FIELDS = ['ws_id', 'actual_wine_id', 'expected_wine_id', 'url',
                  'store_id', 'status', 'motivo']
BATCH_FIELDS = ['ws_id', 'actual_wine_id', 'expected_wine_id', 'store_id',
                'url', 'status', 'motivo']


def write_batch_csvs(batch_num, batch_rows, revert_rows, skipped_rows):
    prefix = f'wrong_owner_move_needed_batch_{batch_num}'

    p1 = os.path.join(DIR, f'{prefix}.csv')
    with open(p1, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=BATCH_FIELDS, extrasaction='ignore')
        w.writeheader()
        w.writerows(batch_rows)

    p2 = os.path.join(DIR, f'{prefix}_revert.csv')
    with open(p2, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=REVERT_FIELDS, extrasaction='ignore')
        w.writeheader()
        w.writerows(revert_rows)

    p3 = os.path.join(DIR, f'{prefix}_skipped.csv')
    with open(p3, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=SKIPPED_FIELDS, extrasaction='ignore')
        w.writeheader()
        w.writerows(skipped_rows)

    return p1, p2, p3


def main():
    print("=" * 70)
    print("CLASSE B — BATCH COMPLETO (4058 restantes)")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 70)

    # 1. Carregar e filtrar
    print("\n[1] Carregando dados...")
    pilot_wsids = load_pilot_wsids()
    print(f"  Piloto ws_ids excluidos: {len(pilot_wsids)}")

    remaining = load_remaining(pilot_wsids)
    print(f"  Remanescentes apos exclusao: {len(remaining)}")

    # Confirmar zero overlap
    remaining_wsids = set(r['ws_id'].strip() for r in remaining)
    overlap = remaining_wsids & pilot_wsids
    if overlap:
        print(f"  !!! OVERLAP com piloto: {len(overlap)} ws_ids. ABORTANDO.")
        return
    print(f"  Overlap com piloto: 0 (OK)")

    # 2. Calcular batches
    n_batches = (len(remaining) + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"\n  Batches de {BATCH_SIZE}: {n_batches} batches")
    for i in range(n_batches):
        start = i * BATCH_SIZE
        end = min(start + BATCH_SIZE, len(remaining))
        print(f"    Batch {i+1}: linhas {start+1}-{end} ({end-start} rows)")

    # 3. Conectar
    print("\n[2] Conectando ao Render...")
    conn = connect_render()
    cur = conn.cursor()
    print("  Conectado.")

    # 4. Executar batches
    total_updated = 0
    total_skipped = 0
    total_errors = 0
    all_revert = []
    all_skipped = []
    all_batch_rows = []
    t0_global = time.time()
    halted = False
    halt_reason = ""
    batches_run = 0

    for batch_num in range(1, n_batches + 1):
        start_idx = (batch_num - 1) * BATCH_SIZE
        end_idx = min(start_idx + BATCH_SIZE, len(remaining))
        batch = remaining[start_idx:end_idx]

        print(f"\n{'='*50}")
        print(f"  BATCH {batch_num}/{n_batches} ({len(batch)} rows)")
        print(f"{'='*50}")

        batch_updated = 0
        batch_skipped = 0
        batch_errors = 0
        batch_revert = []
        batch_skipped_rows = []
        batch_output = []
        t0 = time.time()

        for i, row in enumerate(batch):
            ws_id = int(row['ws_id'])
            actual = int(row['actual_wine_id'])
            expected = int(row['expected_wine_id'])
            sp = f"sp_b{batch_num}_{i}"

            try:
                cur.execute(f"SAVEPOINT {sp}")
                snapshot = snapshot_row(cur, ws_id)

                if not snapshot:
                    status, motivo = 'skipped', 'ws_id nao encontrado'
                else:
                    status, motivo = validate_and_update(cur, row, snapshot)

                if status == 'updated':
                    cur.execute(f"RELEASE SAVEPOINT {sp}")
                    batch_updated += 1
                    rv = {
                        'ws_id': ws_id, 'old_wine_id': actual, 'new_wine_id': expected,
                        'store_id': snapshot['store_id'], 'url': snapshot['url'],
                        'preco': snapshot['preco'], 'moeda': snapshot['moeda'],
                        'disponivel': snapshot['disponivel'],
                        'descoberto_em': snapshot['descoberto_em'],
                        'atualizado_em': snapshot['atualizado_em'],
                    }
                    batch_revert.append(rv)
                else:
                    cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
                    cur.execute(f"RELEASE SAVEPOINT {sp}")
                    if status == 'error':
                        batch_errors += 1
                    else:
                        batch_skipped += 1
                    batch_skipped_rows.append({
                        'ws_id': ws_id, 'actual_wine_id': actual,
                        'expected_wine_id': expected,
                        'url': row.get('url', ''),
                        'store_id': row.get('store_id', ''),
                        'status': status, 'motivo': motivo,
                    })

                batch_output.append({
                    'ws_id': ws_id, 'actual_wine_id': actual,
                    'expected_wine_id': expected,
                    'store_id': snapshot['store_id'] if snapshot else row.get('store_id', ''),
                    'url': snapshot['url'] if snapshot else row.get('url', ''),
                    'status': status, 'motivo': motivo,
                })

                # Log a cada 50 ou no final
                if (i + 1) % 50 == 0 or (i + 1) == len(batch):
                    elapsed_b = time.time() - t0
                    print(f"    [{i+1:3d}/{len(batch)}] updated={batch_updated} skipped={batch_skipped} errors={batch_errors} ({elapsed_b:.1f}s)")

            except Exception as e:
                try:
                    cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
                    cur.execute(f"RELEASE SAVEPOINT {sp}")
                except:
                    pass
                batch_errors += 1
                batch_skipped_rows.append({
                    'ws_id': ws_id, 'actual_wine_id': actual,
                    'expected_wine_id': expected,
                    'url': row.get('url', ''), 'store_id': row.get('store_id', ''),
                    'status': 'error', 'motivo': str(e)[:200],
                })
                batch_output.append({
                    'ws_id': ws_id, 'actual_wine_id': actual,
                    'expected_wine_id': expected,
                    'store_id': row.get('store_id', ''),
                    'url': row.get('url', ''),
                    'status': 'error', 'motivo': str(e)[:200],
                })

        elapsed_batch = time.time() - t0

        # COMMIT do batch
        conn.commit()
        print(f"  COMMIT batch {batch_num} OK.")

        # Gravar CSVs do batch
        write_batch_csvs(batch_num, batch_output, batch_revert, batch_skipped_rows)

        # Acumular
        total_updated += batch_updated
        total_skipped += batch_skipped
        total_errors += batch_errors
        all_revert.extend(batch_revert)
        all_skipped.extend(batch_skipped_rows)
        all_batch_rows.extend(batch_output)
        batches_run += 1

        skip_pct = batch_skipped / len(batch) if len(batch) > 0 else 0

        print(f"\n  Batch {batch_num} resumo:")
        print(f"    Updated: {batch_updated}/{len(batch)}")
        print(f"    Skipped: {batch_skipped} ({skip_pct*100:.1f}%)")
        print(f"    Errors:  {batch_errors}")
        print(f"    Tempo:   {elapsed_batch:.1f}s ({elapsed_batch/len(batch)*1000:.0f}ms/caso)")

        # Guardrails
        if batch_errors > MAX_ERRORS:
            halted = True
            halt_reason = f"Erros no batch {batch_num}: {batch_errors}"
            print(f"\n  !!! GUARDRAIL: {halt_reason}. PARANDO.")
            break

        if skip_pct > MAX_SKIP_PCT:
            halted = True
            halt_reason = f"Skip rate no batch {batch_num}: {skip_pct*100:.1f}% > {MAX_SKIP_PCT*100:.1f}%"
            print(f"\n  !!! GUARDRAIL: {halt_reason}. PARANDO.")
            break

    elapsed_global = time.time() - t0_global

    # -----------------------------------------------------------------------
    # Consolidar revert de todos os batches
    # -----------------------------------------------------------------------
    consolidated_revert = os.path.join(DIR, 'wrong_owner_move_needed_batch_all_revert.csv')
    with open(consolidated_revert, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=REVERT_FIELDS, extrasaction='ignore')
        w.writeheader()
        w.writerows(all_revert)

    consolidated_skipped = os.path.join(DIR, 'wrong_owner_move_needed_batch_all_skipped.csv')
    with open(consolidated_skipped, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=SKIPPED_FIELDS, extrasaction='ignore')
        w.writeheader()
        w.writerows(all_skipped)

    # -----------------------------------------------------------------------
    # Validacao pos-UPDATE: 20 exemplos
    # -----------------------------------------------------------------------
    print(f"\n[3] Validacao pos-UPDATE (20 exemplos)...\n")
    sample = all_revert[:20] if len(all_revert) >= 20 else all_revert
    verified_ok = 0
    for rv in sample:
        cur.execute("SELECT wine_id, url FROM wine_sources WHERE id = %s", (rv['ws_id'],))
        db = cur.fetchone()
        if db and db[0] == rv['new_wine_id']:
            verified_ok += 1
            print(f"  ws_id={rv['ws_id']:>8d} expected={rv['new_wine_id']:>8d} db={db[0]:>8d} [OK] url={str(db[1])[:60]}")
        elif db:
            print(f"  ws_id={rv['ws_id']:>8d} expected={rv['new_wine_id']:>8d} db={db[0]:>8d} [MISMATCH]")
        else:
            print(f"  ws_id={rv['ws_id']:>8d} NOT FOUND!")

    # Verificar owner errado perdeu link
    print(f"\n  Verificando actual perdeu link (5 exemplos)...")
    for rv in all_revert[:5]:
        cur.execute("SELECT COUNT(*) FROM wine_sources WHERE id = %s AND wine_id = %s",
                    (rv['ws_id'], rv['old_wine_id']))
        still = cur.fetchone()[0]
        tag = 'PERDEU' if still == 0 else 'AINDA TEM!'
        print(f"  ws_id={rv['ws_id']} actual={rv['old_wine_id']} -> {tag}")

    cur.close()
    conn.close()

    # -----------------------------------------------------------------------
    # Resumo final
    # -----------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("RESUMO FINAL — CLASSE B BATCH COMPLETO")
    print("=" * 70)
    print(f"  Remanescente previsto:      4,058")
    print(f"  Remanescente real:          {len(remaining)}")
    print(f"  Batches executados:         {batches_run}/{n_batches}")
    print(f"  Total atualizado (UPDATE):  {total_updated}")
    print(f"  Total skipped:              {total_skipped}")
    print(f"  Total erros:                {total_errors}")
    print(f"  Tempo total:                {elapsed_global:.1f}s ({elapsed_global/60:.1f}min)")
    if halted:
        print(f"  PARADA ANTECIPADA:          {halt_reason}")
    print(f"\n  Verificados pos-UPDATE:     {verified_ok}/{len(sample)} OK")
    print(f"\n  Saldo final:")
    print(f"    safe restante:            {4158 - 100 - total_updated}")
    print(f"    ambiguous:                43")
    print(f"    incomplete:               606")
    print(f"    stale/skipped (novo):     {total_skipped}")
    print(f"\n  Arquivos consolidados:")
    print(f"    {consolidated_revert} ({len(all_revert)} linhas)")
    print(f"    {consolidated_skipped} ({len(all_skipped)} linhas)")
    print(f"    + {batches_run} x 3 CSVs por batch")
    print(f"\n  INSTRUCAO DE REVERT CONSOLIDADA:")
    print(f"  Usar {os.path.basename(consolidated_revert)} e executar para cada linha:")
    print(f"    UPDATE wine_sources SET wine_id = <old_wine_id>")
    print(f"    WHERE id = <ws_id> AND wine_id = <new_wine_id>;")
    print()


if __name__ == '__main__':
    main()
