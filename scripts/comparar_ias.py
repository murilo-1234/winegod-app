"""
Compara respostas de 7 IAs contra Mistral (referência).
Analisa: completude, classificação W/X/S, produtor, vinho, país, cor.
"""
import re
import os
from collections import Counter

DIR = r"C:\winegod-app\scripts\lotes_llm"

# Normalizar cores (cada IA usa termos diferentes)
COR_MAP = {
    'tinto': 'r', 'vermelho': 'r', 'red': 'r', 'r': 'r',
    'branco': 'w', 'white': 'w', 'w': 'w',
    'rose': 'p', 'rosado': 'p', 'rosé': 'p', 'p': 'p',
    'espumante': 's', 's': 's', 'sparkling': 's',
    'fortificado': 'f', 'f': 'f',
    'sobremesa': 'd', 'd': 'd',
    '??': '??', '': '??',
}

# Normalizar países
PAIS_MAP = {
    'estados unidos': 'eua', 'usa': 'eua', 'us': 'eua',
    'africa do sul': 'za', 'south africa': 'za', 'za': 'za',
    'franca': 'fr', 'france': 'fr', 'fr': 'fr', 'frança': 'fr',
    'italia': 'it', 'italy': 'it', 'it': 'it', 'itália': 'it',
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
    'hungria': 'hu', 'hu': 'hu',
    'grecia': 'gr', 'gr': 'gr',
    'romenia': 'ro', 'ro': 'ro',
    'eua': 'eua',
    '??': '??', '': '??',
}

def norm_cor(c):
    return COR_MAP.get(c.strip().lower(), c.strip().lower()) if c else '??'

def norm_pais(p):
    pl = p.strip().lower() if p else ''
    return PAIS_MAP.get(pl, pl) if pl else '??'

def norm_text(t):
    """Normaliza texto p/ comparação: minúsculo, sem acentos comuns, sem hifens."""
    if not t:
        return ''
    t = t.strip().lower()
    t = t.replace('-', '').replace("'", '').replace('\u2019', '')
    return t

def parse_line(line):
    """
    Parseia uma linha de resposta. Retorna dict com:
    num, tipo (W/X/S/?/=M), prod, vinho, pais, cor, dedup_ref
    """
    line = line.strip()
    if not line:
        return None

    # Remover número do início: "123. " ou "123 "
    m = re.match(r'^(\d+)\.\s*', line)
    num = int(m.group(1)) if m else None
    if m:
        line = line[m.end():]

    # Linha vazia após remover número
    if not line:
        return None

    # Tipo
    if line.upper() == 'X':
        return {'num': num, 'tipo': 'X', 'prod': '', 'vinho': '', 'pais': '', 'cor': '', 'dedup': None}
    if line.upper() == 'S':
        return {'num': num, 'tipo': 'S', 'prod': '', 'vinho': '', 'pais': '', 'cor': '', 'dedup': None}
    if line.startswith('??'):
        return {'num': num, 'tipo': '??', 'prod': '', 'vinho': '', 'pais': '', 'cor': '', 'dedup': None}

    # Check dedup referências simples: "=M" ou "=123"
    dm = re.match(r'^=(\d+|M)$', line)
    if dm:
        return {'num': num, 'tipo': '=M', 'prod': '', 'vinho': '', 'pais': '', 'cor': '', 'dedup': dm.group(1)}

    # W|prod|vinho|pais|cor...
    if line.startswith('W|') or line.startswith('w|'):
        parts = line.split('|')
        # Checa dedup no final
        dedup = None
        for i, p in enumerate(parts):
            if p.strip().startswith('='):
                dedup = p.strip()[1:]
                parts = parts[:i]  # Remove dedup part
                break

        prod = parts[1].strip() if len(parts) > 1 else ''
        vinho = parts[2].strip() if len(parts) > 2 else ''
        pais = parts[3].strip() if len(parts) > 3 else ''
        cor = parts[4].strip() if len(parts) > 4 else ''

        return {'num': num, 'tipo': 'W', 'prod': prod, 'vinho': vinho, 'pais': pais, 'cor': cor, 'dedup': dedup}

    # S|prod|vinho...  (alguns IAs classificam destilados assim)
    if line.startswith('S|') or line.startswith('s|'):
        return {'num': num, 'tipo': 'S', 'prod': '', 'vinho': '', 'pais': '', 'cor': '', 'dedup': None}

    return None

