# -*- coding: utf-8 -*-
"""
Compara IAs vs Mistral - alinhamento por posicao, com deteccao de offset.
"""
import re
import os
import sys
from collections import Counter

# Fix encoding
sys.stdout.reconfigure(encoding='utf-8')

DIR = r"C:\winegod-app\scripts\lotes_llm"

COR_MAP = {
    'tinto': 'r', 'vermelho': 'r', 'red': 'r', 'r': 'r',
    'branco': 'w', 'white': 'w', 'w': 'w',
    'rose': 'p', 'rosado': 'p', 'p': 'p',
    'espumante': 's', 's': 's',
    'fortificado': 'f', 'f': 'f',
    '??': '??', '': '??',
}

PAIS_MAP = {
    'estados unidos': 'eua', 'usa': 'eua', 'us': 'eua',
    'africa do sul': 'za', 'south africa': 'za', 'za': 'za',
    'franca': 'fr', 'france': 'fr', 'fr': 'fr',
    'italia': 'it', 'italy': 'it', 'it': 'it',
    'argentina': 'ar', 'ar': 'ar',
    'chile': 'cl', 'cl': 'cl',
    'espanha': 'es', 'spain': 'es', 'es': 'es',
    'portugal': 'pt', 'pt': 'pt',
    'australia': 'au', 'au': 'au',
    'nova zelandia': 'nz', 'new zealand': 'nz', 'nz': 'nz',
    'austria': 'at', 'at': 'at',
    'alemanha': 'de', 'germany': 'de', 'de': 'de',
    'china': 'cn', 'cn': 'cn',
    'eslovenia': 'si', 'si': 'si',
    'inglaterra': 'gb', 'reino unido': 'gb', 'gb': 'gb', 'uk': 'gb',
    'eua': 'eua', '??': '??', '': '??',
}

def nc(c):
    return COR_MAP.get(c.strip().lower(), c.strip().lower()) if c else '??'
def npais(p):
    pl = p.strip().lower() if p else ''
    return PAIS_MAP.get(pl, pl) if pl else '??'
def nt(t):
    if not t: return ''
    return t.strip().lower().replace('-','').replace("'",'').replace('\u2019','').replace('  ',' ')

def parse_line(line):
    line = line.strip()
    if not line: return None
    m = re.match(r'^(\d+)\.\s*', line)
    if m: line = line[m.end():]
    if not line: return None

    up = line.upper().strip()
    if up == 'X':
        return {'tipo': 'X', 'prod': '', 'vinho': '', 'pais': '', 'cor': ''}
    if up == 'S':
        return {'tipo': 'S', 'prod': '', 'vinho': '', 'pais': '', 'cor': ''}
    if up == '??':
        return {'tipo': '??', 'prod': '', 'vinho': '', 'pais': '', 'cor': ''}
    if re.match(r'^=(\d+|M)$', line):
        return {'tipo': '=M', 'prod': '', 'vinho': '', 'pais': '', 'cor': ''}

    if len(line) >= 2 and line[0].upper() == 'W' and line[1] == '|':
        parts = line.split('|')
        clean = []
        for p in parts:
            if p.strip().startswith('='):
                break
            clean.append(p)
        parts = clean
        return {
            'tipo': 'W',
            'prod': parts[1].strip() if len(parts) > 1 else '',
            'vinho': parts[2].strip() if len(parts) > 2 else '',
            'pais': parts[3].strip() if len(parts) > 3 else '',
            'cor': parts[4].strip() if len(parts) > 4 else '',
        }
    if len(line) >= 2 and line[0].upper() == 'S' and line[1] == '|':
        return {'tipo': 'S', 'prod': '', 'vinho': '', 'pais': '', 'cor': ''}

    return None

def parse_file(filepath):
    items = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line: continue
            if line.startswith('---') or 'ProdBanco' in line or 'VinhoBanco' in line: continue
            if line.startswith('Aqui est') or line.startswith('Se precisar'): continue
            parsed = parse_line(line)
            if parsed:
                items.append(parsed)
    return items

def find_first_real_item(items):
    """Encontra o indice do primeiro item W com produtor real (nao exemplo do formato)."""
    for i, it in enumerate(items):
        if it['tipo'] == 'W' and it['prod']:
            p = nt(it['prod'])
            # Pular "chateau levangile" que eh o exemplo do formato
            if 'chateau levangile' not in p and 'prodbanco' not in p:
                return i
    return 0

