from __future__ import annotations

import argparse
import json
import os

from .models import ProviderConfig, TransactionRequest


def main() -> None:
    parser = argparse.ArgumentParser(prog="pid-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve", help="Run the P&ID-Agent API and web app")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--reload", action="store_true")

    subparsers.add_parser("mcp", help="Run the MCP server over stdio")
    subparsers.add_parser("transaction-schema", help="Print the transaction JSON schema")

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
    matrix_parser.add_argument("--output", default="", help="Optional JSON report path")

    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn

        uvicorn.run("agentcad.main:app", host=args.host, port=args.port, reload=args.reload)
    elif args.command == "mcp":
        from .mcp_server import main as mcp_main

        mcp_main()
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
        )
        report = run_model_matrix(request, SymbolRegistry())
        payload = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
        if args.output:
            from pathlib import Path

            Path(args.output).write_text(payload + "\n", encoding="utf-8")
        print(payload)
        raise SystemExit(0 if report.accepted else 2)
    else:
        print(json.dumps(TransactionRequest.model_json_schema(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
