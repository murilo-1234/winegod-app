"""Gera os 10 prompts X1-X10 a partir do template base."""
import os

GROUPS = {
    1: {'countries': ['us'], 'count': 784300},
    2: {'countries': ['br', 'au'], 'count': 394442},
    3: {'countries': ['gb', 'it'], 'count': 301317},
    4: {'countries': ['de', 'nl', 'dk'], 'count': 366720},
    5: {'countries': ['ar', 'hk', 'mx'], 'count': 324578},
    6: {'countries': ['pt', 'fr', 'nz', 'es'], 'count': 361515},
    7: {'countries': ['sg', 'ca', 'ph', 'at', 'ie'], 'count': 374052},
    8: {'countries': ['pe', 'be', 'ch', 'pl', 'uy'], 'count': 317625},
    9: {'countries': ['za', 'gr', 'ro', 'cl', 'se', 'md', 'in'], 'count': 340745},
    10: {'countries': ['co', 'fi', 'hu', 'jp', 'lu', 'bg', 'ru', 'il', 'ge', 'cz', 'cn', 'ae', 'kr', 'no', 'hr', 'tw', 'tr', 'th'], 'count': 326330},
}

# Read template
with open('prompts/PROMPT_CHAT_X_BASE.md', 'r', encoding='utf-8') as f:
    template = f.read()

for gnum, gdata in GROUPS.items():
    countries = gdata['countries']
    country_list = ', '.join(c.upper() for c in countries)
    country_sql = ', '.join(f"'{c}'" for c in countries)

    content = template.replace('{GROUP_NUM}', str(gnum))
    content = content.replace('{COUNTRY_LIST}', country_list)
    content = content.replace('{COUNTRY_SQL}', country_sql)

    outpath = f'prompts/PROMPT_CHAT_X{gnum}.md'
    with open(outpath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'Gerado: {outpath} | Paises: {country_list} | ~{gdata["count"]:,} vinhos')

print(f'\n10 prompts gerados em prompts/PROMPT_CHAT_X1.md a X10.md')
