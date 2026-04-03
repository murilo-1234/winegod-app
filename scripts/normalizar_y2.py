"""
Normalização da y2_results para alinhar com o formato do Render (wines).
Campos: pais, safra, abv, regiao, denominacao, uva, harmonizacao.
"""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import psycopg2, re, json

conn = psycopg2.connect(host='localhost', port=5432, dbname='winegod_db',
                        user='postgres', password='postgres123')
conn.autocommit = False
cur = conn.cursor()

total_updates = 0

def run_updates(campo, mapping, set_null_list=None):
    """Roda UPDATEs em batch pra um campo."""
    global total_updates
    count = 0
    for target, sources in mapping.items():
        if not sources:
            continue
        placeholders = ','.join(['%s'] * len(sources))
        cur.execute(f"UPDATE y2_results SET {campo} = %s WHERE {campo} IN ({placeholders})",
                    [target] + list(sources))
        count += cur.rowcount
    if set_null_list:
        placeholders = ','.join(['%s'] * len(set_null_list))
        cur.execute(f"UPDATE y2_results SET {campo} = NULL WHERE {campo} IN ({placeholders})",
                    list(set_null_list))
        count += cur.rowcount
    conn.commit()
    total_updates += count
    print(f"  {campo}: {count:,} registros atualizados")
    return count


# ============================================================
# 1. PAIS → ISO 2 letras minúsculo (como Render)
# ============================================================
print("=== 1. PAIS ===")

pais_map = {
    'fr': ['franc','Franc','franç','Franç','france','fra','FRA','frank','Frank','frenc','FR',
           'jura','cahor','cotes'],
    'it': ['itali','Itali','italy','Italy','itáli','Itáli','ita','IT','ITA'],
    'us': ['usa','USA','eua','EUA','Eua','estad','Estad','unite','ameri','calif','eeuu',
           'US','orego','virgi'],
    'ar': ['argen','Argen','AR','ARG','arg','bonar'],
    'pt': ['portu','Portu','PT','POR','por'],
    'es': ['espan','Espan','spain','Spain','españ','Españ','ESP','esp','ES','spani','Spagn'],
    'au': ['austr','Austr','AU','AUS','aus','SE AU','NSW','VIC','TASMA'],
    'de': ['alema','Alema','germa','Germa','DE','deuts','Deuts','oster','rhein'],
    'cl': ['chile','Chile','CL','CHI','chi','chili'],
    'za': ['afric','Afric','south','South','sudaf','sulaf','sydaf','saf','SAF',
            'áfric','Áfric','afri','afr','SA'],
    'nz': ['nova','Nova','novaz','NovaZ','NZ','new z','New Z','newze','NZL',
            'nova_','neo z','nueva','Nueva','nuova','hawke'],
    'br': ['brasi','Brasi','BR','BRA','bra','brazi','Brazi'],
    'ca': ['canad','Canad','CA'],
    'hu': ['hungr','Hungr','HU','hunga','Hunga'],
    'gr': ['greci','Greci','GR','greec','Greec','gréci'],
    'ro': ['romen','Romen','roman','Romên','ruman'],
    'il': ['israe','Israe'],
    'uy': ['urugu','Urugu','uru'],
    'bg': ['bulga','Bulga','BG','bulgá'],
    'ch': ['suica','Suica','suíça','Suíça','switz','sui'],
    'gb': ['uk','ingla','Ingla','engla','reino','Reino'],
    'ge': ['georg','Georg','geórg'],
    'jp': ['japao','Japão','Japan','japan','japão','japon','Japao'],
    'lb': ['liban','Liban','LB','leban','Leban','líban','Líban'],
    'md': ['molda','Molda','moldo','Moldo','MD','Moldá'],
    'hr': ['croac','Croac','croat','Croat','Croác'],
    'si': ['eslov','Eslov','slove','Slove','SI'],
    'mx': ['mexic','Mexic','MX','méxic'],
    'at': ['AT','áustr','Áustr','AUT'],
    'cz': ['czech','Czech','ceska','checa','chequ','repub','Repub'],
    'am': ['armen','Armen'],
    'rs': ['servi','Servi','serbi','Serbi','sérvi'],
    'tr': ['turqu','turke'],
    'cn': ['china','China'],
    'cy': ['chipr','cypru'],
    'sk': ['slova','Slova'],
    'ma': ['marro','Marro','moroc'],
    'mk': ['maced'],
    'in': ['india','India'],
    'dk': ['dinam','Dinam','denma','Denma'],
    'se': ['sueci','Sueci','swede'],
    'pl': ['polon','Polan','polan'],
    'be': [],
    'lu': ['luxem'],
    'nl': ['holan'],
    'ie': [],
    'lt': [],
    'fi': ['finla'],
    'ua': ['ucran','Ucran','ukrai'],
    'ba': ['bosni','Bosni'],
    'kr': ['corei','Corei','korea'],
    'pe': ['peru'],
    'ru': ['russi','Russi'],
    'tn': ['tunis'],
    'tw': ['taiwa'],
    'sy': ['siria','syria'],
    'ps': ['pales'],
    'cu': [],
    'me': ['monte'],
    'th': ['taila'],
    'ph': ['filip','phili'],
    'az': ['azerb'],
    'np': [],
    'al': [],
    'sg': [],
    'ir': ['iran'],
    'id': [],
    'bo': ['boliv'],
    'ad': [],
    'ee': [],
}

