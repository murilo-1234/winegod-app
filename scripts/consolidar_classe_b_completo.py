"""
consolidar_classe_b_completo.py
================================
Consolidacao rigorosa da Classe B (move_needed) para preparar execucao segura.

Etapa 1: Inventario + consolidacao + dedup + analise de cobertura/overlaps/divergencias
Etapa 2: Classificacao local (move_needed_safe / ambiguous / stale_or_already_fixed)

Uso:
    python scripts/consolidar_classe_b_completo.py

Nao toca no banco. Apenas le CSVs locais e gera artefatos.
"""

import csv
import json
import os
import re
import sys
from collections import defaultdict, OrderedDict
from datetime import datetime

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
RANGE_RE = re.compile(r'_(\d+)_(\d+)')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_range(filename):
    m = RANGE_RE.search(os.path.basename(filename))
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def read_csv_rows(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            reader = csv.DictReader(f)
            return list(reader)
    except Exception as e:
        print(f"  [WARN] Erro lendo {os.path.basename(path)}: {e}")
        return []


def write_csv(path, rows, fieldnames):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)
    print(f"  -> {os.path.basename(path)}: {len(rows)} linhas")


def find_files(pattern):
    import glob
    return sorted(glob.glob(os.path.join(SCRIPTS_DIR, pattern)))


# ---------------------------------------------------------------------------
# Etapa 1: Inventario e coleta
# ---------------------------------------------------------------------------

