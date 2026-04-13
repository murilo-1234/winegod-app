"""
consolidar_wrong_owner_artifacts.py
====================================
Consolida todos os CSVs produzidos pelo pipeline wrong_owner em 4 artefatos
deduplicados. Funciona tanto durante o run (snapshot parcial) quanto depois.

Uso:
    python scripts/consolidar_wrong_owner_artifacts.py [--dir SCRIPTS_DIR] [--suffix _parcial]

Saida (no mesmo diretorio):
    wrong_owner_move_needed_consolidado{suffix}.csv
    wrong_owner_ambiguous_consolidado{suffix}.csv
    wrong_owner_revert_manifest{suffix}.csv
    wrong_owner_exec_manifest{suffix}.csv
"""

import argparse
import csv
import glob
import os
import re
import sys
from collections import OrderedDict
from datetime import datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RANGE_RE = re.compile(r'_(\d+)_(\d+)')

def extract_range(filename: str):
    """Extrai (start, end) do nome do arquivo, ou (None, None)."""
    m = RANGE_RE.search(os.path.basename(filename))
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def read_csv_rows(path: str) -> list[dict]:
    """Le CSV inteiro como lista de dicts. Retorna [] se vazio ou so header."""
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            reader = csv.DictReader(f)
            return list(reader)
    except Exception as e:
        print(f"  [WARN] Erro lendo {os.path.basename(path)}: {e}")
        return []


def dedup_by_key(rows: list[dict], key: str) -> list[dict]:
    """Deduplica mantendo a primeira ocorrencia por chave."""
    seen = OrderedDict()
    for r in rows:
        k = r.get(key)
        if k and k not in seen:
            seen[k] = r
    return list(seen.values())


def write_csv(path: str, rows: list[dict], fieldnames: list[str]):
    """Escreve CSV com header explicito."""
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)
    print(f"  -> {os.path.basename(path)}: {len(rows)} linhas")


# ---------------------------------------------------------------------------
# Coletores por tipo
# ---------------------------------------------------------------------------

def collect_b_rows(scripts_dir: str) -> tuple[list[dict], dict]:
    """
    Coleta todas as linhas Classe B (move_needed) de todas as fases.
    Normaliza colunas para: ws_id, actual_wine_id, expected_wine_id, store_id, url, clean_id
    Retorna (rows, stats).
    """
    rows = []
    stats = {
        'wo_move_needed': {'files': 0, 'rows': 0, 'ranges': []},
        'wo_hybrid_b': {'files': 0, 'rows': 0, 'ranges': []},
        'wo_sql_b': {'files': 0, 'rows': 0, 'ranges': []},
        'wrong_owner_move_needed_candidates': {'files': 0, 'rows': 0, 'ranges': []},
        'wrong_owner_pilot_candidates': {'files': 0, 'rows': 0, 'ranges': []},
    }

    # 1) wo_move_needed_{start}_{end}.csv  (fase del, owners 501-50500)
    for f in sorted(glob.glob(os.path.join(scripts_dir, 'wo_move_needed_*.csv'))):
        data = read_csv_rows(f)
        s, e = extract_range(f)
        stats['wo_move_needed']['files'] += 1
        stats['wo_move_needed']['rows'] += len(data)
        if s: stats['wo_move_needed']['ranges'].append((s, e))
        for r in data:
            rows.append({
                'ws_id': r.get('ws_id', ''),
                'actual_wine_id': r.get('actual_wine_id', ''),
                'expected_wine_id': r.get('expected_wine_id', ''),
                'store_id': r.get('store_id', ''),
                'url': r.get('url', ''),
                'clean_id': r.get('clean_id', ''),
            })

    # 2) wo_hybrid_b_{start}_{end}.csv  (fase hybrid, owners 52501+)
    for f in sorted(glob.glob(os.path.join(scripts_dir, 'wo_hybrid_b_*.csv'))):
        data = read_csv_rows(f)
        s, e = extract_range(f)
        stats['wo_hybrid_b']['files'] += 1
        stats['wo_hybrid_b']['rows'] += len(data)
        if s: stats['wo_hybrid_b']['ranges'].append((s, e))
        for r in data:
            rows.append({
                'ws_id': r.get('ws_id', ''),
                'actual_wine_id': r.get('actual', r.get('actual_wine_id', '')),
                'expected_wine_id': r.get('expected', r.get('expected_wine_id', '')),
                'store_id': r.get('store_id', ''),
                'url': r.get('url', ''),
                'clean_id': r.get('cid', r.get('clean_id', '')),
            })

    # 3) wo_sql_b_{start}_{end}.csv  (fase sql, owners 114501+)
    for f in sorted(glob.glob(os.path.join(scripts_dir, 'wo_sql_b_*.csv'))):
        data = read_csv_rows(f)
        s, e = extract_range(f)
        stats['wo_sql_b']['files'] += 1
        stats['wo_sql_b']['rows'] += len(data)
        if s: stats['wo_sql_b']['ranges'].append((s, e))
        for r in data:
            rows.append({
                'ws_id': r.get('ws_id', ''),
                'actual_wine_id': r.get('actual_wine_id', ''),
                'expected_wine_id': r.get('expected_wine_id', ''),
                'store_id': r.get('store_id', ''),
                'url': r.get('url', ''),
                'clean_id': r.get('clean_id', ''),
            })

    # 4) wrong_owner_move_needed_candidates.csv  (fase inicial)
    p = os.path.join(scripts_dir, 'wrong_owner_move_needed_candidates.csv')
    if os.path.exists(p):
        data = read_csv_rows(p)
        stats['wrong_owner_move_needed_candidates']['files'] += 1
        stats['wrong_owner_move_needed_candidates']['rows'] += len(data)
        for r in data:
            rows.append({
                'ws_id': r.get('ws_id', ''),
                'actual_wine_id': r.get('actual_wine_id', ''),
                'expected_wine_id': r.get('expected_wine_id', ''),
                'store_id': r.get('store_id', ''),
                'url': r.get('url', ''),
                'clean_id': r.get('clean_id', ''),
            })

    # 5) wrong_owner_pilot_candidates.csv  (piloto)
    p = os.path.join(scripts_dir, 'wrong_owner_pilot_candidates.csv')
    if os.path.exists(p):
        data = read_csv_rows(p)
        stats['wrong_owner_pilot_candidates']['files'] += 1
        stats['wrong_owner_pilot_candidates']['rows'] += len(data)
        for r in data:
            rows.append({
                'ws_id': r.get('ws_id', ''),
                'actual_wine_id': r.get('actual_wine_id', ''),
                'expected_wine_id': r.get('expected_wine_id', ''),
                'store_id': r.get('store_id', ''),
                'url': r.get('url', ''),
                'clean_id': r.get('clean_id', ''),
            })

    return rows, stats


