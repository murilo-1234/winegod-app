"""Canonical note resolution engine — nota_wcf v2.

Single source of truth for wine note, seal, source, and public ratings bucket.
All consumers (display, score, Baco, resolver, share, search, compare, frontend)
must use this module. No parallel logic allowed.

Design principles:
- Pure functions for note resolution (no Flask, no DB dependency).
- bucket_lookup_fn is injectable: production uses BucketCache.lookup, tests use mocks.
- Two cache modes: web runtime (graceful degradation) vs batch (fail-fast).
"""

import os
import statistics

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_note_v2(wine, bucket_lookup_fn=None):
    """Resolve canonical note v2 for a wine dict.

    Args:
        wine: dict with DB fields (nota_wcf, vivino_rating, nota_wcf_sample_size,
              vivino_reviews, pais, regiao, sub_regiao, tipo, produtor, confianca_nota).
        bucket_lookup_fn: callable(wine) -> bucket dict | None. Injectable for tests.

    Returns dict with:
        display_note, display_note_type, display_note_source,
        public_ratings_count, public_ratings_bucket, wcf_sample_size,
        context_bucket_key, context_bucket_level, context_bucket_n,
        context_bucket_stddev.
    """
    nota_wcf = wine.get("nota_wcf")
    vivino = wine.get("vivino_rating")
    sample = wine.get("nota_wcf_sample_size")
    pub_count = _get_public_ratings_count(wine)

    seal = _resolve_seal(pub_count, vivino, nota_wcf, sample)
    note, source, bucket_used = _resolve_note_value(
        nota_wcf, vivino, sample, pub_count, wine, bucket_lookup_fn
    )

    # Final seal adjustment based on resolved source
    if source == "contextual" and seal is None:
        seal = "contextual"
    if note is None:
        seal = None
        source = "none"

    return {
        "display_note": round(note, 2) if note is not None else None,
        "display_note_type": seal,
        "display_note_source": source,
        "public_ratings_count": pub_count,
        "public_ratings_bucket": _compute_ratings_bucket(pub_count),
        "wcf_sample_size": int(sample) if sample is not None else None,
        "context_bucket_key": bucket_used.get("bucket_key") if bucket_used else None,
        "context_bucket_level": bucket_used.get("bucket_level") if bucket_used else None,
        "context_bucket_n": bucket_used.get("bucket_n") if bucket_used else None,
        "context_bucket_stddev": bucket_used.get("bucket_stddev") if bucket_used else None,
    }


# ---------------------------------------------------------------------------
# Seal resolution
# ---------------------------------------------------------------------------


def _resolve_seal(pub_count, vivino, nota_wcf, sample):
    """Public seal based on public evidence, not WCF sample size."""
    vr = float(vivino) if vivino is not None else None

    # Wine with public Vivino rating
    if vr is not None and vr > 0 and pub_count is not None:
        if pub_count >= 75:
            return "verified"
        if pub_count >= 25:
            return "estimated"

    # Wine without sufficient public evidence but with own WCF
    if nota_wcf is not None and sample is not None and int(sample) > 0:
        return "estimated"

    # Placeholder — refined to "contextual" or None after note resolution
    return None


# ---------------------------------------------------------------------------
# Note value resolution
# ---------------------------------------------------------------------------


def _resolve_note_value(nota_wcf, vivino, sample, pub_count, wine, bucket_lookup_fn):
    """Resolve numeric note value and its source.

    Returns (note_float|None, source_str, bucket_dict|None).
    """
    nwcf = float(nota_wcf) if nota_wcf is not None else None
    vr = float(vivino) if vivino is not None and float(vivino) > 0 else None
    ss = int(sample) if sample is not None else 0
    conf = float(wine.get("confianca_nota")) if wine.get("confianca_nota") is not None else None

    bucket = bucket_lookup_fn(wine) if bucket_lookup_fn else None

    # ==================================================================
    # BLOCK A: Wine WITH Vivino
    # ==================================================================
    if vr is not None:

        # A1: Robust WCF (sample >= 25) -> WCF v2 with shrinkage + clamp
        if nwcf is not None and ss >= 25:
            if bucket and bucket.get("nota_base") is not None:
                nota = _shrinkage(nwcf, bucket["nota_base"], ss)
                source = "wcf_shrunk"
            else:
                nota = nwcf
                source = "wcf_direct"
            nota = _clamp(nota, vr - 0.30, vr + 0.20)
            return nota, source, bucket

        # A2: Shallow WCF (sample < 25) -> Vivino anchor + contextual delta
        if bucket and bucket.get("delta_contextual") is not None:
            nota = vr + bucket["delta_contextual"]
            # nota_base as brake
            nb = bucket.get("nota_base")
            if nb is not None and nota > nb + 0.50:
                nota = nb + 0.50
            nota = _clamp(nota, vr - 0.30, vr + 0.20)
            return nota, "vivino_contextual_delta", bucket

        # A3: No sufficient context -> Vivino direct with 2 decimal places
        return vr, "vivino_fallback", None

    # ==================================================================
    # BLOCK B: Wine WITHOUT Vivino
    # ==================================================================

    # B1: Has own WCF
    if nwcf is not None and ss > 0:
        if bucket and bucket.get("nota_base") is not None:
            nota = _shrinkage(nwcf, bucket["nota_base"], ss)
            source = "wcf_shrunk"
        else:
            nota = nwcf
            source = "wcf_direct"
        return nota, source, bucket

    # B2: Contextual pure (n=0, no WCF, no Vivino, but has bucket)
    if bucket and bucket.get("nota_base") is not None:
        nota = bucket["nota_base"]
        stddev = bucket.get("bucket_stddev")
        if stddev is not None and stddev > 0:
            nota = nota - 0.5 * stddev
        return nota, "contextual", bucket

    # B3: AI fallback (confianca >= 0.75, residual rule from old system)
    if nwcf is not None and conf is not None and conf >= 0.75:
        return nwcf, "ai", None

    # B4: Nothing
    return None, "none", None


# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------


def _shrinkage(nota_wcf, nota_base, n, k=20):
    """Bayesian shrinkage: pulls WCF toward nota_base when sample is small."""
    return (n / (n + k)) * nota_wcf + (k / (n + k)) * nota_base


def _clamp(value, min_val, max_val):
    """Asymmetric clamp: vivino - 0.30 to vivino + 0.20."""
    return max(min_val, min(value, max_val))


def _compute_ratings_bucket(pub_count):
    """Convert raw public count to visual bucket."""
    if pub_count is None or pub_count < 25:
        return None
    if pub_count >= 500:
        return "500+"
    if pub_count >= 300:
        return "300+"
    if pub_count >= 200:
        return "200+"
    if pub_count >= 100:
        return "100+"
    if pub_count >= 50:
        return "50+"
    return "25+"


def _get_public_ratings_count(wine):
    """Return canonical public ratings count.

    Gate 0 decision: vivino_reviews is the canonical counter.
    """
    val = wine.get("vivino_reviews")
    if val is not None:
        return int(val)
    return None


# ---------------------------------------------------------------------------
# BucketCache — I/O layer, separated from pure logic
# ---------------------------------------------------------------------------


class BucketCache:
    """In-memory cache of wine_context_buckets for Cascata B lookup."""

    def __init__(self):
        self._cache = {}  # {(level, key): bucket_dict}
        self._loaded = False

    def load(self, db_url=None):
        """Load all buckets into memory. ~5k-20k rows = ~2MB.

        Raises on connection failure (fail-fast for batch).
        """
        import psycopg2
        from dotenv import load_dotenv
        load_dotenv()

        url = db_url or os.environ.get("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL not set — cannot load BucketCache")

        conn = psycopg2.connect(url, connect_timeout=30)
        try:
            cur = conn.cursor()
            cur.execute("SELECT bucket_level, bucket_key, bucket_n, nota_base, "
                        "bucket_stddev, delta_contextual, delta_n FROM wine_context_buckets")
            self._cache = {}
            for row in cur.fetchall():
                self._cache[(row[0], row[1])] = {
                    "bucket_level": row[0],
                    "bucket_key": row[1],
                    "bucket_n": row[2],
                    "nota_base": float(row[3]) if row[3] is not None else None,
                    "bucket_stddev": float(row[4]) if row[4] is not None else None,
                    "delta_contextual": float(row[5]) if row[5] is not None else None,
                    "delta_n": row[6],
                }
            self._loaded = True
            print(f"[note_v2] BucketCache loaded: {len(self._cache)} buckets", flush=True)
        finally:
            conn.close()

    def ensure_loaded(self):
        """Fail-fast for batch: raise if cannot load."""
        if not self._loaded:
            self.load()
        if not self._cache:
            raise RuntimeError("BucketCache empty after load — abort batch")

    def lookup(self, wine):
        """Cascata B: return best bucket or None."""
        if not self._loaded:
            return None

        tipo = (wine.get("tipo") or "").strip().lower()
        if not tipo:
            return None

        sub_regiao = (wine.get("sub_regiao") or "").strip().lower()
        regiao = (wine.get("regiao") or "").strip().lower()
        pais = (wine.get("pais") or "").strip().lower()
        vinicola = (wine.get("produtor") or wine.get("vinicola") or "").strip().lower()

        # Tier 1: sub_regiao + tipo
        if sub_regiao:
            b = self._cache.get(("sub_regiao_tipo", f"{sub_regiao}_{tipo}"))
            if b and b["bucket_n"] >= 10:
                return b

        # Tier 2: regiao + tipo
        if regiao:
            b = self._cache.get(("regiao_tipo", f"{regiao}_{tipo}"))
            if b and b["bucket_n"] >= 10:
                return b

        # Tier 3: pais + tipo
        if pais:
            b = self._cache.get(("pais_tipo", f"{pais}_{tipo}"))
            if b and b["bucket_n"] >= 10:
                return b

        # Tier 4: vinicola + tipo
        if vinicola:
            b = self._cache.get(("vinicola_tipo", f"{vinicola}_{tipo}"))
            if b and b["bucket_n"] >= 2:
                return b

        return None

    @property
    def size(self):
        return len(self._cache)


# Singleton for web runtime
_bucket_cache = BucketCache()


def get_bucket_lookup():
    """Web runtime: lazy load with graceful degradation."""
    if not _bucket_cache._loaded:
        try:
            _bucket_cache.load()
        except Exception as e:
            print(f"[note_v2] BucketCache load failed (graceful): {e}", flush=True)
    return _bucket_cache.lookup
