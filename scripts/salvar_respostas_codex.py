"""
Salva respostas do Codex (resposta_z_NNN.txt) na y2_results + y2_lotes_log.
Usa o mesmo formato de parse e insert do run_edge.py.

Uso:
  python scripts/salvar_respostas_codex.py              # salva todos os resposta_z_*.txt pendentes
  python scripts/salvar_respostas_codex.py 1 2 3        # salva lotes especificos
"""
import sys
import os
import re
import time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import psycopg2

DB = dict(host="localhost", port=5432, dbname="winegod_db",
          user="postgres", password="postgres123",
          options="-c client_encoding=UTF8")

LOTE_DIR = r"C:\winegod-app\lotes_codex"
IA_NAME = "codex_gpt54mini"


def get_db():
    return psycopg2.connect(**DB)


def norm(s):
    if not s:
        return ""
    s = s.lower().strip()
    for o, n in [("á","a"),("à","a"),("â","a"),("ã","a"),("ä","a"),
                 ("é","e"),("è","e"),("ê","e"),("ë","e"),
                 ("í","i"),("ì","i"),("î","i"),("ï","i"),
                 ("ó","o"),("ò","o"),("ô","o"),("õ","o"),("ö","o"),
                 ("ú","u"),("ù","u"),("û","u"),("ü","u"),
                 ("ñ","n"),("ç","c")]:
        s = s.replace(o, n)
    return s.strip()


def qq(val):
    if not val or val.strip() in ("??", "?", ""):
        return None
    return val.strip()


def find_files(lote_num):
    """Encontra arquivos do lote independente da letra (z, x, v, u, t)."""
    for letra in ['z', 'x', 'v', 'u', 't', 'y', 'w', 's', 'r', 'q', 'p', 'o', 'n', 'm', 'l', 'k']:
        resp = os.path.join(LOTE_DIR, f"resposta_{letra}_{lote_num:03d}.txt")
        ids = os.path.join(LOTE_DIR, f"lote_{letra}_{lote_num:03d}_ids.txt")
        lote = os.path.join(LOTE_DIR, f"lote_{letra}_{lote_num:03d}.txt")
        if os.path.exists(resp) and os.path.exists(ids):
            return resp, ids, lote
    return None, None, None