def collect_c_rows(scripts_dir: str) -> tuple[list[dict], dict]:
    """Coleta Classe C (ambiguous) de todas as fases."""
    rows = []
    stats = {
        'wo_hybrid_c': {'files': 0, 'rows': 0, 'ranges': []},
        'wrong_owner_ambiguous_candidates': {'files': 0, 'rows': 0, 'ranges': []},
    }

    # wo_hybrid_c_{start}_{end}.csv
    for f in sorted(glob.glob(os.path.join(scripts_dir, 'wo_hybrid_c_*.csv'))):
        data = read_csv_rows(f)
        s, e = extract_range(f)
        stats['wo_hybrid_c']['files'] += 1
        stats['wo_hybrid_c']['rows'] += len(data)
        if s: stats['wo_hybrid_c']['ranges'].append((s, e))
        for r in data:
            rows.append({
                'ws_id': r.get('ws_id', ''),
                'actual_wine_id': r.get('actual', r.get('actual_wine_id', '')),
                'expected_wine_id': r.get('expected', r.get('expected_wine_id', '')),
                'store_id': r.get('store_id', ''),
                'url': r.get('url', ''),
                'clean_id': r.get('cid', r.get('clean_id', '')),
            })

    # wrong_owner_ambiguous_candidates.csv
    p = os.path.join(scripts_dir, 'wrong_owner_ambiguous_candidates.csv')
    if os.path.exists(p):
        data = read_csv_rows(p)
        stats['wrong_owner_ambiguous_candidates']['files'] += 1
        stats['wrong_owner_ambiguous_candidates']['rows'] += len(data)
        for r in data:
            rows.append({
                'ws_id': r.get('ws_id', ''),
                'actual_wine_id': r.get('actual_wine_id', ''),
                'expected_wine_id': r.get('expected_wine_id', ''),
                'store_id': r.get('store_id', ''),
                'url': r.get('url', ''),
                'clean_id': r.get('clean_id', ''),
            })

    return rows, stats


