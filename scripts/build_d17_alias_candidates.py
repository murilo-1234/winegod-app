"""
D17 materializer: generate safe alias candidates and a human QA pack.

Read-only against Render. This script does not insert into wine_aliases.
Outputs:
  - reports/tail_d17_alias_candidates_2026-04-16.csv.gz
  - reports/tail_d17_alias_qa_pack_2026-04-16.csv
  - reports/tail_d17_alias_candidates_summary_2026-04-16.md
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import math
import os
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
DATE = "2026-04-16"

BASE_CSV = REPORTS / "tail_base_extract_2026-04-10.csv.gz"
Y2_CSV = REPORTS / "tail_y2_lineage_enriched_2026-04-10.csv.gz"
OUT_CANDIDATES = REPORTS / f"tail_d17_alias_candidates_{DATE}.csv.gz"
OUT_QA = REPORTS / f"tail_d17_alias_qa_pack_{DATE}.csv"
OUT_SUMMARY = REPORTS / f"tail_d17_alias_candidates_summary_{DATE}.md"

SUPPRESS_FILES = [
    ("d16_strong_patterns_2026-04-15", REPORTS / "tail_d16_strong_suppress_candidates_2026-04-15.csv.gz"),
    ("d16_wine_filter_expansion_2026-04-15", REPORTS / "tail_d16_wine_filter_expansion_candidates_2026-04-15.csv.gz"),
    ("d16_wine_filter_round3_2026-04-15", REPORTS / "tail_d16_round3_candidates_2026-04-15.csv.gz"),
    ("d16_wine_filter_round4_2026-04-15", REPORTS / "tail_d16_round4_candidates_2026-04-15.csv.gz"),
]

LOCAL_DB = dict(host="localhost", port=5432, dbname="winegod_db", user="postgres", password="postgres123")
Y2_MIN_SCORE = 0.70
TOKEN_DF_MAX = 5000
TOKEN_POOL_CAP = 3000
SEED = "winegod_d17_alias_qa_2026-04-16"

STOP_TOKENS = set("""
wine vinho vino vin red white rose tinto branco rouge blanc reserva reserve estate
grand cru brut sec dry sweet de la le los las the and para com sem with from
chateau domaine cantina winery cellars vineyard vineyards bottle garrafa garrafas
pack kit set case caixa gift nv non vintage appellation doc docg aoc igt dop igp
""".split())

APPELLATION_OR_GENERIC = set("""
saint emilion pauillac sauternes barsac medoc hautmedoc pomerol margaux pessac
leognan bordeaux burgundy bourgogne beaune meursault musigny chambolle vosne
romanee corton charlemagne chambertin clos beze vougeot gevrey nuits pommard
volnay puligny montrachet chassagne hermitage crozes ladoix chablis barolo
barbaresco chianti brunello montalcino montepulciano rioja ribera duero douro
madeira champagne prosecco mosel trocken spatlese auslese kabinett premier
classe vineyard vnyd cuvee gran reserva crianza riserva superiore classico
chateauneuf pape cotes cote jura haut bois quincy villages village commune
monopole lieux lieu climat lieu-dit appellation
""".split())

NON_DISTINCTIVE_EVIDENCE = APPELLATION_OR_GENERIC | set("""
bolgheri vermentino sonoma coast valley mountain peninsula mornington spring
vieille vigne vignes hautes palette petit petite natura naturelle tradicao
tradicion tradition mesa suave seco seca dry extra blanc blancs blancas blancs
rouge rosso rosata rosado rosa rosato bianco bianca tinto branco blanco
premiere premier selection selezione speciale special superior superiore
classic classico nature natural reserve reservado reservada riserva expression
terroir organic kosher millesime millesimato metodo tradicional varietale
""".split())

PRODUCER_GENERIC_TOKENS = NON_DISTINCTIVE_EVIDENCE | set("""
wine vinho vino vin bodega bodegas domaine chateau cantina tenuta quinta
maison cave caves estate vineyard vineyards cellars winery
""".split())

FIELDS = [
    "source_wine_id", "canonical_wine_id", "lane", "confidence", "review_state",
    "recommended_action", "score", "gap", "source_stratum", "source_nome",
    "source_produtor", "source_safra", "source_tipo", "canonical_nome",
    "canonical_produtor", "canonical_safra", "canonical_tipo", "channels",
    "evidence_reason", "source_wine_sources_count", "source_stores_count",
    "y2_status_set", "y2_match_score_max", "y2_any_not_wine_or_spirit",
    "qa_required", "qa_sample_rate",
]

sys.path.insert(0, str(ROOT / "scripts"))
from wine_filter import classify_product  # noqa: E402
from build_candidate_controls import score_candidate  # noqa: E402


def log(msg):
    print(msg, flush=True)


def fmt(n):
    return f"{int(n):,}".replace(",", ".")


def norm(text):
    value = (text or "").casefold()
    value = "".join(ch for ch in unicodedata.normalize("NFKD", value) if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def toks(text):
    out = []
    for token in norm(text).split():
        if len(token) < 4 or token in STOP_TOKENS:
            continue
        if re.fullmatch(r"(19|20)\d{2}", token) or re.fullmatch(r"\d+", token):
            continue
        if re.fullmatch(r"\d+(ml|cl|lt|ltr|litro|litros)", token):
            continue
        out.append(token)
    return list(dict.fromkeys(out))


def anchor_tokens(text, generic_tokens):
    return {token for token in toks(text) if token not in generic_tokens}


def parse_ids(text):
    return [int(match) for match in re.findall(r"\d+", text or "")]


def as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def det_hash(*parts):
    return hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()


def connect_local():
    return psycopg2.connect(**LOCAL_DB, connect_timeout=30)


def connect_render():
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / "backend" / ".env", override=False)
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL nao encontrado.")
    return psycopg2.connect(url, connect_timeout=30, keepalives=1, keepalives_idle=30)


def load_suppressed_ids():
    suppressed = set()
    by_reason = []
    for reason, path in SUPPRESS_FILES:
        count = 0
        if path.exists():
            with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    suppressed.add(int(row["render_wine_id"]))
                    count += 1
        by_reason.append((reason, count))
    return suppressed, by_reason


def load_lineage_and_clean_map(suppressed):
    lineage = {}
    clean_to_render = {}
    with gzip.open(Y2_CSV, "rt", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            wid = int(row["render_wine_id"])
            lineage[wid] = row
            if wid in suppressed:
                continue
            for clean_id in parse_ids(row.get("clean_ids_sample")):
                clean_to_render[clean_id] = wid
    return lineage, clean_to_render


def source_stratum(source):
    wf_cls, wf_cat = classify_product(f"{source['nome']} {source['produtor']}")
    y2_nw = source["lineage"].get("y2_any_not_wine_or_spirit") == "1"
    clean_count = as_int(source["lineage"].get("clean_ids_count"))
    lineage_resolved = source["lineage"].get("local_lineage_resolved") == "1"
    if (wf_cls == "not_wine" and wf_cat and wf_cat != "nome_vazio_ou_curto") or y2_nw:
        return "S1_SUSPECT_NOT_WINE"
    if source["no_source_flag"] == "1":
        return "S2_NO_SOURCE"
    if clean_count == 0 or not lineage_resolved:
        return "S3_NO_LINEAGE_OR_ORPHAN"
    if clean_count > 1:
        return "S4_MULTI_CLEAN_OR_AMBIG_LINEAGE"
    if source["wine_sources_count"] >= 3:
        return "S5_SOURCE_RICH_STRUCTURED"
    return "S6_GENERAL_REMAINDER"


def load_sources(suppressed, lineage):
    sources = []
    rejects = Counter()
    with gzip.open(BASE_CSV, "rt", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            wid = int(row["render_wine_id"])
            if wid in suppressed:
                rejects["suppressed"] += 1
                continue
            nome = row.get("nome") or ""
            produtor = row.get("produtor") or ""
            wf_cls, wf_cat = classify_product(f"{nome} {produtor}")
            if wf_cls == "not_wine":
                rejects[f"wine_filter:{wf_cat or 'unknown'}"] += 1
                continue
            source = {
                "id": wid,
                "nome": nome,
                "produtor": produtor,
                "safra": row.get("safra") or "",
                "tipo": row.get("tipo") or "",
                "wine_sources_count": as_int(row.get("wine_sources_count_live")),
                "stores_count": as_int(row.get("stores_count_live")),
                "no_source_flag": row.get("no_source_flag") or "",
                "lineage": lineage.get(wid, {}),
                "norm_name": norm(nome),
                "norm_produtor": norm(produtor),
                "stripped": " ".join(toks(nome)),
                "name_tokens": set(toks(nome)),
                "producer_tokens": set(toks(produtor)),
                "name_anchor_tokens": anchor_tokens(nome, NON_DISTINCTIVE_EVIDENCE),
                "producer_anchor_tokens": anchor_tokens(produtor, PRODUCER_GENERIC_TOKENS),
                "producer_present": len(norm(produtor)) >= 3,
            }
            source["tokens_all"] = list(dict.fromkeys(list(source["name_tokens"]) + list(source["producer_tokens"])))
            source["stratum"] = source_stratum(source)
            if source["stratum"] == "S1_SUSPECT_NOT_WINE":
                rejects["stratum_s1_after_filter"] += 1
                continue
            if len(source["norm_name"]) < 3:
                rejects["short_name"] += 1
                continue
            sources.append(source)
    return sources, rejects


def load_canonicals():
    canonicals = {}
    by_name = defaultdict(list)
    by_stripped = defaultdict(list)
    token_counts = Counter()
    canonical_tokens = {}
    conn = connect_local()
    try:
        cur = conn.cursor(name="d17_vivino_match")
        cur.itersize = 50000
        cur.execute("SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais FROM vivino_match")
        while True:
            rows = cur.fetchmany(50000)
            if not rows:
                break
            for cid, nome, produtor, safra, tipo, pais in rows:
                norm_name = norm(nome)
                if not norm_name:
                    continue
                name_tokens = set(toks(nome))
                producer_tokens = set(toks(produtor))
                all_tokens = list(dict.fromkeys(list(name_tokens) + list(producer_tokens)))
                rec = {
                    "id": int(cid),
                    "nome_normalizado": nome or "",
                    "produtor_normalizado": produtor or "",
                    "safra": str(safra or ""),
                    "tipo": str(tipo or ""),
                    "pais": str(pais or ""),
                    "norm_name": norm_name,
                    "stripped": " ".join(toks(nome)),
                    "name_tokens": name_tokens,
                    "producer_tokens": producer_tokens,
                    "name_anchor_tokens": anchor_tokens(nome, NON_DISTINCTIVE_EVIDENCE),
                    "producer_anchor_tokens": anchor_tokens(produtor, PRODUCER_GENERIC_TOKENS),
                    "tokens_all": all_tokens,
                }
                canonicals[rec["id"]] = rec
                by_name[norm_name].append(rec["id"])
                if rec["stripped"]:
                    by_stripped[rec["stripped"]].append(rec["id"])
                token_counts.update(all_tokens)
                canonical_tokens[rec["id"]] = all_tokens
        cur.close()
    finally:
        conn.close()
    return canonicals, by_name, by_stripped, token_counts, canonical_tokens


def load_y2_candidates(clean_to_render, canonicals):
    y2_by_source = defaultdict(dict)
    conn = connect_local()
    try:
        cur = conn.cursor(name="d17_y2_results")
        cur.itersize = 50000
        cur.execute(
            """
            SELECT clean_id, vivino_id, match_score
            FROM y2_results
            WHERE status = 'matched'
              AND vivino_id IS NOT NULL
              AND match_score >= %s
            """,
            (Y2_MIN_SCORE,),
        )
        while True:
            rows = cur.fetchmany(50000)
            if not rows:
                break
            for clean_id, vivino_id, match_score in rows:
                source_id = clean_to_render.get(int(clean_id))
                if source_id and int(vivino_id) in canonicals:
                    previous = y2_by_source[source_id].get(int(vivino_id), 0.0)
                    y2_by_source[source_id][int(vivino_id)] = max(previous, float(match_score or 0.0))
        cur.close()
    finally:
        conn.close()
    return y2_by_source


def build_postings(sources, token_counts, canonical_tokens):
    source_tokens = {token for source in sources for token in source["tokens_all"]}
    useful = {token for token in source_tokens if 1 <= token_counts.get(token, 0) <= TOKEN_DF_MAX}
    postings = defaultdict(list)
    for cid, token_list in canonical_tokens.items():
        for token in token_list:
            if token in useful:
                postings[token].append(cid)
    return postings


def token_pool(source, postings, token_counts):
    source_tokens = [token for token in source["tokens_all"] if token in postings]
    if len(source_tokens) < 2:
        return set()
    rare_tokens = sorted(source_tokens, key=lambda token: token_counts[token])[:5]
    best = set()
    best_size = 10**9
    for i in range(len(rare_tokens)):
        for j in range(i + 1, len(rare_tokens)):
            inter = set(postings[rare_tokens[i]]).intersection(postings[rare_tokens[j]])
            if inter and len(inter) < best_size:
                best = inter
                best_size = len(inter)
    if not best:
        return set()
    if len(best) > TOKEN_POOL_CAP:
        return set(sorted(best)[:TOKEN_POOL_CAP])
    return best


def evidence(source, canonical, channels):
    common_name = source["name_tokens"] & canonical["name_tokens"]
    common_prod = source["producer_anchor_tokens"] & canonical["producer_anchor_tokens"]
    source_name_to_cprod = source["name_anchor_tokens"] & canonical["producer_anchor_tokens"]
    strong_common_name = source["name_anchor_tokens"] & canonical["name_anchor_tokens"]
    has_anchor = bool(strong_common_name or common_prod or source_name_to_cprod)
    prod_den = max(len(source["producer_anchor_tokens"]), len(canonical["producer_anchor_tokens"]), 1)
    prod_strength = len(common_prod) / prod_den
    if "exact_name" in channels and (has_anchor or not source["producer_present"]):
        return True, "exact_name"
    if (
        "stripped_name" in channels
        and source["stripped"]
        and source["stripped"] == canonical["stripped"]
        and len(source["stripped"].split()) >= 2
        and has_anchor
    ):
        return True, "stripped_name"
    if any(channel.startswith("y2_") for channel in channels):
        if strong_common_name or prod_strength >= 0.5 or common_prod or source_name_to_cprod:
            return True, "y2_plus_text_evidence"
    if len(strong_common_name) >= 2:
        return True, "strong_name_token_overlap>=2"
    if strong_common_name and (prod_strength >= 0.5 or common_prod):
        return True, "strong_name_and_producer_overlap"
    if len(common_name) >= 3 and (prod_strength >= 0.75 or common_prod):
        return True, "broad_name_with_strong_producer"
    if strong_common_name and source_name_to_cprod:
        return True, "name_and_source_to_canonical_producer"
    return False, "weak_single_token_or_no_text_evidence"


def producer_compatible(source, canonical):
    if source["producer_anchor_tokens"] and canonical["producer_anchor_tokens"]:
        if not (source["producer_anchor_tokens"] & canonical["producer_anchor_tokens"]):
            return False
        return True
    if source["producer_anchor_tokens"] and canonical["name_anchor_tokens"]:
        return bool(source["producer_anchor_tokens"] & canonical["name_anchor_tokens"])
    if source["producer_present"] and canonical["producer_anchor_tokens"] and not source["producer_anchor_tokens"]:
        return False
    if canonical["producer_anchor_tokens"]:
        return bool(source["name_anchor_tokens"] & canonical["producer_anchor_tokens"])
    return True


def auto_floor_guard(source, canonical, evidence_reason, score, gap):
    if source["stratum"] != "S6_GENERAL_REMAINDER":
        return None
    if score > 0.55 or gap > 0.15:
        return None
    if evidence_reason in {"stripped_name", "name_and_source_to_canonical_producer"}:
        return "s6_auto_floor_weak_evidence"
    if not source["producer_anchor_tokens"]:
        return "s6_auto_floor_no_producer_anchor"
    if len(source["name_anchor_tokens"] & canonical["name_anchor_tokens"]) < 2:
        return "s6_auto_floor_weak_name_anchor"
    return None


def tipo_mismatch(source, canonical):
    source_tipo = norm(source.get("tipo"))
    canonical_tipo = norm(canonical.get("tipo"))
    if not source_tipo or not canonical_tipo:
        return False
    aliases = {
        "red": "tinto",
        "rouge": "tinto",
        "white": "branco",
        "blanc": "branco",
        "rose": "rose",
        "rosado": "rose",
        "sparkling": "espumante",
    }
    source_tipo = aliases.get(source_tipo, source_tipo)
    canonical_tipo = aliases.get(canonical_tipo, canonical_tipo)
    return source_tipo != canonical_tipo


def classify_lane(source, score, gap):
    if source["stratum"] == "S1_SUSPECT_NOT_WINE":
        return None, "", "", "", "s1_excluded"
    if score >= 0.50 and gap >= 0.10:
        return "ALIAS_AUTO", "HIGH", "RESOLVED", "ALIAS", "0.05"
    if source["stratum"] == "S6_GENERAL_REMAINDER":
        return None, "", "", "", "s6_medium_excluded_for_d19"
    if score >= 0.45 and gap > 0:
        return "ALIAS_QA", "MEDIUM", "SECOND_REVIEW", "ALIAS", "0.10"
    if score >= 0.35 and gap >= 0.05:
        return "ALIAS_QA", "MEDIUM", "SECOND_REVIEW", "ALIAS", "0.10"
    return None, "", "", "", "score_gap_below_d17"


def build_candidates(sources, canonicals, by_name, by_stripped, token_counts, postings, y2_by_source):
    candidates = []
    rejects = Counter()
    started = time.time()
    for idx, source in enumerate(sources, 1):
        pool = defaultdict(set)
        for cid in by_name.get(source["norm_name"], []):
            pool[cid].add("exact_name")
        if source["stripped"]:
            for cid in by_stripped.get(source["stripped"], []):
                pool[cid].add("stripped_name")
        for cid in token_pool(source, postings, token_counts):
            pool[cid].add("token_index")
        for cid, y2_score in y2_by_source.get(source["id"], {}).items():
            pool[cid].add(f"y2_{y2_score:.3f}")
        if not pool:
            rejects["no_candidate_pool"] += 1
            continue

        store = {
            "nome_normalizado": source["norm_name"],
            "nome": source["norm_name"],
            "produtor_normalizado": source["norm_produtor"],
            "produtor": source["norm_produtor"],
            "safra": source["safra"],
            "tipo": source["tipo"],
        }
        scored = []
        for cid, channels in pool.items():
            canonical = canonicals.get(cid)
            if not canonical:
                continue
            if tipo_mismatch(source, canonical):
                rejects["tipo_mismatch"] += 1
                continue
            if not producer_compatible(source, canonical):
                rejects["producer_incompatible"] += 1
                continue
            ok, evidence_reason = evidence(source, canonical, channels)
            if not ok:
                rejects[evidence_reason] += 1
                continue
            score = float(score_candidate(store, canonical))
            if score < 0.30:
                rejects["score_below_030"] += 1
                continue
            scored.append((score, cid, canonical, channels, evidence_reason))
        if not scored:
            rejects["no_scored_candidate"] += 1
            continue

        scored.sort(key=lambda item: (-item[0], item[1]))
        top_score, top_cid, top_canonical, top_channels, top_evidence = scored[0]
        top2_score = scored[1][0] if len(scored) >= 2 else 0.0
        gap = round(top_score - top2_score, 4)
        auto_floor_reason = auto_floor_guard(source, top_canonical, top_evidence, top_score, gap)
        if auto_floor_reason:
            rejects[auto_floor_reason] += 1
            continue
        lane, confidence, review_state, action, qa_rate_or_reason = classify_lane(source, top_score, gap)
        if not lane:
            rejects[qa_rate_or_reason] += 1
            continue

        y2 = source["lineage"]
        candidates.append({
            "source_wine_id": str(source["id"]),
            "canonical_wine_id": str(top_cid),
            "lane": lane,
            "confidence": confidence,
            "review_state": review_state,
            "recommended_action": action,
            "score": f"{top_score:.4f}",
            "gap": f"{gap:.4f}",
            "source_stratum": source["stratum"],
            "source_nome": source["nome"],
            "source_produtor": source["produtor"],
            "source_safra": source["safra"],
            "source_tipo": source["tipo"],
            "canonical_nome": top_canonical["nome_normalizado"],
            "canonical_produtor": top_canonical["produtor_normalizado"],
            "canonical_safra": top_canonical["safra"],
            "canonical_tipo": top_canonical["tipo"],
            "channels": "|".join(sorted(top_channels)),
            "evidence_reason": top_evidence,
            "source_wine_sources_count": str(source["wine_sources_count"]),
            "source_stores_count": str(source["stores_count"]),
            "y2_status_set": y2.get("y2_status_set", ""),
            "y2_match_score_max": y2.get("y2_match_score_max", ""),
            "y2_any_not_wine_or_spirit": y2.get("y2_any_not_wine_or_spirit", ""),
            "qa_required": "1",
            "qa_sample_rate": qa_rate_or_reason,
        })
        if idx % 2000 == 0:
            log(f"  processed={idx:,}/{len(sources):,} candidates={len(candidates):,} elapsed={time.time() - started:.0f}s")
    return candidates, rejects


def existing_alias_sources():
    conn = connect_render()
    try:
        conn.set_session(readonly=True, autocommit=True)
        cur = conn.cursor()
        cur.execute("SELECT source_wine_id FROM wine_aliases WHERE review_status = 'approved'")
        out = {int(row[0]) for row in cur.fetchall()}
        cur.close()
        return out
    finally:
        conn.close()


def render_status(ids):
    if not ids:
        return {}
    status = {}
    conn = connect_render()
    try:
        conn.set_session(readonly=True, autocommit=True)
        cur = conn.cursor()
        id_list = sorted(ids)
        for start in range(0, len(id_list), 10000):
            chunk = id_list[start:start + 10000]
            cur.execute("SELECT id, vivino_id, suppressed_at FROM wines WHERE id = ANY(%s)", (chunk,))
            for wid, vivino_id, suppressed_at in cur.fetchall():
                status[int(wid)] = (vivino_id, suppressed_at)
        cur.close()
    finally:
        conn.close()
    return status


def validate_live(candidates):
    rejects = Counter()
    alias_sources = existing_alias_sources()
    source_ids = {int(row["source_wine_id"]) for row in candidates}
    canonical_ids = {int(row["canonical_wine_id"]) for row in candidates}
    log(f"[validate] source_ids={len(source_ids):,} canonical_ids={len(canonical_ids):,}")
    source_status = render_status(source_ids)
    canonical_status = render_status(canonical_ids)
    valid = []
    for row in candidates:
        source_id = int(row["source_wine_id"])
        canonical_id = int(row["canonical_wine_id"])
        if source_id in alias_sources:
            rejects["source_already_has_approved_alias"] += 1
            continue
        source_vivino, source_suppressed = source_status.get(source_id, (None, "missing"))
        if source_vivino is not None or source_suppressed is not None:
            rejects["source_not_active_tail"] += 1
            continue
        canonical_vivino, canonical_suppressed = canonical_status.get(canonical_id, (None, "missing"))
        if canonical_vivino is None or canonical_suppressed is not None:
            rejects["canonical_not_active_vivino"] += 1
            continue
        valid.append(row)
    return valid, rejects


def write_candidates(rows):
    with gzip.open(OUT_CANDIDATES, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sample_qa(rows):
    by_lane = defaultdict(list)
    for row in rows:
        by_lane[row["lane"]].append(row)
    sampled = []
    for lane, lane_rows in sorted(by_lane.items()):
        rate = 0.05 if lane == "ALIAS_AUTO" else 0.10
        needed = math.ceil(len(lane_rows) * rate)
        ordered = sorted(
            lane_rows,
            key=lambda row: det_hash(SEED, row["source_wine_id"], row["canonical_wine_id"], row["lane"]),
        )
        for row in ordered[:needed]:
            qa_row = dict(row)
            qa_row["qa_sample_rate"] = f"{rate:.2f}"
            qa_row["qa_verdict"] = ""
            qa_row["qa_notes"] = ""
            qa_row["reviewer"] = ""
            sampled.append(qa_row)
    sampled.sort(key=lambda row: (row["lane"], row["source_stratum"], int(row["source_wine_id"])))
    return sampled


def write_qa(rows):
    fields = FIELDS + ["qa_verdict", "qa_notes", "reviewer"]
    with open(OUT_QA, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def md_table(headers, rows):
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def write_summary(candidates, qa_rows, suppressed_by_reason, source_rejects, candidate_rejects, live_rejects, elapsed):
    by_lane = Counter(row["lane"] for row in candidates)
    by_stratum = Counter(row["source_stratum"] for row in candidates)
    by_evidence = Counter(row["evidence_reason"] for row in candidates)
    qa_by_lane = Counter(row["lane"] for row in qa_rows)
    lane_rows = [[lane, fmt(by_lane[lane]), fmt(qa_by_lane.get(lane, 0))] for lane in sorted(by_lane)]
    stratum_rows = [[name, fmt(count)] for name, count in by_stratum.most_common()]
    evidence_rows = [[name, fmt(count)] for name, count in by_evidence.most_common(20)]
    content = f"""# D17 Alias Candidates -- Materializacao para QA

Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Modo: read-only contra Render; sem INSERT em `wine_aliases`