def salvar_lote(lote_num):
    resp_file, ids_file, lote_file = find_files(lote_num)

    if not resp_file:
        print(f"  Lote {lote_num}: resposta NAO encontrada, pulando")
        return 0

    # Ler IDs
    with open(ids_file, encoding="utf-8") as f:
        clean_ids = [int(line.strip()) for line in f if line.strip()]

    # Ler nomes do lote original
    nomes = []
    if os.path.exists(lote_file):
        with open(lote_file, encoding="utf-8") as f:
            for line in f:
                m = re.match(r'^(\d+)\.\s+(.+)', line.strip())
                if m:
                    nomes.append(m.group(2).strip())

    # Ler respostas (strip numeracao tipo "1. ", "2) " etc)
    with open(resp_file, encoding="utf-8") as f:
        respostas = []
        for line in f.readlines():
            line = line.strip()
            line = re.sub(r'^\d+[\.\)]\s+', '', line)
            respostas.append(line)

    print(f"  Lote {lote_num}: {len(respostas)} respostas, {len(clean_ids)} IDs, {len(nomes)} nomes")

    if len(respostas) != len(clean_ids):
        print(f"  AVISO: respostas ({len(respostas)}) != IDs ({len(clean_ids)}), usando o menor")

    n = min(len(respostas), len(clean_ids))
    results = []
    t0 = time.time()

    for i in range(n):
        clean_id = clean_ids[i]
        loja_nome = nomes[i] if i < len(nomes) else ""
        classif = respostas[i].strip()

        r = {
            "clean_id": clean_id, "loja_nome": loja_nome,
            "classificacao": None, "prod_banco": None, "vinho_banco": None,
            "pais": None, "cor": None, "uva": None, "regiao": None,
            "subregiao": None, "safra": None, "abv": None, "denominacao": None,
            "corpo": None, "harmonizacao": None, "docura": None,
            "duplicata_de": None, "status": "error", "fonte_llm": IA_NAME,
        }

        if not classif:
            continue

        if classif.upper() == "X":
            r["classificacao"] = "X"
            r["status"] = "not_wine"

        elif classif.upper() == "S" or classif.upper().startswith("S|"):
            r["classificacao"] = "S"
            r["status"] = "spirit"
            parts = classif.split("|")
            if len(parts) >= 3:
                r["prod_banco"] = qq(norm(parts[1]))
                r["vinho_banco"] = qq(norm(parts[2]))
            if len(parts) >= 4:
                r["pais"] = qq(parts[3].strip()[:5])

        elif classif.startswith("="):
            try:
                ref_num = int(classif[1:])
                if 1 <= ref_num <= len(clean_ids):
                    r["classificacao"] = "W"
                    r["duplicata_de"] = clean_ids[ref_num - 1]
                    r["status"] = "duplicate"
            except ValueError:
                r["status"] = "error"

        elif classif.upper().startswith("W|"):
            parts = classif.split("|")
            # Checar duplicata no ultimo campo
            is_dup = False
            dup_ref = None
            if parts[-1].strip().startswith("="):
                try:
                    ref_num = int(parts[-1].strip()[1:])
                    if 1 <= ref_num <= len(clean_ids):
                        dup_ref = clean_ids[ref_num - 1]
                        is_dup = True
                except ValueError:
                    pass
                parts = parts[:-1]

            r["classificacao"] = "W"
            r["prod_banco"] = qq(norm(parts[1])) if len(parts) > 1 else None
            r["vinho_banco"] = qq(norm(parts[2])) if len(parts) > 2 else None
            r["pais"] = qq(parts[3].strip()[:5]) if len(parts) > 3 else None
            r["cor"] = qq(parts[4].strip()[:1]) if len(parts) > 4 else None
            r["uva"] = qq(parts[5]) if len(parts) > 5 else None
            r["regiao"] = qq(parts[6]) if len(parts) > 6 else None
            r["subregiao"] = qq(parts[7]) if len(parts) > 7 else None
            r["safra"] = qq(parts[8]) if len(parts) > 8 else None
            r["abv"] = qq(parts[9]) if len(parts) > 9 else None
            r["denominacao"] = qq(parts[10]) if len(parts) > 10 else None
            r["corpo"] = qq(parts[11]) if len(parts) > 11 else None
            r["harmonizacao"] = qq(parts[12]) if len(parts) > 12 else None
            r["docura"] = qq(parts[13]) if len(parts) > 13 else None
            r["duplicata_de"] = dup_ref
            r["status"] = "duplicate" if is_dup else "pending_match"

        results.append(r)

    # INSERT no banco
    conn = get_db()
    cur = conn.cursor()
    inserted = 0
    for r in results:
        try:
            cur.execute("""
                INSERT INTO y2_results (
                    clean_id, loja_nome, classificacao, prod_banco, vinho_banco,
                    pais, cor, uva, regiao, subregiao, safra, abv, denominacao,
                    corpo, harmonizacao, docura, duplicata_de, status, fonte_llm
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                ) ON CONFLICT DO NOTHING
            """, (
                r["clean_id"], r["loja_nome"], r["classificacao"],
                r["prod_banco"], r["vinho_banco"],
                r["pais"], r["cor"], r["uva"], r["regiao"], r["subregiao"],
                r["safra"], r["abv"], r["denominacao"],
                r["corpo"], r["harmonizacao"], r["docura"],
                r["duplicata_de"], r["status"], r["fonte_llm"],
            ))
            inserted += 1
        except Exception as e:
            print(f"    ERRO insert clean_id={r['clean_id']}: {e}")
            conn.rollback()
    conn.commit()

    duracao = int(time.time() - t0)

    # Log
    cur.execute("""
        INSERT INTO y2_lotes_log (lote, ia, enviados, recebidos, faltantes, processado_em, duracao_seg, observacao)
        VALUES (%s, %s, %s, %s, %s, NOW(), %s, %s)
    """, (lote_num, IA_NAME, len(respostas), inserted, len(respostas) - inserted, duracao,
          f"codex lote {lote_num}"))
    conn.commit()
    conn.close()

    # Stats
    w = sum(1 for r in results if r["classificacao"] == "W" and r["status"] != "duplicate")
    x = sum(1 for r in results if r["classificacao"] == "X")
    s = sum(1 for r in results if r["classificacao"] == "S")
    d = sum(1 for r in results if r["status"] == "duplicate")
    print(f"  Lote {lote_num} SALVO: {inserted}/{n} inseridos | W={w} X={x} S={s} dup={d} | {duracao}s")
    return inserted


def main():
    # Verificar quais lotes tem resposta
    if len(sys.argv) > 1:
        lotes = [int(x) for x in sys.argv[1:]]
    else:
        lotes = []
        for f in sorted(os.listdir(LOTE_DIR)):
            m = re.match(r'resposta_[a-z]_(\d+)\.txt', f)
            if m:
                lotes.append(int(m.group(1)))

    if not lotes:
        print("Nenhuma resposta encontrada em", LOTE_DIR)
        return

    print(f"Salvando {len(lotes)} lotes: {lotes}")
    total = 0
    for lote_num in lotes:
        total += salvar_lote(lote_num)

    print(f"\nTotal inseridos: {total}")


if __name__ == "__main__":
    main()
