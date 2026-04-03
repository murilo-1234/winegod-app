"""Gera os 8 prompts Y1-Y8 a partir do template base."""

total = 2942304
n_groups = 8
chunk = total // n_groups

RANGES = []
for i in range(n_groups):
    id_start = i * chunk + 1
    id_end = (i + 1) * chunk if i < n_groups - 1 else total
    RANGES.append((i + 1, id_start, id_end))

with open('prompts/PROMPT_CHAT_Y_BASE.md', 'r', encoding='utf-8') as f:
    template = f.read()

for gnum, id_start, id_end in RANGES:
    chunk_size = id_end - id_start + 1
    content = template.replace('{GROUP_NUM}', str(gnum))
    content = content.replace('{ID_START}', str(id_start))
    content = content.replace('{ID_END}', str(id_end))
    content = content.replace('{CHUNK_SIZE}', f'{chunk_size:,}')

    outpath = f'prompts/PROMPT_CHAT_Y{gnum}.md'
    with open(outpath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'Gerado: {outpath} | IDs {id_start:>9,} a {id_end:>9,} | ~{chunk_size:,} vinhos')

print(f'\n{n_groups} prompts gerados em prompts/PROMPT_CHAT_Y1.md a Y{n_groups}.md')