def collect_all_sources():
    """Coleta TODAS as fontes de Classe B, preservando origem e schema original."""
    sources = {}

    # 1) wo_move_needed_{start}_{end}.csv — v1/v2, owners 501-50500
    # Schema: url,expected_wine_id,actual_wine_id,ws_id,store_id,pais,clean_id
    files = find_files('wo_move_needed_*.csv')
    rows = []
    ranges = []
    for f in files:
        data = read_csv_rows(f)
        s, e = extract_range(f)
        if s:
            ranges.append((s, e))
        for r in data:
            rows.append({
                'ws_id': r.get('ws_id', ''),
                'actual_wine_id': r.get('actual_wine_id', ''),
                'expected_wine_id': r.get('expected_wine_id', ''),
                'store_id': r.get('store_id', ''),
                'url': r.get('url', ''),
                'clean_id': r.get('clean_id', ''),
                'pais': r.get('pais', ''),
                'origem_csv': 'wo_move_needed',
                'owner_range': f'{s}-{e}' if s else 'unknown',
            })
    sources['wo_move_needed'] = {
        'files': len(files), 'rows_bruto': len(rows), 'ranges': sorted(ranges),
        'has_ws_id': True, 'schema': 'url,expected_wine_id,actual_wine_id,ws_id,store_id,pais,clean_id',
    }
    all_rows = list(rows)

    # 2) wo_hybrid_b_{start}_{end}.csv — hybrid, owners 52501-300500
    # Schema: ws_id,actual,expected,store_id,url,cid
    files = find_files('wo_hybrid_b_*.csv')
    rows = []
    ranges = []
    for f in files:
        data = read_csv_rows(f)
        s, e = extract_range(f)
        if s:
            ranges.append((s, e))
        for r in data:
            rows.append({
                'ws_id': r.get('ws_id', ''),
                'actual_wine_id': r.get('actual', r.get('actual_wine_id', '')),
                'expected_wine_id': r.get('expected', r.get('expected_wine_id', '')),
                'store_id': r.get('store_id', ''),
                'url': r.get('url', ''),
                'clean_id': r.get('cid', r.get('clean_id', '')),
                'pais': '',
                'origem_csv': 'wo_hybrid_b',
                'owner_range': f'{s}-{e}' if s else 'unknown',
            })
    sources['wo_hybrid_b'] = {
        'files': len(files), 'rows_bruto': len(rows), 'ranges': sorted(ranges),
        'has_ws_id': True, 'schema': 'ws_id,actual,expected,store_id,url,cid',
    }
    all_rows.extend(rows)

    # 3) wo_sql_b_{start}_{end}.csv — sql, owners 114501-144500 + gap 50501-52500
    # Schema: ws_id,actual_wine_id,expected_wine_id,store_id,url,clean_id
    files = find_files('wo_sql_b_*.csv')
    rows = []
    ranges = []
    for f in files:
        data = read_csv_rows(f)
        s, e = extract_range(f)
        if s:
            ranges.append((s, e))
        for r in data:
            rows.append({
                'ws_id': r.get('ws_id', ''),
                'actual_wine_id': r.get('actual_wine_id', ''),
                'expected_wine_id': r.get('expected_wine_id', ''),
                'store_id': r.get('store_id', ''),
                'url': r.get('url', ''),
                'clean_id': r.get('clean_id', ''),
                'pais': '',
                'origem_csv': 'wo_sql_b',
                'owner_range': f'{s}-{e}' if s else 'unknown',
            })
    sources['wo_sql_b'] = {
        'files': len(files), 'rows_bruto': len(rows), 'ranges': sorted(ranges),
        'has_ws_id': True, 'schema': 'ws_id,actual_wine_id,expected_wine_id,store_id,url,clean_id',
    }
    all_rows.extend(rows)

    # 4) wrong_owner_move_needed_candidates.csv
    p = os.path.join(SCRIPTS_DIR, 'wrong_owner_move_needed_candidates.csv')
    rows = []
    if os.path.exists(p):
        data = read_csv_rows(p)
        for r in data:
            rows.append({
                'ws_id': r.get('ws_id', ''),
                'actual_wine_id': r.get('actual_wine_id', ''),
                'expected_wine_id': r.get('expected_wine_id', ''),
                'store_id': r.get('store_id', ''),
                'url': r.get('url', ''),
                'clean_id': r.get('clean_id', ''),
                'pais': '',
                'origem_csv': 'candidates',
                'owner_range': 'unknown',
            })
    sources['candidates'] = {
        'files': 1 if os.path.exists(p) else 0, 'rows_bruto': len(rows), 'ranges': [],
        'has_ws_id': True, 'schema': 'ws_id,actual_wine_id,...',
    }
    all_rows.extend(rows)

    # 5) wrong_owner_pilot_candidates.csv
    # Schema: url,expected_wine_id,actual_wine_id,store_id,pais,clean_id  <-- NO ws_id!
    p = os.path.join(SCRIPTS_DIR, 'wrong_owner_pilot_candidates.csv')
    rows = []
    if os.path.exists(p):
        data = read_csv_rows(p)
        for r in data:
            rows.append({
                'ws_id': '',  # NAO TEM ws_id!
                'actual_wine_id': r.get('actual_wine_id', ''),
                'expected_wine_id': r.get('expected_wine_id', ''),
                'store_id': r.get('store_id', ''),
                'url': r.get('url', ''),
                'clean_id': r.get('clean_id', ''),
                'pais': r.get('pais', ''),
                'origem_csv': 'pilot_candidates',
                'owner_range': 'pilot',
            })
    sources['pilot_candidates'] = {
        'files': 1 if os.path.exists(p) else 0, 'rows_bruto': len(rows), 'ranges': [],
        'has_ws_id': False, 'schema': 'url,expected_wine_id,actual_wine_id,store_id,pais,clean_id (SEM ws_id)',
    }
    all_rows.extend(rows)

    return all_rows, sources