def align_to_reference(ref, items, ref_name, ia_name):
    """Alinha items com ref baseado no primeiro produtor real."""
    ref_start = find_first_real_item(ref)
    ia_start = find_first_real_item(items)

    ref_first_prod = nt(ref[ref_start]['prod'])

    # Procurar onde o primeiro produtor real da ref aparece na IA
    best_offset = ia_start
    for i in range(min(10, len(items))):
        if items[i]['tipo'] == 'W' and nt(items[i]['prod']) == ref_first_prod:
            best_offset = i
            break

    return ref[ref_start:], items[best_offset:]

def compare():
    files = {
        'mistral': os.path.join(DIR, 'lotemistral.txt'),
        'chatgpt': os.path.join(DIR, 'lotechatgpt.txt'),
        'claude45': os.path.join(DIR, 'loteclaude4.5.txt'),
        'grok': os.path.join(DIR, 'lotegrok.txt'),
        'qwen': os.path.join(DIR, 'loteqwen.txt'),
        'gemini_dedup': os.path.join(DIR, 'lotegemini-com-dedup.txt'),
    }

    data = {ia: parse_file(fp) for ia, fp in files.items()}

    print("=" * 80)
    print("COMPARACAO v2: IAs vs MISTRAL (referencia)")
    print("=" * 80)

    # Mostrar primeiros itens pra verificar alinhamento
    print("\nPRIMEIROS 5 ITENS BRUTOS:")
    for ia, items in data.items():
        print(f"\n  {ia}:")
        for i, it in enumerate(items[:7]):
            if it['tipo'] == 'W':
                print(f"    [{i}] W|{it['prod']}|{it['vinho']}|{it['pais']}|{it['cor']}")
            else:
                print(f"    [{i}] {it['tipo']}")

    ref_raw = data['mistral']
    outras = {k: v for k, v in data.items() if k != 'mistral'}

    # Alinhar cada IA com Mistral
    ref_aligned_start = find_first_real_item(ref_raw)
    ref_first_prod = nt(ref_raw[ref_aligned_start]['prod'])
    print(f"\nMistral: primeiro item real na pos {ref_aligned_start}: {ref_first_prod}")

    ref = ref_raw[ref_aligned_start:]

    aligned = {}
    for ia_name, items in outras.items():
        ia_start = -1
        for i in range(min(15, len(items))):
            if items[i]['tipo'] == 'W' and nt(items[i]['prod']) == ref_first_prod:
                ia_start = i
                break
        if ia_start < 0:
            # Fallback: primeiro W real
            ia_start = find_first_real_item(items)
        print(f"{ia_name}: alinhado a partir de pos {ia_start} (prod={nt(items[ia_start]['prod']) if ia_start < len(items) else '?'})")
        aligned[ia_name] = items[ia_start:]

    # Comparar
    print(f"\n{'='*80}")
    print(f"RESULTADOS")
    print(f"{'='*80}")

    for ia_name, items in aligned.items():
        n = min(len(ref), len(items))

        tm = tt = 0
        pe = pp = pt = 0
        ve = vp = vt = 0
        pm = pt2 = 0
        cm = ct = 0

        desacordos = []

        for i in range(n):
            r, o = ref[i], items[i]
            rt = r['tipo'] if r['tipo'] not in ('=M', '??') else 'W'
            ot = o['tipo'] if o['tipo'] not in ('=M', '??') else 'W'

            tt += 1
            if rt == ot:
                tm += 1
            else:
                desacordos.append((i, r, o, rt, ot))

            if rt == 'W' and ot == 'W':
                rp, op = nt(r['prod']), nt(o['prod'])
                if rp and op:
                    pt += 1
                    if rp == op:
                        pe += 1
                    elif rp in op or op in rp:
                        pp += 1

                rv, ov = nt(r['vinho']), nt(o['vinho'])
                if rv and ov:
                    vt += 1
                    if rv == ov:
                        ve += 1
                    elif rv in ov or ov in rv:
                        vp += 1

                rpa, opa = npais(r['pais']), npais(o['pais'])
                if rpa != '??' and opa != '??':
                    pt2 += 1
                    if rpa == opa:
                        pm += 1

                rc, oc = nc(r['cor']), nc(o['cor'])
                if rc != '??' and oc != '??':
                    ct += 1
                    if rc == oc:
                        cm += 1

        def pct(n2, d): return f"{n2/d*100:.1f}%" if d else "-"
        def pctc(n2, p2, d): return f"{(n2+p2*0.5)/d*100:.1f}%" if d else "-"

        print(f"\n  --- {ia_name.upper()} vs MISTRAL ---")
        print(f"  Completude:           {len(items)} itens ({len(items)}/{len(ref)} = {len(items)/len(ref)*100:.0f}%)")
        print(f"  Comparados:           {n}")
        print(f"  Classificacao W/X/S:  {pct(tm, tt)} ({tm}/{tt})")
        print(f"  Produtor exato:       {pct(pe, pt)} ({pe}/{pt})")
        print(f"  Produtor +parcial:    {pctc(pe, pp, pt)}")
        print(f"  Vinho exato:          {pct(ve, vt)} ({ve}/{vt})")
        print(f"  Vinho +parcial:       {pctc(ve, vp, vt)}")
        print(f"  Pais:                 {pct(pm, pt2)} ({pm}/{pt2})")
        print(f"  Cor:                  {pct(cm, ct)} ({cm}/{ct})")

        # Verificar alinhamento com spot checks
        checks = [0, 49, 99, 199, 499, n-1]
        print(f"\n  SPOT CHECKS (verificar se itens batem):")
        for idx in checks:
            if idx >= n: continue
            r2, o2 = ref[idx], items[idx]
            match_prod = "OK" if nt(r2['prod']) == nt(o2['prod']) else "DIFF"
            print(f"    pos {idx:4d}: M={r2['tipo']}|{r2['prod'][:25]:25s}  {ia_name}={o2['tipo']}|{o2['prod'][:25]:25s} [{match_prod}]")

        if desacordos:
            print(f"\n  Desacordos W/X/S: {len(desacordos)} itens")
            for i, r2, o2, rt, ot in desacordos[:10]:
                rl = f"{rt}" if rt != 'W' else f"W:{r2['prod'][:20]}"
                ol = f"{ot}" if ot != 'W' else f"W:{o2['prod'][:20]}"
                print(f"    pos {i:4d}: Mistral={rl:30s} | {ia_name}={ol}")
            if len(desacordos) > 10:
                print(f"    ... e mais {len(desacordos)-10}")

    # TABELA RESUMO
    print(f"\n{'='*80}")
    print("TABELA RESUMO FINAL")
    print(f"{'='*80}")
    print(f"  {'IA':15s} {'Itens':>6s} {'W/X/S':>7s} {'Prod':>7s} {'Prod+':>7s} {'Vinho':>7s} {'Vin+':>7s} {'Pais':>7s} {'Cor':>7s}")
    print(f"  {'-'*15} {'-'*6} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7}")

    for ia_name, items in aligned.items():
        n = min(len(ref), len(items))
        tm=tt=pe=pp=pt=ve=vp=vt=pm2=pt2=cm=ct=0
        for i in range(n):
            r2, o2 = ref[i], items[i]
            rt = r2['tipo'] if r2['tipo'] not in ('=M','??') else 'W'
            ot = o2['tipo'] if o2['tipo'] not in ('=M','??') else 'W'
            tt += 1
            if rt == ot: tm += 1
            if rt == 'W' and ot == 'W':
                rp, op = nt(r2['prod']), nt(o2['prod'])
                if rp and op:
                    pt += 1
                    if rp == op: pe += 1
                    elif rp in op or op in rp: pp += 1
                rv, ov = nt(r2['vinho']), nt(o2['vinho'])
                if rv and ov:
                    vt += 1
                    if rv == ov: ve += 1
                    elif rv in ov or ov in rv: vp += 1
                rpa, opa = npais(r2['pais']), npais(o2['pais'])
                if rpa != '??' and opa != '??':
                    pt2 += 1
                    if rpa == opa: pm2 += 1
                rc, oc = nc(r2['cor']), nc(o2['cor'])
                if rc != '??' and oc != '??':
                    ct += 1
                    if rc == oc: cm += 1

        def p(n2,d): return f"{n2/d*100:.0f}%" if d else "-"
        def pc(n2,p2,d): return f"{(n2+p2*0.5)/d*100:.0f}%" if d else "-"
        print(f"  {ia_name:15s} {len(items):>5d}  {p(tm,tt):>6s} {p(pe,pt):>6s} {pc(pe,pp,pt):>6s} {p(ve,vt):>6s} {pc(ve,vp,vt):>6s} {p(pm2,pt2):>6s} {p(cm,ct):>6s}")

    print(f"\n  Prod+=exato+parcial. Vin+=exato+parcial.")
    print(f"  Parcial = produtor/vinho de um contem o do outro (substring).")

if __name__ == '__main__':
    compare()
