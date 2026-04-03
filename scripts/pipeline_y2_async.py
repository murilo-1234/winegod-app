"""
Pipeline Y2 ASYNC: Gemini Flash via REST API com aiohttp.
200 chamadas concorrentes de verdade (sem threads, sem GIL).
"""
import asyncio, aiohttp, csv, os, time, re, sys, json, threading
from datetime import datetime
from flask import Flask, jsonify, render_template_string
import psycopg2

# === CONFIG ===
API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"
BATCH_SIZE = 20
CONCURRENCY = 200  # chamadas simultaneas reais
DB_HOST = "localhost"
DB_PORT = 5432
DB_NAME = "winegod_db"
DB_USER = "postgres"
DB_PASS = "postgres123"
PORT = 8050

# === GLOBALS ===
app = Flask(__name__)
state = {
    "status": "stopped",
    "started_at": None,
    "total_items": 0,
    "processed": 0,
    "wines": 0,
    "not_wine": 0,
    "spirits": 0,
    "duplicates": 0,
    "unique_wines": 0,
    "match_vivino": 0,
    "match_errado": 0,
    "wine_new": 0,
    "errors": 0,
    "batches_total": 0,
    "batches_done": 0,
    "items_per_sec": 0,
    "eta_minutes": 0,
}
stop_flag = False

PROMPT = """Exemplos do nosso banco:
  produtor: "chateau levangile"  vinho: "pomerol"
  produtor: "campo viejo"  vinho: "reserva rioja"
  produtor: "penfolds"  vinho: "grange shiraz"

TODOS os itens. Uma linha por item. Sem markdown.

Formato:
1. X
2. S
3. W|ProdBanco|VinhoBanco|Pais|Cor
4. W|ProdBanco|VinhoBanco|Pais|Cor|=3

ProdBanco/VinhoBanco = minusculo, sem acento, l' junto, saint junto.
=M=duplicata. X=nao vinho. S=destilado. ??=nao sabe. NAO invente.

"""

def norm(s):
    s = s.lower().strip()
    for o, n in [("\u00e1","a"),("\u00e0","a"),("\u00e2","a"),("\u00e3","a"),("\u00e4","a"),
                 ("\u00e9","e"),("\u00e8","e"),("\u00ea","e"),("\u00eb","e"),
                 ("\u00ed","i"),("\u00ec","i"),("\u00ee","i"),("\u00ef","i"),
                 ("\u00f3","o"),("\u00f2","o"),("\u00f4","o"),("\u00f5","o"),("\u00f6","o"),
                 ("\u00fa","u"),("\u00f9","u"),("\u00fb","u"),("\u00fc","u"),
                 ("\u00f1","n"),("\u00e7","c")]:
        s = s.replace(o, n)
    s = re.sub(r"['\u2019\u2018`]", "", s)
    s = re.sub(r"-", "", s)
    s = re.sub(r"[^a-z0-9 ]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def parse_llm(text):
    m = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line: continue
        p = line.split(". ", 1)
        if len(p) == 2 and p[0].strip().isdigit():
            m[int(p[0].strip())] = p[1].strip()
    return m

def get_db():
    return psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
                            user=DB_USER, password=DB_PASS,
                            options="-c client_encoding=UTF8")