# Valores que são lixo (não são paises) → NULL
pais_null = [
    'w','r','s','p','f','d','A','E','I',
    'red','red w','red b','blend','cava',
    'malbe','pecor','chard','caber','vermu',
    'casci','pinos','pelle','harel','primi','gener','salin','banno',
    'cofer','impor','caves','nacio','desco','vario','escoc',
    '???','Pais','Mundo','mundo','europ','eu','crime',
    'nao i','nao e','nao s','na','SP','sl',
    'andes','tanna','sa','rhein'  # rhein already mapped to de above, but just in case
]

run_updates('pais', pais_map, pais_null)


# ============================================================
# 2. SAFRA → só anos 4 dígitos, resto NULL
# ============================================================
print("=== 2. SAFRA ===")

# NV → NULL
cur.execute("UPDATE y2_results SET safra = NULL WHERE safra IN ('NV','nv','Safra','ABV','0','??','')")
c = cur.rowcount
conn.commit()

# Valores que parecem ABV (13, 13.5, 12, etc.) ou anos de 2 dígitos → NULL
cur.execute(r"UPDATE y2_results SET safra = NULL WHERE safra IS NOT NULL AND safra !~ '^\d{4}$'")
c += cur.rowcount
conn.commit()
total_updates += c
print(f"  safra: {c:,} registros limpos (NV + nao-ano → NULL)")


# ============================================================
# 3. ABV → limpar texto, só números
# ============================================================
print("=== 3. ABV ===")

# Valores que são classificações (igt, doc, aoc, etc.) → NULL
abv_null = ['NV','nv','igt','igp','doc','reserva','grand cru','docg','aoc','dac','AOC',
            'ABV','do','auslese','dop','kabinett','1er cru','pdo','leve','medio',
            'encorpado','DOC','IGT','DOCG','premier cru','brut','seco','doce',
            'IGP','reserv','crianza','riserva','gran reserva','spatlese','qualitaetswein',
            'trocken','VdP','DOP','praedikatswein','??','']
placeholders = ','.join(['%s'] * len(abv_null))
cur.execute(f"UPDATE y2_results SET abv = NULL WHERE abv IN ({placeholders})", abv_null)
c1 = cur.rowcount

# Remover '%' do final
cur.execute("UPDATE y2_results SET abv = REPLACE(abv, '%', '') WHERE abv LIKE '%%'")
c2 = cur.rowcount

# Valores que não são numéricos após limpeza → NULL
cur.execute(r"UPDATE y2_results SET abv = NULL WHERE abv IS NOT NULL AND abv != '' AND abv !~ '^\d+\.?\d*$'")
c3 = cur.rowcount

conn.commit()
total_updates += c1 + c2 + c3
print(f"  abv: {c1+c2+c3:,} registros limpos (classificacoes removidas, % removido)")


# ============================================================
# 4. REGIAO → Title Case + merge sinônimos
# ============================================================
print("=== 4. REGIAO ===")

