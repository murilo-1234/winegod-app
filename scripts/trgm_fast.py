"""Match Vivino RAPIDO: busca exata por produtor + overlap de vinho no Python."""
import sys, time, re
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import psycopg2

DB = dict(host="localhost", port=5432, dbname="winegod_db",
          user="postgres", password="postgres123",
          options="-c client_encoding=UTF8")
BATCH = 1000

conn = psycopg2.connect(**DB)
conn.autocommit = False
cur = conn.cursor()
cur2 = conn.cursor()

# Contar
cur.execute("SELECT COUNT(*) FROM y2_results WHERE status='pending_match' AND prod_banco IS NOT NULL AND prod_banco != '' AND prod_banco != '??'")
total = cur.fetchone()[0]
print(f"Pendentes: {total}")

# Pre-carregar TODOS os produtores do Vivino em memoria (~200K produtores)
print("Carregando produtores do Vivino...", flush=True)
cur.execute("SELECT id, produtor_normalizado, nome_normalizado FROM vivino_match WHERE produtor_normalizado IS NOT NULL AND produtor_normalizado != ''")
vivino_by_prod = {}
for vid, vprod, vnome in cur:
    if vprod not in vivino_by_prod:
        vivino_by_prod[vprod] = []
    vivino_by_prod[vprod].append((vid, vnome))
print(f"  {len(vivino_by_prod)} produtores unicos carregados")

# Tambem indexar por palavras-chave do produtor (pra match parcial)
prod_word_index = {}
for prod in vivino_by_prod:
    for word in prod.split():
        if len(word) >= 4:
            if word not in prod_word_index:
                prod_word_index[word] = set()
            prod_word_index[word].add(prod)
print(f"  {len(prod_word_index)} palavras indexadas")

done = 0; matched = 0; new = 0
start = time.time()

while True:
    cur2.execute("""
        SELECT id, prod_banco, vinho_banco
        FROM y2_results
        WHERE status = 'pending_match'
        AND prod_banco IS NOT NULL AND prod_banco != '' AND prod_banco != '??'
        LIMIT %s
    """, (BATCH,))
    rows = cur2.fetchall()
    if not rows:
        break

    updates_matched = []
    updates_new = []

    for row_id, prod, vin in rows:
        if not vin:
            vin = ""
        best_vid = None
        best_score = 0
        best_prod = ""
        best_nome = ""

        # Estrategia 1: produtor exato
        candidates = vivino_by_prod.get(prod, [])

        # Estrategia 2: produtor contem ou esta contido
        if not candidates:
            for vp in vivino_by_prod:
                if prod in vp or vp in prod:
                    candidates.extend(vivino_by_prod[vp])
                    if len(candidates) > 50: break

        # Estrategia 3: palavra mais longa do produtor
        if not candidates:
            prod_words = [w for w in prod.split() if len(w) >= 4]
            if prod_words:
                longest = max(prod_words, key=len)
                matching_prods = prod_word_index.get(longest, set())
                for mp in list(matching_prods)[:20]:
                    candidates.extend(vivino_by_prod[mp])

        if not candidates:
            updates_new.append(row_id)
            new += 1
            continue

        # Scoring: overlap de palavras do vinho
        vin_words = set(vin.split()) - {"de","du","la","le","les","des","del","di","the","and","et"}
        vin_words = {w for w in vin_words if len(w) >= 3}

        for vid, vnome in candidates:
            vnome_words = set(vnome.split()) - {"de","du","la","le","les","des","del","di","the","and","et"}
            vnome_words = {w for w in vnome_words if len(w) >= 3}

            if vin_words and vnome_words:
                overlap = len(vin_words & vnome_words)
                total_w = max(len(vin_words), len(vnome_words))
                score = overlap / total_w if total_w > 0 else 0
            elif vin in vnome or vnome in vin:
                score = 0.5
            else:
                score = 0

            # Bonus: produtor exato
            if prod in vivino_by_prod and candidates == vivino_by_prod[prod]:
                score += 0.3

            if score > best_score:
                best_score = score
                best_vid = vid
                best_prod = prod
                best_nome = vnome

        if best_vid and best_score >= 0.2:
            updates_matched.append((best_vid, prod, best_nome, round(best_score, 3), row_id))
            matched += 1
        else:
            updates_new.append(row_id)
            new += 1

    # Batch UPDATE
    if updates_matched:
        cur2.executemany("""UPDATE y2_results SET vivino_id=%s, vivino_produtor=%s, vivino_nome=%s,
                          match_score=%s, status='matched' WHERE id=%s""", updates_matched)
    if updates_new:
        cur2.executemany("UPDATE y2_results SET status='new' WHERE id=%s", [(rid,) for rid in updates_new])

    conn.commit()
    done += len(rows)

    elapsed = time.time() - start
    speed = done / elapsed if elapsed > 0 else 0
    remaining = (total - done) / speed / 60 if speed > 0 else 0
    pct = done * 100 // total
    print(f"  {done:>7}/{total} ({pct}%) | match={matched} new={new} | {speed:.0f}/seg | ETA {remaining:.0f}min", flush=True)

conn.close()
print(f"\nFINALIZADO em {(time.time()-start)/60:.1f} min | matched={matched} new={new}")