def collect_revert_rows(scripts_dir: str) -> tuple[list[dict], dict]:
    """Coleta todos os manifestos de revert."""
    rows = []
    stats = {
        'wo_del_revert': {'files': 0, 'rows': 0, 'ranges': []},
        'wo_hybrid_rev': {'files': 0, 'rows': 0, 'ranges': []},
        'wo_sql_rev': {'files': 0, 'rows': 0, 'ranges': []},
        'wrong_owner_delete_only_revert': {'files': 0, 'rows': 0, 'ranges': []},
        'wrong_owner_pilot_100_revert': {'files': 0, 'rows': 0, 'ranges': []},
    }

    # Campos normalizados para revert
    def norm(r):
        return {
            'ws_id': r.get('ws_id', ''),
            'wine_id': r.get('actual_wine_id', r.get('wine_id', r.get('wine_id_errado', ''))),
            'store_id': r.get('store_id', ''),
            'url': r.get('url', ''),
            'preco': r.get('ws_preco', r.get('preco', '')),
            'moeda': r.get('ws_moeda', r.get('moeda', '')),
            'disponivel': r.get('ws_disponivel', r.get('disponivel', '')),
            'descoberto_em': r.get('ws_descoberto_em', r.get('descoberto_em', '')),
            'atualizado_em': r.get('ws_atualizado_em', r.get('atualizado_em', '')),
        }

    # wo_del_revert
    for f in sorted(glob.glob(os.path.join(scripts_dir, 'wo_del_revert_*.csv'))):
        data = read_csv_rows(f)
        s, e = extract_range(f)
        stats['wo_del_revert']['files'] += 1
        stats['wo_del_revert']['rows'] += len(data)
        if s: stats['wo_del_revert']['ranges'].append((s, e))
        rows.extend(norm(r) for r in data)

    # wo_hybrid_rev
    for f in sorted(glob.glob(os.path.join(scripts_dir, 'wo_hybrid_rev_*.csv'))):
        data = read_csv_rows(f)
        s, e = extract_range(f)
        stats['wo_hybrid_rev']['files'] += 1
        stats['wo_hybrid_rev']['rows'] += len(data)
        if s: stats['wo_hybrid_rev']['ranges'].append((s, e))
        for r in data:
            rows.append({
                'ws_id': r.get('ws_id', ''),
                'wine_id': r.get('actual', r.get('wine_id', '')),
                'store_id': r.get('store_id', ''),
                'url': r.get('url', ''),
                'preco': r.get('preco', ''),
                'moeda': r.get('moeda', ''),
                'disponivel': r.get('disponivel', ''),
                'descoberto_em': r.get('descoberto_em', ''),
                'atualizado_em': r.get('atualizado_em', ''),
            })

    # wo_sql_rev
    for f in sorted(glob.glob(os.path.join(scripts_dir, 'wo_sql_rev_*.csv'))):
        data = read_csv_rows(f)
        s, e = extract_range(f)
        stats['wo_sql_rev']['files'] += 1
        stats['wo_sql_rev']['rows'] += len(data)
        if s: stats['wo_sql_rev']['ranges'].append((s, e))
        for r in data:
            rows.append({
                'ws_id': r.get('ws_id', ''),
                'wine_id': r.get('wine_id', ''),
                'store_id': r.get('store_id', ''),
                'url': r.get('url', ''),
                'preco': r.get('preco', ''),
                'moeda': r.get('moeda', ''),
                'disponivel': r.get('disponivel', ''),
                'descoberto_em': r.get('descoberto_em', ''),
                'atualizado_em': r.get('atualizado_em', ''),
            })

    # wrong_owner_delete_only_revert.csv
    p = os.path.join(scripts_dir, 'wrong_owner_delete_only_revert.csv')
    if os.path.exists(p):
        data = read_csv_rows(p)
        stats['wrong_owner_delete_only_revert']['files'] += 1
        stats['wrong_owner_delete_only_revert']['rows'] += len(data)
        rows.extend(norm(r) for r in data)

    # wrong_owner_pilot_100_revert.csv
    p = os.path.join(scripts_dir, 'wrong_owner_pilot_100_revert.csv')
    if os.path.exists(p):
        data = read_csv_rows(p)
        stats['wrong_owner_pilot_100_revert']['files'] += 1
        stats['wrong_owner_pilot_100_revert']['rows'] += len(data)
        for r in data:
            rows.append({
                'ws_id': r.get('ws_id', ''),
                'wine_id': r.get('wine_id_errado', r.get('wine_id', '')),
                'store_id': r.get('store_id', ''),
                'url': r.get('url', ''),
                'preco': r.get('preco', ''),
                'moeda': r.get('moeda', ''),
                'disponivel': r.get('disponivel', ''),
                'descoberto_em': r.get('descoberto_em', ''),
                'atualizado_em': r.get('atualizado_em', ''),
            })

    return rows, stats