## Resultado curto

- Candidatos D17 validados: `{fmt(len(candidates))}`
- `ALIAS_AUTO`: `{fmt(by_lane.get('ALIAS_AUTO', 0))}`
- `ALIAS_QA`: `{fmt(by_lane.get('ALIAS_QA', 0))}`
- QA pack humano: `{fmt(len(qa_rows))}` linhas
- Runtime: `{elapsed:.0f}s`

## Artefatos

- Full rowset: `{OUT_CANDIDATES}`
- QA CSV: `{OUT_QA}`

## Contagem por lane

{md_table(['lane', 'candidatos', 'qa_sample'], lane_rows)}

## Contagem por estrato

{md_table(['estrato', 'candidatos'], stratum_rows)}

## Evidencia principal

{md_table(['evidencia', 'candidatos'], evidence_rows)}

## Suppress removido antes do D17

{md_table(['reason', 'wines'], [[reason, fmt(count)] for reason, count in suppressed_by_reason])}

## Rejeicoes principais

### Source

{md_table(['motivo', 'wines'], [[name, fmt(count)] for name, count in source_rejects.most_common(30)])}

### Candidato

{md_table(['motivo', 'ocorrencias'], [[name, fmt(count)] for name, count in candidate_rejects.most_common(30)])}

### Validacao live Render