def analyze_dedup(all_rows):
    """
    Analisa deduplicacao por ws_id e por chave composta.
    Reporta conflitos e overlaps.
    """
    # Separar rows COM ws_id e SEM ws_id
    with_wsid = [r for r in all_rows if r['ws_id'].strip()]
    without_wsid = [r for r in all_rows if not r['ws_id'].strip()]

    print(f"\n  Rows COM ws_id: {len(with_wsid)}")
    print(f"  Rows SEM ws_id: {len(without_wsid)} (pilot_candidates)")

    # --- Dedup por ws_id (chave primaria operacional) ---
    by_wsid = defaultdict(list)
    for r in with_wsid:
        by_wsid[r['ws_id']].append(r)

    unique_wsid = len(by_wsid)
    conflicts_wsid = {}  # ws_id com expected diferente
    overlaps_wsid = {}   # ws_id duplicado mas sem conflito

    for wsid, rlist in by_wsid.items():
        if len(rlist) > 1:
            expected_set = set(r['expected_wine_id'] for r in rlist)
            if len(expected_set) > 1:
                conflicts_wsid[wsid] = rlist
            else:
                overlaps_wsid[wsid] = rlist

    print(f"\n  ws_id unicos: {unique_wsid}")
    print(f"  ws_id duplicados benignos (mesmo expected): {len(overlaps_wsid)}")
    print(f"  ws_id com CONFLITO (expected diferente): {len(conflicts_wsid)}")

    if conflicts_wsid:
        print("\n  !!! CONFLITOS DE ws_id !!!")
        for wsid, rlist in list(conflicts_wsid.items())[:5]:
            print(f"    ws_id={wsid}:")
            for r in rlist:
                print(f"      expected={r['expected_wine_id']} actual={r['actual_wine_id']} url={r['url'][:60]} origem={r['origem_csv']}")

    # --- Chave composta: (actual_wine_id, expected_wine_id, store_id, url) ---
    by_composite = defaultdict(list)
    for r in with_wsid:
        key = (r['actual_wine_id'], r['expected_wine_id'], r['store_id'], r['url'])
        by_composite[key].append(r)

    unique_composite = len(by_composite)
    multi_wsid_same_composite = {k: v for k, v in by_composite.items() if len(set(r['ws_id'] for r in v)) > 1}

    print(f"\n  Chave composta (actual, expected, store_id, url) unicas: {unique_composite}")
    print(f"  Chaves compostas com MULTIPLOS ws_id: {len(multi_wsid_same_composite)}")

    if multi_wsid_same_composite:
        print("  (Isso significa que existem ws_ids diferentes para o mesmo 'move' — cada um e uma row separada no banco)")
        for key, rlist in list(multi_wsid_same_composite.items())[:3]:
            print(f"    key={key[0]}->{key[1]} store={key[2]} url={key[3][:50]}")
            for r in rlist:
                print(f"      ws_id={r['ws_id']} origem={r['origem_csv']}")

    # --- Analise dos pilot_candidates (sem ws_id) ---
    pilot_covered = 0
    pilot_uncovered = 0
    pilot_uncovered_rows = []
    composite_from_wsid = set()
    for r in with_wsid:
        composite_from_wsid.add((r['actual_wine_id'], r['expected_wine_id'], r['store_id'], r['url']))

    for r in without_wsid:
        key = (r['actual_wine_id'], r['expected_wine_id'], r['store_id'], r['url'])
        if key in composite_from_wsid:
            pilot_covered += 1
        else:
            pilot_uncovered += 1
            pilot_uncovered_rows.append(r)

    print(f"\n  Pilot candidates (sem ws_id):")
    print(f"    Cobertos por outras fontes (tem ws_id noutro CSV): {pilot_covered}")
    print(f"    NAO cobertos (sem ws_id em lugar nenhum): {pilot_uncovered}")

    # --- Conflitos por (url, store_id) com expected divergentes ---
    by_url_store = defaultdict(set)
    for r in with_wsid:
        if r['url'] and r['store_id']:
            by_url_store[(r['url'], r['store_id'])].add(r['expected_wine_id'])

    multi_expected = {k: v for k, v in by_url_store.items() if len(v) > 1}
    print(f"\n  Pares (url, store_id) com MULTIPLOS expected_wine_id: {len(multi_expected)}")
    if multi_expected:
        print("  !!! Estes sao ambiguidades que DEVEM virar 'ambiguous' !!!")
        for (url, sid), expected_set in list(multi_expected.items())[:5]:
            print(f"    url={url[:60]} store={sid} expected_ids={expected_set}")

    return {
        'with_wsid': with_wsid,
        'without_wsid': without_wsid,
        'by_wsid': by_wsid,
        'conflicts_wsid': conflicts_wsid,
        'overlaps_wsid': overlaps_wsid,
        'unique_wsid': unique_wsid,
        'unique_composite': unique_composite,
        'multi_wsid_same_composite': len(multi_wsid_same_composite),
        'pilot_covered': pilot_covered,
        'pilot_uncovered': pilot_uncovered,
        'pilot_uncovered_rows': pilot_uncovered_rows,
        'multi_expected_url_store': multi_expected,
    }