def collect_exec_rows(scripts_dir: str) -> tuple[list[dict], dict]:
    """Coleta todos os manifestos de execucao (deletes efetivados)."""
    rows = []
    stats = {
        'wo_del_executed': {'files': 0, 'rows': 0, 'ranges': []},
        'wrong_owner_delete_only_executed': {'files': 0, 'rows': 0, 'ranges': []},
    }

    # Campos normalizados
    def norm(r):
        return {
            'ws_id': r.get('ws_id', ''),
            'actual_wine_id': r.get('actual_wine_id', ''),
            'expected_wine_id': r.get('expected_wine_id', ''),
            'store_id': r.get('store_id', ''),
            'url': r.get('url', ''),
            'clean_id': r.get('clean_id', ''),
        }

    # wo_del_executed
    for f in sorted(glob.glob(os.path.join(scripts_dir, 'wo_del_executed_*.csv'))):
        data = read_csv_rows(f)
        s, e = extract_range(f)
        stats['wo_del_executed']['files'] += 1
        stats['wo_del_executed']['rows'] += len(data)
        if s: stats['wo_del_executed']['ranges'].append((s, e))
        rows.extend(norm(r) for r in data)

    # wrong_owner_delete_only_executed.csv
    p = os.path.join(scripts_dir, 'wrong_owner_delete_only_executed.csv')
    if os.path.exists(p):
        data = read_csv_rows(p)
        stats['wrong_owner_delete_only_executed']['files'] += 1
        stats['wrong_owner_delete_only_executed']['rows'] += len(data)
        rows.extend(norm(r) for r in data)

    return rows, stats


# ---------------------------------------------------------------------------
# Analise de cobertura
# ---------------------------------------------------------------------------