# Sinônimos que precisam ser unificados
regiao_map = {
    'Burgundy':   ['burgundy','bourgogne','Bourgogne'],
    'Bordeaux':   ['bordeaux'],
    'Champagne':  ['champagne'],
    'California': ['california'],
    'Douro':      ['douro'],
    'Piemonte':   ['piemonte','piedmont','Piedmont'],
    'Rhône':      ['rhone','rhône','Rhone'],
    'Toscana':    ['toscana','tuscany','Tuscany','toscan'],
    'Veneto':     ['veneto'],
    'Rioja':      ['rioja'],
    'Loire':      ['loire'],
    'Mendoza':    ['mendoza'],
    'Languedoc':  ['languedoc'],
    'Alentejo':   ['alentejo'],
    'Marlborough':['marlborough'],
    'Mosel':      ['mosel'],
    'Napa Valley':['napa valley'],
    'Puglia':     ['puglia'],
    'Beaujolais': ['beaujolais'],
    'Provence':   ['provence'],
    'Barolo':     ['barolo'],
    'Alsace':     ['alsace'],
    'Sicilia':    ['sicily','sicilia','Sicily'],
    'Western Cape':['western cape'],
    'South Australia':['south australia'],
    'Dão':        ['dao'],
    'Friuli':     ['friuli'],
    'Oregon':     ['oregon'],
    'Pfalz':      ['pfalz'],
    'Jura':       ['jura'],
    'Abruzzo':    ['abruzzo'],
    'Ribera del Duero':['ribera del duero'],
    'Vinho Verde':['vinho verde'],
    'Alto Adige': ['alto adige'],
    'Marche':     ['marche'],
}

run_updates('regiao', regiao_map)

# Title Case pro resto (que não foi mapeado acima)
cur.execute("""UPDATE y2_results SET regiao = INITCAP(regiao)
    WHERE regiao IS NOT NULL AND regiao != '' AND regiao = LOWER(regiao)
    AND regiao NOT IN ('??')""")
c = cur.rowcount
conn.commit()
total_updates += c
print(f"  regiao (INITCAP resto): {c:,} registros")


# ============================================================
# 5. DENOMINACAO → uppercase padronizado
# ============================================================
print("=== 5. DENOMINACAO ===")

denom_map = {
    'DOC':    ['doc','Doc'],
    'DOCG':   ['docg','Docg'],
    'AOC':    ['aoc','Aoc'],
    'IGT':    ['igt','Igt'],
    'IGP':    ['igp','Igp'],
    'AVA':    ['ava','Ava'],
    'DOP':    ['dop','Dop'],
    'DAC':    ['dac','Dac'],
    'DO':     ['do','Do'],
    'VdP':    ['vdp','VDP'],
    'Grand Cru':    ['grand cru','grand Cru','GRAND CRU'],
    'Premier Cru':  ['premier cru','1er cru','1er Cru','PREMIER CRU'],
    'Reserva':      ['reserva','RESERVA'],
    'Gran Reserva': ['gran reserva','GRAN RESERVA'],
    'Riserva':      ['riserva','RISERVA'],
    'Crianza':      ['crianza','CRIANZA'],
}

run_updates('denominacao', denom_map)


# ============================================================
# 6. Limpar ?? e strings vazias em todos os campos
# ============================================================
print("=== 6. LIMPEZA GERAL ===")
for campo in ['pais','safra','uva','regiao','subregiao','abv','denominacao','corpo','harmonizacao','docura']:
    cur.execute(f"UPDATE y2_results SET {campo} = NULL WHERE {campo} IN ('??','?','')")
    if cur.rowcount > 0:
        total_updates += cur.rowcount
        print(f"  {campo}: {cur.rowcount:,} '??' limpos")
conn.commit()


# ============================================================
# RESUMO FINAL
# ============================================================
print(f"\n{'='*50}")
print(f"TOTAL: {total_updates:,} registros atualizados")

# Verificação
print("\n=== VERIFICACAO FINAL ===")
for campo in ['pais','cor','safra','regiao','abv','denominacao']:
    cur.execute(f"SELECT {campo}, COUNT(*) FROM y2_results WHERE {campo} IS NOT NULL GROUP BY {campo} ORDER BY COUNT(*) DESC LIMIT 8")
    print(f"\n{campo} TOP 8:")
    for r in cur.fetchall():
        print(f"  {str(r[0]):25s}: {r[1]:>10,}")

conn.close()
print("\nNormalizacao concluida.")
