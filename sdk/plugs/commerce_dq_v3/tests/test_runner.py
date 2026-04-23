from __future__ import annotations

from pathlib import Path

import sdk.plugs.commerce_dq_v3.runner as runner


def test_summary_writer_includes_state(tmp_path: Path):
    payload = tmp_path / "payload.jsonl"
    payload.write_text("", encoding="utf-8")
    bundle = type(
        "Bundle",
        (),
        {
            "state": "blocked_external_host",
            "notes": ["x"],
            "command_hint": "cmd",
            "unresolved_domains": ["amazon.com"],
        },
    )()
    md = runner._summary_md(
        "amazon_mirror",
        "run1",
        bundle,
        None,
        payload,
        dry_run=True,
        transport="local",
    )
    assert "blocked_external_host" in md
    assert "amazon.com" in md
    assert "dry_run" in md
