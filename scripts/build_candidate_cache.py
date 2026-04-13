"""
Demanda 6C -- Build cache persistente por chave para os 6 canais D5.

READ-ONLY na producao. Escreve somente um SQLite local em reports/.

Estrategia:
  1) Seleciona um slice de render_wine_ids (via D6A.select_pilot()).
  2) Fetch source info de cada wine (chunked, 1 round-trip grande ao Render).
  3) Para cada canal da D5, computa a chave de cache do wine.
  4) Deduplica chaves no conjunto de wines selecionados.
  5) Para cada chave distinta, dispara a MESMA query da D5 uma unica vez e
     serializa o resultado como JSON no SQLite.

As queries disparadas aqui usam diretamente as funcoes `bcc.channel_*` da
Demanda 5, com o mesmo `similarity_threshold = 0.10`, o mesmo TEMP TABLE
`_only_vivino`, a mesma ordem de `LIMIT`, e os mesmos campos do candidato.
Zero drift.

Uso:
  python scripts/build_candidate_cache.py --slice 250 --out reports/candidate_cache_slice250.sqlite3
  python scripts/build_candidate_cache.py --slice 250 --workers 16

Tabelas SQLite:
  cache_render_nome_produtor (key TEXT PRIMARY KEY, payload_json TEXT)
  cache_render_nome          (key TEXT PRIMARY KEY, payload_json TEXT)
  cache_render_produtor      (key TEXT PRIMARY KEY, payload_json TEXT)
  cache_import_nome_produtor (key TEXT PRIMARY KEY, payload_json TEXT)
  cache_import_nome          (key TEXT PRIMARY KEY, payload_json TEXT)
  cache_import_produtor      (key TEXT PRIMARY KEY, payload_json TEXT)

O key format e texto puro para canais single-anchor, e
`nome_anchor || '\x1f' || prod_anchor` para `import_nome_produtor`.

Payload format: JSON list de dicts. Cada dict contem os campos necessarios
ao `score_candidate` e ao detail output (id, nome_normalizado,
produtor_normalizado, safra, tipo, pais).
"""

import argparse
import json
import os
import queue
import sqlite3
import sys
import threading
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_candidate_controls as bcc  # noqa: E402
import run_candidate_fanout_pilot as d6a_runner  # noqa: E402
import run_candidate_fanout_fast as fast_runner  # noqa: E402


REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports")


# ---------- chaves ----------

KEY_SEP = "\x1f"


def key_for(channel, store):
    """Computa a chave de cache para um (channel, store). None se a D5
    nao dispararia query para este wine neste canal."""
    nome = (store.get("nome_normalizado") or "").strip()
    prod = (store.get("produtor_normalizado") or "").strip()

    if channel == "render_nome_produtor":
        if not nome and not prod:
            return None
        return f"{prod} {nome}".strip()

    if channel == "render_nome":
        return nome if len(nome) >= 3 else None

    if channel == "render_produtor":
        return prod if len(prod) >= 3 else None

    nome_anchor = bcc.longest_word(nome, min_len=4)
    prod_anchor = bcc.longest_word(prod, min_len=3)

    if channel == "import_nome_produtor":
        if not nome_anchor or not prod_anchor:
            return None
        return f"{nome_anchor}{KEY_SEP}{prod_anchor}"

    if channel == "import_nome":
        return nome_anchor if nome_anchor else None

    if channel == "import_produtor":
        return prod_anchor if prod_anchor else None

    raise ValueError(f"unknown channel: {channel}")


# Um store sintetico suficiente pra disparar cada channel do D5 so com a chave
def synth_store_for(channel, key):
    """Reconstroi um 'store' com os campos MINIMOS para que bcc.channel_*
    dispare exatamente a mesma query que disparou na primeira vez."""
    if channel == "render_nome_produtor":
        # bcc usa f"{prod} {nome}".strip(). A query SQL e por esse texto unico.
        # Injetamos o texto no slot 'nome_normalizado' e prod vazio; o SQL vai
        # construir f"{} {key}".strip() == key.strip() == key. Mesma query.
        return {"nome_normalizado": key, "produtor_normalizado": ""}
    if channel == "render_nome":
        return {"nome_normalizado": key, "produtor_normalizado": ""}
    if channel == "render_produtor":
        return {"produtor_normalizado": key, "nome_normalizado": ""}
    if channel == "import_nome_produtor":
        nome_anchor, prod_anchor = key.split(KEY_SEP)
        # bcc.longest_word precisa encontrar essas mesmas anchors. Como
        # longest_word retorna a palavra mais longa com len>=N, passar
        # exatamente o anchor como string unica re-produz a mesma anchor.
        return {
            "nome_normalizado": nome_anchor,
            "produtor_normalizado": prod_anchor,
        }
    if channel == "import_nome":
        return {"nome_normalizado": key, "produtor_normalizado": ""}
    if channel == "import_produtor":
        return {"produtor_normalizado": key, "nome_normalizado": ""}
    raise ValueError(f"unknown channel: {channel}")


