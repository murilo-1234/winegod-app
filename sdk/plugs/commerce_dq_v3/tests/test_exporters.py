from __future__ import annotations

from sdk.plugs.commerce_dq_v3.exporters import export_tier2_to_dq_stub


def test_tier2_stub_reports_blocked_contract():
    bundle = export_tier2_to_dq_stub(source="tier2_chat1")
    assert bundle.state == "blocked_contract_missing"
    assert "tier2_chat1" in bundle.command_hint
