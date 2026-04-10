"""
wrong_owner_classe_b_pilot_100.py
==================================
Piloto de 100 casos da Classe B (move_needed_safe).
Operacao: UPDATE wine_sources SET wine_id = expected WHERE id = ws_id AND wine_id = actual.
Nenhum DELETE. Nenhum INSERT. Revert lossless via CSV.

Uso:
    python scripts/wrong_owner_classe_b_pilot_100.py
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
PILOT_SIZE = 100

# Output files
PILOT_CSV = os.path.join(DIR, 'wrong_owner_move_needed_pilot_100.csv')
REVERT_CSV = os.path.join(DIR, 'wrong_owner_move_needed_pilot_100_revert.csv')
SKIPPED_CSV = os.path.join(DIR, 'wrong_owner_move_needed_pilot_100_skipped.csv')


def select_pilot_rows(safe_csv, n=100):
    """
    Seleciona 100 rows do safe CSV com diversidade:
    - Priorizar rows COM store_id (hybrid/sql) para facilitar validacao
    - Misturar fontes
    - Evitar repeticao de actual/expected
    """
    with open(safe_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        all_rows = list(reader)

    # Separar por fonte e presenca de store_id
    with_store = [r for r in all_rows if r.get('store_id', '').strip()]
    without_store = [r for r in all_rows if not r.get('store_id', '').strip()]

    print(f"  Safe total: {len(all_rows)}")
    print(f"    Com store_id no CSV: {len(with_store)}")
    print(f"    Sem store_id no CSV: {len(without_store)}")

    # Selecionar com diversidade: pegar de with_store primeiro, depois completar
    selected = []
    seen_actual = set()
    seen_expected = set()

    # Primeiro pass: diversidade maxima (nao repetir actual nem expected)
    for r in with_store:
        if len(selected) >= n:
            break
        a = r['actual_wine_id']
        e = r['expected_wine_id']
        if a not in seen_actual and e not in seen_expected:
            selected.append(r)
            seen_actual.add(a)
            seen_expected.add(e)

    # Se nao completou, relaxar restricao
    if len(selected) < n:
        for r in with_store:
            if len(selected) >= n:
                break
            if r not in selected:
                selected.append(r)

    # Se ainda nao completou, pegar de without_store
    if len(selected) < n:
        for r in without_store:
            if len(selected) >= n:
                break
            selected.append(r)

    print(f"  Selecionados para piloto: {len(selected)}")
    return selected


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
    """Captura snapshot completo da row antes do UPDATE."""
    cur.execute("""
        SELECT id, wine_id, store_id, url, preco, moeda, disponivel,
               descoberto_em, atualizado_em
        FROM wine_sources
        WHERE id = %s
    """, (ws_id,))
    row = cur.fetchone()
    if row:
        return {
            'ws_id': row[0],
            'wine_id': row[1],
            'store_id': row[2],
            'url': row[3],
            'preco': row[4],
            'moeda': row[5],
            'disponivel': row[6],
            'descoberto_em': row[7],
            'atualizado_em': row[8],
        }
    return None


def validate_and_update(cur, row, snapshot):
    """
    Valida e executa UPDATE atomico com guard clause + NOT EXISTS.
    Retorna (status, motivo).
    """
    ws_id = int(row['ws_id'])
    actual = int(row['actual_wine_id'])
    expected = int(row['expected_wine_id'])
    store_id = snapshot['store_id']
    url = snapshot['url']

    # Check 1: ws_id ainda pertence ao actual_wine_id
    if snapshot['wine_id'] != actual:
        return 'skipped', f'wine_id mudou: era {actual}, agora {snapshot["wine_id"]}'

    # Check 2: url bate com o esperado (se temos url no CSV)
    csv_url = row.get('url', '').strip()
    if csv_url and csv_url != url:
        return 'skipped', f'url diverge: csv={csv_url[:60]} db={url[:60] if url else "NULL"}'

    # Check 3: store_id bate (se temos no CSV)
    csv_store = row.get('store_id', '').strip()
    if csv_store and str(store_id) != csv_store:
        return 'skipped', f'store_id diverge: csv={csv_store} db={store_id}'

    # Check 4: expected_wine_id existe
    cur.execute("SELECT 1 FROM wines WHERE id = %s", (expected,))
    if not cur.fetchone():
        return 'skipped', f'expected_wine_id {expected} nao existe no banco'

    # UPDATE atomico com guard clause + NOT EXISTS
    cur.execute("""
        UPDATE wine_sources
        SET wine_id = %s
        WHERE id = %s
          AND wine_id = %s
          AND NOT EXISTS (
              SELECT 1
              FROM wine_sources w2
              WHERE w2.wine_id = %s
                AND w2.store_id = %s
                AND w2.url = %s
          )
    """, (expected, ws_id, actual, expected, store_id, url))

    if cur.rowcount == 1:
        return 'updated', 'ok'
    elif cur.rowcount == 0:
        # Determinar por que nao atualizou
        cur.execute("SELECT wine_id FROM wine_sources WHERE id = %s", (ws_id,))
        check = cur.fetchone()
        if not check:
            return 'skipped', 'ws_id nao existe mais'
        if check[0] != actual:
            return 'skipped', f'wine_id ja mudou para {check[0]}'
        # NOT EXISTS falhou = ja existe no expected
        cur.execute("""
            SELECT id FROM wine_sources
            WHERE wine_id = %s AND store_id = %s AND url = %s
        """, (expected, store_id, url))
        dup = cur.fetchone()
        if dup:
            return 'skipped', f'link ja existe no expected (ws_id={dup[0]})'
        return 'skipped', 'rowcount=0 por razao desconhecida'
    else:
        return 'error', f'rowcount inesperado: {cur.rowcount}'


def main():
    print("=" * 70)
    print("PILOTO 100 — CLASSE B (move_needed_safe)")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 70)

    # Selecionar 100
    print("\n[1/4] Selecionando candidatos...")
    pilot_rows = select_pilot_rows(SAFE_CSV, PILOT_SIZE)

    # Conectar
    print("\n[2/4] Conectando ao Render...")
    conn = connect_render()
    cur = conn.cursor()
    print("  Conectado.")

    # Executar
    print(f"\n[3/4] Executando piloto de {len(pilot_rows)} casos...\n")

    revert_rows = []
    skipped_rows = []
    updated_count = 0
    skipped_count = 0
    error_count = 0
    t0 = time.time()

    REVERT_FIELDS = ['ws_id', 'old_wine_id', 'new_wine_id', 'store_id', 'url',
                     'preco', 'moeda', 'disponivel', 'descoberto_em', 'atualizado_em']
    SKIPPED_FIELDS = ['ws_id', 'actual_wine_id', 'expected_wine_id', 'url',
                      'store_id', 'status', 'motivo']
    PILOT_FIELDS = ['ws_id', 'actual_wine_id', 'expected_wine_id', 'store_id',
                    'url', 'clean_id', 'origem_csv', 'status', 'motivo']

    pilot_output = []

    for i, row in enumerate(pilot_rows):
        ws_id = int(row['ws_id'])
        actual = int(row['actual_wine_id'])
        expected = int(row['expected_wine_id'])

        try:
            # SAVEPOINT por linha
            cur.execute(f"SAVEPOINT sp_{i}")

            # Snapshot antes do UPDATE
            snapshot = snapshot_row(cur, ws_id)
            if not snapshot:
                status, motivo = 'skipped', 'ws_id nao encontrado no banco'
            else:
                status, motivo = validate_and_update(cur, row, snapshot)

            if status == 'updated':
                cur.execute(f"RELEASE SAVEPOINT sp_{i}")
                updated_count += 1
                revert_rows.append({
                    'ws_id': ws_id,
                    'old_wine_id': actual,
                    'new_wine_id': expected,
                    'store_id': snapshot['store_id'],
                    'url': snapshot['url'],
                    'preco': snapshot['preco'],
                    'moeda': snapshot['moeda'],
                    'disponivel': snapshot['disponivel'],
                    'descoberto_em': snapshot['descoberto_em'],
                    'atualizado_em': snapshot['atualizado_em'],
                })
            elif status == 'skipped':
                cur.execute(f"ROLLBACK TO SAVEPOINT sp_{i}")
                cur.execute(f"RELEASE SAVEPOINT sp_{i}")
                skipped_count += 1
                skipped_rows.append({
                    'ws_id': ws_id,
                    'actual_wine_id': actual,
                    'expected_wine_id': expected,
                    'url': row.get('url', ''),
                    'store_id': row.get('store_id', ''),
                    'status': status,
                    'motivo': motivo,
                })
            else:
                cur.execute(f"ROLLBACK TO SAVEPOINT sp_{i}")
                cur.execute(f"RELEASE SAVEPOINT sp_{i}")
                error_count += 1
                skipped_rows.append({
                    'ws_id': ws_id,
                    'actual_wine_id': actual,
                    'expected_wine_id': expected,
                    'url': row.get('url', ''),
                    'store_id': row.get('store_id', ''),
                    'status': status,
                    'motivo': motivo,
                })

            tag = 'OK' if status == 'updated' else 'SKIP'
            print(f"  [{i+1:3d}/{len(pilot_rows)}] ws_id={ws_id} {actual}->{expected} [{tag}] {motivo}")

            pilot_output.append({
                'ws_id': ws_id,
                'actual_wine_id': actual,
                'expected_wine_id': expected,
                'store_id': snapshot['store_id'] if snapshot else row.get('store_id', ''),
                'url': snapshot['url'] if snapshot else row.get('url', ''),
                'clean_id': row.get('clean_id', ''),
                'origem_csv': row.get('origem_csv', ''),
                'status': status,
                'motivo': motivo,
            })

        except Exception as e:
            try:
                cur.execute(f"ROLLBACK TO SAVEPOINT sp_{i}")
                cur.execute(f"RELEASE SAVEPOINT sp_{i}")
            except:
                pass
            error_count += 1
            print(f"  [{i+1:3d}/{len(pilot_rows)}] ws_id={ws_id} ERROR: {e}")
            skipped_rows.append({
                'ws_id': ws_id,
                'actual_wine_id': actual,
                'expected_wine_id': expected,
                'url': row.get('url', ''),
                'store_id': row.get('store_id', ''),
                'status': 'error',
                'motivo': str(e)[:200],
            })
            pilot_output.append({
                'ws_id': ws_id,
                'actual_wine_id': actual,
                'expected_wine_id': expected,
                'store_id': row.get('store_id', ''),
                'url': row.get('url', ''),
                'clean_id': row.get('clean_id', ''),
                'origem_csv': row.get('origem_csv', ''),
                'status': 'error',
                'motivo': str(e)[:200],
            })

    elapsed = time.time() - t0

    # COMMIT
    print(f"\n  Fazendo COMMIT...")
    conn.commit()
    print(f"  COMMIT OK.")

    # -----------------------------------------------------------------------
    # Validacao pos-UPDATE: verificar 20 exemplos
    # -----------------------------------------------------------------------
    print(f"\n[4/4] Validacao pos-UPDATE (20 exemplos)...\n")

    verified = []
    sample = revert_rows[:20]
    for rv in sample:
        cur.execute("""
            SELECT ws.wine_id, ws.store_id, ws.url
            FROM wine_sources ws
            WHERE ws.id = %s
        """, (rv['ws_id'],))
        db = cur.fetchone()
        if db:
            ok = db[0] == rv['new_wine_id']
            verified.append({
                'ws_id': rv['ws_id'],
                'expected_wine_id': rv['new_wine_id'],
                'db_wine_id': db[0],
                'match': ok,
                'store_id': db[1],
                'url': (db[2] or '')[:70],
            })
            tag = 'OK' if ok else 'MISMATCH'
            print(f"  ws_id={rv['ws_id']:>8d} expected={rv['new_wine_id']:>8d} db={db[0]:>8d} [{tag}] url={db[2][:60] if db[2] else 'NULL'}")
        else:
            verified.append({
                'ws_id': rv['ws_id'],
                'expected_wine_id': rv['new_wine_id'],
                'db_wine_id': None,
                'match': False,
            })
            print(f"  ws_id={rv['ws_id']:>8d} NOT FOUND!")

    # Verificar que owner errado perdeu o link
    print(f"\n  Verificando que actual_wine_id perdeu o link (5 exemplos)...")
    for rv in revert_rows[:5]:
        cur.execute("""
            SELECT COUNT(*) FROM wine_sources
            WHERE id = %s AND wine_id = %s
        """, (rv['ws_id'], rv['old_wine_id']))
        still_there = cur.fetchone()[0]
        lost = 'PERDEU' if still_there == 0 else 'AINDA TEM!'
        print(f"  ws_id={rv['ws_id']} actual={rv['old_wine_id']} -> {lost}")

    cur.close()
    conn.close()

    # -----------------------------------------------------------------------
    # Gravar CSVs
    # -----------------------------------------------------------------------
    print(f"\n  Gravando CSVs...")

    with open(PILOT_CSV, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=PILOT_FIELDS, extrasaction='ignore')
        w.writeheader()
        w.writerows(pilot_output)
    print(f"  -> {os.path.basename(PILOT_CSV)}: {len(pilot_output)} linhas")

    with open(REVERT_CSV, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=REVERT_FIELDS, extrasaction='ignore')
        w.writeheader()
        w.writerows(revert_rows)
    print(f"  -> {os.path.basename(REVERT_CSV)}: {len(revert_rows)} linhas")

    with open(SKIPPED_CSV, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=SKIPPED_FIELDS, extrasaction='ignore')
        w.writeheader()
        w.writerows(skipped_rows)
    print(f"  -> {os.path.basename(SKIPPED_CSV)}: {len(skipped_rows)} linhas")

    # -----------------------------------------------------------------------
    # Resumo
    # -----------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("RESUMO DO PILOTO 100")
    print("=" * 70)
    print(f"  Candidatos no piloto:   {len(pilot_rows)}")
    print(f"  Atualizados (UPDATE):   {updated_count}")
    print(f"  Pulados (skipped):      {skipped_count}")
    print(f"  Erros:                  {error_count}")
    print(f"  Tempo total:            {elapsed:.1f}s ({elapsed/len(pilot_rows)*1000:.0f}ms/caso)")
    print(f"\n  Verificados pos-UPDATE: {sum(1 for v in verified if v['match'])}/{len(verified)} OK")
    print(f"\n  Arquivos gerados:")
    print(f"    {PILOT_CSV}")
    print(f"    {REVERT_CSV}")
    print(f"    {SKIPPED_CSV}")
    print(f"\n  INSTRUCAO DE REVERT:")
    print(f"  Para desfazer TODOS os updates deste piloto:")
    print(f"  Usar o CSV {os.path.basename(REVERT_CSV)} e executar, para cada linha:")
    print(f"    UPDATE wine_sources SET wine_id = <old_wine_id>")
    print(f"    WHERE id = <ws_id> AND wine_id = <new_wine_id>;")
    print()


if __name__ == '__main__':
    main()