def range_coverage(ranges):
    if not ranges:
        return {'min': None, 'max': None, 'gaps': [], 'count': 0}
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
        'count': len(sorted_r),
    }


def build_deduped(analysis):
    """
    Constroi o consolidado deduplicado.
    Chave de dedup: ws_id (para rows com ws_id).
    Rows sem ws_id que nao estao cobertas sao mantidas separadas.
    """
    deduped = OrderedDict()
    for wsid, rlist in analysis['by_wsid'].items():
        # Pegar a primeira ocorrencia (prioridade: sql > hybrid > move_needed)
        priority = {'wo_sql_b': 0, 'wo_hybrid_b': 1, 'wo_move_needed': 2, 'candidates': 3}
        sorted_rows = sorted(rlist, key=lambda r: priority.get(r['origem_csv'], 99))
        deduped[wsid] = sorted_rows[0]

    return list(deduped.values())


# ---------------------------------------------------------------------------
# Etapa 2: Classificacao local
# ---------------------------------------------------------------------------

def classify_locally(deduped, analysis):
    """
    Classifica cada caso em:
    - move_needed_safe: ws_id + actual + expected + url presentes, sem conflito.
      store_id no CSV pode estar vazio (sera obtido via SELECT no banco na execucao).
    - ambiguous: conflitos reais (multiplos expected para mesmo ws_id ou (url,store_id))
    - incomplete: sem ws_id e nao coberto por outras fontes

    NOTA: Validacao REAL (existe no banco?) requer acesso ao Render.
    Esta classificacao e baseada apenas nos dados locais dos CSVs.
    """
    safe = []
    ambiguous = []
    incomplete = []

    # URLs/stores com multiplos expected
    ambiguous_url_stores = analysis['multi_expected_url_store']

    # ws_ids com conflito
    conflict_wsids = set(analysis['conflicts_wsid'].keys())

    store_needs_lookup = 0

    for row in deduped:
        wsid = row['ws_id']
        url = row.get('url', '').strip()
        store_id = row.get('store_id', '').strip()
        actual = row.get('actual_wine_id', '').strip()
        expected = row.get('expected_wine_id', '').strip()

        hard_reasons = []  # Bloqueiam: viram ambiguous
        soft_flags = []    # Nao bloqueiam: apenas anotacoes

        # Check 1: ws_id presente (hard)
        if not wsid:
            hard_reasons.append('missing_ws_id')

        # Check 2: actual e expected presentes e diferentes (hard)
        if not actual:
            hard_reasons.append('missing_actual_wine_id')
        if not expected:
            hard_reasons.append('missing_expected_wine_id')
        if actual and expected and actual == expected:
            hard_reasons.append('actual_equals_expected')

        # Check 3: store_id — SOFT. Muitos CSVs v1/v2 nao gravaram store_id.
        # O store_id existe no banco e sera obtido via SELECT antes da operacao.
        if not store_id:
            soft_flags.append('store_id_needs_db_lookup')
            store_needs_lookup += 1

        # Check 4: url presente e parece valida (hard se ausente)
        if not url:
            hard_reasons.append('missing_url')
        elif not url.startswith('http'):
            hard_reasons.append('invalid_url')

        # Check 5: conflito de ws_id (hard)
        if wsid in conflict_wsids:
            hard_reasons.append('conflicting_expected_for_ws_id')

        # Check 6: ambiguidade por (url, store_id) (hard)
        if url and store_id and (url, store_id) in ambiguous_url_stores:
            hard_reasons.append('multiple_expected_for_url_store')

        # Classificar
        row_out = dict(row)
        if hard_reasons:
            row_out['classificacao'] = 'ambiguous'
            row_out['motivo'] = '; '.join(hard_reasons)
            if soft_flags:
                row_out['motivo'] += ' | flags: ' + '; '.join(soft_flags)
            ambiguous.append(row_out)
        else:
            row_out['classificacao'] = 'move_needed_safe'
            motivo = 'dados_completos_sem_conflito'
            if soft_flags:
                motivo += ' | flags: ' + '; '.join(soft_flags)
            row_out['motivo'] = motivo
            safe.append(row_out)

    # Adicionar pilot_uncovered como incomplete
    for row in analysis['pilot_uncovered_rows']:
        row_out = dict(row)
        row_out['classificacao'] = 'incomplete'
        row_out['motivo'] = 'pilot_candidate_sem_ws_id_nao_coberto'
        incomplete.append(row_out)

    print(f"  (store_id ausente no CSV mas existente no banco: {store_needs_lookup} rows)")
    return safe, ambiguous, incomplete


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("CONSOLIDACAO COMPLETA — CLASSE B (move_needed)")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Diretorio: {SCRIPTS_DIR}")
    print("=" * 70)

    # -----------------------------------------------------------------------
    # ETAPA 1: Inventario e coleta
    # -----------------------------------------------------------------------
    print("\n[ETAPA 1] Inventario de todas as fontes de Classe B\n")

    all_rows, sources = collect_all_sources()

    total_bruto = sum(s['rows_bruto'] for s in sources.values())
    total_files = sum(s['files'] for s in sources.values())
    print(f"\n  TOTAL: {total_files} arquivos, {total_bruto} linhas brutas")

    print("\n  Fontes inventariadas:")
    for name, info in sources.items():
        print(f"    {name}:")
        print(f"      Arquivos: {info['files']}")
        print(f"      Linhas brutas: {info['rows_bruto']}")
        print(f"      Tem ws_id: {'SIM' if info['has_ws_id'] else 'NAO'}")
        print(f"      Schema: {info['schema']}")
        if info['ranges']:
            cov = range_coverage(info['ranges'])
            print(f"      Range: owners {cov['min']}-{cov['max']} ({cov['count']} blocos)")
            if cov['gaps']:
                print(f"      GAPS: {cov['gaps']}")

    # Verificar cobertura global de ranges
    all_ranges = []
    for name in ['wo_move_needed', 'wo_hybrid_b', 'wo_sql_b']:
        all_ranges.extend(sources[name]['ranges'])

    print("\n  COBERTURA GLOBAL DE OWNER RANGES:")
    # v1/v2: step 500
    del_cov = range_coverage(sources['wo_move_needed']['ranges'])
    print(f"    v1/v2 (wo_move_needed): owners {del_cov['min']}-{del_cov['max']}, {del_cov['count']} blocos")
    if del_cov['gaps']:
        print(f"      GAPS: {del_cov['gaps']}")

    # hybrid: step 2000
    hyb_cov = range_coverage(sources['wo_hybrid_b']['ranges'])
    print(f"    hybrid (wo_hybrid_b): owners {hyb_cov['min']}-{hyb_cov['max']}, {hyb_cov['count']} blocos")
    if hyb_cov['gaps']:
        print(f"      GAPS: {hyb_cov['gaps']}")

    # sql: step 5000 + gap
    sql_cov = range_coverage(sources['wo_sql_b']['ranges'])
    print(f"    sql (wo_sql_b): owners {sql_cov['min']}-{sql_cov['max']}, {sql_cov['count']} blocos")
    if sql_cov['gaps']:
        print(f"      GAPS: {sql_cov['gaps']}")
    # Verificar gap 50501-52500
    sql_ranges_set = set(sources['wo_sql_b']['ranges'])
    gap_covered = (50501, 52500) in sql_ranges_set
    print(f"    Gap 50501-52500 coberto pelo SQL: {'SIM' if gap_covered else 'NAO'}")

    # Overlap entre hybrid e sql
    hybrid_set = set()
    for s, e in sources['wo_hybrid_b']['ranges']:
        for owner in range(s, e+1):
            hybrid_set.add(owner)
    sql_set = set()
    for s, e in sources['wo_sql_b']['ranges']:
        for owner in range(s, e+1):
            sql_set.add(owner)
    overlap_owners = hybrid_set & sql_set
    if overlap_owners:
        print(f"    Overlap hybrid-sql: {min(overlap_owners)}-{max(overlap_owners)} ({len(overlap_owners)} owners)")

    # -----------------------------------------------------------------------
    # ANALISE DE DEDUPLICACAO
    # -----------------------------------------------------------------------
    print("\n[ANALISE DE DEDUPLICACAO]")
    print("  Chave primaria: ws_id (PK da tabela wine_sources)")
    print("  Justificativa: cada ws_id e uma row unica no banco. A operacao")
    print("  de move e por row (DELETE ws_id + INSERT em outro wine_id).")
    print("  Chave composta seria errada: apagaria rows validas distintas.")

    analysis = analyze_dedup(all_rows)

    # -----------------------------------------------------------------------
    # DEDUPLICACAO
    # -----------------------------------------------------------------------
    print("\n[DEDUPLICACAO]")
    deduped = build_deduped(analysis)
    print(f"  Consolidado deduplicado (por ws_id): {len(deduped)} linhas")

    # -----------------------------------------------------------------------
    # ETAPA 2: Classificacao local
    # -----------------------------------------------------------------------
    print("\n[ETAPA 2] Classificacao local\n")
    safe, ambiguous, incomplete = classify_locally(deduped, analysis)

    print(f"  move_needed_safe: {len(safe)}")
    print(f"  ambiguous: {len(ambiguous)}")
    print(f"  incomplete (pilot sem ws_id): {len(incomplete)}")

    # Motivos dos ambiguos
    if ambiguous:
        motivo_counts = defaultdict(int)
        for r in ambiguous:
            for m in r['motivo'].split('; '):
                motivo_counts[m] += 1
        print(f"\n  Motivos de ambiguidade:")
        for m, c in sorted(motivo_counts.items(), key=lambda x: -x[1]):
            print(f"    {m}: {c}")

    # -----------------------------------------------------------------------
    # ETAPA 3: Gerar artefatos
    # -----------------------------------------------------------------------
    print("\n[ETAPA 3] Gerando artefatos\n")

    # Campos para os CSVs
    fields_consolidado = ['ws_id', 'actual_wine_id', 'expected_wine_id', 'store_id',
                          'url', 'clean_id', 'pais', 'origem_csv', 'owner_range']
    fields_safe = ['ws_id', 'actual_wine_id', 'expected_wine_id', 'store_id',
                   'url', 'clean_id', 'origem_csv', 'owner_range', 'motivo']
    fields_ambiguous = ['ws_id', 'actual_wine_id', 'expected_wine_id', 'store_id',
                        'url', 'clean_id', 'origem_csv', 'owner_range', 'classificacao', 'motivo']
    fields_stale = fields_ambiguous  # mesma estrutura

    # Consolidado final (deduplicado)
    consolidado_path = os.path.join(SCRIPTS_DIR, 'wrong_owner_move_needed_consolidado_final.csv')
    write_csv(consolidado_path, deduped, fields_consolidado)

    # Safe
    safe_path = os.path.join(SCRIPTS_DIR, 'wrong_owner_move_needed_safe.csv')
    write_csv(safe_path, safe, fields_safe)

    # Ambiguous
    ambiguous_path = os.path.join(SCRIPTS_DIR, 'wrong_owner_move_needed_ambiguous.csv')
    write_csv(ambiguous_path, ambiguous + incomplete, fields_ambiguous)

    # Stale — nao temos como detectar stale sem acesso ao banco
    # Criamos vazio com header para consistencia
    stale_path = os.path.join(SCRIPTS_DIR, 'wrong_owner_move_needed_stale.csv')
    write_csv(stale_path, [], fields_stale)
    print("  (stale vazio — requer acesso ao banco para detectar)")

    # -----------------------------------------------------------------------
    # STATS JSON
    # -----------------------------------------------------------------------
    stats = {
        'timestamp': datetime.now().isoformat(),
        'etapa': 'consolidacao_classe_b_completa',
        'totais': {
            'bruto': total_bruto,
            'deduplicado': len(deduped),
            'move_needed_safe': len(safe),
            'ambiguous': len(ambiguous),
            'incomplete': len(incomplete),
            'stale_or_already_fixed': 0,
        },
        'chave_dedup': 'ws_id',
        'justificativa_chave': 'ws_id e PK de wine_sources. Cada row e uma operacao distinta de move. Chave composta perderia rows validas.',
        'fontes': {k: {kk: vv for kk, vv in v.items() if kk != 'ranges'}
                   for k, v in sources.items()},
        'cobertura': {
            'v1v2': {'min': del_cov['min'], 'max': del_cov['max'], 'blocos': del_cov['count'], 'gaps': del_cov['gaps']},
            'hybrid': {'min': hyb_cov['min'], 'max': hyb_cov['max'], 'blocos': hyb_cov['count'], 'gaps': hyb_cov['gaps']},
            'sql': {'min': sql_cov['min'], 'max': sql_cov['max'], 'blocos': sql_cov['count'], 'gaps': sql_cov['gaps']},
            'gap_50501_52500_coberto': gap_covered,
        },
        'analise_dedup': {
            'rows_com_wsid': len(analysis['with_wsid']),
            'rows_sem_wsid': len(analysis['without_wsid']),
            'wsid_unicos': analysis['unique_wsid'],
            'conflitos_wsid': len(analysis['conflicts_wsid']),
            'overlaps_benignos': len(analysis['overlaps_wsid']),
            'composite_unicos': analysis['unique_composite'],
            'multi_wsid_same_composite': analysis['multi_wsid_same_composite'],
            'pilot_cobertos': analysis['pilot_covered'],
            'pilot_nao_cobertos': analysis['pilot_uncovered'],
            'ambiguidades_url_store': len(analysis['multi_expected_url_store']),
        },
    }

    stats_path = os.path.join(SCRIPTS_DIR, 'wrong_owner_classe_b_stats.json')
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  -> {os.path.basename(stats_path)}")

    # -----------------------------------------------------------------------
    # RESUMO FINAL
    # -----------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("RESUMO FINAL — CLASSE B")
    print("=" * 70)
    print(f"  Bruto consolidado:        {total_bruto}")
    print(f"  Deduplicado (por ws_id):  {len(deduped)}")
    print(f"  move_needed_safe:         {len(safe)}")
    print(f"  ambiguous:                {len(ambiguous)}")
    print(f"  incomplete (sem ws_id):   {len(incomplete)}")
    print(f"  stale_or_already_fixed:   0 (requer banco)")
    print(f"\n  Chave de dedup: ws_id")
    print(f"  Gap 50501-52500 incluso: {'SIM' if gap_covered else 'NAO'}")
    print(f"  Conflitos de ws_id: {len(analysis['conflicts_wsid'])}")
    print(f"  Ambiguidades (url,store_id): {len(analysis['multi_expected_url_store'])}")
    print(f"\n  Arquivos gerados:")
    print(f"    {consolidado_path}")
    print(f"    {safe_path}")
    print(f"    {ambiguous_path}")
    print(f"    {stale_path}")
    print(f"    {stats_path}")
    print()


if __name__ == '__main__':
    main()
