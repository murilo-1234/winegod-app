"""Test Fase 3: discovery_log migration + log_discovery() + integration.

Runs offline (no DB): python -m tests.test_discovery_log
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import services.discovery as disc_mod
from services.discovery import log_discovery
import routes.chat as chat_mod


# ============================================================
# 1. Migration file validation
# ============================================================

def test_migration_file_exists():
    """010_discovery_log.sql should exist."""
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "database", "migrations", "010_discovery_log.sql",
    )
    assert os.path.exists(path), f"Migration file not found: {path}"


def test_migration_has_table():
    """Migration should create discovery_log table."""
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "database", "migrations", "010_discovery_log.sql",
    )
    content = open(path).read()
    assert "CREATE TABLE" in content
    assert "discovery_log" in content


def test_migration_has_on_delete_set_null():
    """FK should use ON DELETE SET NULL."""
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "database", "migrations", "010_discovery_log.sql",
    )
    content = open(path).read()
    assert "ON DELETE SET NULL" in content


def test_migration_has_3_indexes():
    """Migration should create 3 indexes."""
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "database", "migrations", "010_discovery_log.sql",
    )
    content = open(path).read()
    assert "idx_discovery_status" in content
    assert "idx_discovery_created" in content
    assert "idx_discovery_channel" in content


# ============================================================
# 2. log_discovery() unit tests (mocked DB)
# ============================================================

class _FakeCursor:
    def __init__(self):
        self.executed = []

    def execute(self, query, params=None):
        self.executed.append({"query": query, "params": params})


class _FakeConn:
    def __init__(self, fail_on_commit=False):
        self.cursor_obj = _FakeCursor()
        self.committed = False
        self.rolled_back = False
        self._fail_on_commit = fail_on_commit

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        if self._fail_on_commit:
            raise RuntimeError("DB commit failed")
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def _mock_db(fail_on_commit=False):
    """Returns (fake_conn, mock_get, mock_release) for patching db.connection."""
    conn = _FakeConn(fail_on_commit=fail_on_commit)
    released = [False]

    def mock_get():
        return conn

    def mock_release(c):
        released[0] = True

    return conn, mock_get, mock_release, released


def _run_log_discovery_with_mock_db(items, session_id="test-session", channel="pdf", latency_ms=None, fail_on_commit=False):
    """Run log_discovery with mocked DB connection."""
    conn, mock_get, mock_release, released = _mock_db(fail_on_commit=fail_on_commit)

    # We need to patch the imports inside log_discovery
    # log_discovery does: from db.connection import get_connection, release_connection
    # So we patch the module-level refs after import
    import importlib
    # Reload to get fresh import
    import db.connection as db_conn_mod
    orig_get = db_conn_mod.get_connection
    orig_release = db_conn_mod.release_connection

    db_conn_mod.get_connection = mock_get
    db_conn_mod.release_connection = mock_release
    try:
        log_discovery(session_id, items, channel, latency_ms=latency_ms)
    finally:
        db_conn_mod.get_connection = orig_get
        db_conn_mod.release_connection = orig_release

    return conn, released


def test_log_confirmed_with_note():
    """log_discovery should insert with final_status='with_note' for confirmed_with_note."""
    items = [{
        "ocr": {"name": "Alamos Malbec", "producer": "Catena", "price": "R$ 89"},
        "wine": {"id": 42},
        "status": "confirmed_with_note",
    }]
    conn, released = _run_log_discovery_with_mock_db(items)
    assert conn.committed
    assert released[0]
    assert len(conn.cursor_obj.executed) == 1
    params = conn.cursor_obj.executed[0]["params"]
    assert params[0] == "test-session"  # session_id
    assert params[1] == "pdf"  # source_channel
    assert params[2] == "Alamos Malbec"  # raw_name
    assert params[3] == "Catena"  # raw_producer
    assert params[7] == "with_note"  # final_status
    assert params[6] == 42  # resolved_wine_id


def test_log_confirmed_no_note():
    """log_discovery should insert with final_status='without_note' for confirmed_no_note."""
    items = [{
        "ocr": {"name": "Test Wine"},
        "wine": {"id": 10},
        "status": "confirmed_no_note",
    }]
    conn, _ = _run_log_discovery_with_mock_db(items)
    params = conn.cursor_obj.executed[0]["params"]
    assert params[7] == "without_note"


def test_log_visual_only():
    """log_discovery should insert with final_status='not_found' for visual_only."""
    items = [{
        "ocr": {"name": "Unknown Wine"},
        "status": "visual_only",
    }]
    conn, _ = _run_log_discovery_with_mock_db(items)
    params = conn.cursor_obj.executed[0]["params"]
    assert params[7] == "not_found"
    assert params[6] is None  # no wine.id


def test_log_extras_correctly():
    """log_discovery should pack OCR extras into JSONB."""
    items = [{
        "ocr": {"name": "Wine", "price": "R$ 50", "vintage": "2020", "region": "Mendoza", "grape": "Malbec"},
        "status": "visual_only",
    }]
    conn, _ = _run_log_discovery_with_mock_db(items)
    params = conn.cursor_obj.executed[0]["params"]
    extras = json.loads(params[4])
    assert extras["price"] == "R$ 50"
    assert extras["vintage"] == "2020"
    assert extras["region"] == "Mendoza"
    assert extras["grape"] == "Malbec"


def test_log_enrichment_raw():
    """log_discovery should store enriched_data as enrichment_raw."""
    items = [{
        "ocr": {"name": "Wine"},
        "wine": {"id": 42},
        "status": "confirmed_with_note",
        "enriched_data": {"name": "Corrected Wine", "producer": "Prod"},
    }]
    conn, _ = _run_log_discovery_with_mock_db(items)
    params = conn.cursor_obj.executed[0]["params"]
    enrichment = json.loads(params[5])
    assert enrichment["name"] == "Corrected Wine"


def test_log_latency_ms():
    """log_discovery should pass latency_ms to the insert."""
    items = [{"ocr": {"name": "Wine"}, "status": "visual_only"}]
    conn, _ = _run_log_discovery_with_mock_db(items, latency_ms=1500)
    params = conn.cursor_obj.executed[0]["params"]
    assert params[8] == 1500  # latency_ms


def test_log_rollback_on_error():
    """log_discovery should rollback and NOT raise on commit error."""
    items = [{"ocr": {"name": "Wine"}, "status": "visual_only"}]
    conn, released = _run_log_discovery_with_mock_db(items, fail_on_commit=True)
    assert conn.rolled_back
    assert released[0]
    assert not conn.committed


def test_log_always_releases_connection():
    """log_discovery should always call release_connection, even on error."""
    items = [{"ocr": {"name": "Wine"}, "status": "visual_only"}]
    _, released = _run_log_discovery_with_mock_db(items, fail_on_commit=True)
    assert released[0]


def test_log_empty_items_noop():
    """log_discovery with empty list should not touch DB."""
    # Just verify it doesn't raise
    log_discovery("session", [], "pdf")


# ============================================================
# 3. Integration: chat.py calls log_discovery
# ============================================================

class _FakeTrace:
    def step(self, name):
        return self
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def _make_wine(**kwargs):
    defaults = {
        "id": 1, "nome": "Test Wine", "produtor": "Test Producer",
        "safra": "2020", "tipo": "tinto", "pais_nome": "Argentina",
        "regiao": "Mendoza", "vivino_rating": 4.2, "preco_min": 50,
        "preco_max": 80, "moeda": "BRL", "winegod_score": 3.8,
        "winegod_score_type": "verified", "nota_wcf": 4.1,
        "nota_wcf_sample_size": 150,
    }
    defaults.update(kwargs)
    return defaults


def _noop_discover(unresolved_items, trace=None, initial_seen_ids=None):
    return {"newly_resolved": [], "still_unresolved": list(unresolved_items or []), "stats": {}}


def _noop_auto_create(unresolved_items, source_channel="chat", session_id=None, initial_seen_ids=None):
    return {"newly_resolved": [], "still_unresolved": list(unresolved_items or []), "stats": {}}


def _mock_resolve_returning(resolved_items, unresolved_items):
    def fake(ocr_result):
        return {
            "resolved_wines": [it["wine"] for it in resolved_items],
            "unresolved": [it["ocr"].get("name", "?") for it in unresolved_items],
            "resolved_items": list(resolved_items),
            "unresolved_items": list(unresolved_items),
            "timing_ms": 10,
        }
    return fake


def _run_process_media_with_log_spy(data, message="test", extra_mocks=None):
    """Run _process_media and capture log_discovery calls."""
    import tools.media as media_mod

    log_calls = []
    orig_log = chat_mod.log_discovery

    def spy_log(session_id, items, source_channel, latency_ms=None):
        log_calls.append({
            "session_id": session_id,
            "items": items,
            "source_channel": source_channel,
            "latency_ms": latency_ms,
        })

    mocks_to_apply = {
        "discover_unknowns": _noop_discover,
        "auto_create_unknowns": _noop_auto_create,
    }
    if extra_mocks:
        mocks_to_apply.update(extra_mocks)

    originals = {}
    mock_targets = {
        "process_pdf": [(media_mod, "process_pdf"), (chat_mod, "process_pdf")],
        "process_video": [(media_mod, "process_video"), (chat_mod, "process_video")],
        "resolve_wines_from_ocr": [(chat_mod, "resolve_wines_from_ocr")],
        "discover_unknowns": [(chat_mod, "discover_unknowns")],
        "auto_create_unknowns": [(chat_mod, "auto_create_unknowns")],
    }

    for key, fn in mocks_to_apply.items():
        if key in mock_targets:
            for mod, attr in mock_targets[key]:
                originals[(mod, attr)] = getattr(mod, attr)
                setattr(mod, attr, fn)

    chat_mod.log_discovery = spy_log
    originals[(chat_mod, "log_discovery")] = orig_log

    try:
        trace = _FakeTrace()
        result = chat_mod._process_media(data, message, trace, session_id="test-sid")
        return result, log_calls
    finally:
        for (mod, attr), orig in originals.items():
            setattr(mod, attr, orig)


def test_pdf_calls_log_discovery():
    """PDF rich path should call log_discovery with source_channel='pdf' and session_id."""
    wine = _make_wine()
    resolved_items = [{"ocr": {"name": "Known"}, "wine": wine, "status": "confirmed_with_note"}]
    unresolved_items = [{"ocr": {"name": "Unknown"}, "status": "visual_only"}]

    (msg, photo_mode), log_calls = _run_process_media_with_log_spy(
        {"pdf": "base64data"},
        extra_mocks={
            "process_pdf": lambda b: {
                "status": "success", "description": "test",
                "extraction_method": "native_text", "was_truncated": False,
                "pages_processed": 1,
                "wines": [{"name": "Known"}, {"name": "Unknown"}],
            },
            "resolve_wines_from_ocr": _mock_resolve_returning(resolved_items, unresolved_items),
        },
    )

    assert len(log_calls) == 1
    assert log_calls[0]["source_channel"] == "pdf"
    assert log_calls[0]["session_id"] == "test-sid"
    assert len(log_calls[0]["items"]) == 2  # 1 resolved + 1 unresolved


def test_video_calls_log_discovery():
    """Video rich path should call log_discovery with source_channel='video'."""
    wine = _make_wine()
    resolved_items = [{"ocr": {"name": "Known"}, "wine": wine, "status": "confirmed_with_note"}]

    (msg, photo_mode), log_calls = _run_process_media_with_log_spy(
        {"video": "base64data"},
        extra_mocks={
            "process_video": lambda b: {
                "status": "success",
                "wines": [{"name": "Known"}],
                "wine_count": 1,
                "frames_analyzed": 3,
                "description": "Bottles",
            },
            "resolve_wines_from_ocr": _mock_resolve_returning(resolved_items, []),
        },
    )

    assert len(log_calls) == 1
    assert log_calls[0]["source_channel"] == "video"
    assert log_calls[0]["session_id"] == "test-sid"


def test_text_calls_log_discovery():
    """Text extraction should call log_discovery with source_channel='text'."""
    wine = _make_wine()
    resolved_items = [{"ocr": {"name": "Known"}, "wine": wine, "status": "confirmed_with_note"}]

    log_calls = []
    orig_log = chat_mod.log_discovery
    orig_extract = chat_mod.extract_wines_from_text
    orig_resolve = chat_mod.resolve_wines_from_ocr
    orig_discover = chat_mod.discover_unknowns
    orig_auto = chat_mod.auto_create_unknowns
    orig_text_looks = chat_mod._text_looks_wine_related

    def spy_log(session_id, items, source_channel, latency_ms=None):
        log_calls.append({"session_id": session_id, "source_channel": source_channel, "items": items})

    chat_mod.log_discovery = spy_log
    chat_mod.extract_wines_from_text = lambda text: {"wines": [{"name": "Known"}], "wine_count": 1, "status": "success"}
    chat_mod._text_looks_wine_related = lambda text, **kw: True
    chat_mod.resolve_wines_from_ocr = _mock_resolve_returning(resolved_items, [])
    chat_mod.discover_unknowns = _noop_discover
    chat_mod.auto_create_unknowns = _noop_auto_create

    try:
        trace = _FakeTrace()
        wine_text = "Carta de Vinhos tinto branco reserva malbec cabernet " * 5
        result = chat_mod._try_text_wine_extraction(wine_text, trace, session_id="text-sid")
    finally:
        chat_mod.log_discovery = orig_log
        chat_mod.extract_wines_from_text = orig_extract
        chat_mod.resolve_wines_from_ocr = orig_resolve
        chat_mod.discover_unknowns = orig_discover
        chat_mod.auto_create_unknowns = orig_auto
        chat_mod._text_looks_wine_related = orig_text_looks

    assert result is not None
    assert len(log_calls) == 1
    assert log_calls[0]["source_channel"] == "text"
    assert log_calls[0]["session_id"] == "text-sid"


def test_pdf_fallback_does_not_log():
    """PDF fallback (no wines) should NOT call log_discovery."""
    (msg, photo_mode), log_calls = _run_process_media_with_log_spy(
        {"pdf": "base64data"},
        extra_mocks={
            "process_pdf": lambda b: {
                "status": "success", "description": "No wines",
                "extraction_method": "native_text", "was_truncated": False,
                "pages_processed": 1,
                "wines": [],
            },
        },
    )

    assert len(log_calls) == 0, "Fallback path should not log"


def test_log_receives_final_items_after_discovery():
    """Log should receive items in their FINAL state (after discovery merge)."""
    wine = _make_wine(id=1)
    discovery_wine = _make_wine(id=2, nome="Enriched")

    resolved_items = [{"ocr": {"name": "Known"}, "wine": wine, "status": "confirmed_with_note"}]
    unresolved_items = [{"ocr": {"name": "Was Unknown"}, "status": "visual_only"}]

    def mock_discover(unresolved_items, trace=None, initial_seen_ids=None):
        return {
            "newly_resolved": [{
                "ocr": unresolved_items[0]["ocr"],
                "wine": discovery_wine,
                "status": "confirmed_with_note",
                "enriched": True,
                "enriched_data": {"name": "Enriched"},
            }],
            "still_unresolved": [],
            "stats": {},
        }

    (msg, photo_mode), log_calls = _run_process_media_with_log_spy(
        {"pdf": "base64data"},
        extra_mocks={
            "process_pdf": lambda b: {
                "status": "success", "description": "test",
                "extraction_method": "native_text", "was_truncated": False,
                "pages_processed": 1,
                "wines": [{"name": "Known"}, {"name": "Was Unknown"}],
            },
            "resolve_wines_from_ocr": _mock_resolve_returning(resolved_items, unresolved_items),
            "discover_unknowns": mock_discover,
        },
    )

    assert len(log_calls) == 1
    # Final state: 2 resolved (original + discovery), 0 unresolved
    items = log_calls[0]["items"]
    assert len(items) == 2
    statuses = [it["status"] for it in items]
    assert "visual_only" not in statuses, "After discovery, the formerly unresolved should be confirmed"


# ============================================================
# 4. Wording and photo_mode unchanged
# ============================================================

def test_pdf_wording_unchanged_after_logging():
    """PDF context should still have document wording, not broken by logging."""
    wine = _make_wine()
    resolved_items = [{"ocr": {"name": "Known"}, "wine": wine, "status": "confirmed_with_note"}]

    (msg, photo_mode), _ = _run_process_media_with_log_spy(
        {"pdf": "base64data"},
        extra_mocks={
            "process_pdf": lambda b: {
                "status": "success", "description": "test",
                "extraction_method": "native_text", "was_truncated": False,
                "pages_processed": 1,
                "wines": [{"name": "Known"}],
            },
            "resolve_wines_from_ocr": _mock_resolve_returning(resolved_items, []),
        },
    )

    assert photo_mode is False
    assert "REGRAS CRITICAS DESTE PDF" in msg


# --- Runner ---

if __name__ == "__main__":
    tests = [
        # migration
        test_migration_file_exists,
        test_migration_has_table,
        test_migration_has_on_delete_set_null,
        test_migration_has_3_indexes,
        # log_discovery unit
        test_log_confirmed_with_note,
        test_log_confirmed_no_note,
        test_log_visual_only,
        test_log_extras_correctly,
        test_log_enrichment_raw,
        test_log_latency_ms,
        test_log_rollback_on_error,
        test_log_always_releases_connection,
        test_log_empty_items_noop,
        # integration
        test_pdf_calls_log_discovery,
        test_video_calls_log_discovery,
        test_text_calls_log_discovery,
        test_pdf_fallback_does_not_log,
        test_log_receives_final_items_after_discovery,
        # wording
        test_pdf_wording_unchanged_after_logging,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            import traceback
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