{md_table(['motivo', 'ocorrencias'], [[name, fmt(count)] for name, count in live_rejects.most_common(30)] or [['<nenhum>', '0']])}

## Como revisar

Marque `CORRECT` somente se source e canonical forem o mesmo vinho. Na duvida,
marque `ERROR` ou deixe pendente. O limite operacional original de D17 e erro
abaixo de 3% para alias.
"""
    OUT_SUMMARY.write_text(content, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Processa apenas N sources elegiveis para teste.")
    parser.add_argument("--offset", type=int, default=0, help="Pula os primeiros N sources elegiveis.")
    parser.add_argument("--suffix", type=str, default="", help="Sufixo para artefatos (ex: chunk_000).")
    args = parser.parse_args()
    if args.suffix:
        global OUT_CANDIDATES, OUT_QA, OUT_SUMMARY
        OUT_CANDIDATES = REPORTS / f"tail_d17_alias_candidates_{DATE}_{args.suffix}.csv.gz"
        OUT_QA = REPORTS / f"tail_d17_alias_qa_pack_{DATE}_{args.suffix}.csv"
        OUT_SUMMARY = REPORTS / f"tail_d17_alias_candidates_summary_{DATE}_{args.suffix}.md"

    started = time.time()
    REPORTS.mkdir(parents=True, exist_ok=True)

    log("[1] Load suppress IDs")
    suppressed, suppressed_by_reason = load_suppressed_ids()
    log(f"    suppressed_ids={len(suppressed):,}")

    log("[2] Load y2 lineage and clean map")
    lineage, clean_to_render = load_lineage_and_clean_map(suppressed)
    log(f"    lineage_rows={len(lineage):,} clean_map_active={len(clean_to_render):,}")

    log("[3] Load eligible sources")
    sources, source_rejects = load_sources(suppressed, lineage)
    total_eligible = len(sources)
    if args.offset:
        sources = sources[args.offset:]
    if args.limit:
        sources = sources[:args.limit]
    log(f"    sources_eligible_total={total_eligible:,} sources_in_chunk={len(sources):,} offset={args.offset} limit={args.limit}")

    log("[4] Load local canonicals")
    canonicals, by_name, by_stripped, token_counts, canonical_tokens = load_canonicals()
    log(f"    canonicals={len(canonicals):,} name_keys={len(by_name):,}")

    log("[5] Load y2 matched hints")
    y2_by_source = load_y2_candidates(clean_to_render, canonicals)
    log(f"    source_y2_hints={len(y2_by_source):,}")

    log("[6] Build token postings")
    postings = build_postings(sources, token_counts, canonical_tokens)
    log(f"    postings_tokens={len(postings):,}")

    log("[7] Build candidates")
    candidates, candidate_rejects = build_candidates(
        sources, canonicals, by_name, by_stripped, token_counts, postings, y2_by_source
    )
    log(f"    raw_candidates={len(candidates):,}")

    log("[8] Validate live Render state")
    candidates, live_rejects = validate_live(candidates)
    candidates.sort(key=lambda row: (row["lane"], row["source_stratum"], int(row["source_wine_id"])))
    log(f"    validated_candidates={len(candidates):,}")

    log("[9] Write artifacts")
    write_candidates(candidates)
    qa_rows = sample_qa(candidates)
    write_qa(qa_rows)
    elapsed = time.time() - started
    write_summary(candidates, qa_rows, suppressed_by_reason, source_rejects, candidate_rejects, live_rejects, elapsed)

    log("")
    log(f"OK candidates: {OUT_CANDIDATES}")
    log(f"OK qa_csv:     {OUT_QA}")
    log(f"OK summary:    {OUT_SUMMARY}")
    log(f"validated={len(candidates):,} qa={len(qa_rows):,} elapsed={elapsed:.0f}s")


if __name__ == "__main__":
    main()
