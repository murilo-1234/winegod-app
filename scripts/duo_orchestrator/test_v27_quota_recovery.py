"""Testes do V2.7 — Quota exhaustion autonoma com health-ping.

Rodar com:
    python -m unittest scripts/duo_orchestrator/test_v27_quota_recovery.py -v

Sem dependencias externas (stdlib apenas). Sem chamada real a Claude/Codex.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "duo_orchestrator"))

import importlib.util


def _load_orchestrator_module():
    spec = importlib.util.spec_from_file_location(
        "orchestrator_mod",
        str(ROOT / "scripts" / "duo_orchestrator" / "orchestrator.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_viewer_module():
    spec = importlib.util.spec_from_file_location(
        "session_viewer_mod",
        str(ROOT / "scripts" / "duo_orchestrator" / "session_viewer.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class QuotaClassifierTest(unittest.TestCase):
    """_classify_error deve detectar QUOTA antes de TRANSIENT ou UNKNOWN."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_orchestrator_module()

    def _make(self, stderr="", stdout="", ok=False):
        return {
            "ok": ok,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": 0 if ok else 1,
        }

    def test_credit_balance_too_low(self):
        r = self._make(stderr="Error: Your credit balance is too low to access the Claude API")
        self.assertEqual(self.mod._classify_error(r), "QUOTA")

    def test_insufficient_credits(self):
        r = self._make(stderr="insufficient_credits: please recharge")
        self.assertEqual(self.mod._classify_error(r), "QUOTA")

    def test_out_of_credits(self):
        r = self._make(stderr="You are out of credits")
        self.assertEqual(self.mod._classify_error(r), "QUOTA")

    def test_quota_exceeded(self):
        r = self._make(stderr="quota_exceeded for this billing period")
        self.assertEqual(self.mod._classify_error(r), "QUOTA")

    def test_http_402(self):
        r = self._make(stderr="HTTP 402 Payment Required")
        self.assertEqual(self.mod._classify_error(r), "QUOTA")

    def test_payment_required(self):
        r = self._make(stderr="payment required to continue")
        self.assertEqual(self.mod._classify_error(r), "QUOTA")

    def test_low_balance(self):
        r = self._make(stderr="low balance on account")
        self.assertEqual(self.mod._classify_error(r), "QUOTA")

    def test_quota_not_confused_with_rate_limit(self):
        # Rate limit NAO eh quota — eh transitorio comum (API sobrecarregada,
        # nao falta de credito).
        r = self._make(stderr="rate_limit exceeded, try again later")
        self.assertEqual(self.mod._classify_error(r), "TRANSIENT")

    def test_quota_not_confused_with_500(self):
        r = self._make(stderr="API Error: 500 internal server error")
        self.assertEqual(self.mod._classify_error(r), "TRANSIENT")

    def test_ok_always_wins(self):
        r = self._make(ok=True, stderr="credit balance too low (ignored)")
        self.assertEqual(self.mod._classify_error(r), "OK")

    def test_unknown_error_stays_unknown(self):
        r = self._make(stderr="some random bug not in any pattern")
        self.assertEqual(self.mod._classify_error(r), "UNKNOWN")


class QuotaBackoffScheduleTest(unittest.TestCase):
    """Schedule deve ser 1min, 10min, 30min, 30min, 30min... (teto)."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_orchestrator_module()

    def test_schedule_values(self):
        self.assertEqual(self.mod.QUOTA_BACKOFF_SCHEDULE_S[0], 60)
        self.assertEqual(self.mod.QUOTA_BACKOFF_SCHEDULE_S[1], 600)
        self.assertEqual(self.mod.QUOTA_BACKOFF_SCHEDULE_S[2], 1800)

    def test_ceiling_at_30min(self):
        # Para qualquer quota_attempt >= 3 (indice 2+), deve ficar em 1800s.
        sched = self.mod.QUOTA_BACKOFF_SCHEDULE_S
        for attempt in [3, 5, 10, 100]:
            idx = min(attempt - 1, len(sched) - 1)
            self.assertEqual(sched[idx], 1800,
                             f"attempt {attempt} deveria ser 30min, veio {sched[idx]}")


class QuotaSessionStateTest(unittest.TestCase):
    """SessionState deve ter os campos quota_* com defaults seguros."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_orchestrator_module()

    def test_defaults_quota_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            ss = self.mod.SessionState(tmp)
            self.assertEqual(ss.data.get("quota_attempt"), 0)
            self.assertIsNone(ss.data.get("quota_since"))
            self.assertIsNone(ss.data.get("quota_last_error"))
            self.assertIsNone(ss.data.get("quota_next_ping_at"))

    def test_quota_fields_persist_through_save_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            ss = self.mod.SessionState(tmp)
            ss.data["session_id"] = "S-TEST"
            ss.set(
                quota_attempt=2,
                quota_since="2026-04-16T23:00:00",
                quota_last_error="credit balance too low",
                quota_next_ping_at="2026-04-16T23:30:00",
            )
            ss2 = self.mod.SessionState(tmp)
            self.assertTrue(ss2.load())
            self.assertEqual(ss2.data.get("quota_attempt"), 2)
            self.assertEqual(ss2.data.get("quota_last_error"),
                             "credit balance too low")


