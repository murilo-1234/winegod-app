from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = REPO_ROOT / "sdk"

for entry in (str(REPO_ROOT), str(SDK_ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from winegod_scraper_sdk import Reporter, load_manifest  # noqa: E402
from winegod_scraper_sdk.connectors import TelemetryDelivery  # noqa: E402


def load_envs() -> None:
    for path in (REPO_ROOT / ".env", REPO_ROOT / "backend" / ".env"):
        if path.exists():
            load_dotenv(path, override=False)


def _normalize_command(parts: list[str]) -> list[str]:
    if parts and parts[0] == "--":
        return parts[1:]
    return parts


def main() -> int:
    parser = argparse.ArgumentParser(description="Shadow runner generico para scrapers externos")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--log", required=True)
    parser.add_argument("--heartbeat-seconds", type=float, default=30.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    command = _normalize_command(args.command)
    if not command:
        parser.error("missing command after --")

    workdir = Path(args.workdir).resolve()
    log_path = Path(args.log).resolve()
    manifest = load_manifest(args.manifest)

    if args.dry_run:
        print(f"shadow_wrapper=ok manifest={manifest.scraper_id}")
        print(f"workdir={workdir}")
        print(f"log={log_path}")
        print("command=" + " ".join(command))
        return 0

    load_envs()
    base_url = os.environ.get("OPS_BASE_URL")
    token = os.environ.get("OPS_TOKEN")
    if not base_url or not token:
        print("OPS_BASE_URL/OPS_TOKEN missing", file=sys.stderr)
        return 2

    reporter = Reporter(
        manifest=manifest,
        delivery=TelemetryDelivery.from_env(default_url=base_url),
    )
    reporter.register()
    reporter.start_run(
        run_params={
            "shadow": True,
            "dry_run": False,
            "workdir": str(workdir),
            "command_preview": " ".join(command[:8])[:200],
        }
    )

    log_path.parent.mkdir(parents=True, exist_ok=True)
    started_at = time.time()
    try:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(
                f"[shadow] manifest={manifest.scraper_id} workdir={workdir} command={' '.join(command)}\n"
            )
            handle.flush()
            process = subprocess.Popen(
                command,
                cwd=workdir,
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
            )
            last_heartbeat = 0.0
            while True:
                now = time.time()
                if now - last_heartbeat >= max(args.heartbeat_seconds, 5.0):
                    reporter.heartbeat(
                        items_collected_so_far=0,
                        note=f"shadow_running pid={process.pid}",
                    )
                    last_heartbeat = now
                rc = process.poll()
                if rc is not None:
                    break
                time.sleep(2.0)
    except Exception as exc:
        reporter.fail(error_summary=f"shadow_wrapper_error: {type(exc).__name__}: {str(exc)[:500]}", status="failed")
        print(f"shadow wrapper failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3

    duration_ms = int((time.time() - started_at) * 1000)
    if rc == 0:
        reporter.event(
            code="shadow.process.exit",
            message=f"shadow success rc=0 duration_ms={duration_ms}",
            level="audit",
            payload_pointer=str(log_path),
        )
        reporter.end(
            status="success",
            items_extracted=0,
            items_valid_local=0,
            items_sent=0,
            items_final_inserted=0,
            batches_total=1,
        )
        return 0

    reporter.fail(
        error_summary=f"shadow_process_exit={rc}; duration_ms={duration_ms}; log={log_path}",
        status="failed",
    )
    print(f"shadow command exited with rc={rc}", file=sys.stderr)
    return int(rc)


if __name__ == "__main__":
    raise SystemExit(main())
