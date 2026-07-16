from __future__ import annotations

import argparse
import json

from .models import TransactionRequest


def main() -> None:
    parser = argparse.ArgumentParser(prog="pid-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve", help="Run the P&ID-Agent API and web app")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--reload", action="store_true")

    subparsers.add_parser("mcp", help="Run the MCP server over stdio")
    subparsers.add_parser("transaction-schema", help="Print the transaction JSON schema")

    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn

        uvicorn.run("agentcad.main:app", host=args.host, port=args.port, reload=args.reload)
    elif args.command == "mcp":
        from .mcp_server import main as mcp_main

        mcp_main()
    else:
        print(json.dumps(TransactionRequest.model_json_schema(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
