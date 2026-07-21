# Continuous integration

GitHub Actions runs deterministic validation on every pull request and every push to `main`.

## Automated jobs

The workflow in `.github/workflows/ci.yml` runs three bounded Ubuntu jobs:

- **Backend · Python 3.11** installs `.[mcp,dev]`, runs `ruff check backend`, then `pytest -q`;
- **Frontend · Node 24** installs the locked npm dependency graph with `npm ci`, runs the frontend pure-function suite, then the production TypeScript/Vite build;
- **Browser acceptance · Chromium** installs the project and locked frontend dependencies, restores the Playwright browser cache keyed by `package-lock.json`, installs Chromium/runtime dependencies, builds the deterministic E2E bundle, and runs the engineering E2E, visual regression, and 500-element performance smoke suites.

The backend runner installs the Cairo runtime required by SVG/PNG export tests. The browser job starts a real FastAPI service and production Vite preview with an isolated SQLite database. It never uses a real model-provider API key or user project data. Agent scenarios use deterministic test data and a test-only preview injection bridge.

Retries and timeouts are explicit: Playwright uses one worker, at most one retry in CI, a 45-second per-test limit, bounded web-server startup, and a 30-minute job limit. Core scenarios are not conditionally skipped. On failure, the job uploads screenshots, traces, videos, the HTML report, and diagnostics for seven days.

Detailed local commands, visual baseline review, and trace inspection are documented in [`browser-e2e-visual-acceptance.md`](browser-e2e-visual-acceptance.md).

## Manual acceptance checks

The following remain manual because they require external services, credentials, subjective engineering review, other platforms, or longer execution time:

- real-provider `pid-agent model-matrix` runs;
- complex production drawing review;
- 1000/2500/5000-element browser benchmarks;
- non-Chromium/Linux headed acceptance;
- approval of intentional visual changes before snapshot updates.

Manual reports should be committed under `reports/` only after confirming that API keys, authorization headers, model prompts, local paths, and confidential engineering data are absent.
