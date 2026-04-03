# -*- coding: utf-8 -*-
"""
v3: Compara apenas os primeiros N itens onde o alinhamento esta OK para todas as IAs.
Inclui tambem a comparacao completa do ChatGPT (unico 100% alinhado).
"""
import re, os, sys
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')
DIR = r"C:\winegod-app\scripts\lotes_llm"

COR_MAP = {
    'tinto': 'r', 'vermelho': 'r', 'r': 'r',
    'branco': 'w', 'w': 'w',
    'rose': 'p', 'rosado': 'p', 'p': 'p',
    'espumante': 's', 's': 's',
    'fortificado': 'f', 'f': 'f',
    '??': '??', '': '??',
}
PAIS_MAP = {
    'estados unidos': 'eua', 'usa': 'eua', 'us': 'eua', 'eua': 'eua',
    'africa do sul': 'za', 'za': 'za',
    'franca': 'fr', 'fr': 'fr',
    'italia': 'it', 'it': 'it',
    'argentina': 'ar', 'ar': 'ar',
    'chile': 'cl', 'cl': 'cl',
    'espanha': 'es', 'es': 'es',
    'portugal': 'pt', 'pt': 'pt',
    'australia': 'au', 'au': 'au',
    'nova zelandia': 'nz', 'nz': 'nz',
    'austria': 'at', 'at': 'at',
    'alemanha': 'de', 'de': 'de',
    'china': 'cn', 'cn': 'cn',
    'eslovenia': 'si', 'si': 'si',
    'inglaterra': 'gb', 'reino unido': 'gb', 'gb': 'gb',
    '??': '??', '': '??',
}

def nc(c):
    return COR_MAP.get(c.strip().lower(), '??') if c else '??'
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
    if up == 'X': return {'tipo': 'X', 'prod': '', 'vinho': '', 'pais': '', 'cor': ''}
    if up == 'S': return {'tipo': 'S', 'prod': '', 'vinho': '', 'pais': '', 'cor': ''}
    if up == '??': return {'tipo': '??', 'prod': '', 'vinho': '', 'pais': '', 'cor': ''}
    if re.match(r'^=(\d+|M)$', line):
        return {'tipo': '=M', 'prod': '', 'vinho': '', 'pais': '', 'cor': ''}
    if len(line) >= 2 and line[0].upper() == 'W' and line[1] == '|':
        parts = line.split('|')
        clean = []
        for p in parts:
            if p.strip().startswith('='): break
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
            if parsed: items.append(parsed)
    return items

def find_first_real(items):
    for i, it in enumerate(items):
        if it['tipo'] == 'W' and it['prod'] and 'chateau levangile' not in nt(it['prod']):
            return i
    return 0

def compare_range(ref, other, start, end):
    """Compara ref[start:end] vs other[start:end]."""
    n = min(end, len(ref), len(other)) - start
    if n <= 0: return None

    tm=tt=pe=pp=pt=ve=vp=vt=pm=pt2=cm=ct=0
    for i in range(start, start + n):
        if i >= len(ref) or i >= len(other): break
        r, o = ref[i], other[i]
        rt = r['tipo'] if r['tipo'] not in ('=M','??') else 'W'
        ot = o['tipo'] if o['tipo'] not in ('=M','??') else 'W'
        tt += 1
        if rt == ot: tm += 1
        if rt == 'W' and ot == 'W':
            rp, op = nt(r['prod']), nt(o['prod'])
            if rp and op:
                pt += 1
                if rp == op: pe += 1
                elif rp in op or op in rp: pp += 1
            rv, ov = nt(r['vinho']), nt(o['vinho'])
            if rv and ov:
                vt += 1
                if rv == ov: ve += 1
                elif rv in ov or ov in rv: vp += 1
            rpa, opa = npais(r['pais']), npais(o['pais'])
            if rpa != '??' and opa != '??':
                pt2 += 1
                if rpa == opa: pm += 1
            rc, oc = nc(r['cor']), nc(o['cor'])
            if rc != '??' and oc != '??':
                ct += 1
                if rc == oc: cm += 1

    def p(n2,d): return f"{n2/d*100:.0f}%" if d else "-"
    def pc(n2,p2,d): return f"{(n2+p2*0.5)/d*100:.0f}%" if d else "-"
    return {
        'n': n,
        'wxs': p(tm,tt), 'wxs_raw': tm/tt*100 if tt else 0,
        'prod': p(pe,pt), 'prod_p': pc(pe,pp,pt), 'prod_raw': (pe+pp*0.5)/pt*100 if pt else 0,
        'vinho': p(ve,vt), 'vinho_p': pc(ve,vp,vt), 'vinho_raw': (ve+vp*0.5)/vt*100 if vt else 0,
        'pais': p(pm,pt2), 'pais_raw': pm/pt2*100 if pt2 else 0,
        'cor': p(cm,ct), 'cor_raw': cm/ct*100 if ct else 0,
    }