def setup_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS y2_results (
            id SERIAL PRIMARY KEY,
            clean_id INTEGER,
            loja_nome TEXT,
            classificacao VARCHAR(1),
            prod_banco TEXT,
            vinho_banco TEXT,
            pais VARCHAR(5),
            cor VARCHAR(1),
            duplicata_de INTEGER,
            vivino_id INTEGER,
            vivino_produtor TEXT,
            vivino_nome TEXT,
            match_score REAL,
            status VARCHAR(20),
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_y2_clean_id ON y2_results(clean_id);
        CREATE INDEX IF NOT EXISTS idx_y2_status ON y2_results(status);
    """)
    conn.commit()
    conn.close()


def load_items_and_skip_done():
    """Carrega todos os itens, pula os ja processados."""
    conn = get_db()
    cur = conn.cursor()

    # IDs ja processados
    cur.execute("SELECT clean_id FROM y2_results")
    done = set(r[0] for r in cur.fetchall())
    print(f"  Ja processados: {len(done)}")

    # Total
    cur.execute("SELECT COUNT(*) FROM wines_clean")
    total = cur.fetchone()[0]

    # Carregar tudo em ordem (server-side cursor)
    conn.autocommit = False
    cur2 = conn.cursor(name="load_all")
    cur2.itersize = 10000
    cur2.execute("SELECT id, nome_normalizado FROM wines_clean ORDER BY nome_normalizado")

    items = []
    for row in cur2:
        if row[0] not in done:
            items.append({"clean_id": row[0], "loja_nome": row[1] or ""})

    cur2.close()
    conn.close()
    print(f"  Itens a processar: {len(items)}")
    return items, total, len(done)


async def call_gemini(session, items, semaphore):
    """Chama Gemini REST API com controle de concorrencia."""
    txt = "\n".join(f"{i+1}. {it['loja_nome']}" for i, it in enumerate(items))

    payload = {
        "contents": [{"parts": [{"text": PROMPT + txt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 4096}
    }

    async with semaphore:
        for attempt in range(3):
            try:
                async with session.post(GEMINI_URL, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        text = data["candidates"][0]["content"]["parts"][0]["text"]
                        lines = parse_llm(text)
                        if len(lines) >= len(items) * 0.5:
                            return lines
                    elif resp.status == 429:
                        await asyncio.sleep(2)
                    else:
                        await asyncio.sleep(1)
            except Exception:
                await asyncio.sleep(1)

    return {}


def save_results(conn, items, lines):
    """Salva resultados no banco."""
    cur = conn.cursor()
    results_summary = {"W": 0, "X": 0, "S": 0, "dup": 0, "err": 0, "pending": 0}

    for i, item in enumerate(items):
        llm = lines.get(i + 1, "MISSING")
        cid = item["clean_id"]
        loja = item["loja_nome"]

        if llm.startswith("X"):
            results_summary["X"] += 1
            cur.execute("INSERT INTO y2_results (clean_id,loja_nome,classificacao,status) VALUES (%s,%s,'X','not_wine') ON CONFLICT DO NOTHING", (cid, loja))

        elif llm.startswith("S"):
            results_summary["S"] += 1
            cur.execute("INSERT INTO y2_results (clean_id,loja_nome,classificacao,status) VALUES (%s,%s,'S','spirit') ON CONFLICT DO NOTHING", (cid, loja))

        elif llm.startswith("W"):
            parts = llm.split("|")
            if len(parts) < 5:
                results_summary["err"] += 1
                cur.execute("INSERT INTO y2_results (clean_id,loja_nome,classificacao,status) VALUES (%s,%s,'W','error') ON CONFLICT DO NOTHING", (cid, loja))
                continue

            prod = norm(parts[1].strip().split("=")[0].strip())
            vin = norm(parts[2].strip().split("=")[0].strip())
            pais = parts[3].strip()[:5] if len(parts) > 3 else "??"
            cor = parts[4].strip()[:1] if len(parts) > 4 else "?"
            is_dup = "=" in llm
            dup_ref = None
            if is_dup:
                try:
                    ref = llm.split("=")[-1].strip()
                    dup_ref = int(ref) if ref.isdigit() else None
                except:
                    pass

            status = "duplicate" if is_dup else "pending_match"
            if is_dup:
                results_summary["dup"] += 1
            else:
                results_summary["pending"] += 1
            results_summary["W"] += 1

            cur.execute("""INSERT INTO y2_results (clean_id,loja_nome,classificacao,prod_banco,vinho_banco,pais,cor,duplicata_de,status)
                          VALUES (%s,%s,'W',%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                       (cid, loja, prod, vin, pais, cor, dup_ref, status))
        else:
            results_summary["err"] += 1

    conn.commit()
    return results_summary


async def run_pipeline_async():
    """Pipeline principal com asyncio. Streaming — nao carrega tudo em memoria."""
    global state, stop_flag

    conn_load = get_db()
    cur = conn_load.cursor()

    # IDs ja feitos (set em memoria ~84K = ~1MB)
    cur.execute("SELECT clean_id FROM y2_results")
    done_ids = set(r[0] for r in cur.fetchall())
    already_done = len(done_ids)

    cur.execute("SELECT COUNT(*) FROM wines_clean")
    total = cur.fetchone()[0]
    conn_load.close()

    state["total_items"] = total
    state["processed"] = already_done
    state["batches_total"] = (total - already_done + BATCH_SIZE - 1) // BATCH_SIZE
    state["status"] = "running"
    state["started_at"] = datetime.now().isoformat()

    print(f"  Ja feitos: {already_done} | Restantes: ~{total - already_done}")
    print(f"  Concorrencia: {CONCURRENCY}")

    # Carregar tudo em Python e filtrar (mais rapido que SQL NOT IN)
    conn_ids = get_db()
    cur_ids = conn_ids.cursor()

    print(f"  Carregando itens do banco...", flush=True)
    cur_ids.execute("SELECT id, nome_normalizado FROM wines_clean")
    all_rows = cur_ids.fetchall()
    conn_ids.close()

    todo_items = [{"clean_id": r[0], "loja_nome": r[1] or ""} for r in all_rows if r[0] not in done_ids]
    del all_rows  # liberar memoria

    print(f"  Carregados {len(todo_items)} itens pra processar")

    # Dividir em batches
    batches = [todo_items[i:i+BATCH_SIZE] for i in range(0, len(todo_items), BATCH_SIZE)]
    state["batches_total"] = len(batches)

    conn_save = get_db()
    semaphore = asyncio.Semaphore(CONCURRENCY)
    start_time = time.time()

    async with aiohttp.ClientSession() as session:
        # Processar em chunks de 50 batches
        CHUNK = 50
        for chunk_start in range(0, len(batches), CHUNK):
            if stop_flag:
                break

            chunk = batches[chunk_start:chunk_start + CHUNK]
            tasks = [call_gemini(session, b, semaphore) for b in chunk]
            results = await asyncio.gather(*tasks)

            for batch, lines in zip(chunk, results):
                summary = save_results(conn_save, batch, lines)
                state["wines"] += summary["W"]
                state["not_wine"] += summary["X"]
                state["spirits"] += summary["S"]
                state["duplicates"] += summary["dup"]
                state["wine_new"] += summary["pending"]
                state["errors"] += summary["err"]
                state["processed"] += len(batch)
                state["batches_done"] += 1

            elapsed = time.time() - start_time
            new_items = state["processed"] - already_done
            if elapsed > 0:
                state["items_per_sec"] = round(new_items / elapsed, 1)
            remaining = total - state["processed"]
            if state["items_per_sec"] > 0:
                state["eta_minutes"] = round(remaining / state["items_per_sec"] / 60, 1)

    conn_save.close()
    state["status"] = "completed" if not stop_flag else "stopped"


def start_async_pipeline():
    """Roda o pipeline async numa thread separada."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_pipeline_async())


# === DASHBOARD ===

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>WineGod Pipeline Y2 ASYNC</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:#0D0D1A; color:#E0E0E0; font-family:'Segoe UI',sans-serif; padding:20px; }
  h1 { color:#8B1A4A; margin-bottom:5px; font-size:28px; }
  .subtitle { color:#666; margin-bottom:20px; font-size:14px; }
  .status-bar { display:flex; align-items:center; gap:15px; margin-bottom:25px; }
  .status-badge { padding:6px 16px; border-radius:20px; font-weight:bold; font-size:14px; }
  .status-running { background:#1B5E20; color:#A5D6A7; }
  .status-stopped { background:#4A1A1A; color:#EF9A9A; }
  .status-completed { background:#1A237E; color:#90CAF9; }
  .btn { padding:8px 24px; border:none; border-radius:8px; font-size:14px; cursor:pointer; font-weight:bold; }
  .btn-start { background:#2E7D32; color:white; }
  .btn-stop { background:#C62828; color:white; }
  .progress-container { background:#1A1A2E; border-radius:12px; padding:20px; margin-bottom:25px; border:1px solid #2A2A4E; }
  .progress-bar-bg { background:#2A2A4E; border-radius:8px; height:40px; overflow:hidden; }
  .progress-bar-fill { height:100%; border-radius:8px; transition:width 0.5s; display:flex; align-items:center; justify-content:center; font-weight:bold; font-size:16px; }
  .progress-bar-fill.low { background:linear-gradient(90deg,#C62828,#E53935); }
  .progress-bar-fill.mid { background:linear-gradient(90deg,#E65100,#FF9800); }
  .progress-bar-fill.high { background:linear-gradient(90deg,#2E7D32,#66BB6A); }
  .progress-stats { display:flex; justify-content:space-between; margin-top:10px; font-size:13px; color:#888; }
  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:15px; margin-bottom:25px; }
  .card { background:#1A1A2E; border:1px solid #2A2A4E; border-radius:12px; padding:18px; text-align:center; }
  .card-value { font-size:32px; font-weight:bold; margin:8px 0; }
  .card-label { font-size:12px; color:#888; text-transform:uppercase; letter-spacing:1px; }
  .card-pct { font-size:14px; color:#666; }
  .card.wine .card-value { color:#8B1A4A; }
  .card.match .card-value { color:#2E7D32; }
  .card.new .card-value { color:#1565C0; }
  .card.dup .card-value { color:#FF8F00; }
  .card.notwine .card-value { color:#616161; }
  .card.spirit .card-value { color:#4E342E; }
  .card.error .card-value { color:#C62828; }
  .card.speed .card-value { color:#00ACC1; }
  .section-title { color:#8B1A4A; font-size:18px; margin:20px 0 10px; }
  .eta { color:#00ACC1; font-size:14px; }
</style>
</head>
<body>
<h1>WineGod Pipeline Y2</h1>
<p class="subtitle">ASYNC | Gemini 2.5 Flash | 200 chamadas concorrentes | Fase 1 + Fase 2 background</p>
<div class="status-bar">
  <span id="badge" class="status-badge status-stopped">PARADO</span>
  <button class="btn btn-start" onclick="startPipeline()">START</button>
  <button class="btn btn-stop" onclick="stopPipeline()">STOP</button>
  <span class="eta" id="eta"></span>
</div>
<div class="progress-container">
  <div class="progress-bar-bg">
    <div id="progressBar" class="progress-bar-fill low" style="width:0%">0%</div>
  </div>
  <div class="progress-stats">
    <span id="pProcessed">0 / 0</span>
    <span id="pBatches">0 / 0 batches</span>
    <span id="pSpeed">0 itens/seg</span>
  </div>
</div>
<div class="cards">
  <div class="card wine"><div class="card-label">Vinhos (W)</div><div class="card-value" id="cW">0</div><div class="card-pct" id="cWp"></div></div>
  <div class="card match"><div class="card-label">Match Vivino</div><div class="card-value" id="cM">0</div><div class="card-pct" id="cMp"></div></div>
  <div class="card new"><div class="card-label">Pendente Match</div><div class="card-value" id="cN">0</div><div class="card-pct" id="cNp"></div></div>
  <div class="card dup"><div class="card-label">Duplicatas</div><div class="card-value" id="cD">0</div><div class="card-pct" id="cDp"></div></div>
  <div class="card notwine"><div class="card-label">Nao-Vinho</div><div class="card-value" id="cX">0</div><div class="card-pct" id="cXp"></div></div>
  <div class="card spirit"><div class="card-label">Destilados</div><div class="card-value" id="cS">0</div><div class="card-pct" id="cSp"></div></div>
  <div class="card error"><div class="card-label">Erros</div><div class="card-value" id="cE">0</div><div class="card-pct" id="cEp"></div></div>
  <div class="card speed"><div class="card-label">Velocidade</div><div class="card-value" id="cV">0</div><div class="card-pct">itens/seg</div></div>
</div>
<script>
function fmt(n){return n.toLocaleString('pt-BR')}
function pct(n,t){return t>0?Math.round(n*100/t)+'%':''}
function update(){
  fetch('/api/status').then(r=>r.json()).then(d=>{
    document.getElementById('badge').className='status-badge status-'+d.status;
    document.getElementById('badge').textContent={running:'RODANDO',stopped:'PARADO',completed:'COMPLETO'}[d.status]||d.status;
    const p=d.total_items>0?Math.round(d.processed*100/d.total_items):0;
    const bar=document.getElementById('progressBar');
    bar.style.width=p+'%';bar.textContent=p+'%';
    bar.className='progress-bar-fill '+(p<33?'low':p<66?'mid':'high');
    document.getElementById('pProcessed').textContent=fmt(d.processed)+' / '+fmt(d.total_items);
    document.getElementById('pBatches').textContent=fmt(d.batches_done)+' / '+fmt(d.batches_total)+' batches';
    document.getElementById('pSpeed').textContent=d.items_per_sec+' itens/seg';
    document.getElementById('eta').textContent=d.eta_minutes>0?'ETA: '+Math.round(d.eta_minutes)+' min':'';
    const t=d.processed||1;const w=d.wines||1;
    document.getElementById('cW').textContent=fmt(d.wines);document.getElementById('cWp').textContent=pct(d.wines,t);
    document.getElementById('cM').textContent=fmt(d.match_vivino);document.getElementById('cMp').textContent=pct(d.match_vivino,w);
    document.getElementById('cN').textContent=fmt(d.wine_new);document.getElementById('cNp').textContent=pct(d.wine_new,w);
    document.getElementById('cD').textContent=fmt(d.duplicates);document.getElementById('cDp').textContent=pct(d.duplicates,w);
    document.getElementById('cX').textContent=fmt(d.not_wine);document.getElementById('cXp').textContent=pct(d.not_wine,t);
    document.getElementById('cS').textContent=fmt(d.spirits);document.getElementById('cSp').textContent=pct(d.spirits,t);
    document.getElementById('cE').textContent=fmt(d.errors);document.getElementById('cEp').textContent=pct(d.errors,t);
    document.getElementById('cV').textContent=d.items_per_sec;
  });
}
function startPipeline(){fetch('/api/start',{method:'POST'}).then(()=>update())}
function stopPipeline(){fetch('/api/stop',{method:'POST'}).then(()=>update())}
setInterval(update,2000);update();
</script>
</body>
</html>
"""

@app.route("/")
def dashboard():
    return render_template_string(DASHBOARD_HTML)

@app.route("/api/status")
def api_status():
    return jsonify(state)

@app.route("/api/start", methods=["POST"])
def api_start():
    global stop_flag
    if state["status"] == "running":
        return jsonify({"error": "ja rodando"})
    stop_flag = False
    t = threading.Thread(target=start_async_pipeline, daemon=True)
    t.start()
    # Fase 2 background
    t2 = threading.Thread(target=run_vivino_match, daemon=True)
    t2.start()
    return jsonify({"ok": True})

@app.route("/api/stop", methods=["POST"])
def api_stop():
    global stop_flag
    stop_flag = True
    state["status"] = "stopped"
    return jsonify({"ok": True})


def run_vivino_match():
    """Fase 2: Match Vivino em background."""
    THRESHOLD = 0.30
    conn = get_db()
    cur = conn.cursor()

    while not stop_flag:
        cur.execute("""
            SELECT id, prod_banco, vinho_banco
            FROM y2_results
            WHERE status = 'pending_match'
            AND prod_banco IS NOT NULL AND prod_banco != '' AND prod_banco != '??'
            LIMIT 100
        """)
        rows = cur.fetchall()
        if not rows:
            time.sleep(5)
            continue

        for row_id, prod, vin in rows:
            if stop_flag: break
            search = f"{prod} {vin}".strip()
            if len(search) < 4:
                cur.execute("UPDATE y2_results SET status='new' WHERE id=%s", (row_id,))
                continue
            cur.execute("""
                SELECT id, produtor_normalizado, nome_normalizado,
                       similarity(texto_busca, %s) as ts
                FROM vivino_match WHERE texto_busca %% %s
                ORDER BY similarity(texto_busca, %s) DESC LIMIT 1
            """, (search, search, search))
            cand = cur.fetchone()
            if cand and cand[3] >= THRESHOLD:
                cur.execute("UPDATE y2_results SET vivino_id=%s, vivino_produtor=%s, vivino_nome=%s, match_score=%s, status='matched' WHERE id=%s",
                           (cand[0], cand[1], cand[2], round(cand[3], 3), row_id))
                state["match_vivino"] += 1
                state["wine_new"] -= 1
            else:
                cur.execute("UPDATE y2_results SET status='new' WHERE id=%s", (row_id,))
        conn.commit()

    conn.close()


if __name__ == "__main__":
    setup_db()

    # Carregar stats do banco
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT status, COUNT(*) FROM y2_results GROUP BY status")
    stats = dict(cur.fetchall())
    cur.execute("SELECT COUNT(*) FROM wines_clean")
    state["total_items"] = cur.fetchone()[0]
    conn.close()

    state["match_vivino"] = stats.get("matched", 0)
    state["wine_new"] = stats.get("new", 0) + stats.get("pending_match", 0)
    state["not_wine"] = stats.get("not_wine", 0)
    state["spirits"] = stats.get("spirit", 0)
    state["duplicates"] = stats.get("duplicate", 0)
    state["errors"] = stats.get("error", 0)
    state["wines"] = state["match_vivino"] + state["wine_new"] + state["duplicates"]
    state["processed"] = state["wines"] + state["not_wine"] + state["spirits"] + state["errors"]

    print(f"\n  Dashboard: http://localhost:{PORT}")
    print(f"  Modelo: {MODEL}")
    print(f"  Concorrencia: {CONCURRENCY}")
    print(f"  Ja processados: {state['processed']}")
    print(f"  Restantes: {state['total_items'] - state['processed']}\n")
    app.run(host="0.0.0.0", port=PORT, debug=False)
