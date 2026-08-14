from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from installer_core import (
    AdbClient,
    InstallerEngine,
    InstallerError,
    prepare_runtime_payload,
    verify_payload,
)
from installer_gui import normalize_exception, run_gui


def run_cli(args: argparse.Namespace) -> int:
    log_lines: list[dict[str, object]] = []
    client: Optional[AdbClient] = None

    def log(level: str, message: str, progress: Optional[int]) -> None:
        log_lines.append(
            {
                "time": datetime.now().isoformat(timespec="seconds"),
                "level": level,
                "message": message,
                "progress": progress,
            }
        )

    report: dict[str, object] = {"success": False, "action": args.cli}
    exit_code = 1
    try:
        embedded_payload = verify_payload()
        report["payload"] = {name: str(path) for name, path in embedded_payload.items()}
        if args.cli == "bundle-check":
            report["success"] = True
            report["message"] = "All embedded resources passed SHA-256 verification."
            exit_code = 0
        else:
            payload = prepare_runtime_payload(embedded_payload)
            client = AdbClient(payload)
            engine = InstallerEngine(client, payload)
            if args.cli == "status":
                scan = engine.scan(log)
                devices = []
                for info in scan.devices:
                    item = dict(info.__dict__)
                    item["installation_status"] = info.installation_status
                    item["has_manager_components"] = info.has_manager_components
                    devices.append(item)
                report["devices"] = devices
                report["message"] = scan.message
                report["success"] = True
                exit_code = 0
            elif args.cli in {"install", "uninstall"}:
                if not args.accept_risk:
                    raise InstallerError(
                        "risk_not_accepted",
                        "CLI operation requires --accept-risk.",
                    )
                if not args.serial:
                    raise InstallerError("serial_missing", "CLI operation requires --serial.")
                if args.cli == "install":
                    operation = engine.install(args.serial, log)
                else:
                    operation = engine.uninstall(args.serial, log)
                report["success"] = operation.success
                report["message"] = operation.message
                report["warnings"] = operation.warnings
                exit_code = 0 if operation.success else 1
    except Exception as exc:
        error = normalize_exception(exc)
        report["error"] = {
            "code": error.code,
            "message": error.message,
            "technical": error.technical,
            "remedies": list(error.remedies),
        }
    if client is not None:
        client.shutdown_owned_server(log)
    report["log"] = log_lines
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report_file:
        Path(args.report_file).write_text(output, encoding="utf-8")
    elif sys.stdout:
        print(output)
    return exit_code


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument(
        "--cli",
        choices=("bundle-check", "status", "install", "uninstall"),
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--serial", help=argparse.SUPPRESS)
    parser.add_argument("--accept-risk", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--report-file", help=argparse.SUPPRESS)
    return parser


def main() -> int:
    args = build_argument_parser().parse_args()
    if args.cli:
        return run_cli(args)
    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
