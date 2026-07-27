# Codex Handoff

Date: 2026-07-27

## Current State

The P&ID-Agent web and agent workflow fixes are ready to hand off and have been prepared for Git push.

Main branch: `main`

Remote: `origin https://github.com/yichensunjoe/PID-Agent.git`

Local service status:

- Existing main service: `pid-agent serve --host 0.0.0.0 --port 8000`
- Experience service relaunched: `pid-agent serve --host 0.0.0.0 --port 8001`
- Experience service database: `/Users/joe/Documents/Codex/projects/active/P009-PID-Agent/data/pid-agent.db`
- Experience service timeout: `PID_AGENT_AGENT_TIMEOUT_SECONDS=600`
- Health check: `http://127.0.0.1:8001/health` returned ok

Runtime logs under `logs/` are intentionally ignored and should not be committed.

## What Changed

- Replaced `window.prompt()` document creation with an in-app create document dialog so the embedded browser can create drawings.
- Added backend runtime config at `GET /api/v2/agent/runtime-config` and wired the frontend timeout input to the actual server-side limit.
- Changed provider connection testing from `/models`-only to `/models` plus one minimal chat completion, reducing false positives when a model is listed but not usable.
- Tightened semantic planner and compiler behavior for P&ID instrument taps:
  - repeated instrument labels are rejected at planning/model validation time;
  - instrument branch style now inherits the main line unless explicitly overridden;
  - instrument and root valve placement uses actual rotated port coordinates for precise vertical alignment.
- Corrected OPC-in visual direction while keeping the process port semantics intact.
- Hid transmitter symbols from the visible built-in library and agent catalog while preserving the definitions for old documents.
- Added regression tests for runtime config, provider completion tests, repeated instrument labels, instrument tap alignment, provider compatibility, and visible symbol library filtering.
- Added documentation for the real web-agent experience, MCP/web coordination, and the LongCat exact reproduction prompt.

## Important Documents

- `docs/usage-experience-web-agent-2026-07-27.md`
- `docs/usage-experience-mcp-web.md`
- `docs/longcat-exact-condenser-replica-prompt.md`
- `tasks/2026-07-27-web-agent-fixes.md`

## LongCat Reproduction

LongCat-2.0 generated `LongCat复现-严格对齐废气冷凝器-20260727` in one LLM revision without manual drawing edits.

Key facts:

- LongCat document ID: `doc_53d1ba949772`
- Baseline document ID: `doc_9d09bcff3da0`
- Revision history: `0 -> 1`, `source=llm`
- Semantic operations: 48
- Planning duration: about 106.8 seconds
- Visual and topology comparison against the baseline: 0 differences in element IDs, coordinates, dimensions, rotations, ports, connector waypoints, flow direction, labels, and styles

The two stored JSON snapshots are not byte-for-byte identical because the baseline carries extra non-rendering metadata and manual routing provenance. The visible drawing and engineering topology are identical.

## Verification Already Run

- Related backend tests: 21 passed
- Frontend unit tests: 85 passed
- Frontend production build: passed
- Full backend suite: 220 passed, with 3 known local Cairo/PDF/PNG environment failures
- Symbol quality harness: 3/3 passed, 57 visible symbols rendered
- Web health check on `8001`: passed

## Follow-Up Ideas

- Add a post-generation requirement checker so a legal transaction can still be rejected when it misses the user's engineering intent.
- Improve long-running agent progress with elapsed time, active phase, effective timeout, and cancellation state.
- Extend label collision checks across internal symbol labels, generated annotations, and independent text elements.
- Consider a durable service launcher for the `8001` experience profile if it will remain a daily workflow.
