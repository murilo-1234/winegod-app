"""
Fast price audit --single big query per country, minimal round trips.
READ-ONLY.
"""
import psycopg2, json, sys

DB = "postgresql://postgres:postgres123@localhost:5432/winegod_db"

COUNTRIES = [
    "ae","ar","at","au","be","bg","br","ca","ch","cl",
    "cn","co","cz","de","dk","es","fi","fr","gb","ge",
    "gr","hk","hr","hu","ie","il","in","it","jp","kr",
    "lu","md","mx","nl","no","nz","pe","ph","pl","pt",
    "ro","ru","se","sg","th","tr","tw","us","uy","za"
]

CURRENCY_MINS = {
    "EUR":1,"USD":1,"GBP":1,"CHF":1,"CAD":1,"AUD":1,
    "NZD":1,"SGD":1,"HKD":5,"AED":3,"DKK":5,"SEK":5,
    "NOK":5,"PLN":3,"CZK":20,"HUF":200,"RON":3,"BGN":1,
    "HRK":5,"RUB":50,"TRY":5,"GEL":2,"ILS":3,"INR":50,
    "JPY":100,"KRW":500,"CNY":5,"TWD":20,"THB":20,
    "PHP":30,"MXN":10,"BRL":5,"ARS":100,"CLP":500,
    "COP":2000,"PEN":3,"UYU":30,"ZAR":10,"MDL":10,
}

PLACEHOLDERS = [0.01, 0.99, 1.00, 9999, 99999, 999999]

conn = psycopg2.connect(DB)
conn.set_session(readonly=True)
cur = conn.cursor()

results = []

for i, cc in enumerate(COUNTRIES):
    t = f"vinhos_{cc}_fontes"
    print(f"[{i+1}/50] {cc.upper()}...", end=" ", flush=True)
    try:
        # Single combined query for counts
        cur.execute(f"""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE preco < 0) as negative,
                COUNT(*) FILTER (WHERE preco = 0) as zero,
                COUNT(*) FILTER (WHERE preco IS NULL) as null_cnt,
                COUNT(*) FILTER (WHERE preco = -1) as sentinel_neg1,
                COUNT(*) FILTER (WHERE preco = 0.01) as ph_001,
                COUNT(*) FILTER (WHERE preco = 0.99) as ph_099,
                COUNT(*) FILTER (WHERE preco = 1.00) as ph_100,
                COUNT(*) FILTER (WHERE preco = 9999) as ph_9999,
                COUNT(*) FILTER (WHERE preco = 99999) as ph_99999,
                COUNT(*) FILTER (WHERE preco = 999999) as ph_999999
            FROM {t}
        """)
        row = cur.fetchone()
        total, neg, zero, null_c, sent_neg1 = row[0], row[1], row[2], row[3], row[4]
        ph_detail = {"0.01":row[5],"0.99":row[6],"1.0":row[7],"9999":row[8],"99999":row[9],"999999":row[10]}
        ph_total = sum([row[5],row[6],row[7],row[8],row[9],row[10]])

        # Currency distribution
        cur.execute(f"SELECT moeda, COUNT(*) FROM {t} GROUP BY moeda ORDER BY COUNT(*) DESC")
        currencies = {}
        for r in cur.fetchall():
            currencies[r[0] if r[0] else "NULL"] = r[1]

        # p99 and outliers
        p99 = None; outliers = 0; outlier_threshold = 0; extreme_samples = []
        if total > 0:
            cur.execute(f"SELECT percentile_cont(0.99) WITHIN GROUP (ORDER BY preco) FROM {t} WHERE preco > 0")
            p99_row = cur.fetchone()
            if p99_row and p99_row[0]:
                p99 = float(p99_row[0])
                outlier_threshold = p99 * 10
                cur.execute(f"SELECT COUNT(*) FROM {t} WHERE preco > %s", (outlier_threshold,))
                outliers = cur.fetchone()[0]
                cur.execute(f"""
                    SELECT preco, moeda, COALESCE(dados_extras->>'loja', fonte) as loja
                    FROM {t} WHERE preco > %s ORDER BY preco DESC LIMIT 3
                """, (outlier_threshold,))
                extreme_samples = [(float(r[0]),r[1],r[2]) for r in cur.fetchall()]

        # Suspicious low: build dynamic query
        susp = 0
        susp_parts = []
        susp_params = []
        for moeda, minp in CURRENCY_MINS.items():
            susp_parts.append(f"COUNT(*) FILTER (WHERE moeda = %s AND preco > 0 AND preco < %s)")
            susp_params.extend([moeda, minp])
        if susp_parts:
            q = f"SELECT {', '.join(susp_parts)} FROM {t}"
            cur.execute(q, susp_params)
            susp_row = cur.fetchone()
            susp = sum(v for v in susp_row if v)

        problems = neg + zero + null_c + outliers + susp + ph_total
        prob_pct = (problems / total * 100) if total > 0 else 0

        real_cur = {k:v for k,v in currencies.items() if k != "NULL"}
        mixed = len(real_cur) > 1

        results.append({
            "cc": cc, "total": total, "neg": neg, "zero": zero, "null": null_c,
            "sent_neg1": sent_neg1, "currencies": currencies, "mixed": mixed,
            "p99": p99, "outlier_threshold": outlier_threshold,
            "outliers": outliers, "extreme_samples": extreme_samples,
            "susp": susp, "ph_total": ph_total, "ph_detail": ph_detail,
            "problems": problems, "prob_pct": prob_pct,
        })
        print(f"OK ({total:,} rows, {problems:,} problems)")

    except Exception as e:
        print(f"ERROR: {e}")
        results.append({"cc":cc,"total":0,"error":str(e)})