def parse_file(filepath, ia_name):
    """Parseia um arquivo de resposta inteiro. Retorna dict {num: parsed_item}."""
    items = {}
    auto_num = 0

    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Pular cabeçalhos/separadores do Mistral
        if line.startswith('---') or line.startswith('Aqui está') or line.startswith('Se precisar'):
            continue
        if line in ['1. X', '2. S'] and ia_name == 'mistral':
            # Cabeçalho de formato do Mistral - pular primeiras linhas se forem exemplos
            continue
        if 'ProdBanco' in line or 'VinhoBanco' in line:
            continue

        parsed = parse_line(line)
        if parsed is None:
            continue

        if parsed['num'] is not None:
            auto_num = parsed['num']
        else:
            auto_num += 1
            parsed['num'] = auto_num

        items[parsed['num']] = parsed

    return items

def compare_ias():
    files = {
        'mistral': os.path.join(DIR, 'lotemistral.txt'),
        'chatgpt': os.path.join(DIR, 'lotechatgpt.txt'),
        'claude45': os.path.join(DIR, 'loteclaude4.5.txt'),
        'grok': os.path.join(DIR, 'lotegrok.txt'),
        'qwen': os.path.join(DIR, 'loteqwen.txt'),
        'gemini_dedup': os.path.join(DIR, 'lotegemini-com-dedup.txt'),
    }

    # Parsear todos
    data = {}
    for ia, fp in files.items():
        data[ia] = parse_file(fp, ia)

    ref = data['mistral']
    outras = {k: v for k, v in data.items() if k != 'mistral'}

    print("=" * 80)
    print("COMPARACAO: TODAS AS IAs vs MISTRAL (referencia)")
    print("=" * 80)

    # 1. Completude
    print(f"\n{'='*60}")
    print("1. COMPLETUDE")
    print(f"{'='*60}")
    print(f"  Mistral (ref): {len(ref)} itens")
    for ia, items in outras.items():
        print(f"  {ia:15s}: {len(items)} itens ({len(items)/len(ref)*100:.0f}%)")

    # 2. Distribuição W/X/S por IA
    print(f"\n{'='*60}")
    print("2. DISTRIBUICAO W / X / S / =M / ??")
    print(f"{'='*60}")
    for ia_name, items in data.items():
        tipos = Counter(it['tipo'] for it in items.values())
        w = tipos.get('W', 0)
        x = tipos.get('X', 0)
        s = tipos.get('S', 0)
        dup = tipos.get('=M', 0)
        unk = tipos.get('??', 0)
        total = len(items)
        print(f"  {ia_name:15s}: W={w:4d} ({w/total*100:5.1f}%)  X={x:3d} ({x/total*100:4.1f}%)  S={s:3d} ({s/total*100:4.1f}%)  =M={dup:3d} ({dup/total*100:4.1f}%)  ??={unk:2d} ({unk/total*100:3.1f}%)  total={total}")

    # 3. Concordância item-a-item com Mistral
    print(f"\n{'='*60}")
    print("3. CONCORDANCIA ITEM-A-ITEM vs MISTRAL")
    print(f"{'='*60}")

    for ia_name, items in outras.items():
        # Encontrar items em comum (por número)
        common_nums = set(ref.keys()) & set(items.keys())
        if not common_nums:
            print(f"  {ia_name}: NENHUM item em comum por numero!")
            continue

        tipo_match = 0
        tipo_total = 0
        prod_match = 0
        prod_total = 0
        vinho_match = 0
        vinho_total = 0
        pais_match = 0
        pais_total = 0
        cor_match = 0
        cor_total = 0

        tipo_disagreements = []
        prod_disagreements = []

        for n in sorted(common_nums):
            r = ref[n]
            o = items[n]

            # Normalizar tipo: =M conta como W (é um vinho, só duplicado)
            rt = r['tipo'] if r['tipo'] != '=M' else 'W'
            ot = o['tipo'] if o['tipo'] != '=M' else 'W'

            tipo_total += 1
            if rt == ot:
                tipo_match += 1
            else:
                tipo_disagreements.append((n, rt, ot))

            # Só comparar campos se ambos são W
            if rt == 'W' and ot == 'W':
                # Produtor
                rp = norm_text(r['prod'])
                op = norm_text(o['prod'])
                if rp and op:
                    prod_total += 1
                    if rp == op:
                        prod_match += 1
                    elif rp in op or op in rp:
                        prod_match += 0.5  # Parcial
                    else:
                        prod_disagreements.append((n, rp, op))

                # Vinho
                rv = norm_text(r['vinho'])
                ov = norm_text(o['vinho'])
                if rv and ov:
                    vinho_total += 1
                    if rv == ov:
                        vinho_match += 1
                    elif rv in ov or ov in rv:
                        vinho_match += 0.5

                # País
                rpa = norm_pais(r['pais'])
                opa = norm_pais(o['pais'])
                if rpa != '??' and opa != '??':
                    pais_total += 1
                    if rpa == opa:
                        pais_match += 1

                # Cor
                rc = norm_cor(r['cor'])
                oc = norm_cor(o['cor'])
                if rc != '??' and oc != '??':
                    cor_total += 1
                    if rc == oc:
                        cor_match += 1

        print(f"\n  --- {ia_name.upper()} vs MISTRAL ---")
        print(f"  Itens comparados: {len(common_nums)} / {len(ref)}")
        print(f"  Classificacao W/X/S: {tipo_match}/{tipo_total} = {tipo_match/tipo_total*100:.1f}%")
        if prod_total:
            print(f"  Produtor:           {prod_match:.0f}/{prod_total} = {prod_match/prod_total*100:.1f}%")
        if vinho_total:
            print(f"  Vinho:              {vinho_match:.0f}/{vinho_total} = {vinho_match/vinho_total*100:.1f}%")
        if pais_total:
            print(f"  Pais:               {pais_match}/{pais_total} = {pais_match/pais_total*100:.1f}%")
        if cor_total:
            print(f"  Cor:                {cor_match}/{cor_total} = {cor_match/cor_total*100:.1f}%")

        if tipo_disagreements:
            print(f"\n  Desacordos W/X/S ({len(tipo_disagreements)} itens):")
            for n, rt, ot in tipo_disagreements[:20]:
                ref_line = f"{rt}: {ref[n]['prod']}|{ref[n]['vinho']}" if rt == 'W' else rt
                out_line = f"{ot}: {items[n]['prod']}|{items[n]['vinho']}" if ot == 'W' else ot
                print(f"    #{n}: Mistral={ref_line}  |  {ia_name}={out_line}")
            if len(tipo_disagreements) > 20:
                print(f"    ... e mais {len(tipo_disagreements)-20}")

    # 4. Resumo final
    print(f"\n{'='*60}")
    print("4. RESUMO — RANKING")
    print(f"{'='*60}")
    print(f"  {'IA':15s} {'Completo':>8s} {'W/X/S':>8s} {'Produtor':>10s} {'Vinho':>10s} {'Pais':>8s} {'Cor':>8s}")
    print(f"  {'-'*15} {'-'*8} {'-'*8} {'-'*10} {'-'*10} {'-'*8} {'-'*8}")

    for ia_name, items in outras.items():
        common_nums = set(ref.keys()) & set(items.keys())
        if not common_nums:
            continue

        tipo_m = tipo_t = prod_m = prod_t = vin_m = vin_t = pais_m = pais_t = cor_m = cor_t = 0
        for n in common_nums:
            r = ref[n]; o = items[n]
            rt = r['tipo'] if r['tipo'] != '=M' else 'W'
            ot = o['tipo'] if o['tipo'] != '=M' else 'W'
            tipo_t += 1
            if rt == ot: tipo_m += 1
            if rt == 'W' and ot == 'W':
                rp, op = norm_text(r['prod']), norm_text(o['prod'])
                if rp and op:
                    prod_t += 1
                    if rp == op: prod_m += 1
                    elif rp in op or op in rp: prod_m += 0.5
                rv, ov = norm_text(r['vinho']), norm_text(o['vinho'])
                if rv and ov:
                    vin_t += 1
                    if rv == ov: vin_m += 1
                    elif rv in ov or ov in rv: vin_m += 0.5
                rpa, opa = norm_pais(r['pais']), norm_pais(o['pais'])
                if rpa != '??' and opa != '??':
                    pais_t += 1
                    if rpa == opa: pais_m += 1
                rc, oc = norm_cor(r['cor']), norm_cor(o['cor'])
                if rc != '??' and oc != '??':
                    cor_t += 1
                    if rc == oc: cor_m += 1

        comp = f"{len(items)}/1000"
        tip = f"{tipo_m/tipo_t*100:.0f}%" if tipo_t else "-"
        pro = f"{prod_m/prod_t*100:.0f}%" if prod_t else "-"
        vin = f"{vin_m/vin_t*100:.0f}%" if vin_t else "-"
        pai = f"{pais_m/pais_t*100:.0f}%" if pais_t else "-"
        co = f"{cor_m/cor_t*100:.0f}%" if cor_t else "-"
        print(f"  {ia_name:15s} {comp:>8s} {tip:>8s} {pro:>10s} {vin:>10s} {pai:>8s} {co:>8s}")

if __name__ == '__main__':
    compare_ias()
