from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import ProviderConfig, TransactionRequest


def _default_database_path() -> Path:
    root = Path(__file__).resolve().parents[2]
    return Path(
        os.getenv(
            "PID_AGENT_DATABASE_PATH",
            os.getenv("AGENTCAD_DATABASE_PATH", str(root / "data" / "pid-agent.db")),
        )
    )


def _add_database_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--database",
        type=Path,
        default=None,
        help="SQLite database path; defaults to PID_AGENT_DATABASE_PATH",
    )


def _json_payload(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _run_database_command(args: argparse.Namespace) -> None:
    from .database_recovery import (
        DatabaseRecoveryError,
        create_backup,
        database_info,
        restore_backup,
    )

    database_path = args.database or _default_database_path()
    try:
        if args.database_command == "info":
            payload = {"ok": True, "database": asdict(database_info(database_path, migrate=True))}
        elif args.database_command == "backup":
            result = create_backup(database_path, args.output, overwrite=args.overwrite)
            payload = {"ok": True, "backup": asdict(result)}
        elif args.database_command == "restore":
            result = restore_backup(
                args.input,
                database_path,
                expected_instance_id=args.expect_instance_id,
                allow_instance_mismatch=args.allow_instance_mismatch,
            )
            payload = {"ok": True, "restore": asdict(result)}
        else:  # pragma: no cover - argparse guarantees a subcommand
            raise AssertionError(f"unsupported database command: {args.database_command}")
    except DatabaseRecoveryError as exc:
        print(
            _json_payload(
                {
                    "ok": False,
                    "error": {
                        "code": exc.code,
                        "message": str(exc),
                    },
                }
            ),
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
    print(_json_payload(payload))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="pid-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve", help="Run the P&ID-Agent API and web app")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--reload", action="store_true")

    subparsers.add_parser("mcp", help="Run the MCP server over stdio")
    subparsers.add_parser("transaction-schema", help="Print the transaction JSON schema")

    database_parser = subparsers.add_parser(
        "db", help="Inspect, back up, or restore the SQLite document database"
    )
    database_subparsers = database_parser.add_subparsers(
        dest="database_command", required=True
    )
    info_parser = database_subparsers.add_parser(
        "info", help="Migrate if needed and print database identity and schema information"
    )
    _add_database_argument(info_parser)

    backup_parser = database_subparsers.add_parser(
        "backup", help="Create an integrity-checked online SQLite backup"
    )
    _add_database_argument(backup_parser)
    backup_parser.add_argument("--output", type=Path, required=True, help="Destination .pidbak file")
    backup_parser.add_argument(
        "--overwrite", action="store_true", help="Replace an existing regular backup file"
    )

    restore_parser = database_subparsers.add_parser(
        "restore", help="Verify and atomically restore a SQLite backup"
    )
    _add_database_argument(restore_parser)
    restore_parser.add_argument("--input", type=Path, required=True, help="Source .pidbak file")
    restore_parser.add_argument(
        "--expect-instance-id",
        default=None,
        help=(
            "Explicitly confirm the backup instance id; required for a missing/corrupt target "
            "or an intentional instance override"
        ),
    )
    restore_parser.add_argument(
        "--allow-instance-mismatch",
        action="store_true",
        help="Allow replacing a different database instance when paired with confirmation",
    )

    matrix_parser = subparsers.add_parser(
        "model-matrix",
        help="Run the semantic acceptance matrix against an OpenAI-compatible provider",
    )
    matrix_parser.add_argument("--base-url", required=True)
    matrix_parser.add_argument("--model", required=True)
    matrix_parser.add_argument(
        "--api-key",
        default="",
        help="API key value; prefer --api-key-env to avoid command history exposure",
    )
    matrix_parser.add_argument(
        "--api-key-env",
        default="PID_AGENT_MATRIX_API_KEY",
        help="Environment variable containing the API key",
    )
    matrix_parser.add_argument("--timeout", type=float, default=120)
    matrix_parser.add_argument("--repetitions", type=int, default=3)
    matrix_parser.add_argument("--max-replans", type=int, default=3)
    matrix_parser.add_argument(
        "--include-complex-diagram",
        action="store_true",
        help="Add the 30-50 element complex full-diagram generation scenario",
    )
    matrix_parser.add_argument("--output", default="", help="Optional JSON report path")

    quality_parser = subparsers.add_parser(
        "quality-harness",
        help="Run deterministic symbol, topology, and Agent-contract checks without a model",
    )
    quality_parser.add_argument(
        "--symbol-path",
        action="append",
        type=Path,
        default=[],
        help="Additional symbol JSON file or directory; may be repeated",
    )
    quality_parser.add_argument("--output", type=Path, default=None, help="Optional JSON report path")

    args = parser.parse_args(argv)
    if args.command == "serve":
        import uvicorn

        uvicorn.run("agentcad.main:app", host=args.host, port=args.port, reload=args.reload)
    elif args.command == "mcp":
        from .mcp_server import main as mcp_main

        mcp_main()
    elif args.command == "db":
        _run_database_command(args)
    elif args.command == "model-matrix":
        from .model_acceptance import ModelMatrixRequest, run_model_matrix
        from .symbols import SymbolRegistry

        api_key = args.api_key or os.getenv(args.api_key_env, "")
        request = ModelMatrixRequest(
            provider=ProviderConfig(
                base_url=args.base_url,
                model=args.model,
                api_key=api_key or None,
                timeout_seconds=args.timeout,
            ),
            repetitions=args.repetitions,
            max_replans=args.max_replans,
            include_complex_diagram=args.include_complex_diagram,
        )
        report = run_model_matrix(request, SymbolRegistry())
        payload = _json_payload(report.model_dump(mode="json"))
        if args.output:
            Path(args.output).write_text(payload + "\n", encoding="utf-8")
        print(payload)
        raise SystemExit(0 if report.accepted else 2)
    elif args.command == "quality-harness":
        from .quality_harness import run_quality_harness, symbol_load_failure_report
        from .symbols import SymbolCatalogLoadError, SymbolRegistry

        try:
            report = run_quality_harness(SymbolRegistry(search_paths=args.symbol_path))
        except SymbolCatalogLoadError as exc:
            report = symbol_load_failure_report(exc)
        payload = _json_payload(report.model_dump(mode="json", by_alias=True))
        if args.output:
            args.output.write_text(payload + "\n", encoding="utf-8")
        print(payload)
        raise SystemExit(0 if report.passed else 2)
    else:
        print(_json_payload(TransactionRequest.model_json_schema()))


if __name__ == "__main__":
    main()
