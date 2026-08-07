"""Remove the pressure_transmitter symbol definition and all its instances.

Deletes:
- the symbol definition from standard_symbols.json
- vision_semantic_planner.py references (manual cleanup afterwards)
- every pressure_transmitter symbol element and its attached connectors
  across all documents in the live database

Usage: python scripts/remove_pressure_transmitter.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
SYMBOL_KEY = "pressure_transmitter"
STD_SYMBOLS = Path(__file__).resolve().parent.parent / "backend" / "agentcad" / "data" / "standard_symbols.json"


def main() -> int:
    client = httpx.Client(base_url=BASE, timeout=30.0)

    # 1) Remove symbol definition from standard_symbols.json
    raw = STD_SYMBOLS.read_text(encoding="utf-8")
    data = json.loads(raw)
    symbols = data if isinstance(data, list) else data.get("symbols", data.get("items", []))
    before = len(symbols)
    symbols = [s for s in symbols if s.get("key") != SYMBOL_KEY]
    removed_def = before - len(symbols)
    if isinstance(data, list):
        data = symbols
    else:
        data["symbols"] = symbols if "symbols" in data else symbols
        if "items" in data:
            data["items"] = symbols
    STD_SYMBOLS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[definition] removed {removed_def} entry from standard_symbols.json")

    # 2) Remove instances + attached connectors from every document
    docs = client.get("/api/v2/documents").json()
    total_instances = 0
    total_connectors = 0
    total_docs = 0

    for doc in docs:
        doc_id = doc["id"]
        full = client.get(f"/api/v2/documents/{doc_id}").json()
        elements = full["elements"]

        pt_ids = {
            e["id"]
            for e in elements
            if e.get("type") == "symbol" and e.get("symbol_key") == SYMBOL_KEY
        }
        if not pt_ids:
            continue

        # Find connectors attached to any pressure_transmitter
        conn_ids = set()
        for e in elements:
            if e.get("type") != "connector":
                continue
            src = e.get("source") or {}
            tgt = e.get("target") or {}
            if src.get("element_id") in pt_ids or tgt.get("element_id") in pt_ids:
                conn_ids.add(e["id"])

        ops = []
        for cid in conn_ids:
            ops.append({"op": "delete_element", "element_id": cid})
        for pid in pt_ids:
            ops.append({"op": "delete_element", "element_id": pid})

        if not ops:
            continue

        revision = full["revision"]
        resp = client.post(
            f"/api/v2/documents/{doc_id}/transactions",
            json={
                "expected_revision": revision,
                "label": f"remove {SYMBOL_KEY} instances and attached connectors",
                "source": "system",
                "operations": ops,
            },
        )
        if resp.status_code != 200:
            print(f"  [{doc['name']}] FAILED: {resp.status_code} {resp.text[:200]}")
            continue

        total_instances += len(pt_ids)
        total_connectors += len(conn_ids)
        total_docs += 1
        print(f"  [{doc['name']}] removed {len(pt_ids)} instance(s), {len(conn_ids)} connector(s)")

    print(
        f"\n[done] {total_docs} document(s), "
        f"{total_instances} instance(s), {total_connectors} connector(s) removed"
    )
    print("\nNext: manually clean vision_semantic_planner.py references, then run tests.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