class QuotaHealthPingTest(unittest.TestCase):
    """Health-ping retorna True/False baseado na classificacao."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_orchestrator_module()

    def _with_patched_claude(self, fake_call, expected):
        mod = self.mod
        original = mod.call_claude
        try:
            mod.call_claude = fake_call
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".log", delete=False, encoding="utf-8"
            ) as tmp:
                log_path = tmp.name
            try:
                result = mod._quota_health_ping("claude", log_path)
                self.assertEqual(result, expected)
            finally:
                os.unlink(log_path)
        finally:
            mod.call_claude = original

    def test_ping_true_when_api_ok(self):
        self._with_patched_claude(
            lambda p, cwd=None, timeout_s=None: {
                "ok": True, "stdout": "ok", "stderr": "", "exit_code": 0,
            },
            expected=True,
        )

    def test_ping_false_when_still_quota(self):
        self._with_patched_claude(
            lambda p, cwd=None, timeout_s=None: {
                "ok": False, "stdout": "",
                "stderr": "credit balance too low", "exit_code": 1,
            },
            expected=False,
        )

    def test_ping_pessimistic_on_exception(self):
        def boom(*a, **k):
            raise RuntimeError("binario missing")
        self._with_patched_claude(boom, expected=False)

    def test_ping_true_on_transient_error(self):
        # Se o ping bater TRANSIENT (API 500), NAO e quota — podemos sair
        # do backoff de quota. O erro real reaparece na call seguinte e
        # entra no backoff TRANSIENT normal.
        self._with_patched_claude(
            lambda p, cwd=None, timeout_s=None: {
                "ok": False, "stdout": "",
                "stderr": "API Error: 503", "exit_code": 1,
            },
            expected=True,
        )


class QuotaViewerNarrativeTest(unittest.TestCase):
    """Viewer deve mostrar linguagem de CREDITO quando quota_attempt > 0."""

    @classmethod
    def setUpClass(cls):
        cls.viewer = _load_viewer_module()

    def test_retry_backoff_with_quota_shows_credit_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = {
                "state": "RETRY_BACKOFF",
                "current_round": 13,
                "retry_count": 0,
                "quota_attempt": 2,
                "quota_since": "2026-04-16T23:00:00",
                "quota_last_error": "credit balance too low",
                "quota_next_ping_at": "2026-04-16T23:40:00",
                "next_retry_at": "2026-04-16T23:40:00",
                "paused_reason": "quota esgotada: credit balance too low",
            }
            headline, detail, what_to_do = self.viewer.humanize_state_v2(
                "RETRY_BACKOFF", state, tmp, checkpoint_md="")
            self.assertIn("Creditos", headline)
            self.assertIn("recarga", headline)
            self.assertIn("ping", headline)
            self.assertIn("1min", detail)
            self.assertIn("10min", detail)
            self.assertIn("30min", detail)
            self.assertIn("sozinha", detail)
            self.assertIn("Recarregue", what_to_do)

    def test_retry_backoff_without_quota_keeps_original_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = {
                "state": "RETRY_BACKOFF",
                "current_round": 5,
                "retry_count": 3,
                "quota_attempt": 0,  # NAO eh quota
                "next_retry_at": "2026-04-16T23:40:00",
                "paused_reason": "erro transitorio: API Error: 500",
            }
            headline, detail, what_to_do = self.viewer.humanize_state_v2(
                "RETRY_BACKOFF", state, tmp, checkpoint_md="")
            self.assertIn("API com problema", headline)
            self.assertNotIn("Creditos", headline)


if __name__ == "__main__":
    unittest.main()