def range_coverage(ranges: list[tuple]) -> dict:
    """Dado lista de (start, end), retorna min, max e gaps."""
    if not ranges:
        return {'min': None, 'max': None, 'gaps': []}
    sorted_r = sorted(ranges)
    gaps = []
    for i in range(1, len(sorted_r)):
        prev_end = sorted_r[i-1][1]
        curr_start = sorted_r[i][0]
        if curr_start > prev_end + 1:
            gaps.append((prev_end + 1, curr_start - 1))
    return {
        'min': sorted_r[0][0],
        'max': sorted_r[-1][1],
        'gaps': gaps,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Consolida artefatos wrong_owner')
    parser.add_argument('--dir', default=os.path.join(os.path.dirname(__file__)),
                        help='Diretorio dos CSVs (default: scripts/)')
    parser.add_argument('--suffix', default='_parcial',
                        help='Sufixo dos arquivos de saida (default: _parcial)')
    args = parser.parse_args()

    scripts_dir = os.path.abspath(args.dir)
    suffix = args.suffix

    print(f"=== Consolidacao wrong_owner ===")
    print(f"Diretorio: {scripts_dir}")
    print(f"Sufixo: {suffix}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()

    # --- Classe B (move_needed) ---
    print("[1/4] Coletando Classe B (move_needed)...")
    b_rows, b_stats = collect_b_rows(scripts_dir)
    b_dedup = dedup_by_key(b_rows, 'ws_id')
    b_fields = ['ws_id', 'actual_wine_id', 'expected_wine_id', 'store_id', 'url', 'clean_id']
    b_path = os.path.join(scripts_dir, f'wrong_owner_move_needed_consolidado{suffix}.csv')
    write_csv(b_path, b_dedup, b_fields)
    for src, st in b_stats.items():
        if st['files']:
            cov = range_coverage(st['ranges'])
            print(f"    {src}: {st['files']} files, {st['rows']} rows, range {cov['min']}-{cov['max']}")
    print(f"    Total bruto: {len(b_rows)}, dedup por ws_id: {len(b_dedup)}")
    print()

    # --- Classe C (ambiguous) ---
    print("[2/4] Coletando Classe C (ambiguous)...")
    c_rows, c_stats = collect_c_rows(scripts_dir)
    c_dedup = dedup_by_key(c_rows, 'ws_id')
    c_fields = ['ws_id', 'actual_wine_id', 'expected_wine_id', 'store_id', 'url', 'clean_id']
    c_path = os.path.join(scripts_dir, f'wrong_owner_ambiguous_consolidado{suffix}.csv')
    write_csv(c_path, c_dedup, c_fields)
    for src, st in c_stats.items():
        if st['files']:
            cov = range_coverage(st['ranges'])
            print(f"    {src}: {st['files']} files, {st['rows']} rows, range {cov['min']}-{cov['max']}")
    print(f"    Total bruto: {len(c_rows)}, dedup por ws_id: {len(c_dedup)}")
    print()

    # --- Revert manifest ---
    print("[3/4] Coletando revert manifests...")
    rev_rows, rev_stats = collect_revert_rows(scripts_dir)
    rev_dedup = dedup_by_key(rev_rows, 'ws_id')
    rev_fields = ['ws_id', 'wine_id', 'store_id', 'url', 'preco', 'moeda', 'disponivel', 'descoberto_em', 'atualizado_em']
    rev_path = os.path.join(scripts_dir, f'wrong_owner_revert_manifest{suffix}.csv')
    write_csv(rev_path, rev_dedup, rev_fields)
    for src, st in rev_stats.items():
        if st['files']:
            cov = range_coverage(st['ranges'])
            print(f"    {src}: {st['files']} files, {st['rows']} rows, range {cov['min']}-{cov['max']}")
    print(f"    Total bruto: {len(rev_rows)}, dedup por ws_id: {len(rev_dedup)}")
    print()

    # --- Exec manifest ---
    print("[4/4] Coletando exec manifests (deletes efetivados)...")
    exec_rows, exec_stats = collect_exec_rows(scripts_dir)
    exec_dedup = dedup_by_key(exec_rows, 'ws_id')
    exec_fields = ['ws_id', 'actual_wine_id', 'expected_wine_id', 'store_id', 'url', 'clean_id']
    exec_path = os.path.join(scripts_dir, f'wrong_owner_exec_manifest{suffix}.csv')
    write_csv(exec_path, exec_dedup, exec_fields)
    for src, st in exec_stats.items():
        if st['files']:
            cov = range_coverage(st['ranges'])
            print(f"    {src}: {st['files']} files, {st['rows']} rows, range {cov['min']}-{cov['max']}")
    print(f"    Total bruto: {len(exec_rows)}, dedup por ws_id: {len(exec_dedup)}")
    print()

    # --- Resumo ---
    print("=" * 60)
    print("RESUMO")
    print("=" * 60)
    total_csvs = sum(st['files'] for st in b_stats.values()) + \
                 sum(st['files'] for st in c_stats.values()) + \
                 sum(st['files'] for st in rev_stats.values()) + \
                 sum(st['files'] for st in exec_stats.values())
    print(f"CSVs lidos: {total_csvs}")
    print(f"Classe B (move_needed) dedup: {len(b_dedup)}")
    print(f"Classe C (ambiguous) dedup:   {len(c_dedup)}")
    print(f"Revert manifest dedup:        {len(rev_dedup)}")
    print(f"Exec manifest dedup:          {len(exec_dedup)}")
    print()

    # Cobertura geral
    all_del_ranges = b_stats['wo_move_needed']['ranges']  # fase del = 501-50500
    all_hybrid_ranges = b_stats['wo_hybrid_b']['ranges']  # fase hybrid = 52501-240500
    all_sql_ranges = b_stats['wo_sql_b']['ranges']        # fase sql = 114501-144500

    print("COBERTURA DE RANGES:")
    for name, ranges in [('del (500-step)', all_del_ranges),
                          ('hybrid (2000-step)', all_hybrid_ranges),
                          ('sql (5000-step)', all_sql_ranges)]:
        cov = range_coverage(ranges)
        if cov['min']:
            print(f"  {name}: owners {cov['min']}-{cov['max']}")
            if cov['gaps']:
                print(f"    GAPS: {cov['gaps']}")
            else:
                print(f"    Sem gaps")
        else:
            print(f"  {name}: nenhum arquivo")
    print()

    # Salvar stats como JSON para uso programatico
    import json
    stats_path = os.path.join(scripts_dir, f'wrong_owner_consolidation_stats{suffix}.json')
    stats_out = {
        'timestamp': datetime.now().isoformat(),
        'suffix': suffix,
        'total_csvs_read': total_csvs,
        'b_move_needed': {'bruto': len(b_rows), 'dedup': len(b_dedup), 'sources': {k: v for k, v in b_stats.items() if v['files']}},
        'c_ambiguous': {'bruto': len(c_rows), 'dedup': len(c_dedup), 'sources': {k: v for k, v in c_stats.items() if v['files']}},
        'revert': {'bruto': len(rev_rows), 'dedup': len(rev_dedup), 'sources': {k: v for k, v in rev_stats.items() if v['files']}},
        'exec': {'bruto': len(exec_rows), 'dedup': len(exec_dedup), 'sources': {k: v for k, v in exec_stats.items() if v['files']}},
    }
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(stats_out, f, indent=2, ensure_ascii=False, default=str)
    print(f"Stats salvas em: {os.path.basename(stats_path)}")


if __name__ == '__main__':
    main()