def main():
    files = {
        'mistral': os.path.join(DIR, 'lotemistral.txt'),
        'chatgpt': os.path.join(DIR, 'lotechatgpt.txt'),
        'claude45': os.path.join(DIR, 'loteclaude4.5.txt'),
        'grok': os.path.join(DIR, 'lotegrok.txt'),
        'qwen': os.path.join(DIR, 'loteqwen.txt'),
        'gemini_dedup': os.path.join(DIR, 'lotegemini-com-dedup.txt'),
    }

    data = {}
    for ia, fp in files.items():
        raw = parse_file(fp)
        start = find_first_real(raw)
        data[ia] = raw[start:]

    # Para Grok: alinhar manualmente (pula longyu, comeca em lookout cape)
    # Grok pos 0 apos find_first_real = lookout cape (faltou longyu)
    # Mistral pos 0 = longyu, pos 1 = lookout cape
    # Verificar
    ref = data['mistral']
    grok = data['grok']

    # Grok perdeu o primeiro item (longyu). Inserir placeholder
    if nt(grok[0]['prod']) != nt(ref[0]['prod']):
        ref_prod0 = nt(ref[0]['prod'])
        # Achar onde Grok comeca
        grok_first = nt(grok[0]['prod'])
        for ri, r in enumerate(ref[:10]):
            if nt(r['prod']) == grok_first:
                # Inserir ri placeholders no inicio do grok
                placeholders = [{'tipo': '??', 'prod': '', 'vinho': '', 'pais': '', 'cor': ''}] * ri
                data['grok'] = placeholders + grok
                print(f"GROK: inseridos {ri} placeholders (perdeu {ri} itens iniciais)")
                break

    ref = data['mistral']

    print("=" * 80)
    print("COMPARACAO v3: PRIMEIROS 200 ITENS (alinhamento confiavel)")
    print("=" * 80)

    print(f"\n  {'IA':15s} {'N':>4s} {'W/X/S':>7s} {'Prod':>7s} {'Prod+':>7s} {'Vinho':>7s} {'Vin+':>7s} {'Pais':>7s} {'Cor':>7s}")
    print(f"  {'-'*15} {'-'*4} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7}")

    outras = {k: v for k, v in data.items() if k != 'mistral'}
    for ia_name, items in outras.items():
        r = compare_range(ref, items, 0, 200)
        if r:
            print(f"  {ia_name:15s} {r['n']:>4d} {r['wxs']:>6s} {r['prod']:>6s} {r['prod_p']:>6s} {r['vinho']:>6s} {r['vinho_p']:>6s} {r['pais']:>6s} {r['cor']:>6s}")

    # ChatGPT: comparacao completa (unico 100% alinhado)
    print(f"\n{'='*80}")
    print("CHATGPT vs MISTRAL — COMPLETO (1000 itens, 100% alinhado)")
    print(f"{'='*80}")
    r = compare_range(ref, data['chatgpt'], 0, 1000)
    if r:
        print(f"  Itens:     {r['n']}")
        print(f"  W/X/S:     {r['wxs']}")
        print(f"  Produtor:  {r['prod']} (exato) / {r['prod_p']} (+parcial)")
        print(f"  Vinho:     {r['vinho']} (exato) / {r['vinho_p']} (+parcial)")
        print(f"  Pais:      {r['pais']}")
        print(f"  Cor:       {r['cor']}")

    # Comparacao por faixas pra detectar drift em Claude/Qwen
    print(f"\n{'='*80}")
    print("DETECCAO DE DRIFT — Comparacao por faixas de 100")
    print(f"{'='*80}")

    for ia_name in ['claude45', 'qwen']:
        items = data[ia_name]
        print(f"\n  {ia_name.upper()}:")
        print(f"  {'Faixa':>10s} {'W/X/S':>7s} {'Prod+':>7s} {'Vin+':>7s} {'Pais':>7s} {'Cor':>7s}")
        for start in range(0, min(1000, len(ref), len(items)), 100):
            end = start + 100
            r = compare_range(ref, items, start, end)
            if r:
                faixa = f"{start}-{start+r['n']-1}"
                print(f"  {faixa:>10s} {r['wxs']:>6s} {r['prod_p']:>6s} {r['vinho_p']:>6s} {r['pais']:>6s} {r['cor']:>6s}")

    # Distribuicao W/X/S
    print(f"\n{'='*80}")
    print("DISTRIBUICAO W/X/S (totais)")
    print(f"{'='*80}")
    for ia_name, items in data.items():
        tipos = Counter(it['tipo'] for it in items)
        w = tipos.get('W', 0) + tipos.get('=M', 0) + tipos.get('??', 0)
        x = tipos.get('X', 0)
        s = tipos.get('S', 0)
        t = len(items)
        print(f"  {ia_name:15s}: W={w:4d} ({w/t*100:.1f}%)  X={x:3d} ({x/t*100:.1f}%)  S={s:3d} ({s/t*100:.1f}%)  total={t}")

    # Quem classificou X quando Mistral disse W (primeiros 200)
    print(f"\n{'='*80}")
    print("QUEM DISCORDA DE MISTRAL EM W/X/S? (primeiros 200)")
    print(f"{'='*80}")
    for i in range(min(200, len(ref))):
        rt = ref[i]['tipo'] if ref[i]['tipo'] not in ('=M','??') else 'W'
        discordantes = []
        for ia_name, items in outras.items():
            if i >= len(items): continue
            ot = items[i]['tipo'] if items[i]['tipo'] not in ('=M','??') else 'W'
            if rt != ot:
                discordantes.append(f"{ia_name}={ot}")
        if discordantes:
            label = f"W:{ref[i]['prod'][:25]}" if rt == 'W' else rt
            print(f"  pos {i:3d}: Mistral={label:30s} | {', '.join(discordantes)}")

if __name__ == '__main__':
    main()