cur.close()
conn.close()

# ===========================================================================
# SUMMARY TABLE
# ===========================================================================
print("\n\n" + "="*150)
print("SUMMARY TABLE --ALL 50 COUNTRIES")
print("="*150)
hdr = f"{'CC':<5} {'Total':>10} {'Negative':>10} {'Zero':>10} {'NULL':>10} {'Mixed$':>7} {'Outliers':>10} {'SuspLow':>10} {'Placehld':>10} {'Problems':>10} {'Prob%':>7}"
print(hdr)
print("-"*150)

gt = gn = gz = gnl = go = gs = gp = gpr = 0
for r in results:
    if "error" in r and r.get("error"):
        print(f"{r['cc'].upper():<5} ERROR: {r['error']}")
        continue
    m = "YES" if r["mixed"] else "no"
    print(f"{r['cc'].upper():<5} {r['total']:>10,} {r['neg']:>10,} {r['zero']:>10,} {r['null']:>10,} {m:>7} {r['outliers']:>10,} {r['susp']:>10,} {r['ph_total']:>10,} {r['problems']:>10,} {r['prob_pct']:>6.1f}%")
    gt += r["total"]; gn += r["neg"]; gz += r["zero"]; gnl += r["null"]
    go += r["outliers"]; gs += r["susp"]; gp += r["ph_total"]; gpr += r["problems"]

print("-"*150)
gpct = (gpr/gt*100) if gt>0 else 0
print(f"{'TOT':<5} {gt:>10,} {gn:>10,} {gz:>10,} {gnl:>10,} {'':>7} {go:>10,} {gs:>10,} {gp:>10,} {gpr:>10,} {gpct:>6.1f}%")

# ===========================================================================
# TOP 20 WORST
# ===========================================================================
valid = [r for r in results if "error" not in r or not r.get("error")]
valid.sort(key=lambda x: x["problems"], reverse=True)

print("\n\n" + "="*120)
print("TOP 20 WORST COUNTRIES (most problems)")
print("="*120)

for rank, r in enumerate(valid[:20], 1):
    if r["total"] == 0: continue
    print(f"\n{'-'*80}")
    print(f"  #{rank}  {r['cc'].upper()} -- {r['problems']:,} problems ({r['prob_pct']:.1f}% of {r['total']:,} records)")
    print(f"{'-'*80}")
    print(f"    Negative: {r['neg']:,} (sentinel -1: {r['sent_neg1']:,})  |  Zero: {r['zero']:,}  |  NULL: {r['null']:,}")
    print(f"    Suspicious low: {r['susp']:,}  |  Extreme outliers: {r['outliers']:,}  |  Placeholders: {r['ph_total']:,}")
    rc = {k:v for k,v in r["currencies"].items() if k!="NULL"}
    if len(rc)>1:
        print(f"    MIXED CURRENCIES: {json.dumps(rc, default=str)}")
    elif rc:
        mk = list(rc.keys())[0]
        print(f"    Currency: {mk} ({list(rc.values())[0]:,})")
    if "NULL" in r["currencies"]:
        print(f"    NULL currency: {r['currencies']['NULL']:,}")
    ph_nonzero = {k:v for k,v in r["ph_detail"].items() if v>0}
    if ph_nonzero:
        print(f"    Placeholder breakdown: {', '.join(f'{k}={v:,}' for k,v in ph_nonzero.items())}")
    if r.get("p99"):
        print(f"    P99={r['p99']:,.2f}, outlier threshold={r['outlier_threshold']:,.2f}")
    if r["extreme_samples"]:
        print(f"    Top extreme prices:")
        for p,m,l in r["extreme_samples"]:
            print(f"      {m} {p:,.2f} --{l}")

# ===========================================================================
# MIXED CURRENCIES
# ===========================================================================
print("\n\n" + "="*100)
print("COUNTRIES WITH MIXED CURRENCIES")
print("="*100)
any_mixed = False
for r in results:
    if "error" in r and r.get("error"): continue
    rc = {k:v for k,v in r["currencies"].items() if k!="NULL"}
    if len(rc)>1:
        any_mixed = True
        print(f"\n  {r['cc'].upper()} ({r['total']:,} records):")
        for cur_name, cnt in sorted(rc.items(), key=lambda x: -x[1]):
            pct = cnt/r["total"]*100
            print(f"    {cur_name}: {cnt:,} ({pct:.1f}%)")
if not any_mixed:
    print("  None --all countries use single currency.")

# ===========================================================================
# SENTINEL -1 SUMMARY
# ===========================================================================
print("\n\n" + "="*100)
print("SENTINEL VALUE -1 SUMMARY")
print("="*100)
for r in results:
    if "error" in r and r.get("error"): continue
    if r.get("sent_neg1",0)>0:
        print(f"  {r['cc'].upper()}: {r['sent_neg1']:,} records with preco = -1")

print("\n\nAudit complete.")