# ---------- SQLite store ----------

def open_cache(path):
    db = sqlite3.connect(path, isolation_level=None, timeout=30)
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("PRAGMA synchronous = NORMAL")
    for ch in ("render_nome_produtor", "render_nome", "render_produtor",
               "import_nome_produtor", "import_nome", "import_produtor"):
        db.execute(
            f"CREATE TABLE IF NOT EXISTS cache_{ch} (key TEXT PRIMARY KEY, payload_json TEXT NOT NULL)"
        )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS cache_meta (
            k TEXT PRIMARY KEY,
            v TEXT
        )
        """
    )
    return db


def cache_put(db, channel, key, payload):
    db.execute(
        f"INSERT OR REPLACE INTO cache_{channel} (key, payload_json) VALUES (?, ?)",
        (key, json.dumps(payload, ensure_ascii=False)),
    )


def cache_count(db, channel):
    cur = db.execute(f"SELECT COUNT(*) FROM cache_{channel}")
    return cur.fetchone()[0]


# ---------- serializacao de candidatos ----------

def serialize_render_cand(cand):
    return {
        "id": cand["id"],
        "nome_normalizado": cand.get("nome_normalizado"),
        "produtor_normalizado": cand.get("produtor_normalizado"),
        "safra": cand.get("safra"),
        "tipo": cand.get("tipo"),
        "pais": cand.get("pais"),
    }


def serialize_import_cand(cand):
    return {
        "id": cand["id"],
        "nome": cand.get("nome"),
        "produtor": cand.get("produtor"),
        "tipo": cand.get("tipo"),
        "safra": cand.get("safra"),
        "pais": cand.get("pais"),
    }


RENDER_CHANNELS = {
    "render_nome_produtor": (bcc.channel_render_nome_produtor, serialize_render_cand),
    "render_nome":          (bcc.channel_render_nome,          serialize_render_cand),
    "render_produtor":      (bcc.channel_render_produtor,      serialize_render_cand),
}
IMPORT_CHANNELS = {
    "import_nome_produtor": (bcc.channel_import_nome_produtor, serialize_import_cand),
    "import_nome":          (bcc.channel_import_nome,          serialize_import_cand),
    "import_produtor":      (bcc.channel_import_produtor,      serialize_import_cand),
}


# ---------- workers ----------

def worker_render(task_q, result_q):
    conn = bcc.connect_local()
    try:
        cur = conn.cursor()
        cur.execute("SET pg_trgm.similarity_threshold = 0.10")
        while True:
            task = task_q.get()
            if task is None:
                break
            channel, key = task
            try:
                fn, serialize = RENDER_CHANNELS[channel]
                store = synth_store_for(channel, key)
                cands = fn(cur, store)
                payload = [serialize(c) for c in cands]
                result_q.put(("ok", channel, key, payload))
            except Exception as e:
                result_q.put(("err", channel, key, f"{type(e).__name__}: {e}"))
    finally:
        try: conn.close()
        except Exception: pass


def worker_import(task_q, result_q, only_vivino_ids):
    conn = bcc.connect_vivino_db()
    try:
        cur = bcc.setup_only_vivino_temp(conn, only_vivino_ids)
        cur.execute("SET pg_trgm.similarity_threshold = 0.10")
        while True:
            task = task_q.get()
            if task is None:
                break
            channel, key = task
            try:
                fn, serialize = IMPORT_CHANNELS[channel]
                store = synth_store_for(channel, key)
                cands = fn(cur, store)
                payload = [serialize(c) for c in cands]
                result_q.put(("ok", channel, key, payload))
            except Exception as e:
                result_q.put(("err", channel, key, f"{type(e).__name__}: {e}"))
    finally:
        try: conn.close()
        except Exception: pass


# ---------- main ----------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slice", type=int, default=250,
                        help="Quantos render_wine_ids do piloto processar")
    parser.add_argument("--workers", type=int, default=16,
                        help="Workers por pool (1 pool Render local + 1 pool vivino)")
    parser.add_argument("--out", type=str,
                        default=os.path.join(REPORT_DIR, "candidate_cache_slice250.sqlite3"))
    args = parser.parse_args()

    # selecionar slice
    pilot_ids, _ = d6a_runner.select_pilot()
    slice_ids = pilot_ids[:args.slice]
    print(f"[slice] {len(slice_ids):,} wines: {slice_ids[0]} .. {slice_ids[-1]}")

    # source info via fast runner (1 query Render)
    print(f"[prefetch] source info...")
    t0 = time.time()
    source_info = fast_runner.prefetch_source_info(slice_ids)
    print(f"[prefetch] {len(source_info):,} rows em {time.time()-t0:.1f}s")

    # bootstrap only_vivino
    print(f"[boot] vivino_db only set...")
    t0 = time.time()
    rset = bcc.bootstrap_render_vivino_id_set()
    only_vivino = bcc.bootstrap_only_vivino_db_set(rset)
    print(f"[boot] done {time.time()-t0:.1f}s  (only_vivino_db size={len(only_vivino):,})")

    # enumerar chaves distintas por canal
    unique_keys = {ch: set() for ch in (*RENDER_CHANNELS.keys(), *IMPORT_CHANNELS.keys())}
    for wid in slice_ids:
        store = source_info.get(wid)
        if not store:
            continue
        for ch in unique_keys:
            k = key_for(ch, store)
            if k is not None:
                unique_keys[ch].add(k)

    print(f"[keys distintas no slice]")
    total_work = 0
    for ch, kset in unique_keys.items():
        print(f"  {ch:24s}: {len(kset):>6,}")
        total_work += len(kset)
    print(f"  TOTAL de SQL-calls a fazer: {total_work:,}")

    # Abrir cache SQLite
    print(f"[cache] abrindo {args.out}")
    if os.path.exists(args.out):
        os.remove(args.out)
    db = open_cache(args.out)

    # Render pool
    print(f"[pool] {args.workers} workers Render local")
    render_task_q = queue.Queue()
    render_result_q = queue.Queue()
    for ch in RENDER_CHANNELS:
        for k in unique_keys[ch]:
            render_task_q.put((ch, k))
    render_submitted = render_task_q.qsize()
    render_threads = [
        threading.Thread(target=worker_render, args=(render_task_q, render_result_q), daemon=True)
        for _ in range(args.workers)
    ]
    for t in render_threads:
        t.start()

    # Import pool (precisa do only_vivino)
    print(f"[pool] {args.workers} workers Import vivino_db")
    import_task_q = queue.Queue()
    import_result_q = queue.Queue()
    for ch in IMPORT_CHANNELS:
        for k in unique_keys[ch]:
            import_task_q.put((ch, k))
    import_submitted = import_task_q.qsize()
    import_threads = [
        threading.Thread(
            target=worker_import, args=(import_task_q, import_result_q, only_vivino), daemon=True
        )
        for _ in range(args.workers)
    ]
    for t in import_threads:
        t.start()

    # Coletar
    t_render0 = time.time()
    render_collected = 0
    render_errors = 0
    while render_collected + render_errors < render_submitted:
        status, channel, key, payload = render_result_q.get()
        if status == "ok":
            cache_put(db, channel, key, payload)
            render_collected += 1
            if render_collected % 200 == 0:
                print(f"  [render] {render_collected:,}/{render_submitted:,} "
                      f"({(time.time()-t_render0):.0f}s)")
        else:
            render_errors += 1
            print(f"  [render ERR] {channel} key={key!r} : {payload}")
    render_time = time.time() - t_render0
    print(f"[pool render] {render_collected:,} chaves em {render_time:.1f}s "
          f"({render_time/max(render_collected,1)*1000:.0f}ms/key)")

    for _ in render_threads:
        render_task_q.put(None)
    for t in render_threads:
        t.join(timeout=5)

    t_import0 = time.time()
    import_collected = 0
    import_errors = 0
    while import_collected + import_errors < import_submitted:
        status, channel, key, payload = import_result_q.get()
        if status == "ok":
            cache_put(db, channel, key, payload)
            import_collected += 1
            if import_collected % 200 == 0:
                print(f"  [import] {import_collected:,}/{import_submitted:,} "
                      f"({(time.time()-t_import0):.0f}s)")
        else:
            import_errors += 1
            print(f"  [import ERR] {channel} key={key!r} : {payload}")
    import_time = time.time() - t_import0
    print(f"[pool import] {import_collected:,} chaves em {import_time:.1f}s "
          f"({import_time/max(import_collected,1)*1000:.0f}ms/key)")

    for _ in import_threads:
        import_task_q.put(None)
    for t in import_threads:
        t.join(timeout=5)

    # Meta
    db.execute("INSERT OR REPLACE INTO cache_meta (k, v) VALUES (?, ?)",
               ("slice_size", str(len(slice_ids))))
    db.execute("INSERT OR REPLACE INTO cache_meta (k, v) VALUES (?, ?)",
               ("first_id", str(slice_ids[0])))
    db.execute("INSERT OR REPLACE INTO cache_meta (k, v) VALUES (?, ?)",
               ("last_id", str(slice_ids[-1])))
    db.execute("INSERT OR REPLACE INTO cache_meta (k, v) VALUES (?, ?)",
               ("built_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    db.execute("INSERT OR REPLACE INTO cache_meta (k, v) VALUES (?, ?)",
               ("render_build_sec", str(round(render_time, 3))))
    db.execute("INSERT OR REPLACE INTO cache_meta (k, v) VALUES (?, ?)",
               ("import_build_sec", str(round(import_time, 3))))

    print()
    print(f"[cache counts]")
    for ch in (*RENDER_CHANNELS.keys(), *IMPORT_CHANNELS.keys()):
        print(f"  cache_{ch:24s}: {cache_count(db, ch):,}")
    print()
    print(f"Cache file: {args.out}")
    print(f"Render build: {render_time:.1f}s, Import build: {import_time:.1f}s, total {render_time + import_time:.1f}s")

    db.close()


if __name__ == "__main__":
    main()
